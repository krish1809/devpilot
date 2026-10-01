"""Phase 6 evaluation: does repository retrieval help the agent?

Builds small multi-file Python repos with planted bugs. Each task gives the
agent ONLY the issue text and a test command — not the file to fix — and is run
twice: RAG off (the planner sees the plain file list) and RAG on (hybrid
retrieval over pgvector). Uses the real LLM, Docker sandbox, and embedder.
Nothing is published.

    cd apps/api && python -m scripts.rag_eval --owner you@example.com

Writes docs/eval/phase6-rag.{json,md}. Small n: read it as a smoke-level signal,
not a benchmark (that's Phase 7, SWE-bench Lite).
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from app.agents import runner
from app.agents.graph import AgentDeps
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations import git_ops
from app.integrations.github_pr import PublishError
from app.sandbox.runner import run_in_sandbox
from app.services import agent as agent_service
from app.services.user import get_user_by_email

TEST_COMMAND = "python -m unittest discover -s tests -t ."
DOCS = Path(__file__).resolve().parents[3] / "docs" / "eval"


@dataclass
class Case:
    name: str
    issue: str
    files: dict[str, str]
    gold_path: str
    gold_old: str
    gold_new: str


CASES = [
    Case(
        name="shop-cents",
        issue=(
            "Cart totals are off by a factor of ten: a cart with items priced $1.50 and "
            "$2.00 reports a total of 35 cents instead of 350."
        ),
        files={
            "shop/__init__.py": "",
            "shop/money.py": (
                "def to_cents(amount):\n"
                '    """Dollars (float) -> integer cents."""\n'
                "    return int(round(amount * 10))\n\n\n"
                "def from_cents(cents):\n    return cents / 100\n"
            ),
            "shop/cart.py": (
                "from shop.money import to_cents\n\n\n"
                "class Cart:\n"
                "    def __init__(self):\n        self.items = []\n\n"
                "    def add(self, name, price, qty=1):\n"
                "        self.items.append((name, price, qty))\n\n"
                "    def total_cents(self):\n"
                "        return sum(to_cents(price) * qty for _, price, qty in self.items)\n"
            ),
            "shop/pricing.py": (
                "def unit_price(base, markup_percent):\n"
                "    return base * (1 + markup_percent / 100)\n"
            ),
            "shop/tax.py": (
                'TAX_RATES = {"eu": 0.2, "us": 0.07}\n\n\n'
                "def tax_for(amount_cents, region):\n"
                "    return round(amount_cents * TAX_RATES[region])\n"
            ),
            "shop/discounts.py": (
                'COUPONS = {"TEN": 10, "HALF": 50}\n\n\n'
                "def apply_coupon(total_cents, code):\n"
                "    return total_cents - total_cents * COUPONS.get(code, 0) // 100\n"
            ),
            "tests/__init__.py": "",
            "tests/test_cart.py": (
                "import unittest\n\nfrom shop.cart import Cart\nfrom shop.tax import tax_for\n\n\n"
                "class CartTest(unittest.TestCase):\n"
                "    def test_total(self):\n"
                "        cart = Cart()\n"
                '        cart.add("tea", 1.50)\n        cart.add("milk", 2.00)\n'
                "        self.assertEqual(cart.total_cents(), 350)\n\n"
                "    def test_tax(self):\n"
                '        self.assertEqual(tax_for(1000, "eu"), 200)\n'
            ),
        },
        gold_path="shop/money.py",
        gold_old="amount * 10)",
        gold_new="amount * 100)",
    ),
    Case(
        name="textkit-slug",
        issue=(
            "Blog article URLs keep uppercase letters: 'Hello World' from 2024 becomes "
            "/blog/2024/Hello-World/ but our links must be all lowercase."
        ),
        files={
            "textkit/__init__.py": "",
            "textkit/normalize.py": (
                "import re\n\n\n"
                "def slugify(text):\n"
                '    words = re.findall(r"[A-Za-z0-9]+", text)\n'
                '    return "-".join(words)\n'
            ),
            "textkit/urls.py": (
                "from textkit.normalize import slugify\n\n\n"
                "def article_url(title, year):\n"
                '    return f"/blog/{year}/{slugify(title)}/"\n'
            ),
            "textkit/truncate.py": (
                "def truncate(text, limit):\n"
                '    return text if len(text) <= limit else text[: limit - 1] + "…"\n'
            ),
            "textkit/html.py": (
                "def escape(text):\n"
                '    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")\n'
            ),
            "tests/__init__.py": "",
            "tests/test_urls.py": (
                "import unittest\n\nfrom textkit.urls import article_url\n\n\n"
                "class UrlTest(unittest.TestCase):\n"
                "    def test_article_url(self):\n"
                "        self.assertEqual(\n"
                '            article_url("Hello World", 2024), "/blog/2024/hello-world/"\n'
                "        )\n"
            ),
        },
        gold_path="textkit/normalize.py",
        gold_old='"-".join(words)',
        gold_new='"-".join(w.lower() for w in words)',
    ),
    Case(
        name="feature-flags",
        issue="Feature flags set to false in the environment file are still treated as enabled.",
        files={
            "settings/__init__.py": "",
            "settings/loader.py": (
                "def parse_bool(value):\n"
                '    """Interpret an environment string as a boolean."""\n'
                "    return bool(value.strip())\n"
            ),
            "settings/env.py": (
                "def read_env(text):\n"
                "    env = {}\n"
                "    for line in text.splitlines():\n"
                '        if "=" in line and not line.startswith("#"):\n'
                '            key, value = line.split("=", 1)\n'
                "            env[key.strip()] = value.strip()\n"
                "    return env\n"
            ),
            "app/__init__.py": "",
            "app/features.py": (
                "from settings.env import read_env\nfrom settings.loader import parse_bool\n\n\n"
                "def enabled_features(env_text):\n"
                "    env = read_env(env_text)\n"
                "    return sorted(\n"
                '        key[len("FEATURE_"):].lower()\n'
                "        for key, value in env.items()\n"
                '        if key.startswith("FEATURE_") and parse_bool(value)\n'
                "    )\n"
            ),
            "app/logging_setup.py": (
                "import logging\n\n\ndef configure(level=logging.INFO):\n"
                "    logging.basicConfig(level=level)\n"
            ),
            "tests/__init__.py": "",
            "tests/test_features.py": (
                "import unittest\n\nfrom app.features import enabled_features\n\n\n"
                "class FeatureTest(unittest.TestCase):\n"
                "    def test_false_flags_are_disabled(self):\n"
                '        env = "FEATURE_BETA=false\\nFEATURE_SEARCH=true\\n"\n'
                '        self.assertEqual(enabled_features(env), ["search"])\n'
            ),
        },
        gold_path="settings/loader.py",
        gold_old="return bool(value.strip())",
        gold_new='return value.strip().lower() in {"1", "true", "yes", "on"}',
    ),
    Case(
        name="weekly-report",
        issue=(
            "The weekly report groups entries under the Tuesday of each week instead of "
            "the Monday that starts the week."
        ),
        files={
            "calendar_utils/__init__.py": "",
            "calendar_utils/weeks.py": (
                "from datetime import timedelta\n\n\n"
                "def week_start(day):\n"
                '    """The Monday of the ISO week containing `day`."""\n'
                "    return day - timedelta(days=day.weekday() - 1)\n"
            ),
            "calendar_utils/holidays.py": (
                "from datetime import date\n\n"
                'FIXED = {(1, 1): "New Year", (12, 25): "Christmas"}\n\n\n'
                "def is_holiday(day: date) -> bool:\n"
                "    return (day.month, day.day) in FIXED\n"
            ),
            "reports/__init__.py": "",
            "reports/weekly.py": (
                "from collections import Counter\n\n"
                "from calendar_utils.weeks import week_start\n\n\n"
                "def group_by_week(days):\n"
                "    return dict(Counter(week_start(d) for d in days))\n"
            ),
            "reports/monthly.py": (
                "from collections import Counter\n\n\n"
                "def group_by_month(days):\n"
                "    return dict(Counter((d.year, d.month) for d in days))\n"
            ),
            "tests/__init__.py": "",
            "tests/test_reports.py": (
                "import unittest\nfrom datetime import date\n\n"
                "from reports.weekly import group_by_week\n\n\n"
                "class WeeklyTest(unittest.TestCase):\n"
                "    def test_groups_by_monday(self):\n"
                "        days = [date(2024, 1, 3), date(2024, 1, 5)]\n"
                "        self.assertEqual(group_by_week(days), {date(2024, 1, 1): 2})\n"
            ),
        },
        gold_path="calendar_utils/weeks.py",
        gold_old="day.weekday() - 1",
        gold_new="day.weekday()",
    ),
    Case(
        name="last-in-stock",
        issue=(
            "Customers can't buy the last unit of an item: checkout fails with OutOfStock "
            "even though exactly one is left."
        ),
        files={
            "inventory/__init__.py": "",
            "inventory/stock.py": (
                "class OutOfStock(Exception):\n    pass\n\n\n"
                "class Stock:\n"
                "    def __init__(self, levels):\n        self.levels = dict(levels)\n\n"
                "    def can_reserve(self, sku, qty):\n"
                "        return self.levels.get(sku, 0) > qty\n\n"
                "    def reserve(self, sku, qty):\n"
                "        if not self.can_reserve(sku, qty):\n"
                "            raise OutOfStock(sku)\n"
                "        self.levels[sku] -= qty\n"
            ),
            "inventory/suppliers.py": (
                'SUPPLIERS = {"apple": "Orchard Co", "pear": "Orchard Co"}\n\n\n'
                "def supplier_for(sku):\n    return SUPPLIERS.get(sku)\n"
            ),
            "orders/__init__.py": "",
            "orders/checkout.py": (
                "from inventory.stock import Stock\n\n\n"
                "def checkout(stock: Stock, cart: dict) -> str:\n"
                "    for sku, qty in cart.items():\n"
                "        stock.reserve(sku, qty)\n"
                '    return "ok"\n'
            ),
            "orders/receipts.py": (
                "def receipt_lines(cart):\n"
                '    return [f"{sku} x{qty}" for sku, qty in sorted(cart.items())]\n'
            ),
            "tests/__init__.py": "",
            "tests/test_checkout.py": (
                "import unittest\n\nfrom inventory.stock import Stock\n"
                "from orders.checkout import checkout\n\n\n"
                "class CheckoutTest(unittest.TestCase):\n"
                "    def test_can_buy_last_unit(self):\n"
                '        stock = Stock({"apple": 1})\n'
                '        self.assertEqual(checkout(stock, {"apple": 1}), "ok")\n'
                '        self.assertEqual(stock.levels["apple"], 0)\n'
            ),
        },
        gold_path="inventory/stock.py",
        gold_old="self.levels.get(sku, 0) > qty",
        gold_new="self.levels.get(sku, 0) >= qty",
    ),
]


def _commit_all(repo: Path) -> str:
    git_ops._run(["git", "init", "-q"], cwd=repo)
    git_ops._run(["git", "add", "-A"], cwd=repo)
    git_ops._run(
        ["git", "-c", "user.email=eval@devpilot", "-c", "user.name=eval", "commit", "-qm", "init"],
        cwd=repo,
    )
    return git_ops.head_commit(repo)


def build_repo(root: Path, case: Case) -> tuple[Path, str]:
    repo = root / case.name
    for rel, content in case.files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(content)
    return repo, _commit_all(repo)


def sanity_check(root: Path, case: Case, repo: Path) -> None:
    """In the sandbox: the test fails as planted, and passes with the gold fix."""
    settings = get_settings()
    kw = {"image": settings.sandbox_image, "timeout_seconds": settings.sandbox_timeout_seconds}
    if run_in_sandbox(repo, TEST_COMMAND, **kw).passed:
        raise SystemExit(f"{case.name}: test passes before the fix")
    fixed = root / f"{case.name}-gold"
    shutil.copytree(repo, fixed)
    target = fixed / case.gold_path
    target.write_text(target.read_text().replace(case.gold_old, case.gold_new))
    result = run_in_sandbox(fixed, TEST_COMMAND, **kw)
    if not result.passed:
        raise SystemExit(f"{case.name}: gold fix does not pass:\n{result.output[-800:]}")


def _refuse_publish(*args, **kwargs):  # noqa: ANN002, ANN003
    raise PublishError("evaluation never publishes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, help="email of the user who owns eval tasks")
    parser.add_argument("--cases", nargs="*", help="subset of case names")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.cases or c.name in args.cases]
    root = Path(tempfile.mkdtemp(prefix="devpilot_rag_eval_"))
    deps = AgentDeps(
        session_factory=SessionLocal, checkpointer=InMemorySaver(), publisher=_refuse_publish
    )
    results = []
    try:
        with SessionLocal() as db:
            owner = get_user_by_email(db, args.owner)
            if owner is None:
                raise SystemExit(f"No user {args.owner!r}")
            repos = {}
            for case in cases:
                repos[case.name] = build_repo(root, case)
                sanity_check(root, case, repos[case.name][0])
                print(f"[ok] {case.name}: fails as planted, gold fix passes")

            # RAG off/on back to back per case, so both see the same conditions
            # (e.g. provider rate limits).
            for case in cases:
                for use_rag in (False, True):
                    repo, sha = repos[case.name]
                    task = agent_service.create_task(
                        db,
                        owner.id,
                        repo_url=str(repo),
                        base_commit=sha,
                        test_command=TEST_COMMAND,
                        target_path=None,
                        description=case.issue,
                    )
                    started = time.monotonic()
                    run = runner.run_to_completion(db, task, deps, use_rag=use_rag)
                    row = {
                        "case": case.name,
                        "rag": use_rag,
                        "run_id": run.id,
                        "status": run.status,
                        "resolved": run.status == "validated",
                        # The run itself failed (provider/infra), not the fix attempt.
                        "errored": run.status == "error",
                        "target": run.target_path,
                        "localized": run.target_path == case.gold_path,
                        "attempts": run.attempts,
                        "llm_calls": run.llm_calls,
                        "tokens": run.prompt_tokens + run.completion_tokens,
                        "seconds": round(time.monotonic() - started, 1),
                        "error": run.error,
                    }
                    results.append(row)
                    print(json.dumps(row))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    write_report(results)


def write_report(results: list[dict]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    meta = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "llm": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "max_attempts": settings.agent_max_attempts,
        "cases": len({r["case"] for r in results}),
    }
    (DOCS / "phase6-rag.json").write_text(json.dumps({"meta": meta, "runs": results}, indent=2))

    def summary(rag: bool) -> dict:
        rows = [r for r in results if r["rag"] is rag]
        n = len(rows) or 1
        return {
            "errored": sum(r["errored"] for r in rows),
            "resolved": sum(r["resolved"] for r in rows),
            "localized": sum(r["localized"] for r in rows),
            "n": len(rows),
            "attempts": sum(r["attempts"] for r in rows) / n,
            "tokens": sum(r["tokens"] for r in rows) / n,
            "seconds": sum(r["seconds"] for r in rows) / n,
        }

    off, on = summary(False), summary(True)
    lines = [
        "# Phase 6 — RAG vs no-RAG (smoke evaluation)",
        "",
        f"{meta['date']} · LLM `{meta['llm']}` · embeddings `{meta['embedding_model']}` · "
        f"max {meta['max_attempts']} attempts · {meta['cases']} cases. Generated by "
        "`python -m scripts.rag_eval`.",
        "",
        "Each task gives only the issue text and a test command — **not** the file. "
        "RAG off: the planner localizes from the repo's file list. RAG on: hybrid "
        "retrieval (pgvector + full-text) supplies ranked candidate files and code chunks. "
        "Resolved = the test passes in the sandbox; localized = the agent edited the file "
        "where the bug was planted (a test can pass with a fix elsewhere).",
        "",
        "| Config | Resolved | Localized to buggy file | Run errors | Avg attempts "
        "| Avg tokens | Avg time |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, s in (("No RAG (file list)", off), ("RAG (hybrid retrieval)", on)):
        lines.append(
            f"| {label} | {s['resolved']}/{s['n']} | {s['localized']}/{s['n']} | "
            f"{s['errored']} | {s['attempts']:.1f} | {s['tokens']:,.0f} | {s['seconds']:.1f}s |"
        )
    lines += [
        "",
        "| Case | RAG | Status | Edited file | Attempts | Tokens |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: (r["case"], r["rag"])):
        lines.append(
            f"| {r['case']} | {'on' if r['rag'] else 'off'} | {r['status']} | "
            f"`{r['target']}`{' ✓' if r['localized'] else ''} | {r['attempts']} | {r['tokens']:,} |"
        )
    lines += [
        "",
        "Caveats: 5 hand-made cases, one trial each at temperature 0 — a smoke-level signal, "
        "not a benchmark. The real measurement is Phase 7 (SWE-bench Lite).",
        "",
    ]
    (DOCS / "phase6-rag.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
