"""Focused tests for install-vscode.py: every test runs the installer with a temporary HOME."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / "install-vscode.py"


def run_installer(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("XDG_", "VSCODE_")) and key != "REA_REPO"
    }
    env.update({"HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"})
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args], env=env, capture_output=True, text=True, check=False
    )


def add_fake_mcp_runtimes(home: Path) -> None:
    """Create the paths that the MCP servers of config/opencode.json start."""
    for relative in (
        ".local/bin/browse",
        ".local/share/opencode/trading-mcp-venv/bin/trading-mcp",
        ".local/share/opencode/headroom-venv/bin/headroom",
        ".config/opencode/bin/rea-mcp.sh",
    ):
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
    (home / ".local" / "share" / "opencode" / "rea").mkdir(parents=True, exist_ok=True)


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    return yaml.safe_load(text[4:].split("\n---", 1)[0])


@pytest.fixture(scope="module")
def home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("home")
    add_fake_mcp_runtimes(root)
    result = run_installer(root, "--target", "user")
    assert result.returncode == 0, result.stdout + result.stderr
    return root


def test_agents_list_go_fallbacks_and_edit_tools(home: Path) -> None:
    trade = frontmatter(home / ".copilot" / "agents" / "trade.agent.md")
    assert trade["model"][0] == "opencodego/gemini-4-argon"
    assert len(trade["model"]) > 1
    assert all(entry.startswith("opencodego/") for entry in trade["model"])
    assert {"edit", "create", "apply_patch"} <= set(trade["tools"])


def test_bare_fallbacks_get_the_provider_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location("install_vscode", INSTALLER)
    installer = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "install_vscode", installer)
    spec.loader.exec_module(installer)
    mapping = {
        "provider_prefix": "opencodego",
        "fallbacks": {"glm-5.3": ["deepseek-v4-pro", "GPT-6 Luna (copilot)", "glm-5.3"]},
    }
    monkeypatch.setattr(installer, "load_model_map", lambda: mapping)
    assert installer.models_for("opencode-go/glm-5.3#high") == [
        "opencodego/glm-5.3",
        "opencodego/deepseek-v4-pro",
        "GPT-6 Luna (copilot)",
    ]


def test_planner_gets_only_the_trading_tool_that_it_may_use(home: Path) -> None:
    planner = frontmatter(home / ".copilot" / "agents" / "coder-planner.agent.md")
    assert "trading/*" not in planner["tools"]
    assert "trading/get_skill_knowledge" in planner["tools"]


def test_hook_files_use_the_copilot_format_and_gate_only_subagents(home: Path) -> None:
    gate = json.loads((home / ".copilot" / "hooks" / "verifica-gate.json").read_text(encoding="utf-8"))
    assert gate["version"] == 1
    gated = gate["hooks"]["SubagentStop"][0]["command"].split("--agents=", 1)[1].split(",")
    assert "trade" in gated and "router" not in gated
    graphify = json.loads((home / ".copilot" / "hooks" / "graphify-reminder.json").read_text(encoding="utf-8"))
    assert graphify["version"] == 1
    assert list(graphify["hooks"]) == ["SessionStart"]


def test_commands_become_slash_only_skills(home: Path) -> None:
    meta = frontmatter(home / ".copilot" / "skills" / "read-chunk" / "SKILL.md")
    assert meta["name"] == "read-chunk"
    assert meta["disable-model-invocation"] is True


def test_mcp_reads_v2_servers_and_resolves_env_placeholders(home: Path) -> None:
    servers = json.loads((home / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))["mcpServers"]
    assert {"browse", "headroom", "rea", "trading"} <= set(servers)
    assert servers["trading"]["command"].startswith(str(home))
    assert all("{env:" not in json.dumps(spec) for spec in servers.values())


def test_servers_without_runtime_are_left_out_and_removed(tmp_path: Path) -> None:
    config = tmp_path / ".copilot" / "mcp-config.json"
    config.parent.mkdir(parents=True)
    mine = {"type": "stdio", "command": "my-server", "args": []}
    config.write_text(json.dumps({"mcpServers": {"rea": {"type": "stdio", "command": "old"}, "mine": mine}}))
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "browse").write_text("#!/bin/sh\n", encoding="utf-8")
    result = run_installer(tmp_path, "--target", "user")
    servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"browse", "mine"}
    assert servers["mine"] == mine
    assert "./setup-trading-mcp.sh, then rerun ./install.sh" in result.stdout
    assert "./install.sh --with-rea" in result.stdout
    assert run_installer(tmp_path, "--verify", "--target", "user").returncode == 0


def test_trading_server_that_cannot_start_is_left_out(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    python = tmp_path / ".local/share/opencode/trading-mcp-venv/bin/python"
    python.write_text("#!/bin/sh\necho \"ModuleNotFoundError: No module named 'sklearn'\" >&2\nexit 1\n", encoding="utf-8")
    python.chmod(0o755)
    result = run_installer(tmp_path, "--target", "user")
    servers = json.loads((tmp_path / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "trading" not in servers and "browse" in servers
    assert "the server does not start (ModuleNotFoundError: No module named 'sklearn')" in result.stdout


def test_legacy_file_with_user_edits_goes_to_the_backup(tmp_path: Path) -> None:
    hooks = tmp_path / ".copilot" / "hooks"
    hooks.mkdir(parents=True)
    legacy = hooks / "verifica_gate.py"
    legacy.write_text("# opencode `## VERIFICA` contract\n# my edit\n", encoding="utf-8")
    run_installer(tmp_path, "--target", "user")
    assert legacy.read_text(encoding="utf-8") == (REPO / "vscode" / "hooks" / "verifica_gate.py").read_text(
        encoding="utf-8"
    )
    backups = list((tmp_path / ".cache" / "opencode-skills" / "backup").rglob("hooks/verifica_gate.py"))
    assert backups and "# my edit" in backups[0].read_text(encoding="utf-8")


def test_verify_reports_no_drift_after_install(home: Path) -> None:
    result = run_installer(home, "--verify", "--target", "user")
    assert result.returncode == 0, result.stdout


def test_files_of_the_user_are_kept_without_force(tmp_path: Path) -> None:
    agents = tmp_path / ".copilot" / "agents"
    agents.mkdir(parents=True)
    mine = agents / "trade.agent.md"
    mine.write_text("my own agent\n", encoding="utf-8")
    result = run_installer(tmp_path, "--target", "user")
    assert mine.read_text(encoding="utf-8") == "my own agent\n"
    assert "not generated by this installer" in result.stdout


def test_force_moves_a_real_skill_folder_to_the_backup(tmp_path: Path) -> None:
    skill = tmp_path / ".copilot" / "skills" / "python-venv"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("my skill\n", encoding="utf-8")
    run_installer(tmp_path, "--target", "user", "--force")
    assert skill.is_symlink()
    backups = list((tmp_path / ".cache" / "opencode-skills" / "backup").rglob("python-venv/SKILL.md"))
    assert backups and backups[0].read_text(encoding="utf-8") == "my skill\n"


def test_legacy_generated_prompts_are_removed_and_user_prompts_stay(tmp_path: Path) -> None:
    prompts = tmp_path / ".config" / "Code" / "User" / "prompts"
    prompts.mkdir(parents=True)
    legacy = prompts / "read-chunk.prompt.md"
    legacy.write_text("<!-- Generated by opencode-skills/install-vscode.py from command/read-chunk.md. -->\n")
    own = prompts / "token-stats.prompt.md"
    own.write_text("my prompt\n", encoding="utf-8")
    run_installer(tmp_path, "--target", "user")
    assert not legacy.exists()
    assert own.exists()


RUNTIME_SOURCES = (
    "config/opencode.json",
    "config/bin/*",
    "agents/*.md",
    "command/*.md",
    "vscode/systemd/*",
    "install.sh",
    "scripts/sync-vscode.sh",
)


@pytest.mark.parametrize("pattern", RUNTIME_SOURCES)
def test_runtime_sources_have_no_machine_specific_paths(pattern: str) -> None:
    files = sorted(REPO.glob(pattern))
    assert files, pattern
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "/home/" not in text, path
        assert "Progetti" not in text, path
