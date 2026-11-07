#!/usr/bin/env python3
"""Install the opencode-skills workflow into VS Code Copilot Chat.

The opencode definitions in `skills/`, `agents/`, `command/`, and
`config/opencode.json` remain the single source of truth. This script generates
the VS Code-native equivalents:

    opencode                          VS Code
    ────────────────────────────────  ──────────────────────────────────────────
    skills/<name>/SKILL.md            <skills>/<name>/SKILL.md   (symlink)
    agents/<name>.md                  <agents>/<name>.agent.md   (generated)
    command/<name>.md                 <prompts>/<name>.prompt.md (generated)
    config/AGENTS.md                  .github/copilot-instructions.md
    config/opencode.json → mcp        .vscode/mcp.json
    plugins/verifica-gate             .github/hooks/verifica-gate.json
    plugins/graphify                  .github/hooks/graphify-reminder.json

Usage:
    python3 install-vscode.py --workspace /path/to/workspace
    python3 install-vscode.py --target user
    python3 install-vscode.py --target both --workspace /path/to/workspace --force

Workspace target writes `.github/` and `.vscode/` inside the workspace.
User target writes to `~/.copilot/` (skills, agents, hooks, instructions, MCP)
and to the VS Code profile prompts folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_SRC = REPO_ROOT / "skills"
AGENTS_SRC = REPO_ROOT / "agents"
COMMANDS_SRC = REPO_ROOT / "command"
CONFIG_SRC = REPO_ROOT / "config"
VSCODE_SRC = REPO_ROOT / "vscode"

SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)

# opencode agent file → VS Code agent name (also the .agent.md file stem)
AGENT_NAMES = {
    "router": "router",
    "trade": "trade",
    "coder": "coder",
    "coder_planner": "coder-planner",
    "graphify_helper": "graphify-helper",
    "skill_updater": "skill-updater",
    "book-to-skill-agent": "book-to-skill-agent",
    "pdf_reader": "pdf-reader",
}

# VS Code resolves an agent `model:` entry against `metadata.id` first and against
# `metadata.name` only for non-BYOK models. The OpenCode Go provider is BYOK, so
# only the bare model id (the part after the vendor slash) can match. Emit that id
# and never the provider display name.

TRADING_PERMISSION_KEYS = {
    "get_macro_context",
    "analyze_stock",
    "analyze_options",
    "fetch_stock_data",
    "fetch_crypto_data",
    "fetch_options_chain",
    "scan_market",
    "suggest_options_strategy",
    "get_skill_knowledge",
    "clear_macro_cache",
    "trading_*",
}

PROMPT_HINTS = {
    "read-chunk": "<hash> [--info | --chunk N | --lines START END | --search PATTERN]",
    "routing-stats": "[--day YYYY-MM-DD | --json]",
    "token-stats": "[--json]",
}


@dataclass
class Options:
    """Installer options."""

    target: str = "workspace"
    workspace: Path | None = None
    force: bool = False
    dry_run: bool = False
    no_hooks: bool = False
    no_mcp: bool = False
    verbose: bool = False
    verify: bool = False
    expose_subagents: bool = False
    mcp_format: str = "vscode"
    actions: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Record an action and print it when verbose."""
        self.actions.append(message)
        if self.verbose:
            print(message)


def strip_quotes(value: str) -> str:
    """Remove matching single or double quotes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], dict[str, str], str]:
    """Return (top-level scalars, permission keys, body).

    This intentionally implements only the small YAML subset used by the
    opencode agent/command files, so the installer has no PyYAML dependency.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, {}, text

    raw, body = match.group(1), match.group(2)
    scalars: dict[str, str] = {}
    permission: dict[str, str] = {}
    lines = raw.splitlines()
    in_permission = False
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if re.match(r"^permission:\s*$", line):
            in_permission = True
            index += 1
            continue

        if in_permission:
            if line.startswith("  ") and not line.startswith("    "):
                key, _, value = line.strip().partition(":")
                permission[key.strip()] = value.strip()
                index += 1
                continue
            if not line.startswith((" ", "\t")):
                in_permission = False
            else:
                index += 1
                continue

        if line.startswith((" ", "\t")):
            index += 1
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Folded/literal block scalar: join the indented lines into one value.
        if value in (">", "|", ">-", "|-", ">+", "|+"):
            index += 1
            block: list[str] = []
            while index < len(lines) and (lines[index].startswith("  ") or not lines[index].strip()):
                block.append(lines[index].strip())
                index += 1
            scalars[key] = " ".join(part for part in block if part).strip()
            continue

        scalars[key] = value
        index += 1

    return scalars, permission, body


def permission_allowed(permission: dict[str, str], key: str) -> bool:
    """True when a permission key is present and not explicitly denied."""
    if key not in permission:
        return False
    value = permission[key].strip()
    if value in ("deny", "false", "no"):
        return False
    return True


