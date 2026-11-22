"""Tests for the VS Code agent hooks: bootstrap, digest, routing, guard, graphify.

Every test runs the standalone script with a temporary `HOOK_STATE_DIR`, so no
state ever reaches `~/.cache`.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
PYTHON = sys.executable
CALL_IDS = itertools.count(1)


def run(
    script: Path | str,
    payload: dict,
    *args: str,
    state: Path,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """Run one hook script with the payload on stdin and return its JSON answer."""
    path = script if isinstance(script, Path) else HOOKS / script
    env = {"HOOK_STATE_DIR": str(state), "PATH": "/usr/bin:/bin"}
    env.update(extra_env or {})
    result = subprocess.run(
        [PYTHON, str(path), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout or "{}")


def context_of(output: dict) -> str:
    """Return the additionalContext of a hook answer."""
    return str((output.get("hookSpecificOutput") or {}).get("additionalContext", ""))


def start_payload(agent: str, session: str = "s1") -> dict:
    """Return a SubagentStart payload."""
    return {
        "hook_event_name": "SubagentStart",
        "agent_id": "a1",
        "agent_type": agent,
        "session_id": session,
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp",
    }


# ── agent_bootstrap.py (SubagentStart) ─────────────────────────────────────


def test_bootstrap_trade_snippet(tmp_path: Path) -> None:
    out = run("agent_bootstrap.py", start_payload("trade"), "--agents=trade,coder", "--repo=/repo", state=tmp_path)
    text = context_of(out)
    assert "## VERIFICA" in text
    assert "positions-ledger.md" in text


def test_bootstrap_coder_snippet(tmp_path: Path) -> None:
    out = run("agent_bootstrap.py", start_payload("coder"), "--agents=trade,coder", "--repo=/repo", state=tmp_path)
    text = context_of(out)
    assert "## VERIFICA" in text
    assert "/tmp/opencode/.venv" in text


def test_bootstrap_injects_a_saved_plan(tmp_path: Path) -> None:
    session_state = tmp_path / "session-state"
    plan = session_state / "s1" / "plan-refactor.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# plan\n", encoding="utf-8")
    out = run(
        "agent_bootstrap.py",
        start_payload("coder"),
        "--agents=coder",
        "--repo=/repo",
        state=tmp_path / "state",
        extra_env={"COPILOT_SESSION_STATE_DIR": str(session_state)},
    )
    text = context_of(out)
    assert str(plan) in text
    assert "Leggilo prima di agire" in text


def test_bootstrap_skips_an_agent_outside_the_list(tmp_path: Path) -> None:
    out = run("agent_bootstrap.py", start_payload("trade"), "--agents=coder", "--repo=/repo", state=tmp_path)
    assert out == {}


def test_bootstrap_dedupes_within_one_minute(tmp_path: Path) -> None:
    first = run("agent_bootstrap.py", start_payload("trade"), "--agents=trade", "--repo=/repo", state=tmp_path)
    second = run("agent_bootstrap.py", start_payload("trade"), "--agents=trade", "--repo=/repo", state=tmp_path)
    assert "## VERIFICA" in context_of(first)
    assert second == {}


def test_bootstrap_gives_parallel_subagents_of_one_type_the_contract(tmp_path: Path) -> None:
    """Two invocations of one agent type share no marker: both get the contract."""
    first = start_payload("trade")
    first["agent_id"] = "a1"
    second = start_payload("trade")
    second["agent_id"] = "a2"
    out1 = run("agent_bootstrap.py", first, "--agents=trade", "--repo=/repo", state=tmp_path)
    out2 = run("agent_bootstrap.py", second, "--agents=trade", "--repo=/repo", state=tmp_path)
    assert "## VERIFICA" in context_of(out1)
    assert "## VERIFICA" in context_of(out2)


# ── handoff_digest.py (PostToolUse) ────────────────────────────────────────

ANSWER = (
    "## VERIFICA\n"
    "- confidenza: 58\n"
    "- evidenza: pytest\n"
    "- non_verificato: test lenti\n"
    "- escalation_consigliata: no\n\n"
    '## DELEGA\n{"agente":"coder","compito":"fix"}'
)


def test_digest_parses_confidence_and_delega(tmp_path: Path) -> None:
    payload = {"tool_name": "agent", "tool_use_id": "u1", "tool_response": ANSWER}
    line = context_of(run("handoff_digest.py", payload, state=tmp_path))
    assert "confidenza=58" in line
    assert 'DELEGA={"agente":"coder","compito":"fix"}' in line


def test_digest_ignores_other_tools(tmp_path: Path) -> None:
    payload = {"tool_name": "read", "tool_use_id": "u2", "tool_response": ANSWER}
    assert run("handoff_digest.py", payload, state=tmp_path) == {}


def test_digest_dedupes_by_tool_use_id(tmp_path: Path) -> None:
    payload = {"tool_name": "agent", "tool_use_id": "u3", "tool_response": ANSWER}
    assert "confidenza=58" in context_of(run("handoff_digest.py", payload, state=tmp_path))
    assert run("handoff_digest.py", payload, state=tmp_path) == {}


# ── routing_guard.py (UserPromptSubmit + PreToolUse) ───────────────────────


def prompt(payload: dict, state: Path) -> dict:
    """Run the prompt event of the routing guard."""
    return run("routing_guard.py", payload, "--event=prompt", state=state)


def tool(payload: dict, state: Path) -> dict:
    """Run the tool event of the routing guard."""
    return run("routing_guard.py", payload, "--event=tool", state=state)


def spawn(agent: str, session: str) -> dict:
    """Return a PreToolUse agent-spawn payload with a distinct tool call id."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "agent",
        "tool_use_id": f"call-{next(CALL_IDS)}",
        "tool_input": {"agent_type": agent},
        "session_id": session,
    }


