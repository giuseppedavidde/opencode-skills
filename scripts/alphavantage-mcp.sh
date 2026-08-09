#!/bin/bash
# Bootstrap per Alpha Vantage MCP Server
# Path risolti rispetto a $HOME — portabile su qualsiasi macchina
#
# La chiave API viene da:
#   1. ALPHA_VANTAGE_API_KEY (env var)
#   2. $HOME/.config/opencode/alpha_vantage_key.txt (file gitignorato)

KEY="${ALPHA_VANTAGE_API_KEY}"
if [ -z "$KEY" ]; then
  KEY_FILE="$HOME/.config/opencode/alpha_vantage_key.txt"
  if [ -f "$KEY_FILE" ]; then
    KEY=$(head -1 "$KEY_FILE")
  fi
fi

if [ -z "$KEY" ]; then
  echo '{"error":"ALPHA_VANTAGE_API_KEY not set. Set env var or create ~/.config/opencode/alpha_vantage_key.txt"}' >&2
  exit 1
fi

# Usa path assoluto per uvx — non dipende dalla PATH di opencode
UVX="$HOME/.local/bin/uvx"
if [ ! -x "$UVX" ]; then
  UVX="uvx"
fi

exec "$UVX" --from "marketdata-mcp-server" --with "mcp<1.25.0" marketdata-mcp "$KEY"
