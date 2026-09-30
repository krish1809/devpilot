"""Provider-neutral LLM interface with a Groq implementation.

Business logic depends only on `LLMProvider.complete(...)`; the concrete
provider and model are configuration. Groq exposes an OpenAI-compatible REST
API, so this is a thin client over `POST {base_url}/chat/completions`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.5


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(Exception):
    """Raised when a completion request fails."""


class LLMProvider(Protocol):
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

    def complete(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Bounded retries for transient network/5xx errors; never retry a 4xx
        # (bad key/model/request) since it will not recover.
        last_exc: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
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
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Unexpected LLM response shape") from exc


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
