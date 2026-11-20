#!/usr/bin/env python3
"""Preselect the workflow agent and model in VS Code startup state.

VS Code has no setting for the default custom agent. The agent picker keeps the
last choice in application storage, keyed by session scheme:

    workbench.agentsession.agentHostAgentPicker.<scheme>.selectedAgentUri
    chat.currentLanguageModel.panel.<scheme>

This script writes those keys, so a fresh VS Code window starts on the agent and
model declared in config/opencode.json (`default_agent`, `model`).

Run it while VS Code is closed. VS Code caches storage in memory and would
overwrite the values on exit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_SRC = REPO_ROOT / "config"
MODELS_FILE = REPO_ROOT / "vscode" / "models.json"
STATE_DB = Path.home() / ".config" / "Code" / "User" / "globalStorage" / "state.vscdb"
DEFAULT_SCHEME = "agent-host-copilotcli"


def provider_vendor() -> str:
    """Return the VS Code vendor id of the OpenCode Go models (vscode/models.json)."""
    try:
        data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    prefix = data.get("provider_prefix") if isinstance(data, dict) else None
    return str(prefix or "opencodego")


def opencode_config() -> dict:
    """Return the parsed opencode workflow configuration."""
    path = CONFIG_SRC / "opencode.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def model_id(raw: str) -> str:
    """Return the bare VS Code model id for an opencode model reference."""
    return raw.split("#", 1)[0].strip().rsplit("/", 1)[-1]


def vscode_is_running() -> bool:
    """Return True when a VS Code process (any common install) owns the storage database."""
    names = {"code", "code-insiders", "code-oss", "codium"}
    markers = (
        "/usr/share/code",
        "/usr/lib/code",
        "/opt/visual-studio-code",
        "/usr/share/code-insiders",
        "/snap/code",
        "/var/lib/flatpak/app/com.visualstudio.code",
    )
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            exe = Path(entry / "exe").resolve()
        except OSError:
            continue
        if exe.name in names or any(str(exe).startswith(marker) for marker in markers):
            return True
    return False


def agent_file_for(agent: str, workspace: Path) -> Path | None:
    """Return the generated agent file: user scope (~/.copilot) first, then the workspace."""
    for candidate in (
        Path.home() / ".copilot" / "agents" / f"{agent}.agent.md",
        workspace / ".github" / "agents" / f"{agent}.agent.md",
    ):
        if candidate.is_file():
            return candidate
    return None


def prune_backups(state_db: Path, keep: int = 3) -> None:
    """Keep only the newest `keep` database backups that this script made."""
    backups = sorted(state_db.parent.glob(f"{state_db.name}.bak-preselect-*"))
    for old in backups[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def read_keys(db: Path, keys: list[str]) -> dict[str, str]:
    """Read existing values for the given keys."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        found = {}
        for key in keys:
            row = cur.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
            if row is not None:
                value = row[0]
                found[key] = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
        return found
    finally:
        con.close()


def write_keys(db: Path, values: dict[str, str], overwrite: set[str]) -> list[str]:
    """Write the given keys, skipping values already equal."""
    con = sqlite3.connect(str(db), timeout=10)
    actions: list[str] = []
    try:
        cur = con.cursor()
        for key, value in values.items():
            row = cur.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
            current = None
            if row is not None:
                current = row[0].decode("utf-8", "replace") if isinstance(row[0], bytes) else str(row[0])
            if current == value:
                actions.append(f"OK   {key} = {value}")
                continue
            if current is not None and key not in overwrite:
                actions.append(f"KEEP {key} = {current}")
                continue
            cur.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            actions.append(f"SET  {key} = {value}")
        con.commit()
    finally:
        con.close()
    return actions


def main() -> int:
    """Run the preselect step."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT.parent)
    parser.add_argument("--state-db", type=Path, default=STATE_DB, help="VS Code state database")
    parser.add_argument("--scheme", default=DEFAULT_SCHEME)
    parser.add_argument("--agent", default=None, help="Agent name (default: config default_agent)")
    parser.add_argument("--model", default=None, help="Model id (default: config model)")
    parser.add_argument("--force", action="store_true", help="Run while VS Code is open")
    parser.add_argument(
        "--keep-user-choice",
        action="store_true",
        help="Keep a stored agent/model instead of enforcing the workflow default",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    state_db = args.state_db.expanduser().resolve()

    config = opencode_config()
    agent = args.agent or str(config.get("default_agent") or "router")
    model = model_id(args.model or str(config.get("model") or ""))
    workspace = args.workspace.expanduser().resolve()
    agent_file = agent_file_for(agent, workspace)

    if agent_file is None:
        print(f"preselect: no generated agent file for {agent!r}; run ./install.sh first", file=sys.stderr)
        return 1
    if not model:
        print("preselect: no model in config/opencode.json", file=sys.stderr)
        return 1
    if not state_db.is_file():
        print(f"preselect: missing VS Code storage {state_db}", file=sys.stderr)
        return 1

    values = {
        f"workbench.agentsession.agentHostAgentPicker.{args.scheme}.selectedAgentUri":
            agent_file.as_uri(),
    }
    model_key = f"chat.currentLanguageModel.panel.{args.scheme}"
    values[model_key] = f"{args.scheme}:{provider_vendor()}/{model}"

    if args.dry_run:
        print(f"Target: {state_db}")
        for key, value in values.items():
            print(f"DRY  {key} = {value}")
        return 0

    if vscode_is_running() and not args.force:
        print("preselect: VS Code is running; it would overwrite these values on exit.")
        print("preselect: close VS Code or pass --force.")
        return 2

    backup = state_db.with_name(f"{state_db.name}.bak-preselect-{time.time_ns()}")
    shutil.copy2(state_db, backup)
    prune_backups(state_db)
    print(f"Backup: {backup}")

    overwrite = set() if args.keep_user_choice else set(values)
    actions = write_keys(state_db, values, overwrite)
    for action in actions:
        print(action)

    if args.keep_user_choice:
        print("preselect: --keep-user-choice, stored selections kept when present")

    return 0


if __name__ == "__main__":
    sys.exit(main())