def tools_for(permission: dict[str, str], agent_name: str = "") -> list[str]:
    """Map opencode permissions to VS Code tool aliases."""
    tools: list[str] = []

    def add(tool: str) -> None:
        if tool not in tools:
            tools.append(tool)

    if permission_allowed(permission, "read"):
        add("read")
    if permission_allowed(permission, "glob") or permission_allowed(permission, "grep"):
        add("search")
    # Path-scoped write maps (e.g. router) cannot be expressed in VS Code, so
    # only an explicit scalar `write: allow` / `edit: allow` grants edit.
    if permission.get("edit", "").strip() == "allow" or permission.get("write", "").strip() == "allow":
        add("edit")
    if permission_allowed(permission, "bash"):
        add("execute")
    if permission_allowed(permission, "webfetch"):
        add("web")
    if permission_allowed(permission, "task"):
        add("agent")
    if permission_allowed(permission, "todowrite"):
        add("todo")
    if any(key in permission for key in TRADING_PERMISSION_KEYS):
        add("trading/*")
    if "headroom_*" in permission:
        add("headroom/*")
    # REA is the reverse-engineering MCP server used by the coder workflow.
    if agent_name == "coder":
        add("rea/*")

    if not tools:
        add("read")
        add("search")
    return tools


def model_for(raw_model: str) -> str | None:
    """Map an opencode model id to the VS Code model id.

    `opencode-go/deepseek-v4.1-flash#low` becomes `deepseek-v4.1-flash`, which is
    the value VS Code compares against `metadata.id`.
    """
    raw_model = strip_quotes(raw_model).split("#", 1)[0].strip()
    if not raw_model:
        return None
    return raw_model.rsplit("/", 1)[-1]


def skill_directories() -> list[Path]:
    """Return valid skill directories (must contain SKILL.md)."""
    if not SKILLS_SRC.is_dir():
        return []
    return sorted(
        path
        for path in SKILLS_SRC.iterdir()
        if path.is_dir() and not path.name.startswith(".") and (path / "SKILL.md").is_file()
    )


def validate_skills() -> list[str]:
    """Validate skill names/descriptions against VS Code discovery rules."""
    problems: list[str] = []
    for skill_dir in skill_directories():
        try:
            text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{skill_dir.name}: cannot read SKILL.md ({exc})")
            continue
        scalars, _, _ = parse_frontmatter(text)
        name = strip_quotes(scalars.get("name", ""))
        description = strip_quotes(scalars.get("description", ""))
        if name != skill_dir.name:
            problems.append(f"{skill_dir.name}: frontmatter name is {name!r}")
        if not SKILL_NAME_RE.match(name):
            problems.append(f"{skill_dir.name}: name does not match [a-z0-9-]{{1,64}}")
        if not description:
            problems.append(f"{skill_dir.name}: missing description")
        elif len(description) > 1024:
            problems.append(f"{skill_dir.name}: description is {len(description)} chars (max 1024)")
    return problems


def ensure_parent(path: Path) -> None:
    """Create the parent directory of `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str, options: Options, label: str) -> None:
    """Write a generated file, skipping identical content."""
    if path.exists() and not path.is_file():
        options.log(f"SKIP {label}: {path} exists and is not a file")
        return
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == content:
                options.log(f"OK   {label}: {path} (unchanged)")
                return
        except OSError:
            pass
    if options.dry_run:
        options.log(f"DRY  {label}: would write {path}")
        return
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")
    options.log(f"WROTE {label}: {path}")


def write_json(path: Path, data: dict, options: Options, label: str) -> None:
    """Write JSON with stable formatting."""
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", options, label)


def load_json_file(path: Path) -> dict:
    """Parse a JSON or JSONC file (VS Code settings/mcp allow comments)."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(strip_jsonc(text))
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value is not an object")
    return data


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments plus trailing commas, preserving strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue

        if char == "/" and index + 1 < len(text):
            next_char = text[index + 1]
            if next_char == "/":
                index += 2
                while index < len(text) and text[index] not in "\r\n":
                    index += 1
                continue
            if next_char == "*":
                index += 2
                while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                    index += 1
                index += 2
                continue

        output.append(char)
        index += 1

    return re.sub(r",(\s*[}\]])", r"\1", "".join(output))


def merge_json(path: Path, updates: dict, options: Options, label: str) -> None:
    """Merge keys into an existing JSON file without overwriting user values."""
    if path.is_file():
        try:
            existing = load_json_file(path)
        except Exception as exc:
            options.log(f"SKIP {label}: cannot parse {path} ({exc}); not overwriting")
            return
    else:
        existing = {}

    changed = False
    for key, value in updates.items():
        if key not in existing or options.force:
            existing[key] = value
            changed = True

    if not changed:
        options.log(f"OK   {label}: {path} (already configured)")
        return
    write_json(path, existing, options, label)


def link_skill(source: Path, destination: Path, options: Options) -> None:
    """Symlink a skill directory into a VS Code skills location."""
    if destination.is_symlink():
        try:
            current = destination.resolve()
        except OSError:
            current = None
        if current == source.resolve():
            options.log(f"OK   skill: {destination} -> {source}")
            return
        if not options.force:
            options.log(f"SKIP skill: {destination} points elsewhere (use --force)")
            return
        if options.dry_run:
            options.log(f"DRY  skill: would replace {destination}")
            return
        destination.unlink()
    elif destination.exists():
        if not options.force:
            options.log(f"SKIP skill: {destination} exists and is not a symlink (use --force)")
            return
        if options.dry_run:
            options.log(f"DRY  skill: would replace {destination}")
            return
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if options.dry_run:
        options.log(f"DRY  skill: would link {destination} -> {source}")
        return
    ensure_parent(destination)
    relative = os.path.relpath(source, destination.parent)
    destination.symlink_to(relative, target_is_directory=True)
    options.log(f"LINK skill: {destination} -> {relative}")


