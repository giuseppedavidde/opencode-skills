#!/usr/bin/env python3
"""SessionStart hook: remind the model to query an existing graphify graph.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

Port of the opencode `graphify` plugin. When the session folder (or one of its
parents) contains `graphify-out/graph.json`, the hook adds a short reminder to
the model context. `sessionStart` output supports `additionalContext` in the
Copilot harness, and `hookSpecificOutput.additionalContext` in the Local one.

A legacy `PreToolUse` configuration still works: the reminder then appears
once per session, before the first shell command.

When a `.manifest.json` sits next to this script, the hook checks the sha256 of
every installed file. A mismatch adds a drift line to the context. The drift
line is emitted even when the project has no graph.

Fail-open: any error returns `{}` and never blocks the session or a tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

DRIFT_TEXT = "opencode-skills: gli hook installati differiscono dal manifest. Rerun ./install.sh."

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


def state_dir() -> Path:
    """Return the hook state folder, never the home cache when HOOK_STATE_DIR is set."""
    override = os.environ.get("HOOK_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "opencode-vscode-hooks"


def session_marker(payload: dict) -> Path | None:
    session = payload_value(payload, "session_id", "sessionId") or "default"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session)[:120]
    return state_dir() / "graphify" / f"{safe}.seen"


def check_manifest_drift(script_dir: Path) -> str | None:
    """Return the drift message when an installed file does not match the manifest."""
    try:
        manifest_path = script_dir / ".manifest.json"
        if not manifest_path.is_file():
            return None
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            return None
        for name, expected in hooks.items():
            path = script_dir / name
            if not path.is_file():
                return DRIFT_TEXT
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return DRIFT_TEXT
        return None
    except Exception:
        return None


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


def emit_reminder(event: str, drift: str | None = None, reminder: str | None = REMINDER) -> None:
    """Print the reminder and/or the drift line in the Copilot shape and in the Local shape."""
    context = "\n".join(part for part in (reminder, drift) if part)
    print(
        json.dumps(
            {
                "additionalContext": context,
                "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
            }
        )
    )


def legacy_pre_tool_use(payload: dict) -> int:
    """Old PreToolUse configuration: remind once per session, before a shell command."""
    if tool_name(payload) not in SHELL_TOOL_NAMES or not command_of(payload):
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

    emit_reminder("PreToolUse", check_manifest_drift(script_dir()))
    return 0


def script_dir() -> Path:
    """Return the folder of this installed script."""
    return Path(__file__).resolve().parent


def main() -> int:
    payload = read_payload()
    if tool_name(payload):
        return legacy_pre_tool_use(payload)

    root = resolve_workspace_root(payload)
    has_graph = (root / "graphify-out" / "graph.json").is_file()
    drift = check_manifest_drift(script_dir())
    if not has_graph and not drift:
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
            # If the marker cannot be written, still emit the context once per call.
            pass

    emit_reminder(
        payload_value(payload, "hook_event_name", "hookEventName") or "SessionStart",
        drift,
        REMINDER if has_graph else None,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
