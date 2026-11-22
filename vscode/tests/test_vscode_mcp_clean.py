"""Tests for scripts/vscode-mcp-clean.py: stale extension MCP entries in agent-host snapshots."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLEANER = REPO / "scripts" / "vscode-mcp-clean.py"
INSTALLER = REPO / "install-vscode.py"

SNAPSHOT_DIR = "agentPlugins/vscode-synced-customization-agent-host-copilotcli-1-standalone/abc"


def run_cleaner(user_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("XDG_", "VSCODE_"))}
    env["VSCODE_USER_DIR"] = str(user_dir)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(CLEANER), *args], env=env, capture_output=True, text=True, check=False
    )


def write_snapshot(user_dir: Path, servers: dict) -> Path:
    path = user_dir / SNAPSHOT_DIR / ".mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")
    return path


def test_stale_pylance_entry_is_removed_and_other_servers_stay(tmp_path: Path) -> None:
    pylance = {"type": "http", "url": "http://localhost:38961/stream", "headers": {"authorization": "x"}}
    headroom = {"type": "stdio", "command": "headroom", "args": ["mcp", "serve"]}
    path = write_snapshot(tmp_path, {"pylance mcp server": pylance, "headroom": headroom})

    result = run_cleaner(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    assert servers == {"headroom": headroom}
    assert "removed 1 entry" in result.stdout


def test_verify_reports_the_stale_entry_then_passes(tmp_path: Path) -> None:
    write_snapshot(tmp_path, {"pylance mcp server": {"type": "http", "url": "http://localhost:1/stream"}})
    drift = run_cleaner(tmp_path, "--verify")
    assert drift.returncode == 1
    assert "1 stale entry remains" in drift.stdout
    run_cleaner(tmp_path)
    clean = run_cleaner(tmp_path, "--verify")
    assert clean.returncode == 0, clean.stdout
    assert "No stale extension MCP entry" in clean.stdout


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    path = write_snapshot(tmp_path, {"pylance mcp server": {"type": "http", "url": "http://localhost:1/stream"}})
    before = path.read_text(encoding="utf-8")
    result = run_cleaner(tmp_path, "--dry-run")
    assert result.returncode == 0
    assert path.read_text(encoding="utf-8") == before
    assert "would remove 1 entry" in result.stdout


def test_another_server_name_is_kept_by_default(tmp_path: Path) -> None:
    mine = {"type": "http", "url": "http://localhost:9000/stream"}
    path = write_snapshot(tmp_path, {"my server": mine})
    run_cleaner(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"] == {"my server": mine}


def test_installer_verify_reports_the_stale_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    user_dir = home / ".config" / "Code" / "User"
    write_snapshot(
        user_dir,
        {"pylance mcp server": {"type": "http", "url": "http://localhost:1/stream"}},
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("XDG_", "VSCODE_")) and key != "REA_REPO"
    }
    env.update({"HOME": str(home), "VSCODE_USER_DIR": str(user_dir), "PYTHONDONTWRITEBYTECODE": "1"})
    result = subprocess.run(
        [sys.executable, str(INSTALLER), "--verify", "--target", "user"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "run scripts/vscode-mcp-clean.py" in result.stdout, result.stdout
