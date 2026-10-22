"""Phase 9: exporting real runs into the read-only showcase."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents import runner
from app.agents.graph import AgentDeps
from app.core.demo import get_or_create_demo_user
from app.evals import swebench as sb
from app.models.agent_run import AgentRun, RunEvent
from app.models.eval import EvalResult
from app.models.task import Task
from app.models.trace import LlmCall
from scripts import showcase
from tests.test_agent import FIX, ScriptedLLM, ScriptedSandbox, _task


def test_export_then_import_under_the_demo_user(
    db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    agent_deps.llm_factory = lambda: ScriptedLLM("plan", FIX)
    agent_deps.sandbox = ScriptedSandbox(False, True)
    task = _task(db_session, description=f"see {Path.home()}/secret/notes and org_ABC123")
    run = runner.run_to_completion(db_session, task, agent_deps, use_rag=False)
    ev = sb.get_or_create_run(db_session, "bench", [], ["rag"], {"seed": 1})
    db_session.add(EvalResult(eval_run_id=ev.id, instance_id="a__a-1", repo="a/a",
                              config="rag", status="validated", resolved=True,
                              agent_run_id=run.id))  # fmt: skip
    db_session.commit()

    data = json.loads(json.dumps(showcase.export(db_session, [task.id], ["bench"]), default=str))
    text = json.dumps(data)
    assert str(Path.home()) not in text and "org_ABC123" not in text

    for _ in range(2):  # idempotent
        counts = showcase.import_(db_session, data)
    assert counts == {"tasks": 1, "runs": 1, "eval_results": 1}

    demo = get_or_create_demo_user(db_session)
    [copy] = db_session.query(Task).filter_by(owner_id=demo.id).all()
    [copied_run] = db_session.query(AgentRun).filter_by(task_id=copy.id).all()
    assert copied_run.diff == run.diff and copied_run.status == "validated"
    assert db_session.query(RunEvent).filter_by(run_id=copied_run.id).count() == len(
        data["tasks"][0]["runs"][0]["run_events"]
    )
    assert db_session.query(LlmCall).filter_by(run_id=copied_run.id).count() == 2
    assert db_session.query(EvalResult).filter(EvalResult.agent_run_id.is_(None)).count() == 1


# --------------------------------------------------------------------------- #
# autoload: the deployed showcase refreshes itself from the bundled file
# --------------------------------------------------------------------------- #
def _bundle(tmp_path: Path, tasks: int = 0) -> Path:
    path = tmp_path / "showcase.json"
    path.write_text(json.dumps({"version": 1, "tasks": [], "evals": [], "n": tasks}))
    return path


def test_autoload_imports_once_per_content_change(db_session: Session, tmp_path: Path) -> None:
    import hashlib

    from app.models.app_state import AppState

    path = _bundle(tmp_path)
    assert showcase.autoload(db_session, path, demo_mode=True).startswith("imported")
    assert showcase.autoload(db_session, path, demo_mode=True) == "unchanged"  # e.g. a restart

    path.write_text(path.read_text().replace('"n": 0', '"n": 1'))  # a new export was deployed
    assert showcase.autoload(db_session, path, demo_mode=True).startswith("imported")
    state = db_session.get(AppState, showcase.STATE_KEY)
    assert state.value == hashlib.sha256(path.read_bytes()).hexdigest()


def test_autoload_only_runs_in_demo_mode(db_session: Session, tmp_path: Path) -> None:
    assert showcase.autoload(db_session, _bundle(tmp_path), demo_mode=False) == (
        "skipped (not in demo mode)"
    )
    missing = tmp_path / "nope.json"
    assert showcase.autoload(db_session, missing, demo_mode=True) == "skipped (nope.json not found)"


def test_autoload_command_never_blocks_startup(monkeypatch, capsys) -> None:  # noqa: ANN001
    def broken_session():  # noqa: ANN202
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(showcase, "SessionLocal", broken_session)
    monkeypatch.setattr("sys.argv", ["showcase", "autoload"])

    showcase.main()  # must not raise

    assert "failed (continuing): RuntimeError: database unreachable" in capsys.readouterr().err


def test_bundled_showcase_file_is_valid(tmp_path: Path) -> None:
    data = json.loads(showcase.BUNDLED.read_text())
    assert data["version"] == 1 and data["tasks"] and data["evals"]
