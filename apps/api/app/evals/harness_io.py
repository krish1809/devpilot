"""Running the official SWE-bench harness and reading its verdicts.

Standard library only, so the CI scoring job (``scripts/ci_score.py``) can import
it without installing the API's dependencies: local and CI scoring share one
implementation of the command line and of how a verdict is read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATASET = "SWE-bench/SWE-bench_Lite"
_ORG_ID = re.compile(r"org_[A-Za-z0-9]+")


def scrub(text: str | None) -> str | None:
    """Remove account identifiers (e.g. a provider org id in an error message)."""
    return _ORG_ID.sub("org_[redacted]", text) if text else text


def model_name(config: str) -> str:
    """The harness groups predictions by model name; one per DevPilot config."""
    return f"devpilot-{config}"


def write_prediction(path: Path, instance_id: str, config: str, patch: str) -> None:
    path.write_text(
        json.dumps(
            {
                "instance_id": instance_id,
                "model_name_or_path": model_name(config),
                "model_patch": patch,
            }
        )
        + "\n"
    )


def harness_command(
    python: str, instance_id: str, predictions: Path, run_id: str, workdir: Path, timeout: int
) -> list[str]:
    """``swebench.harness.run_evaluation`` for one instance (run with cwd=workdir)."""
    return [
        python, "-m", "swebench.harness.run_evaluation",
        "-d", DATASET, "-s", "test", "-i", instance_id, "-p", str(predictions),
        "--max_workers", "1", "-t", str(timeout), "-id", run_id,
        "--report_dir", str(workdir),
    ]  # fmt: skip


def summarize_tests(status: dict) -> dict:
    """Test-name lists → counts, e.g. {"FAIL_TO_PASS": {"success": 3, "failure": 0}}."""
    return {
        group: {k: len(v) for k, v in (outcome or {}).items()} for group, outcome in status.items()
    }


def read_verdict(workdir: Path, run_id: str, model: str, instance_id: str) -> dict | None:
    """The harness's verdict on one prediction: ``{"resolved", "score_detail"}``.

    None when it wrote no report — the harness itself failed (e.g. Docker Hub
    couldn't serve the image), which is not a verdict on the patch.
    """
    report = workdir / "logs" / "run_evaluation" / run_id / model / instance_id / "report.json"
    if not report.exists():
        return None
    run_report = workdir / f"{model}.{run_id}.json"
    reasons = {}
    if run_report.exists():
        reasons = json.loads(run_report.read_text()).get("failure_reasons") or {}
    detail = json.loads(report.read_text()).get(instance_id, {})
    return {
        "resolved": bool(detail.get("resolved")),
        "score_detail": {
            "patch_applied": detail.get("patch_successfully_applied"),
            "tests_status": summarize_tests(detail.get("tests_status") or {}),
            "infra_failure": reasons.get(instance_id),
        },
    }
