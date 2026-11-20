"""Regression tests for the VS Code SubagentStop verifica gate.

The gate must never turn a complete answer into a footer-only reply. A long
answer without the VERIFICA block is allowed (and logged); only short answers
are blocked, and the block reason asks for the COMPLETE answer again.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "verifica_gate.py"

FOOTER = (
    "## VERIFICA\n"
    "- confidenza: 90\n"
    "- evidenza: pytest\n"
    "- non_verificato: nulla\n"
    "- escalation_consigliata: no"
)


def _message(text: str) -> dict:
    return {"type": "assistant.message", "data": {"content": [{"type": "text", "text": text}]}}


def _run(tmp_path: Path, messages: list[dict]) -> dict:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(m) for m in messages) + "\n", encoding="utf-8"
    )
    payload = {"transcript_path": str(transcript), "agent_type": "trade"}
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={"GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    return json.loads(result.stdout or "{}")


def test_long_answer_without_verifica_is_not_blocked(tmp_path: Path) -> None:
    """Blocking a long answer triggers a retry that loses the body."""
    assert _run(tmp_path, [_message("A" * 900)]) == {}


def test_short_answer_without_verifica_is_blocked(tmp_path: Path) -> None:
    decision = _run(tmp_path, [_message("fatto")])
    assert decision.get("decision") == "block"
    reason = decision.get("reason", "")
    assert "COMPLETE answer" in reason
    assert "only the VERIFICA block" in reason


def test_long_answer_with_footer_passes(tmp_path: Path) -> None:
    assert _run(tmp_path, [_message("A" * 900 + "\n\n" + FOOTER)]) == {}


def test_footer_only_followup_is_logged(tmp_path: Path) -> None:
    _run(tmp_path, [_message("A" * 900), _message(FOOTER)])
    log = (tmp_path / "gate_events.jsonl").read_text(encoding="utf-8")
    assert "verifica_only_followup" in log


def test_missing_verifica_soft_is_logged(tmp_path: Path) -> None:
    _run(tmp_path, [_message("A" * 900)])
    log = (tmp_path / "gate_events.jsonl").read_text(encoding="utf-8")
    assert "missing_verifica_soft" in log


def test_stop_hook_active_fails_open(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps(_message("x")) + "\n", encoding="utf-8")
    payload = {"transcript_path": str(transcript), "stop_hook_active": True}
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={"GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert json.loads(result.stdout or "{}") == {}


# ── Copilot harness payloads (VS Code-compatible SubagentStop) ──────────────

COMPLETE = "A" * 900 + "\n\n" + FOOTER


def _tagged(text: str, agent_id: str) -> dict:
    """A Copilot transcript entry: the parent transcript tags subagent messages."""
    return {"type": "assistant.message", "agentId": agent_id, "data": {"content": text}}


def _gate(tmp_path: Path, payload: dict, entries: list[dict], *args: str) -> dict:
    transcript = tmp_path / "events.jsonl"
    transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    payload = {"transcript_path": str(transcript), **payload}
    result = subprocess.run(
        [sys.executable, str(HOOK), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={"GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    return json.loads(result.stdout or "{}")


def _subagent_stop(**extra: str) -> dict:
    return {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "trade", **extra}


def test_payload_answer_wins_over_parallel_agent_in_transcript(tmp_path: Path) -> None:
    """A short message of a parallel agent is the last line, but trade's answer is complete."""
    entries = [_tagged(COMPLETE, "a1"), _tagged("done", "a2")]
    assert _gate(tmp_path, _subagent_stop(last_assistant_message=COMPLETE), entries) == {}


def test_short_payload_answer_is_blocked_even_if_transcript_is_complete(tmp_path: Path) -> None:
    entries = [_tagged("done", "a1"), _tagged(COMPLETE, "a2")]
    decision = _gate(tmp_path, _subagent_stop(last_assistant_message="done"), entries)
    assert decision.get("decision") == "block"


def test_camelcase_response_field_is_read(tmp_path: Path) -> None:
    payload = {"hookEventName": "subagentStop", "agentId": "a1", "agentType": "trade", "response": "done"}
    assert _gate(tmp_path, payload, [_tagged(COMPLETE, "a2")]).get("decision") == "block"


def test_transcript_fallback_keeps_only_the_same_agent(tmp_path: Path) -> None:
    """Without an answer in the payload, the messages of other agents are ignored."""
    entries = [_tagged(COMPLETE, "a1"), _tagged("done", "a2")]
    assert _gate(tmp_path, _subagent_stop(), entries) == {}


def test_top_level_agent_stop_is_allowed(tmp_path: Path) -> None:
    assert _gate(tmp_path, {"hook_event_name": "Stop"}, [_message("done")]) == {}


def test_agent_outside_the_gated_list_is_allowed(tmp_path: Path) -> None:
    """Built-in agents (explore, task) and other bundles are never gated."""
    payload = _subagent_stop(agent_type="explore", agent_name="explore", last_assistant_message="done")
    assert _gate(tmp_path, payload, [], "--agents=trade,coder") == {}


def test_gated_agent_name_matches_in_any_spelling(tmp_path: Path) -> None:
    payload = _subagent_stop(agent_type="Coder_Planner", last_assistant_message="done")
    assert _gate(tmp_path, payload, [], "--agents=coder-planner").get("decision") == "block"
