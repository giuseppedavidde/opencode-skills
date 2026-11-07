# VS Code compatibility layer

This directory contains the VS Code-native assets generated from the opencode
definitions. The entry point is [`install-vscode.py`](../install-vscode.py) in
the repository root.

## Why

opencode reads `~/.config/opencode/{skills,agents,command}` and
`config/opencode.json`. VS Code Copilot Chat reads a different set of folders
and file formats. The installer keeps opencode as the source of truth and
generates the VS Code layer from it.

## Mapping

| opencode | VS Code | Notes |
|----------|---------|-------|
| `skills/<name>/SKILL.md` | `.github/skills/<name>/SKILL.md` | Symlink; the format is identical |
| `agents/<name>.md` | `.github/agents/<name>.agent.md` | Frontmatter converted (`tools`, `model`, `user-invocable`); body preserved with a runtime preamble |
| `command/<name>.md` | `.github/prompts/<name>.prompt.md` | Frontmatter converted (`agent: agent`) |
| `config/AGENTS.md` | `.github/copilot-instructions.md` (workspace) / `~/.copilot/copilot-instructions.md` (user) | Rewritten for VS Code |
| `config/opencode.json` → `mcp` | `.vscode/mcp.json` (workspace) / `~/.copilot/mcp-config.json` (user) | stdio servers |
| `plugins/verifica-gate` | `.github/hooks/verifica-gate.json` + `hooks/verifica_gate.py` | `SubagentStop` hook, fail-open, audit to `~/.config/opencode/stats/gate_events.jsonl` |
| `plugins/graphify` | `.github/hooks/graphify-reminder.json` + `hooks/graphify_reminder.py` | `PreToolUse` hook, injects the reminder once per session |
| `plugins/auto-headroom` | — | No VS Code equivalent; use the `headroom` MCP server + `/read-chunk` |
| `plugins/routing-stats`, `tokens-per-second` | — | Scripts remain available via prompts; telemetry only covers opencode sessions |

The writing directive `asd-ste100` is a normal skill, so it maps automatically.
The generated `.agent.md` files and `copilot-instructions.md` also embed a
compact copy, so an agent follows the directive without an extra read.

### Agent models

`model:` in a generated agent is the **bare VS Code model id**, for example
`deepseek-v4.1-flash` from `opencode-go/deepseek-v4.1-flash#low`. VS Code
resolves an agent model against `metadata.id` first and against
`metadata.name` only for models that are not BYOK. The OpenCode Go provider is
BYOK, so a display name such as `DeepSeek V4.1 Flash` never resolves and the
agent silently falls back to the session model. Keep the bare id.

## Startup selection

VS Code has a setting for the default model but **no setting for the default
custom agent**. The selection lives in application storage:

| Key | Value |
|-----|-------|
| `workbench.agentsession.agentHostAgentPicker.<scheme>.selectedAgentUri` | `file://.../.github/agents/<name>.agent.md` |
| `chat.currentLanguageModel.panel.<scheme>` | `<scheme>:opencodego/<model-id>` |

`<scheme>` is `agent-host-copilotcli` for the Copilot agent host.

Two mechanisms cover startup:

1. `chat.defaultModel` in `.vscode/settings.json`, written from
   `config/opencode.json` → `model`. VS Code applies it to every new
   conversation.
2. [`scripts/vscode-preselect.py`](../scripts/vscode-preselect.py), which writes
   both storage keys from `config/opencode.json` → `default_agent` and `model`.
   Run it while VS Code is closed; it exits 2 otherwise.

```bash
scripts/vscode-preselect.py --dry-run
scripts/vscode-preselect.py --force            # VS Code open (last write wins)
scripts/vscode-preselect.py --keep-user-choice # respect an existing selection
```

`vscode/systemd/opencode-skills-vscode-preselect.service` runs the helper at
login, before the graphical session starts applications:

```bash
ln -sfn "$PWD/vscode/systemd/opencode-skills-vscode-preselect.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable opencode-skills-vscode-preselect.service
```

A manual agent choice inside a session is not lost: it survives until the next
login, when the workflow default is applied again.

## Install

