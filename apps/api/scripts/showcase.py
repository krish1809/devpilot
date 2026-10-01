"""Copy curated real runs and benchmark results into a public showcase DB.

    # locally: write deploy/showcase.json from chosen tasks + benchmark runs
    python -m scripts.showcase export --tasks 3 4 51 --evals lite-s20-seed7
    # on the deployed database (DEMO_MODE): load it under the read-only demo user
    DATABASE_URL=... python -m scripts.showcase import ../../deploy/showcase.json

Exports tasks with their runs, timeline events, pull requests, approvals, LLM
and MCP tool-call traces, plus benchmark runs with every result. Local paths
and provider account ids are scrubbed. Import is idempotent: it replaces the
demo user's tasks and any benchmark runs with the same names.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, delete, select
from sqlalchemy.orm import Session

from app.core.demo import get_or_create_demo_user
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.agent_run import AgentRun, Approval, PullRequest, RunEvent
from app.models.eval import EvalResult, EvalRun
from app.models.task import Task
from app.models.trace import LlmCall, ToolCall

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "deploy" / "showcase.json"
_HOME = str(Path.home())
_SCRUBS = [
    (re.compile(re.escape(_HOME)), "~"),
    (re.compile(r"/tmp/[\w.-]*devpilot[\w.-]*"), "/tmp/…"),
    (re.compile(r"org_[A-Za-z0-9]+"), "org_[redacted]"),
]
_CHILDREN = (RunEvent, PullRequest, Approval, LlmCall, ToolCall)


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        for pattern, repl in _SCRUBS:
            value = pattern.sub(repl, value)
        return value
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def _row(obj: Base, drop: tuple[str, ...] = ()) -> dict:
    out = {}
    for col in obj.__table__.columns:
        if col.name in drop or col.computed is not None:
            continue
        value = getattr(obj, col.name)
        out[col.name] = value.isoformat() if isinstance(value, datetime) else scrub(value)
    return out


def _load(model: type[Base], data: dict, **overrides: Any) -> Base:
    values = {**data, **overrides}
    for col in model.__table__.columns:
        if isinstance(col.type, DateTime) and isinstance(values.get(col.name), str):
            values[col.name] = datetime.fromisoformat(values[col.name])
    return model(**values)


# --------------------------------------------------------------------------- #
def export(db: Session, task_ids: list[int], eval_names: list[str]) -> dict:
    tasks = []
    for task in db.scalars(select(Task).where(Task.id.in_(task_ids)).order_by(Task.id)):
        runs = []
        for run in db.scalars(select(AgentRun).where(AgentRun.task_id == task.id)):
            children = {
                model.__tablename__: [
                    _row(c, drop=("id", "run_id"))
                    for c in db.scalars(select(model).where(model.run_id == run.id))
                ]
                for model in _CHILDREN
            }
            runs.append({"run": _row(run, drop=("id", "task_id")), **children})
        tasks.append({"task": _row(task, drop=("id", "owner_id")), "runs": runs})

    evals = []
    for run in db.scalars(select(EvalRun).where(EvalRun.name.in_(eval_names))):
        results = db.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id))
        evals.append(
            {
                "eval_run": _row(run, drop=("id",)),
                "results": [_row(r, drop=("id", "eval_run_id", "agent_run_id")) for r in results],
            }
        )
    return {"version": 1, "tasks": tasks, "evals": evals}


def import_(db: Session, data: dict) -> dict:
    demo = get_or_create_demo_user(db)
    db.execute(delete(Task).where(Task.owner_id == demo.id))  # cascades to runs etc.
    names = [e["eval_run"]["name"] for e in data["evals"]]
    db.execute(delete(EvalRun).where(EvalRun.name.in_(names)))
    db.flush()

    counts = {"tasks": 0, "runs": 0, "eval_results": 0}
    for item in data["tasks"]:
        task = _load(Task, item["task"], owner_id=demo.id)
        db.add(task)
        db.flush()
        counts["tasks"] += 1
        for r in item["runs"]:
            run = _load(AgentRun, r["run"], task_id=task.id)
            db.add(run)
            db.flush()
            counts["runs"] += 1
            for model in _CHILDREN:
                db.add_all(_load(model, c, run_id=run.id) for c in r[model.__tablename__])
    for item in data["evals"]:
        run = _load(EvalRun, item["eval_run"])
        db.add(run)
        db.flush()
        db.add_all(_load(EvalResult, r, eval_run_id=run.id) for r in item["results"])
        counts["eval_results"] += len(item["results"])
    db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--tasks", nargs="*", type=int, default=[])
    e.add_argument("--evals", nargs="*", default=[])
    e.add_argument("--out", type=Path, default=DEFAULT_OUT)
    i = sub.add_parser("import")
    i.add_argument("path", type=Path)
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.cmd == "export":
            data = export(db, args.tasks, args.evals)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(data, indent=1, default=str))
            print(f"Wrote {args.out}: {len(data['tasks'])} tasks, {len(data['evals'])} evals")
        else:
            print("Imported:", import_(db, json.loads(args.path.read_text())))


if __name__ == "__main__":
    main()
