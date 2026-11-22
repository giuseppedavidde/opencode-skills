#!/usr/bin/env python3
"""SubagentStart hook: give each opencode subagent the response contract.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

The command lists the gated agents and the repository root:

    agent_bootstrap.py --agents=a,b,c --repo=/abs/path

The hook emits `hookSpecificOutput.additionalContext` with three parts: the
response contract, one short snippet for the agent, and the path of a saved
plan when one exists. The text is capped at 1500 characters.

One injection per subagent invocation per 60 seconds. The dedupe key is the
invocation id (`agent_id`, fallback `agentId`, then `session_id`) plus the
normalized agent name, so two parallel subagents of one type each get the
contract. Duplicate registrations of one start share `agent_id`. The marker
lives in `<state>/bootstrap/`. The state folder is `HOOK_STATE_DIR` when set, else
`$XDG_CACHE_HOME/opencode-vscode-hooks` (default `~/.cache`).

Fail-open: any error returns `{}` and never blocks the subagent.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

MAX_CONTEXT_CHARS = 1500
DEDUPE_SECONDS = 60

CONTRACT = (
    "## Contratto di risposta\n"
    "1. Chiudi la risposta con `## VERIFICA`.\n"
    "2. Scrivi 4 campi: confidenza (0-100), evidenza, non_verificato, escalation_consigliata.\n"
    "3. Non inviare solo il footer.\n"
    '4. Passa il lavoro con una riga: `## DELEGA {"agente":"coder","compito":"..."}`.'
)

SNIPPETS: dict[str, str] = {
    "coder": (
        "[coder] Usa un virtualenv. Non usare il pip di sistema.\n"
        "Riusa /tmp/opencode/.venv.\n"
        "Esegui pylint prima di proporre codice Python."
    ),
    "trade": (
        "[trade] Registro: {repo}/trades/positions-ledger.md.\n"
        "Riusa ~/.local/share/opencode/trading-mcp-venv.\n"
        "Aggiungi ogni raccomandazione al journal."
    ),
    "pdf-reader": (
        "[pdf-reader] Usa pdftotext prima.\n"
        "Usa OCR solo quando il testo è vuoto."
    ),
    "graphify-helper": (
        "[graphify-helper] Se esiste graphify-out/graph.json, preferisci `graphify query`."
    ),
    "oegk-health": (
        "[oegk-health] Usa importi EUR esatti e i nomi ufficiali delle tariffe. Cita la fonte."
    ),
}

PLANNER_SNIPPET = (
    "[{agent}] Scrivi il piano in {target}/plan-<slug>.md.\n"
    "Rispondi con il percorso del piano."
)


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


def normalize_agent(name: str) -> str:
    """Normalize an agent name for comparison (`Coder_Planner` == `coder-planner`)."""
    return name.strip().lower().replace("_", "-")


def cli_value(argv: list[str], flag: str) -> str:
    """Return the value of `--flag=value` or `--flag value`, else an empty string."""
    for index, arg in enumerate(argv):
        if arg == flag and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return ""


def cli_agents(argv: list[str]) -> set[str]:
    """Return the agent names from `--agents a,b,c` (empty set = no agent)."""
    return {normalize_agent(item) for item in cli_value(argv, "--agents").split(",") if item.strip()}


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


def session_id(payload: dict) -> str:
    """Return the session id of the payload."""
    return payload_value(payload, "session_id", "sessionId") or "default"


def session_state_root() -> Path:
    """Return the folder where the runtime keeps the per-session state."""
    override = os.environ.get("COPILOT_SESSION_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".copilot" / "session-state"


def newest_plan(session: str) -> Path | None:
    """Return the newest `plan-*.md` of the session, if any."""
    base = session_state_root() / session
    try:
        if not base.is_dir():
            return None
        plans = sorted(base.glob("plan-*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        return None
    return plans[0] if plans else None


def snippet_for(agent: str, repo: str, session: str) -> str:
    """Return the snippet for `agent` (the last two planner lines include the plan path)."""
    if agent in ("coder-planner", "vscode-ext-planner"):
        target = session_state_root() / session
        return PLANNER_SNIPPET.format(agent=agent, target=target)
    snippet = SNIPPETS.get(agent)
    if snippet is None:
        return ""
    return snippet.format(repo=repo.rstrip("/") or str(Path.cwd()))


def build_context(agent: str, repo: str, session: str) -> str:
    """Return the contract, the snippet of the agent and the plan hint."""
    lines = [CONTRACT]
    snippet = snippet_for(agent, repo, session)
    if snippet:
        lines.append(snippet)
    if agent == "coder":
        plan = newest_plan(session)
        if plan is not None:
            lines.append(f"Piano: {plan}. Leggilo prima di agire.")
    return "\n\n".join(lines)[:MAX_CONTEXT_CHARS]


def dedupe_seen(invocation: str, agent: str) -> bool:
    """True when this (invocation, agent) pair already got a snippet within 60 s."""
    marker = state_dir() / "bootstrap" / f"{safe_name(invocation)}__{safe_name(agent)}.seen"
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < DEDUPE_SECONDS:
            return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass
    return False


def main(argv: list[str] | None = None) -> int:
    """Emit the contract and the snippet for one gated subagent."""
    argv = sys.argv[1:] if argv is None else argv
    payload = read_payload()
    agent = normalize_agent(
        payload_value(payload, "agent_type", "agentType", "agent_name", "agentName")
    )
    if not agent or agent not in cli_agents(argv):
        print("{}")
        return 0

    session = session_id(payload)
    invocation = payload_value(payload, "agent_id", "agentId") or session
    if dedupe_seen(invocation, agent):
        print("{}")
        return 0

    repo = cli_value(argv, "--repo")
    text = build_context(agent, repo, session)
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}},
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
