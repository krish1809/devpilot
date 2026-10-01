from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.agents import runner
from app.agents.graph import AgentDeps
from app.api.deps import CurrentUser, DbSession
from app.schemas.agent import (
    ApprovalRequest,
    CheckpointResponse,
    PullRequestResponse,
    RunEventResponse,
    RunRequest,
    RunResponse,
    RunSummary,
    RunTrace,
    TaskCreate,
    TaskResponse,
)
from app.services import agent as agent_service
from app.services import audit

router = APIRouter(tags=["agent"])

Deps = Annotated[AgentDeps, Depends(runner.get_agent_deps)]


def _run_response(db, run) -> RunResponse:  # noqa: ANN001
    resp = RunResponse.model_validate(run)
    resp.events = [
        RunEventResponse.model_validate(e) for e in agent_service.list_run_events(db, run.id)
    ]
    pr = agent_service.get_pull_request(db, run.id)
    resp.pull_request = PullRequestResponse.model_validate(pr) if pr else None
    return resp


def _owned_task(db, task_id: int, user) -> object:  # noqa: ANN001
    task = agent_service.get_task(db, task_id, user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _owned_run(db, run_id: int, user) -> object:  # noqa: ANN001
    run = agent_service.get_run(db, run_id, user.id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, db: DbSession, current_user: CurrentUser) -> TaskResponse:
    return agent_service.create_task(db, current_user.id, **data.model_dump())


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(db: DbSession, current_user: CurrentUser) -> list[TaskResponse]:
    return agent_service.list_tasks(db, current_user.id)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: DbSession, current_user: CurrentUser) -> TaskResponse:
    return _owned_task(db, task_id, current_user)


@router.get("/tasks/{task_id}/runs", response_model=list[RunSummary])
def list_task_runs(task_id: int, db: DbSession, current_user: CurrentUser) -> list[RunSummary]:
    """The task's runs, newest first."""
    _owned_task(db, task_id, current_user)
    return agent_service.list_task_runs(db, task_id)


@router.post(
    "/tasks/{task_id}/run", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED
)
def run_task(
    task_id: int,
    db: DbSession,
    current_user: CurrentUser,
    deps: Deps,
    background_tasks: BackgroundTasks,
    data: RunRequest | None = None,
) -> RunResponse:
    """Start the agent graph in the background; poll ``GET /runs/{id}`` for progress."""
    task = _owned_task(db, task_id, current_user)
    try:
        run = runner.start_run(db, task, deps, use_rag=data.use_rag if data else None)
    except runner.RunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(runner.execute_run, run.id, deps)
    return _run_response(db, run)


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: int, db: DbSession, current_user: CurrentUser) -> RunResponse:
    run = _owned_run(db, run_id, current_user)
    db.refresh(run)  # background steps commit on other sessions
    return _run_response(db, run)


@router.get("/runs/{run_id}/trace", response_model=RunTrace)
def get_run_trace(run_id: int, db: DbSession, current_user: CurrentUser) -> RunTrace:
    """The run's LLM calls (usage, latency, outcome) and audited MCP tool calls."""
    _owned_run(db, run_id, current_user)
    return agent_service.get_run_trace(db, run_id)


@router.get("/runs/{run_id}/checkpoints", response_model=list[CheckpointResponse])
def get_run_checkpoints(
    run_id: int, db: DbSession, current_user: CurrentUser, deps: Deps
) -> list[CheckpointResponse]:
    """Every persisted graph step for the run, oldest first."""
    _owned_run(db, run_id, current_user)
    return runner.checkpoint_history(run_id, deps)


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_run(run_id: int, db: DbSession, current_user: CurrentUser) -> RunResponse:
    """Ask a running run to stop; it halts at the next step boundary."""
    run = _owned_run(db, run_id, current_user)
    try:
        run = runner.cancel_run(db, run)
    except runner.RunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_response(db, run)


@router.post(
    "/runs/{run_id}/resume", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED
)
def resume_run(
    run_id: int,
    db: DbSession,
    current_user: CurrentUser,
    deps: Deps,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """Continue an errored/cancelled/abandoned run from its last checkpoint."""
    run = _owned_run(db, run_id, current_user)
    try:
        run = runner.prepare_resume(db, run, deps)
    except runner.RunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(runner.execute_run, run.id, deps)
    return _run_response(db, run)


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
def approve_run(
    run_id: int, data: ApprovalRequest, db: DbSession, current_user: CurrentUser, deps: Deps
) -> RunResponse:
    """Approve (→ resume the graph and open a PR) or reject a run."""
    run = _owned_run(db, run_id, current_user)
    try:
        run = runner.approve_run(db, run, data.decision, deps, base_branch=data.base_branch)
    except runner.ApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit.record_event(
        db,
        audit.RUN_APPROVED if data.decision == "approved" else audit.RUN_REJECTED,
        user_id=current_user.id,
        detail=f"run {run.id} -> {run.status}",
    )
    return _run_response(db, run)
