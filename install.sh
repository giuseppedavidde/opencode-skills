#!/usr/bin/env bash
# Quick-install opencode skills into ~/.config/opencode/
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install opencode skills and optional config files.

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

# Install skills
SKILLS_SRC="$REPO_DIR/skills"
if [[ -d "$SKILLS_SRC" ]]; then
    echo "Installing skills..."
    mkdir -p "$CONFIG_DIR/skills"
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
            if [[ -e "$target" ]]; then
                echo "  SKIP  $name  (already exists)"
            else
                ln -s "$item" "$target"
                echo "  LINK  $name"
            fi
        done
    fi
fi

# Install plugins
PLUGINS_SRC="$REPO_DIR/plugins"
if [[ -d "$PLUGINS_SRC" ]]; then
    echo "Installing plugins..."
    mkdir -p "$CONFIG_DIR/.opencode/plugins"
    if $FORCE; then
        for item in "$PLUGINS_SRC"/*; do
            name=$(basename "$item")
            target="$CONFIG_DIR/.opencode/plugins/$name"
            rm -rf "$target" 2>/dev/null || true
            ln -sf "$item" "$target"
        done
    else
        for item in "$PLUGINS_SRC"/*; do
            name=$(basename "$item")
            target="$CONFIG_DIR/.opencode/plugins/$name"
            if [[ -e "$target" ]]; then
                echo "  SKIP  $name  (already exists)"
            else
                ln -s "$item" "$target"
                echo "  LINK  $name"
            fi
        done
    fi
fi

# Install config files (optional, won't overwrite unless --force)
CONFIG_SRC="$REPO_DIR/config"
if [[ -d "$CONFIG_SRC" ]]; then
    echo "Installing config files..."
    for item in "$CONFIG_SRC"/*; do
        name=$(basename "$item")
        target="$CONFIG_DIR/$name"
        if [[ -e "$target" ]] && ! $FORCE; then
            echo "  SKIP  $name  (already exists)"
        else
            rm -rf "$target" 2>/dev/null || true
            ln -s "$item" "$target"
            echo "  LINK  $name"
        fi
    done
fi

echo "Done."

# Offer headroom installation
HEADROOM_SH="$REPO_DIR/setup-headroom.sh"
if [[ -x "$HEADROOM_SH" ]]; then
    echo ""
    echo "Vuoi installare anche headroom (compressione token 60-95%)?"
    read -r -p "  [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        "$HEADROOM_SH"
    else
        echo "  Salta headroom. Puoi installarlo dopo con: ./setup-headroom.sh"
    fi
fi
