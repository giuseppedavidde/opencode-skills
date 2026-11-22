#!/usr/bin/env python3
"""Per-agent PreToolUse hook: keep Python installs inside a virtualenv.

opencode-skills: managed file. install-vscode.py copies it; edit vscode/hooks/.

The generated `trade` and `coder` agents run this script from their own
frontmatter:

    agent_guard.py --agent=trade

The hook checks `execute`, `bash`, `shell` and `runInTerminal`. When the
command installs a package with the system pip and names no virtualenv, the
hook denies the call and names the venv to use.

Fail-open: any error returns `{}` and never blocks a tool.
"""

from __future__ import annotations

import json
import re
import sys

SHELL_TOOLS = {"execute", "bash", "shell", "runInTerminal"}
SYSTEM_PIP_RE = re.compile(
    r"\bsudo\s+pip3?\b"
    r"|\bpip3?\s+install\b"
    r"|\bpython3?\s+-m\s+pip\s+install\b",
    re.IGNORECASE,
)
VENV_RE = re.compile(
    r"/bin/pip\b"
    r"|/bin/activate\b"
    r"|VIRTUAL_ENV"
    r"|/venv/"
    r"|trading-mcp-venv",
)

REASONS = {
    "trade": (
        "Usa il virtualenv ~/.local/share/opencode/trading-mcp-venv. "
        "Non usare il pip di sistema.\n"
        "Esempio: ~/.local/share/opencode/trading-mcp-venv/bin/pip install <pkg>"
    ),
    "coder": (
        "Usa un virtualenv. Riusa /tmp/opencode/.venv o un virtualenv del progetto. "
        "Non usare il pip di sistema.\n"
        "Esempio: /tmp/opencode/.venv/bin/pip install <pkg>"
    ),
}


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


def cli_value(argv: list[str], flag: str) -> str:
    """Return the value of `--flag=value` or `--flag value`, else an empty string."""
    for index, arg in enumerate(argv):
        if arg == flag and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return ""


def tool_input(payload: dict) -> dict:
    """Return the tool input mapping of the payload."""
    value = payload.get("tool_input")
    if not isinstance(value, dict):
        value = payload.get("toolInput")
    return value if isinstance(value, dict) else {}


def command_of(payload: dict) -> str:
    """Return the shell command of the tool call."""
    args = tool_input(payload)
    for key in ("command", "commandLine", "cmd", "script"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def deny(reason: str) -> None:
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


def main(argv: list[str] | None = None) -> int:
    """Deny a system pip install that names no virtualenv."""
    argv = sys.argv[1:] if argv is None else argv
    agent = (cli_value(argv, "--agent") or "coder").strip().lower()
    payload = read_payload()
    if payload_value(payload, "tool_name", "toolName") not in SHELL_TOOLS:
        print("{}")
        return 0

    command = command_of(payload)
    if not command or not SYSTEM_PIP_RE.search(command) or VENV_RE.search(command):
        print("{}")
        return 0

    deny(REASONS.get(agent, REASONS["coder"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("{}")
        sys.exit(0)
