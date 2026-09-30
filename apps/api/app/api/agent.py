from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.agent import (
    RunEventResponse,
    RunResponse,
    TaskCreate,
    TaskResponse,
)
from app.services import agent as agent_service

router = APIRouter(tags=["agent"])


def _run_response(db, run) -> RunResponse:  # noqa: ANN001
    resp = RunResponse.model_validate(run)
    resp.events = [
        RunEventResponse.model_validate(e) for e in agent_service.list_run_events(db, run.id)
    ]
    return resp


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, db: DbSession, current_user: CurrentUser) -> TaskResponse:
    return agent_service.create_task(db, current_user.id, **data.model_dump())


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(db: DbSession, current_user: CurrentUser) -> list[TaskResponse]:
    return agent_service.list_tasks(db, current_user.id)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: DbSession, current_user: CurrentUser) -> TaskResponse:
    task = agent_service.get_task(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/run", response_model=RunResponse)
def run_task(task_id: int, db: DbSession, current_user: CurrentUser) -> RunResponse:
    """Run the agent synchronously and return the resulting run with its diff.

    This blocks while the repo is cloned, the LLM is called, and the test runs
    in the sandbox — acceptable for the walking skeleton; later phases move it
    to a background worker.
    """
    task = agent_service.get_task(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    run = agent_service.run_agent(db, task)
    return _run_response(db, run)


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: int, db: DbSession, current_user: CurrentUser) -> RunResponse:
    run = agent_service.get_run(db, run_id, current_user.id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _run_response(db, run)
