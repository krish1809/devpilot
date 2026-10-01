"""Phase 4: GitHub integration. All GitHub HTTP is mocked via httpx.MockTransport."""

import base64
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.github import get_github_client
from app.integrations import git_ops, github_api
from app.integrations.github_api import GitHubClient, GitHubError
from app.main import app as fastapi_app

SHA = "a" * 40
REPO = "octo/demo"


def _fake_github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/user/repos":
        return httpx.Response(
            200,
            json=[
                {
                    "full_name": REPO,
                    "private": False,
                    "default_branch": "main",
                    "description": "demo",
                    "html_url": f"https://github.com/{REPO}",
                    "open_issues_count": 2,
                    "permissions": {"push": True},
                }
            ],
        )
    if path == f"/repos/{REPO}":
        return httpx.Response(200, json={"full_name": REPO, "default_branch": "main"})
    if path == f"/repos/{REPO}/commits/main":
        return httpx.Response(200, text=SHA)
    if path == f"/repos/{REPO}/git/trees/{SHA}":
        return httpx.Response(
            200,
            json={
                "tree": [
                    {"path": "calculator.py", "type": "blob"},
                    {"path": "pkg", "type": "tree"},
                    {"path": "pkg/util.py", "type": "blob"},
                ]
            },
        )
    if path == f"/repos/{REPO}/contents/calculator.py":
        assert request.url.params["ref"] == SHA
        content = base64.b64encode(b"def add(a, b):\n    return a - b\n").decode()
        return httpx.Response(200, json={"type": "file", "content": content})
    if path == f"/repos/{REPO}/issues":
        return httpx.Response(
            200,
            json=[
                _issue(1, "add() subtracts"),
                {**_issue(2, "a PR"), "pull_request": {}},
            ],
        )
    if path == f"/repos/{REPO}/issues/1":
        return httpx.Response(200, json={**_issue(1, "add() subtracts"), "body": "2+3 gives -1"})
    if path == f"/repos/{REPO}/issues/3":
        return httpx.Response(200, json={**_issue(3, "old", state="closed"), "body": ""})
    if path == f"/repos/{REPO}/pulls" and request.method == "POST":
        payload = json.loads(request.content)
        assert payload["base"] == "main"
        return httpx.Response(
            201, json={"html_url": f"https://github.com/{REPO}/pull/7", "number": 7}
        )
    return httpx.Response(404, json={"message": "Not Found"})


def _issue(number: int, title: str, state: str = "open") -> dict:
    return {
        "number": number,
        "title": title,
        "state": state,
        "html_url": f"https://github.com/{REPO}/issues/{number}",
        "labels": [{"name": "bug"}],
        "created_at": "2026-09-30T00:00:00Z",
    }


def _client() -> GitHubClient:
    return GitHubClient("test-token", transport=httpx.MockTransport(_fake_github))


@pytest.fixture()
def gh_override():
    fastapi_app.dependency_overrides[get_github_client] = _client
    yield
    fastapi_app.dependency_overrides.pop(get_github_client, None)


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def test_client_lists_repos_and_filters_prs_from_issues() -> None:
    gh = _client()
    repos = gh.list_repos()
    assert repos[0]["full_name"] == REPO and repos[0]["can_push"] is True
    issues = gh.list_issues(github_api.parse_full_name(REPO))
    assert [i["number"] for i in issues] == [1]
    assert issues[0]["labels"] == ["bug"]


def test_client_resolves_commit_and_reads_file_at_sha() -> None:
    gh = _client()
    repo = github_api.parse_full_name(REPO)
    assert gh.resolve_commit(repo, "main") == SHA
    assert gh.list_files(repo, SHA) == ["calculator.py", "pkg/util.py"]
    assert "return a - b" in gh.read_file(repo, "calculator.py", SHA)


def test_client_maps_upstream_errors() -> None:
    with pytest.raises(GitHubError) as info:
        _client().get_issue(github_api.parse_full_name(REPO), 999)
    assert info.value.status == 404


@pytest.mark.parametrize("bad", ["octo", "a/b/c", "../x", "octo/..", "o o/x"])
def test_parse_full_name_rejects_bad_names(bad: str) -> None:
    with pytest.raises(GitHubError):
        github_api.parse_full_name(bad)


def test_parse_github_url() -> None:
    assert github_api.parse_github_url("https://github.com/octo/demo.git").full_name == REPO
    assert github_api.parse_github_url("https://github.com/octo/demo").full_name == REPO
    assert github_api.parse_github_url("/tmp/repo") is None
    assert github_api.parse_github_url("https://gitlab.com/octo/demo") is None


