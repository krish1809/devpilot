from fastapi.testclient import TestClient

from app.core.config import get_settings

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"


def test_login_is_rate_limited(client: TestClient) -> None:
    max_requests = get_settings().auth_rate_limit_max
    payload = {"email": "nobody@example.com", "password": "wrongpassword"}

    # The first `max_requests` are allowed through (they return 401).
    for _ in range(max_requests):
        assert client.post(LOGIN, json=payload).status_code == 401

    # The next one is blocked.
    blocked = client.post(LOGIN, json=payload)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_register_and_login_limits_are_independent(client: TestClient) -> None:
    max_requests = get_settings().auth_rate_limit_max

    # Exhaust the login limit.
    for _ in range(max_requests):
        client.post(LOGIN, json={"email": "x@example.com", "password": "wrongpassword"})
    assert client.post(LOGIN, json={"email": "x@example.com", "password": "y"}).status_code == 429

    # Register uses a separate bucket and still works.
    assert (
        client.post(
            REGISTER, json={"email": "new@example.com", "password": "supersecret"}
        ).status_code
        == 201
    )
