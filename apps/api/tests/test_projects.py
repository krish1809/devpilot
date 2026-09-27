from fastapi.testclient import TestClient

BASE = "/api/v1/projects"


def _create(client: TestClient, name: str = "DevPilot", description: str | None = "AI platform"):
    return client.post(BASE, json={"name": name, "description": description})


def test_create_project(client: TestClient) -> None:
    response = _create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "DevPilot"
    assert body["description"] == "AI platform"
    assert body["created_at"]
    assert body["updated_at"]


def test_create_project_without_description(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "NoDesc"})

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_project_rejects_empty_name(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "", "description": "x"})

    assert response.status_code == 422


def test_create_project_rejects_missing_name(client: TestClient) -> None:
    response = client.post(BASE, json={"description": "x"})

    assert response.status_code == 422


def test_create_project_rejects_overlong_name(client: TestClient) -> None:
    response = client.post(BASE, json={"name": "x" * 101})

    assert response.status_code == 422


def test_list_projects_empty(client: TestClient) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_returns_created(client: TestClient) -> None:
    _create(client, name="A")
    _create(client, name="B")

    response = client.get(BASE)

    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["A", "B"]


def test_get_project(client: TestClient) -> None:
    project_id = _create(client).json()["id"]

    response = client.get(f"{BASE}/{project_id}")

    assert response.status_code == 200
    assert response.json()["id"] == project_id


def test_get_project_not_found(client: TestClient) -> None:
    response = client.get(f"{BASE}/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_update_project(client: TestClient) -> None:
    project_id = _create(client).json()["id"]

    response = client.patch(f"{BASE}/{project_id}", json={"description": "updated"})

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "updated"
    assert body["name"] == "DevPilot"  # unchanged


def test_update_project_partial_name_only(client: TestClient) -> None:
    project_id = _create(client).json()["id"]

    response = client.patch(f"{BASE}/{project_id}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_update_project_rejects_empty_name(client: TestClient) -> None:
    project_id = _create(client).json()["id"]

    response = client.patch(f"{BASE}/{project_id}", json={"name": ""})

    assert response.status_code == 422


def test_update_project_not_found(client: TestClient) -> None:
    response = client.patch(f"{BASE}/999999", json={"name": "x"})

    assert response.status_code == 404


def test_delete_project(client: TestClient) -> None:
    project_id = _create(client).json()["id"]

    response = client.delete(f"{BASE}/{project_id}")

    assert response.status_code == 204
    assert client.get(f"{BASE}/{project_id}").status_code == 404


def test_delete_project_not_found(client: TestClient) -> None:
    response = client.delete(f"{BASE}/999999")

    assert response.status_code == 404


def test_project_persists_across_requests(client: TestClient) -> None:
    project_id = _create(client, name="Persisted").json()["id"]

    fetched = client.get(f"{BASE}/{project_id}").json()

    assert fetched["name"] == "Persisted"
