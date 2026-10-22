"""Unattended SWE-bench pipeline (scripts/eval_pipeline.py): real git against a local
bare repository, a scripted `gh`, and the real test database."""

import json
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.evals import report
from app.evals import swebench as sb
from app.models.eval import EvalResult
from scripts import eval_pipeline as pipe

PATCH = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout  # fmt: skip


@pytest.fixture()
def remote(tmp_path: Path) -> Path:
    """A bare 'GitHub' repository with one commit on main."""
    bare = tmp_path / "remote.git"
    _git("init", "--quiet", "--bare", "--initial-branch=main", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", "--quiet", str(bare), str(seed), cwd=tmp_path)
    (seed / "README.md").write_text(
        f"# Demo\n\n{pipe.README_START}\nold numbers\n{pipe.README_END}\n\nMore.\n"
    )
    _git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A", cwd=seed)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init", cwd=seed)
    _git("push", "--quiet", "origin", "HEAD:main", cwd=seed)
    return bare


def _publisher(tmp_path: Path, remote: Path) -> pipe.Publisher:
    return pipe.Publisher(tmp_path / "publish", str(remote), identity=("bot", "bot@example.com"))


def _remote_log(remote: Path) -> list[str]:
    return _git("log", "--format=%s", "main", cwd=remote).splitlines()


# --------------------------------------------------------------------------- #
# Publishing from a dedicated clone
# --------------------------------------------------------------------------- #
def test_github_repo_parses_remote_urls() -> None:
    assert pipe.github_repo("https://github.com/krish1809/devpilot.git") == "krish1809/devpilot"
    assert pipe.github_repo("git@github.com:krish1809/devpilot") == "krish1809/devpilot"
    with pytest.raises(pipe.PipelineError):
        pipe.github_repo("https://gitlab.com/a/b.git")


def test_publisher_commits_only_when_something_changed(tmp_path: Path, remote: Path) -> None:
    publisher = _publisher(tmp_path, remote)

    def write(root: Path) -> list[str]:
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "report.md").write_text("42\n")
        return ["docs/report.md"]

    assert publisher.publish(write, "eval: report [automated]") is True
    assert publisher.publish(write, "eval: report [automated]") is False  # same content
    assert _remote_log(remote) == ["eval: report [automated]", "init"]
    author = _git("log", "-1", "--format=%an <%ae>", "main", cwd=remote).strip()
    assert author == "bot <bot@example.com>"


def test_publisher_retries_when_main_moves_underneath(tmp_path: Path, remote: Path) -> None:
    publisher = _publisher(tmp_path, remote)
    other = tmp_path / "someone-else"
    _git("clone", "--quiet", str(remote), str(other), cwd=tmp_path)
    calls = {"n": 0}

    def write(root: Path) -> list[str]:
        calls["n"] += 1
        if calls["n"] == 1:  # a human pushes between our sync and our push
            (other / "human.txt").write_text("hi\n")
            _git("-c", "user.name=h", "-c", "user.email=h@h", "add", "-A", cwd=other)
            _git("-c", "user.name=h", "-c", "user.email=h@h", "commit", "-qm", "human", cwd=other)
            _git("push", "--quiet", "origin", "HEAD:main", cwd=other)
        (root / "report.md").write_text("numbers\n")
        return ["report.md"]

    assert publisher.publish(write, "eval: numbers [automated]") is True
    assert calls["n"] == 2  # regenerated on top of the new main
    assert _remote_log(remote) == ["eval: numbers [automated]", "human", "init"]


