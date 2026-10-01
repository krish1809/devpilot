"""GitHub-backed task sources: browse authorized repos/issues and import an
issue as a Task pinned to (repo, base branch, base commit SHA)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.integrations.github_api import GitHubClient, GitHubError, parse_full_name
from app.models.task import Task
from app.schemas.agent import TaskFromIssueCreate
from app.services import agent as agent_service


def list_repos(gh: GitHubClient) -> list[dict]:
    return gh.list_repos()


def list_issues(gh: GitHubClient, full_name: str, state: str = "open") -> list[dict]:
    return gh.list_issues(parse_full_name(full_name), state=state)


def get_tree(gh: GitHubClient, full_name: str, ref: str | None = None) -> dict:
    """Files at ``ref`` (default branch if omitted), plus the resolved SHA."""
    repo = parse_full_name(full_name)
    ref = ref or gh.get_repo(repo)["default_branch"]
    sha = gh.resolve_commit(repo, ref)
    return {
        "repo_full_name": repo.full_name,
        "ref": ref,
        "commit_sha": sha,
        "files": gh.list_files(repo, sha),
    }


def import_issue(db: Session, gh: GitHubClient, owner_id: int, data: TaskFromIssueCreate) -> Task:
    """Create a task from a GitHub issue.

    The base branch's current head is resolved to a SHA now, so every run of
    this task works on the same commit. The target file is read at that SHA to
    confirm it exists and is text before anything is stored.
    """
    repo = parse_full_name(data.repo_full_name)
    base_branch = data.base_branch or gh.get_repo(repo)["default_branch"]
    sha = gh.resolve_commit(repo, base_branch)
    issue = gh.get_issue(repo, data.issue_number)
    if issue["state"] != "open":
        raise GitHubError(f"Issue #{data.issue_number} is not open", status=422)
    if data.target_path:  # existence + text check at the pinned commit
        gh.read_file(repo, data.target_path, sha)

    description = f"{issue['title']}\n\n{issue['body']}".strip()
    return agent_service.create_task(
        db,
        owner_id,
        repo_url=repo.clone_url,
        repo_full_name=repo.full_name,
        base_branch=base_branch,
        base_commit=sha,
        issue_number=issue["number"],
        issue_title=issue["title"][:500],
        issue_url=issue["html_url"],
        test_command=data.test_command,
        target_path=data.target_path,
        description=description,
    )
