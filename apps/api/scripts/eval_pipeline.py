"""Unattended SWE-bench pipeline: generate locally, score in GitHub Actions, publish.

    python -m scripts.swebench_eval ci-score --name lite-s20-seed7 --with-gold
    python -m scripts.swebench_eval pipeline --name lite-s20-seed7 --n 20 --seed 7 \\
        --owner you@example.com --with-gold

Generating patches needs the local database and the LLM key, and only ~2 GB of
disk. Scoring needs room for each instance's Docker image (up to ~9 GB
unpacked), so it runs in CI (``.github/workflows/swebench-score.yml``).

Everything the pipeline publishes — predictions, reports, the README numbers and
the showcase data — is regenerated from the database into a dedicated clone of
the repository and pushed from there, so the developer's own checkout is never
modified by an automated commit.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = "swebench-score.yml"
README_START = "<!-- swebench:start -->"
README_END = "<!-- swebench:end -->"
SHOWCASE_FILE = "apps/api/showcase/showcase.json"
SERVICE = "devpilot-benchmark.service"

Run = Callable[..., subprocess.CompletedProcess]


class PipelineError(Exception):
    """A step of the pipeline failed; it is safe to retry the pipeline later."""


class PushRejected(PipelineError):
    """The remote branch moved while we were publishing."""


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True, run: Run | None = None):
    proc = (run or subprocess.run)(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        raise PipelineError(f"`{' '.join(cmd[:4])} …` failed: {detail}")
    return proc


def github_repo(remote_url: str) -> str:
    """``owner/name`` from an https or ssh GitHub remote URL."""
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", remote_url.strip())
    if not m:
        raise PipelineError(f"not a GitHub remote: {remote_url!r}")
    return m.group(1)


# --------------------------------------------------------------------------- #
# Publishing from a dedicated clone
# --------------------------------------------------------------------------- #
class Publisher:
    """A clone used only to publish generated files to ``branch``."""

    def __init__(
        self,
        path: Path,
        remote: str,
        *,
        branch: str = "main",
        identity: tuple[str, str] | None = None,
        run: Run | None = None,
    ) -> None:
        self.path, self.remote, self.branch = path, remote, branch
        self.identity = identity
        self._runner = run

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return _run(["git", *args], cwd=self.path, check=check, run=self._runner)

    def sync(self) -> Path:
        """A clean checkout of the remote branch's latest commit."""
        if not (self.path / ".git").exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _run(
                ["git", "clone", "--quiet", "--branch", self.branch, self.remote, str(self.path)],
                run=self._runner,
            )
            if self.identity:
                self._git("config", "user.name", self.identity[0])
                self._git("config", "user.email", self.identity[1])
        self._git("fetch", "--quiet", "origin", self.branch)
        self._git("reset", "--quiet", "--hard", f"origin/{self.branch}")
        self._git("clean", "-fdq")
        return self.path

    def commit_and_push(self, paths: list[str], message: str) -> bool:
        """Commit ``paths`` if they changed and push; False when nothing changed."""
        self._git("add", "--", *paths)
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return False
        self._git("commit", "--quiet", "-m", message)
        push = self._git("push", "--quiet", "origin", f"HEAD:{self.branch}", check=False)
        if push.returncode != 0:
            raise PushRejected((push.stderr or "").strip()[:400])
        return True

    def publish(self, write: Callable[[Path], list[str]], message: str, attempts: int = 3) -> bool:
        """Regenerate files into a fresh checkout, commit and push; retry if main moved."""
        for attempt in range(1, attempts + 1):
            root = self.sync()
            try:
                return self.commit_and_push(write(root), message)
            except PushRejected:
                if attempt == attempts:
                    raise
        return False


def default_publisher(cache: Path) -> Publisher:
    remote = _run(["git", "remote", "get-url", "origin"], cwd=REPO_ROOT).stdout.strip()
    name = _run(["git", "config", "user.name"], cwd=REPO_ROOT, check=False).stdout.strip()
    email = _run(["git", "config", "user.email"], cwd=REPO_ROOT, check=False).stdout.strip()
    return Publisher(cache / "publish-repo", remote, identity=(name, email) if name else None)