def install_skills(skills_root: Path, options: Options) -> None:
    """Symlink every valid skill into `skills_root`."""
    for skill_dir in skill_directories():
        link_skill(skill_dir, skills_root / skill_dir.name, options)


def agent_preamble(name: str, source_name: str, skills_dir: str, available: Iterable[str]) -> str:
    """Return the VS Code adaptation block prepended to opencode agent bodies."""
    visible = [item for item in available if name == "router" or item != "router"]
    others = ", ".join(f"`{item}`" for item in visible if item != name)
    return f"""<!-- Generated by opencode-skills/install-vscode.py from agents/{source_name}.md.
     Edit the opencode source and rerun the installer; do not edit this file. -->

## VS Code runtime

You are the `{name}` custom agent in VS Code Copilot Chat. The opencode
definition below is your operating manual. Apply these translations:

- `@name` or `subagent_type="name"` → invoke the `agent` tool with agent name
  `name`. Available agents: {others}.
- `@skills/<name>` or the `skill` tool → read `{skills_dir}/<name>/SKILL.md`
  (or use `/<name>` in chat).
- Tool aliases: `bash`→`execute`, `read`→`read`, `glob`/`grep`→`search`,
  `edit`/`write`→`edit`, `webfetch`→`web`, `task`→`agent`,
  `todowrite`→`todo`, `headroom_*`→`headroom/*`, `trading_*`→`trading/*`.
- `permission`, `steps`, and `hidden` are opencode-only. Your tool access is
  set by the `tools` list in this file's frontmatter.
- End every response with a `## VERIFICA` section (confidenza, evidenza,
  non_verificato, escalation_consigliata).

---

"""


def build_agent(
    source: Path,
    name: str,
    skills_dir: str,
    available: list[str],
    expose_subagents: bool = False,
) -> str | None:
    """Convert one opencode agent file to VS Code `.agent.md` content."""
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return None

    scalars, permission, body = parse_frontmatter(text)
    description = strip_quotes(scalars.get("description", ""))
    if not description:
        return None

    # Align opencode agent references with the generated VS Code agent names.
    for old, new in (
        ("coder_planner", "coder-planner"),
        ("graphify_helper", "graphify-helper"),
        ("pdf_reader", "pdf-reader"),
        ("skill_updater", "skill-updater"),
    ):
        description = description.replace(old, new)
        body = body.replace(old, new)

    if name == "router":
        body = body.replace("on the opencode CLI", "in VS Code Copilot Chat")

    mode = strip_quotes(scalars.get("mode", "subagent"))
    model = model_for(scalars.get("model", ""))
    tools = tools_for(permission, name)

    lines = ["---", f"description: {json.dumps(description, ensure_ascii=False)}"]
    if model:
        lines.append(f"model: {json.dumps(model, ensure_ascii=False)}")
    lines.append(f"tools: {json.dumps(tools, ensure_ascii=False)}")
    invocable = mode == "primary" or expose_subagents
    lines.append(f"user-invocable: {'true' if invocable else 'false'}")
    if mode != "primary":
        lines.append("disable-model-invocation: false")
    if name == "router":
        subagents = [item for item in available if item != name]
        lines.append(f"agents: {json.dumps(subagents, ensure_ascii=False)}")
        lines.append(
            'argument-hint: "Describe the task; the router delegates to trade, '
            'coder, graphify-helper, pdf-reader, skill-updater, or book-to-skill-agent."'
        )
    lines.append("---")
    lines.append("")

    preamble = agent_preamble(name, source.stem, skills_dir, available)
    return "\n".join(lines) + preamble + body.lstrip("\n")


def install_agents(agents_root: Path, skills_dir: str, options: Options) -> None:
    """Generate VS Code custom agents from the opencode agent files."""
    available = [AGENT_NAMES.get(path.stem, path.stem) for path in sorted(AGENTS_SRC.glob("*.md"))]
    for source in sorted(AGENTS_SRC.glob("*.md")):
        name = AGENT_NAMES.get(source.stem, source.stem.replace("_", "-"))
        content = build_agent(source, name, skills_dir, available, options.expose_subagents)
        if content is None:
            options.log(f"SKIP agent: {source.name} (missing description)")
            continue
        write_text(agents_root / f"{name}.agent.md", content, options, "agent")


def build_prompt(source: Path, name: str) -> str | None:
    """Convert one opencode command file to VS Code `.prompt.md` content."""
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return None

    scalars, _, body = parse_frontmatter(text)
    description = strip_quotes(scalars.get("description", ""))
    if not description:
        return None

    lines = [
        "---",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        'agent: "agent"',
    ]
    if name in PROMPT_HINTS:
        lines.append(f"argument-hint: {json.dumps(PROMPT_HINTS[name], ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    lines.append(
        f"<!-- Generated by opencode-skills/install-vscode.py from command/{source.name}. "
        "Edit the opencode source and rerun the installer. -->"
    )
    lines.append("")
    lines.append(
        "> VS Code note: `$ARGUMENTS` is the text the user typed after the slash "
        "command. Replace it with the actual arguments when running the script."
    )
    lines.append("")
    return "\n".join(lines) + body.lstrip("\n")


