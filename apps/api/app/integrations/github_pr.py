"""Open a pull request for an approved run.

Re-clones the repo at the base commit, applies the exact reviewed diff on a new
branch, pushes it, and opens a PR with the GitHub CLI (`gh`, already
authenticated on the host). Nothing here runs repository code.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.integrations.git_ops import GitError, _run, clone_at_commit

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
    workspace = Path(tempfile.mkdtemp(prefix="devpilot_pr_"))
    patch_file = workspace.parent / f"{workspace.name}.patch"
    try:
        clone_at_commit(repo_url, base_commit, workspace)
        _run(["git", "checkout", "-b", branch], cwd=workspace)

        patch_file.write_text(diff if diff.endswith("\n") else diff + "\n", encoding="utf-8")
        try:
            _run(["git", "apply", str(patch_file)], cwd=workspace)
        except GitError as exc:
            raise PublishError(f"Reviewed diff no longer applies cleanly: {exc}") from exc

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
        _run(["git", "push", "-u", "origin", branch], cwd=workspace)

        proc = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base_branch,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise PublishError(f"gh pr create failed: {proc.stderr.strip()[:300]}")

        url = proc.stdout.strip().splitlines()[-1].strip()
        number = _parse_pr_number(url)
        return {"url": url, "number": number}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        patch_file.unlink(missing_ok=True)


def _parse_pr_number(url: str) -> int | None:
    tail = url.rstrip("/").split("/")[-1]
    return int(tail) if tail.isdigit() else None
