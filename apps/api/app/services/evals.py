"""Read-side queries for benchmark results (written by scripts/swebench_eval.py)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evals.swebench import summarize
from app.models.eval import EvalResult, EvalRun


def _configs(run: EvalRun, results: list[EvalResult]) -> list[str]:
    extra = [c for c in sorted({r.config for r in results}) if c not in run.configs]
    return list(run.configs) + extra  # e.g. "gold" calibration


def _summary(run: EvalRun, results: list[EvalResult]) -> dict:
    return {
        "id": run.id,
        "name": run.name,
        "dataset": run.dataset,
        "model": run.model,
        "instance_count": len(run.instance_ids),
        "configs": _configs(run, results),
        "settings": run.settings or {},
        "created_at": run.created_at,
        "summary": summarize(results, _configs(run, results)),
    }


def _results(db: Session, run_id: int) -> list[EvalResult]:
    return list(
        db.scalars(
            select(EvalResult)
            .where(EvalResult.eval_run_id == run_id)
            .order_by(EvalResult.instance_id, EvalResult.config)
        ).all()
    )


def list_eval_runs(db: Session) -> list[dict]:
    runs = db.scalars(select(EvalRun).order_by(EvalRun.id.desc())).all()
    return [_summary(run, _results(db, run.id)) for run in runs]


def get_eval_run(db: Session, run_id: int) -> dict | None:
    run = db.get(EvalRun, run_id)
    if run is None:
        return None
    results = _results(db, run.id)
    return {**_summary(run, results), "instance_ids": run.instance_ids, "results": results}
