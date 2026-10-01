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

Models don't always comply exactly, so application is forgiving in two
bounded ways: a unified diff (``@@`` hunks) is accepted in place of blocks, and
a SEARCH that isn't found verbatim may match the single most similar window of
the file (≥ 3 lines, ≥ 92% similar, clearly better than any other window).
Anything less is rejected with a precise error that is fed back to the model.
"""

from __future__ import annotations

import difflib
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


_FUZZY_RATIO = 0.92
_FUZZY_MIN_LINES = 3  # short snippets match unrelated lines too easily
_FUZZY_MARGIN = 0.03  # the best window must clearly beat the runner-up
_HUNK_RE = re.compile(r"^@@[^\n]*@@[^\n]*\n", re.MULTILINE)


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


def _find_fuzzy(text: str, search: str) -> tuple[int, int] | None:
    """The unique line window most similar to ``search`` (ratio ≥ threshold)."""
    want = search.splitlines()
    have = text.splitlines(keepends=True)
    n = len(want)
    if n < _FUZZY_MIN_LINES or n > len(have):
        return None
    target = "\n".join(w.strip() for w in want)
    scored = []
    for i in range(len(have) - n + 1):
        window = "\n".join(h.strip() for h in have[i : i + n])
        ratio = difflib.SequenceMatcher(None, target, window, autojunk=False).ratio()
        if ratio >= _FUZZY_RATIO:
            scored.append((ratio, i))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[1][0] > scored[0][0] - _FUZZY_MARGIN:
        return None  # ambiguous
    i = scored[0][1]
    start = sum(len(x) for x in have[:i])
    return start, start + sum(len(x) for x in have[i : i + n])


def diff_to_blocks(reply: str) -> list[tuple[str, str]]:
    """Turn unified-diff hunks into (search, replace) pairs."""
    blocks = []
    for m in _HUNK_RE.finditer(reply):
        body = reply[m.end() :]
        nxt = re.search(r"^(@@|diff --git|--- |```)", body, re.MULTILINE)
        body = body[: nxt.start()] if nxt else body
        old, new = [], []
        for line in body.splitlines():
            if line.startswith("-"):
                old.append(line[1:])
            elif line.startswith("+"):
                new.append(line[1:])
            elif line.startswith(" ") or line == "":
                old.append(line[1:])
                new.append(line[1:])
            elif line.startswith("\\"):
                continue  # "\ No newline at end of file"
        while old and new and old[-1] == "" and new[-1] == "":
            old.pop()
            new.pop()
        if old:
            blocks.append(("\n".join(old), "\n".join(new)))
    return blocks


def apply_edits(original: str, reply: str) -> str:
    """Apply every SEARCH/REPLACE block (or diff hunk) in ``reply`` to ``original``."""
    blocks = _EDIT_RE.findall(reply) or diff_to_blocks(reply)
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
        span = _find_loose(text, search) or _find_fuzzy(text, search)
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
