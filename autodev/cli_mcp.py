"""autodev-mcp: Model Context Protocol server exposing AutoDev-CLI as tools.

Run as: `autodev-mcp` (after `pip install -e .`). Communicates via stdio JSON-RPC.

Tools exposed (all read-only or strictly guarded):

- autodev_status          — current goal / budget / KB stats
- autodev_lessons         — query learned lessons
- autodev_run_experiment  — submit one mutation + verify (no LLM call)
- autodev_init            — initialise a project

The server is intentionally thin: it shells out to the autodev CLI which is
the verified entry point. NO business logic in here.
"""
import json
import shutil
import subprocess
import sys
from typing import Any

# MCP SDK is a runtime dependency; we import at module top so pyright
# can see the symbols. If it is somehow missing, the script aborts with
# a clear message in main().
try:
    from mcp.server import Server as _Server  # type: ignore[import-not-found]
    from mcp.server.stdio import stdio_server as _stdio_server  # type: ignore[import-not-found]
    from mcp.types import TextContent as _TextContent  # type: ignore[import-not-found]
    from mcp.types import Tool as _Tool  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "MCP SDK not available. Install with: pip install 'mcp>=0.4.0'\n"
    )
    sys.exit(2)

# Lift to public names so the rest of the module reads cleanly.
Server = _Server
stdio_server = _stdio_server
Tool = _Tool
TextContent = _TextContent


SERVER_NAME = "autodev-mcp"
SERVER_VERSION = "0.2.0"


def _resolve_autodev_bin() -> str:
    bin_ = shutil.which("autodev")
    if bin_ is None:
        raise RuntimeError(
            "autodev CLI not on PATH. Install with `pip install -e .` "
            "into the same venv that runs autodev-mcp."
        )
    return bin_


