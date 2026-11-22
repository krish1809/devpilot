"""Outgoing email behind a tiny provider interface.

Backends (``EMAIL_BACKEND``):

- ``console`` — local development. Prints the message to stdout, which *is* the
  developer's inbox: this is the one place a reset link is printed on purpose.
  In production (``ENVIRONMENT=production``) it refuses to print the body and
  only warns that email isn't configured, so a missing setting fails closed
  (no link leaks into hosted logs) without taking the API down.
- ``resend`` — production. Sends through the Resend HTTPS API (Render's free
  plan blocks outbound SMTP ports, so an HTTP API is the reliable option).

Tests override :func:`get_email_sender` with :class:`MemoryEmailSender`.
Callers never log message bodies; failures are logged by status code only.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


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
            raise EmailError(f"email provider returned HTTP {response.status_code}")


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
