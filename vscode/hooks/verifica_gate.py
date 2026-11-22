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

The same answer is evaluated one time only: a sha1 key of session, agent and
text under `<state>/verifica_dedupe/` skips a repeat within 120 seconds and
writes no audit line.

A `## VERIFICA` block with confidenza below 60 blocks one time per session and
agent, and asks for the corrected COMPLETE answer. The counter of the block
expires after LOW_CONFIDENCE_TTL_SECONDS (600 s): the retry arrives within
seconds and passes, a later answer is gated again.

Audit events go to the file of the opencode verifica-gate plugin:
~/.config/opencode/stats/gate_events.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_DIR = Path.home() / ".config" / "opencode" / "stats"
VERIFICA_RE = re.compile(r"##\s*VERIFICA\b", re.IGNORECASE)
CONFIDENCE_RE = re.compile(r"confidenza\s*[:：]\s*(\d{1,3})", re.IGNORECASE)
DEDUPE_SECONDS = 120
LOW_CONFIDENCE_LIMIT = 60
LOW_CONFIDENCE_TTL_SECONDS = 600

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


def state_dir() -> Path:
    """Return the hook state folder, never the home cache when HOOK_STATE_DIR is set."""
    override = os.environ.get("HOOK_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "opencode-vscode-hooks"


def safe_name(value: str) -> str:
    """Return a file-system-safe name for a session or agent id."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:120]
    return cleaned or "default"


def agent_of(payload: dict) -> str:
    """Return the agent name of the payload, normalized for the state file names."""
    return normalize_agent(
        payload_value(payload, "agent_type", "agentType", "agent_name", "agentName") or "unknown"
    )


def dedupe_seen(payload: dict, text: str) -> bool:
    """True when the same answer was evaluated within 120 seconds."""
    session = payload_value(payload, "session_id", "sessionId") or "default"
    key = hashlib.sha1((session + "\x00" + agent_of(payload) + "\x00" + text).encode("utf-8")).hexdigest()
    marker = state_dir() / "verifica_dedupe" / key
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < DEDUPE_SECONDS:
            return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass
    return False


def low_confidence_used(payload: dict) -> bool:
    """True when this session and agent got a low-confidence block within the TTL.

    The counter is unused when its file is older than LOW_CONFIDENCE_TTL_SECONDS.
    A retry arrives within seconds, so the fresh counter lets it pass; a later
    low-confidence answer of a long session blocks again.
    """
    session = payload_value(payload, "session_id", "sessionId") or "default"
    path = state_dir() / "verifica_conf" / f"{safe_name(session)}__{safe_name(agent_of(payload))}"
    try:
        if time.time() - path.stat().st_mtime >= LOW_CONFIDENCE_TTL_SECONDS:
            return False
        return int(path.read_text(encoding="utf-8").strip() or "0") > 0
    except (OSError, ValueError):
        return False


def mark_low_confidence(payload: dict) -> None:
    """Increment the low-confidence counter of the session and agent."""
    session = payload_value(payload, "session_id", "sessionId") or "default"
    path = state_dir() / "verifica_conf" / f"{safe_name(session)}__{safe_name(agent_of(payload))}"
    count = 0
    try:
        count = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        count = 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(count + 1), encoding="utf-8")
    except OSError:
        pass


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

    # One evaluation per answer: a repeated stop is a no-op and is not logged.
    if dedupe_seen(payload, text):
        print("{}")
        return 0

    # Diagnostic: the answer was split and only the footer survived the retry.
    if present and len(text) < FOOTER_LIMIT_CHARS and len(previous) >= SOFT_LIMIT_CHARS:
        log_event(payload, "verifica_only_followup", confidence)
        print("{}")
        return 0

    if present or not text:
        # A low confidence asks for one corrected, complete answer. The cap is
        # one block per session and agent within 600 s, so a retry always passes
        # and a later answer of a long session is gated again.
        if present and confidence is not None and confidence < LOW_CONFIDENCE_LIMIT and not low_confidence_used(payload):
            mark_low_confidence(payload)
            log_event(payload, "low_confidence", confidence)
            reason = (
                f"Confidenza {confidence} sotto {LOW_CONFIDENCE_LIMIT}. "
                "Controlla i punti in non_verificato. Correggi. "
                "Rimanda la risposta COMPLETA con ## VERIFICA. Non inviare solo il footer."
            )
            print(json.dumps({"decision": "block", "reason": reason, "hookSpecificOutput": {"hookEventName": "SubagentStop", "decision": "block", "reason": reason}}))
            return 0
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
