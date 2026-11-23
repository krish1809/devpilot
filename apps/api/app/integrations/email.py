"""Outgoing email behind a tiny provider interface.

Backends (``EMAIL_BACKEND``):

- ``console`` — local development. Prints the message to stdout, which *is* the
  developer's inbox: this is the one place a reset link is printed on purpose.
  In production (``ENVIRONMENT=production``) it refuses to print the body and
  only warns that email isn't configured, so a missing setting fails closed
  (no link leaks into hosted logs) without taking the API down.
- ``resend`` — production. Sends through the Resend HTTPS API (Render's free
  plan blocks outbound SMTP ports, so an HTTP API is the reliable option).
  ``EMAIL_FROM`` must be an address on a domain verified in Resend: Resend's
  ``onboarding@resend.dev`` test sender only delivers to the Resend account
  owner's own inbox and rejects every other recipient with a 403.

Tests override :func:`get_email_sender` with :class:`MemoryEmailSender`.
Callers never log message bodies. A failure carries the provider's own error
text (e.g. "domain is not verified"), so a misconfiguration is visible in the
logs instead of a bare status code; it never contains the message body.

Check a deployment end to end with ``python -m scripts.send_test_email you@example.com``.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
RESEND_TEST_DOMAIN = "@resend.dev"
_MAX_PROVIDER_ERROR = 300
# A provider could echo part of the request back in its error. Reset links must
# never reach the logs, so URLs and token values are blanked first.
_REDACT = (
    (re.compile(r"https?://\S+"), "[url]"),
    (re.compile(r"token=[^\s\"'&<]+"), "token=[redacted]"),
)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


class EmailError(Exception):
    """Delivery failed. The message never contains the email body."""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._production = settings.environment == "production"

    def send(self, message: EmailMessage) -> None:
        if self._production:
            logger.warning(
                "EMAIL_BACKEND=console in production: an email was not sent "
                "(configure EMAIL_BACKEND=resend)."
            )
            return
        sys.stdout.write(
            "\n----- email (console backend; dev only) -----\n"
            f"To: {message.to}\nSubject: {message.subject}\n\n{message.text}\n"
            "---------------------------------------------\n"
        )
        sys.stdout.flush()


class ResendEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._key = settings.resend_api_key
        self._from = settings.email_from
        self._timeout = settings.email_timeout_seconds

    def send(self, message: EmailMessage) -> None:
        # Checked at send time (in the background), so a missing key can't turn
        # the public endpoint into a 500 that differs from the normal response.
        if not self._key:
            raise EmailError("RESEND_API_KEY is not set")
        try:
            response = httpx.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "from": self._from,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.text,
                    "html": message.html,
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise EmailError(f"email provider unreachable ({type(exc).__name__})") from None
        if response.status_code >= 400:
            raise EmailError(
                f"email provider returned HTTP {response.status_code}: {_provider_error(response)}"
            )


def _provider_error(response: httpx.Response) -> str:
    """The provider's error message (Resend: {"name", "message"}), shortened."""
    try:
        body = response.json()
        text = body.get("message") or body.get("name") or response.text
    except (ValueError, AttributeError):
        text = response.text
    text = " ".join(str(text).split())
    for pattern, replacement in _REDACT:
        text = pattern.sub(replacement, text)
    return text[:_MAX_PROVIDER_ERROR] or "(no details)"


def email_config_problems(settings: Settings) -> list[str]:
    """Plain-language reasons the configured backend can't deliver real email.

    Logged once at startup and printed by scripts/send_test_email.py. Never
    includes secret values.
    """
    problems: list[str] = []
    if settings.email_backend == "console":
        if settings.environment == "production":
            problems.append(
                "EMAIL_BACKEND=console in production: no email is sent. Set EMAIL_BACKEND=resend."
            )
        return problems
    if not settings.resend_api_key:
        problems.append("RESEND_API_KEY is not set.")
    if RESEND_TEST_DOMAIN in settings.email_from.lower():
        problems.append(
            "EMAIL_FROM uses Resend's test sender (@resend.dev), which only delivers to the "
            "Resend account owner. Verify your own domain in Resend and send from it."
        )
    if "@" not in settings.email_from or "localhost" in settings.email_from:
        problems.append("EMAIL_FROM is not a real sender address on your verified domain.")
    return problems


class MemoryEmailSender:
    """Collects messages in a list (tests)."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)


def get_email_sender() -> EmailSender:
    """FastAPI dependency: the configured backend."""
    settings = get_settings()
    if settings.email_backend == "resend":
        return ResendEmailSender(settings)
    return ConsoleEmailSender(settings)
