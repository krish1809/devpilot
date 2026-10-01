from collections.abc import Generator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.api.deps import CurrentUser, DbSession
from app.integrations.github_api import GitHubClient, GitHubError
from app.schemas.agent import GitHubIssue, GitHubRepo, GitHubTree, TaskFromIssueCreate, TaskResponse
from app.services import audit
from app.services import github as github_service

router = APIRouter(tags=["github"])

_Owner = Annotated[str, Path(pattern=r"^[\w.-]{1,100}$")]
_Name = Annotated[str, Path(pattern=r"^[\w.-]{1,100}$")]


def get_github_client() -> Generator[GitHubClient, None, None]:
    try:
        client = GitHubClient()
    except GitHubError as exc:
        raise _http_error(exc) from exc
    try:
        yield client
    finally:
        client.close()


GitHub = Annotated[GitHubClient, Depends(get_github_client)]


def _http_error(exc: GitHubError) -> HTTPException:
    """Map upstream failures to safe client-facing errors."""
    if exc.status == 404:
        return HTTPException(status.HTTP_404_NOT_FOUND, "Not found on GitHub (or no access)")
    if exc.status in (422, 409):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    if exc.status == 503:
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub request failed")


@router.get("/github/repos", response_model=list[GitHubRepo])
def list_repos(gh: GitHub, current_user: CurrentUser) -> list[GitHubRepo]:
    """Repositories the server's GitHub token can access."""
    try:
        return github_service.list_repos(gh)
    except GitHubError as exc:
        raise _http_error(exc) from exc


@router.get("/github/repos/{owner}/{name}/issues", response_model=list[GitHubIssue])
def list_issues(
    owner: _Owner,
    name: _Name,
    gh: GitHub,
    current_user: CurrentUser,
    state: Annotated[Literal["open", "closed", "all"], Query()] = "open",
) -> list[GitHubIssue]:
    try:
        return github_service.list_issues(gh, f"{owner}/{name}", state)
    except GitHubError as exc:
        raise _http_error(exc) from exc


@router.get("/github/repos/{owner}/{name}/tree", response_model=GitHubTree)
def get_tree(
    owner: _Owner,
    name: _Name,
    gh: GitHub,
    current_user: CurrentUser,
    ref: Annotated[str | None, Query(max_length=200, pattern=r"^[\w./-]+$")] = None,
) -> GitHubTree:
    """File list at a branch/SHA (default branch if omitted), with the resolved SHA."""
    try:
        return github_service.get_tree(gh, f"{owner}/{name}", ref)
    except GitHubError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/from-issue", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task_from_issue(
    data: TaskFromIssueCreate, db: DbSession, gh: GitHub, current_user: CurrentUser
) -> TaskResponse:
    """Import an open GitHub issue as a task pinned to the base branch's current commit."""
    try:
        task = github_service.import_issue(db, gh, current_user.id, data)
    except GitHubError as exc:
        raise _http_error(exc) from exc
    audit.record_event(
        db,
        audit.TASK_IMPORTED,
        user_id=current_user.id,
        detail=f"{task.repo_full_name}#{task.issue_number} -> task {task.id}",
    )
    return task
