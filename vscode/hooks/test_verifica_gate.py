"""Regression tests for the VS Code SubagentStop verifica gate.

The gate must never turn a complete answer into a footer-only reply. A long
answer without the VERIFICA block is allowed (and logged); only short answers
are blocked, and the block reason asks for the COMPLETE answer again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "verifica_gate.py"
LOW_CONFIDENCE_TTL_SECONDS = 600

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
        env={"HOOK_STATE_DIR": str(tmp_path), "GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
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
        env={"HOOK_STATE_DIR": str(tmp_path), "GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
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
        env={"HOOK_STATE_DIR": str(tmp_path), "GATE_LOG_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
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


# ── Dedupe and confidence gate ─────────────────────────────────────────────


def _footer(confidence: int) -> str:
    return (
        "## VERIFICA\n"
        f"- confidenza: {confidence}\n"
        "- evidenza: pytest\n"
        "- non_verificato: nulla\n"
        "- escalation_consigliata: no"
    )


def _audit_lines(tmp_path: Path) -> int:
    log = tmp_path / "gate_events.jsonl"
    if not log.is_file():
        return 0
    return len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()])


def test_duplicate_stop_writes_one_audit_line(tmp_path: Path) -> None:
    """The same answer is evaluated one time only; the repeat is a no-op."""
    payload = _subagent_stop(session_id="s1", last_assistant_message="A" * 900 + "\n\n" + _footer(90))
    entries = [_tagged("A" * 900 + "\n\n" + _footer(90), "a1")]
    assert _gate(tmp_path, payload, entries) == {}
    assert _gate(tmp_path, payload, entries) == {}
    assert _audit_lines(tmp_path) == 1


def test_low_confidence_blocks_one_time(tmp_path: Path) -> None:
    """Confidenza below 60 asks for one corrected answer, then passes."""
    low = "A" * 900 + "\n\n" + _footer(58)
    first = _gate(
        tmp_path,
        _subagent_stop(session_id="s1", last_assistant_message=low),
        [_tagged(low, "a1")],
    )
    assert first.get("decision") == "block"
    assert "60" in first.get("reason", "")

    second_text = "B" * 900 + "\n\n" + _footer(58)
    second = _gate(
        tmp_path,
        _subagent_stop(session_id="s1", last_assistant_message=second_text),
        [_tagged(second_text, "a1")],
    )
    assert second == {}


def test_low_confidence_block_carries_the_event_name(tmp_path: Path) -> None:
    """The block names its event, so the harness reads the hookSpecificOutput."""
    low = "A" * 900 + "\n\n" + _footer(58)
    decision = _gate(
        tmp_path,
        _subagent_stop(session_id="s1", last_assistant_message=low),
        [_tagged(low, "a1")],
    )
    assert decision.get("decision") == "block"
    assert (decision.get("hookSpecificOutput") or {}).get("hookEventName") == "SubagentStop"


def test_high_confidence_is_allowed_and_logged(tmp_path: Path) -> None:
    """Confidenza 90 passes and writes the ok case."""
    text = "A" * 900 + "\n\n" + _footer(90)
    assert _gate(tmp_path, _subagent_stop(session_id="s1", last_assistant_message=text), [_tagged(text, "a1")]) == {}
    log = (tmp_path / "gate_events.jsonl").read_text(encoding="utf-8")
    assert '"case": "ok"' in log


def test_low_confidence_counter_expires_after_ttl(tmp_path: Path) -> None:
    """An old counter is unused, so a later low-confidence answer blocks again."""
    low = "A" * 900 + "\n\n" + _footer(58)
    first = _gate(tmp_path, _subagent_stop(session_id="s1", last_assistant_message=low), [_tagged(low, "a1")])
    assert first.get("decision") == "block"

    counter = tmp_path / "verifica_conf" / "s1__trade"
    assert counter.is_file()
    old = time.time() - LOW_CONFIDENCE_TTL_SECONDS - 60
    os.utime(counter, (old, old))

    later = "B" * 900 + "\n\n" + _footer(58)
    second = _gate(tmp_path, _subagent_stop(session_id="s1", last_assistant_message=later), [_tagged(later, "a1")])
    assert second.get("decision") == "block"
    assert "60" in second.get("reason", "")
