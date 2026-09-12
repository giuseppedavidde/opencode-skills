#!/usr/bin/env bash
# Quick-install opencode skills into ~/.config/opencode/
# Full portable installation — agents, commands, config, MCP, plugins, skills.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install opencode skills, agents, commands, plugins, config and alphavantage
bootstrap into ~/.config/opencode/ for a complete portable setup.

Options:
  -f, --force       Overwrite existing files
  -h, --help        Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE=true; shift ;;
        -h|--help)  usage ;;
        *)          echo "Unknown option: $1"; usage ;;
    esac
done

# ─── Submodule check ───
check_submodules() {
    local dirs=(
        "skills/graphify-src"
        "skills/karpathy-llm-wiki-src"
        "src/book-to-skill-src"
        "skills/quant-mind-src"
    )
    local missing=false
    for d in "${dirs[@]}"; do
        # Dir exists but is empty, or doesn't exist
        if [[ -d "$REPO_DIR/$d" ]]; then
            if [[ -z "$(ls -A "$REPO_DIR/$d" 2>/dev/null)" ]]; then
                echo "  VUOTO: $d" >&2
                missing=true
            fi
        else
            echo "  ASSENTE: $d" >&2
            missing=true
        fi
    done
    if $missing; then
        echo "" >&2
        echo "ATTENZIONE: Submodule git non inizializzati!" >&2
        echo "Esegui: git submodule update --init --recursive" >&2
        echo "" >&2
    fi
}

check_submodules

mkdir -p "$CONFIG_DIR"

# ─── Link helper ───
# link_item <src> <target>
#   - target assente        → crea symlink
#   - target è symlink      → ripara/relinka (anche rotto)
#   - target file/dir reale → SKIP (mai cancellare, anche con --force)
link_item() {
    local src="$1"
    local target="$2"
    local name
    name="$(basename "$target")"

    if [[ -L "$target" ]]; then
        ln -sfn "$src" "$target"
        echo "  LINK  $name"
    elif [[ -e "$target" ]]; then
        echo "  SKIP  $name  (già presente, non symlink)"
    else
        ln -s "$src" "$target"
        echo "  LINK  $name"
    fi
}

# ─── Skills (whole-dir symlink, come routing-eval) ───
SKILLS_SRC="$REPO_DIR/skills"
if [[ -d "$SKILLS_SRC" ]]; then
    echo "Installing skills..."
    target="$CONFIG_DIR/skills"
    if [[ -L "$target" ]]; then
        ln -sfn "$SKILLS_SRC" "$target"
        echo "  LINK  skills (whole-dir)"
    elif [[ -e "$target" ]]; then
        echo "  SKIP  skills  (directory reale: non la cancello)"
    else
        ln -s "$SKILLS_SRC" "$target"
        echo "  LINK  skills (whole-dir)"
    fi
fi

