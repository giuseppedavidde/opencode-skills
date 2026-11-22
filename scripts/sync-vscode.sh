#!/usr/bin/env bash
# Regenerate the VS Code Copilot layer from the opencode-skills sources.
#
# Skills are symlinks and follow edits immediately. Agents, prompts,
# instructions, hooks and MCP are generated copies, so they need a rerun.
# This script is hash-gated: it runs the installer only when a source file
# changed since the last successful run.
#
# Usage:
#   scripts/sync-vscode.sh [--target workspace|user|both] [--workspace PATH]
#                          [--check] [--quiet] [--expose-subagents|--no-expose-subagents]
#
#   --target     Which scope to regenerate (default: user). Use one scope only:
#                each scope is a native Copilot source, so two copies load
#                every agent, skill and hook two times.
#   --workspace  Workspace root that owns .github/ and .mcp.json
#                (workspace|both), or whose legacy .vscode/mcp.json the user
#                target migrates to the root .mcp.json.
#   --check      Run the installer verification only; no writes.
#   --quiet      Print nothing unless the run fails.
#   --no-migrate-mcp  Keep the legacy VS Code MCP files unchanged.

set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

REPO_ROOT="$(cd -- "$(dirname -- "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/opencode-skills"
LOG_FILE="$STATE_DIR/sync-vscode.log"
PYTHON="${PYTHON:-$(command -v python3 || echo /usr/bin/python3)}"

target="user"
workspace="${VSCODE_WORKSPACE:-}"
check=0
quiet=0
migrate_mcp=1
# Keep the specialist subagents in the agent picker. This matches the
# installer default; EXPOSE_SUBAGENTS=0 writes `user-invocable: false` and
# leaves `router` as the only visible agent.
expose_subagents="${EXPOSE_SUBAGENTS:-1}"

usage() {
    cat <<'EOF'
Regenerate the VS Code Copilot layer from the opencode-skills sources.

Usage:
  scripts/sync-vscode.sh [--target workspace|user|both] [--workspace PATH]
                         [--check] [--quiet]
                         [--expose-subagents | --no-expose-subagents]

  --target     Which scope to regenerate (default: user). Use one scope only.
  --workspace  Workspace root that owns .github/ and .mcp.json
               (workspace|both), or whose legacy .vscode/mcp.json the user
               target migrates to the root .mcp.json.
  --check      Run the installer verification only; no writes.
  --quiet      Print nothing unless the run fails.
  --no-migrate-mcp  Keep the legacy VS Code MCP files unchanged.
  --expose-subagents     List the specialist subagents in the agent picker
                         (default; EXPOSE_SUBAGENTS=0 restores router-only).
  --no-expose-subagents  Show only the primary agents in the picker.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)          target="${2:?missing value for --target}"; shift 2 ;;
        --target=*)        target="${1#*=}"; shift ;;
        --workspace)       workspace="${2:?missing value for --workspace}"; shift 2 ;;
        --workspace=*)     workspace="${1#*=}"; shift ;;
        --check)           check=1; shift ;;
        --quiet)           quiet=1; shift ;;
        --no-migrate-mcp)  migrate_mcp=0; shift ;;
        --expose-subagents)    expose_subagents=1; shift ;;
        --no-expose-subagents) expose_subagents=0; shift ;;
        -h|--help)         usage; exit 0 ;;
        *) echo "sync-vscode: unknown option: $1" >&2; exit 2 ;;
    esac
done

case "$target" in
    workspace|user|both) ;;
    *) echo "sync-vscode: invalid --target: $target" >&2; exit 2 ;;
esac

if [[ "$target" != "user" && -z "$workspace" ]]; then
    echo "sync-vscode: --target $target needs --workspace PATH" >&2
    exit 2
fi

# The supported layout is the native ~/.copilot folder. A workspace .github
# symlink would make a workspace write land outside the workspace, so refuse it.
if [[ "$target" != "user" && -L "$workspace/.github" ]]; then
    printf 'sync-vscode: %s is a symlink (%s); a workspace write would land outside the workspace\n' \
        "$workspace/.github" "$(readlink -f "$workspace/.github")" >&2
    exit 2
fi

installer_args=(--target "$target")
if [[ -n "$workspace" ]]; then
    installer_args+=(--workspace "$workspace")
fi
if [[ "$expose_subagents" != "0" ]]; then
    installer_args+=(--expose-subagents)
else
    installer_args+=(--no-expose-subagents)
fi
if [[ "$migrate_mcp" == "0" ]]; then
    installer_args+=(--no-migrate-mcp)
fi

if (( check )); then
    exec "$PYTHON" "$REPO_ROOT/install-vscode.py" --verify "${installer_args[@]}"
fi

# Remove frozen extension MCP entries (Pylance) from the VS Code agent-host
# snapshots. A frozen localhost port fails after the extension restarts. This
# runs on every invocation, because a snapshot goes stale on each VS Code
# restart, not only when a workflow source changes.
if [[ -x "$REPO_ROOT/scripts/vscode-mcp-clean.py" ]]; then
    "$REPO_ROOT/scripts/vscode-mcp-clean.py" >/dev/null 2>&1 || true
fi

mkdir -p "$STATE_DIR"
stamp="$STATE_DIR/layer-${target}-$(printf '%s' "$workspace" | sha256sum | cut -c1-12).stamp"

fingerprint() {
    {
        printf '%s\n' "$REPO_ROOT/install-vscode.py"
        printf '%s\n' "$REPO_ROOT/scripts/sync-vscode.sh"
        find "$REPO_ROOT/agents" "$REPO_ROOT/command" "$REPO_ROOT/config" \
             "$REPO_ROOT/plugins" "$REPO_ROOT/vscode" \
             -type f -printf '%p %s %T@\n' 2>/dev/null
        find "$REPO_ROOT/skills" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null
    } | sort | sha256sum | cut -d' ' -f1
}

current="$(fingerprint)"
if [[ -f "$stamp" ]] && [[ "$(<"$stamp")" == "$current" ]]; then
    (( quiet )) || echo "sync-vscode: layer is up to date ($current)"
    exit 0
fi

set +e
# No --force: generated files refresh by ownership; files of the user stay.
output="$("$PYTHON" "$REPO_ROOT/install-vscode.py" "${installer_args[@]}" 2>&1)"
status=$?
set -e

if [[ -f "$LOG_FILE" ]] && (( $(stat -c%s "$LOG_FILE") > 1048576 )); then
    tail -n 500 "$LOG_FILE" >"$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

{
    printf '=== %s target=%s workspace=%s\n' "$(date -Is)" "$target" "$workspace"
    printf '%s\n' "$output"
} >>"$LOG_FILE"

if (( status != 0 )); then
    echo "sync-vscode: installer failed (exit $status); see $LOG_FILE" >&2
    exit "$status"
fi

printf '%s\n' "$current" >"$stamp"
if (( ! quiet )); then
    echo "sync-vscode: layer updated ($current)"
    printf '%s\n' "$output" | tail -n 5
fi

# Apply the workflow agent/model as the VS Code startup selection. This only
# works while VS Code is closed; the helper exits 2 otherwise and never fails
# the sync.
if [[ -x "$REPO_ROOT/scripts/vscode-preselect.py" ]]; then
    "$REPO_ROOT/scripts/vscode-preselect.py" >/dev/null 2>&1 || true
fi
