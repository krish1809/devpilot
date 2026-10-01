"""Thin wrappers over `git` for cloning a repo, editing files, and diffing.

Cloning and PR pushes run on the host (they need network and credentials);
executing the repo's code does not happen here — that is the sandbox's job.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath


class GitError(Exception):
    """Raised when a git command fails."""


_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def is_safe_relpath(relpath: str) -> bool:
    """True if ``relpath`` is a plain relative path that stays inside a checkout."""
    p = PurePosixPath(relpath)
    return (
        bool(relpath)
        and not p.is_absolute()
        and "\\" not in relpath
        and all(part not in ("..", ".git", "") for part in p.parts)
    )


def is_safe_branch(name: str) -> bool:
    """A conservative check that a ref name can't be read as a git option."""
    return bool(_BRANCH_RE.match(name)) and not name.startswith(("-", "/")) and ".." not in name


def _run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env={**os.environ, **env} if env else None,
    )
    if proc.returncode != 0:
        raise GitError(f"`{' '.join(args)}` failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def clone_at_commit(
    repo_url: str, commit: str | None, dest: Path, *, env: dict[str, str] | None = None
) -> None:
    """Clone ``repo_url`` into ``dest`` and check out ``commit`` (or default HEAD).

    ``env`` carries git auth (see ``github_api.git_auth_env``) for private repos.
    """
    _run(["git", "clone", "--quiet", "--", repo_url, str(dest)], env=env)
    if commit:
        _run(["git", "checkout", "--quiet", commit, "--"], cwd=dest)


def _resolve_inside(workspace: Path, relpath: str) -> Path:
    if not is_safe_relpath(relpath):
        raise GitError(f"Refusing unsafe path: {relpath!r}")
    target = (workspace / relpath).resolve()
    if not target.is_relative_to(workspace.resolve()):
        raise GitError(f"Refusing path outside the checkout: {relpath!r}")
    return target


def read_text(workspace: Path, relpath: str) -> str:
    return _resolve_inside(workspace, relpath).read_text(encoding="utf-8")


def write_text(workspace: Path, relpath: str, content: str) -> None:
    target = _resolve_inside(workspace, relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def git_diff(workspace: Path) -> str:
    """Unified diff of the working tree vs HEAD (what the agent changed)."""
    return _run(["git", "diff"], cwd=workspace)


def head_commit(workspace: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=workspace).strip()