def test_routing_pdf_denies_the_wrong_agent(tmp_path: Path) -> None:
    prompt({"prompt": "riassumi il contratto.pdf", "session_id": "s1"}, tmp_path)
    denied = tool(spawn("coder", "s1"), tmp_path)
    assert denied.get("permissionDecision") == "deny"
    assert "pdf-reader" in denied.get("permissionDecisionReason", "")
    assert tool(spawn("pdf-reader", "s1"), tmp_path) == {}


def test_routing_coder_prompt_allows_coder_and_denies_trade(tmp_path: Path) -> None:
    prompt({"prompt": "implementa una funzione python nel modulo app.py", "session_id": "s2"}, tmp_path)
    assert tool(spawn("coder", "s2"), tmp_path) == {}
    denied = tool(spawn("trade", "s2"), tmp_path)
    assert denied.get("permissionDecision") == "deny"
    assert "coder" in denied.get("permissionDecisionReason", "")


def test_routing_without_state_allows(tmp_path: Path) -> None:
    assert tool(spawn("coder", "absent"), tmp_path) == {}


def test_routing_caps_denials_at_two(tmp_path: Path) -> None:
    prompt({"prompt": "leggi la fattura", "session_id": "s3"}, tmp_path)
    first = tool(spawn("trade", "s3"), tmp_path)
    second = tool(spawn("trade", "s3"), tmp_path)
    third = tool(spawn("trade", "s3"), tmp_path)
    assert first.get("permissionDecision") == "deny"
    assert second.get("permissionDecision") == "deny"
    assert third == {}


