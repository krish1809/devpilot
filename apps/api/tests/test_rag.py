"""Phase 6: repository RAG — chunking, exclusions, pgvector index, hybrid
retrieval, and retrieval/localization inside the agent graph. Embeddings are
a deterministic hashing fake (no model download)."""

import hashlib
import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import runner
from app.agents.graph import AgentDeps, parse_localized_plan
from app.integrations import git_ops
from app.models.rag import RepoChunk, RepoIndex
from app.rag import chunking
from app.rag import index as rag_index
from app.rag.embeddings import EMBEDDING_DIM
from app.services import agent as agent_service
from tests.test_agent import FIX, ScriptedLLM, ScriptedSandbox, _make_fixture_repo, _task


class HashEmbedder:
    """Bag-of-words hashed into 384 dims, L2-normalized. Deterministic."""

    model = "test/hash-embedder"
    dim = EMBEDDING_DIM

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * EMBEDDING_DIM
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _git_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    repo = tmp_path / "repo"
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
    git_ops._run(["git", "init", "-q"], cwd=repo)
    git_ops._run(["git", "add", "-A", "-f"], cwd=repo)
    git_ops._run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=repo
    )
    return repo


SHOP = {
    "shop/money.py": (
        "def to_cents(amount):\n"
        '    """Convert a decimal amount of dollars to integer cents."""\n'
        "    return int(amount * 10)  # bug: should be 100\n"
    ),
    "shop/cart.py": (
        "from shop.money import to_cents\n\n\n"
        "def apply_discount(total, percent):\n"
        "    return total - total * percent / 100\n\n\n"
        "def cart_total_cents(prices):\n"
        "    return sum(to_cents(p) for p in prices)\n"
    ),
    "tests/test_cart.py": (
        "from shop.cart import cart_total_cents\n\n\n"
        "def test_total():\n"
        "    assert cart_total_cents([1.5, 2]) == 350\n"
    ),
    "README.md": "# Shop\n\nA tiny shop. Money is stored as integer cents.\n",
}


# --------------------------------------------------------------------------- #
# Chunking + exclusions
# --------------------------------------------------------------------------- #
def test_python_chunks_split_at_top_level_definitions() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(20))
    text = f"import os\n\n\ndef a():\n{body}\n\n\ndef b():\n{body}\n\n\nclass C:\n{body}\n"
    chunks = chunking.chunk_file("m.py", text)
    starts = [c.content.splitlines()[0] for c in chunks]
    assert any(s.startswith("def b") for s in starts)
    assert any(s.startswith("class C") for s in starts)
    assert all(c.start_line <= c.end_line for c in chunks)


def test_long_files_use_overlapping_windows() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 201))
    chunks = chunking.chunk_file("notes.md", text)
    assert len(chunks) >= 4
    assert chunks[0].start_line == 1 and chunks[-1].end_line == 200
    assert chunks[1].start_line <= chunks[0].end_line  # overlap


@pytest.mark.parametrize(
    "path,ok",
    [
        ("src/app.py", True),
        ("README.md", True),
        ("Makefile", True),
        ("node_modules/x/index.js", False),
        ("vendor/lib.go", False),
        (".venv/lib/site.py", False),
        ("package-lock.json", False),
        ("static/app.min.js", False),
        (".env", False),
        (".env.production", False),
        ("deploy/server.pem", False),
        ("keys/id_rsa", False),
        ("image.png", False),
    ],
)
def test_indexable_paths(path: str, ok: bool) -> None:
    assert chunking.is_indexable_path(path) is ok


def test_secrets_are_redacted_without_mangling_code() -> None:
    text = (
        'TOKEN = "ghp_' + "a" * 36 + '"\n'
        'password = "hunter2hunter2"\n'
        "work_directory_for_temporary_files = 1\n"
        "task-list-for-the-weekend-planner = 2\n"
    )
    out = chunking.redact_secrets(text)
    assert "ghp_" not in out and "hunter2hunter2" not in out
    assert "work_directory_for_temporary_files" in out
    assert "task-list-for-the-weekend-planner" in out


def test_binary_and_private_key_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "blob.py").write_bytes(b"abc\x00def")
    (tmp_path / "k.py").write_text("-----BEGIN RSA PRIVATE KEY-----\nxyz\n")
    (tmp_path / "ok.py").write_text("print('hi')\n")
    assert chunking.read_indexable_text(tmp_path, "blob.py") is None
    assert chunking.read_indexable_text(tmp_path, "k.py") is None
    assert chunking.read_indexable_text(tmp_path, "ok.py") == "print('hi')\n"


