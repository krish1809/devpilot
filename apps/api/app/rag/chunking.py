"""Select indexable files from a checkout and split them into chunks.

Only git-tracked text files are considered. Excluded: vendored/generated
directories, lockfiles and minified assets, binaries, oversized files, and
anything that looks like a secret (key files are skipped; token-like strings in
other files are redacted). Repository content is untrusted: nothing here
executes it.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.integrations import git_ops

_EXCLUDED_DIRS = {
    ".git", "node_modules", "vendor", "vendors", "third_party", "third-party",
    "site-packages", "dist", "build", ".venv", "venv", "env", "__pycache__",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next",
    "coverage", "htmlcov", ".idea", ".vscode", ".eggs",
}  # fmt: skip
_EXCLUDED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
    "uv.lock", "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum",
}  # fmt: skip
_SECRET_NAME = re.compile(
    r"(^\.env(\..*)?$)|(\.(pem|key|p12|pfx|jks|keystore|crt|der)$)|(^id_(rsa|dsa|ecdsa|ed25519))"
    r"|(^\.(npmrc|pypirc|netrc)$)|(^credentials(\.json)?$)",
    re.IGNORECASE,
)
_TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".kt", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".scala",
    ".sh", ".bash", ".sql", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json",
    ".cfg", ".ini", ".html", ".css", ".scss", ".vue", ".svelte",
}  # fmt: skip
_TEXT_NAMES = {"README", "LICENSE", "Makefile", "Dockerfile", "CHANGELOG", "CONTRIBUTING"}

_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b(?:sk-|gsk_|sk_live_|rk_live_)[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(
        r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*)(['\"])[^'\"\s]{8,}\2"
    ),
]

MAX_FILE_BYTES = 200_000
WINDOW = 60  # lines per window chunk
OVERLAP = 10
MAX_CHUNK_LINES = 120
MIN_SEGMENT_LINES = 15


@dataclass(frozen=True)
class Chunk:
    path: str
    start_line: int  # 1-based, inclusive
    end_line: int
    content: str


def is_indexable_path(relpath: str) -> bool:
    p = PurePosixPath(relpath)
    if any(part in _EXCLUDED_DIRS for part in p.parts[:-1]):
        return False
    name = p.name
    if name in _EXCLUDED_NAMES or _SECRET_NAME.search(name):
        return False
    if name.endswith((".min.js", ".min.css", ".map")):
        return False
    return p.suffix.lower() in _TEXT_SUFFIXES or p.stem in _TEXT_NAMES


def redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]{m.group(2)}", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def read_indexable_text(workspace: Path, relpath: str) -> str | None:
    """The file's text if it should be indexed, else None (binary/large/key)."""
    path = workspace / relpath
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if _PRIVATE_KEY.search(text):
        return None
    return redact_secrets(text)


def tracked_files(workspace: Path) -> list[str]:
    out = git_ops._run(["git", "ls-files", "-z"], cwd=workspace)
    return sorted(f for f in out.split("\0") if f)


def _windows(lines: list[str], start: int, end: int) -> list[tuple[int, int]]:
    """Overlapping windows over 1-based [start, end]."""
    spans, s = [], start
    while s <= end:
        e = min(s + WINDOW - 1, end)
        spans.append((s, e))
        if e == end:
            break
        s = e - OVERLAP + 1
    return spans


def _python_spans(text: str, n_lines: int) -> list[tuple[int, int]] | None:
    """Spans split at top-level def/class boundaries (None if unparsable)."""
    try:
        with warnings.catch_warnings():  # old code: invalid escape sequences etc.
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    starts = sorted(
        {
            min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
    )
    bounds = sorted({1, *starts})
    segments = [
        (s, (bounds[i + 1] - 1) if i + 1 < len(bounds) else n_lines) for i, s in enumerate(bounds)
    ]
    merged: list[tuple[int, int]] = []
    for s, e in segments:
        if merged and (merged[-1][1] - merged[-1][0] + 1) < MIN_SEGMENT_LINES:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def chunk_file(relpath: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    n = len(lines)
    spans = (_python_spans(text, n) if relpath.endswith(".py") else None) or [(1, n)]
    out: list[Chunk] = []
    for s, e in spans:
        pieces = [(s, e)] if e - s + 1 <= MAX_CHUNK_LINES else _windows(lines, s, e)
        for ps, pe in pieces:
            content = "\n".join(lines[ps - 1 : pe])
            if content.strip():
                out.append(Chunk(relpath, ps, pe, content))
    return out


_TEST_DIRS = {"tests", "test", "testing", "testcases"}


_DOC_SUFFIXES = {".md", ".rst", ".txt"}


def is_doc_path(relpath: str) -> bool:
    p = PurePosixPath(relpath)
    return p.suffix.lower() in _DOC_SUFFIXES or "docs" in p.parts[:-1] or p.stem in _TEXT_NAMES


def is_test_path(relpath: str) -> bool:
    p = PurePosixPath(relpath)
    name = p.name
    return (
        any(part in _TEST_DIRS for part in p.parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", "_tests.py"))
        or name == "conftest.py"
    )


def collect_chunks(workspace: Path, *, max_files: int, max_chunks: int) -> tuple[list[Chunk], int]:
    """Chunks for every indexable tracked file. Returns (chunks, files_indexed).

    Source files are indexed before tests, so when a large repository hits the
    caps it is the (usually huge) test suite that gets cut, not the code."""
    chunks: list[Chunk] = []
    files = 0
    for relpath in sorted(tracked_files(workspace), key=lambda f: (is_test_path(f), f)):
        if files >= max_files or len(chunks) >= max_chunks:
            break
        if not is_indexable_path(relpath):
            continue
        text = read_indexable_text(workspace, relpath)
        if text is None:
            continue
        files += 1
        chunks.extend(chunk_file(relpath, text))
    return chunks[:max_chunks], files
