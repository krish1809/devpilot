from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.integrations.git_ops import is_safe_branch, is_safe_relpath


def _check_target_path(v: str) -> str:
    v = v.strip()
    if not is_safe_relpath(v):
        raise ValueError("must be a relative path inside the repository")
    return v


def _check_branch(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not is_safe_branch(v):
        raise ValueError("invalid branch name")
    return v


class TaskCreate(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)
    base_commit: str | None = Field(default=None, max_length=64)
    base_branch: str | None = Field(default=None, max_length=200)
    test_command: str = Field(min_length=1, max_length=500)
    target_path: str = Field(min_length=1, max_length=500)
    description: str | None = None

    _target = field_validator("target_path")(_check_target_path)
    _branch = field_validator("base_branch")(_check_branch)

    @field_validator("repo_url")
    @classmethod
    def _no_option_like_url(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("-"):
            raise ValueError("invalid repository URL")
        return v


class TaskFromIssueCreate(BaseModel):
    """Import a GitHub issue as a task, pinned to the branch's current commit."""

    repo_full_name: str = Field(min_length=3, max_length=200, pattern=r"^[\w.-]+/[\w.-]+$")
    issue_number: int = Field(gt=0)
    base_branch: str | None = Field(default=None, max_length=200)
    test_command: str = Field(min_length=1, max_length=500)
    target_path: str = Field(min_length=1, max_length=500)

    _target = field_validator("target_path")(_check_target_path)
    _branch = field_validator("base_branch")(_check_branch)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    repo_url: str
    base_commit: str | None
    base_branch: str | None
    repo_full_name: str | None
    issue_number: int | None
    issue_title: str | None
    issue_url: str | None
    test_command: str
    target_path: str
    description: str | None
    created_at: datetime


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    # Overrides the task's base branch for the PR (defaults to the task's, else "main").
    base_branch: str | None = Field(default=None, max_length=200)

    _branch = field_validator("base_branch")(_check_branch)


class PullRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    number: int | None
    status: str
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
    base_commit: str | None
    diff: str | None
    test_passed: bool | None
    sandbox_output: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    events: list[RunEventResponse] = []
    pull_request: PullRequestResponse | None = None


# --- GitHub browsing -------------------------------------------------------
class GitHubRepo(BaseModel):
    full_name: str
    private: bool
    default_branch: str
    description: str | None
    html_url: str
    open_issues_count: int
    can_push: bool


class GitHubIssue(BaseModel):
    number: int
    title: str
    state: str
    html_url: str
    labels: list[str]
    created_at: datetime


class GitHubTree(BaseModel):
    repo_full_name: str
    ref: str
    commit_sha: str
    files: list[str]