```bash
# Current workspace (writes .github/, .vscode/, copilot-instructions.md)
python3 install-vscode.py --workspace /path/to/workspace

# User scope (all workspaces)
python3 install-vscode.py --target user

# Both scopes
python3 install-vscode.py --target both --workspace /path/to/workspace

# Non-default VS Code profile (prompts folder)
VSCODE_USER_PROMPTS_FOLDER="$HOME/.config/Code/User/profiles/<id>/prompts" \
  python3 install-vscode.py --target user

# Preview without writing
python3 install-vscode.py --workspace /path/to/workspace --dry-run -v

# Overwrite existing files/symlinks
python3 install-vscode.py --workspace /path/to/workspace --force
```

The installer:

- validates every skill (`name` matches the folder, matches
  `[a-z0-9-]{1,64}`, description present and at most 1024 chars);
- symlinks skills so edits propagate immediately;
- regenerates agents/prompts with a "do not edit" header;
- writes MCP, settings, and hooks without clobbering existing user values;
- skips an existing `copilot-instructions.md` unless `--force`.

Generated agents, prompts, and hook files are refreshed on every run. `--force`
is only needed for skill symlinks, the instructions file, MCP conflicts, and
settings conflicts.

`chat.useAgentsMdFile` is set to `false`: the generated always-on rules live
in `.github/copilot-instructions.md`, and a root `AGENTS.md` would be loaded
by both VS Code and opencode. Enable it only if you keep a separate
`AGENTS.md`.

## Automatic sync

Skills are symlinks and follow edits immediately. Agents, prompts,
instructions, hooks and MCP are generated copies, so they need a rerun of the
installer.

[`scripts/sync-vscode.sh`](../scripts/sync-vscode.sh) wraps that rerun. It
hashes `agents/`, `command/`, `config/`, `plugins/`, `vscode/`, the skill
folder names and `install-vscode.py`, then runs the installer only when one of
them changed. It always passes `--force`, so `copilot-instructions.md` is
refreshed too.

```bash
scripts/sync-vscode.sh                    # both scopes (current installation)
scripts/sync-vscode.sh --target workspace # only .github/ + .vscode/
scripts/sync-vscode.sh --check            # verify only, no writes
```

The repository ships a systemd user path + service unit, so a save in
`agents/` (or a `git checkout`) regenerates both scopes without a manual
command:

```bash
ln -sfn "$PWD/vscode/systemd/opencode-skills-vscode-sync.service" ~/.config/systemd/user/
ln -sfn "$PWD/vscode/systemd/opencode-skills-vscode-sync.path" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now opencode-skills-vscode-sync.path
```

The path unit uses `PathModified=`, which also fires when a file inside a
watched directory is saved. Runs are hash-gated, so a metadata-only write
does not rewrite the generated layer. Logs go to
`~/.cache/opencode-skills/sync-vscode.log`. Disable the watcher with
`systemctl --user disable --now opencode-skills-vscode-sync.path`.

The units assume the repository lives at `~/Progetti/Github/opencode-skills`;
edit the `%h/...` paths for a different checkout.

## The VS Code Migrations panel

**Ignore both migrations.** They move generated files away from the
opencode-skills source of truth.

| Migration | What it does | Why to ignore it |
|-----------|--------------|------------------|
| Convert Prompt to Skills (3) | Deletes `.github/prompts/*.prompt.md` (to trash) and creates `.github/skills/<name>/SKILL.md` with `disable-model-invocation: true` | Prompts are generated from opencode `command/*.md`. After conversion the next installer run recreates the prompts, so you get a skill **and** a prompt with the same name. `/read-chunk` etc. keep working as prompts. |
| MCP Servers (3) | Moves the servers from `.vscode/mcp.json` to `.mcp.json` (portable format) | Optional: both formats work. If you prefer the portable file, install with `--mcp-format portable` instead of migrating, so the next run does not recreate `.vscode/mcp.json`. |

`--verify` detects a converted prompt (a skill whose name matches a generated
prompt) and reports it, so a migration never passes unnoticed.

### Choose the MCP format

```bash
python3 install-vscode.py --workspace /path/to/workspace                      # .vscode/mcp.json (default)
python3 install-vscode.py --workspace /path/to/workspace --mcp-format portable # .mcp.json
python3 install-vscode.py --workspace /path/to/workspace --mcp-format both     # keep both in sync
```

`--verify` accepts either file and warns when both exist.

## Workspace scope semantics

`.github/skills`, `.github/agents`, `.github/prompts`, `.github/hooks` and
`.github/copilot-instructions.md` are resolved **relative to the workspace
root only**. VS Code does not descend into subfolders, so a nested
`sub/.github` is never read.

