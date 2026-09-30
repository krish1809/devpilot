"""Thin wrappers over `git` for cloning a repo, editing files, and diffing.

Cloning and PR pushes run on the host (they need network and credentials);
executing the repo's code does not happen here — that is the sandbox's job.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git command fails."""


def _run(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"`{' '.join(args)}` failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def clone_at_commit(repo_url: str, commit: str | None, dest: Path) -> None:
    """Clone ``repo_url`` into ``dest`` and check out ``commit`` (or default HEAD)."""
    _run(["git", "clone", "--quiet", repo_url, str(dest)])
    if commit:
        _run(["git", "checkout", "--quiet", commit], cwd=dest)


def read_text(workspace: Path, relpath: str) -> str:
    return (workspace / relpath).read_text(encoding="utf-8")


def write_text(workspace: Path, relpath: str, content: str) -> None:
    target = workspace / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def git_diff(workspace: Path) -> str:
    """Unified diff of the working tree vs HEAD (what the agent changed)."""
    return _run(["git", "diff"], cwd=workspace)


def head_commit(workspace: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=workspace).strip()
