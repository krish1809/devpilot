"""Forgot-password / reset-password (docs/password-reset.md)."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.integrations import email as email_mod
from app.integrations.email import (
    ConsoleEmailSender,
    EmailError,
    EmailMessage,
    MemoryEmailSender,
    ResendEmailSender,
    get_email_sender,
)
from app.main import app as fastapi_app
from app.models.audit import AuditLog
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services.user import ensure_bootstrap_user

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"

EMAIL = "user@example.com"
OLD_PW = "old-password-1"
NEW_PW = "new-password-2"


@pytest.fixture()
def outbox() -> MemoryEmailSender:
    sender = MemoryEmailSender()
    fastapi_app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        yield sender
    finally:
        fastapi_app.dependency_overrides.pop(get_email_sender, None)


def _register(client: TestClient, email: str = EMAIL, password: str = OLD_PW) -> None:
    assert client.post(REGISTER, json={"email": email, "password": password}).status_code == 201


def _login(client: TestClient, email: str = EMAIL, password: str = OLD_PW) -> httpx.Response:
    return client.post(LOGIN, json={"email": email, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_from(message: EmailMessage) -> str:
    match = re.search(r"/reset-password#token=([A-Za-z0-9_-]+)", message.text)
    assert match, "reset link missing from email"
    return match.group(1)


def _request_token(client: TestClient, outbox: MemoryEmailSender, email: str = EMAIL) -> str:
    assert client.post(FORGOT, json={"email": email}).status_code == 202
    return _token_from(outbox.outbox[-1])


# --------------------------------------------------------------------------- #
# Requesting a reset
# --------------------------------------------------------------------------- #
def test_existing_and_unknown_emails_get_identical_responses(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    _register(client)

    known = client.post(FORGOT, json={"email": EMAIL})
    unknown = client.post(FORGOT, json={"email": "ghost@example.com"})
    malformed = client.post(FORGOT, json={"email": "not-an-email"})

    for response in (unknown, malformed):
        assert response.status_code == known.status_code == 202
        assert response.content == known.content
        assert response.headers.get("content-type") == known.headers.get("content-type")
    assert known.json()["detail"].startswith("If an account exists")
    # Only the real account got mail.
    assert [m.to for m in outbox.outbox] == [EMAIL]


def test_email_is_normalized_like_login(client: TestClient, outbox: MemoryEmailSender) -> None:
    _register(client)
    client.post(FORGOT, json={"email": "  USER@Example.com "})
    assert [m.to for m in outbox.outbox] == [EMAIL]


def test_link_uses_configured_frontend_url_and_a_fragment(
    client: TestClient, outbox: MemoryEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "frontend_url", "https://app.example.test")
    _register(client)
    client.post(FORGOT, json={"email": EMAIL})

    message = outbox.outbox[0]
    assert "https://app.example.test/reset-password#token=" in message.text
    assert "https://app.example.test/reset-password#token=" in message.html
    assert "?token=" not in message.text  # never in a query string (server logs)


def test_only_a_hash_of_the_token_is_stored(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    _register(client)
    raw = _request_token(client, outbox)

    row = db_session.scalar(select(PasswordResetToken))
    assert row is not None
    assert row.token_hash != raw
    assert row.token_hash == security.hash_url_token(raw)
    assert row.used_at is None
    ttl = row.expires_at - row.created_at
    assert timedelta(minutes=29) < ttl <= timedelta(minutes=31)


def test_demo_and_inactive_accounts_get_no_email(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    demo_email = get_settings().demo_user_email
    _register(client, email=demo_email)
    _register(client, email="inactive@example.com")
    db_session.execute(
        update(User).where(User.email == "inactive@example.com").values(is_active=False)
    )
    db_session.commit()

    for email in (demo_email, "inactive@example.com"):
        assert client.post(FORGOT, json={"email": email}).status_code == 202
    assert outbox.outbox == []
    assert db_session.scalar(select(PasswordResetToken)) is None


def test_delivery_failure_does_not_change_the_response(client: TestClient) -> None:
    class Failing:
        def send(self, message: EmailMessage) -> None:
            raise EmailError("email provider returned HTTP 500")

    fastapi_app.dependency_overrides[get_email_sender] = lambda: Failing()
    try:
        _register(client)
        known = client.post(FORGOT, json={"email": EMAIL})
        unknown = client.post(FORGOT, json={"email": "ghost@example.com"})
    finally:
        fastapi_app.dependency_overrides.pop(get_email_sender, None)
    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content


# --------------------------------------------------------------------------- #
# Redeeming a token
# --------------------------------------------------------------------------- #
def test_valid_reset_changes_the_password(client: TestClient, outbox: MemoryEmailSender) -> None:
    _register(client)
    token = _request_token(client, outbox)

    response = client.post(RESET, json={"token": token, "new_password": NEW_PW})

    assert response.status_code == 200
    assert _login(client, password=OLD_PW).status_code == 401
    assert _login(client, password=NEW_PW).status_code == 200


def test_reused_token_is_rejected(client: TestClient, outbox: MemoryEmailSender) -> None:
    _register(client)
    token = _request_token(client, outbox)
    assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 200

    again = client.post(RESET, json={"token": token, "new_password": "third-password"})

    assert again.status_code == 400
    assert "invalid or has expired" in again.json()["detail"]
    assert _login(client, password=NEW_PW).status_code == 200


def test_expired_token_is_rejected(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    _register(client)
    token = _request_token(client, outbox)
    db_session.execute(
        update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db_session.commit()

    response = client.post(RESET, json={"token": token, "new_password": NEW_PW})

    assert response.status_code == 400
    assert _login(client, password=OLD_PW).status_code == 200


@pytest.mark.parametrize("token", ["not-a-real-token", "x" * 43, "a"])
def test_unknown_token_is_rejected(client: TestClient, token: str) -> None:
    response = client.post(RESET, json={"token": token, "new_password": NEW_PW})
    assert response.status_code == 400
    assert "invalid or has expired" in response.json()["detail"]


def test_oversized_or_empty_token_fails_validation(client: TestClient) -> None:
    for token in ("", "x" * 129):
        assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 422


@pytest.mark.parametrize("weak", ["short", "", "x" * 129])
def test_weak_passwords_are_rejected_and_the_token_survives(
    client: TestClient, outbox: MemoryEmailSender, weak: str
) -> None:
    _register(client)
    token = _request_token(client, outbox)

    assert client.post(RESET, json={"token": token, "new_password": weak}).status_code == 422
    # A validation failure doesn't burn the link.
    assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 200


def test_reset_invalidates_other_outstanding_links(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    _register(client)
    first = _request_token(client, outbox)
    second = _request_token(client, outbox)
    assert first != second

    assert client.post(RESET, json={"token": second, "new_password": NEW_PW}).status_code == 200

    stale = client.post(RESET, json={"token": first, "new_password": "third-pass"})
    assert stale.status_code == 400
    rows = db_session.scalars(select(PasswordResetToken)).all()
    assert len(rows) == 2 and all(r.used_at is not None for r in rows)


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def test_tokens_issued_before_a_reset_stop_working(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    _register(client)
    old_jwt = _login(client).json()["access_token"]
    assert client.get(ME, headers=_bearer(old_jwt)).status_code == 200

    token = _request_token(client, outbox)
    assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 200

    assert client.get(ME, headers=_bearer(old_jwt)).status_code == 401
    new_jwt = _login(client, password=NEW_PW).json()["access_token"]
    assert client.get(ME, headers=_bearer(new_jwt)).status_code == 200


def test_requesting_a_reset_alone_keeps_sessions(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    _register(client)
    jwt = _login(client).json()["access_token"]
    _request_token(client, outbox)
    assert client.get(ME, headers=_bearer(jwt)).status_code == 200


def test_tokens_from_before_the_ver_claim_still_work(
    client: TestClient, db_session: Session
) -> None:
    """Sessions issued before this release (no `ver`) count as version 0."""
    _register(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    now = int(time.time())
    parts = [
        security._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()),
        security._b64url_encode(
            json.dumps({"sub": str(user.id), "iat": now, "exp": now + 60}).encode()
        ),
    ]
    signing_input = ".".join(parts).encode("ascii")
    legacy = ".".join([*parts, security._b64url_encode(security._sign(signing_input))])

    assert client.get(ME, headers=_bearer(legacy)).status_code == 200

    db_session.execute(update(User).values(token_version=1))
    db_session.commit()
    assert client.get(ME, headers=_bearer(legacy)).status_code == 401


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def test_forgot_password_is_rate_limited_per_ip(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    limit = get_settings().password_reset_ip_limit_max
    for i in range(limit):
        assert client.post(FORGOT, json={"email": f"u{i}@example.com"}).status_code == 202

    blocked = client.post(FORGOT, json={"email": "another@example.com"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.parametrize("registered", [True, False])
def test_forgot_password_is_rate_limited_per_email(
    client: TestClient, outbox: MemoryEmailSender, registered: bool
) -> None:
    """Same limit whether or not the account exists — a 429 reveals nothing."""
    settings = get_settings()
    assert settings.password_reset_email_limit_max < settings.password_reset_ip_limit_max
    if registered:
        _register(client)
    for _ in range(settings.password_reset_email_limit_max):
        assert client.post(FORGOT, json={"email": EMAIL}).status_code == 202
    assert client.post(FORGOT, json={"email": EMAIL}).status_code == 429
    # A different address from the same IP is still allowed.
    assert client.post(FORGOT, json={"email": "other@example.com"}).status_code == 202


def test_reset_password_is_rate_limited(client: TestClient) -> None:
    limit = get_settings().auth_rate_limit_max
    for _ in range(limit):
        client.post(RESET, json={"token": "guess", "new_password": NEW_PW})
    assert client.post(RESET, json={"token": "guess", "new_password": NEW_PW}).status_code == 429


# --------------------------------------------------------------------------- #
# Audit, showcase mode, bootstrap, email backends
# --------------------------------------------------------------------------- #
def test_reset_is_audited_without_secrets(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    _register(client)
    token = _request_token(client, outbox)
    client.post(FORGOT, json={"email": "ghost@example.com"})
    client.post(RESET, json={"token": token, "new_password": NEW_PW})

    rows = db_session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    actions = [r.action for r in rows]
    assert actions.count("user.password_reset.requested") == 2
    assert actions.count("user.password_reset.completed") == 1
    token_hash = security.hash_url_token(token)
    for row in rows:
        for secret in (token, token_hash, NEW_PW, OLD_PW):
            assert secret not in (row.detail or "")


def test_reset_flow_works_in_showcase_mode(
    client: TestClient, outbox: MemoryEmailSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(client)  # before demo mode: registration is refused there
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    refused = client.post(REGISTER, json={"email": "x@example.com", "password": NEW_PW})
    assert refused.status_code == 403

    token = _request_token(client, outbox)
    assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 200
    assert _login(client, password=NEW_PW).status_code == 200


def test_bootstrap_user_is_created_once_and_set_up_by_reset(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    created = ensure_bootstrap_user(db_session, "  Owner@Example.com ")
    assert created is not None and created.email == "owner@example.com"
    assert ensure_bootstrap_user(db_session, "owner@example.com") is None
    assert ensure_bootstrap_user(db_session, "") is None

    token = _request_token(client, outbox, email="owner@example.com")
    assert client.post(RESET, json={"token": token, "new_password": NEW_PW}).status_code == 200
    assert _login(client, email="owner@example.com", password=NEW_PW).status_code == 200


def test_console_backend_prints_in_dev_but_never_in_production(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    message = EmailMessage(to=EMAIL, subject="s", text="link #token=SECRET123", html="")
    settings = get_settings()

    ConsoleEmailSender(settings).send(message)
    assert "SECRET123" in capsys.readouterr().out

    monkeypatch.setattr(settings, "environment", "production")
    ConsoleEmailSender(settings).send(message)
    captured = capsys.readouterr()
    assert "SECRET123" not in captured.out + captured.err


def test_resend_backend_posts_to_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={"resend_api_key": "re_test", "email_from": "DevPilot <a@b.dev>"}
    )
    calls: list[dict] = []

    def fake_post(url: str, **kwargs):  # noqa: ANN003, ANN202
        calls.append({"url": url, **kwargs})
        return httpx.Response(200, json={"id": "1"})

    monkeypatch.setattr(email_mod.httpx, "post", fake_post)
    ResendEmailSender(settings).send(EmailMessage(to=EMAIL, subject="s", text="t", html="h"))

    assert calls[0]["url"] == email_mod.RESEND_URL
    assert calls[0]["headers"] == {"Authorization": "Bearer re_test"}
    assert calls[0]["json"]["to"] == [EMAIL]
    assert calls[0]["json"]["from"] == "DevPilot <a@b.dev>"


def test_resend_backend_errors_never_include_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"resend_api_key": "re_test"})
    monkeypatch.setattr(
        email_mod.httpx, "post", lambda *a, **k: httpx.Response(422, text="bad #token=SECRET")
    )
    with pytest.raises(EmailError) as excinfo:
        ResendEmailSender(settings).send(EmailMessage(to=EMAIL, subject="s", text="t", html="h"))
    assert "422" in str(excinfo.value) and "SECRET" not in str(excinfo.value)

    no_key = get_settings().model_copy(update={"resend_api_key": ""})
    with pytest.raises(EmailError):
        ResendEmailSender(no_key).send(EmailMessage(to=EMAIL, subject="s", text="t", html="h"))
