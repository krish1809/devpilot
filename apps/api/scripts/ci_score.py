"""Score DevPilot's SWE-bench predictions with the official harness — CI side.

Runs in GitHub Actions (``.github/workflows/swebench-score.yml``), where each
job has the disk space and Docker Hub bandwidth that SWE-bench images need (up
to ~9 GB unpacked) — more than a laptop can spare. It imports only the
standard-library ``app.evals.harness_io``, so the job installs nothing but the
official ``swebench`` package. Run from anywhere:

    python apps/api/scripts/ci_score.py score --predictions preds.jsonl \\
        --instance django__django-11620 --out scores/django__django-11620.json
    python apps/api/scripts/ci_score.py merge --dir scores --out swebench-scores.json

A predictions line is ``{"instance_id", "config", "model_name_or_path",
"model_patch"}`` (written by ``swebench_eval export-predictions``). Each verdict
has the same shape the local scorer stores: ``{"resolved", "score_detail"}``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, no install needed

from app.evals import harness_io  # noqa: E402

MAX_HARNESS_ERRORS = 3
RETRY_PAUSE_SECONDS = 30


def load_predictions(path: Path, instance_id: str | None = None) -> list[dict]:
    preds = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [p for p in preds if instance_id is None or p["instance_id"] == instance_id]


def score_one(
    pred: dict,
    *,
    workdir: Path,
    timeout: int,
    python: str = sys.executable,
    retries: int = MAX_HARNESS_ERRORS,
    pause: float = RETRY_PAUSE_SECONDS,
    run: Callable | None = None,
    sleep: Callable[[float], None] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """The harness verdict for one prediction, retrying harness errors."""
    run = run or subprocess.run  # looked up at call time (patchable in tests)
    sleep = sleep or time.sleep
    instance_id, config = pred["instance_id"], pred["config"]
    model = harness_io.model_name(config)
    run_id = f"ci-{config.replace('+', '-')}"
    preds = workdir / f"{run_id}.{instance_id}.jsonl"
    harness_io.write_prediction(preds, instance_id, config, pred["model_patch"])
    cmd = harness_io.harness_command(python, instance_id, preds, run_id, workdir, timeout)

    stderr = ""
    for attempt in range(1, retries + 1):
        try:
            proc = run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout + 1200)
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired:
            stderr = "harness timed out"
        verdict = harness_io.read_verdict(workdir, run_id, model, instance_id)
        if verdict is not None:
            log(f"{instance_id} [{config}] resolved={verdict['resolved']}")
            return verdict
        log(f"{instance_id} [{config}] harness error (attempt {attempt}/{retries})")
        if attempt < retries:
            sleep(pause)
    return {
        "resolved": False,
        "score_detail": {
            "harness_errors": retries,
            "stderr": harness_io.scrub(stderr[-1500:]),
            "infra_failure": "harness_error",
        },
    }


def cmd_score(args: argparse.Namespace) -> None:
    preds = load_predictions(Path(args.predictions), args.instance)
    if not preds:
        raise SystemExit(f"No predictions for {args.instance} in {args.predictions}")
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    results = {p["config"]: score_one(p, workdir=workdir, timeout=args.timeout) for p in preds}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"instance_id": args.instance, "results": results}, indent=2))


def merge(paths: list[Path]) -> dict:
    rows = []
    for path in sorted(paths):
        data = json.loads(path.read_text())
        for config, verdict in sorted(data["results"].items()):
            rows.append({"instance_id": data["instance_id"], "config": config, **verdict})
    return {
        "dataset": harness_io.DATASET,
        "scored_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": rows,
    }


def cmd_merge(args: argparse.Namespace) -> None:
    merged = merge(list(Path(args.dir).glob("*.json")))
    Path(args.out).write_text(json.dumps(merged, indent=2))
    print(f"Merged {len(merged['results'])} verdicts into {args.out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score one instance's predictions")
    s.add_argument("--predictions", required=True)
    s.add_argument("--instance", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--workdir", default="harness-work")
    s.add_argument("--timeout", type=int, default=1800)
    s.set_defaults(fn=cmd_score)
    m = sub.add_parser("merge", help="combine per-instance score files")
    m.add_argument("--dir", required=True)
    m.add_argument("--out", required=True)
    m.set_defaults(fn=cmd_merge)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
