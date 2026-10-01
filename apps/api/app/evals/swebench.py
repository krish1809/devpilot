"""SWE-bench Lite harness.

Two steps, both resumable:

1. ``generate`` — for each sampled instance, check out the repo at its base
   commit and run the DevPilot agent under each config. The agent sees only the
   issue text (the benchmark's tests stay hidden), so runs carry no test
   command. The resulting diff is the prediction.
2. ``score`` — feed each prediction to the **official** SWE-bench harness
   (``swebench.harness.run_evaluation``, installed in its own virtualenv), which
   applies the patch inside the instance's Docker image and runs the hidden
   FAIL_TO_PASS / PASS_TO_PASS tests. Images are removed after each instance
   to keep disk bounded.

Configs:
- ``rag``          — realistic: issue only; RAG retrieves context and the
                     planner localizes the file. The headline number.
- ``oracle-file``  — the file the gold patch edits is given (oracle
                     localization), no retrieval: isolates patch writing.
- ``oracle-file+rag`` — oracle file plus retrieved cross-file context.
- ``gold``         — (score only) the benchmark's reference patch, to calibrate
                     the environment: the best score achievable on this machine.

Infra failures (the harness's own classification, e.g. tests needing network
the environment can't reach) are recorded per result and reported separately.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents import runner
from app.agents.graph import AgentDeps
from app.core.config import Settings, get_settings
from app.integrations import git_ops
from app.integrations.github_pr import PublishError
from app.models.eval import EvalResult, EvalRun
from app.models.rag import RepoIndex
from app.services import agent as agent_service

DATASET = "SWE-bench/SWE-bench_Lite"
_ROWS_API = "https://datasets-server.huggingface.co/rows"
_HF_DATASET = "princeton-nlp/SWE-bench_Lite"
CACHE = Path.home() / ".cache" / "devpilot" / "swebench"
API_ROOT = Path(__file__).resolve().parents[2]  # apps/api
SWEBENCH_PY = API_ROOT / ".venv-swebench" / "bin" / "python"

CONFIGS = {
    "rag": {"use_rag": True, "oracle_file": False},
    "oracle-file": {"use_rag": False, "oracle_file": True},
    "oracle-file+rag": {"use_rag": True, "oracle_file": True},
}

# Prompt/budget overrides so every request fits Groq's free tier (8k tokens/min).
EVAL_SETTINGS = {
    "agent_max_attempts": 2,  # no tests in the loop: retries only re-try failed edits
    "agent_whole_file_chars": 6_000,
    "agent_excerpt_chars": 5_000,
    "agent_issue_chars": 4_000,
    "rag_context_chars": 5_000,
    "rag_candidate_files": 8,
    "rag_max_files": 4_000,
    "rag_max_chunks": 12_000,
    "agent_run_timeout_seconds": 1_800,
}


class QuotaExhausted(Exception):
    """The LLM provider's daily quota is used up; resume later."""


@dataclass
class Instance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str

    @property
    def gold_path(self) -> str | None:
        files = sorted(git_ops.changed_files(self.patch))
        return files[0] if files else None


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
def load_dataset(refresh: bool = False) -> list[Instance]:
    """All SWE-bench Lite test instances (cached as JSON)."""
    cache = CACHE / "swe-bench-lite-test.json"
    if refresh or not cache.exists():
        rows, offset = [], 0
        while True:
            resp = httpx.get(
                _ROWS_API,
                params={"dataset": _HF_DATASET, "config": "default", "split": "test",
                        "offset": offset, "length": 100},
                timeout=60,
            )  # fmt: skip
            resp.raise_for_status()
            data = resp.json()
            rows += [r["row"] for r in data["rows"]]
            offset += 100
            if offset >= data["num_rows_total"]:
                break
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows))
    keep = ("instance_id", "repo", "base_commit", "problem_statement", "patch")
    return [Instance(**{k: r[k] for k in keep}) for r in json.loads(cache.read_text())]


def sample(instances: list[Instance], n: int, seed: int) -> list[Instance]:
    """A seeded random sample (stable across runs), returned in id order."""
    picked = random.Random(seed).sample(sorted(instances, key=lambda i: i.instance_id), n)
    return sorted(picked, key=lambda i: i.instance_id)


def prepare_checkout(inst: Instance) -> Path:
    """A local repo containing just the base commit (shallow fetch), cached."""
    repo = CACHE / "repos" / inst.instance_id
    if (repo / ".git").exists():
        return repo
    repo.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{inst.repo}.git"
    git_ops._run(["git", "init", "-q"], cwd=repo)
    git_ops._run(["git", "fetch", "-q", "--depth", "1", url, inst.base_commit], cwd=repo)
    git_ops._run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=repo)
    return repo


