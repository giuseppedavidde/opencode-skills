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


def run_installer(
    home: Path, *args: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("XDG_", "VSCODE_")) and key != "REA_REPO"
    }
    env.update({"HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra_env or {})
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


def load_installer():
    spec = importlib.util.spec_from_file_location("install_vscode_probe", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["install_vscode_probe"] = module
    spec.loader.exec_module(module)
    return module


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


def test_user_legacy_mcp_is_migrated_to_copilot_home(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    legacy = tmp_path / ".config" / "Code" / "User" / "mcp.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "servers": {
                    "browse": {"type": "stdio", "command": "/old/browse", "args": ["mcp"]},
                    "mine": {"type": "stdio", "command": "mine", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    profile = tmp_path / ".config" / "Code" / "User" / "profiles" / "work" / "mcp.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        json.dumps({"servers": {"trading": {"type": "stdio", "command": "old"}}}),
        encoding="utf-8",
    )

    result = run_installer(tmp_path, "--target", "user")
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(json.loads(legacy.read_text(encoding="utf-8"))["servers"]) == {"mine"}
    assert json.loads(profile.read_text(encoding="utf-8")) == {}
    destination = json.loads((tmp_path / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))
    assert {"browse", "headroom", "rea", "trading"} <= set(destination["mcpServers"])
    verify = run_installer(tmp_path, "--verify", "--target", "user")
    assert verify.returncode == 0, verify.stdout


def test_workspace_legacy_mcp_moves_to_the_root_dot_mcp(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    workspace = tmp_path / "ws"
    (workspace / ".vscode").mkdir(parents=True)
    legacy = workspace / ".vscode" / "mcp.json"
    legacy.write_text(
        json.dumps(
            {
                "servers": {
                    "headroom": {"type": "stdio", "command": "old"},
                    "rea": {"type": "stdio", "command": "old"},
                    "mine": {"type": "stdio", "command": "mine", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_installer(tmp_path, "--target", "workspace", "--workspace", str(workspace))
    assert result.returncode == 0, result.stdout + result.stderr
    root = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert {"browse", "headroom", "rea", "trading"} <= set(root)
    assert set(json.loads(legacy.read_text(encoding="utf-8"))["servers"]) == {"mine"}
    verify = run_installer(
        tmp_path, "--verify", "--target", "workspace", "--workspace", str(workspace)
    )
    assert verify.returncode == 0, verify.stdout


def test_legacy_server_without_runtime_leaves_the_workspace_file(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    absent_rea = str(tmp_path / "no-rea-here")
    workspace = tmp_path / "ws"
    (workspace / ".vscode").mkdir(parents=True)
    legacy = workspace / ".vscode" / "mcp.json"
    legacy.write_text(
        json.dumps(
            {
                "servers": {
                    "rea": {"type": "stdio", "command": "old"},
                    "mine": {"type": "stdio", "command": "mine", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_installer(
        tmp_path,
        "--target",
        "workspace",
        "--workspace",
        str(workspace),
        extra_env={"REA_REPO": absent_rea},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(json.loads(legacy.read_text(encoding="utf-8"))["servers"]) == {"mine"}
    assert "./install.sh --with-rea" in result.stdout


def test_no_migrate_mcp_keeps_the_legacy_copy_and_verify_reports_it(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    legacy = tmp_path / ".config" / "Code" / "User" / "mcp.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"servers": {"browse": {"type": "stdio", "command": "/old/browse"}}}),
        encoding="utf-8",
    )

    run_installer(tmp_path, "--target", "user", "--no-migrate-mcp")
    assert "browse" in json.loads(legacy.read_text(encoding="utf-8"))["servers"]
    assert run_installer(tmp_path, "--verify", "--target", "user", "--no-migrate-mcp").returncode == 0
    drift = run_installer(tmp_path, "--verify", "--target", "user")
    assert drift.returncode == 1
    assert "legacy copies remain" in drift.stdout


def test_vscode_format_does_not_migrate_by_design(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    workspace = tmp_path / "ws"
    (workspace / ".vscode").mkdir(parents=True)
    legacy = workspace / ".vscode" / "mcp.json"
    legacy.write_text(json.dumps({"servers": {}}), encoding="utf-8")

    run_installer(
        tmp_path, "--target", "workspace", "--workspace", str(workspace), "--mcp-format", "vscode"
    )
    assert not (workspace / ".mcp.json").exists()
    assert "headroom" in json.loads(legacy.read_text(encoding="utf-8"))["servers"]


def test_rea_checkout_falls_back_to_the_sibling_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer = load_installer()
    sibling = tmp_path / "work" / "rea"
    sibling.mkdir(parents=True)
    monkeypatch.setattr(installer, "REPO_ROOT", tmp_path / "work" / "opencode-skills")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    assert installer.rea_checkout() == sibling

    monkeypatch.setenv("REA_REPO", str(tmp_path / "configured"))
    assert installer.rea_checkout() == tmp_path / "configured"


def test_workspace_dot_mcp_keeps_managed_servers_in_sync(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "browse": {"type": "stdio", "command": "old"},
                    "mine": {"type": "stdio", "command": "mine", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )

    run_installer(tmp_path, "--target", "user", "--workspace", str(workspace))
    servers = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert {"browse", "headroom", "rea", "trading", "mine"} <= set(servers)


def test_a_github_link_into_copilot_is_not_written_through(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    copilot = tmp_path / ".copilot"
    copilot.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".github").symlink_to(copilot, target_is_directory=True)

    result = run_installer(tmp_path, "--target", "workspace", "--workspace", str(workspace))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "links into ~/.copilot" in result.stdout
    assert not (copilot / "agents").exists()
    assert not (copilot / "skills").exists()


HOOK_SCRIPTS = {
    "verifica_gate.py",
    "graphify_reminder.py",
    "agent_bootstrap.py",
    "handoff_digest.py",
    "routing_guard.py",
    "agent_guard.py",
}
HOOK_CONFIGS = {
    "verifica-gate.json",
    "graphify-reminder.json",
    "agent-bootstrap.json",
    "handoff-digest.json",
    "routing-guard.json",
}


def test_hook_scripts_configs_and_manifest_are_installed(home: Path) -> None:
    hooks = home / ".copilot" / "hooks"
    files = {path.name for path in hooks.iterdir() if path.is_file()}
    assert HOOK_SCRIPTS <= files
    assert HOOK_CONFIGS <= files
    assert ".manifest.json" in files
    json_configs = {name for name in files if name.endswith(".json") and name != ".manifest.json"}
    assert json_configs == HOOK_CONFIGS

    manifest = json.loads((hooks / ".manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert set(manifest["hooks"]) == HOOK_SCRIPTS


def test_new_hook_configs_use_the_right_events(home: Path) -> None:
    hooks = home / ".copilot" / "hooks"
    bootstrap = json.loads((hooks / "agent-bootstrap.json").read_text(encoding="utf-8"))
    command = bootstrap["hooks"]["SubagentStart"][0]["command"]
    assert "agent_bootstrap.py" in command
    assert "--agents=" in command
    assert "--repo=" in command

    digest = json.loads((hooks / "handoff-digest.json").read_text(encoding="utf-8"))
    assert list(digest["hooks"]) == ["PostToolUse"]
    assert "handoff_digest.py" in digest["hooks"]["PostToolUse"][0]["command"]

    routing = json.loads((hooks / "routing-guard.json").read_text(encoding="utf-8"))
    assert set(routing["hooks"]) == {"UserPromptSubmit", "PreToolUse"}
    assert "--event=prompt" in routing["hooks"]["UserPromptSubmit"][0]["command"]
    assert "--event=tool" in routing["hooks"]["PreToolUse"][0]["command"]


def test_trade_and_coder_agents_carry_per_agent_hooks(home: Path) -> None:
    for name in ("trade", "coder"):
        meta = frontmatter(home / ".copilot" / "agents" / f"{name}.agent.md")
        assert "hooks" in meta
        entry = meta["hooks"]["PreToolUse"][0]
        assert "agent_guard.py" in entry["command"]
        assert f"--agent={name}" in entry["command"]
        assert entry["timeout"] == 10

    other = frontmatter(home / ".copilot" / "agents" / "router.agent.md")
    assert "hooks" not in other


def test_no_hooks_writes_no_configs_no_manifest_and_no_agent_block(tmp_path: Path) -> None:
    add_fake_mcp_runtimes(tmp_path)
    result = run_installer(tmp_path, "--target", "user", "--no-hooks")
    assert result.returncode == 0, result.stdout + result.stderr
    hooks = tmp_path / ".copilot" / "hooks"
    files = {path.name for path in hooks.iterdir() if path.is_file()} if hooks.is_dir() else set()
    assert not (files & HOOK_CONFIGS)
    assert ".manifest.json" not in files
    for name in ("trade", "coder"):
        text = (tmp_path / ".copilot" / "agents" / f"{name}.agent.md").read_text(encoding="utf-8")
        assert "hooks:" not in text
        assert "agent_guard.py" not in text
    assert run_installer(tmp_path, "--verify", "--target", "user", "--no-hooks").returncode == 0
