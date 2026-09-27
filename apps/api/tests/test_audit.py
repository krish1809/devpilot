from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from tests.conftest import register_and_login

AUDIT_ME = "/api/v1/audit/me"
PROJECTS = "/api/v1/projects"


def test_audit_me_requires_auth(client: TestClient) -> None:
    assert client.get(AUDIT_ME).status_code == 401


def test_register_and_login_are_audited(client: TestClient, auth_headers: dict) -> None:
    events = client.get(AUDIT_ME, headers=auth_headers).json()
    actions = {e["action"] for e in events}

    assert "user.registered" in actions
    assert "user.login.succeeded" in actions


def test_project_creation_is_audited(client: TestClient, auth_headers: dict) -> None:
    client.post(PROJECTS, json={"name": "Tracked"}, headers=auth_headers)

    events = client.get(AUDIT_ME, headers=auth_headers).json()
    created = [e for e in events if e["action"] == "project.created"]

    assert len(created) == 1
    assert created[0]["detail"].startswith("project:")


def test_events_are_newest_first(client: TestClient, auth_headers: dict) -> None:
    client.post(PROJECTS, json={"name": "One"}, headers=auth_headers)

    events = client.get(AUDIT_ME, headers=auth_headers).json()
    ids = [e["id"] for e in events]

    assert ids == sorted(ids, reverse=True)


def test_users_only_see_their_own_events(client: TestClient, auth_headers: dict) -> None:
    client.post(PROJECTS, json={"name": "alice"}, headers=auth_headers)
    bob = register_and_login(client, "bob@example.com")

    bob_events = client.get(AUDIT_ME, headers=bob).json()
    bob_actions = [e["action"] for e in bob_events]

    # Bob sees his own registration/login, never Alice's project.created.
    assert "project.created" not in bob_actions
    assert "user.registered" in bob_actions


def test_failed_login_is_audited(client: TestClient, db_session: Session) -> None:
    client.post("/api/v1/auth/register", json={"email": "u@example.com", "password": "supersecret"})
    client.post("/api/v1/auth/login", json={"email": "u@example.com", "password": "wrongpass"})

    failed = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "user.login.failed")
    ).all()

    assert len(failed) == 1
    assert failed[0].user_id is None