# --------------------------------------------------------------------------- #
# GitHub Actions (via the authenticated `gh` CLI)
# --------------------------------------------------------------------------- #
class Actions:
    def __init__(
        self,
        repo: str,
        *,
        workflow: str = WORKFLOW,
        run: Run | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo, self.workflow = repo, workflow
        self._runner = run
        self._sleep = sleep or time.sleep
        self._clock = clock or (lambda: datetime.now(UTC))

    def _gh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return _run(["gh", *args, "--repo", self.repo], check=check, run=self._runner)

    def run_url(self, run_id: int) -> str:
        return f"https://github.com/{self.repo}/actions/runs/{run_id}"

    def dispatch(self, inputs: dict[str, str], *, ref: str = "main", polls: int = 18) -> int:
        """Start the workflow and return the id of the run it created."""
        started = self._clock()
        fields = [arg for k, v in inputs.items() for arg in ("-f", f"{k}={v}")]
        self._gh("workflow", "run", self.workflow, "--ref", ref, *fields)
        for _ in range(polls):
            self._sleep(10)
            listed = self._gh(
                "run", "list", "--workflow", self.workflow, "--event", "workflow_dispatch",
                "--json", "databaseId,createdAt", "--limit", "10",
            ).stdout  # fmt: skip
            fresh = [
                r
                for r in json.loads(listed or "[]")
                if datetime.fromisoformat(r["createdAt"]) >= started - timedelta(seconds=60)
            ]
            if fresh:
                return max(fresh, key=lambda r: r["createdAt"])["databaseId"]
        raise PipelineError("the dispatched workflow run never appeared")

    def wait(self, run_id: int, *, interval: float = 60, polls: int = 480) -> str:
        """Block until the run completes (up to ~8 h); returns its conclusion."""
        for _ in range(polls):
            view = self._gh("run", "view", str(run_id), "--json", "status,conclusion")
            info = json.loads(view.stdout)
            if info.get("status") == "completed":
                return info.get("conclusion") or "unknown"
            self._sleep(interval)
        raise PipelineError(f"workflow run {run_id} did not finish")

    def download_scores(self, run_id: int) -> dict | None:
        """The merged verdicts artifact, or None if the run produced none."""
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._gh(
                "run", "download", str(run_id), "-n", "swebench-scores", "-D", tmp, check=False
            )
            path = Path(tmp) / "swebench-scores.json"
            if proc.returncode != 0 or not path.exists():
                return None
            return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# README numbers
# --------------------------------------------------------------------------- #
_PROJECTS = {
    "django": "Django", "sympy": "SymPy", "scikit-learn": "scikit-learn", "sphinx-doc": "Sphinx",
    "matplotlib": "Matplotlib", "pylint-dev": "Pylint", "astropy": "Astropy",
    "pytest-dev": "pytest", "psf": "Requests", "mwaskom": "seaborn", "pydata": "xarray",
    "pallets": "Flask",
}  # fmt: skip


def _projects(instance_ids: list[str]) -> str:
    names: list[str] = []
    for iid in instance_ids:
        org = iid.split("__")[0]
        name = _PROJECTS.get(org, org)
        if name not in names:
            names.append(name)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def is_complete(report: dict) -> bool:
    """Every sampled instance attempted, and every generated result scored."""
    attempted = {r["instance_id"] for r in report["results"] if r["config"] != "gold"}
    rows = [row for row in report["summary"] if row["generated"]]
    return (
        len(attempted) == len(report["instances"])
        and bool(rows)
        and all(row["scored"] == row["generated"] for row in rows)
    )


def render_readme_block(
    report: dict, *, labels: dict[str, str], links: list[tuple[str, str]]
) -> str:
    """The README's SWE-bench section, between the swebench markers."""
    n = len(report["instances"])
    attempted = len({r["instance_id"] for r in report["results"] if r["config"] != "gold"})
    lines = [
        README_START,
        f"**SWE-bench Lite** ([method](docs/eval/README.md)) — a seeded random sample of {n} "
        f"real issues from {_projects(report['instances'])}, run with a free-tier open-weight "
        f"model (`{report['model']}` on Groq) and scored by the official SWE-bench harness. "
        "The agent sees only the issue text; the benchmark's tests stay hidden.",
        "",
    ]
    if is_complete(report):
        lines += ["| Config | Resolved | Resolve rate (95% CI) |", "|---|---|---|"]
        for row in report["summary"]:
            if not row["generated"]:
                continue
            lo, hi = row["ci95"]
            lines.append(
                f"| {labels.get(row['config'], row['config'])} | "
                f"{row['resolved']}/{row['scored']} | "
                f"{row['resolve_rate']:.0%} ({lo:.0%}–{hi:.0%}) |"
            )
        lines.append("")
    else:
        lines += [
            f"**In progress:** {attempted}/{n} instances attempted so far. The run is paced by "
            "the free tier's daily token quota, and the numbers are published here once every "
            "patch has been scored.",
            "",
        ]
    lines += [
        " · ".join(f"[{text}]({href})" for text, href in links),
        "",
        "Read it as a capability demonstration with wide confidence intervals, not a "
        "leaderboard claim.",
        README_END,
    ]
    return "\n".join(lines)


def update_readme(readme: Path, block: str) -> bool:
    """Replace the marked section; False if it was already up to date."""
    text = readme.read_text()
    start, end = text.find(README_START), text.find(README_END)
    if start == -1 or end == -1 or end < start:
        raise PipelineError(f"{readme} has no {README_START} … {README_END} section")
    updated = text[:start] + block + text[end + len(README_END) :]
    if updated == text:
        return False
    readme.write_text(updated)
    return True


def disable_service(run: Run | None = None) -> None:
    """Best effort: stop the systemd user unit from starting again at login."""
    _run(["systemctl", "--user", "disable", SERVICE], check=False, run=run)


# --------------------------------------------------------------------------- #
# Orchestration (needs the database)
# --------------------------------------------------------------------------- #
def predictions_path(name: str) -> str:
    return f"docs/eval/predictions/{name}.jsonl"


def _eval_run(db, name: str):  # noqa: ANN001, ANN202
    from app.evals import report

    run = report.get_eval_run(db, name)
    if run is None:
        raise PipelineError(f"No eval run named {name!r}; run `generate` first.")
    return run


def _counts(db, name: str) -> tuple[int, int, int]:  # noqa: ANN001
    """(instances attempted, instances sampled, results still unscored)."""
    from sqlalchemy import select

    from app.models.eval import EvalResult

    run = _eval_run(db, name)
    rows = db.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id)).all()
    attempted = len({r.instance_id for r in rows if r.config != "gold"})
    return attempted, len(run.instance_ids), sum(1 for r in rows if r.resolved is None)