def test_only_tracked_files_are_collected(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path, {**SHOP, ".env": "SECRET=1\n"})
    (repo / "untracked.py").write_text("x = 1\n")
    chunks, files = chunking.collect_chunks(repo, max_files=100, max_chunks=100)
    paths = {c.path for c in chunks}
    assert "untracked.py" not in paths and ".env" not in paths
    assert {"shop/money.py", "shop/cart.py", "README.md"} <= paths
    assert files == 4


# --------------------------------------------------------------------------- #
# Index + hybrid retrieval (real pgvector in the test DB)
# --------------------------------------------------------------------------- #
def _build(tmp_path: Path, agent_deps: AgentDeps, files=SHOP):  # noqa: ANN001
    repo = _git_repo(tmp_path, files)
    return rag_index.ensure_index(
        agent_deps.session_factory,
        HashEmbedder(),
        repo_url=str(repo),
        commit_sha=git_ops.head_commit(repo),
        workspace=repo,
        max_files=100,
        max_chunks=100,
    )


def test_index_is_built_once_and_reused(
    tmp_path: Path, db_session: Session, agent_deps: AgentDeps
) -> None:
    index, built = _build(tmp_path, agent_deps)
    assert built and index.chunk_count > 0 and index.file_count == 4
    again, built_again = rag_index.ensure_index(
        agent_deps.session_factory,
        HashEmbedder(),
        repo_url=index.repo_url,
        commit_sha=index.commit_sha,
        workspace=tmp_path / "repo",
        max_files=100,
        max_chunks=100,
    )
    assert not built_again and again.id == index.id
    assert db_session.query(RepoIndex).count() == 1
    assert db_session.query(RepoChunk).filter_by(index_id=index.id).count() == index.chunk_count


def test_keyword_search_finds_exact_identifier(
    tmp_path: Path, db_session: Session, agent_deps: AgentDeps
) -> None:
    index, _ = _build(tmp_path, agent_deps)
    hits = rag_index.retrieve(db_session, HashEmbedder(), index.id, "where is apply_discount")
    assert hits and hits[0].path == "shop/cart.py"


def test_traceback_paths_boost_ranking(
    tmp_path: Path, db_session: Session, agent_deps: AgentDeps
) -> None:
    index, _ = _build(tmp_path, agent_deps)
    output = 'Traceback:\n  File "/work/shop/money.py", line 3, in to_cents\nAssertionError'
    boost = rag_index.traceback_paths(output)
    assert boost == {"shop/money.py"}
    hits = rag_index.retrieve(db_session, HashEmbedder(), index.id, "total", boost_paths=boost)
    assert rag_index.rank_files(hits)[0] == "shop/money.py"


def test_select_context_respects_budget_and_exclusions() -> None:
    hits = [
        rag_index.Hit("a.py", 1, 5, "x" * 400, 0.9),
        rag_index.Hit("b.py", 1, 5, "y" * 400, 0.8),
        rag_index.Hit("c.py", 1, 5, "z" * 400, 0.7),
    ]
    chosen = rag_index.select_context(hits, budget_chars=900, exclude={"a.py"})
    assert [h.path for h in chosen] == ["b.py", "c.py"]
    assert len(rag_index.select_context(hits, budget_chars=500, exclude=set())) == 1


@pytest.mark.parametrize(
    "reply,target",
    [
        ("TARGET: shop/money.py\nPLAN:\n1. use 100", "shop/money.py"),
        ("**TARGET:** `shop/money.py`\n**PLAN:**\n1. use 100", "shop/money.py"),
        ("TARGET: ./shop/money.py\n\n1. fix", "shop/money.py"),
        ("1. just a plan", None),
    ],
)
def test_parse_localized_plan(reply: str, target: str | None) -> None:
    got, plan = parse_localized_plan(reply)
    assert got == target
    assert plan and "TARGET" not in plan


# --------------------------------------------------------------------------- #
# Retrieval inside the graph
# --------------------------------------------------------------------------- #
def _rag_deps(agent_deps: AgentDeps, llm: ScriptedLLM) -> None:
    agent_deps.embedder_factory = HashEmbedder
    agent_deps.llm_factory = lambda: llm


