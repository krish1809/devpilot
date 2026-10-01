"""Task and run queries. Orchestration lives in ``app.agents`` (LangGraph)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import github_api
from app.models.agent_run import AgentRun, PullRequest, RunEvent
from app.models.task import Task


def create_task(db: Session, owner_id: int, **fields) -> Task:
    if not fields.get("repo_full_name"):
        ref = github_api.parse_github_url(fields["repo_url"])
        fields["repo_full_name"] = ref.full_name if ref else None
    task = Task(owner_id=owner_id, **fields)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int, owner_id: int) -> Task | None:
    return db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))


def list_tasks(db: Session, owner_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.owner_id == owner_id).order_by(Task.id)).all())


def list_task_runs(db: Session, task_id: int) -> list[AgentRun]:
    """Runs for a task, newest first."""
    return list(
        db.scalars(
            select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.id.desc())
        ).all()
    )


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


def get_pull_request(db: Session, run_id: int) -> PullRequest | None:
    return db.scalar(select(PullRequest).where(PullRequest.run_id == run_id))