def _run_cli(args: list[str]) -> dict[str, Any]:
    """Run the autodev CLI and parse its single-line JSON output.

    Raises RuntimeError on non-zero exit or invalid JSON.
    """
    bin_ = _resolve_autodev_bin()
    proc = subprocess.run(
        [bin_, *args, "--json"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(
            f"autodev {' '.join(args)} failed (exit={proc.returncode}): "
            f"{proc.stderr.strip()[:500]}"
        )
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON autodev output: {e}: {proc.stdout[:200]!r}") from e


def tool_autodev_status(project_root: str) -> dict[str, Any]:
    return _run_cli(["status", "--project-root", project_root])


def tool_autodev_lessons(
    project_root: str, pattern: str = "", limit: int = 20,
) -> dict[str, Any]:
    args = ["lessons", "--project-root", project_root, "--limit", str(limit)]
    if pattern:
        args.extend(["--pattern", pattern])
    return _run_cli(args)


def tool_autodev_run_experiment(
    project_root: str, file: str, mutation: str, verify_cmd: str,
) -> dict[str, Any]:
    return _run_cli([
        "run-experiment",
        "--project-root", project_root,
        "--mutation", mutation,
        "--verify-cmd", verify_cmd,
        file,
    ])


def tool_autodev_init(project_root: str) -> dict[str, Any]:
    return _run_cli(["init", project_root])


def tool_autodev_swarm(
    project_root: str,
    prompt: str,
    verify_cmd: str,
    agents: str = "fast,precise",
    budget_minutes: int = 15,
) -> dict[str, Any]:
    """Spawn a parallel swarm via the CLI; returns the SwarmResult JSON.

    Bridge pattern: no logic in cli_mcp.py. The CLI is the verified
    entry point (covered by tests/test_cli.py).
    """
    return _run_cli([
        "swarm",
        "--project-root", project_root,
        "--agents", agents,
        "--verify-cmd", verify_cmd,
        "--budget-minutes", str(budget_minutes),
        "--json",
        "-p", prompt,
    ])


def tool_autodev_session_log(
    project_root: str,
    action: str = "log",
    branch: str = "",
    source: str = "",
    target: str = "",
    reason: str = "",
    new_branch: str = "",
    parent_branch: str = "main",
) -> dict[str, Any]:
    """Time-travel session ops: fork / branches / log / merge / drop / snapshot / diff."""
    args = ["session", action, "--project-root", project_root, "--json"]
    if action == "fork":
        args.extend(["--into", new_branch, "--from", parent_branch])
        if reason:
            args.extend(["--reason", reason])
    elif action == "merge":
        args.extend(["--from", source, "--into", target])
    elif action in ("snapshot", "diff"):
        args.extend(["--branch", branch])
    elif action == "drop":
        args.extend(["--branch", branch])
    return _run_cli(args)


# ── Wire to MCP SDK ────────────────────────────────────────────────────
def build_server() -> Any:
    server: Any = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return [
            Tool(
                name="autodev_status",
                description="Get current goal / budget / KB stats for an AutoDev project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {
                            "type": "string",
                            "description": "Absolute path to the AutoDev project.",
                        },
                    },
                    "required": ["project_root"],
                },
            ),
            Tool(
                name="autodev_lessons",
                description="Query the lessons-learned SQLite database.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "pattern": {"type": "string", "default": ""},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["project_root"],
                },
            ),
            Tool(
                name="autodev_run_experiment",
                description="Run verification on a candidate mutation (no LLM call).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "file": {
                            "type": "string",
                            "description": "Path relative to project_root.",
                        },
                        "mutation": {
                            "type": "string",
                            "description": "Full file content to apply.",
                        },
                        "verify_cmd": {
                            "type": "string",
                            "description": "Shell command to execute for verification.",
                        },
                    },
                    "required": ["project_root", "file", "mutation", "verify_cmd"],
                },
            ),
            Tool(
                name="autodev_init",
                description="Bootstrap a project: create .autodev/knowledge.db.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                    },
                    "required": ["project_root"],
                },
            ),
            Tool(
                name="autodev_swarm",
                description="Spawn a parallel swarm of profile agents; first-verified-wins.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "prompt": {"type": "string"},
                        "verify_cmd": {"type": "string"},
                        "agents": {
                            "type": "string",
                            "default": "fast,precise",
                            "description": "Comma-separated profile names",
                        },
                        "budget_minutes": {
                            "type": "integer",
                            "default": 15,
                        },
                    },
                    "required": ["project_root", "prompt", "verify_cmd"],
                },
            ),
            Tool(
                name="autodev_session_log",
                description="Time-travel sessions: fork/branches/log/merge/drop/snapshot/diff.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["fork", "branches", "log", "merge",
                                     "drop", "snapshot", "diff"],
                            "default": "log",
                        },
                        "new_branch": {"type": "string"},
                        "parent_branch": {"type": "string", "default": "main"},
                        "branch": {"type": "string"},
                        "source": {"type": "string"},
                        "target": {"type": "string", "default": "main"},
                        "reason": {"type": "string", "default": ""},
                    },
                    "required": ["project_root"],
                },
            ),
        ]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[Any]:
            try:
                if name == "autodev_status":
                    result = tool_autodev_status(arguments["project_root"])
                elif name == "autodev_lessons":
                    result = tool_autodev_lessons(
                        arguments["project_root"],
                        arguments.get("pattern", ""),
                        int(arguments.get("limit", 20)),
                    )
                elif name == "autodev_run_experiment":
                    result = tool_autodev_run_experiment(
                        arguments["project_root"],
                        arguments["file"],
                        arguments["mutation"],
                        arguments["verify_cmd"],
                    )
                elif name == "autodev_init":
                    result = tool_autodev_init(arguments["project_root"])
                elif name == "autodev_swarm":
                    result = tool_autodev_swarm(
                        arguments["project_root"],
                        arguments["prompt"],
                        arguments["verify_cmd"],
                        arguments.get("agents", "fast,precise"),
                        int(arguments.get("budget_minutes", 15)),
                    )
                elif name == "autodev_session_log":
                    result = tool_autodev_session_log(
                        arguments["project_root"],
                        arguments.get("action", "log"),
                        arguments.get("branch", ""),
                        arguments.get("source", ""),
                        arguments.get("target", "main"),
                        arguments.get("reason", ""),
                        arguments.get("new_branch", ""),
                        arguments.get("parent_branch", "main"),
                    )
                else:
                    return [TextContent(type="text", text=f"unknown tool: {name}")]
            except (RuntimeError, KeyError, json.JSONDecodeError) as e:
                return [TextContent(type="text", text=f"error: {e}")]
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        return server


def main() -> int:
    server = build_server()
    import asyncio
    asyncio.run(_run(server))
    return 0


async def _run(server: Any) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    sys.exit(main())
