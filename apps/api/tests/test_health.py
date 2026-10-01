from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_preflight_is_allowed(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_disallows_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    # Middleware does not echo an allow-origin header for disallowed origins.
    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"


def test_root_describes_the_api(client) -> None:  # noqa: ANN001
    body = client.get("/").json()
    assert body["name"] == "DevPilot API" and body["docs"] == "/docs"
