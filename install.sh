#!/usr/bin/env bash
# One-command installer for the opencode-skills workflow (opencode + VS Code).
#
#   git clone --recursive https://github.com/giuseppedavidde/opencode-skills.git
#   cd opencode-skills && ./install.sh
#
# The installer is idempotent: run it again after a `git pull` or after you move
# the repository. It never deletes a real file. With --force, a file that is in
# the way goes to ~/.cache/opencode-skills/backup/<timestamp>/ first.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_REAL="$(cd "$REPO_DIR" && pwd -P)"
CONFIG_DIR="${OPENCODE_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode}"
# config/opencode.json reaches the repository through this fixed link.
ANCHOR="$HOME/.config/opencode/opencode-skills"
BACKUP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/opencode-skills/backup/$(date +%Y%m%d-%H%M%S)"
PYTHON="${PYTHON:-$(command -v python3 || true)}"

FORCE=false
DRY_RUN=false
WITH_VSCODE=true
WITH_MCP=true
WITH_REA=false
WITH_SYSTEMD=false
ASSUME_YES=false
WARNINGS=()

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install the opencode-skills workflow for opencode and for VS Code (Copilot):
  1. initialize the git submodules
  2. link skills, agents, commands, config, scripts into $CONFIG_DIR
  3. set up the Python MCP runtimes (headroom, trading)
  4. generate the VS Code layer in ~/.copilot (install-vscode.py --target user)

Options:
  -f, --force        Replace real files that are in the way (backup first)
  -n, --dry-run      Print the plan; change nothing
      --no-vscode    Do not generate the VS Code layer
      --no-mcp       Do not set up the MCP runtimes (headroom, trading)
      --with-rea     Also set up the rea MCP (Node.js >= 22, separate repo)
      --with-systemd Regenerate the VS Code layer automatically after edits
  -y, --yes          Do not ask questions (CI, scripts)
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE=true ;;
        -n|--dry-run) DRY_RUN=true ;;
        --no-vscode) WITH_VSCODE=false ;;
        --no-mcp) WITH_MCP=false ;;
        --with-rea) WITH_REA=true ;;
        --with-systemd) WITH_SYSTEMD=true ;;
        -y|--yes) ASSUME_YES=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "install.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

say() { printf '%s\n' "$*"; }
warn() { WARNINGS+=("$*"); printf '  WARN  %s\n' "$*" >&2; }
run() { if $DRY_RUN; then say "  DRY   $*"; else "$@"; fi; }
ask() {
    # ask <question>: true only on an interactive "y" answer
    if $ASSUME_YES || $DRY_RUN || [[ ! -t 0 ]]; then return 1; fi
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]]
}

backup_path() {
    local target="$1" dest="$BACKUP_DIR$1"
    run mkdir -p "$(dirname "$dest")"
    run mv "$target" "$dest"
    say "  BACKUP $target -> $dest"
}

