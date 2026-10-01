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