# --------------------------------------------------------------------------- #
# Generate
# --------------------------------------------------------------------------- #
def eval_settings(base: Settings | None = None) -> Settings:
    return (base or get_settings()).model_copy(update=EVAL_SETTINGS)


def make_deps(session_factory: Callable[[], Session], settings: Settings) -> AgentDeps:
    def refuse_publish(*args, **kwargs):  # noqa: ANN002, ANN003
        raise PublishError("benchmark runs never publish")

    return AgentDeps(
        session_factory=session_factory,
        checkpointer=InMemorySaver(),
        publisher=refuse_publish,
        settings=settings,
    )


def get_or_create_run(
    db: Session, name: str, instances: list[Instance], configs: list[str], settings: dict
) -> EvalRun:
    run = db.scalar(select(EvalRun).where(EvalRun.name == name))
    if run:
        return run
    run = EvalRun(
        name=name,
        dataset=DATASET,
        split="test",
        instance_ids=[i.instance_id for i in instances],
        configs=configs,
        model=get_settings().llm_model,
        settings=settings,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _existing(db: Session, eval_run_id: int) -> set[tuple[str, str]]:
    rows = db.execute(
        select(EvalResult.instance_id, EvalResult.config).where(
            EvalResult.eval_run_id == eval_run_id
        )
    )
    return {(i, c) for i, c in rows}


def generate(
    db: Session,
    deps: AgentDeps,
    eval_run: EvalRun,
    instances: Iterable[Instance],
    owner_id: int,
    *,
    keep_index: bool = False,
    log: Callable[[str], None] = print,
) -> None:
    """Run the agent for every (instance, config) without a stored result."""
    done = _existing(db, eval_run.id)
    for inst in instances:
        todo = [c for c in eval_run.configs if (inst.instance_id, c) not in done]
        if not todo:
            continue
        repo = prepare_checkout(inst)
        for config in todo:
            opts = CONFIGS[config]
            task = agent_service.create_task(
                db,
                owner_id,
                repo_url=str(repo),
                base_commit=inst.base_commit,
                test_command=None,
                target_path=inst.gold_path if opts["oracle_file"] else None,
                description=inst.problem_statement,
            )
            started = time.monotonic()
            run = runner.run_to_completion(db, task, deps, use_rag=opts["use_rag"])
            error = run.error or ""
            if "daily rate limit" in error.lower() or "per day" in error.lower():
                raise QuotaExhausted(error)
            db.add(
                EvalResult(
                    eval_run_id=eval_run.id,
                    instance_id=inst.instance_id,
                    repo=inst.repo,
                    config=config,
                    agent_run_id=run.id,
                    status=run.status,
                    patch=run.diff if run.status == "validated" else None,
                    target_path=run.target_path,
                    gold_path=inst.gold_path,
                    localized=(run.target_path == inst.gold_path) if run.target_path else False,
                    error=run.error,
                    llm_calls=run.llm_calls,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    seconds=round(time.monotonic() - started, 1),
                )
            )
            db.commit()
            log(f"{inst.instance_id} [{config}] {run.status} file={run.target_path} "
                f"tokens={run.prompt_tokens + run.completion_tokens}")  # fmt: skip
        if not keep_index:  # indexes are large; drop this commit's index
            db.execute(delete(RepoIndex).where(RepoIndex.repo_url == str(repo)))
            db.commit()
        shutil.rmtree(repo, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Score (official harness)
# --------------------------------------------------------------------------- #
def add_gold(db: Session, eval_run: EvalRun, instances: list[Instance]) -> None:
    """Queue the reference patches as a ``gold`` config for calibration scoring."""
    done = _existing(db, eval_run.id)
    for inst in instances:
        if (inst.instance_id, "gold") in done:
            continue
        db.add(
            EvalResult(
                eval_run_id=eval_run.id, instance_id=inst.instance_id, repo=inst.repo,
                config="gold", status="reference", patch=inst.patch,
                target_path=inst.gold_path, gold_path=inst.gold_path, localized=True,
            )
        )  # fmt: skip
    db.commit()


def _harness_run_id(eval_run: EvalRun, config: str) -> str:
    return f"devpilot-{eval_run.id}-{config.replace('+', '-')}"


def score(
    db: Session,
    eval_run: EvalRun,
    *,
    workdir: Path,
    remove_images: bool = True,
    timeout: int = 1800,
    log: Callable[[str], None] = print,
) -> None:
    """Score every generated-but-unscored result with the official harness."""
    if not SWEBENCH_PY.exists():
        raise SystemExit(
            f"Official harness not installed: create {SWEBENCH_PY.parent.parent} and "
            "`pip install swebench` into it (see docs/eval/README.md)."
        )
    workdir.mkdir(parents=True, exist_ok=True)
    pending = db.scalars(
        select(EvalResult)
        .where(EvalResult.eval_run_id == eval_run.id, EvalResult.resolved.is_(None))
        .order_by(EvalResult.instance_id, EvalResult.config)
    ).all()
    by_instance: dict[str, list[EvalResult]] = {}
    for r in pending:
        by_instance.setdefault(r.instance_id, []).append(r)

    for instance_id, results in by_instance.items():
        for r in results:
            if not r.patch:  # nothing to apply: unresolved by definition
                r.resolved, r.score_detail = False, {"reason": "no patch"}
                r.scored_at = datetime.now(UTC)
                db.commit()
                continue
            model = f"devpilot-{r.config}"
            run_id = _harness_run_id(eval_run, r.config)
            preds = workdir / f"{run_id}.{instance_id}.jsonl"
            preds.write_text(json.dumps(
                {"instance_id": instance_id, "model_name_or_path": model, "model_patch": r.patch}
            ) + "\n")  # fmt: skip
            proc = subprocess.run(
                [str(SWEBENCH_PY), "-m", "swebench.harness.run_evaluation",
                 "-d", DATASET, "-s", "test", "-i", instance_id, "-p", str(preds),
                 "--max_workers", "1", "-t", str(timeout), "-id", run_id,
                 "--report_dir", str(workdir)],
                cwd=workdir, capture_output=True, text=True, timeout=timeout + 1200,
            )  # fmt: skip
            report = workdir / "logs" / "run_evaluation" / run_id / model / instance_id
            report = report / "report.json"
            run_report = workdir / f"{model}.{run_id}.json"
            reasons = {}
            if run_report.exists():
                reasons = json.loads(run_report.read_text()).get("failure_reasons") or {}
            if report.exists():
                detail = json.loads(report.read_text()).get(instance_id, {})
                r.resolved = bool(detail.get("resolved"))
                r.score_detail = {
                    "patch_applied": detail.get("patch_successfully_applied"),
                    "tests_status": _summarize_tests(detail.get("tests_status") or {}),
                    "infra_failure": reasons.get(instance_id),
                }
            else:  # harness error (e.g. patch failed to apply): unresolved
                r.resolved = False
                r.score_detail = {"reason": "no report", "stderr": proc.stderr[-1500:]}
            r.scored_at = datetime.now(UTC)
            db.commit()
            log(f"{instance_id} [{r.config}] resolved={r.resolved}")
        if remove_images:
            _remove_instance_images(instance_id)


def _summarize_tests(status: dict) -> dict:
    return {
        group: {k: len(v) for k, v in (outcome or {}).items()} for group, outcome in status.items()
    }


def _remove_instance_images(instance_id: str) -> None:
    name = instance_id.replace("__", "_1776_").lower()
    out = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True, text=True,
    ).stdout  # fmt: skip
    for image in out.split():
        if name in image:
            subprocess.run(["docker", "rmi", "-f", image], capture_output=True)
    subprocess.run(["docker", "image", "prune", "-f"], capture_output=True)


# --------------------------------------------------------------------------- #
# Summaries
# --------------------------------------------------------------------------- #
def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(results: list[EvalResult], configs: list[str]) -> list[dict]:
    out = []
    for config in configs:
        rows = [r for r in results if r.config == config]
        scored = [r for r in rows if r.resolved is not None]
        resolved = sum(1 for r in scored if r.resolved)
        infra = [
            r.instance_id
            for r in scored
            if not r.resolved and (r.score_detail or {}).get("infra_failure")
        ]
        lo, hi = wilson_interval(resolved, len(scored))
        n = len(rows) or 1
        out.append(
            {
                "config": config,
                "generated": len(rows),
                "scored": len(scored),
                "resolved": resolved,
                "resolve_rate": resolved / len(scored) if scored else None,
                "ci95": [lo, hi] if scored else None,
                "infra_failures": infra,
                "with_patch": sum(1 for r in rows if r.patch),
                "localized": sum(1 for r in rows if r.localized),
                "avg_tokens": sum(r.prompt_tokens + r.completion_tokens for r in rows) / n,
                "avg_llm_calls": sum(r.llm_calls for r in rows) / n,
                "avg_seconds": sum(r.seconds for r in rows) / n,
            }
        )
    return out