# --------------------------------------------------------------------------- #
# GitHub Actions via a scripted `gh`
# --------------------------------------------------------------------------- #
class FakeGh:
    def __init__(self, started: datetime, views: list[dict], artifact: dict | None) -> None:
        self.started, self.views, self.artifact = started, list(views), artifact
        self.calls: list[list[str]] = []

    def __call__(self, cmd, cwd=None, **kwargs):  # noqa: ANN001, ANN003, ANN204
        self.calls.append(cmd)
        sub = cmd[1:3]
        out = ""
        if sub == ["run", "list"]:
            out = json.dumps([
                {"databaseId": 1, "createdAt": "2020-01-01T00:00:00Z"},  # an old run
                {"databaseId": 99, "createdAt": self.started.isoformat()},
            ])  # fmt: skip
        elif sub == ["run", "view"]:
            out = json.dumps(self.views.pop(0))
        elif sub == ["run", "download"] and self.artifact is not None:
            dest = Path(cmd[cmd.index("-D") + 1])
            (dest / "swebench-scores.json").write_text(json.dumps(self.artifact))
        return subprocess.CompletedProcess(cmd, 0, out, "")


def _actions(gh: FakeGh) -> pipe.Actions:
    return pipe.Actions("me/repo", run=gh, sleep=lambda s: None, clock=lambda: gh.started)


def test_actions_dispatch_waits_and_downloads() -> None:
    started = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    gh = FakeGh(started, [{"status": "in_progress"}, {"status": "completed",
                "conclusion": "success"}], {"results": []})  # fmt: skip
    actions = _actions(gh)

    run_id = actions.dispatch({"predictions": "docs/eval/predictions/x.jsonl"})

    assert run_id == 99  # the run created after we dispatched, not the old one
    dispatch = gh.calls[0]
    assert dispatch[:4] == ["gh", "workflow", "run", pipe.WORKFLOW]
    assert "predictions=docs/eval/predictions/x.jsonl" in dispatch
    assert dispatch[-2:] == ["--repo", "me/repo"]
    assert actions.wait(run_id) == "success"
    assert actions.download_scores(run_id) == {"results": []}
    assert actions.run_url(99) == "https://github.com/me/repo/actions/runs/99"


def test_actions_download_without_artifact_returns_none() -> None:
    gh = FakeGh(datetime.now(UTC), [], None)
    assert _actions(gh).download_scores(5) is None


# --------------------------------------------------------------------------- #
# README numbers
# --------------------------------------------------------------------------- #
def _report(attempted: int, scored: bool) -> dict:
    instances = ["django__django-1", "sympy__sympy-2"]
    results = [
        {"instance_id": iid, "config": c} for iid in instances[:attempted] for c in ("rag", "gold")
    ]
    rows = [
        {"config": "rag", "generated": attempted, "scored": attempted if scored else 0,
         "resolved": 1 if scored else 0, "resolve_rate": 0.5 if scored else None,
         "ci95": [0.09, 0.91] if scored else None},
        {"config": "oracle-file", "generated": 0, "scored": 0, "resolved": 0,
         "resolve_rate": None, "ci95": None},
    ]  # fmt: skip
    return {"instances": instances, "model": "m", "results": results, "summary": rows}


LINKS = [("Full report", "docs/eval/phase7-x.md")]


def test_readme_block_shows_numbers_only_when_complete() -> None:
    done = pipe.render_readme_block(_report(2, True), labels=report.CONFIG_LABELS, links=LINKS)
    assert "| **RAG, issue only** (realistic) | 1/2 | 50% (9%–91%) |" in done
    assert "Oracle file" not in done  # configs that never ran are left out
    assert "Django and SymPy" in done
    assert done.startswith(pipe.README_START) and done.endswith(pipe.README_END)

    partial = pipe.render_readme_block(_report(1, False), labels=report.CONFIG_LABELS, links=LINKS)
    assert "**In progress:** 1/2 instances attempted" in partial
    assert "| Config |" not in partial
    assert "[Full report](docs/eval/phase7-x.md)" in partial