def _write_report(db, name: str, root: Path) -> list[str]:  # noqa: ANN001
    from app.evals import report

    md, js = report.write_report(db, name, root / "docs" / "eval")
    return [str(md.relative_to(root)), str(js.relative_to(root))]


def ci_score(
    name: str,
    *,
    with_gold: bool,
    publisher: Publisher,
    actions: Actions,
    session_factory: Callable,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> int:
    """Score every patch of eval run ``name`` in GitHub Actions.

    Returns how many results are still unscored (0 = done). Re-scores results
    already scored locally too, so every reported verdict comes from the same
    CI environment.
    """
    from app.evals import swebench as sb

    with session_factory() as db:
        run = _eval_run(db, name)
        if with_gold:
            sb.queue_gold_for_attempted(db, run)
        sb.mark_patchless(db, run)
        preds = sb.export_predictions(db, run)
        pending = _counts(db, name)[2]
    if not preds or (pending == 0 and not force):
        log(f"{name}: nothing to score in CI.")
        return pending

    rel = predictions_path(name)

    def write(root: Path) -> list[str]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(p, sort_keys=True) + "\n" for p in preds))
        return [rel]

    publisher.publish(write, f"eval: predictions for {name} — {len(preds)} patches [automated]")
    run_id = actions.dispatch({"predictions": rel})
    url = actions.run_url(run_id)
    log(f"Scoring {len(preds)} predictions in GitHub Actions: {url}")
    conclusion = actions.wait(run_id)
    scores = actions.download_scores(run_id)
    if scores is None:
        log(f"The scoring run ended '{conclusion}' without a verdicts artifact; will retry.")
        return pending
    with session_factory() as db:
        counts = sb.import_scores(db, _eval_run(db, name), scores, source=f"GitHub Actions {url}")
    log(f"Imported CI verdicts (run {conclusion}): {counts}")
    return counts["pending"]


