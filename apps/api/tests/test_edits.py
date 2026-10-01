"""Phase 7: excerpts + SEARCH/REPLACE editing for large files, and untested runs."""

import pytest
from sqlalchemy.orm import Session

from app.agents import runner
from app.agents.edits import EditError, apply_edits, file_excerpt
from app.agents.graph import AgentDeps
from tests.test_agent import ScriptedLLM, ScriptedSandbox, _settings, _task

BIG = "\n".join(
    [f"def helper_{i}(x):\n    return x + {i}\n" for i in range(1000)]
    + ["def percent(part, whole):\n    return part // whole * 100\n"]
)


def test_excerpt_keeps_small_files_whole() -> None:
    assert file_excerpt("a = 1\n", "anything", 1000) == "a = 1\n"


def test_excerpt_finds_the_relevant_window_within_budget() -> None:
    out = file_excerpt(BIG, "percent() returns 0 for fractions", 1500)
    assert "def percent(part, whole)" in out
    assert len(out) < 2200
    assert "### lines 1-" in out and "other lines not shown" in out


def test_apply_edits_exact_and_whitespace_tolerant() -> None:
    reply = (
        "<<<<<<< SEARCH\n    return part // whole * 100\n=======\n"
        "    return part / whole * 100\n>>>>>>> REPLACE"
    )
    assert "return part / whole * 100" in apply_edits(BIG, reply)
    loose = reply.replace("return part // whole * 100\n", "return part // whole * 100   \n")
    assert "return part / whole * 100" in apply_edits(BIG, loose)


@pytest.mark.parametrize(
    "reply,message",
    [
        ("just prose", "No SEARCH/REPLACE"),
        ("<<<<<<< SEARCH\nnot in file\n=======\nx\n>>>>>>> REPLACE", "not found"),
        ("<<<<<<< SEARCH\n    return x\n=======\nx\n>>>>>>> REPLACE", "matches"),
        ("<<<<<<< SEARCH\ndef helper_1(x):\n=======\ndef helper_1(x):\n>>>>>>> REPLACE",
         "do not change"),
    ],
)  # fmt: skip
def test_apply_edits_errors(reply: str, message: str) -> None:
    with pytest.raises(EditError, match=message):
        apply_edits(BIG, reply)


def _big_repo_task(db_session: Session, tmp_path, **overrides):  # noqa: ANN001
    from tests.test_rag import _git_repo

    repo = _git_repo(tmp_path, {"calc.py": BIG, "README.md": "calc\n"})
    return _task(
        db_session, repo_url=str(repo), target_path="calc.py", test_command=None,
        description="percent(1, 4) returns 0 instead of 25.0", **overrides,
    )  # fmt: skip


GOOD_EDIT = (
    "<<<<<<< SEARCH\n    return part // whole * 100\n=======\n"
    "    return part / whole * 100\n>>>>>>> REPLACE"
)


def test_large_file_uses_excerpt_and_edit_blocks_without_tests(
    tmp_path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    llm = ScriptedLLM("1. use true division", GOOD_EDIT)
    agent_deps.llm_factory = lambda: llm
    agent_deps.sandbox = ScriptedSandbox(True)  # must not be called
    run = runner.run_to_completion(db_session, _big_repo_task(db_session, tmp_path), agent_deps)

    assert run.status == "validated", run.error
    assert run.test_passed is None and agent_deps.sandbox.calls == 0
    assert "+    return part / whole * 100" in run.diff
    coder_system, coder_user = llm.calls[1]
    assert "SEARCH" in coder_system.content
    assert "<file_excerpt>" in coder_user.content and "def helper_500" not in coder_user.content


def test_failed_edit_is_retried_with_feedback(
    tmp_path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    bad = "<<<<<<< SEARCH\nreturn nonsense\n=======\nx\n>>>>>>> REPLACE"
    llm = ScriptedLLM("plan", bad, GOOD_EDIT)
    agent_deps.llm_factory = lambda: llm
    run = runner.run_to_completion(db_session, _big_repo_task(db_session, tmp_path), agent_deps)

    assert run.status == "validated" and run.attempts == 2
    assert "could not be applied" in llm.calls[2][-1].content


def test_edit_failures_exhaust_attempts(
    tmp_path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps
) -> None:
    _settings(agent_deps, agent_max_attempts=2)
    agent_deps.llm_factory = lambda: ScriptedLLM("plan", "no blocks here")
    run = runner.run_to_completion(db_session, _big_repo_task(db_session, tmp_path), agent_deps)
    assert run.status == "error" and "No applicable edit" in run.error
