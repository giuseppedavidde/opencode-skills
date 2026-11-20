#!/usr/bin/env python3
"""SubagentStop hook: enforce the opencode `## VERIFICA` contract in VS Code.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

install-vscode.py registers this script for `SubagentStop` with
`--agents <list>`. Only the listed opencode subagents are gated. Built-in
agents (`explore`, `task`, ...) and agents of other bundles pass unchanged.

The final answer comes from the payload (`last_assistant_message` in the
VS Code-compatible format, `response` in camelCase). When the payload has no
answer, the script reads the transcript and keeps only the messages of the
same agent (`agent_id`). The parent transcript also contains the messages of
other, parallel subagents.

A stop of a top-level agent is always allowed. The hook is fail-open: any
parse or runtime error returns `{}`, so a broken transcript cannot stop chat.

Audit events go to the file of the opencode verifica-gate plugin:
~/.config/opencode/stats/gate_events.jsonl
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

# Blocking a long, complete answer is worse than a missing footer: the retry
# usually replaces the whole analysis with a bare VERIFICA block, and the user
# loses the deliverable. Only short answers are blocked; long ones are logged.
SOFT_LIMIT_CHARS = 600
# A message shorter than this is a footer-sized reply, not an answer.
FOOTER_LIMIT_CHARS = 300


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


def entry_agent_id(entry: dict) -> str:
    """Return the agent id that a transcript entry carries, or an empty string."""
    for container in (entry, entry.get("data") if isinstance(entry.get("data"), dict) else {}):
        value = container.get("agentId") or container.get("agent_id")
        if isinstance(value, str) and value:
            return value
    return ""


def transcript_assistant_texts(transcript_path: str, agent_id: str = "") -> list[str]:
    """Return the assistant message texts of the transcript, oldest first.

    Supports the Copilot transcript (`assistant.message` + `data.content`) and
    the Claude-style (`assistant` / `role: assistant` + `message.content`).

    With `agent_id`, a transcript that tags entries with agent ids keeps only
    the entries of that agent. A transcript without agent ids keeps all entries.
    """
    if not transcript_path:
        return []
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return []
        texts: list[str] = []
        own: list[str] = []
        tagged = False
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
                if not candidate:
                    continue
                texts.append(candidate)
                owner = entry_agent_id(entry)
                if owner:
                    tagged = True
                if agent_id and owner == agent_id:
                    own.append(candidate)
        if agent_id and tagged:
            return own
        return texts
    except Exception:
        return []


def is_subagent_stop(payload: dict) -> bool:
    """True when the payload belongs to a subagent, not to the top-level agent."""
    if payload_value(payload, "hook_event_name", "hookEventName") in ("SubagentStop", "subagentStop"):
        return True
    return bool(
        payload_value(
            payload,
            "agent_id",
            "agentId",
            "agent_type",
            "agentType",
            "parent_agent_id",
            "parentAgentId",
            "last_assistant_message",
            "response",
        )
    )


def final_and_previous(payload: dict) -> tuple[str, str]:
    """Return (final answer, previous answer of the same agent)."""
    agent_id = payload_value(payload, "agent_id", "agentId")
    transcript_path = payload_value(payload, "transcript_path", "transcriptPath")
    texts = transcript_assistant_texts(transcript_path, agent_id)
    direct = payload_value(payload, "last_assistant_message", "response")
    if direct:
        earlier = [text for text in texts if text.strip() != direct.strip()]
        return direct, earlier[-1] if earlier else ""
    text = texts[-1] if texts else ""
    previous = texts[-2] if len(texts) > 1 else ""
    return text, previous


def log_event(payload: dict, case: str, confidence: int | None) -> None:
    """Append an audit event, mirroring the opencode verifica-gate format."""
    try:
        log_dir = Path(os.environ.get("GATE_LOG_DIR", str(DEFAULT_LOG_DIR))).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "vscode-verifica-gate",
            "subagent_type": payload_value(payload, "agent_type", "agentType", "agent_name", "agentName")
            or "unknown",
            "event": payload_value(payload, "hook_event_name", "hookEventName") or "unknown",
            "case": case,
            "confidenza": confidence,
            "prompt_snippet": "",
        }
        with (log_dir / "gate_events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # Audit is best effort; never break the chat because logging failed.
        pass


def normalize_agent(name: str) -> str:
    """Normalize an agent name for comparison (`Coder_Planner` == `coder-planner`)."""
    return name.strip().lower().replace("_", "-")


def gated_agents(argv: list[str]) -> set[str]:
    """Return the agent names from `--agents a,b,c` (empty set = gate every subagent)."""
    names: set[str] = set()
    for index, arg in enumerate(argv):
        value = ""
        if arg == "--agents" and index + 1 < len(argv):
            value = argv[index + 1]
        elif arg.startswith("--agents="):
            value = arg.split("=", 1)[1]
        names.update(normalize_agent(item) for item in value.split(",") if item.strip())
    return names


def agent_in_scope(payload: dict, agents: set[str]) -> bool:
    """True when the subagent is one of the gated agents (or when no list is set)."""
    if not agents:
        return True
    for key in ("agent_name", "agentName", "agent_type", "agentType", "agent_display_name", "agentDisplayName"):
        value = payload.get(key)
        if isinstance(value, str) and normalize_agent(value) in agents:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    payload = read_payload()
    agents = gated_agents(sys.argv[1:] if argv is None else argv)

    # The harness sets this after a block to prevent infinite stop loops.
    if payload.get("stop_hook_active") or payload.get("stopHookActive"):
        print("{}")
        return 0

    # The contract applies to opencode subagents only: never to the top-level
    # agent, to built-in agents, or to agents of other customization bundles.
    if not is_subagent_stop(payload) or not agent_in_scope(payload, agents):
        print("{}")
        return 0

    text, previous = final_and_previous(payload)
    present = bool(VERIFICA_RE.search(text))

    confidence = None
    match = CONFIDENCE_RE.search(text)
    if match:
        try:
            confidence = int(match.group(1))
        except Exception:
            confidence = None

    # Diagnostic: the answer was split and only the footer survived the retry.
    if present and len(text) < FOOTER_LIMIT_CHARS and len(previous) >= SOFT_LIMIT_CHARS:
        log_event(payload, "verifica_only_followup", confidence)
        print("{}")
        return 0

    if present or not text:
        # No transcript or no assistant message: fail open.
        log_event(payload, "ok" if present else "no_text", confidence)
        print("{}")
        return 0

    if len(text) >= SOFT_LIMIT_CHARS:
        # Long, complete answer without the footer. Blocking would trigger a
        # retry that commonly returns a bare VERIFICA block and loses the body.
        log_event(payload, "missing_verifica_soft", confidence)
        print("{}")
        return 0

    log_event(payload, "missing_verifica", confidence)

    reason = (
        "Missing the `## VERIFICA` section.\n"
        "Send your COMPLETE answer again, with the block APPENDED at the end.\n"
        "Do NOT send a message that contains only the VERIFICA block: the user "
        "would lose the analysis.\n\n"
        "## VERIFICA\n"
        "- confidenza: <0-100>\n"
        "- evidenza: <commands/files actually checked>\n"
        "- non_verificato: <what was not checked>\n"
        "- escalation_consigliata: <sì/no>"
    )
    # Emit both shapes: the Copilot harness reads the top-level decision/reason,
    # the deprecated Local harness reads hookSpecificOutput.
    print(json.dumps({"decision": "block", "reason": reason, "hookSpecificOutput": {"decision": "block", "reason": reason}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
