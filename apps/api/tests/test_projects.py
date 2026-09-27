from fastapi.testclient import TestClient

from tests.conftest import register_and_login

BASE = "/api/v1/projects"


def _create(client, headers, name="DevPilot", description="AI platform"):
    return client.post(BASE, json={"name": name, "description": description}, headers=headers)


# --------------------------------------------------------------------------- #
# Authentication is required
# --------------------------------------------------------------------------- #
def test_create_requires_auth(client: TestClient) -> None:
    assert client.post(BASE, json={"name": "x"}).status_code == 401


def test_list_requires_auth(client: TestClient) -> None:
    assert client.get(BASE).status_code == 401


def test_get_requires_auth(client: TestClient) -> None:
    assert client.get(f"{BASE}/1").status_code == 401


# --------------------------------------------------------------------------- #
# CRUD (authenticated)
# --------------------------------------------------------------------------- #
def test_create_project(client: TestClient, auth_headers: dict) -> None:
    response = _create(client, auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["owner_id"] > 0
    assert body["name"] == "DevPilot"
    assert body["description"] == "AI platform"


def test_create_project_rejects_empty_name(client: TestClient, auth_headers: dict) -> None:
    response = client.post(BASE, json={"name": ""}, headers=auth_headers)

    assert response.status_code == 422


def test_list_projects_empty(client: TestClient, auth_headers: dict) -> None:
    response = client.get(BASE, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_returns_created(client: TestClient, auth_headers: dict) -> None:
    _create(client, auth_headers, name="A")
    _create(client, auth_headers, name="B")

    response = client.get(BASE, headers=auth_headers)

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["A", "B"]


def test_get_project(client: TestClient, auth_headers: dict) -> None:
    project_id = _create(client, auth_headers).json()["id"]

    response = client.get(f"{BASE}/{project_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == project_id


def test_get_project_not_found(client: TestClient, auth_headers: dict) -> None:
    response = client.get(f"{BASE}/999999", headers=auth_headers)

    assert response.status_code == 404


def test_update_project(client: TestClient, auth_headers: dict) -> None:
    project_id = _create(client, auth_headers).json()["id"]

    response = client.patch(
        f"{BASE}/{project_id}", json={"description": "updated"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["description"] == "updated"


def test_delete_project(client: TestClient, auth_headers: dict) -> None:
    project_id = _create(client, auth_headers).json()["id"]

    response = client.delete(f"{BASE}/{project_id}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get(f"{BASE}/{project_id}", headers=auth_headers).status_code == 404


# --------------------------------------------------------------------------- #
# Cross-user isolation (RBAC by ownership)
# --------------------------------------------------------------------------- #
def test_users_only_see_their_own_projects(client: TestClient, auth_headers: dict) -> None:
    _create(client, auth_headers, name="alice-project")
    bob = register_and_login(client, "bob@example.com")

    _create(client, bob, name="bob-project")

    alice_list = client.get(BASE, headers=auth_headers).json()
    bob_list = client.get(BASE, headers=bob).json()

    assert [p["name"] for p in alice_list] == ["alice-project"]
    assert [p["name"] for p in bob_list] == ["bob-project"]


def test_user_cannot_get_others_project(client: TestClient, auth_headers: dict) -> None:
    alice_project_id = _create(client, auth_headers).json()["id"]
    bob = register_and_login(client, "bob@example.com")

    # 404 (not 403) so we do not reveal that the project exists.
    assert client.get(f"{BASE}/{alice_project_id}", headers=bob).status_code == 404


def test_user_cannot_update_others_project(client: TestClient, auth_headers: dict) -> None:
    alice_project_id = _create(client, auth_headers).json()["id"]
    bob = register_and_login(client, "bob@example.com")

    response = client.patch(f"{BASE}/{alice_project_id}", json={"name": "hijacked"}, headers=bob)

    assert response.status_code == 404


def test_user_cannot_delete_others_project(client: TestClient, auth_headers: dict) -> None:
    alice_project_id = _create(client, auth_headers).json()["id"]
    bob = register_and_login(client, "bob@example.com")

    assert client.delete(f"{BASE}/{alice_project_id}", headers=bob).status_code == 404
    # Alice's project still exists.
    assert client.get(f"{BASE}/{alice_project_id}", headers=auth_headers).status_code == 200
