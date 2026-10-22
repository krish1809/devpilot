"""Copy curated real runs and benchmark results into a public showcase DB.

    # locally: write apps/api/showcase/showcase.json from tasks + benchmark runs
    python -m scripts.showcase export --tasks 3 4 51 --evals lite-s20-seed7
    # load it under the read-only demo user (any database, any time)
    DATABASE_URL=... python -m scripts.showcase import showcase/showcase.json
    # what the showcase deployment runs on every start (see the Dockerfile):
    python -m scripts.showcase autoload

`autoload` makes the deployed showcase refresh itself: committing a new
showcase file redeploys the API, and on start it imports the bundled file only
if its content changed since the last import (DEMO_MODE only; never blocks
startup). No database credentials ever leave the host.

Exports tasks with their runs, timeline events, pull requests, approvals, LLM
and MCP tool-call traces, plus benchmark runs with every result. Local paths
and provider account ids are scrubbed. Import is idempotent: it replaces the
demo user's tasks and any benchmark runs with the same names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.demo import get_or_create_demo_user
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.agent_run import AgentRun, Approval, PullRequest, RunEvent
from app.models.app_state import AppState
from app.models.eval import EvalResult, EvalRun
from app.models.task import Task
from app.models.trace import LlmCall, ToolCall

BUNDLED = Path(__file__).resolve().parents[1] / "showcase" / "showcase.json"
DEFAULT_OUT = BUNDLED
STATE_KEY = "showcase_sha256"
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


def autoload(db: Session, path: Path = BUNDLED, *, demo_mode: bool) -> str:
    """Import the bundled showcase file if its content changed since the last import."""
    if not demo_mode:
        return "skipped (not in demo mode)"
    if not path.exists():
        return f"skipped ({path.name} not found)"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    state = db.get(AppState, STATE_KEY)
    if state is not None and state.value == digest:
        return "unchanged"
    counts = import_(db, json.loads(raw))
    if state is None:
        db.add(AppState(key=STATE_KEY, value=digest))
    else:
        state.value = digest
    db.commit()
    return f"imported {counts}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--tasks", nargs="*", type=int, default=[])
    e.add_argument("--evals", nargs="*", default=[])
    e.add_argument("--out", type=Path, default=DEFAULT_OUT)
    i = sub.add_parser("import")
    i.add_argument("path", type=Path)
    a = sub.add_parser("autoload", help="import the bundled file if it changed (DEMO_MODE)")
    a.add_argument("--file", type=Path, default=BUNDLED)
    args = parser.parse_args()

    if args.cmd == "autoload":  # runs on every start: report problems, never block startup
        try:
            with SessionLocal() as db:
                outcome = autoload(db, args.file, demo_mode=get_settings().demo_mode)
            print(f"showcase autoload: {outcome}")
        except Exception as exc:  # noqa: BLE001
            print(f"showcase autoload failed (continuing): {type(exc).__name__}: {exc}",
                  file=sys.stderr)  # fmt: skip
        return

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