def test_git_auth_env_keeps_token_out_of_args() -> None:
    env = github_api.git_auth_env("secret-token")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert "secret-token" not in env["GIT_CONFIG_VALUE_0"]  # base64-encoded, never raw
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_missing_token_is_a_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(github_api, "get_settings", lambda: type("S", (), {"github_token": ""}))
    monkeypatch.setattr(github_api, "_gh_cli_token", lambda: "")
    with pytest.raises(GitHubError) as info:
        github_api.get_token()
    assert info.value.status == 503


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def test_github_endpoints_require_auth(client: TestClient, gh_override) -> None:
    assert client.get("/api/v1/github/repos").status_code == 401
    assert client.post("/api/v1/tasks/from-issue", json={}).status_code == 401


def test_list_repos_issues_and_tree(client: TestClient, auth_headers: dict, gh_override) -> None:
    repos = client.get("/api/v1/github/repos", headers=auth_headers)
    assert repos.status_code == 200 and repos.json()[0]["full_name"] == REPO

    issues = client.get(f"/api/v1/github/repos/{REPO}/issues", headers=auth_headers)
    assert [i["number"] for i in issues.json()] == [1]

    tree = client.get(f"/api/v1/github/repos/{REPO}/tree", headers=auth_headers).json()
    assert tree["ref"] == "main" and tree["commit_sha"] == SHA
    assert "calculator.py" in tree["files"]


def test_unknown_repo_is_404(client: TestClient, auth_headers: dict, gh_override) -> None:
    resp = client.get("/api/v1/github/repos/octo/nope/issues", headers=auth_headers)
    assert resp.status_code == 404


def _import_payload(**overrides) -> dict:
    base = {
        "repo_full_name": REPO,
        "issue_number": 1,
        "target_path": "calculator.py",
        "test_command": "python -m unittest test_calculator",
    }
    return {**base, **overrides}


def test_import_issue_pins_repo_branch_and_commit(
    client: TestClient, auth_headers: dict, gh_override
) -> None:
    resp = client.post("/api/v1/tasks/from-issue", json=_import_payload(), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["repo_full_name"] == REPO
    assert task["repo_url"] == f"https://github.com/{REPO}.git"
    assert task["base_branch"] == "main"
    assert task["base_commit"] == SHA
    assert task["issue_number"] == 1
    assert task["issue_title"] == "add() subtracts"
    assert "2+3 gives -1" in task["description"]

    audit = client.get("/api/v1/audit/me", headers=auth_headers).json()
    assert any(a["action"] == "task.imported_from_issue" for a in audit)


def test_import_rejects_closed_issue(client: TestClient, auth_headers: dict, gh_override) -> None:
    resp = client.post(
        "/api/v1/tasks/from-issue", json=_import_payload(issue_number=3), headers=auth_headers
    )
    assert resp.status_code == 422


def test_import_rejects_missing_target_file(
    client: TestClient, auth_headers: dict, gh_override
) -> None:
    resp = client.post(
        "/api/v1/tasks/from-issue",
        json=_import_payload(target_path="nope.py"),
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", ".git/config", "a/../../b"])
def test_unsafe_target_path_rejected(
    client: TestClient, auth_headers: dict, gh_override, path: str
) -> None:
    resp = client.post(
        "/api/v1/tasks/from-issue", json=_import_payload(target_path=path), headers=auth_headers
    )
    assert resp.status_code == 422
    manual = client.post(
        "/api/v1/tasks",
        json={
            "repo_url": "https://github.com/octo/demo.git",
            "test_command": "x",
            "target_path": path,
        },
        headers=auth_headers,
    )
    assert manual.status_code == 422


def test_unsafe_branch_rejected(client: TestClient, auth_headers: dict, gh_override) -> None:
    resp = client.post(
        "/api/v1/tasks/from-issue",
        json=_import_payload(base_branch="--upload-pack=evil"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_manual_task_with_github_url_is_bound(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/tasks",
        json={
            "repo_url": "https://github.com/octo/demo.git",
            "test_command": "pytest",
            "target_path": "x.py",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["repo_full_name"] == REPO


# --------------------------------------------------------------------------- #
# git_ops path safety
# --------------------------------------------------------------------------- #
def test_write_text_refuses_escape(tmp_path: Path) -> None:
    with pytest.raises(git_ops.GitError):
        git_ops.write_text(tmp_path, "../outside.py", "x")
    (tmp_path / "link").symlink_to("/tmp")
    with pytest.raises(git_ops.GitError):
        git_ops.write_text(tmp_path, "link/evil.py", "x")


def test_publish_rejects_non_github_repo() -> None:
    from app.integrations import github_pr

    with pytest.raises(github_pr.PublishError):
        github_pr.open_pull_request(
            "/tmp/local", None, "", branch="b", base_branch="main", title="t", body="b"
        )