Consequence: one installation per workspace root you actually open.

| Opened folder | Layer read |
|---------------|-----------|
| `~/Progetti` | `~/Progetti/.github` |
| `~/Progetti/Github` | `~/Progetti/Github/.github` |

`--verify` reports nested copies that are inside the workspace but ignored, so
duplicates are easy to spot and delete.

To avoid per-workspace copies entirely, use `--target user`: one installation
in `~/.copilot/` applies to every workspace.

## Agent picker visibility

`mode: primary` → `user-invocable: true`; `mode: subagent` → `user-invocable: false`.
So by default the picker shows only `router`, exactly like opencode where the
subagents are reached through delegation. The subagents stay available to the
model because `disable-model-invocation: false` is set.

To also list the specialists in the picker (direct `trade`, `coder`, ...):

```bash
python3 install-vscode.py --workspace /path/to/workspace --expose-subagents
```

Verify with the same flag, otherwise the check reports drift:

```bash
python3 install-vscode.py --verify --workspace /path/to/workspace --expose-subagents
```

## Verify the layer matches opencode

```bash
# Structural check: skills, agents, prompts, instructions, MCP, hooks
python3 install-vscode.py --verify --workspace /path/to/workspace
python3 install-vscode.py --verify --target user
```

Exit code `0` = no drift, `1` = something is missing or out of date. The output
also reports two runtime counters (`verifica-gate` firings from VS Code and
`graphify` hook sessions) that prove the hooks actually executed.

The check compares generated files byte-for-byte with what the installer would
produce now, so it also catches manual edits to `.github/agents/`,
`.github/prompts/`, or the hooks.

In-chat confirmation:

| Signal | Where | Expected |
|--------|-------|----------|
| Skills | type `/` in chat | 46 skills (`/python-venv`, `/graphify`, ...) + 3 prompts |
| Agents | agent picker in chat | `router`, `trade`, `coder`, `coder-planner`, `graphify-helper`, `pdf-reader`, `skill-updater`, `book-to-skill-agent` |
| MCP | MCP view / tools list | `headroom`, `trading`, `rea` running |
| Instructions | ask "which rules apply to Python files?" | cites `.github/instructions/python.instructions.md` |

## Agent tool mapping

| opencode | VS Code alias |
|----------|---------------|
| `bash` | `execute` |
| `read` | `read` |
| `glob`, `grep` | `search` |
| `write`, `edit` | `edit` |
| `webfetch` | `web` |
| `task` | `agent` |
| `todowrite` | `todo` |
| `headroom_*` | `headroom/*` |
| `trading_*` | `trading/*` |
| `skill`, `external_directory` | — (skills load on demand; no path sandbox) |

`permission`, `steps`, and `hidden` are opencode-only. Path-scoped permissions
(for example the router's `write` allow-list) cannot be expressed in VS Code, so
the router gets no `edit` tool.

## Models

`model` uses the display names from the OpenCode Go Copilot provider
(`DeepSeek V4.1 Flash`, `Qwen3.8 Flash`). If that provider is not installed, VS
Code falls back to the model selected in the picker.

## Hooks

Hooks require a trusted workspace and `chat.useHooks` (default `true`). Both
scripts are fail-open: parse/runtime errors return `{}` and never block the
chat.

- `verifica_gate.py` (`SubagentStop`): reads `transcript_path`, finds the last
  `assistant.message`, and blocks when `## VERIFICA` is missing. It honors
  `stop_hook_active` to prevent loops.
- `graphify_reminder.py` (`PreToolUse`): when `graphify-out/graph.json` exists
  and a shell command is about to run, injects the `graphify query` reminder
  once per session.

## Limitations

- `.opencode/` and `config/opencode.json` are ignored by VS Code; the generated
  layer is the VS Code equivalent.
- opencode plugin behavior (automatic compression, routing telemetry) is not
  reproduced; see the mapping table.
- Skill scripts that reference `~/.config/opencode/...` keep working because the
  opencode install is present. On a machine without opencode, adjust the paths
  or use `--target user`.
- Hook commands contain absolute paths. Rerun the installer after moving or
  renaming the workspace so the `cwd` and script paths stay valid.
- Regenerate after editing `agents/`, `command/`, or `config/opencode.json`:

  ```bash
  python3 install-vscode.py --workspace /path/to/workspace
  ```
