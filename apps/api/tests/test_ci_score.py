"""CI-side SWE-bench scoring (scripts/ci_score.py): no Docker, fake harness."""

import json
import subprocess
from pathlib import Path

from app.evals import harness_io
from scripts import ci_score

PRED = {
    "instance_id": "a__a-1",
    "config": "oracle-file+rag",
    "model_name_or_path": "devpilot-oracle-file+rag",
    "model_patch": "diff --git a/x.py b/x.py\n",
}


class FakeHarness:
    """Mimics run_evaluation's outputs; each call follows the next scripted outcome."""

    def __init__(self, *outcomes: str) -> None:
        self.outcomes = list(outcomes)  # "resolved" | "unresolved" | "error" | "timeout"
        self.calls: list[list[str]] = []

    def __call__(self, cmd, cwd, **kwargs):  # noqa: ANN001, ANN003, ANN204
        self.calls.append(cmd)
        outcome = self.outcomes.pop(0)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        if outcome in ("resolved", "unresolved"):
            run_id = cmd[cmd.index("-id") + 1]
            pred = json.loads(Path(cmd[cmd.index("-p") + 1]).read_text())
            model, iid = pred["model_name_or_path"], pred["instance_id"]
            report = Path(cwd) / "logs" / "run_evaluation" / run_id / model / iid / "report.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({iid: {
                "resolved": outcome == "resolved",
                "patch_successfully_applied": True,
                "tests_status": {"FAIL_TO_PASS": {"success": ["t1", "t2"], "failure": []}},
            }}))  # fmt: skip
            (Path(cwd) / f"{model}.{run_id}.json").write_text(json.dumps({"failure_reasons": {}}))
        return subprocess.CompletedProcess(cmd, 1 if outcome == "error" else 0, "", "boom org_X1")


def _score(tmp_path: Path, harness: FakeHarness) -> dict:
    return ci_score.score_one(
        PRED, workdir=tmp_path, timeout=60, run=harness, sleep=lambda s: None, log=lambda m: None
    )


def test_reads_the_official_report(tmp_path: Path) -> None:
    harness = FakeHarness("resolved")
    verdict = _score(tmp_path, harness)

    assert verdict == {
        "resolved": True,
        "score_detail": {
            "patch_applied": True,
            "tests_status": {"FAIL_TO_PASS": {"success": 2, "failure": 0}},
            "infra_failure": None,
        },
    }
    cmd = harness.calls[0]
    assert cmd[1:3] == ["-m", "swebench.harness.run_evaluation"]
    assert cmd[cmd.index("-i") + 1] == "a__a-1"
    assert cmd[cmd.index("-id") + 1] == "ci-oracle-file-rag"  # '+' is not run-id safe


def test_retries_harness_errors_then_scores(tmp_path: Path) -> None:
    harness = FakeHarness("error", "timeout", "unresolved")
    verdict = _score(tmp_path, harness)

    assert verdict["resolved"] is False
    assert verdict["score_detail"]["infra_failure"] is None  # a real verdict, not infra
    assert len(harness.calls) == 3


def test_persistent_harness_errors_become_infra_failures(tmp_path: Path) -> None:
    verdict = _score(tmp_path, FakeHarness("error", "error", "error"))

    assert verdict["resolved"] is False
    assert verdict["score_detail"]["infra_failure"] == "harness_error"
    assert verdict["score_detail"]["harness_errors"] == 3
    assert "org_X1" not in verdict["score_detail"]["stderr"]  # account ids scrubbed


def test_score_command_writes_one_file_per_instance(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    preds = tmp_path / "preds.jsonl"
    other = {**PRED, "instance_id": "b__b-2"}
    gold = {**PRED, "config": "gold", "model_name_or_path": "devpilot-gold"}
    preds.write_text("\n".join(json.dumps(p) for p in (PRED, other, gold)) + "\n")
    harness = FakeHarness("resolved", "unresolved")
    monkeypatch.setattr(ci_score.subprocess, "run", harness)
    monkeypatch.setattr(ci_score.time, "sleep", lambda s: None)

    out = tmp_path / "scores" / "a__a-1.json"
    ci_score.main(["score", "--predictions", str(preds), "--instance", "a__a-1",
                   "--out", str(out), "--workdir", str(tmp_path / "w")])  # fmt: skip

    data = json.loads(out.read_text())
    assert data["instance_id"] == "a__a-1"
    assert set(data["results"]) == {"oracle-file+rag", "gold"}  # b__b-2 is another job's
    assert len(harness.calls) == 2


def test_merge_flattens_and_sorts(tmp_path: Path) -> None:
    verdict = {"resolved": True, "score_detail": {"infra_failure": None}}
    (tmp_path / "b.json").write_text(
        json.dumps({"instance_id": "b__b-2", "results": {"rag": verdict}})
    )
    (tmp_path / "a.json").write_text(
        json.dumps({"instance_id": "a__a-1", "results": {"rag": verdict, "gold": verdict}})
    )

    merged = ci_score.merge(list(tmp_path.glob("*.json")))

    assert merged["dataset"] == harness_io.DATASET
    assert [(r["instance_id"], r["config"]) for r in merged["results"]] == [
        ("a__a-1", "gold"),
        ("a__a-1", "rag"),
        ("b__b-2", "rag"),
    ]
    assert merged["results"][0]["resolved"] is True


def test_read_verdict_reports_infra_failure_reasons(tmp_path: Path) -> None:
    run_id, model, iid = "r", "devpilot-rag", "a__a-1"
    report = tmp_path / "logs" / "run_evaluation" / run_id / model / iid / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({iid: {"resolved": False, "tests_status": {}}}))
    (tmp_path / f"{model}.{run_id}.json").write_text(
        json.dumps({"failure_reasons": {iid: "network_unreachable"}})
    )

    verdict = harness_io.read_verdict(tmp_path, run_id, model, iid)

    assert verdict["score_detail"]["infra_failure"] == "network_unreachable"
    assert harness_io.read_verdict(tmp_path, "missing", model, iid) is None