def install_prompts(prompts_root: Path, options: Options) -> None:
    """Generate VS Code prompt files from the opencode commands."""
    for source in sorted(COMMANDS_SRC.glob("*.md")):
        name = source.stem.replace("_", "-")
        content = build_prompt(source, name)
        if content is None:
            options.log(f"SKIP prompt: {source.name} (missing description)")
            continue
        write_text(prompts_root / f"{name}.prompt.md", content, options, "prompt")


def render_template(template: Path, replacements: dict[str, str]) -> str:
    """Read a template and substitute `{{KEY}}` placeholders."""
    content = template.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace("{{" + key + "}}", value)
    return content


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


def default_model_id() -> str | None:
    """Return the workflow default model as a VS Code model id."""
    return model_for(str(opencode_config().get("model", "")))


def default_agent_name() -> str:
    """Return the workflow default agent name."""
    raw = str(opencode_config().get("default_agent", "router"))
    return AGENT_NAMES.get(raw, raw.replace("_", "-"))


def mcp_servers_from_opencode() -> dict[str, dict]:
    """Convert the opencode MCP config to VS Code stdio server definitions."""
    config_path = CONFIG_SRC / "opencode.json"
    if not config_path.is_file():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    servers: dict[str, dict] = {}
    for name, spec in (config.get("mcp") or {}).items():
        if not isinstance(spec, dict) or not spec.get("enabled", True):
            continue
        command = spec.get("command")
        if isinstance(command, list) and command:
            executable, args = str(command[0]), [str(item) for item in command[1:]]
        elif isinstance(command, str) and command:
            executable, args = command, []
        else:
            continue
        server = {"type": "stdio", "command": executable, "args": args}
        environment = spec.get("environment")
        if isinstance(environment, dict) and environment:
            server["env"] = {str(key): str(value) for key, value in environment.items()}
        servers[name] = server
    return servers


def install_mcp_workspace(workspace: Path, options: Options) -> None:
    """Write MCP servers in the requested VS Code format(s)."""
    if options.no_mcp:
        options.log("SKIP mcp: disabled by --no-mcp")
        return
    if options.mcp_format in ("vscode", "both"):
        install_mcp(workspace / ".vscode" / "mcp.json", "servers", options)
    if options.mcp_format in ("portable", "both"):
        install_mcp(workspace / ".mcp.json", "mcpServers", options)


def install_mcp(path: Path, key: str, options: Options) -> None:
    """Write or merge MCP server definitions."""
    servers = mcp_servers_from_opencode()
    if not servers:
        options.log("SKIP mcp: no enabled servers in config/opencode.json")
        return

    if path.is_file():
        try:
            existing = load_json_file(path)
        except Exception as exc:
            options.log(f"SKIP mcp: cannot parse {path} ({exc}); not overwriting")
            return
        current = existing.get(key)
        if not isinstance(current, dict):
            current = {}
        for name, spec in servers.items():
            if name not in current or options.force:
                current[name] = spec
        existing[key] = current
        write_json(path, existing, options, "mcp")
        return

    write_json(path, {key: servers}, options, "mcp")


def install_hooks(hooks_root: Path, cwd: Path, options: Options) -> None:
    """Copy hook scripts and write hook configuration with absolute paths."""
    if options.no_hooks:
        options.log("SKIP hooks: disabled by --no-hooks")
        return

    if not options.dry_run:
        hooks_root.mkdir(parents=True, exist_ok=True)
    script_sources = {
        "verifica_gate.py": VSCODE_SRC / "hooks" / "verifica_gate.py",
        "graphify_reminder.py": VSCODE_SRC / "hooks" / "graphify_reminder.py",
    }
    for filename, source in script_sources.items():
        if not source.is_file():
            options.log(f"SKIP hook script: missing {source}")
            continue
        destination = hooks_root / filename
        if source.resolve() == destination.resolve():
            options.log(f"OK   hook script: {destination} (source)")
            continue
        write_text(destination, source.read_text(encoding="utf-8"), options, "hook script")
        if not options.dry_run:
            destination.chmod(0o755)

    python = shutil.which("python3") or sys.executable or "python3"
    verifica_cmd = f'{python} "{hooks_root / "verifica_gate.py"}"'
    graphify_cmd = f'{python} "{hooks_root / "graphify_reminder.py"}"'

    write_json(
        hooks_root / "verifica-gate.json",
        {
            "hooks": {
                "SubagentStop": [
                    {
                        "type": "command",
                        "command": verifica_cmd,
                        "cwd": str(cwd),
                        "timeout": 15,
                    }
                ]
            }
        },
        options,
        "hook config",
    )
    write_json(
        hooks_root / "graphify-reminder.json",
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "type": "command",
                        "command": graphify_cmd,
                        "cwd": str(cwd),
                        "timeout": 10,
                    }
                ]
            }
        },
        options,
        "hook config",
    )


