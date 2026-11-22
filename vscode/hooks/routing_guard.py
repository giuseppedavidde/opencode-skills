#!/usr/bin/env python3
"""Routing hook: classify a prompt and guard the agent spawn.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

Two events share this script:

- `--event=prompt` (`UserPromptSubmit`): classify the prompt, save the result
  in `<state>/routing/<session_id>.json`, and tell the model the deterministic
  category and the agent to use.
- `--event=tool` (`PreToolUse`): read the saved category. The allowed agents
  are the union of the parent category and the subtask prompt
  (`tool_input.prompt`). When the spawned agent is a known specialist outside
  that union, deny the call and name the correct agent. One user request gets
  at most 2 denials; `--event=prompt` resets the counter, so a later request
  gets a fresh cap. A repeat of one event within its TTL writes nothing extra.

The state folder is `HOOK_STATE_DIR` when set, else
`$XDG_CACHE_HOME/opencode-vscode-hooks` (default `~/.cache`).

Fail-open: any error returns `{}` and never blocks a tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

STATE_MAX_AGE_SECONDS = 600
MAX_DENIALS = 2
PROMPT_DEDUPE_SECONDS = 30
TOOL_DEDUPE_SECONDS = 120

SPAWN_TOOLS = {"agent", "Agent", "runSubagent", "task", "Task"}

ALLOWED: dict[str, tuple[str, ...]] = {
    "PDF": ("pdf-reader",),
    "OEGK": ("oegk-health",),
    "GRAPHIFY": ("graphify-helper",),
    "VSCODE_EXT": ("vscode-ext", "vscode-ext-planner"),
    "CODER": ("coder", "coder-planner"),
    "SKILL_UPDATE": ("skill-updater",),
    "BOOK": ("book-to-skill-agent",),
    "TRADE": ("trade",),
}
KNOWN_SPECIALISTS = {agent for agents in ALLOWED.values() for agent in agents}

PDF_COMPRESS_RE = re.compile(
    r"(?:comprimi|comprimere|riduci|ridurre|ottimizza|ottimizzare|alleggerisci)\b[\s\S]{0,40}?pdf"
    r"|pdf\b[\s\S]{0,40}?(?:comprimi|comprimere|riduci|ridurre|ottimizza|ottimizzare|alleggerisci)",
    re.IGNORECASE,
)
PDF_RE = re.compile(
    r"\.pdf\b|(?:contratto|polizza|rechnung|verbale|estratto conto|fattura)",
    re.IGNORECASE,
)
OEGK_RE = re.compile(
    r"(?:oegk|öGK|gesundheitskasse|krankenkasse|kassenleistung|wahlarzt|rezeptgebühr"
    r"|selbstbehalt|blutbefund|vorsorgeuntersuchung)",
    re.IGNORECASE,
)
GRAPHIFY_RE = re.compile(
    r"(?:graphify|grafo|knowledge graph|mappa del codice|god nodes|community detection)",
    re.IGNORECASE,
)
VSCODE_EXT_RE = re.compile(
    r"(?:vscode extension|estensione (?:per )?vs ?code|vsix|activationEvents|contributes)",
    re.IGNORECASE,
)
CODER_VERB_RE = re.compile(
    r"\b(?:implementa|implement|refactor|rifattorizza|modifica|fix|debug|scrivi|crea|aggiungi"
    r"|develop|build|write|create|add|modify|refactoring)\b",
    re.IGNORECASE,
)
CODER_OBJECT_RE = re.compile(
    r"(?:\b(?:script|modulo|module|funzione|function|classe|class|file|test|backtest|api|codice"
    r"|code|libreria|plugin|applicazione)\b|web app"
    r"|\.(?:py|ts|js|sh|go|rs|java|sql|json|ya?ml|toml)\b)",
    re.IGNORECASE,
)
SKILL_VERB_RE = re.compile(
    r"\b(?:aggiorna|aggiornare|update|sincronizza|sync|allinea)\b", re.IGNORECASE
)
SKILL_WORD_RE = re.compile(r"\bskill\b", re.IGNORECASE)
SKILL_TARGET_RE = re.compile(
    r"(?:skill|graphify|quant-mind|submodule|book-to-skill)", re.IGNORECASE
)
BOOK_RE = re.compile(r"book-to-skill", re.IGNORECASE)
BOOK_HINT_RE = re.compile(r"\b(?:libro|pdf|epub|documento)\b", re.IGNORECASE)
TRADE_STRONG_TICKER_RE = re.compile(r"\$\s?[A-Za-z]{1,5}\b")
TRADE_WEAK_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
TRADE_STOPLIST = frozenset(
    {
        "PDF", "API", "JSON", "YAML", "SQL", "HTML", "CSS", "TS", "JS", "OK", "README", "MCP",
        "LLM", "URL", "HTTP", "CSV", "SKILL", "VSIX", "TSX", "CLI", "SDK", "OS", "UI", "UX",
        "AI", "ID", "IV", "DTE", "VS", "DB", "GUI", "CPU", "GPU", "RAM", "SSD", "PNG", "JPG",
        "SVG", "XML", "TOML", "GIT", "PR", "CI", "CD", "MAIN", "THE", "AND", "NOT",
    }
)
TRADE_WORD_RE = re.compile(
    r"\b(?:opzioni?|options?|calls?|puts?|strike|delta|gamma|theta|vega|dte|roll"
    r"|hedg\w*|volatilit\w*|iv|portfolio|portafoglio|posizion\w*|mercato)\b",
    re.IGNORECASE,
)
TRADE_ACTION_RE = re.compile(
    r"\b(?:analizza|analisi|valuta|conviene|compro|vendo|strategia|scan|verdict|prezzo"
    r"|quotazione|andamento|roll|scadenza|aggiorna|macro|vix|dxy|fed|tassi|inflazione)\b",
    re.IGNORECASE,
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


def tool_input(payload: dict) -> dict:
    """Return the tool input mapping of the payload."""
    value = payload.get("tool_input")
    if not isinstance(value, dict):
        value = payload.get("toolInput")
    return value if isinstance(value, dict) else {}


def cli_value(argv: list[str], flag: str) -> str:
    """Return the value of `--flag=value` or `--flag value`, else an empty string."""
    for index, arg in enumerate(argv):
        if arg == flag and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return ""


def normalize_agent(name: str) -> str:
    """Normalize an agent name for comparison (`Coder_Planner` == `coder-planner`)."""
    return name.strip().lower().replace("_", "-")


def state_root() -> Path:
    """Return the hook state folder, never the home cache when HOOK_STATE_DIR is set."""
    override = os.environ.get("HOOK_STATE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "opencode-vscode-hooks"


def safe_name(value: str) -> str:
    """Return a file-system-safe name for a session id."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:120]
    return cleaned or "default"


