from fastapi.testclient import TestClient

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

CREDS = {"email": "user@example.com", "password": "supersecret"}


def _register(client: TestClient, **overrides):
    return client.post(REGISTER, json={**CREDS, **overrides})


def _login(client: TestClient, **overrides):
    return client.post(LOGIN, json={**CREDS, **overrides})


def _auth_header(client: TestClient) -> dict[str, str]:
    _register(client)
    token = _login(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_success(client: TestClient) -> None:
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["is_active"] is True
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_normalizes_email(client: TestClient) -> None:
    response = _register(client, email="  User@Example.COM ")

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = _register(client)

    assert response.status_code == 409


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = _register(client, email="not-an-email")

    assert response.status_code == 422


def test_register_rejects_short_password(client: TestClient) -> None:
    response = _register(client, password="short")

    assert response.status_code == 422


def test_login_success_returns_token(client: TestClient) -> None:
    _register(client)
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client: TestClient) -> None:
    _register(client)
    response = _login(client, password="wrongpassword")

    assert response.status_code == 401


def test_login_unknown_email(client: TestClient) -> None:
    response = _login(client, email="ghost@example.com")

    assert response.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get(ME).status_code == 401


def test_me_rejects_bad_token(client: TestClient) -> None:
    response = client.get(ME, headers={"Authorization": "Bearer garbage.token.here"})

    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient) -> None:
    headers = _auth_header(client)
    response = client.get(ME, headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