def workspace_replacements(workspace: Path, options: Options) -> dict[str, str]:
    """Template values for a workspace install."""
    repo = REPO_ROOT
    try:
        repo_ref = os.path.relpath(repo, workspace)
    except ValueError:
        repo_ref = str(repo)
    return {
        "OPENCODE_SKILLS": repo_ref,
        "SKILLS_DIR": ".github/skills",
        "AGENTS_DIR": ".github/agents",
        "PROMPTS_DIR": ".github/prompts",
        "INSTRUCTIONS_DIR": ".github/instructions",
        "MCP_FILE": ".vscode/mcp.json",
        "HOOKS_DIR": ".github/hooks",
    }


def user_replacements() -> dict[str, str]:
    """Template values for a user-level install."""
    return {
        "OPENCODE_SKILLS": str(REPO_ROOT),
        "SKILLS_DIR": "~/.copilot/skills",
        "AGENTS_DIR": "~/.copilot/agents",
        "PROMPTS_DIR": "~/.config/Code/User/prompts",
        "INSTRUCTIONS_DIR": "~/.copilot/instructions",
        "MCP_FILE": "~/.copilot/mcp-config.json",
        "HOOKS_DIR": "~/.copilot/hooks",
    }


def install_instructions(path: Path, replacements: dict[str, str], options: Options) -> None:
    """Write the always-on copilot-instructions.md file."""
    template = VSCODE_SRC / "copilot-instructions.md"
    if not template.is_file():
        options.log(f"SKIP instructions: missing {template}")
        return
    if path.exists() and not options.force:
        options.log(f"SKIP instructions: {path} exists (use --force to overwrite)")
        print(
            f"WARNING: {path} already exists; the opencode-skills instructions were "
            "not written. Rerun with --force to overwrite it."
        )
        return
    write_text(path, render_template(template, replacements), options, "instructions")


def install_python_instructions(path: Path, replacements: dict[str, str], options: Options) -> None:
    """Write the file-scoped Python instructions."""
    template = VSCODE_SRC / "instructions" / "python.instructions.md"
    if not template.is_file():
        options.log(f"SKIP python instructions: missing {template}")
        return
    write_text(path, render_template(template, replacements), options, "python instructions")


def install_workspace(options: Options) -> None:
    """Install the VS Code layer into a workspace folder."""
    if options.workspace is None:
        raise SystemExit("--workspace is required for the workspace target")
    workspace = options.workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise SystemExit(f"workspace does not exist: {workspace}")

    print(f"\nWorkspace target: {workspace}")
    github = workspace / ".github"
    install_skills(github / "skills", options)
    install_agents(github / "agents", ".github/skills", options)
    install_prompts(github / "prompts", options)

    replacements = workspace_replacements(workspace, options)
    install_instructions(github / "copilot-instructions.md", replacements, options)
    install_python_instructions(
        github / "instructions" / "python.instructions.md", replacements, options
    )

    install_mcp_workspace(workspace, options)
    install_hooks(github / "hooks", workspace, options)

    settings_updates = {
        "chat.useAgentSkills": True,
        "chat.useAgentsMdFile": False,
        "chat.useHooks": True,
    }
    default_model = default_model_id()
    if default_model:
        settings_updates["chat.defaultModel"] = default_model

    merge_json(
        workspace / ".vscode" / "settings.json",
        settings_updates,
        options,
        "settings",
    )

    for stray in stray_duplicates(workspace):
        print(
            f"NOTE: {stray} is a nested copy that VS Code never reads "
            "(only <workspaceRoot>/.github is scanned). Delete it to avoid confusion."
        )

    if (workspace / "AGENTS.md").is_file():
        print(
            "WARNING: AGENTS.md exists at the workspace root. VS Code Copilot may "
            "load it in addition to .github/copilot-instructions.md; keep only one "
            "always-on instructions source or set chat.useAgentsMdFile=false."
        )


def install_user(options: Options) -> None:
    """Install the VS Code layer at user scope (~/.copilot and the profile)."""
    home = Path.home()
    copilot = home / ".copilot"
    prompts = Path(
        os.environ.get("VSCODE_USER_PROMPTS_FOLDER", home / ".config" / "Code" / "User" / "prompts")
    ).expanduser()

    print(f"\nUser target: {copilot}")
    install_skills(copilot / "skills", options)
    install_agents(copilot / "agents", "~/.copilot/skills", options)
    install_prompts(prompts, options)

    replacements = user_replacements()
    install_instructions(copilot / "copilot-instructions.md", replacements, options)
    install_python_instructions(
        copilot / "instructions" / "python.instructions.md", replacements, options
    )

    if not options.no_mcp:
        install_mcp(copilot / "mcp-config.json", "mcpServers", options)
    install_hooks(copilot / "hooks", Path.home(), options)


# ── Verification ─────────────────────────────────────────────────────────────


def expected_agent_files(skills_dir: str, expose_subagents: bool = False) -> dict[str, str]:
    """Return {filename: content} for the agents that should exist."""
    available = [AGENT_NAMES.get(path.stem, path.stem) for path in sorted(AGENTS_SRC.glob("*.md"))]
    expected: dict[str, str] = {}
    for source in sorted(AGENTS_SRC.glob("*.md")):
        name = AGENT_NAMES.get(source.stem, source.stem.replace("_", "-"))
        content = build_agent(source, name, skills_dir, available, expose_subagents)
        if content is not None:
            expected[f"{name}.agent.md"] = content
    return expected


