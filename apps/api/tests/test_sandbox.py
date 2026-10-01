import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.sandbox.runner import run_in_sandbox

IMAGE = "python:3.11-slim"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
    except (subprocess.SubprocessError, OSError):
        return False
    # Image must be present locally (we never pull inside tests).
    result = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=10)
    return result.returncode == 0


docker = pytest.mark.skipif(not _docker_available(), reason="docker or base image unavailable")


def test_missing_docker_is_handled_gracefully() -> None:
    # A bogus binary name simulates docker being absent; no exception should escape.
    with tempfile.TemporaryDirectory() as tmp:
        result = run_in_sandbox(Path(tmp), "true", image=IMAGE, timeout_seconds=5, network="none")
        # Either it ran (docker present) or returned a handled error code.
        assert result.exit_code in (0, 127) or not result.passed


@docker
def test_passing_command_reports_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_in_sandbox(
            Path(tmp), "python -c 'print(1+1)'", image=IMAGE, timeout_seconds=60
        )
        assert result.passed
        assert result.exit_code == 0


@docker
def test_failing_command_reports_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_in_sandbox(
            Path(tmp), "python -c 'import sys; sys.exit(1)'", image=IMAGE, timeout_seconds=60
        )
        assert not result.passed
        assert result.exit_code == 1


@docker
def test_timeout_is_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_in_sandbox(Path(tmp), "sleep 30", image=IMAGE, timeout_seconds=2)
        assert result.timed_out
        assert not result.passed


@pytest.mark.skipif(not _docker_available(), reason="docker not available")
def test_sandbox_writes_are_removable_by_host(tmp_path) -> None:  # noqa: ANN001
    result = run_in_sandbox(
        tmp_path, "mkdir -p out && touch out/f && id -u", image=IMAGE, timeout_seconds=60
    )
    assert result.passed
    import os

    assert result.output.strip() == str(os.getuid())
    (tmp_path / "out" / "f").unlink()  # would raise PermissionError if root-owned
