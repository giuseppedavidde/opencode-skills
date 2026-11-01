#!/usr/bin/env python3
"""VS Code PreToolUse hook: remind the model to query an existing graphify graph.

Faithful port of the opencode `graphify` plugin: before a shell command runs in
a directory that contains `graphify-out/graph.json`, inject a short reminder
into the model context. The reminder is emitted once per session.

Fail-open: any error returns `{}` and never blocks the tool call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SHELL_TOOL_NAMES = {
    "runInTerminal",
    "run_in_terminal",
    "execute",
    "bash",
    "shell",
    "terminal",
    "Shell",
    "Bash",
}

REMINDER = (
    "[graphify] A knowledge graph exists at graphify-out/. For focused questions "
    'run `graphify query "<question>"` (scoped subgraph, usually much smaller than '
    "GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for "
    "broad architecture context."
)


def read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def payload_value(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def tool_name(payload: dict) -> str:
    return payload_value(payload, "tool_name", "toolName")


def command_of(payload: dict) -> str:
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    if not isinstance(args, dict):
        return ""
    for key in ("command", "commandLine", "cmd", "script"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def session_marker(payload: dict) -> Path | None:
    session = payload_value(payload, "session_id", "sessionId") or "default"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:120]
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache_root / "opencode-vscode-graphify" / f"{safe}.seen"


def find_graph_root(start: Path) -> Path | None:
    """Walk up from `start` to the first directory containing graphify-out/graph.json."""
    try:
        candidates = [start, *start.parents]
    except Exception:
        return None
    for candidate in candidates:
        try:
            if (candidate / "graphify-out" / "graph.json").is_file():
                return candidate
        except OSError:
            continue
    return None


def resolve_workspace_root(payload: dict) -> Path:
    """Resolve the directory where the graph should be looked up."""
    for key in ("cwd", "workspaceFolder", "workspace_folder"):
        value = payload_value(payload, key)
        if value:
            candidate = Path(value).expanduser()
            if candidate.is_dir():
                found = find_graph_root(candidate)
                return found or candidate
    cwd = Path(os.environ.get("VSCODE_CWD", os.getcwd())).expanduser()
    return find_graph_root(cwd) or cwd


def main() -> int:
    payload = read_payload()
    if tool_name(payload) not in SHELL_TOOL_NAMES:
        print("{}")
        return 0

    if not command_of(payload):
        print("{}")
        return 0

    root = resolve_workspace_root(payload)
    if not (root / "graphify-out" / "graph.json").is_file():
        print("{}")
        return 0

    marker = session_marker(payload)
    if marker is not None:
        try:
            if marker.exists():
                print("{}")
                return 0
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1", encoding="utf-8")
        except Exception:
            # If the marker cannot be written, still emit the reminder once per call.
            pass

    # Emit both shapes: the VS Code extension reads hookSpecificOutput, while
    # the shared Copilot runtime accepts a top-level additionalContext.
    print(
        json.dumps(
            {
                "additionalContext": REMINDER,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": REMINDER,
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