def test_update_readme_replaces_only_the_marked_section(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n{pipe.README_START}\nold\n{pipe.README_END}\noutro\n")
    block = f"{pipe.README_START}\nnew\n{pipe.README_END}"

    assert pipe.update_readme(readme, block) is True
    assert readme.read_text() == f"intro\n{block}\noutro\n"
    assert pipe.update_readme(readme, block) is False
    readme.write_text("no markers\n")
    with pytest.raises(pipe.PipelineError):
        pipe.update_readme(readme, block)


# --------------------------------------------------------------------------- #
# CI scoring hand-off (real test DB, fake publisher + Actions)
# --------------------------------------------------------------------------- #
def _session_factory(db: Session):  # noqa: ANN202
    @contextmanager
    def factory():  # noqa: ANN202
        yield db

    return factory


class FakePublisher:
    def __init__(self, root: Path) -> None:
        self.root, self.messages = root, []

    def publish(self, write, message: str) -> bool:  # noqa: ANN001
        self.messages.append(message)
        write(self.root)
        return True


class FakeActions:
    def __init__(self, scores: dict | None) -> None:
        self.scores, self.dispatched = scores, []

    def dispatch(self, inputs: dict) -> int:
        self.dispatched.append(inputs)
        return 7

    def run_url(self, run_id: int) -> str:
        return f"https://ci/{run_id}"

    def wait(self, run_id: int) -> str:
        return "success"

    def download_scores(self, run_id: int) -> dict | None:
        return self.scores


def _eval_run(db_session: Session, name: str) -> object:
    run = sb.get_or_create_run(db_session, name, [], ["rag"], {})
    db_session.add_all([
        EvalResult(eval_run_id=run.id, instance_id="a__a-1", repo="x/y", config="rag",
                   status="validated", patch=PATCH),
        EvalResult(eval_run_id=run.id, instance_id="b__b-2", repo="x/y", config="rag",
                   status="review_failed", patch=None),
    ])  # fmt: skip
    db_session.commit()
    return run


def test_ci_score_publishes_predictions_and_imports_verdicts(
    tmp_path: Path, db_session: Session
) -> None:
    _eval_run(db_session, "pipe")
    verdict = {"instance_id": "a__a-1", "config": "rag", "resolved": True,
               "score_detail": {"infra_failure": None}}  # fmt: skip
    publisher, actions = FakePublisher(tmp_path), FakeActions({"results": [verdict]})

    pending = pipe.ci_score(
        "pipe",
        with_gold=False,
        publisher=publisher,
        actions=actions,
        session_factory=_session_factory(db_session),
        log=lambda m: None,
    )

    assert pending == 0
    preds = (tmp_path / pipe.predictions_path("pipe")).read_text().splitlines()
    assert [json.loads(p)["instance_id"] for p in preds] == ["a__a-1"]  # patch-less row skipped
    assert actions.dispatched == [{"predictions": "docs/eval/predictions/pipe.jsonl"}]
    db_session.expire_all()
    rows = {r.instance_id: r for r in db_session.query(EvalResult).all()}
    assert rows["a__a-1"].resolved is True
    assert rows["a__a-1"].score_detail["scored_by"] == "GitHub Actions https://ci/7"
    assert rows["b__b-2"].resolved is False  # no patch → unresolved without the harness


def test_ci_score_without_an_artifact_leaves_results_pending(
    tmp_path: Path, db_session: Session
) -> None:
    _eval_run(db_session, "pipe2")
    pending = pipe.ci_score("pipe2", with_gold=False, publisher=FakePublisher(tmp_path),
                            actions=FakeActions(None), session_factory=_session_factory(db_session),
                            log=lambda m: None)  # fmt: skip
    assert pending == 1


# --------------------------------------------------------------------------- #
# The whole pipeline, with each stage faked
# --------------------------------------------------------------------------- #
def _run_pipeline(tmp_path: Path, monkeypatch, *, generate, ci_results):  # noqa: ANN001, ANN202
    events: list[str] = []
    monkeypatch.setattr(pipe, "publish_progress", lambda name, **k: events.append("progress"))
    monkeypatch.setattr(
        pipe, "ci_score", lambda name, **k: events.append("ci") or ci_results.pop(0)
    )
    monkeypatch.setattr(pipe, "publish_final", lambda name, **k: events.append("final"))
    monkeypatch.setattr(pipe, "disable_service", lambda: events.append("disable"))
    marker = tmp_path / "pipeline-x.done"
    pipe.run_pipeline(
        name="x", generate=generate, with_gold=True, publisher=None, actions=None,
        session_factory=None, showcase_tasks=[], showcase_evals=["x"], ablation=None,
        marker=marker, sleep_seconds=0, sleep=lambda s: None, log=lambda m: None,
    )  # fmt: skip
    return events, marker


def test_pipeline_generates_then_scores_then_publishes(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    passes = [False, True]  # quota ran out once
    events, marker = _run_pipeline(
        tmp_path, monkeypatch, generate=lambda: passes.pop(0), ci_results=[2, 0]
    )

    assert events == ["progress", "progress", "ci", "ci", "final", "disable"]
    assert marker.exists()


def test_pipeline_does_nothing_once_complete(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    (tmp_path / "pipeline-x.done").write_text("done")

    def never() -> bool:
        raise AssertionError("must not generate again")

    events, _ = _run_pipeline(tmp_path, monkeypatch, generate=never, ci_results=[])
    assert events == []


def test_pipeline_gives_up_after_repeated_ci_failures(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    with pytest.raises(pipe.PipelineError, match="still unscored"):
        _run_pipeline(tmp_path, monkeypatch, generate=lambda: True, ci_results=[3] * 5)
    assert not (tmp_path / "pipeline-x.done").exists()


# --------------------------------------------------------------------------- #
# Publishing progress and final results (real DB + real git)
# --------------------------------------------------------------------------- #
def _scored_run(db_session: Session, name: str, *, scored: bool) -> None:
    inst = sb.Instance("django__django-1", "django/django", "abc", "issue", PATCH)
    run = sb.get_or_create_run(db_session, name, [inst], ["rag"], {"seed": 7})
    for config, resolved in (("rag", True), ("gold", True)):
        db_session.add(EvalResult(eval_run_id=run.id, instance_id=inst.instance_id,
                                  repo="django/django", config=config, status="validated",
                                  patch=PATCH, resolved=resolved if scored else None))  # fmt: skip
    db_session.commit()


def _remote_file(remote: Path, path: str) -> str:
    return _git("show", f"main:{path}", cwd=remote)


def test_publish_progress_updates_the_report_and_readme(
    tmp_path: Path, remote: Path, db_session: Session
) -> None:
    _scored_run(db_session, "prog", scored=False)
    publisher = _publisher(tmp_path, remote)

    assert pipe.publish_progress(
        "prog", publisher=publisher, session_factory=_session_factory(db_session), ablation="v1"
    )

    assert _remote_log(remote)[0] == "eval: prog progress — 1/1 instances attempted [automated]"
    readme = _remote_file(remote, "README.md")
    assert "**In progress:** 1/1 instances attempted" in readme
    assert "[Current partial report](docs/eval/phase7-prog.md)" in readme
    assert "[earlier agent version](docs/eval/phase7-v1.md)" in readme
    assert "# SWE-bench Lite — DevPilot (prog)" in _remote_file(remote, "docs/eval/phase7-prog.md")


def test_publish_final_commits_report_readme_and_showcase(
    tmp_path: Path, remote: Path, db_session: Session
) -> None:
    _scored_run(db_session, "fin", scored=True)
    publisher = _publisher(tmp_path, remote)

    assert pipe.publish_final(
        "fin", publisher=publisher, session_factory=_session_factory(db_session),
        showcase_tasks=[], showcase_evals=["fin"], ablation=None,
    )  # fmt: skip

    assert _remote_log(remote)[0] == "eval: fin complete — RAG 1/1 resolved [automated]"
    readme = _remote_file(remote, "README.md")
    assert "| **RAG, issue only** (realistic) | 1/1 |" in readme
    assert "[the exact patches scored](docs/eval/predictions/fin.jsonl)" in readme
    assert readme.endswith("More.\n")  # text outside the markers untouched
    exported = json.loads(_remote_file(remote, pipe.SHOWCASE_FILE))
    assert [e["eval_run"]["name"] for e in exported["evals"]] == ["fin"]
