"""Run DevPilot on SWE-bench Lite and score it with the official harness.

    cd apps/api
    python -m scripts.swebench_eval generate --name lite-s20 --n 20 --seed 7 \
        --owner you@example.com [--configs rag oracle-file oracle-file+rag]
    python -m scripts.swebench_eval score  --name lite-s20
    python -m scripts.swebench_eval report --name lite-s20   # -> docs/eval/
    # or all of it, unattended across LLM daily-quota windows:
    python -m scripts.swebench_eval run-all --name lite-s20 --n 20 --seed 7 \
        --owner you@example.com --with-gold
    # without the local disk scoring needs: score in GitHub Actions instead
    python -m scripts.swebench_eval ci-score --name lite-s20 --with-gold
    python -m scripts.swebench_eval pipeline --name lite-s20 --n 20 --seed 7 \
        --owner you@example.com --with-gold   # generate → CI scoring → publish

Both generate and score are resumable: re-running skips finished work, and
generate stops cleanly when the LLM provider's daily quota runs out.
See docs/eval/README.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.evals import report
from app.evals import swebench as sb
from app.models.eval import EvalRun
from app.services.user import get_user_by_email
from scripts import eval_pipeline as pipe

DOCS = Path(__file__).resolve().parents[3] / "docs" / "eval"


def _run(db, name: str) -> EvalRun:  # noqa: ANN001
    run = db.scalar(select(EvalRun).where(EvalRun.name == name))
    if run is None:
        raise SystemExit(f"No eval run named {name!r}; run `generate` first.")
    return run


def cmd_generate(args: argparse.Namespace) -> bool:
    """Returns True when every (instance, config) has a result."""
    instances = sb.load_dataset()
    if args.instances:
        wanted = set(args.instances)
        chosen = [i for i in instances if i.instance_id in wanted]
    else:
        chosen = sb.sample(instances, args.n, args.seed)
    settings = sb.eval_settings()
    with SessionLocal() as db:
        owner = get_user_by_email(db, args.owner)
        if owner is None:
            raise SystemExit(f"No user {args.owner!r}")
        run = sb.get_or_create_run(
            db,
            args.name,
            chosen,
            args.configs,
            {"seed": args.seed, "n": len(chosen), **sb.EVAL_SETTINGS,
             "embedding_model": settings.embedding_model},
        )  # fmt: skip
        by_id = {i.instance_id: i for i in instances}
        ordered = [by_id[i] for i in run.instance_ids]
        print(f"Eval run #{run.id} {run.name}: {len(ordered)} instances × {run.configs}")
        deps = sb.make_deps(SessionLocal, settings)
        try:
            sb.generate(db, deps, run, ordered, owner.id, keep_index=args.keep_index)
        except sb.QuotaExhausted:
            print("Stopped: LLM daily token quota reached. Re-run later to resume.")
            return False
        except sb.LowDisk as exc:
            print(f"Stopped generating: {exc}")
            return False
        return True


def cmd_score(args: argparse.Namespace) -> bool:
    """Returns True when every generated result has been scored."""
    with SessionLocal() as db:
        run = _run(db, args.name)
        if args.with_gold:
            sb.queue_gold_for_attempted(db, run)
        try:
            sb.score(
                db,
                run,
                workdir=sb.CACHE / "harness",
                remove_images=not args.keep_images,
                timeout=args.timeout,
            )
        except sb.LowDisk as exc:
            print(f"Stopped scoring: {exc}")
            return False
        return True


def cmd_report(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        try:
            md_path, _ = report.write_report(db, args.name, DOCS)
        except LookupError as exc:
            raise SystemExit(str(exc)) from exc
    print(md_path.read_text())


def cmd_run_all(args: argparse.Namespace) -> None:
    """Loop generate → score → report until every result is generated and scored.

    Sleeps between passes to wait out the LLM's daily quota or a low-disk stop;
    each pass resumes where the previous one stopped.
    """
    import time

    while True:
        generated = cmd_generate(args)
        scored = cmd_score(args)
        cmd_report(args)  # refresh the (partial) report after every pass
        if generated and scored:
            print("All instances generated and scored.")
            return
        print(
            f"Waiting {args.sleep}s before the next pass (LLM quota window / disk space)…",
            flush=True,
        )
        time.sleep(args.sleep)


def cmd_export_predictions(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        preds = sb.export_predictions(db, _run(db, args.name))
    out = Path(args.out) if args.out else DOCS.parents[1] / pipe.predictions_path(args.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(p, sort_keys=True) + "\n" for p in preds))
    print(f"Wrote {len(preds)} predictions to {out}")


def cmd_import_scores(args: argparse.Namespace) -> None:
    scores = json.loads(Path(args.file).read_text())
    with SessionLocal() as db:
        counts = sb.import_scores(db, _run(db, args.name), scores, source=args.source)
    print(f"Imported: {counts}")


def _ci_deps() -> tuple[pipe.Publisher, pipe.Actions]:
    publisher = pipe.default_publisher(sb.CACHE)
    return publisher, pipe.Actions(pipe.github_repo(publisher.remote))


def cmd_ci_score(args: argparse.Namespace) -> None:
    publisher, actions = _ci_deps()
    pending = pipe.ci_score(
        args.name,
        with_gold=args.with_gold,
        publisher=publisher,
        actions=actions,
        session_factory=SessionLocal,
        force=args.force,
    )
    print(f"{pending} results still unscored.")


def cmd_pipeline(args: argparse.Namespace) -> None:
    publisher, actions = _ci_deps()
    pipe.run_pipeline(
        name=args.name,
        generate=lambda: cmd_generate(args),
        with_gold=args.with_gold,
        publisher=publisher,
        actions=actions,
        session_factory=SessionLocal,
        showcase_tasks=args.showcase_tasks,
        showcase_evals=args.showcase_evals or [args.name, *filter(None, [args.ablation])],
        ablation=args.ablation,
        marker=sb.CACHE / f"pipeline-{args.name}.done",
        sleep_seconds=args.sleep,
        ci_attempts=args.ci_attempts,
        site=args.site,
        api=args.api,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--name", required=True)
    g.add_argument("--owner", required=True)
    g.add_argument("--n", type=int, default=20)
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--instances", nargs="*")
    g.add_argument("--configs", nargs="+", default=list(sb.CONFIGS), choices=list(sb.CONFIGS))
    g.add_argument("--keep-index", action="store_true")
    g.set_defaults(fn=cmd_generate)
    s = sub.add_parser("score")
    s.add_argument("--name", required=True)
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--keep-images", action="store_true")
    s.add_argument("--with-gold", action="store_true", help="also score reference patches")
    s.set_defaults(fn=cmd_score)
    a = sub.add_parser("run-all", help="generate+score+report until complete")
    for flag, kw in (
        ("--name", {"required": True}), ("--owner", {"required": True}),
        ("--n", {"type": int, "default": 20}), ("--seed", {"type": int, "default": 7}),
        ("--instances", {"nargs": "*"}), ("--timeout", {"type": int, "default": 1800}),
        ("--sleep", {"type": int, "default": 1800}),
    ):  # fmt: skip
        a.add_argument(flag, **kw)
    a.add_argument("--configs", nargs="+", default=list(sb.CONFIGS), choices=list(sb.CONFIGS))
    a.add_argument("--keep-index", action="store_true")
    a.add_argument("--keep-images", action="store_true")
    a.add_argument("--with-gold", action="store_true")
    a.set_defaults(fn=cmd_run_all)
    r = sub.add_parser("report")
    r.add_argument("--name", required=True)
    r.set_defaults(fn=cmd_report)
    e = sub.add_parser("export-predictions", help="write the run's patches as harness input")
    e.add_argument("--name", required=True)
    e.add_argument("--out", help="default: docs/eval/predictions/<name>.jsonl")
    e.set_defaults(fn=cmd_export_predictions)
    i = sub.add_parser("import-scores", help="apply a CI verdicts file (swebench-scores.json)")
    i.add_argument("--name", required=True)
    i.add_argument("--file", required=True)
    i.add_argument("--source", default="GitHub Actions")
    i.set_defaults(fn=cmd_import_scores)
    c = sub.add_parser("ci-score", help="score in GitHub Actions and import the verdicts")
    c.add_argument("--name", required=True)
    c.add_argument("--with-gold", action="store_true")
    c.add_argument("--force", action="store_true", help="re-score even if nothing is pending")
    c.set_defaults(fn=cmd_ci_score)
    pl = sub.add_parser("pipeline", help="generate → score in CI → publish, unattended")
    for flag, kw in (
        ("--name", {"required": True}), ("--owner", {"required": True}),
        ("--n", {"type": int, "default": 20}), ("--seed", {"type": int, "default": 7}),
        ("--instances", {"nargs": "*"}), ("--sleep", {"type": int, "default": 1800}),
        ("--ci-attempts", {"type": int, "default": 5}),
        ("--showcase-tasks", {"nargs": "*", "type": int, "default": [3, 4, 51]}),
        ("--showcase-evals", {"nargs": "*"}), ("--ablation", {"default": None}),
        ("--site", {"default": None}), ("--api", {"default": None}),
    ):  # fmt: skip
        pl.add_argument(flag, **kw)
    pl.add_argument("--configs", nargs="+", default=list(sb.CONFIGS), choices=list(sb.CONFIGS))
    pl.add_argument("--keep-index", action="store_true")
    pl.add_argument("--with-gold", action="store_true")
    pl.set_defaults(fn=cmd_pipeline)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
