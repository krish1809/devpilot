"""Flag security-sensitive additions in a patch for the human reviewer.

Repository and issue text are untrusted, so a model can be talked into adding
code that reads secrets, runs commands, or phones home. These checks don't
block — legitimate fixes sometimes touch such APIs — but anything the patch
*newly introduces* (more occurrences added than removed) is surfaced as a
warning next to the Approve button.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("reads environment variables / secrets",
     re.compile(r"os\.environ|os\.getenv|getenv\(|process\.env|dotenv")),
    ("executes processes or dynamic code",
     re.compile(r"\bsubprocess\b|os\.system|os\.popen|\beval\(|\bexec\(|child_process")),
    ("makes network calls",
     re.compile(r"\brequests\.(get|post|put)|urllib|http\.client|\bsocket\b|\bhttpx\b|"
                r"\bfetch\(|\bcurl\b|\bwget\b")),
    ("touches credential files",
     re.compile(r"\.ssh/|id_rsa|\.git-credentials|/etc/passwd|\.aws/credentials|\.netrc")),
    ("decodes embedded payloads", re.compile(r"b64decode|base64\.decode|fromCharCode")),
]  # fmt: skip


def risk_warnings(diff: str) -> list[str]:
    """Warnings for risky constructs the diff adds on net."""
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [
        ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")
    ]
    warnings = []
    for label, pattern in _PATTERNS:
        new = sum(len(pattern.findall(ln)) for ln in added)
        old = sum(len(pattern.findall(ln)) for ln in removed)
        if new > old:
            example = next(ln.strip() for ln in added if pattern.search(ln))
            warnings.append(f"Patch {label}: `{example[:120]}`")
    return warnings
