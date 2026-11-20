#!/usr/bin/env bash
# Installa o aggiorna trading-mcp nel venv canonico per opencode.
# Ogni esecuzione: crea il venv se manca, installa le dipendenze bloccate
# (mcp/requirements.lock), reinstalla il pacchetto editable da questo clone
# e verifica che il server si avvii. Dopo l'installazione riavvia opencode.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.local/share/opencode/trading-mcp-venv"
LOCK="$REPO_DIR/mcp/requirements.lock"
PIP_FLAGS=(--disable-pip-version-check --quiet)

echo "trading-mcp — Market Analysis MCP Server"
echo "========================================="
echo ""

fail() {
    echo "" >&2
    echo "ERRORE: $1" >&2
    shift
    for line in "$@"; do
        echo "  $line" >&2
    done
    exit 1
}

if [ ! -f "$LOCK" ]; then
    fail "lockfile non trovato: $LOCK" \
        "Rigeneralo con: uv pip compile mcp/pyproject.toml --universal --python-version 3.11 -o mcp/requirements.lock"
fi

# 1. Venv: crealo solo se manca.
if [ ! -x "$VENV/bin/python" ]; then
    command -v python3 >/dev/null 2>&1 || fail "python3 non trovato nel PATH" "Installa Python 3.11 o successivo."
    echo "Creazione virtual environment in $VENV ..."
    mkdir -p "$(dirname "$VENV")"
    python3 -m venv "$VENV" || fail "creazione del venv fallita" \
        "Su Debian/Ubuntu installa il modulo venv: sudo apt install python3-venv"
else
    echo "Venv esistente: $VENV"
    # The editable install records the absolute clone path: relink it after a move.
    current="$("$VENV/bin/python" -c 'import importlib.util, os; s = importlib.util.find_spec("trading_mcp"); print(os.path.realpath(os.path.dirname(s.origin)) if s and s.origin else "")' 2>/dev/null || true)"
    expected="$(cd "$REPO_DIR/mcp/src/trading_mcp" && pwd -P)"
    if [ -n "$current" ] && [ "$current" != "$expected" ]; then
        echo "trading-mcp usa il codice di un altro clone ($current)."
        echo "Reinstallazione editable da $REPO_DIR/mcp ..."
    fi
fi

# 2. Dipendenze bloccate: a ogni esecuzione, così un nuovo pin arriva sempre nel venv.
echo "Installazione delle dipendenze da mcp/requirements.lock ..."
"$VENV/bin/python" -m pip install "${PIP_FLAGS[@]}" -r "$LOCK" \
    || fail "installazione delle dipendenze fallita" "Controlla la rete e riesegui ./setup-trading-mcp.sh"

# 3. Il pacchetto stesso, editable, senza toccare le dipendenze bloccate.
echo "Installazione di trading-mcp-server (editable, --no-deps) da $REPO_DIR/mcp ..."
"$VENV/bin/python" -m pip install "${PIP_FLAGS[@]}" --no-deps -e "$REPO_DIR/mcp" \
    || fail "installazione editable fallita"

expected="$(cd "$REPO_DIR/mcp/src/trading_mcp" && pwd -P)"
current="$("$VENV/bin/python" -c 'import importlib.util, os; s = importlib.util.find_spec("trading_mcp"); print(os.path.realpath(os.path.dirname(s.origin)) if s and s.origin else "")' 2>/dev/null || true)"
if [ "$current" != "$expected" ]; then
    fail "il venv usa ancora il codice di ${current:-nessun clone}, non di $expected"
fi
echo "trading-mcp ora usa $expected"

# 4. Smoke test: il server deve avviarsi e registrare i tool (nessuna richiesta di rete).
echo "Verifica di avvio del server ..."
if ! smoke="$(cd / && TRADING_SKILLS_DIR="${TRADING_SKILLS_DIR:-$REPO_DIR/skills}" \
        TRADING_TICKERS_DIR="${TRADING_TICKERS_DIR:-$REPO_DIR/skills/market-accumulation-scanner/data}" \
        "$VENV/bin/python" -c '
import asyncio
from trading_mcp.mcp import initialize_mcp
server = initialize_mcp()
for tool in sorted(asyncio.run(server.list_tools()), key=lambda t: t.name):
    print(tool.name)
' 2>&1)"; then
    fail "il server trading-mcp non si avvia" \
        "Ultime righe dell'errore:" \
        "$(printf '%s\n' "$smoke" | tail -n 5)" \
        "Correggi l'errore e riesegui ./setup-trading-mcp.sh"
fi
tools="$(printf '%s\n' "$smoke" | grep -E '^[a-z_]+$' || true)"
count="$(printf '%s\n' "$tools" | grep -c . || true)"
if [ "$count" -eq 0 ]; then
    fail "il server si avvia ma non registra nessun tool" "$(printf '%s\n' "$smoke" | tail -n 5)"
fi

echo ""
echo "trading-mcp installato con successo!"
echo "  Venv: $VENV"
echo "  Dipendenze: $LOCK"
echo ""
echo "Riavvia opencode per attivare i $count tool MCP:"
printf '%s\n' "$tools" | sed 's/^/  - /'
