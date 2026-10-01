"""Run untrusted repository code inside a disposable Docker container.

Security posture (see docs/SECURITY.md): network disabled by default, CPU/
memory/PID limits, a hard timeout, bounded captured output, and `--rm` so the
container is always removed. It runs as the host's (non-root) user so anything
it writes into the mounted checkout stays removable, with bytecode writes off.
The host Docker socket is never mounted and no host credentials are passed in.
This never executes repository code on the API host.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_OUTPUT_LIMIT = 20_000  # characters of combined stdout/stderr to keep


@dataclass
class SandboxResult:
    passed: bool
    exit_code: int
    output: str
    timed_out: bool = False


def run_in_sandbox(
    workspace: Path,
    command: str,
    *,
    image: str,
    timeout_seconds: int,
    network: str = "none",
    memory: str = "512m",
    cpus: str = "1",
) -> SandboxResult:
    """Run ``command`` in ``image`` with ``workspace`` mounted at /work.

    Returns a SandboxResult; a non-zero exit code (including a timeout) means
    the test did not pass.
    """
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "--memory",
        memory,
        "--cpus",
        cpus,
        "--pids-limit",
        "256",
        *_user_args(),
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{workspace}:/work:rw",
        "-w",
        "/work",
        image,
        "sh",
        "-c",
        command,
    ]

    try:
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        captured = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(captured, bytes):  # pragma: no cover - text=True returns str
            captured = captured.decode("utf-8", "replace")
        return SandboxResult(
            passed=False,
            exit_code=124,
            output=_truncate(captured) + "\n[sandbox timed out]",
            timed_out=True,
        )
    except FileNotFoundError as exc:  # docker not installed / not on PATH
        return SandboxResult(
            passed=False,
            exit_code=127,
            output=f"[sandbox error] docker not available: {exc}",
        )

    output = _truncate((proc.stdout or "") + (proc.stderr or ""))
    return SandboxResult(passed=proc.returncode == 0, exit_code=proc.returncode, output=output)


def _user_args() -> list[str]:
    """Run as the invoking (non-root) user where the platform has uids."""
    if hasattr(os, "getuid") and os.getuid() != 0:
        return ["--user", f"{os.getuid()}:{os.getgid()}"]
    return []


def _truncate(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    head = text[: _OUTPUT_LIMIT // 2]
    tail = text[-_OUTPUT_LIMIT // 2 :]
    return f"{head}\n…[output truncated]…\n{tail}"