def test_routing_new_prompt_resets_the_denial_cap(tmp_path: Path) -> None:
    """The cap covers one user request; the next prompt gives a fresh cap."""
    prompt({"prompt": "leggi la fattura", "session_id": "s8"}, tmp_path)
    assert tool(spawn("trade", "s8"), tmp_path).get("permissionDecision") == "deny"
    assert tool(spawn("trade", "s8"), tmp_path).get("permissionDecision") == "deny"
    assert tool(spawn("trade", "s8"), tmp_path) == {}

    prompt({"prompt": "leggi la fattura", "session_id": "s8"}, tmp_path)
    again = tool(spawn("trade", "s8"), tmp_path)
    assert again.get("permissionDecision") == "deny"
    assert "pdf-reader" in again.get("permissionDecisionReason", "")


def test_routing_ignores_a_technical_acronym(tmp_path: Path) -> None:
    """`JSON` is not a ticker, so the prompt has no deterministic category."""
    assert prompt({"prompt": "analizza il file JSON", "session_id": "s4"}, tmp_path) == {}


def test_routing_classifies_a_bare_ticker_as_trade(tmp_path: Path) -> None:
    out = prompt({"prompt": "analizza LHX", "session_id": "s5"}, tmp_path)
    assert "TRADE" in context_of(out)


def chain(agent: str, subtask: str, session: str) -> dict:
    """Return a PreToolUse spawn payload that carries the subtask prompt."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "agent",
        "tool_use_id": f"call-{next(CALL_IDS)}",
        "tool_input": {"agent_type": agent, "prompt": subtask},
        "session_id": session,
    }


def test_routing_allows_a_coding_subtask_of_a_trade_parent(tmp_path: Path) -> None:
    prompt({"prompt": "analizza LHX", "session_id": "s6"}, tmp_path)
    assert tool(chain("coder", "scrivi uno script python", "s6"), tmp_path) == {}


def test_routing_denies_a_trade_subtask_repeated_by_coder(tmp_path: Path) -> None:
    prompt({"prompt": "analizza LHX", "session_id": "s7"}, tmp_path)
    denied = tool(chain("coder", "valuta il titolo", "s7"), tmp_path)
    assert denied.get("permissionDecision") == "deny"
    assert "trade" in denied.get("permissionDecisionReason", "")


def test_routing_prompt_emits_the_line_once_per_prompt(tmp_path: Path) -> None:
    """A runtime that runs one prompt event twice adds one line, not two."""
    payload = {"prompt": "leggi la fattura", "session_id": "p1"}
    first = prompt(payload, tmp_path)
    second = prompt(payload, tmp_path)
    assert "PDF" in context_of(first)
    assert second == {}

    fresh = prompt({"prompt": "analizza LHX", "session_id": "p1"}, tmp_path)
    assert "TRADE" in context_of(fresh)


def test_routing_tool_counts_one_denial_per_tool_use_id(tmp_path: Path) -> None:
    """A repeated invocation of one tool call denies once and counts one denial."""
    prompt({"prompt": "leggi la fattura", "session_id": "p2"}, tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "agent",
        "tool_use_id": "dup-1",
        "tool_input": {"agent_type": "trade"},
        "session_id": "p2",
    }
    first = tool(payload, tmp_path)
    second = tool(payload, tmp_path)
    assert first.get("permissionDecision") == "deny"
    assert second == {}
    counter = (tmp_path / "routing" / "p2.denials").read_text(encoding="utf-8").strip()
    assert counter == "1"


# ── agent_guard.py (per-agent PreToolUse) ─────────────────────────────────


def test_guard_denies_a_system_pip_install(tmp_path: Path) -> None:
    payload = {"tool_name": "execute", "tool_input": {"command": "pip install requests"}}
    out = run("agent_guard.py", payload, "--agent=coder", state=tmp_path)
    assert out.get("permissionDecision") == "deny"
    assert "venv" in out.get("permissionDecisionReason", "")


def test_guard_allows_an_install_inside_a_venv(tmp_path: Path) -> None:
    payload = {"tool_name": "execute", "tool_input": {"command": "/tmp/opencode/.venv/bin/pip install requests"}}
    assert run("agent_guard.py", payload, "--agent=coder", state=tmp_path) == {}


def test_guard_ignores_other_tools(tmp_path: Path) -> None:
    payload = {"tool_name": "read", "tool_input": {"command": "pip install requests"}}
    assert run("agent_guard.py", payload, "--agent=coder", state=tmp_path) == {}


# ── graphify_reminder.py (SessionStart) ───────────────────────────────────


def graph_workspace(root: Path) -> Path:
    """Create a workspace with a graphify graph and return it."""
    (root / "graphify-out").mkdir(parents=True)
    (root / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    return root


def test_graphify_reminds_once_per_session(tmp_path: Path) -> None:
    workspace = graph_workspace(tmp_path / "ws")
    state = tmp_path / "state"
    payload = {"hook_event_name": "SessionStart", "session_id": "g1", "cwd": str(workspace)}
    first = run("graphify_reminder.py", payload, state=state)
    assert "graphify" in context_of(first).lower()
    assert run("graphify_reminder.py", payload, state=state) == {}


def test_graphify_reports_manifest_drift(tmp_path: Path) -> None:
    workspace = graph_workspace(tmp_path / "ws")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    script = hooks / "graphify_reminder.py"
    shutil.copy2(HOOKS / "graphify_reminder.py", script)
    (hooks / ".manifest.json").write_text(
        json.dumps({"version": 1, "hooks": {"graphify_reminder.py": "0" * 64}}), encoding="utf-8"
    )
    payload = {"hook_event_name": "SessionStart", "session_id": "g2", "cwd": str(workspace)}
    out = run(script, payload, state=tmp_path / "state")
    assert "differiscono dal manifest" in context_of(out)


def test_graphify_reports_drift_without_a_graph(tmp_path: Path) -> None:
    """A project without graphify-out must still report the installed-file drift."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    script = hooks / "graphify_reminder.py"
    shutil.copy2(HOOKS / "graphify_reminder.py", script)
    (hooks / ".manifest.json").write_text(
        json.dumps({"version": 1, "hooks": {"graphify_reminder.py": "0" * 64}}), encoding="utf-8"
    )
    payload = {"hook_event_name": "SessionStart", "session_id": "g3", "cwd": str(workspace)}
    text = context_of(run(script, payload, state=tmp_path / "state"))
    assert "differiscono dal manifest" in text
    assert "graphify-out" not in text


