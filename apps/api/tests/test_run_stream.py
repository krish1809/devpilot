import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.services import agent as agent_service
from app.services.run_stream import format_event, run_events
from tests.conftest import register_and_login


def _collect(gen) -> list[str]:  # noqa: ANN001
    async def go() -> list[str]:
        return [frame async for frame in gen]

    return asyncio.run(go())


def _events(frames: list[str]) -> list[tuple[str, str]]:
    """(event, data) pairs; retry hints and keep-alive comments are skipped."""
    out = []
    for frame in frames:
        if not frame.startswith("event: "):
            continue
        lines = frame.strip().split("\n")
        data = "\n".join(line[len("data: ") :] for line in lines[1:])
        out.append((lines[0][len("event: ") :], data))
    return out


def _sequence(*snaps):  # noqa: ANN002, ANN202
    """A snapshot function returning each value in turn, then repeating the last."""
    remaining = list(snaps)
    current = {"value": None}

    async def snapshot():  # noqa: ANN202
        if remaining:
            current["value"] = remaining.pop(0)
        return current["value"]

    return snapshot


async def _connected() -> bool:
    return False


def _stream(snapshot, **overrides) -> list[str]:  # noqa: ANN001, ANN003
    opts = {
        "poll_seconds": 0,
        "heartbeat_seconds": 60,
        "max_seconds": 60,
        "is_disconnected": _connected,
        **overrides,
    }
    return _collect(run_events(snapshot, **opts))


# --------------------------------------------------------------------------- #
# The event generator
# --------------------------------------------------------------------------- #
def test_format_event_splits_multiline_data() -> None:
    assert format_event("run", "a\nb") == "event: run\ndata: a\ndata: b\n\n"


def test_sends_only_changes_then_done() -> None:
    snapshot = _sequence(
        {"status": "running", "step": 1},
        {"status": "running", "step": 1},  # unchanged: not re-sent
        {"status": "running", "step": 2},
        {"status": "validated", "step": 3},
    )
    events = _events(_stream(snapshot))

    assert [kind for kind, _ in events] == ["run", "run", "run", "done"]
    assert json.loads(events[2][1])["status"] == "validated"
    assert json.loads(events[3][1]) == {"status": "validated"}


def test_heartbeats_while_idle_and_times_out() -> None:
    frames = _stream(
        _sequence({"status": "running"}),
        poll_seconds=0.005,
        heartbeat_seconds=0,
        max_seconds=0.05,
    )

    assert ": keep-alive\n\n" in frames
    assert _events(frames)[-1][0] == "timeout"


def test_stops_when_the_client_disconnects() -> None:
    async def gone() -> bool:
        return True

    frames = _stream(_sequence({"status": "running"}), is_disconnected=gone)

    assert [kind for kind, _ in _events(frames)] == ["run"]


def test_reports_a_run_that_disappeared() -> None:
    assert _events(_stream(_sequence(None))) == [("done", '{"status": "gone"}')]


# --------------------------------------------------------------------------- #
# The HTTP endpoint
# --------------------------------------------------------------------------- #
def _run(db_session: Session, status: str = "validated") -> AgentRun:
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    task = agent_service.create_task(
        db_session,
        owner.id,
        repo_url="https://example.test/repo.git",
        test_command="python -m unittest test_x",
        target_path="x.py",
    )
    run = AgentRun(task_id=task.id, status=status, model="test-model", diff="+fix\n")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_stream_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/runs/1/stream").status_code == 401


def test_stream_hides_other_users_runs(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    run = _run(db_session)
    bob = register_and_login(client, "bob@example.com")

    assert client.get(f"/api/v1/runs/{run.id}/stream", headers=bob).status_code == 404


def test_stream_of_a_finished_run_sends_a_snapshot_then_done(
    client: TestClient, auth_headers: dict, db_session: Session
) -> None:
    run = _run(db_session)

    with client.stream("GET", f"/api/v1/runs/{run.id}/stream", headers=auth_headers) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        body = "".join(resp.iter_text())

    events = _events([frame + "\n\n" for frame in body.split("\n\n") if frame])
    assert [kind for kind, _ in events] == ["run", "done"]
    snapshot = json.loads(events[0][1])
    assert snapshot["id"] == run.id
    assert snapshot["status"] == "validated"
    assert snapshot["diff"] == "+fix\n"
    assert "events" in snapshot and "pull_request" in snapshot  # same shape as GET /runs/{id}
