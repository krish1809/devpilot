"""Run lifecycle around the agent graph: start, execute (in the background),
cancel, resume from the last checkpoint, and the human approval decision."""

from __future__ import annotations

import logging
import shutil
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agents.checkpoint import get_postgres_checkpointer
from app.agents.graph import (
    AgentDeps,
    AgentState,
    RunAborted,
    RunCancelled,
    build_graph,
    diff_sha256,
    record_event,
)
from app.db.session import SessionLocal
from app.integrations.git_ops import GitError
from app.integrations.github_api import GitHubError
from app.integrations.llm import LLMError
from app.models.agent_run import AgentRun, Approval, RunStatus
from app.models.task import Task
from app.rag.embeddings import EmbeddingError

logger = logging.getLogger(__name__)

_RECURSION_LIMIT = 40  # graph supersteps per invocation; far above any bounded run


class RunStateError(Exception):
    """The requested action isn't allowed in the run's current state."""


class ApprovalError(RunStateError):
    """Raised when a run cannot be approved in its current state."""


@lru_cache
def _default_deps() -> AgentDeps:
    return AgentDeps(session_factory=SessionLocal, checkpointer=get_postgres_checkpointer())


def get_agent_deps() -> AgentDeps:
    """FastAPI dependency (overridden in tests)."""
    return _default_deps()


def thread_config(run_id: int) -> dict:
    return {"configurable": {"thread_id": f"run-{run_id}"}, "recursion_limit": _RECURSION_LIMIT}


