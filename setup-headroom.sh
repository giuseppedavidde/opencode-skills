#!/usr/bin/env bash
# Installa headroom nel venv canonico per opencode
# Dopo l'installazione, riavvia opencode per usare i tool di compressione
set -euo pipefail

VENV="$HOME/.local/share/opencode/headroom-venv"

echo "Headroom — Compression Layer per OpenCode"
echo "========================================="
echo ""

if [ -f "$VENV/bin/headroom" ]; then
    echo "headroom già installato:"
    echo "  $($VENV/bin/headroom --version)"
    echo ""
    echo "  Venv: $VENV"
    echo ""
    echo "Per reinstallare, rimuovi il venv e riavvia:"
    echo "  rm -rf $VENV"
    echo "  ./setup-headroom.sh"
    exit 0
fi

echo "Creazione virtual environment in $VENV ..."
python3 -m venv "$VENV"

echo "Installazione headroom-ai[mcp] ..."
"$VENV/bin/pip" install "headroom-ai[mcp]" --quiet

echo ""
echo "✅ headroom installato con successo!"
echo "  $($VENV/bin/headroom --version)"
echo "  Venv: $VENV"
echo ""
echo "Riavvia opencode per attivare i tool:"
echo "  - headroom_compress  (comprime output dei tool)"
echo "  - headroom_retrieve  (recupera originali)"
echo "  - headroom_stats     (statistiche sessione)"
echo ""
echo "I tool sono usati automaticamente — vedi AGENTS.md per le regole."
