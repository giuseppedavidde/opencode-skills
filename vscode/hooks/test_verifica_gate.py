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
