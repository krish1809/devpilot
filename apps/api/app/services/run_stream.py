"""Server-Sent Events for live run progress.

The agent graph runs in the background and commits each step from its own
session, so the stream re-reads the run on a short interval and pushes a full
run snapshot whenever anything changed. It ends once the run leaves
``running`` (validated / failed / cancelled / …), or after ``max_seconds``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.models.agent_run import RunStatus


def format_event(event: str, data: str) -> str:
    """One SSE frame. Multi-line data becomes multiple ``data:`` lines."""
    lines = data.split("\n") or [""]
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


async def run_events(
    snapshot: Callable[[], Awaitable[dict | None]],
    *,
    poll_seconds: float,
    heartbeat_seconds: float,
    max_seconds: float,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """Yield SSE frames for one run.

    ``run`` carries the full run (same shape as ``GET /runs/{id}``) and is only
    sent when it changed; ``done`` ends a finished run; ``timeout`` ends a
    stream that outlived ``max_seconds`` (the client falls back to polling).
    Comment lines keep idle proxies from closing the connection.
    """
    yield "retry: 3000\n\n"
    started = time.monotonic()
    last_payload: str | None = None
    last_write = started

    while True:
        snap = await snapshot()
        if snap is None:  # deleted or no longer visible to this user
            yield format_event("done", json.dumps({"status": "gone"}))
            return

        now = time.monotonic()
        payload = json.dumps(snap, separators=(",", ":"), default=str)
        if payload != last_payload:
            yield format_event("run", payload)
            last_payload, last_write = payload, now

        if snap.get("status") != RunStatus.RUNNING:
            yield format_event("done", json.dumps({"status": snap.get("status")}))
            return
        if now - started >= max_seconds:
            yield format_event("timeout", "{}")
            return
        if now - last_write >= heartbeat_seconds:
            yield ": keep-alive\n\n"
            last_write = now

        await asyncio.sleep(poll_seconds)
        if await is_disconnected():
            return
