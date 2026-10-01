"""Minimal GitHub REST client for repo/issue/PR operations.

The token lives server-side only: ``GITHUB_TOKEN`` (a fine-grained PAT) from the
environment, falling back to the host's authenticated ``gh`` CLI. It is never
sent to the browser, the LLM, logs, or run events. Everything returned from
GitHub (issue titles/bodies, file contents) is untrusted input.
"""

from __future__ import annotations

import base64
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.core.config import get_settings

_API = "https://api.github.com"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_TREE_LIMIT = 5000
_ISSUE_BODY_LIMIT = 8000


class GitHubError(Exception):
    """A GitHub call failed. ``status`` is the upstream HTTP status (0 if none)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.full_name}.git"


def parse_full_name(full_name: str) -> RepoRef:
    """Validate an ``owner/name`` string (rejects anything path-like)."""
    parts = full_name.strip().split("/")
    if len(parts) != 2 or not all(_NAME_RE.match(p) for p in parts) or ".." in parts:
        raise GitHubError(f"Invalid repository name: {full_name!r}", status=422)
    return RepoRef(parts[0], parts[1])


def parse_github_url(url: str) -> RepoRef | None:
    """Return the RepoRef for an https github.com URL, else None."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None
    try:
        return parse_full_name(f"{m.group(1)}/{m.group(2)}")
    except GitHubError:
        return None


@lru_cache
def _gh_cli_token() -> str:
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def get_token() -> str:
    token = get_settings().github_token or _gh_cli_token()
    if not token:
        raise GitHubError(
            "No GitHub token configured. Set GITHUB_TOKEN or run `gh auth login`.", status=503
        )
    return token


def git_auth_env(token: str) -> dict[str, str]:
    """Env vars that make `git` send the token to github.com without it
    appearing in the remote URL, the process arguments, or error output."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    }


class GitHubClient:
    def __init__(self, token: str | None = None, *, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=_API,
            headers={
                "Authorization": f"Bearer {token or get_token()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=get_settings().github_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message", "")
            except ValueError:
                msg = ""
            raise GitHubError(
                f"GitHub {method} {path} → {resp.status_code} {msg}".strip()[:300],
                status=resp.status_code,
            )
        return resp

    # --- Repositories -----------------------------------------------------
    def list_repos(self) -> list[dict]:
        resp = self._request(
            "GET",
            "/user/repos",
            params={"affiliation": "owner,collaborator", "sort": "updated", "per_page": 100},
        )
        return [
            {
                "full_name": r["full_name"],
                "private": r["private"],
                "default_branch": r["default_branch"],
                "description": r.get("description"),
                "html_url": r["html_url"],
                "open_issues_count": r.get("open_issues_count", 0),
                "can_push": bool(r.get("permissions", {}).get("push")),
            }
            for r in resp.json()
        ]

    def get_repo(self, repo: RepoRef) -> dict:
        return self._request("GET", f"/repos/{repo.full_name}").json()

    def resolve_commit(self, repo: RepoRef, ref: str) -> str:
        """Resolve a branch/tag/SHA to a full commit SHA."""
        resp = self._request(
            "GET",
            f"/repos/{repo.full_name}/commits/{ref}",
            headers={"Accept": "application/vnd.github.sha"},
        )
        sha = resp.text.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise GitHubError(f"Could not resolve {ref!r} to a commit", status=422)
        return sha

    def list_files(self, repo: RepoRef, sha: str) -> list[str]:
        """File paths (blobs) in the tree at ``sha``, capped for safety."""
        resp = self._request(
            "GET", f"/repos/{repo.full_name}/git/trees/{sha}", params={"recursive": "1"}
        )
        return [e["path"] for e in resp.json().get("tree", []) if e.get("type") == "blob"][
            :_TREE_LIMIT
        ]

    def read_file(self, repo: RepoRef, path: str, sha: str) -> str:
        """Contents of ``path`` at commit ``sha`` (text files only)."""
        data = self._request(
            "GET", f"/repos/{repo.full_name}/contents/{path}", params={"ref": sha}
        ).json()
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubError(f"{path} is not a file", status=422)
        try:
            return base64.b64decode(data.get("content", "")).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubError(f"{path} is not a UTF-8 text file", status=422) from exc

    # --- Issues -----------------------------------------------------------
    def list_issues(self, repo: RepoRef, state: str = "open") -> list[dict]:
        resp = self._request(
            "GET",
            f"/repos/{repo.full_name}/issues",
            params={"state": state, "per_page": 50, "sort": "updated"},
        )
        # The issues API also returns PRs; keep real issues only.
        return [_issue_summary(i) for i in resp.json() if "pull_request" not in i]

    def get_issue(self, repo: RepoRef, number: int) -> dict:
        data = self._request("GET", f"/repos/{repo.full_name}/issues/{number}").json()
        if "pull_request" in data:
            raise GitHubError(f"#{number} is a pull request, not an issue", status=422)
        return {**_issue_summary(data), "body": (data.get("body") or "")[:_ISSUE_BODY_LIMIT]}

    # --- Pull requests ----------------------------------------------------
    def create_pull_request(
        self, repo: RepoRef, *, head: str, base: str, title: str, body: str
    ) -> dict:
        data = self._request(
            "POST",
            f"/repos/{repo.full_name}/pulls",
            json={"head": head, "base": base, "title": title, "body": body},
        ).json()
        return {"url": data["html_url"], "number": data["number"]}


def _issue_summary(i: dict) -> dict:
    return {
        "number": i["number"],
        "title": i["title"],
        "state": i["state"],
        "html_url": i["html_url"],
        "labels": [lbl["name"] for lbl in i.get("labels", []) if isinstance(lbl, dict)],
        "created_at": i["created_at"],
    }