def seen(key: str, folder: str, ttl: int) -> bool:
    """True when `key` already fired for `folder` within `ttl` seconds.

    A marker in `<state>/<folder>/<sha1(key)>` records the key. The first call
    creates or refreshes it and returns False; a repeat inside the TTL returns
    True. An OSError returns False, so the hook stays fail-open.
    """
    marker = state_root() / folder / hashlib.sha1(key.encode("utf-8")).hexdigest()
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < ttl:
            return True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        return False
    return False


def classify(text: str) -> tuple[str | None, str]:
    """Return (category, evidence) for one prompt; (None, "") when nothing matches."""
    if not text.strip():
        return None, ""
    if PDF_COMPRESS_RE.search(text):
        return None, ""
    skill_verb = SKILL_VERB_RE.search(text)
    if skill_verb is not None and SKILL_TARGET_RE.search(text) is not None:
        return "SKILL_UPDATE", skill_verb.group(0)[:80]
    book = BOOK_RE.search(text)
    if book is not None:
        return "BOOK", book.group(0)[:80]
    if SKILL_WORD_RE.search(text) is not None:
        hint = BOOK_HINT_RE.search(text)
        if hint is not None:
            return "BOOK", hint.group(0)[:80]
    match = PDF_RE.search(text)
    if match is not None:
        return "PDF", match.group(0)[:80]
    match = OEGK_RE.search(text)
    if match is not None:
        return "OEGK", match.group(0)[:80]
    match = GRAPHIFY_RE.search(text)
    if match is not None:
        return "GRAPHIFY", match.group(0)[:80]
    match = VSCODE_EXT_RE.search(text)
    if match is not None:
        return "VSCODE_EXT", match.group(0)[:80]
    verb = CODER_VERB_RE.search(text)
    if verb is not None and CODER_OBJECT_RE.search(text) is not None:
        return "CODER", verb.group(0)[:80]
    ticker = trade_match(text)
    if ticker is not None:
        return "TRADE", ticker.group(0)[:80]
    return None, ""


def trade_match(text: str) -> re.Match[str] | None:
    """Return the trade evidence: a ticker with an action or a trade word, else an action with a word."""
    strong = TRADE_STRONG_TICKER_RE.search(text)
    weak = [m for m in TRADE_WEAK_TICKER_RE.finditer(text) if m.group(0) not in TRADE_STOPLIST]
    ticker = strong if strong is not None else (weak[0] if weak else None)
    action = TRADE_ACTION_RE.search(text)
    word = TRADE_WORD_RE.search(text)
    if ticker is not None and (action is not None or word is not None):
        return ticker
    if len(weak) >= 2:
        return weak[0]
    if action is not None and word is not None:
        return word
    return None


