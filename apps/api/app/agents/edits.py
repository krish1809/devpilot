"""Large-file editing: pick the relevant excerpt of a file to show the model,
and apply the SEARCH/REPLACE blocks it returns.

Whole-file rewrites don't scale to real repositories (a 3,000-line module
blows the prompt and output budget), so above a size threshold the coder sees
only the windows most related to the issue/plan and answers with edit blocks:

    <<<<<<< SEARCH
    exact existing lines
    =======
    replacement lines
    >>>>>>> REPLACE
"""

from __future__ import annotations

import math
import re

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP = {
    "the", "and", "for", "not", "with", "this", "that", "from", "self", "return", "def",
    "class", "import", "none", "true", "false", "should", "when", "but", "are", "was",
    "have", "has", "can", "will", "would", "into", "use", "used", "using", "also", "than",
}  # fmt: skip
_WINDOW = 30
_CONTEXT_LINES = 5
_EDIT_RE = re.compile(
    r"<<<<<<<\s*SEARCH[^\n]*\n(.*?)\n?=======[^\n]*\n(.*?)\n?>>>>>>>\s*REPLACE", re.DOTALL
)


class EditError(Exception):
    """The model's edit blocks could not be applied to the file."""


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _IDENT.findall(text)} - _STOP


def file_excerpt(text: str, query: str, budget_chars: int) -> str:
    """The parts of ``text`` most related to ``query``, within ``budget_chars``.

    Windows are scored by the IDF-weighted identifiers they share with the
    query; the best ones (plus a few lines of context and the file header) are
    shown in file order, each labelled with its line range.
    """
    lines = text.splitlines()
    if len(text) <= budget_chars:
        return text
    windows = [(s, min(s + _WINDOW, len(lines))) for s in range(0, len(lines), _WINDOW)]
    win_tokens = [_tokens("\n".join(lines[s:e])) for s, e in windows]
    query_tokens = _tokens(query)
    df = {t: sum(t in w for w in win_tokens) for t in query_tokens}
    n = len(windows)

    def score(i: int) -> float:
        return sum(math.log((n + 1) / (1 + df[t])) for t in query_tokens & win_tokens[i])

    ranked = sorted(range(n), key=lambda i: (-score(i), i))
    chosen: list[tuple[int, int]] = [(0, min(15, len(lines)))]  # header: imports etc.
    used = len("\n".join(lines[0:15]))
    for i in ranked:
        if score(i) <= 0:
            break
        s, e = windows[i]
        s, e = max(0, s - _CONTEXT_LINES), min(len(lines), e + _CONTEXT_LINES)
        size = len("\n".join(lines[s:e]))
        if used + size > budget_chars:
            continue
        chosen.append((s, e))
        used += size

    merged: list[list[int]] = []
    for s, e in sorted(chosen):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    parts = [f"### lines {s + 1}-{e}\n" + "\n".join(lines[s:e]) for s, e in merged]
    omitted = len(lines) - sum(e - s for s, e in merged)
    return "\n…\n".join(parts) + f"\n… ({omitted} other lines not shown)"


def _find_loose(text: str, search: str) -> tuple[int, int] | None:
    """Locate ``search`` ignoring trailing whitespace on each line (unique match)."""
    want = [ln.rstrip() for ln in search.splitlines()]
    have = text.splitlines(keepends=True)
    hits = []
    for i in range(len(have) - len(want) + 1):
        if all(have[i + j].rstrip() == want[j] for j in range(len(want))):
            hits.append(i)
    if len(hits) != 1:
        return None
    start = sum(len(x) for x in have[: hits[0]])
    end = start + sum(len(x) for x in have[hits[0] : hits[0] + len(want)])
    return start, end


def apply_edits(original: str, reply: str) -> str:
    """Apply every SEARCH/REPLACE block in ``reply`` to ``original``."""
    blocks = _EDIT_RE.findall(reply)
    if not blocks:
        raise EditError("No SEARCH/REPLACE blocks found in the reply.")
    text = original
    for search, replace in blocks:
        if not search.strip():
            raise EditError("A SEARCH block is empty.")
        count = text.count(search)
        if count == 1:
            text = text.replace(search, replace, 1)
            continue
        if count > 1:
            raise EditError(
                f"SEARCH block matches {count} places; include more surrounding lines: "
                f"{search.strip().splitlines()[0][:120]!r}"
            )
        span = _find_loose(text, search)
        if span is None:
            raise EditError(
                "SEARCH block not found in the file (it must be copied exactly): "
                f"{search.strip().splitlines()[0][:120]!r}"
            )
        start, end = span
        tail = "\n" if text[start:end].endswith("\n") and not replace.endswith("\n") else ""
        text = text[:start] + replace + tail + text[end:]
    if text == original:
        raise EditError("The edits do not change the file.")
    return text
