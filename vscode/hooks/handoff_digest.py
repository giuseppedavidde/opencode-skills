#!/usr/bin/env python3
"""PostToolUse hook: turn an agent answer into one short handoff line.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

The hook acts only when the finished tool is an agent spawn (`agent`, `task`,
`runSubagent`, ...). It reads `tool_response`, extracts the `## VERIFICA`
fields and the `## DELEGA` line, and emits one line in
`hookSpecificOutput.additionalContext`. The line is capped at 400 characters.

Dedupe by `tool_use_id` under `<state>/digest/`. The state folder is
`HOOK_STATE_DIR` when set, else `$XDG_CACHE_HOME/opencode-vscode-hooks`
(default `~/.cache`).

Fail-open: any error returns `{}` and never blocks the tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

SPAWN_TOOLS = {"agent", "Agent", "runSubagent", "task", "Task"}
MAX_LINE_CHARS = 400

CONFIDENCE_RE = re.compile(r"confidenza\s*[:：]\s*(\d{1,3})", re.IGNORECASE)
NON_VERIFIED_RE = re.compile(r"non_verificato\s*[:：]\s*(.*)", re.IGNORECASE)
ESCALATION_RE = re.compile(r"escalation_consigliata\s*[:：]\s*(.*)", re.IGNORECASE)
DELEGA_RE = re.compile(r"^##\s*DELEGA\b")


def read_payload() -> dict:
    """Parse the hook payload from stdin; return an empty dict on failure."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def payload_value(payload: dict, *keys: str) -> str:
    """Return the first non-empty string value among `keys`."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def flatten(value: object, depth: int = 0) -> str:
    """Flatten a tool response (string, dict or list of parts) to text."""
    if depth > 6:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [flatten(item, depth + 1) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if value.get("type") == "text":
            for key in ("text", "content"):
                if isinstance(value.get(key), str):
                    return value[key]
        for key in ("content", "result", "response", "text", "output", "message"):
            if key in value:
                text = flatten(value[key], depth + 1)
                if text:
                    return text
    return ""


def one_line(value: str, limit: int) -> str:
    """Collapse whitespace and cut `value` to `limit` characters."""
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed[:limit]


def first_line(match: re.Match[str] | None) -> str:
    """Return the first line of the first capture group of `match`."""
    if match is None:
        return ""
    return match.group(1).splitlines()[0] if match.group(1) else ""


def delega_line(text: str) -> str:
    """Return the text of the `## DELEGA` line, or its first non-empty next line."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if DELEGA_RE.match(stripped):
            rest = DELEGA_RE.sub("", stripped).strip()
            if rest:
                return rest
            for follow in lines[index + 1 :]:
                if follow.strip():
                    return follow.strip()
            return ""
    return ""


def state_dir() -> Path:
    """Return the hook state folder, never the home cache when HOOK_STATE_DIR is set."""
    override = os.environ.get("HOOK_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "opencode-vscode-hooks"


def already_seen(tool_use_id: str) -> bool:
    """True when this tool call already produced a digest line."""
    if not tool_use_id:
        return False
    key = hashlib.sha1(tool_use_id.encode("utf-8")).hexdigest()
    marker = state_dir() / "digest" / key
    try:
        if marker.exists():
            return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass
    return False


def build_line(text: str) -> str:
    """Return the one-line digest, or an empty string when nothing is found."""
    parts: list[str] = []
    confidence = CONFIDENCE_RE.search(text)
    if confidence is not None and confidence.group(1):
        parts.append(f"confidenza={confidence.group(1)}")
    non_verified = NON_VERIFIED_RE.search(text)
    if non_verified is not None and first_line(non_verified):
        parts.append(f"non_verificato={one_line(first_line(non_verified), 100)}")
    escalation = ESCALATION_RE.search(text)
    if escalation is not None and first_line(escalation):
        parts.append(f"escalation={one_line(first_line(escalation), 60)}")
    delega = delega_line(text)
    if delega:
        parts.append(f"DELEGA={one_line(delega, 200)}")
    if not parts:
        return ""
    line = "[handoff] " + " | ".join(parts)
    return line[:MAX_LINE_CHARS]


def main() -> int:
    """Emit the digest line for a finished agent spawn."""
    payload = read_payload()
    if payload_value(payload, "tool_name", "toolName") not in SPAWN_TOOLS:
        print("{}")
        return 0
    if already_seen(payload_value(payload, "tool_use_id", "toolUseId")):
        print("{}")
        return 0

    response = payload.get("tool_response")
    if response is None:
        response = payload.get("toolResponse")
    line = build_line(flatten(response))
    if not line:
        print("{}")
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": line,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