def test_agent_localizes_the_file_from_retrieval(
    db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    llm = ScriptedLLM("TARGET: calculator.py\nPLAN:\n1. Use + instead of -", FIX)
    _rag_deps(agent_deps, llm)
    agent_deps.sandbox = ScriptedSandbox(False, True)
    task = _task(db_session, target_path=None)

    run = runner.run_to_completion(db_session, task, agent_deps, use_rag=True)

    assert run.status == "validated", run.error
    assert run.use_rag and run.target_path == "calculator.py"
    assert run.plan == "1. Use + instead of -"
    assert "calculator.py" in run.retrieval["candidates"]
    assert run.retrieval["index"]["chunks"] > 0
    planner_user = llm.calls[0][-1].content
    assert "Candidate files" in planner_user and "<retrieved_context>" in planner_user
    coder_user = llm.calls[1][-1].content
    assert "File `calculator.py`" in coder_user


def test_disallowed_localization_falls_back_to_a_candidate(
    db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    llm = ScriptedLLM("TARGET: ../../etc/passwd\nPLAN:\n1. pwn", FIX)
    _rag_deps(agent_deps, llm)
    agent_deps.sandbox = ScriptedSandbox(False, True)
    run = runner.run_to_completion(
        db_session, _task(db_session, target_path=None), agent_deps, use_rag=True
    )
    assert run.target_path in {"calculator.py", "test_calculator.py"}
    events = [e.message for e in agent_service.list_run_events(db_session, run.id)]
    assert any("not allowed" in m for m in events)


def test_retrieved_context_excludes_the_target_file(
    tmp_path: Path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    repo = _git_repo(tmp_path, SHOP)
    llm = ScriptedLLM("1. multiply by 100", "def to_cents(amount):\n    return int(amount * 100)\n")
    _rag_deps(agent_deps, llm)
    agent_deps.sandbox = ScriptedSandbox(False, True)
    task = _task(
        db_session,
        repo_url=str(repo),
        target_path="shop/money.py",
        test_command="pytest -q",
        issue_number=1,
        description="cart_total_cents returns the wrong number of cents",
    )
    run = runner.run_to_completion(db_session, task, agent_deps, use_rag=True)

    assert run.status == "validated", run.error
    coder_user = llm.calls[1][-1].content
    assert 'path="shop/cart.py"' in coder_user  # related code is provided…
    assert 'path="shop/money.py"' not in coder_user  # …but not the file sent in full
    assert all(c["path"] != "shop/money.py" for c in run.retrieval["context"])


def test_rag_off_skips_retrieval(
    db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    agent_deps.llm_factory = lambda: ScriptedLLM("plan", FIX)
    agent_deps.sandbox = ScriptedSandbox(False, True)
    run = runner.run_to_completion(db_session, _task(db_session), agent_deps, use_rag=False)
    assert run.status == "validated"
    assert run.use_rag is False and run.retrieval is None


def test_no_target_without_rag_localizes_from_the_file_list(
    db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    llm = ScriptedLLM("TARGET: calculator.py\nPLAN:\n1. fix", FIX)
    agent_deps.llm_factory = lambda: llm
    agent_deps.sandbox = ScriptedSandbox(False, True)
    run = runner.run_to_completion(
        db_session, _task(db_session, target_path=None), agent_deps, use_rag=False
    )
    assert run.status == "validated", run.error
    assert run.target_path == "calculator.py" and run.retrieval is None
    planner_user = llm.calls[0][-1].content
    assert "Repository files:" in planner_user and "<retrieved_context>" not in planner_user


def test_run_endpoint_accepts_use_rag(
    client: TestClient, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    _rag_deps(agent_deps, ScriptedLLM("TARGET: calculator.py\nPLAN:\n1. fix", FIX))
    agent_deps.sandbox = ScriptedSandbox(False, True)
    task = client.post(
        "/api/v1/tasks",
        json={"repo_url": _make_fixture_repo(), "test_command": "python -m unittest"},
        headers=auth_headers,
    ).json()
    started = client.post(
        f"/api/v1/tasks/{task['id']}/run", json={"use_rag": True}, headers=auth_headers
    )
    assert started.status_code == 202
    run = client.get(f"/api/v1/runs/{started.json()['id']}", headers=auth_headers).json()
    assert run["use_rag"] is True and run["target_path"] == "calculator.py"
    assert run["retrieval"]["candidates"]
