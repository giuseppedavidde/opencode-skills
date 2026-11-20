#!/usr/bin/env bash
# Decrypt secrets and place them in the right locations.
# Usage:
#   OPENCODE_SECRETS_PASSPHRASE=... ./scripts/decrypt_secrets.sh
#   ./scripts/decrypt_secrets.sh            # prompts for the passphrase
# A passphrase given as the first argument still works, but it stays in the
# shell history: prefer the variable or the prompt.

set -euo pipefail

# Resolve the real location: the installer links this script into ~/.config/opencode/scripts.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS="${OPENCODE_SECRETS_PASSPHRASE:-}"
if [ -z "$PASS" ] && [ -n "${1:-}" ]; then
    echo "⚠️  The passphrase argument stays in the shell history. Use OPENCODE_SECRETS_PASSPHRASE or the prompt." >&2
    PASS="$1"
fi
if [ -z "$PASS" ]; then
    read -rsp "Enter decryption passphrase: " PASS
    echo
fi

TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT
chmod 600 "$TMPFILE"

# The passphrase goes through the environment, not the command line (ps shows arguments).
if ! OPENSSL_PASSPHRASE="$PASS" openssl enc -aes-256-cbc -d -salt -pbkdf2 -iter 100000 \
    -in "$REPO_ROOT/config/secrets.env.enc" \
    -out "$TMPFILE" \
    -pass env:OPENSSL_PASSPHRASE 2>/dev/null; then
    echo "❌ Decryption failed — wrong passphrase?" >&2
    exit 1
fi

# Read KEY=VALUE lines only; never execute the decrypted file.
FMP_API_KEY=""
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        FMP_API_KEY=*) FMP_API_KEY="${line#FMP_API_KEY=}" ;;
    esac
done < "$TMPFILE"
FMP_API_KEY="${FMP_API_KEY%\"}"
FMP_API_KEY="${FMP_API_KEY#\"}"

if [ -z "$FMP_API_KEY" ]; then
    echo "❌ FMP_API_KEY not found in config/secrets.env.enc" >&2
    exit 1
fi

# FMP key for the trading MCP server
mkdir -p ~/.config/opencode
umask 077
printf '%s\n' "$FMP_API_KEY" > ~/.config/opencode/fmp_api_key.txt
chmod 600 ~/.config/opencode/fmp_api_key.txt
echo "✅ FMP_API_KEY → ~/.config/opencode/fmp_api_key.txt"

echo "✅ All secrets decrypted and placed."