# ─── Agents ───
AGENTS_SRC="$REPO_DIR/agents"
if [[ -d "$AGENTS_SRC" ]]; then
    echo "Installing agents..."
    mkdir -p "$CONFIG_DIR/agents"
    for item in "$AGENTS_SRC"/*; do
        link_item "$item" "$CONFIG_DIR/agents/$(basename "$item")"
    done
fi

# ─── Commands ───
COMMANDS_SRC="$REPO_DIR/command"
if [[ -d "$COMMANDS_SRC" ]]; then
    echo "Installing commands..."
    mkdir -p "$CONFIG_DIR/command"
    for item in "$COMMANDS_SRC"/*; do
        link_item "$item" "$CONFIG_DIR/command/$(basename "$item")"
    done
fi

# ─── Plugins (auto-discovery via .opencode/plugins) ───
PLUGINS_SRC="$REPO_DIR/plugins"
if [[ -d "$PLUGINS_SRC" ]]; then
    echo "Installing plugins..."
    mkdir -p "$CONFIG_DIR/.opencode/plugins"
    for item in "$PLUGINS_SRC"/*; do
        link_item "$item" "$CONFIG_DIR/.opencode/plugins/$(basename "$item")"
    done
fi

# ─── Config (AGENTS.md, opencode.json) ───
CONFIG_SRC="$REPO_DIR/config"
if [[ -d "$CONFIG_SRC" ]]; then
    echo "Installing config files..."
    mkdir -p "$CONFIG_DIR"
    for item in "$CONFIG_SRC"/*; do
        name=$(basename "$item")
        # Skip encrypted secrets file
        [[ "$name" == "secrets.env.enc" ]] && continue
        link_item "$item" "$CONFIG_DIR/$name"
    done
fi

# ─── Routing Eval ───
ROUTING_EVAL_SRC="$REPO_DIR/routing-eval"
if [[ -d "$ROUTING_EVAL_SRC" ]]; then
    echo "Installing routing-eval..."
    target="$CONFIG_DIR/routing-eval"
    if $FORCE; then
        rm -rf "$target" 2>/dev/null || true
        ln -sfn "$ROUTING_EVAL_SRC" "$target"
        echo "  LINK  routing-eval"
    elif [[ -e "$target" || -L "$target" ]]; then
        echo "  SKIP  routing-eval  (already exists)"
    else
        ln -sfn "$ROUTING_EVAL_SRC" "$target"
        echo "  LINK  routing-eval"
    fi
fi

# ─── Alphavantage bootstrap ───
ALPHA_SRC="$REPO_DIR/scripts/alphavantage-mcp.sh"
if [[ -f "$ALPHA_SRC" ]]; then
    echo "Installing alphavantage bootstrap..."
    ALPHA_DEST="$HOME/.local/bin/alphavantage-mcp.sh"
    mkdir -p "$HOME/.local/bin"
    if $FORCE; then
        rm -rf "$ALPHA_DEST" 2>/dev/null || true
        ln -sf "$ALPHA_SRC" "$ALPHA_DEST"
        chmod +x "$ALPHA_SRC"
        echo "  LINK  alphavantage-mcp.sh  →  $ALPHA_DEST"
    elif [[ -e "$ALPHA_DEST" ]]; then
        echo "  SKIP  alphavantage-mcp.sh  (already exists)"
    else
        ln -s "$ALPHA_SRC" "$ALPHA_DEST"
        chmod +x "$ALPHA_SRC"
        echo "  LINK  alphavantage-mcp.sh  →  $ALPHA_DEST"
    fi
fi

echo "Done."
echo ""

# ─── Next steps ───
cat <<NEXT
PROSSIMI PASSI:
1. Headroom (compressione token):
   ./setup-headroom.sh

2. Trading MCP (analisi mercati):
   ./setup-trading-mcp.sh

3. Alphavantage API key:
   echo 'YOUR_KEY' > ~/.config/opencode/alpha_vantage_key.txt
   oppure: export ALPHA_VANTAGE_API_KEY='YOUR_KEY'

4. Segreti (FMP, altre chiavi):
   ./scripts/decrypt_secrets.sh
   oppure crea: ~/.config/opencode/fmp_api_key.txt

5. Riavvia opencode per applicare la configurazione

NOTA: routing-stats usa routing-eval incluso nella repo (symlink
  ~/.config/opencode/routing-eval). Dipendenze:
  pip install -r "$REPO_DIR/routing-eval/requirements.txt" nel venv del comando
  (es. /tmp/opencode/.venv).

Se sposti la repo, rilancia: python3 install.py (ripara i symlink rotti senza --force)
NEXT
echo ""

# ─── Offer headroom ───
HEADROOM_SH="$REPO_DIR/setup-headroom.sh"
if [[ -x "$HEADROOM_SH" ]]; then
    echo "Vuoi installare anche headroom (compressione token 60-95%)?"
    read -r -p "  [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        "$HEADROOM_SH"
    else
        echo "  Salta headroom. Puoi installarlo dopo con: ./setup-headroom.sh"
    fi
fi

# ─── Offer trading-mcp ───
TRADING_MCP_SH="$REPO_DIR/setup-trading-mcp.sh"
if [[ -x "$TRADING_MCP_SH" ]]; then
    echo ""
    echo "Vuoi installare anche trading-mcp (analisi mercati via MCP)?"
    read -r -p "  [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        "$TRADING_MCP_SH"
    else
        echo "  Salta trading-mcp. Puoi installarlo dopo con: ./setup-trading-mcp.sh"
    fi
fi
