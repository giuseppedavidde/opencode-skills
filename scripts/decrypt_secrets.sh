#!/usr/bin/env bash
# Decrypt secrets and place them in the right locations.
# Usage: ./scripts/decrypt_secrets.sh [passphrase]
#   If passphrase is omitted, prompts interactively.

set -euo pipefail

PASS="${1:-}"
if [ -z "$PASS" ]; then
    read -rsp "Enter decryption passphrase: " PASS
    echo
fi

# Decrypt into /tmp first, then source
TMPFILE=$(mktemp)
trap 'rm -f $TMPFILE' EXIT

openssl enc -aes-256-cbc -d -salt -pbkdf2 -iter 100000 \
    -in "$(dirname "$0")/../config/secrets.env.enc" \
    -out "$TMPFILE" \
    -pass pass:"$PASS" 2>/dev/null || {
    echo "❌ Decryption failed — wrong passphrase?" >&2
    exit 1
}

set -a
source "$TMPFILE"
set +a

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# FMP key for MCP server
mkdir -p ~/.config/opencode
echo "${FMP_API_KEY}" > ~/.config/opencode/fmp_api_key.txt
chmod 600 ~/.config/opencode/fmp_api_key.txt
echo "✅ FMP_API_KEY → ~/.config/opencode/fmp_api_key.txt"

# FMP key for lgbm-trader .env
cat > "$REPO_ROOT/skills/lgbm-trader-skill/.env" << INNEREOF
FMP_API_KEY=${FMP_API_KEY}
INNEREOF
echo "✅ FMP_API_KEY → skills/lgbm-trader-skill/.env"

echo "✅ All secrets decrypted and placed."
