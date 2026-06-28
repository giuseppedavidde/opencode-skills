#!/usr/bin/env bash
# Installa trading-mcp nel venv canonico per opencode
# Dopo l'installazione, riavvia opencode per usare i tool di analisi
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.local/share/opencode/trading-mcp-venv"

echo "trading-mcp — Market Analysis MCP Server"
echo "========================================="
echo ""

if [ -f "$VENV/bin/trading-mcp" ]; then
    echo "trading-mcp gia installato."
    echo "  Venv: $VENV"
    echo ""
    echo "Per reinstallare, rimuovi il venv e riavvia:"
    echo "  rm -rf $VENV"
    echo "  ./setup-trading-mcp.sh"
    exit 0
fi

echo "Creazione virtual environment in $VENV ..."
python3 -m venv "$VENV"

echo "Installazione trading-mcp-server in editable mode ..."
"$VENV/bin/pip" install -e "$REPO_DIR/mcp" --quiet

echo ""
echo "trading-mcp installato con successo!"
echo "  Venv: $VENV"
echo ""
echo "Riavvia opencode per attivare i 9 tool MCP:"
echo ""
echo "  DATA FETCH:"
echo "  - fetch_stock_data      (OHLCV + fondamentali da yfinance)"
echo "  - fetch_crypto_data     (CoinGecko + yfinance)"
echo "  - fetch_options_chain   (catena opzioni + Greeks + IV)"
echo ""
echo "  ANALYSIS:"
echo "  - scan_market           (scanner accumulazione multi-mercato)"
echo "  - analyze_stock          (analisi completa Wyckoff+VP+VPA)"
echo "  - analyze_options        (analisi opzioni: Greeks, payoff)"
echo ""
echo "  KNOWLEDGE:"
echo "  - get_macro_context     (VIX, DXY, regime, pesi dinamici)"
echo "  - get_skill_knowledge    (conoscenza on-demand dai SKILL.md)"
echo "  - suggest_options_strategy (strategia opzioni consigliata)"
