"""Sign in with Google (docs/google-sign-in.md).

Tokens are signed here with a throwaway RSA key and verified by the real
JwksGoogleVerifier (only the JWKS download is replaced), so signature,
audience, issuer and expiry checks are all exercised for real.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations import google as google_mod
from app.models.audit import AuditLog
from app.models.user import User

GOOGLE = "/api/v1/auth/google"
ME = "/api/v1/auth/me"
CLIENT_ID = "test-client.apps.googleusercontent.com"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def google_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", CLIENT_ID)
    # Serve our test public key instead of downloading Google's JWKS.
    monkeypatch.setattr(
        google_mod._jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=_KEY.public_key()),
    )


def _credential(key=_KEY, **overrides) -> str:  # noqa: ANN001
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "Person@Gmail.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def _sign_in(client: TestClient, credential: str):  # noqa: ANN202
    return client.post(GOOGLE, json={"credential": credential})


def _me(client: TestClient, response) -> dict:  # noqa: ANN001
    token = response.json()["access_token"]
    return client.get(ME, headers={"Authorization": f"Bearer {token}"}).json()


def test_first_sign_in_creates_an_account(client: TestClient, db_session: Session) -> None:
    response = _sign_in(client, _credential())
    assert response.status_code == 200
    assert _me(client, response)["email"] == "person@gmail.com"

    user = db_session.scalar(select(User).where(User.email == "person@gmail.com"))
    assert user is not None and user.google_sub == "google-sub-1"
    actions = set(db_session.scalars(select(AuditLog.action)).all())
    assert {"user.registered", "user.login.succeeded"} <= actions


def test_second_sign_in_reuses_the_account_by_google_id(
    client: TestClient, db_session: Session
) -> None:
    first = _me(client, _sign_in(client, _credential()))
    # Same Google account, email changed on Google's side: still the same user.
    second = _me(client, _sign_in(client, _credential(email="renamed@gmail.com")))
    assert first["id"] == second["id"]
    assert db_session.scalar(select(User).where(User.google_sub == "google-sub-1")) is not None


def test_existing_password_account_is_linked(client: TestClient, db_session: Session) -> None:
    credentials = {"email": "person@gmail.com", "password": "pw-123456"}
    client.post("/api/v1/auth/register", json=credentials)
    response = _sign_in(client, _credential())
    assert response.status_code == 200
    assert _me(client, response)["email"] == "person@gmail.com"
    assert db_session.scalar(select(User.google_sub).where(User.email == "person@gmail.com")) == (
        "google-sub-1"
    )
    # Password login still works after linking.
    login = client.post("/api/v1/auth/login", json=credentials)
    assert login.status_code == 200


@pytest.mark.parametrize(
    "credential",
    [
        pytest.param(lambda: _credential(email_verified=False), id="unverified-email"),
        pytest.param(lambda: _credential(aud="someone-else.apps.googleusercontent.com"), id="aud"),
        pytest.param(lambda: _credential(iss="https://evil.example"), id="issuer"),
        pytest.param(lambda: _credential(exp=int(time.time()) - 3600), id="expired"),
        pytest.param(lambda: _credential(key=_OTHER_KEY), id="forged-signature"),
        pytest.param(lambda: _credential(sub=None), id="no-subject"),
        pytest.param(lambda: "not-a-jwt", id="garbage"),
    ],
)
def test_bad_tokens_are_rejected_with_one_message(
    client: TestClient, db_session: Session, credential
) -> None:  # noqa: ANN001
    response = _sign_in(client, credential())
    assert response.status_code == 401
    assert response.json()["detail"].startswith("Google sign-in failed")
    assert db_session.scalar(select(User).where(User.email == "person@gmail.com")) is None
    failed = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "user.login.failed")
    ).all()
    assert failed and failed[-1].detail.startswith("google:")


def test_hs256_token_signed_with_the_public_key_is_rejected(client: TestClient) -> None:
    """Algorithm confusion: only RS256 is accepted."""
    token = jwt.encode(
        {"iss": "accounts.google.com", "aud": CLIENT_ID, "sub": "x", "email": "a@b.c"},
        "a-symmetric-secret-that-is-long-enough!!",
        algorithm="HS256",
    )
    assert _sign_in(client, token).status_code == 401


def test_account_linked_to_another_google_id_is_not_relinked(client: TestClient) -> None:
    assert _sign_in(client, _credential()).status_code == 200
    other = _credential(sub="google-sub-2")  # different Google account, same email
    assert _sign_in(client, other).status_code == 401


def test_inactive_and_demo_accounts_cannot_sign_in(client: TestClient, db_session: Session) -> None:
    _sign_in(client, _credential())
    db_session.execute(
        User.__table__.update().where(User.email == "person@gmail.com").values(is_active=False)
    )
    db_session.commit()
    assert _sign_in(client, _credential()).status_code == 401

    demo = _credential(sub="demo-sub", email=get_settings().demo_user_email)
    assert _sign_in(client, demo).status_code == 401


def test_endpoint_is_off_without_a_client_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    assert _sign_in(client, _credential()).status_code == 404


def test_works_in_the_read_only_showcase(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    response = _sign_in(client, _credential())
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/v1/tasks", headers=headers).status_code == 200
    # Still read-only for everything else.
    assert client.post("/api/v1/projects", json={"name": "x"}, headers=headers).status_code == 403


def test_public_config_exposes_the_client_id(client: TestClient) -> None:
    assert client.get("/api/v1/config").json()["google_client_id"] == CLIENT_ID


def test_oversized_credential_is_rejected(client: TestClient) -> None:
    assert _sign_in(client, "x" * 5000).status_code == 422
