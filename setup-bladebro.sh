#!/usr/bin/env bash
# Installa bladebro (stealth browser MCP) nella dir canonica per opencode
# e collega un binario Chrome stabile tramite symlink usato da opencode.json.
# Idempotente: se bladebro è già installato garantisce comunque il link Chrome.
# Al termine, riavvia opencode per usare il tool MCP bladebro.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/.local/share/opencode/bladebro-node"

echo "bladebro — Stealth Browser MCP Server"
echo "====================================="
echo ""

# ─── Rilevamento Chrome (primo match vince) ───
detect_chrome() {
    local c latest
    if [ -n "${CHROME_PATH:-}" ] && [ -x "${CHROME_PATH}" ]; then
        printf '%s\n' "$CHROME_PATH"
        return 0
    fi
    for c in chromium chromium-browser google-chrome google-chrome-stable; do
        if command -v "$c" >/dev/null 2>&1; then
            command -v "$c"
            return 0
        fi
    done
    latest="$(ls -1d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome 2>/dev/null | sort -V | tail -n1 || true)"
    if [ -n "$latest" ] && [ -x "$latest" ]; then
        printf '%s\n' "$latest"
        return 0
    fi
    return 1
}

# ─── Garantisce il symlink stabile $DIR/chrome ───
link_chrome() {
    local chrome
    if chrome="$(detect_chrome)"; then
        ln -sfn "$chrome" "$DIR/chrome"
        echo "Chrome collegato:"
        echo "  $DIR/chrome  ->  $chrome"
        return 0
    fi
    echo "⚠️  Nessun Chrome/Chromium trovato."
    echo "   Installa Chrome/Chromium (o imposta CHROME_PATH) e rilancia:"
    echo "     ./setup-bladebro.sh"
    return 1
}

if [ -f "$DIR/bin/bladebro" ]; then
    echo "bladebro gia installato."
    echo "  Dir: $DIR"
    echo ""
    link_chrome || true
    echo ""
    echo "Per reinstallare, rimuovi la dir e riavvia:"
    echo "  rm -rf $DIR"
    echo "  ./setup-bladebro.sh"
    echo ""
    echo "Riavvia opencode per usare il tool MCP bladebro."
    exit 0
fi

echo "Node: $(node --version 2>/dev/null || echo 'non trovato')"
echo ""
echo "Installazione bladebro in $DIR ..."
mkdir -p "$DIR"
npm install --prefix "$DIR" bladebro

echo ""
link_chrome || true

echo ""
echo "bladebro installato con successo!"
echo "  Dir: $DIR"
echo ""
echo "Riavvia opencode per attivare il tool MCP bladebro."
