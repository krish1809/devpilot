"""Phase 9: read-only showcase mode for the public deployment."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture()
def demo_mode(monkeypatch):  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "demo_mode", True)


def test_demo_login_is_hidden_outside_demo_mode(client: TestClient) -> None:
    assert client.get("/api/v1/config").json() == {"demo_mode": False}
    assert client.post("/api/v1/auth/demo").status_code == 404


def test_demo_visitors_get_a_read_only_session(client: TestClient, demo_mode) -> None:  # noqa: ANN001
    assert client.get("/api/v1/config").json() == {"demo_mode": True}
    token = client.post("/api/v1/auth/demo").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == "demo@devpilot.dev"
    assert client.get("/api/v1/tasks", headers=headers).status_code == 200
    assert client.get("/api/v1/evals", headers=headers).status_code == 200

    # Same demo user every time.
    again = client.post("/api/v1/auth/demo").json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {again}"}).json()
    assert me["email"] == "demo@devpilot.dev"


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/tasks"),
        ("post", "/api/v1/tasks/1/run"),
        ("post", "/api/v1/runs/1/approve"),
        ("post", "/api/v1/runs/1/resume"),
        ("post", "/api/v1/auth/register"),
        ("delete", "/api/v1/projects/1"),
        ("get", "/api/v1/github/repos"),
    ],
)
def test_showcase_refuses_writes_and_github(
    client: TestClient,
    demo_mode,
    method: str,
    path: str,  # noqa: ANN001
) -> None:
    resp = client.request(method.upper(), path, json={} if method == "post" else None)
    assert resp.status_code == 403 and "read-only showcase" in resp.json()["detail"]


def test_login_still_works_in_showcase(client: TestClient, demo_mode) -> None:  # noqa: ANN001
    resp = client.post("/api/v1/auth/login", json={"email": "x@y.dev", "password": "wrongpass"})
    assert resp.status_code == 401  # reached the handler, not blocked


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@host/db?sslmode=require", "postgresql://u:p@host/db?sslmode=require"],
)
def test_hosted_database_urls_use_the_psycopg_driver(given: str) -> None:
    from app.core.config import Settings

    assert Settings(database_url=given).database_url == (
        "postgresql+psycopg://u:p@host/db?sslmode=require"
    )
