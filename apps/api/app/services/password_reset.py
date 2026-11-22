"""Forgot-password / reset-password (design: docs/password-reset.md).

- A reset token is 256 random bits; only its SHA-256 is stored, with an expiry
  and a ``used_at`` marker. The raw token leaves this module exactly once — in
  the email — and is never logged or audited.
- Redeeming a token is one transaction: lock the token row, check it, set the
  new password hash, mark every outstanding token for the user as used, and
  bump ``users.token_version`` so access tokens issued before the reset stop
  working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_url_token, hash_password, hash_url_token
from app.integrations.email import EmailError, EmailMessage, EmailSender
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.user import get_user_by_email

logger = logging.getLogger(__name__)


class InvalidResetTokenError(Exception):
    """The token doesn't exist, has expired, or was already used.

    Callers report all three the same way, so a response never says which.
    """


@dataclass(frozen=True)
class IssuedReset:
    user: User
    raw_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def issue_reset_token(db: Session, email: str) -> IssuedReset | None:
    """Create a reset token for ``email`` if it belongs to an eligible account.

    Returns ``None`` (and writes nothing) for unknown or inactive accounts and
    for the shared showcase demo user, whose address isn't ours to email.
    """
    settings = get_settings()
    user = get_user_by_email(db, email)
    if user is None or not user.is_active or user.email == settings.demo_user_email:
        return None

    raw, token_hash = generate_url_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=_now() + timedelta(minutes=settings.password_reset_token_ttl_minutes),
        )
    )
    db.commit()
    return IssuedReset(user=user, raw_token=raw)


def build_reset_email(to: str, raw_token: str) -> EmailMessage:
    settings = get_settings()
    # The token goes in the URL fragment: browsers never send fragments to the
    # server or in Referer headers, so it stays out of hosting access logs.
    link = f"{settings.frontend_url}/reset-password#token={raw_token}"
    minutes = settings.password_reset_token_ttl_minutes
    text = (
        "Someone asked to reset the password for your DevPilot account.\n\n"
        f"Choose a new password here (the link works once and expires in {minutes} minutes):\n"
        f"{link}\n\n"
        "If this wasn't you, ignore this email — your password won't change."
    )
    html = (
        "<p>Someone asked to reset the password for your DevPilot account.</p>"
        f'<p><a href="{escape(link)}">Choose a new password</a></p>'
        f"<p>The link works once and expires in {minutes} minutes.</p>"
        "<p>If this wasn't you, ignore this email — your password won't change.</p>"
    )
    return EmailMessage(to=to, subject="Reset your DevPilot password", text=text, html=html)


def send_reset_email(sender: EmailSender, to: str, raw_token: str) -> None:
    """Deliver the reset email. Runs as a background task after the response,
    so response time doesn't reveal whether an email was sent."""
    try:
        sender.send(build_reset_email(to, raw_token))
    except EmailError as exc:
        logger.error("Password reset email was not delivered: %s", exc)


def reset_password(db: Session, raw_token: str, new_password: str) -> User:
    """Redeem ``raw_token`` and set ``new_password``; raise InvalidResetTokenError."""
    row = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_url_token(raw_token))
        # Row lock: two concurrent requests with the same token serialize here,
        # and the second one sees used_at set.
        .with_for_update()
    )
    now = _now()
    if row is None or row.used_at is not None or row.expires_at <= now:
        db.rollback()
        raise InvalidResetTokenError

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        db.rollback()
        raise InvalidResetTokenError

    user.hashed_password = hash_password(new_password)
    user.token_version = User.token_version + 1  # atomic in SQL
    # Marks this token used and invalidates any other outstanding link.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.commit()
    db.refresh(user)
    return user
