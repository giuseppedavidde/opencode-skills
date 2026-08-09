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
        "skills/book-to-skill-src"
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

# ─── Skills ───
SKILLS_SRC="$REPO_DIR/skills"
if [[ -d "$SKILLS_SRC" ]]; then
    echo "Installing skills..."
    mkdir -p "$CONFIG_DIR/skills"
    SKIP_SKILLS="market-accumulation-scanner stock-crypto-analysis options-analysis options-strategy-suggestions market-data-fetch"
    if $FORCE; then
        for item in "$SKILLS_SRC"/*; do
            name=$(basename "$item")
            target="$CONFIG_DIR/skills/$name"
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
        done
    else
        for item in "$SKILLS_SRC"/*; do
            name=$(basename "$item")
            target="$CONFIG_DIR/skills/$name"
            if [[ " $SKIP_SKILLS " == *" $name "* ]]; then
                echo "  SKIP  $name  (replaced by trading MCP)"
                continue
            fi
            if [[ -e "$target" ]]; then
                echo "  SKIP  $name  (already exists)"
            else
                ln -s "$item" "$target"
                echo "  LINK  $name"
            fi
        done
    fi
fi

# ─── Agents ───
AGENTS_SRC="$REPO_DIR/agents"
if [[ -d "$AGENTS_SRC" ]]; then
    echo "Installing agents..."
    mkdir -p "$CONFIG_DIR/agents"
    for item in "$AGENTS_SRC"/*; do
        name=$(basename "$item")
        target="$CONFIG_DIR/agents/$name"
        if $FORCE; then
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
            echo "  LINK  $name"
        elif [[ -e "$target" ]]; then
            echo "  SKIP  $name  (already exists)"
        else
            ln -s "$item" "$target"
            echo "  LINK  $name"
        fi
    done
fi

# ─── Commands ───
COMMANDS_SRC="$REPO_DIR/command"
if [[ -d "$COMMANDS_SRC" ]]; then
    echo "Installing commands..."
    mkdir -p "$CONFIG_DIR/command"
    for item in "$COMMANDS_SRC"/*; do
        name=$(basename "$item")
        target="$CONFIG_DIR/command/$name"
        if $FORCE; then
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
            echo "  LINK  $name"
        elif [[ -e "$target" ]]; then
            echo "  SKIP  $name  (already exists)"
        else
            ln -s "$item" "$target"
            echo "  LINK  $name"
        fi
    done
fi

# ─── Plugins (auto-discovery via .opencode/plugins) ───
PLUGINS_SRC="$REPO_DIR/plugins"
if [[ -d "$PLUGINS_SRC" ]]; then
    echo "Installing plugins..."
    mkdir -p "$CONFIG_DIR/.opencode/plugins"
    for item in "$PLUGINS_SRC"/*; do
        name=$(basename "$item")
        target="$CONFIG_DIR/.opencode/plugins/$name"
        if $FORCE; then
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
            echo "  LINK  $name"
        elif [[ -e "$target" ]]; then
            echo "  SKIP  $name  (already exists)"
        else
            ln -s "$item" "$target"
            echo "  LINK  $name"
        fi
    done
fi

# ─── Config (AGENTS.md, opencode.json) ───
CONFIG_SRC="$REPO_DIR/config"
if [[ -d "$CONFIG_SRC" ]]; then
    echo "Installing config files..."
    for item in "$CONFIG_SRC"/*; do
        name=$(basename "$item")
        # Skip encrypted secrets file
        [[ "$name" == "secrets.env.enc" ]] && continue
        target="$CONFIG_DIR/$name"
        if $FORCE; then
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
            echo "  LINK  $name"
        elif [[ -e "$target" ]]; then
            echo "  SKIP  $name  (already exists)"
        else
            ln -s "$item" "$target"
            echo "  LINK  $name"
        fi
    done
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

NOTA: routing-stats richiede routing-eval clonato separatamente:
  git clone https://github.com/giuseppedavidde/routing-eval.git \\
    ~/Progetti/Github/routing-eval
  pip install -r ~/Progetti/Github/routing-eval/requirements.txt
  export ROUTING_EVAL_DIR="\$HOME/Progetti/Github/routing-eval"

Se sposti la repo, rilancia: ./install.sh --force
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
