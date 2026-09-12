#!/usr/bin/env bash
# Installa headroom nel venv canonico per opencode e applica il patch opencode (idempotente).
# Rieseguibile: usalo anche DOPO un upgrade manuale di headroom per ri-applicare il patch.
# Al termine, riavvia opencode per usare i tool di compressione.
set -euo pipefail

# Overridabile per test/simulazioni; default = venv canonico.
VENV="${HEADROOM_VENV:-$HOME/.local/share/opencode/headroom-venv}"
HEADROOM_PIN="headroom-ai[mcp]==0.27.0"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_FILE="$REPO_ROOT/scripts/patches/headroom-0.27.0-opencode.patch"

echo "Headroom — Compression Layer per OpenCode"
echo "========================================="
echo ""

apply_patch() {
    if [ ! -f "$PATCH_FILE" ]; then
        echo "❌ Patch non trovata: $PATCH_FILE" >&2
        exit 1
    fi

    local site_packages target
    site_packages="$("$VENV/bin/python" -c 'import os, headroom; print(os.path.dirname(os.path.dirname(os.path.abspath(headroom.__file__))))')"
    target="$site_packages/headroom/ccr/mcp_server.py"

    # Idempotenza: se il reverse-dry-run riesce, il patch è già applicato.
    # NB: niente --batch (maschera l'exit code con falsi positivi); stdin da /dev/null.
    if (cd "$site_packages" && patch --dry-run -R -p1 -i "$PATCH_FILE" </dev/null) >/dev/null 2>&1; then
        echo "✅ Patch opencode già applicato (skip)."
        return 0
    fi
    # Altrimenti, se il forward-dry-run riesce, applichiamo il patch.
    if (cd "$site_packages" && patch --dry-run -p1 -i "$PATCH_FILE" </dev/null) >/dev/null 2>&1; then
        (cd "$site_packages" && patch -p1 -i "$PATCH_FILE" </dev/null)
        if grep -q '\[opencode-patch\]' "$target" 2>/dev/null; then
            echo "✅ Patch opencode applicato."
            return 0
        fi
        echo "❌ Patch eseguito ma marker [opencode-patch] assente: verifica $target" >&2
        exit 1
    fi
    echo "❌ Versione headroom incompatibile: il patch non applica né in forward né in reverse." >&2
    echo "   Atteso $HEADROOM_PIN. Verifica $PATCH_FILE." >&2
    exit 1
}

if [ -f "$VENV/bin/headroom" ]; then
    echo "headroom già installato:"
    echo "  $($VENV/bin/headroom --version)"
    echo ""
    echo "  Venv: $VENV"
    echo ""
    echo "Verifica/applicazione del patch opencode ..."
    apply_patch
    echo ""
    echo "Per reinstallare da zero, rimuovi il venv e riavvia:"
    echo "  rm -rf $VENV"
    echo "  ./setup-headroom.sh"
    echo ""
    echo "Riavvia opencode per attivare i tool."
    exit 0
fi

echo "Creazione virtual environment in $VENV ..."
python3 -m venv "$VENV"

echo "Installazione $HEADROOM_PIN ..."
"$VENV/bin/pip" install "$HEADROOM_PIN" --quiet

echo ""
echo "Applicazione del patch opencode ..."
apply_patch

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
echo "Nota: il patch opencode va RI-APPLICATO dopo ogni upgrade manuale di headroom —"
echo "      basta rieseguire ./setup-headroom.sh (idempotente)."
echo "I tool sono usati automaticamente — vedi AGENTS.md per le regole."