# inside_repo <path>: true when the path resolves to the repository or into it.
inside_repo() {
    local real
    real="$(readlink -f -- "$1" 2>/dev/null || true)"
    [[ -n "$real" && ( "$real" == "$REPO_REAL" || "$real" == "$REPO_REAL"/* ) ]]
}

# link <source> <target>: create or repair a symlink; never delete a real file,
# and never move a file of the repository itself.
link() {
    local src="$1" target="$2"
    if [[ -L "$target" ]]; then
        if [[ "$(readlink "$target")" == "$src" ]]; then
            say "  OK    $target"
            return
        fi
        run ln -sfn "$src" "$target"
        say "  LINK  $target -> $src"
        return
    fi
    if [[ -e "$target" ]]; then
        if [[ "$target" -ef "$src" ]]; then
            say "  OK    $target (resolves to the same file)"
            return
        fi
        if inside_repo "$target"; then
            warn "$target resolves into the repository; kept (the installer never moves repository files)"
            return
        fi
        if ! $FORCE; then
            warn "$target exists and is not a symlink; kept (use --force to back it up and link)"
            return
        fi
        backup_path "$target"
    fi
    run mkdir -p "$(dirname "$target")"
    run ln -s "$src" "$target"
    say "  LINK  $target -> $src"
}

# prune <dir>: remove dangling links that point into this repository.
prune() {
    local dir="$1" entry dest
    [[ -d "$dir" ]] || return 0
    inside_repo "$dir" && return 0
    while IFS= read -r -d '' entry; do
        dest="$(readlink "$entry")"
        if [[ "$dest" == "$REPO_DIR"/* && ! -e "$entry" ]]; then
            run rm "$entry"
            say "  PRUNE $entry (target removed from the repository)"
        fi
    done < <(find "$dir" -type l -print0)
}

check_prerequisites() {
    say "Prerequisites:"
    local tool
    for tool in git python3 node opencode code; do
        if command -v "$tool" >/dev/null 2>&1; then
            say "  OK    $tool"
        else
            case "$tool" in
                git|python3) warn "$tool not found: it is necessary for this installer" ;;
                node) say "  --    node (only for the rea MCP server)" ;;
                opencode) say "  --    opencode CLI not found (install it from https://opencode.ai)" ;;
                code) say "  --    VS Code CLI not found (only necessary for VS Code)" ;;
            esac
        fi
    done
    if [[ -n "${XDG_CONFIG_HOME:-}" && "${XDG_CONFIG_HOME%/}" != "$HOME/.config" ]]; then
        warn "XDG_CONFIG_HOME is $XDG_CONFIG_HOME; config/opencode.json expects the anchor at $ANCHOR"
    fi
}

init_submodules() {
    say "Submodules:"
    if [[ ! -e "$REPO_DIR/.git" ]]; then
        warn "not a git checkout: submodules not initialized (clone with git clone --recursive)"
        return
    fi
    local missing
    missing="$(git -C "$REPO_DIR" submodule status 2>/dev/null | grep -c '^-' || true)"
    if [[ "${missing:-0}" == "0" ]]; then
        say "  OK    all submodules initialized"
        return
    fi
    say "  INIT  $missing submodule(s)"
    if ! run git -C "$REPO_DIR" submodule update --init --recursive; then
        warn "git submodule update failed: the skills that link into submodules stay empty"
    fi
}

install_opencode_layer() {
    say "opencode layer ($CONFIG_DIR):"
    if inside_repo "$CONFIG_DIR"; then
        warn "$CONFIG_DIR is inside the repository: clone opencode-skills into another folder (opencode layer skipped)"
        return
    fi
    run mkdir -p "$CONFIG_DIR"
    if [[ ! -L "$ANCHOR" && "$REPO_DIR" -ef "$ANCHOR" ]]; then
        say "  OK    $ANCHOR (the repository itself)"
    else
        link "$REPO_DIR" "$ANCHOR"
    fi
    link "$REPO_DIR/skills" "$CONFIG_DIR/skills"
    local file rel
    for file in "$REPO_DIR"/agents/*.md; do
        link "$file" "$CONFIG_DIR/agents/$(basename "$file")"
    done
    for file in "$REPO_DIR"/command/*.md; do
        link "$file" "$CONFIG_DIR/command/$(basename "$file")"
    done
    link "$REPO_DIR/config/AGENTS.md" "$CONFIG_DIR/AGENTS.md"
    link "$REPO_DIR/config/opencode.json" "$CONFIG_DIR/opencode.json"
    for file in "$REPO_DIR"/config/bin/*; do
        link "$file" "$CONFIG_DIR/bin/$(basename "$file")"
    done
    while IFS= read -r -d '' file; do
        rel="${file#"$REPO_DIR"/scripts/}"
        link "$file" "$CONFIG_DIR/scripts/$rel"
    done < <(find "$REPO_DIR/scripts" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' -print0 | sort -z)
    link "$REPO_DIR/routing-eval" "$CONFIG_DIR/routing-eval"
    link "$REPO_DIR/scripts/alphavantage-mcp.sh" "$HOME/.local/bin/alphavantage-mcp.sh"
    prune "$CONFIG_DIR/agents"
    prune "$CONFIG_DIR/command"
    prune "$CONFIG_DIR/scripts"
}

run_setup() {
    local script="$1"
    if $DRY_RUN; then
        say "  DRY   ./$script"
        return
    fi
    if ! "$REPO_DIR/$script"; then
        warn "./$script failed: fix the error above, then run it again"
    fi
}

setup_mcp_runtimes() {
    say "MCP runtimes:"
    if $WITH_MCP; then
        run_setup setup-headroom.sh
        run_setup setup-trading-mcp.sh
    else
        say "  SKIP  headroom, trading (--no-mcp)"
    fi
    if $WITH_REA || ask "Set up the rea MCP (reverse engineering, Node.js >= 22)?"; then
        run_setup setup-rea-mcp.sh
    else
        say "  SKIP  rea (use --with-rea)"
    fi
}

# check_trading_server: start the trading MCP server once; a missing package stops it at import time.
check_trading_server() {
    local python="$HOME/.local/share/opencode/trading-mcp-venv/bin/python"
    [[ -x "$python" ]] || return 0
    if $DRY_RUN; then
        say "  DRY   start check of the trading MCP server"
        return 0
    fi
    local output
    if output="$(cd /tmp && timeout 180 "$python" -c 'from trading_mcp.mcp import initialize_mcp; initialize_mcp()' 2>&1)"; then
        say "  OK    trading MCP server starts"
    else
        warn "the trading MCP server does not start: ${output##*$'\n'} (rerun ./setup-trading-mcp.sh)"
    fi
}

install_vscode_layer() {
    say "VS Code layer (~/.copilot):"
    if ! $WITH_VSCODE; then
        say "  SKIP  VS Code layer (--no-vscode)"
        return
    fi
    if [[ -z "$PYTHON" ]]; then
        warn "python3 not found: VS Code layer not installed"
        return
    fi
    local args=(--target user)
    $FORCE && args+=(--force)
    $DRY_RUN && args+=(--dry-run)
    if ! "$PYTHON" "$REPO_DIR/install-vscode.py" "${args[@]}"; then
        warn "install-vscode.py failed"
    fi
}

install_systemd_sync() {
    $WITH_SYSTEMD || return 0
    say "Automatic VS Code sync (systemd user units):"
    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemctl not found: run scripts/sync-vscode.sh after each change"
        return
    fi
    local unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" unit
    for unit in opencode-skills-vscode-sync.service opencode-skills-vscode-sync.path; do
        link "$REPO_DIR/vscode/systemd/$unit" "$unit_dir/$unit"
    done
    run systemctl --user daemon-reload || warn "systemctl --user daemon-reload failed"
    run systemctl --user enable --now opencode-skills-vscode-sync.path \
        || warn "could not enable opencode-skills-vscode-sync.path"
}

print_summary() {
    say ""
    if (( ${#WARNINGS[@]} )); then
        say "Warnings (${#WARNINGS[@]}):"
        local item
        for item in "${WARNINGS[@]}"; do say "  ! $item"; done
        say ""
    fi
    cat <<EOF
Done$($DRY_RUN && printf ' (dry run: nothing changed)').

Steps that the installer cannot do for you:
  1. opencode provider login (once per machine):   opencode auth login
  2. API keys (only for the skills that use them):
       echo 'YOUR_KEY' > ~/.config/opencode/alpha_vantage_key.txt
       ./scripts/decrypt_secrets.sh        # FMP and other keys (passphrase)
  3. Restart opencode. In VS Code, start a NEW chat session (Copilot harness).
     For the OpenCode Go models in VS Code, install the extension
     OnesoftQwQ.opencode-go-copilot-provider and set its API key.
  4. Optional MCP servers, then rerun ./install.sh:
       rea:     ./install.sh --with-rea
       browse:  curl -fsSL https://opencode.ai/browse/install | bash
  5. Optional check:  python3 install-vscode.py --verify --target user

Rerun ./install.sh after a git pull or after you move this repository.
EOF
}

say "opencode-skills installer"
say "  repository: $REPO_DIR"
$DRY_RUN && say "  dry run: nothing changes"
say ""
check_prerequisites
init_submodules
install_opencode_layer
setup_mcp_runtimes
check_trading_server
install_vscode_layer
install_systemd_sync
print_summary