# ── routing_guard.py: deterministic classifier regression ─────────────────

ROUTING_GUARD = HOOKS / "routing_guard.py"
GOLDEN_SET = HOOKS.parent.parent / "routing-eval" / "data" / "golden_set.json"
GOLDEN_LABELS = {"BOOK_TO_SKILL": "BOOK", "SKILL_UPDATER": "SKILL_UPDATE"}


def load_routing_guard():
    """Import vscode/hooks/routing_guard.py as a module."""
    spec = importlib.util.spec_from_file_location("routing_guard", ROUTING_GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classifier_never_returns_a_wrong_category() -> None:
    """No golden case may return a category different from its expected category."""
    guard = load_routing_guard()
    cases = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    wrong = []
    for case in cases:
        expected = GOLDEN_LABELS.get(case["expected"], case["expected"])
        if expected == "SIMPLE":
            assert guard.classify(case["text"])[0] is None, case["text"]
            continue
        got = guard.classify(case["text"])[0]
        if got is not None and got != expected:
            wrong.append((case["id"], case["text"], expected, got))
    assert not wrong


def test_classifier_direct_cases() -> None:
    """The classifier routes PDF, ÖGK and VS Code extension prompts to their specialists."""
    guard = load_routing_guard()
    assert guard.classify("riassumi questo contratto.pdf")[0] == "PDF"
    assert guard.classify("quanto rimborsa la ÖGK per una MRT?")[0] == "OEGK"
    assert guard.classify("crea un'estensione VS Code con un comando")[0] == "VSCODE_EXT"
