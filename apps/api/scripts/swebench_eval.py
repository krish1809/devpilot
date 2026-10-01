"""Run DevPilot on SWE-bench Lite and score it with the official harness.

    cd apps/api
    python -m scripts.swebench_eval generate --name lite-s20 --n 20 --seed 7 \
        --owner you@example.com [--configs rag oracle-file oracle-file+rag]
    python -m scripts.swebench_eval score  --name lite-s20
    python -m scripts.swebench_eval report --name lite-s20   # -> docs/eval/
    # or all of it, unattended across LLM daily-quota windows:
    python -m scripts.swebench_eval run-all --name lite-s20 --n 20 --seed 7 \
        --owner you@example.com --with-gold

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
from app.evals import swebench as sb
from app.models.eval import EvalResult, EvalRun
from app.services.user import get_user_by_email

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
        return True


def cmd_score(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        run = _run(db, args.name)
        if args.with_gold:  # only for instances the agent has attempted
            by_id = {i.instance_id: i for i in sb.load_dataset()}
            attempted = set(
                db.scalars(
                    select(EvalResult.instance_id).where(
                        EvalResult.eval_run_id == run.id, EvalResult.config != "gold"
                    )
                )
            )
            sb.add_gold(db, run, [by_id[i] for i in run.instance_ids if i in attempted])
        sb.score(
            db,
            run,
            workdir=sb.CACHE / "harness",
            remove_images=not args.keep_images,
            timeout=args.timeout,
        )


def cmd_report(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        run = _run(db, args.name)
        results = list(db.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id)).all())
        configs = run.configs + (["gold"] if any(r.config == "gold" for r in results) else [])
        summary = sb.summarize(results, configs)
    DOCS.mkdir(parents=True, exist_ok=True)
    data = {
        "name": run.name,
        "dataset": run.dataset,
        "model": run.model,
        "settings": run.settings,
        "instances": run.instance_ids,
        "summary": summary,
        "results": [
            {k: getattr(r, k) for k in ("instance_id", "config", "status", "target_path",
             "gold_path", "localized", "resolved", "llm_calls", "prompt_tokens",
             "completion_tokens", "seconds", "error")}
            for r in sorted(results, key=lambda r: (r.instance_id, r.config))
        ],
    }  # fmt: skip
    for row in data["results"]:
        row["error"] = sb.scrub(row["error"])
    stem = DOCS / f"phase7-{run.name}"
    stem.with_suffix(".json").write_text(json.dumps(data, indent=2, default=str))
    stem.with_suffix(".md").write_text(render_markdown(run, summary, results, configs))
    print(stem.with_suffix(".md").read_text())


def cmd_run_all(args: argparse.Namespace) -> None:
    """generate → score → (sleep while the LLM quota refills) → … → report."""
    import time

    while True:
        done = cmd_generate(args)
        cmd_score(args)
        cmd_report(args)  # refresh the (partial) report after every pass
        if done:
            print("All instances generated and scored.")
            return
        print(f"Waiting {args.sleep}s for the LLM quota window…", flush=True)
        time.sleep(args.sleep)


def render_markdown(
    run: EvalRun, summary: list[dict], results: list[EvalResult], configs: list[str]
) -> str:
    s = run.settings
    attempted = len({r.instance_id for r in results if r.config != "gold"})
    lines = [
        f"# SWE-bench Lite — DevPilot ({run.name})",
        "",
        f"Seeded random sample of **{len(run.instance_ids)}** of the 300 SWE-bench Lite "
        f"test instances (seed {s.get('seed')}); **{attempted} attempted so far**. "
        f"LLM `{run.model}` (Groq free tier), "
        f"embeddings `{s.get('embedding_model')}`. Patches scored with the **official "
        "SWE-bench harness** (`swebench.harness.run_evaluation`): an instance is resolved "
        "only if all FAIL_TO_PASS and PASS_TO_PASS tests pass.",
        "",
        "The agent never sees the benchmark's tests (standard setting): it gets the issue "
        "text, retrieves/plans/edits one file, and the automated reviewer gates the diff.",
        "",
        "| Config | Resolved | Resolve rate (95% CI) | Patch produced | Edited gold file "
        "| Avg LLM calls | Avg tokens | Avg time |",
        "|---|---|---|---|---|---|---|---|",
    ]
    labels = {
        "rag": "**RAG, issue only** (realistic)",
        "oracle-file": "Oracle file, no retrieval",
        "oracle-file+rag": "Oracle file + RAG context",
        "gold": "Reference (gold) patch — environment ceiling",
    }
    for row in summary:
        rate = (
            f"{row['resolve_rate']:.0%} ({row['ci95'][0]:.0%}–{row['ci95'][1]:.0%})"
            if row["resolve_rate"] is not None
            else "not scored"
        )
        lines.append(
            f"| {labels.get(row['config'], row['config'])} | {row['resolved']}/{row['scored']} "
            f"| {rate} | {row['with_patch']}/{row['generated']} | "
            f"{row['localized']}/{row['generated']} | {row['avg_llm_calls']:.1f} | "
            f"{row['avg_tokens']:,.0f} | {row['avg_seconds']:.0f}s |"
        )
    infra = {c["config"]: c["infra_failures"] for c in summary if c["infra_failures"]}
    if infra:
        lines += ["", "Infra failures (harness-classified, counted as unresolved above): "
                  + "; ".join(f"{c}: {', '.join(v)}" for c, v in infra.items())]  # fmt: skip
    lines += ["", "| Instance | " + " | ".join(configs) + " |",
              "|---|" + "---|" * len(configs)]  # fmt: skip
    cell = {True: "✅", False: "❌", None: "·"}
    by = {(r.instance_id, r.config): r for r in results}
    for iid in run.instance_ids:
        cells = []
        for c in configs:
            r = by.get((iid, c))
            cells.append("—" if r is None else f"{cell[r.resolved]} {r.status}")
        lines.append(f"| {iid} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Legend: ✅ resolved · ❌ not resolved · · not scored yet · — not run. "
        "Status is the agent's final state (`validated` = a patch passed review; "
        "`review_failed`/`error` = no patch submitted).",
        "",
    ]
    return "\n".join(lines)


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
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