def start_run(db: Session, task: Task, deps: AgentDeps, *, use_rag: bool | None = None) -> AgentRun:
    """Create a run row; the graph is executed separately (``execute_run``)."""
    use_rag = deps.settings.rag_enabled if use_rag is None else use_rag
    run = AgentRun(
        task_id=task.id,
        status=RunStatus.RUNNING,
        model=deps.settings.llm_model,
        use_rag=use_rag,
        target_path=task.target_path or None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    record_event(db, run.id, "start", f"Run started for task {task.id}")
    return run


def _initial_state(deps: AgentDeps, run_id: int) -> AgentState:
    with deps.session_factory() as db:
        run = db.get(AgentRun, run_id)
        task = db.get(Task, run.task_id)
        return {
            "run_id": run_id,
            "repo_url": task.repo_url,
            "base_commit": task.base_commit,
            "target_path": task.target_path or None,
            "test_command": task.test_command,
            "issue": task.description or None,  # untrusted context (issue text / notes)
            "use_rag": run.use_rag,
            "attempts": 0,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }


def _finish_with(deps: AgentDeps, run_id: int, status: str, message: str, stage: str) -> None:
    with deps.session_factory() as db:
        run = db.get(AgentRun, run_id)
        run.status = status
        run.error = message[:2000] if status == RunStatus.ERROR else run.error
        db.commit()
        record_event(db, run_id, stage, message)


def execute_run(run_id: int, deps: AgentDeps, command: Command | None = None) -> None:
    """Drive the graph for ``run_id`` until it ends or pauses for approval.

    With ``command`` (a resume value) it continues a paused graph. Without it,
    it starts fresh — or, if checkpoints already exist, continues from the last
    one (re-running only the step that didn't complete). Never raises: every
    outcome is recorded on the run, since this usually runs in the background.
    """
    graph = build_graph(deps, deadline=time.monotonic() + deps.settings.agent_run_timeout_seconds)
    config = thread_config(run_id)
    try:
        if command is not None:
            graph.invoke(command, config)
        elif graph.get_state(config).values:
            graph.invoke(None, config)
        else:
            graph.invoke(_initial_state(deps, run_id), config)
    except RunCancelled as exc:
        _finish_with(deps, run_id, RunStatus.CANCELLED, str(exc), "cancel")
    except (RunAborted, GitError, GitHubError, LLMError, EmbeddingError, OSError) as exc:
        _finish_with(deps, run_id, RunStatus.ERROR, str(exc), "error")
    except Exception:  # background job: never leave a run stuck in "running"
        logger.exception("Unexpected agent error in run %s", run_id)
        _finish_with(deps, run_id, RunStatus.ERROR, "Unexpected internal agent error", "error")
    finally:
        shutil.rmtree(deps.workspace(run_id), ignore_errors=True)


def run_to_completion(
    db: Session, task: Task, deps: AgentDeps, *, use_rag: bool | None = None
) -> AgentRun:
    """Start and execute a run synchronously (scripts, evaluation, tests)."""
    run = start_run(db, task, deps, use_rag=use_rag)
    execute_run(run.id, deps)
    db.refresh(run)
    return run


def cancel_run(db: Session, run: AgentRun) -> AgentRun:
    if run.status != RunStatus.RUNNING:
        raise RunStateError("Only a running run can be cancelled.")
    run.cancel_requested = True
    db.commit()
    record_event(db, run.id, "cancel", "Cancellation requested; stopping at the next step")
    db.refresh(run)
    return run


def _is_stale(run: AgentRun, deps: AgentDeps) -> bool:
    limit = timedelta(seconds=deps.settings.agent_run_timeout_seconds + 60)
    return run.updated_at < datetime.now(UTC) - limit


def prepare_resume(db: Session, run: AgentRun, deps: AgentDeps) -> AgentRun:
    """Mark a failed/cancelled/abandoned run to continue from its last checkpoint."""
    resumable = run.status in (RunStatus.ERROR, RunStatus.CANCELLED) or (
        run.status == RunStatus.RUNNING and _is_stale(run, deps)
    )
    if not resumable:
        raise RunStateError("Only an errored, cancelled, or abandoned run can be resumed.")
    if not build_graph(deps).get_state(thread_config(run.id)).values:
        raise RunStateError("This run has no checkpoints to resume from; start a new run.")
    run.status = RunStatus.RUNNING
    run.error = None
    run.cancel_requested = False
    db.commit()
    record_event(db, run.id, "resume", "Resuming from the last checkpoint")
    db.refresh(run)
    return run


def approve_run(
    db: Session,
    run: AgentRun,
    decision: str,
    deps: AgentDeps,
    *,
    base_branch: str | None = None,
) -> AgentRun:
    """Record a human decision and resume the paused graph with it.

    Only a run paused at ``human_approval`` (status ``validated``) can be
    approved. The approval is bound to the SHA-256 of the exact diff shown and
    the base commit; the publish step refuses if the diff no longer matches.
    Runs that ended without reaching approval can still be rejected.
    """
    if run.status != RunStatus.VALIDATED:
        if decision == "rejected" and run.status in (
            RunStatus.TEST_FAILED,
            RunStatus.REVIEW_FAILED,
            RunStatus.ERROR,
            RunStatus.CANCELLED,
        ):
            db.add(Approval(run_id=run.id, decision=decision, base_commit=run.base_commit))
            run.status = RunStatus.REJECTED
            db.commit()
            record_event(db, run.id, "approve", "Run rejected by reviewer")
            db.refresh(run)
            return run
        raise ApprovalError("Only a validated run (passing test) can be approved for publishing.")

    config = thread_config(run.id)
    if not build_graph(deps).get_state(config).interrupts:
        raise ApprovalError(
            "This run has no pending approval (it predates the LangGraph agent); re-run the task."
        )

    approved_hash = diff_sha256(run.diff)
    db.add(
        Approval(
            run_id=run.id, decision=decision, diff_sha256=approved_hash, base_commit=run.base_commit
        )
    )
    if decision == "approved":
        run.status = RunStatus.APPROVED
    db.commit()
    record_event(
        db,
        run.id,
        "approve",
        "Run approved; resuming the graph to publish"
        if decision == "approved"
        else "Run rejected by reviewer",
    )

    execute_run(
        run.id,
        deps,
        Command(
            resume={"decision": decision, "base_branch": base_branch, "diff_sha256": approved_hash}
        ),
    )
    db.refresh(run)
    return run


def checkpoint_history(run_id: int, deps: AgentDeps) -> list[dict]:
    """The run's checkpoints, oldest first: what ran, what's next, key counters."""
    graph = build_graph(deps)
    snapshots = list(graph.get_state_history(thread_config(run_id)))
    history = []
    for snap in reversed(snapshots):
        values = snap.values or {}
        history.append(
            {
                "checkpoint_id": snap.config["configurable"]["checkpoint_id"],
                "step": (snap.metadata or {}).get("step", -1),
                "next": list(snap.next),
                "created_at": snap.created_at,
                "attempts": values.get("attempts", 0),
                "test_passed": values.get("test_passed"),
                "llm_calls": values.get("llm_calls", 0),
                "waiting_for_approval": bool(snap.interrupts),
            }
        )
    return history
