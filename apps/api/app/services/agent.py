"""The walking-skeleton agent loop.

Given a Task, this: clones the repo at its base commit, runs the failing test
once to capture the failure, asks the LLM for a corrected version of the target
file, applies it, re-runs the test in the sandbox, and records the diff and
result on an AgentRun. One LLM call, one file, no LangGraph/RAG yet.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations import git_ops
from app.integrations.llm import LLMError, LLMProvider, Message, get_llm_provider
from app.models.agent_run import AgentRun, RunEvent, RunStatus
from app.models.task import Task
from app.sandbox.runner import run_in_sandbox

_SYSTEM_PROMPT = (
    "You are an expert software engineer. You fix a failing test by editing exactly "
    "one file. Return ONLY the complete corrected contents of that file — no "
    "explanation, no commentary, and no markdown code fences."
)


def _record(db: Session, run: AgentRun, stage: str, message: str) -> None:
    seq = db.scalar(
        select(RunEvent.seq).where(RunEvent.run_id == run.id).order_by(RunEvent.seq.desc())
    )
    db.add(RunEvent(run_id=run.id, seq=(seq or 0) + 1, stage=stage, message=message[:2000]))
    db.commit()


def _extract_file_contents(reply: str) -> str:
    """Strip a surrounding markdown code fence if the model added one."""
    text = reply.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop opening ``` (possibly ```python)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text if text.endswith("\n") else text + "\n"


def _build_prompt(target_path: str, content: str, test_command: str, failure: str) -> list[Message]:
    user = (
        f"Repository file `{target_path}`:\n\n```\n{content}\n```\n\n"
        f"Running `{test_command}` fails with:\n\n```\n{failure}\n```\n\n"
        f"Return the complete corrected contents of `{target_path}` so the test passes. "
        f"Output only the file contents."
    )
    return [Message("system", _SYSTEM_PROMPT), Message("user", user)]


def run_agent(db: Session, task: Task, *, llm: LLMProvider | None = None) -> AgentRun:
    settings = get_settings()
    llm = llm or get_llm_provider()

    run = AgentRun(task_id=task.id, status=RunStatus.RUNNING, model=settings.llm_model)
    db.add(run)
    db.commit()
    db.refresh(run)
    _record(db, run, "start", f"Run started for task {task.id}")

    workspace = Path(tempfile.mkdtemp(prefix="devpilot_run_"))
    try:
        _record(db, run, "clone", f"Cloning {task.repo_url} @ {task.base_commit or 'HEAD'}")
        git_ops.clone_at_commit(task.repo_url, task.base_commit, workspace)

        original = git_ops.read_text(workspace, task.target_path)

        _record(db, run, "baseline", f"Running failing test: {task.test_command}")
        baseline = run_in_sandbox(
            workspace,
            task.test_command,
            image=settings.sandbox_image,
            timeout_seconds=settings.sandbox_timeout_seconds,
        )
        if baseline.passed:
            _record(db, run, "baseline", "Test already passes; nothing to fix.")

        _record(db, run, "plan", "Requesting a patch from the LLM")
        reply = llm.complete(
            _build_prompt(task.target_path, original, task.test_command, baseline.output)
        )
        fixed = _extract_file_contents(reply)
        git_ops.write_text(workspace, task.target_path, fixed)

        run.diff = git_ops.git_diff(workspace)
        _record(db, run, "patch", "Applied patch; re-running the test")

        result = run_in_sandbox(
            workspace,
            task.test_command,
            image=settings.sandbox_image,
            timeout_seconds=settings.sandbox_timeout_seconds,
        )
        run.test_passed = result.passed
        run.sandbox_output = result.output
        run.status = RunStatus.VALIDATED if result.passed else RunStatus.TEST_FAILED
        _record(db, run, "validate", f"Test {'passed' if result.passed else 'failed'}")

    except (git_ops.GitError, LLMError, OSError) as exc:
        run.status = RunStatus.ERROR
        run.error = str(exc)[:2000]
        _record(db, run, "error", str(exc)[:2000])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        db.commit()
        db.refresh(run)

    return run


def create_task(db: Session, owner_id: int, **fields) -> Task:
    task = Task(owner_id=owner_id, **fields)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int, owner_id: int) -> Task | None:
    return db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))


def list_tasks(db: Session, owner_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.owner_id == owner_id).order_by(Task.id)).all())


def get_run(db: Session, run_id: int, owner_id: int) -> AgentRun | None:
    """Fetch a run, scoped to the owner via its task."""
    return db.scalar(
        select(AgentRun)
        .join(Task, AgentRun.task_id == Task.id)
        .where(AgentRun.id == run_id, Task.owner_id == owner_id)
    )


def list_run_events(db: Session, run_id: int) -> list[RunEvent]:
    return list(
        db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)).all()
    )
