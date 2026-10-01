"""Synchronous helpers for calling ``devpilot-tools`` from the agent graph.

Production launches the server as a stdio subprocess bound to the run
(``stdio_target``); tests pass an in-process ``MCPServer`` instead. Either way
the call goes through the MCP protocol layer: schema validation, the server's
permission checks, and its audit log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from app.mcp.server import ToolBinding

API_ROOT = Path(__file__).resolve().parents[2]  # apps/api


class ToolCallError(Exception):
    """The server refused or failed the call (message comes from the server)."""


def stdio_target(binding: ToolBinding) -> StdioServerParameters:
    """Launch parameters for a server process bound to ``binding``. Only the
    binding is passed explicitly; the child inherits the SDK's safe default
    environment (no host secrets beyond what the app's own .env provides)."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp.server"],
        cwd=str(API_ROOT),
        env={
            "DEVPILOT_RUN_ID": str(binding.run_id),
            "DEVPILOT_TOOL_POLICY": ",".join(sorted(binding.policy)),
            "DEVPILOT_WORKSPACE_ROOT": str(binding.workspace_root),
        },
    )


def call_tool(target: Any, tool: str, arguments: dict[str, Any], *, timeout: float) -> dict:
    """Call one tool and return its JSON result (raises ToolCallError on refusal).

    ``timeout`` bounds the whole exchange, including starting the server."""

    async def go() -> dict:
        with anyio.fail_after(timeout):
            async with Client(target, read_timeout_seconds=timeout) as client:
                result = await client.call_tool(tool, arguments)
        text = "".join(getattr(c, "text", "") for c in result.content)
        if result.is_error:
            raise ToolCallError(text or f"{tool} failed")
        return json.loads(text) if text else {}

    try:
        return anyio.run(go)
    except TimeoutError as exc:
        raise ToolCallError(f"{tool} timed out after {timeout:.0f}s") from exc