def expected_prompt_files() -> dict[str, str]:
    """Return {filename: content} for the prompts that should exist."""
    expected: dict[str, str] = {}
    for source in sorted(COMMANDS_SRC.glob("*.md")):
        name = source.stem.replace("_", "-")
        content = build_prompt(source, name)
        if content is not None:
            expected[f"{name}.prompt.md"] = content
    return expected


def compare_text(path: Path, expected: str, label: str, problems: list[str]) -> None:
    """Record a problem when a generated file is missing or out of date."""
    if not path.is_file():
        problems.append(f"{label}: missing {path}")
        return
    if path.read_text(encoding="utf-8", errors="replace") != expected:
        problems.append(f"{label}: out of date {path} (rerun the installer)")


def verify_skills(root: Path, problems: list[str], notes: list[str]) -> None:
    """Check that every opencode skill is linked from the VS Code location."""
    sources = skill_directories()
    if not root.is_dir():
        problems.append(f"skills: missing directory {root}")
        return
    linked = 0
    for source in sources:
        dest = root / source.name
        if not dest.exists():
            problems.append(f"skill {source.name}: missing {dest}")
            continue
        try:
            resolved = dest.resolve()
        except OSError:
            resolved = None
        if resolved != source.resolve():
            problems.append(f"skill {source.name}: {dest} does not point to {source}")
            continue
        linked += 1
    source_names = {source.name for source in sources}
    extra = sorted(
        item.name for item in root.iterdir() if item.is_dir() and item.name not in source_names
    )
    if extra:
        notes.append(
            f"skills: {len(extra)} extra entries not from opencode-skills: {', '.join(extra[:5])}"
        )
    notes.append(f"skills: {linked}/{len(sources)} linked to opencode-skills")


def verify_mcp(path: Path, key: str, problems: list[str], notes: list[str]) -> None:
    """Check that the VS Code MCP config mirrors config/opencode.json."""
    expected = mcp_servers_from_opencode()
    if not expected:
        notes.append("mcp: no enabled servers in config/opencode.json")
        return
    if not path.is_file():
        problems.append(f"mcp: missing {path}")
        return
    try:
        data = load_json_file(path)
    except Exception as exc:
        problems.append(f"mcp: cannot parse {path} ({exc})")
        return
    servers = data.get(key)
    if not isinstance(servers, dict):
        problems.append(f"mcp: {path} has no {key!r} object")
        return
    for name, spec in expected.items():
        current = servers.get(name)
        if not isinstance(current, dict):
            problems.append(f"mcp: server {name!r} missing from {path}")
            continue
        if current.get("command") != spec["command"] or list(current.get("args") or []) != spec["args"]:
            problems.append(f"mcp: server {name!r} differs from config/opencode.json")
    notes.append(f"mcp: {len(expected)} servers configured ({', '.join(sorted(expected))})")


def verify_mcp_workspace(workspace: Path, problems: list[str], notes: list[str]) -> None:
    """Check whichever MCP format the workspace actually uses."""
    candidates = [
        (workspace / ".vscode" / "mcp.json", "servers", ".vscode/mcp.json"),
        (workspace / ".mcp.json", "mcpServers", ".mcp.json"),
    ]
    present = [item for item in candidates if item[0].is_file()]
    if not present:
        problems.append(
            "mcp: no MCP config found (.vscode/mcp.json or .mcp.json); "
            "run the installer without --no-mcp"
        )
        return
    for path, key, label in present:
        verify_mcp(path, key, problems, notes)
    if len(present) == 2:
        notes.append(
            "mcp: both .vscode/mcp.json and .mcp.json exist; keep one to avoid "
            "duplicate servers (rerun with --mcp-format vscode|portable)"
        )


def verify_hooks(root: Path, problems: list[str], notes: list[str]) -> None:
    """Check the hook scripts and their configuration."""
    pairs = {
        "verifica_gate.py": (VSCODE_SRC / "hooks" / "verifica_gate.py", "verifica-gate.json"),
        "graphify_reminder.py": (VSCODE_SRC / "hooks" / "graphify_reminder.py", "graphify-reminder.json"),
    }
    installed = 0
    for filename, (source, config_name) in pairs.items():
        target = root / filename
        if not target.is_file():
            problems.append(f"hook: missing {target}")
            continue
        if target.read_text(encoding="utf-8", errors="replace") != source.read_text(
            encoding="utf-8", errors="replace"
        ):
            problems.append(f"hook: {target} differs from {source}")
            continue
        config_path = root / config_name
        if not config_path.is_file():
            problems.append(f"hook: missing config {config_path}")
            continue
        try:
            config = load_json_file(config_path)
        except Exception as exc:
            problems.append(f"hook: cannot parse {config_path} ({exc})")
            continue
        events = config.get("hooks")
        if not isinstance(events, dict) or not events:
            problems.append(f"hook: {config_path} defines no events")
            continue
        for event, entries in events.items():
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                if filename not in str(entry.get("command", "")):
                    problems.append(f"hook: {config_path} {event} does not run {filename}")
                cwd = entry.get("cwd")
                if cwd is not None and not Path(str(cwd)).is_dir():
                    problems.append(f"hook: {config_path} cwd does not exist: {cwd}")
        installed += 1
    notes.append(f"hooks: {installed}/{len(pairs)} installed with config")


