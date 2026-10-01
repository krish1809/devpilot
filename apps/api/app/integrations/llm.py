"""Provider-neutral LLM interface with a Groq implementation.

Business logic depends only on `LLMProvider.complete(...)`; the concrete
provider and model are configuration. Groq exposes an OpenAI-compatible REST
API, so this is a thin client over `POST {base_url}/chat/completions`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings

_MAX_ATTEMPTS = 3  # network errors / 5xx
_BACKOFF_SECONDS = 1.5
_MAX_RATE_LIMIT_RETRIES = 6  # 429s (free tiers have tight tokens-per-minute limits)
_MAX_RATE_LIMIT_WAIT = 30.0
_TRY_AGAIN_RE = re.compile(r"try again in ([0-9.]+)\s*(ms|s)", re.IGNORECASE)


def _is_daily_quota(response: httpx.Response) -> bool:
    text = response.text.lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text


def _rate_limit_wait(response: httpx.Response, retry: int) -> float:
    """Seconds to wait before retrying a 429: Retry-After, else the provider's
    "try again in Xs" hint, else exponential backoff — always capped."""
    wait = None
    header = response.headers.get("retry-after")
    if header:
        try:
            wait = float(header)
        except ValueError:
            wait = None
    if wait is None:
        m = _TRY_AGAIN_RE.search(response.text)
        if m:
            wait = float(m.group(1)) / (1000 if m.group(2).lower() == "ms" else 1)
    if wait is None:
        wait = _BACKOFF_SECONDS * (2**retry)
    return min(max(wait, 0.5) + 0.5, _MAX_RATE_LIMIT_WAIT)


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(Exception):
    """Raised when a completion request fails."""


class LLMProvider(Protocol):
    """``complete`` returns the reply text. Providers may also expose
    ``last_usage`` ({"prompt_tokens", "completion_tokens"}) for cost tracking."""

    def complete(self, messages: list[Message], *, temperature: float = 0.0) -> str: ...


class GroqProvider:
    """Calls Groq's OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
    ) -> None:
        if not api_key:
            raise LLMError(
                "GROQ_API_KEY is not set. Add it to apps/api/.env before running the agent."
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self.last_usage: dict | None = None

    def complete(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Bounded retries: transient network/5xx errors, and 429 rate limits
        # (waiting as long as the provider asks, capped). Other 4xx (bad
        # key/model/request) are never retried since they will not recover.
        last_exc: Exception | None = None
        response: httpx.Response | None = None
        attempt = 0
        rate_limited = 0
        while True:
            attempt += 1
            try:
                response = httpx.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_BACKOFF_SECONDS * attempt)
                    continue
                raise LLMError(f"LLM request failed after {attempt} attempts: {exc}") from exc

            if response.status_code == 429 and _is_daily_quota(response):
                break  # a per-day quota won't recover by waiting seconds
            if response.status_code == 429 and rate_limited < _MAX_RATE_LIMIT_RETRIES:
                time.sleep(_rate_limit_wait(response, rate_limited))
                rate_limited += 1
                attempt -= 1  # rate limits don't consume transient-error attempts
                continue
            if response.status_code >= 500 and attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS * attempt)
                continue
            break

        if response is None:  # pragma: no cover - defensive
            raise LLMError(f"LLM request failed: {last_exc}")

        if response.status_code != 200:
            # Body may contain an error message but never the API key.
            raise LLMError(f"LLM returned {response.status_code}: {response.text[:300]}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Unexpected LLM response shape") from exc
        usage = data.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
        return content


def get_llm_provider() -> LLMProvider:
    """Build the configured provider. Only 'groq' is implemented so far."""
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.llm_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise LLMError(f"Unsupported LLM provider: {settings.llm_provider!r}")
