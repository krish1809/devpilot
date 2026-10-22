"""SWE-bench report files: ``docs/eval/phase7-<name>.{md,json}``.

Shared by the CLI (``scripts/swebench_eval.py report``) and the unattended
pipeline (``scripts/eval_pipeline.py``), which writes the same files into its
publishing checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evals import swebench as sb
from app.models.eval import EvalResult, EvalRun

CONFIG_LABELS = {
    "rag": "**RAG, issue only** (realistic)",
    "oracle-file": "Oracle file, no retrieval",
    "oracle-file+rag": "Oracle file + RAG context",
    "gold": "Reference (gold) patch — environment ceiling",
}


def get_eval_run(db: Session, name: str) -> EvalRun | None:
    return db.scalar(select(EvalRun).where(EvalRun.name == name))


def load(db: Session, name: str) -> tuple[EvalRun, list[EvalResult], list[str], list[dict]]:
    run = get_eval_run(db, name)
    if run is None:
        raise LookupError(f"No eval run named {name!r}; run `generate` first.")
    results = list(db.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id)).all())
    configs = run.configs + (["gold"] if any(r.config == "gold" for r in results) else [])
    return run, results, configs, sb.summarize(results, configs)


def report_data(run: EvalRun, results: list[EvalResult], summary: list[dict]) -> dict:
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
    return data


def _scoring_sources(results: list[EvalResult]) -> list[str]:
    return sorted(
        {
            (r.score_detail or {}).get("scored_by")
            for r in results
            if (r.score_detail or {}).get("scored_by")
        }
    )


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
    for row in summary:
        rate = (
            f"{row['resolve_rate']:.0%} ({row['ci95'][0]:.0%}–{row['ci95'][1]:.0%})"
            if row["resolve_rate"] is not None
            else "not scored"
        )
        lines.append(
            f"| {CONFIG_LABELS.get(row['config'], row['config'])} | "
            f"{row['resolved']}/{row['scored']} "
            f"| {rate} | {row['with_patch']}/{row['generated']} | "
            f"{row['localized']}/{row['generated']} | {row['avg_llm_calls']:.1f} | "
            f"{row['avg_tokens']:,.0f} | {row['avg_seconds']:.0f}s |"
        )
    infra = {c["config"]: c["infra_failures"] for c in summary if c["infra_failures"]}
    if infra:
        lines += ["", "Infra failures (harness-classified, counted as unresolved above): "
                  + "; ".join(f"{c}: {', '.join(v)}" for c, v in infra.items())]  # fmt: skip
    sources = _scoring_sources(results)
    if sources:
        lines += ["", "Scored by: " + "; ".join(sources) + "."]
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


def write_report(db: Session, name: str, docs_dir: Path) -> tuple[Path, Path]:
    """Write ``phase7-<name>.md`` and ``.json`` into ``docs_dir``; returns both paths."""
    run, results, configs, summary = load(db, name)
    docs_dir.mkdir(parents=True, exist_ok=True)
    stem = docs_dir / f"phase7-{run.name}"
    json_path, md_path = stem.with_suffix(".json"), stem.with_suffix(".md")
    json_path.write_text(json.dumps(report_data(run, results, summary), indent=2, default=str))
    md_path.write_text(render_markdown(run, summary, results, configs))
    return md_path, json_path