def migrated_prompts(github: Path) -> list[str]:
    """Return prompt names that the Migrations panel converted into skills."""
    skills_root = github / "skills"
    prompts_root = github / "prompts"
    if not skills_root.is_dir() or not prompts_root.is_dir():
        return []
    names: list[str] = []
    for prompt in sorted(prompts_root.glob("*.prompt.md")):
        stem = prompt.name[: -len(".prompt.md")]
        candidate = skills_root / stem / "SKILL.md"
        if candidate.is_file():
            names.append(stem)
    return names


def stray_duplicates(workspace: Path) -> list[Path]:
    """Find nested VS Code layers inside the workspace that opencode-skills generated.

    VS Code only reads `<workspaceRoot>/.github/skills`, never a subfolder, so a
    nested copy is dead weight (and confusing when several exist).
    """
    found: list[Path] = []
    if not workspace.is_dir():
        return found
    for child in sorted(workspace.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        candidate = child / ".github" / "skills"
        if not candidate.is_dir():
            continue
        try:
            links = [item for item in candidate.iterdir() if item.is_symlink()]
        except OSError:
            continue
        for link in links:
            try:
                if REPO_ROOT in link.resolve().parents:
                    found.append(child / ".github")
                    break
            except OSError:
                continue
    return found


def runtime_evidence(notes: list[str]) -> None:
    """Report on-disk proof that the VS Code hooks actually executed."""
    gate = Path.home() / ".config" / "opencode" / "stats" / "gate_events.jsonl"
    count = 0
    if gate.is_file():
        for line in gate.read_text(encoding="utf-8", errors="replace").splitlines():
            if "vscode-verifica-gate" in line:
                count += 1
    notes.append(
        f"runtime: verifica-gate hook fired {count}x from VS Code "
        "(>0 proves it ran; 0 = no subagent finished yet)"
    )
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    markers = sorted((cache_root / "opencode-vscode-graphify").glob("*.seen"))
    notes.append(f"runtime: graphify hook fired in {len(markers)} session(s)")


def verify_workspace(options: Options) -> tuple[list[str], list[str]]:
    """Verify a workspace-scope installation."""
    if options.workspace is None:
        raise SystemExit("--workspace is required for --verify with the workspace target")
    workspace = options.workspace.expanduser().resolve()
    github = workspace / ".github"
    replacements = workspace_replacements(workspace, options)
    problems: list[str] = []
    notes: list[str] = []

    print(f"\nWorkspace: {workspace}")
    verify_skills(github / "skills", problems, notes)

    agents = expected_agent_files(".github/skills", options.expose_subagents)
    for filename, content in agents.items():
        compare_text(github / "agents" / filename, content, "agent", problems)
    notes.append(f"agents: {len(agents)} expected")

    prompts = expected_prompt_files()
    for filename, content in prompts.items():
        compare_text(github / "prompts" / filename, content, "prompt", problems)
    notes.append(f"prompts: {len(prompts)} expected")

    compare_text(
        github / "copilot-instructions.md",
        render_template(VSCODE_SRC / "copilot-instructions.md", replacements),
        "instructions",
        problems,
    )
    compare_text(
        github / "instructions" / "python.instructions.md",
        render_template(VSCODE_SRC / "instructions" / "python.instructions.md", replacements),
        "python instructions",
        problems,
    )
    verify_mcp_workspace(workspace, problems, notes)
    verify_hooks(github / "hooks", problems, notes)

    settings_path = workspace / ".vscode" / "settings.json"
    if settings_path.is_file():
        try:
            settings = load_json_file(settings_path)
        except Exception:
            settings = {}
        notes.append(
            "settings: "
            f"chat.useAgentSkills={settings.get('chat.useAgentSkills', 'default(true)')}, "
            f"chat.useHooks={settings.get('chat.useHooks', 'default(true)')}, "
            f"chat.useAgentsMdFile={settings.get('chat.useAgentsMdFile', 'default(true)')}, "
            f"chat.defaultModel={settings.get('chat.defaultModel', 'unset')}"
        )
        expected_model = default_model_id()
        if expected_model and settings.get("chat.defaultModel") != expected_model:
            notes.append(
                f"settings: chat.defaultModel is not {expected_model!r} from config/opencode.json"
            )
    else:
        notes.append("settings: no .vscode/settings.json (defaults enable skills, hooks, AGENTS.md)")
    if (workspace / "AGENTS.md").is_file():
        notes.append("settings: a root AGENTS.md exists and VS Code will load it too")

    migrated = migrated_prompts(github)
    if migrated:
        notes.append(
            f"migration: {len(migrated)} prompt(s) also exist as skills "
            f"({', '.join(migrated)}); the Migrations panel moved them, so the "
            "generated prompts were replaced. Click Ignore instead, or delete the "
            "skill copies to keep opencode-skills as the source of truth"
        )

    strays = stray_duplicates(workspace)
    for stray in strays:
        notes.append(
            f"duplicate: {stray} is nested inside the workspace, so VS Code ignores it "
            "(only <workspaceRoot>/.github is read); safe to delete"
        )

    return problems, notes


def verify_user(options: Options) -> tuple[list[str], list[str]]:
    """Verify a user-scope installation."""
    home = Path.home()
    copilot = home / ".copilot"
    prompts_root = Path(
        os.environ.get("VSCODE_USER_PROMPTS_FOLDER", home / ".config" / "Code" / "User" / "prompts")
    ).expanduser()
    replacements = user_replacements()
    problems: list[str] = []
    notes: list[str] = []

    print(f"\nUser scope: {copilot}")
    verify_skills(copilot / "skills", problems, notes)

    agents = expected_agent_files("~/.copilot/skills", options.expose_subagents)
    for filename, content in agents.items():
        compare_text(copilot / "agents" / filename, content, "agent", problems)
    notes.append(f"agents: {len(agents)} expected")

    prompts = expected_prompt_files()
    for filename, content in prompts.items():
        compare_text(prompts_root / filename, content, "prompt", problems)
    notes.append(f"prompts: {len(prompts)} expected in {prompts_root}")

    compare_text(
        copilot / "copilot-instructions.md",
        render_template(VSCODE_SRC / "copilot-instructions.md", replacements),
        "instructions",
        problems,
    )
    compare_text(
        copilot / "instructions" / "python.instructions.md",
        render_template(VSCODE_SRC / "instructions" / "python.instructions.md", replacements),
        "python instructions",
        problems,
    )
    verify_mcp(copilot / "mcp-config.json", "mcpServers", problems, notes)
    verify_hooks(copilot / "hooks", problems, notes)
    return problems, notes


def run_verify(options: Options) -> int:
    """Run the compatibility check and return a process exit code."""
    print("opencode-skills → VS Code compatibility check")
    print(f"Source: {REPO_ROOT}")
    print(f"Target: {options.target}")

    source_warnings = validate_skills()
    problems: list[str] = []
    notes: list[str] = []

    if options.target in ("workspace", "both"):
        found, found_notes = verify_workspace(options)
        problems += found
        notes += found_notes
    if options.target in ("user", "both"):
        found, found_notes = verify_user(options)
        problems += found
        notes += found_notes

    runtime_evidence(notes)

    print("\nChecks:")
    for note in notes:
        print(f"  · {note}")

    if source_warnings:
        print("\nSource warnings:")
        for warning in source_warnings:
            print(f"  ! {warning}")

    if problems:
        print(f"\nDRIFT / MISSING ({len(problems)}):")
        for problem in problems:
            print(f"  x {problem}")
        print("\nVerdict: the VS Code layer is NOT in sync with opencode-skills.")
        if options.target == "user":
            print("Fix: python3 install-vscode.py --target user --force")
        elif options.workspace is not None:
            print(f"Fix: python3 install-vscode.py --workspace {options.workspace} --force")
        else:
            print("Fix: python3 install-vscode.py --workspace <workspace> --force")
        return 1

    print("\nVerdict: the VS Code layer matches opencode-skills (no drift).")
    print("In-chat proof: type '/' to list skills, open the agent picker,")
    print("and check the MCP view for headroom / trading / rea.")
    return 0


def parse_args(argv: list[str] | None = None) -> Options:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install the opencode-skills workflow into VS Code Copilot Chat.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--target",
        choices=("workspace", "user", "both"),
        default="workspace",
        help="Where to install (default: workspace)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=os.environ.get("VSCODE_WORKSPACE"),
        help="Workspace folder for the workspace target (default: $VSCODE_WORKSPACE)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files/symlinks")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--no-hooks", action="store_true", help="Skip VS Code hook generation")
    parser.add_argument("--no-mcp", action="store_true", help="Skip MCP server generation")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print every action")
    parser.add_argument(
        "--mcp-format",
        choices=("vscode", "portable", "both"),
        default="vscode",
        help=(
            "Where to write MCP servers: 'vscode' = .vscode/mcp.json (default), "
            "'portable' = .mcp.json, 'both' = keep both in sync"
        ),
    )
    parser.add_argument(
        "--expose-subagents",
        action="store_true",
        help="Show subagents (trade, coder, ...) in the agent picker as well",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only check that the installed VS Code layer matches the opencode sources",
    )
    args = parser.parse_args(argv)

    return Options(
        target=args.target,
        workspace=Path(args.workspace) if args.workspace else None,
        force=args.force,
        dry_run=args.dry_run,
        no_hooks=args.no_hooks,
        no_mcp=args.no_mcp,
        verbose=args.verbose,
        verify=args.verify,
        expose_subagents=args.expose_subagents,
        mcp_format=args.mcp_format,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the installer."""
    options = parse_args(argv)

    if options.verify:
        return run_verify(options)

    print("opencode-skills → VS Code compatibility installer")
    print(f"Source: {REPO_ROOT}")
    print(f"Target: {options.target}{' (dry run)' if options.dry_run else ''}")

    problems = validate_skills()
    if problems:
        print("\nSkill validation warnings:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"\nSkill validation: OK ({len(skill_directories())} skills)")

    if options.target in ("workspace", "both"):
        install_workspace(options)
    if options.target in ("user", "both"):
        install_user(options)
    if options.target == "both":
        print(
            "\nWARNING: installing both scopes duplicates skills/agents. "
            "VS Code will show both copies; prefer one scope."
        )

    print(f"\nDone: {len(options.actions)} actions.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
