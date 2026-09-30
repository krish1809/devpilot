from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)
    base_commit: str | None = Field(default=None, max_length=64)
    test_command: str = Field(min_length=1, max_length=500)
    target_path: str = Field(min_length=1, max_length=500)
    description: str | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    repo_url: str
    base_commit: str | None
    test_command: str
    target_path: str
    description: str | None
    created_at: datetime


class RunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    stage: str
    message: str
    created_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    status: str
    model: str
    diff: str | None
    test_passed: bool | None
    sandbox_output: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    events: list[RunEventResponse] = []
