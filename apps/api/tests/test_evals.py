"""Phase 7: SWE-bench harness pieces (no network, no Docker, fake LLM)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.graph import AgentDeps
from app.evals import swebench as sb
from app.models.eval import EvalResult
from tests.test_agent import FIX, ScriptedLLM
from tests.test_rag import HashEmbedder, _git_repo

PATCH = (
    "diff --git a/calculator.py b/calculator.py\n--- a/calculator.py\n+++ b/calculator.py\n"
    "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
)


def test_wilson_interval() -> None:
    assert sb.wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = sb.wilson_interval(5, 20)
    assert 0.10 < lo < 0.13 and 0.46 < hi < 0.50


def test_sample_is_seeded_and_sorted() -> None:
    insts = [sb.Instance(f"r__r-{i}", "o/r", "sha", "issue", PATCH) for i in range(50)]
    a, b = sb.sample(insts, 5, seed=7), sb.sample(insts, 5, seed=7)
    assert [i.instance_id for i in a] == [i.instance_id for i in b]
    assert [i.instance_id for i in a] == sorted(i.instance_id for i in a)
    assert a[0].gold_path == "calculator.py"


def _fixture_instance(tmp_path: Path, monkeypatch) -> sb.Instance:  # noqa: ANN001
    repo = _git_repo(tmp_path, {
        "calculator.py": "def add(a, b):\n    return a - b\n",
        "README.md": "Calculator. add() adds two numbers.\n",
    })  # fmt: skip
    from app.integrations import git_ops

    sha = git_ops.head_commit(repo)
    monkeypatch.setattr(sb, "prepare_checkout", lambda inst: repo)
    return sb.Instance("demo__calc-1", "demo/calc", sha, "add() subtracts instead of adding", PATCH)


def test_generate_runs_each_config_once_and_records_results(
    tmp_path: Path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps, monkeypatch
) -> None:
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    inst = _fixture_instance(tmp_path, monkeypatch)
    agent_deps.settings = sb.eval_settings(agent_deps.settings)
    agent_deps.embedder_factory = HashEmbedder
    agent_deps.llm_factory = lambda: ScriptedLLM("TARGET: calculator.py\nPLAN:\n1. fix", FIX)

    run = sb.get_or_create_run(db_session, "t", [inst], ["rag", "oracle-file"], {"seed": 1})
    sb.generate(db_session, agent_deps, run, [inst], owner.id, keep_index=True, log=lambda m: None)
    sb.generate(db_session, agent_deps, run, [inst], owner.id, log=lambda m: None)  # resumable

    rows = db_session.query(EvalResult).filter_by(eval_run_id=run.id).all()
    assert sorted(r.config for r in rows) == ["oracle-file", "rag"]
    for r in rows:
        assert r.status == "validated" and r.resolved is None
        assert "+    return a + b" in r.patch
        assert r.localized is True and r.gold_path == "calculator.py"


def test_quota_exhaustion_stops_generation(
    tmp_path: Path, db_session: Session, auth_headers: dict, agent_deps: AgentDeps, monkeypatch
) -> None:
    from app.integrations.llm import LLMError
    from app.services.user import get_user_by_email

    owner = get_user_by_email(db_session, "owner@example.com")
    inst = _fixture_instance(tmp_path, monkeypatch)
    agent_deps.llm_factory = lambda: ScriptedLLM(
        LLMError("LLM returned 429: Rate limit reached on tokens per day (TPD)")
    )
    run = sb.get_or_create_run(db_session, "q", [inst], ["oracle-file"], {})
    with pytest.raises(sb.QuotaExhausted):
        sb.generate(db_session, agent_deps, run, [inst], owner.id, log=lambda m: None)
    assert db_session.query(EvalResult).filter_by(eval_run_id=run.id).count() == 0


def test_score_reads_official_reports(tmp_path: Path, db_session: Session, monkeypatch) -> None:
    run = sb.get_or_create_run(db_session, "s", [], ["rag"], {})
    for iid, patch in (("a__a-1", PATCH), ("b__b-2", None)):
        db_session.add(EvalResult(eval_run_id=run.id, instance_id=iid, repo="x/y",
                                  config="rag", status="validated", patch=patch))  # fmt: skip
    db_session.commit()

    def fake_harness(cmd, cwd, **kwargs):  # noqa: ANN001, ANN003
        iid, run_id = cmd[cmd.index("-i") + 1], cmd[cmd.index("-id") + 1]
        out = Path(cwd) / "logs" / "run_evaluation" / run_id / "devpilot-rag" / iid
        out.mkdir(parents=True)
        (out / "report.json").write_text(json.dumps({iid: {
            "resolved": True, "patch_successfully_applied": True,
            "tests_status": {"FAIL_TO_PASS": {"success": ["t1"], "failure": []}},
        }}))  # fmt: skip
        return type("P", (), {"stderr": "", "returncode": 0})()

    monkeypatch.setattr(sb, "SWEBENCH_PY", tmp_path / "python")
    (tmp_path / "python").write_text("")
    monkeypatch.setattr(sb.subprocess, "run", fake_harness)
    monkeypatch.setattr(sb, "_remove_instance_images", lambda iid: None)
    sb.score(db_session, run, workdir=tmp_path / "work", log=lambda m: None)

    by_id = {r.instance_id: r for r in db_session.query(EvalResult).all()}
    assert by_id["a__a-1"].resolved is True
    assert by_id["a__a-1"].score_detail["tests_status"]["FAIL_TO_PASS"] == {
        "success": 1,
        "failure": 0,
    }
    assert by_id["b__b-2"].resolved is False  # no patch → unresolved without running


def test_eval_endpoints(client: TestClient, db_session: Session, auth_headers: dict) -> None:
    run = sb.get_or_create_run(db_session, "api", [], ["rag"], {"seed": 3})
    db_session.add_all([
        EvalResult(eval_run_id=run.id, instance_id="a__a-1", repo="a/a", config="rag",
                   status="validated", patch=PATCH, resolved=True, localized=True),
        EvalResult(eval_run_id=run.id, instance_id="b__b-2", repo="b/b", config="rag",
                   status="error", resolved=False, localized=False),
    ])  # fmt: skip
    db_session.commit()

    assert client.get("/api/v1/evals").status_code == 401
    listed = client.get("/api/v1/evals", headers=auth_headers).json()
    summary = listed[0]["summary"][0]
    assert summary["config"] == "rag" and summary["resolved"] == 1 and summary["scored"] == 2
    assert summary["resolve_rate"] == 0.5

    detail = client.get(f"/api/v1/evals/{run.id}", headers=auth_headers).json()
    assert len(detail["results"]) == 2 and detail["settings"] == {"seed": 3}
    assert client.get("/api/v1/evals/999", headers=auth_headers).status_code == 404
