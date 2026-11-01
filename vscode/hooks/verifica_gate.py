#!/usr/bin/env python3
"""VS Code SubagentStop hook: enforce the opencode `## VERIFICA` contract.

Reads the hook payload from stdin, finds the last assistant message in the
session transcript, and blocks the subagent when the block is missing. The
hook is intentionally fail-open: any parsing/runtime error returns `{}` so a
broken transcript can never trap the chat.

Audit events are appended to the same file used by the opencode verifica-gate
plugin: ~/.config/opencode/stats/gate_events.jsonl
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_DIR = Path.home() / ".config" / "opencode" / "stats"
VERIFICA_RE = re.compile(r"##\s*VERIFICA\b", re.IGNORECASE)
CONFIDENCE_RE = re.compile(r"confidenza\s*[:：]\s*(\d{1,3})", re.IGNORECASE)


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


def content_to_text(content: object) -> str:
    """Normalize a transcript message content (string or parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part.get("content"), str):
                parts.append(part["content"])
        return "\n".join(parts)
    return ""


def last_assistant_text(transcript_path: str) -> str:
    """Return the content of the last assistant message in the transcript.

    Supports the VS Code Copilot transcript (`assistant.message` + `data.content`)
    and the Claude-style (`assistant` / `role: assistant` + `message.content`).
    """
    if not transcript_path:
        return ""
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return ""
        text = ""
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if not isinstance(entry, dict):
                    continue
                candidate = ""
                if entry.get("type") == "assistant.message":
                    data = entry.get("data") or {}
                    candidate = content_to_text(data.get("content")) if isinstance(data, dict) else ""
                elif entry.get("type") == "assistant":
                    message = entry.get("message") or {}
                    candidate = content_to_text(message.get("content")) if isinstance(message, dict) else ""
                    candidate = candidate or content_to_text(entry.get("content"))
                elif entry.get("role") == "assistant":
                    candidate = content_to_text(entry.get("content"))
                if candidate:
                    text = candidate
        return text
    except Exception:
        return ""


def log_event(payload: dict, present: bool, confidence: int | None) -> None:
    """Append an audit event, mirroring the opencode verifica-gate format."""
    try:
        log_dir = Path(os.environ.get("GATE_LOG_DIR", str(DEFAULT_LOG_DIR))).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "vscode-verifica-gate",
            "subagent_type": payload_value(payload, "agent_type", "agentType") or "unknown",
            "case": "ok" if present else "missing_verifica",
            "confidenza": confidence,
            "prompt_snippet": "",
        }
        with (log_dir / "gate_events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # Audit is best effort; never break the chat because logging failed.
        pass


def main() -> int:
    payload = read_payload()

    # The harness sets this after a block to prevent infinite stop loops.
    if payload.get("stop_hook_active") or payload.get("stopHookActive"):
        print("{}")
        return 0

    transcript_path = payload_value(payload, "transcript_path", "transcriptPath")
    text = last_assistant_text(transcript_path)
    present = bool(VERIFICA_RE.search(text))

    confidence = None
    match = CONFIDENCE_RE.search(text)
    if match:
        try:
            confidence = int(match.group(1))
        except Exception:
            confidence = None

    log_event(payload, present, confidence)

    if present or not text:
        # No transcript or no assistant message: fail open.
        print("{}")
        return 0

    reason = (
        "Missing required `## VERIFICA` section. Append it before finishing:\n"
        "## VERIFICA\n"
        "- confidenza: <0-100>\n"
        "- evidenza: <commands/files actually checked>\n"
        "- non_verificato: <what was not checked>\n"
        "- escalation_consigliata: <sì/no>"
    )
    # Emit both shapes: the VS Code extension reads hookSpecificOutput, while
    # the shared Copilot runtime accepts the top-level decision/reason.
    print(json.dumps({"decision": "block", "reason": reason, "hookSpecificOutput": {"decision": "block", "reason": reason}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
