import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import git_ops
from app.integrations.llm import Message
from app.sandbox.runner import SandboxResult
from app.services import agent as agent_service

TASKS = "/api/v1/tasks"


# --------------------------------------------------------------------------- #
# Endpoint auth + CRUD
# --------------------------------------------------------------------------- #
def test_tasks_require_auth(client: TestClient) -> None:
    assert client.get(TASKS).status_code == 401
    assert client.post(TASKS, json={}).status_code == 401


def _task_payload(**overrides) -> dict:
    base = {
        "repo_url": "https://example.test/repo.git",
        "test_command": "python -m unittest test_x",
        "target_path": "x.py",
    }
    return {**base, **overrides}


def test_create_and_list_task(client: TestClient, auth_headers: dict) -> None:
    created = client.post(TASKS, json=_task_payload(), headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["owner_id"] > 0
    assert body["target_path"] == "x.py"

    listed = client.get(TASKS, headers=auth_headers).json()
    assert [t["id"] for t in listed] == [body["id"]]


def test_create_task_validates_input(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(TASKS, json=_task_payload(repo_url=""), headers=auth_headers)
    assert resp.status_code == 422


def test_get_task_not_found(client: TestClient, auth_headers: dict) -> None:
    assert client.get(f"{TASKS}/999999", headers=auth_headers).status_code == 404


# --------------------------------------------------------------------------- #
# Orchestration logic (real local git clone, mocked sandbox, fake LLM)
# --------------------------------------------------------------------------- #
def _make_fixture_repo() -> str:
    repo = Path(tempfile.mkdtemp(prefix="devpilot_fixture_"))
    (repo / "calculator.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    (repo / "test_calculator.py").write_text(
        "import unittest\nfrom calculator import add\n"
        "class T(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n"
    )
    git_ops._run(["git", "init", "-q"], cwd=repo)
    git_ops._run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=repo)
    git_ops._run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=repo
    )
    return str(repo)


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, messages: list[Message], *, temperature: float = 0.0) -> str:
        return self._reply


def test_run_agent_produces_validated_run(db_session: Session, auth_headers: dict, monkeypatch):
    # auth_headers ensures a user (id 1) exists; create a task owned by them.
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    task = agent_service.create_task(
        db_session,
        owner.id,
        repo_url=_make_fixture_repo(),
        base_commit=None,
        test_command="python -m unittest test_calculator",
        target_path="calculator.py",
        description="fix add",
    )

    # Mock the sandbox: fail on the baseline run, pass after the patch.
    calls = {"n": 0}

    def fake_sandbox(workspace, command, **kwargs):  # noqa: ANN001, ANN003
        calls["n"] += 1
        return SandboxResult(
            passed=calls["n"] > 1, exit_code=0 if calls["n"] > 1 else 1, output="…"
        )

    monkeypatch.setattr(agent_service, "run_in_sandbox", fake_sandbox)

    fake = _FakeLLM("def add(a, b):\n    return a + b\n")
    run = agent_service.run_agent(db_session, task, llm=fake)

    assert run.status == "validated"
    assert run.test_passed is True
    assert "return a + b" in run.diff
    events = agent_service.list_run_events(db_session, run.id)
    assert [e.stage for e in events][:2] == ["start", "clone"]


def test_run_agent_reports_test_failed(db_session: Session, auth_headers: dict, monkeypatch):
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    task = agent_service.create_task(
        db_session,
        owner.id,
        repo_url=_make_fixture_repo(),
        base_commit=None,
        test_command="python -m unittest test_calculator",
        target_path="calculator.py",
    )

    monkeypatch.setattr(
        agent_service,
        "run_in_sandbox",
        lambda *a, **k: SandboxResult(passed=False, exit_code=1, output="still failing"),
    )
    # LLM returns a still-wrong file.
    run = agent_service.run_agent(db_session, task, llm=_FakeLLM("def add(a, b):\n    return 0\n"))

    assert run.status == "test_failed"
    assert run.test_passed is False


def test_run_agent_records_error_on_bad_repo(db_session: Session, auth_headers: dict):
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    task = agent_service.create_task(
        db_session,
        owner.id,
        repo_url="/nonexistent/repo/path",
        base_commit=None,
        test_command="python -m unittest test_x",
        target_path="x.py",
    )
    run = agent_service.run_agent(db_session, task, llm=_FakeLLM("whatever"))
    assert run.status == "error"
    assert run.error


def test_extract_file_contents_strips_fences() -> None:
    fenced = "```python\nprint('hi')\n```"
    assert agent_service._extract_file_contents(fenced) == "print('hi')\n"