def readme_links(name: str, *, ablation: str | None, complete: bool) -> list[tuple[str, str]]:
    report_md = f"docs/eval/phase7-{name}.md"
    links = (
        [("Full report", report_md), ("the exact patches scored", predictions_path(name))]
        if complete
        else [("Current partial report", report_md)]
    )
    if ablation:
        links.append(("earlier agent version", f"docs/eval/phase7-{ablation}.md"))
    return links


def _write_readme(root: Path, report_json: Path, *, name: str, ablation: str | None) -> dict:
    from app.evals import report

    data = json.loads(report_json.read_text())
    links = readme_links(name, ablation=ablation, complete=is_complete(data))
    update_readme(
        root / "README.md", render_readme_block(data, labels=report.CONFIG_LABELS, links=links)
    )
    return data


def publish_progress(
    name: str, *, publisher: Publisher, session_factory: Callable, ablation: str | None = None
) -> bool:
    """The partial report and the README's in-progress line."""
    with session_factory() as db:
        attempted, n, _ = _counts(db, name)

    def write(root: Path) -> list[str]:
        with session_factory() as db:
            paths = _write_report(db, name, root)
        _write_readme(root, root / paths[1], name=name, ablation=ablation)
        return [*paths, "README.md"]

    return publisher.publish(
        write, f"eval: {name} progress — {attempted}/{n} instances attempted [automated]"
    )


def publish_final(
    name: str,
    *,
    publisher: Publisher,
    session_factory: Callable,
    showcase_tasks: list[int],
    showcase_evals: list[str],
    ablation: str | None,
) -> bool:
    """The final report, the README numbers and the showcase data, in one commit."""
    from scripts import showcase

    headline = ""

    def write(root: Path) -> list[str]:
        nonlocal headline
        with session_factory() as db:
            paths = _write_report(db, name, root)
            exported = showcase.export(db, showcase_tasks, showcase_evals)
        data = _write_readme(root, root / paths[1], name=name, ablation=ablation)
        target = root / SHOWCASE_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(exported, indent=1, default=str))
        rag = next((r for r in data["summary"] if r["config"] == "rag"), None)
        if rag and rag["scored"]:
            headline = f" — RAG {rag['resolved']}/{rag['scored']} resolved"
        return [*paths, "README.md", SHOWCASE_FILE]

    # The commit message needs the headline, which is only known after writing.
    root = publisher.sync()
    changed = write(root)
    message = f"eval: {name} complete{headline} [automated]"
    try:
        return publisher.commit_and_push(changed, message)
    except PushRejected:
        return publisher.publish(write, message)


def run_pipeline(
    *,
    name: str,
    generate: Callable[[], bool],
    with_gold: bool,
    publisher: Publisher,
    actions: Actions,
    session_factory: Callable,
    showcase_tasks: list[int],
    showcase_evals: list[str],
    ablation: str | None,
    marker: Path,
    sleep_seconds: int,
    ci_attempts: int = 5,
    sleep: Callable[[float], None] | None = None,
    log: Callable[[str], None] = print,
) -> None:
    """generate (until done) → score in CI (until done) → publish → mark complete."""
    sleep = sleep or time.sleep
    if marker.exists():
        log(f"{name}: already complete ({marker}); nothing to do.")
        return

    while True:  # 1. every patch, paced by the LLM quota and the disk guard
        done = generate()
        if publish_progress(
            name, publisher=publisher, session_factory=session_factory, ablation=ablation
        ):
            log("Published the progress report.")
        if done:
            break
        log(f"Waiting {sleep_seconds}s before the next pass (LLM quota window / disk space)…")
        sleep(sleep_seconds)

    for attempt in range(1, ci_attempts + 1):  # 2. a verdict for every patch
        pending = ci_score(
            name,
            with_gold=with_gold,
            publisher=publisher,
            actions=actions,
            session_factory=session_factory,
            log=log,
        )
        if pending == 0:
            break
        log(f"CI attempt {attempt}/{ci_attempts}: {pending} unscored; retrying in {sleep_seconds}s")
        sleep(sleep_seconds)
    else:
        raise PipelineError(f"{name}: results still unscored after {ci_attempts} CI attempts")

    publish_final(  # 3. report, README numbers, showcase data
        name,
        publisher=publisher,
        session_factory=session_factory,
        showcase_tasks=showcase_tasks,
        showcase_evals=showcase_evals,
        ablation=ablation,
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now(UTC).isoformat())
    disable_service()
    log(f"{name}: complete — results published.")