def target_agent(category: str) -> str:
    """Return the preferred agent name of a category."""
    return " o ".join(ALLOWED[category])


def emit_context(event: str, context: str) -> None:
    """Print an additionalContext answer in both harness shapes."""
    print(
        json.dumps(
            {
                "additionalContext": context,
                "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
            },
            ensure_ascii=False,
        )
    )


def state_file(session: dict) -> Path:
    """Return the routing state file of the session."""
    return state_root() / "routing" / f"{safe_name(session['id'])}.json"


def write_state(session: dict, category: str | None, evidence: str) -> None:
    """Save the classification of the session and ignore a write failure."""
    path = state_file(session)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"category": category, "evidence": evidence, "ts": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def read_state(session: dict) -> dict:
    """Return the saved classification of the session; {} when absent or old."""
    try:
        data = json.loads(state_file(session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        age = time.time() - float(data.get("ts", 0))
    except (TypeError, ValueError):
        return {}
    if age > STATE_MAX_AGE_SECONDS:
        return {}
    return data


def denial_count(session: dict) -> int:
    """Return how many denials the current user request already got."""
    path = state_root() / "routing" / f"{safe_name(session['id'])}.denials"
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def mark_denial(session: dict, count: int) -> None:
    """Save the new denial count; ignore a write failure."""
    path = state_root() / "routing" / f"{safe_name(session['id'])}.denials"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(count + 1), encoding="utf-8")
    except OSError:
        pass


def clear_denials(session: dict) -> None:
    """Reset the denial cap for a new user request; ignore a delete failure."""
    try:
        (state_root() / "routing" / f"{safe_name(session['id'])}.denials").unlink()
    except OSError:
        pass


def handle_prompt(payload: dict) -> int:
    """Classify the prompt and save the result. A new prompt resets the denial cap."""
    session = {"id": payload_value(payload, "session_id", "sessionId") or "default"}
    clear_denials(session)
    text = payload_value(payload, "prompt", "userPrompt", "message")
    category, evidence = classify(text)
    write_state(session, category, evidence)
    if category is None:
        print("{}")
        return 0
    if seen(f"{session['id']}\x00{text}", "routing_prompt", PROMPT_DEDUPE_SECONDS):
        print("{}")
        return 0
    emit_context("UserPromptSubmit", f"Categoria deterministica: {category}. Delega a {target_agent(category)}.")
    return 0


def emit_denial(reason: str) -> None:
    """Print a PreToolUse denial in the official and the legacy shape."""
    print(
        json.dumps(
            {
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
            },
            ensure_ascii=False,
        )
    )


def handle_tool(payload: dict) -> int:
    """Allow or deny one agent spawn, using the saved classification."""
    if payload_value(payload, "tool_name", "toolName") not in SPAWN_TOOLS:
        print("{}")
        return 0
    session = {"id": payload_value(payload, "session_id", "sessionId") or "default"}
    agent = normalize_agent(
        payload_value(tool_input(payload), "agent_type", "agentType", "agent_name", "agentName")
        or payload_value(payload, "agent_type", "agentType")
    )
    subtask = payload_value(tool_input(payload), "prompt")
    key = payload_value(payload, "tool_use_id", "toolUseId") or (
        f"{session['id']}\x00{agent}\x00{subtask}"
    )
    if seen(key, "routing_tool", TOOL_DEDUPE_SECONDS):
        print("{}")
        return 0

    state = read_state(session)
    category = state.get("category")
    if not isinstance(category, str) or category not in ALLOWED:
        print("{}")
        return 0

    if not agent or agent not in KNOWN_SPECIALISTS:
        print("{}")
        return 0

    allowed = set(ALLOWED[category])
    if subtask:
        subtask_category, _ = classify(subtask)
        if subtask_category in ALLOWED:
            allowed.update(ALLOWED[subtask_category])
    if agent in allowed:
        print("{}")
        return 0

    count = denial_count(session)
    if count >= MAX_DENIALS:
        print("{}")
        return 0
    mark_denial(session, count)

    evidence = str(state.get("evidence") or "")
    reason = (
        f"La richiesta è di categoria {category}. Delega a {target_agent(category)}. "
        f"Evidenza: \"{evidence}\"."
    )
    emit_denial(reason)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the prompt or the tool handler."""
    argv = sys.argv[1:] if argv is None else argv
    event = cli_value(argv, "--event")
    payload = read_payload()
    if event == "prompt":
        return handle_prompt(payload)
    if event == "tool":
        return handle_tool(payload)
    print("{}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
