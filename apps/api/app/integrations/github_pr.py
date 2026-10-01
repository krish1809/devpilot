"""Open a pull request for an approved run.

Re-clones the repo at the base commit, applies the exact reviewed diff on a new
branch, pushes it, and opens a PR through the GitHub REST API. The token is
passed to git via environment (never in URLs/args). Nothing here runs
repository code.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.integrations import github_api
from app.integrations.git_ops import GitError, _run, clone_at_commit, is_safe_branch

_BOT_NAME = "DevPilot"
_BOT_EMAIL = "devpilot@users.noreply.github.com"


class PublishError(Exception):
    """Raised when opening the pull request fails."""


def open_pull_request(
    repo_url: str,
    base_commit: str | None,
    diff: str,
    *,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> dict:
    """Apply ``diff`` on ``branch`` and open a PR. Returns {url, number}."""
    repo = github_api.parse_github_url(repo_url)
    if repo is None:
        raise PublishError("Pull requests can only be opened for https://github.com repos.")
    if not (is_safe_branch(branch) and is_safe_branch(base_branch)):
        raise PublishError("Invalid branch name.")
    try:
        token = github_api.get_token()
    except github_api.GitHubError as exc:
        raise PublishError(str(exc)) from exc
    env = github_api.git_auth_env(token)

    workspace = Path(tempfile.mkdtemp(prefix="devpilot_pr_"))
    patch_file = workspace.parent / f"{workspace.name}.patch"
    try:
        try:
            clone_at_commit(repo.clone_url, base_commit, workspace, env=env)
            _run(["git", "checkout", "-b", branch], cwd=workspace)
        except GitError as exc:
            raise PublishError(f"Could not prepare branch: {exc}") from exc

        patch_file.write_text(diff if diff.endswith("\n") else diff + "\n", encoding="utf-8")
        try:
            _run(["git", "apply", str(patch_file)], cwd=workspace)
        except GitError as exc:
            raise PublishError(f"Reviewed diff no longer applies cleanly: {exc}") from exc

        try:
            _run(
                [
                    "git",
                    "-c",
                    f"user.name={_BOT_NAME}",
                    "-c",
                    f"user.email={_BOT_EMAIL}",
                    "commit",
                    "-am",
                    title,
                ],
                cwd=workspace,
            )
            _run(["git", "push", "-u", "origin", branch], cwd=workspace, env=env)
        except GitError as exc:
            raise PublishError(f"Could not push branch: {exc}") from exc

        try:
            with github_api.GitHubClient(token) as gh:
                return gh.create_pull_request(
                    repo, head=branch, base=base_branch, title=title, body=body
                )
        except github_api.GitHubError as exc:
            raise PublishError(f"Opening the PR failed: {exc}") from exc
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        patch_file.unlink(missing_ok=True)
