#!/usr/bin/env bash
# Installa il repo rea (https://github.com/morluto/rea) e prepara la build servita
# dal wrapper MCP config/bin/rea-mcp.sh. Idempotente: rieseguibile in sicurezza.
# Al termine, riavvia opencode per usare i tool rea.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$HOME/.config/opencode/bin/rea-mcp.sh"
[ -x "$WRAPPER" ] || WRAPPER="$REPO_DIR/config/bin/rea-mcp.sh"

TARGET="${1:-${REA_REPO:-$HOME/Progetti/Github/rea}}"
# Alternativa ssh (se hai una chiave configurata):
#   git clone git@github.com:morluto/rea.git "$TARGET"
CLONE_URL="https://github.com/morluto/rea.git"

echo "rea MCP (reverse engineering / app analysis)"
echo "============================================"
echo "  Target: $TARGET"
echo ""

# ─── Node version (repo engines: ^22.23.4 || ^24.22.1 || >=26.12.1) ───
if ! command -v node >/dev/null 2>&1; then
    echo "ERRORE: node non trovato. rea richiede Node.js >= 22 (^22.23.4 || ^24.22.1 || >=26.12.1)." >&2
    exit 1
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
NODE_MINOR="$(node -p 'process.versions.node.split(".")[1]')"
node_ok=0
if [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -ge 23 ]; then node_ok=1; fi
if [ "$NODE_MAJOR" -eq 24 ] && [ "$NODE_MINOR" -ge 22 ]; then node_ok=1; fi
if [ "$NODE_MAJOR" -eq 26 ] && [ "$NODE_MINOR" -ge 12 ]; then node_ok=1; fi
if [ "$NODE_MAJOR" -gt 26 ]; then node_ok=1; fi
if [ "$node_ok" -ne 1 ]; then
    echo "ERRORE: Node.js $(node --version) non supportato da rea." >&2
    echo "        richiesto: ^22.23.4 || ^24.22.1 || >=26.12.1" >&2
    exit 1
fi
echo "node $(node --version) OK"

# ─── Clone ───
if [ ! -d "$TARGET/.git" ]; then
    if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
        echo "ERRORE: $TARGET esiste ma non è un repo git. Spostalo o passa un altro path." >&2
        exit 1
    fi
    echo "Clono $CLONE_URL ..."
    mkdir -p "$(dirname "$TARGET")"
    git clone "$CLONE_URL" "$TARGET"
else
    echo "Repo già presente (skip clone)"
fi

# ─── Dipendenze ───
if [ ! -d "$TARGET/node_modules" ]; then
    echo "Installo le dipendenze (npm ci) ..."
    if ! ( cd "$TARGET" && npm ci ); then
        echo "ATTENZIONE: npm ci fallito, provo npm install" >&2
        ( cd "$TARGET" && npm install )
    fi
else
    echo "node_modules presente (skip npm install)"
fi

# ─── Build ───
if [ -d "$TARGET/dist/application" ] && [ "${REA_SKIP_BUILD:-0}" = "1" ]; then
    echo "dist/application presente e REA_SKIP_BUILD=1 (skip build)"
else
    echo "Build (npm run build) ..."
    ( cd "$TARGET" && npm run build )
fi

# ─── Verifica wrapper ───
echo ""
if [ -x "$WRAPPER" ]; then
    echo "Verifica wrapper ($WRAPPER) ..."
    REA_REPO="$TARGET" bash "$WRAPPER" --check
else
    echo "ATTENZIONE: wrapper non trovato in $WRAPPER (né in $REPO_DIR/config/bin)." >&2
    echo "           Esegui prima: python3 $REPO_DIR/install.py" >&2
fi

echo ""
echo "Fatto. Riavvia opencode per caricare il MCP server 'rea'."
echo "  Stato build/log: ${XDG_CACHE_HOME:-$HOME/.cache}/rea-mcp/"
echo "  Per servire senza ricompilare: REA_MCP_SKIP_BUILD=1"
