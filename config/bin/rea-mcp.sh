#!/usr/bin/env bash
# rea-mcp.sh — serve the LOCAL rea repo as a stdio MCP server, rebuilding only
# when the repo HEAD or the tracked working tree changes.
#
# Env vars:
#   REA_REPO            path to the rea checkout (default: $HOME/Progetti/Github/rea)
#   REA_MCP_SKIP_BUILD  set to 1 to never rebuild (serve existing dist)
#   XDG_CACHE_HOME      state/log dir base (default: $HOME/.cache);
#                       stamp/build.log live in <base>/rea-mcp/
#
# Usage:
#   rea-mcp.sh            serve MCP over stdio
#   rea-mcp.sh --check    print signature + rebuild decision, do not serve
#
# MCP stdio: nothing but the protocol may go to stdout, so all build output is
# redirected to the log and all diagnostics go to stderr.
set -euo pipefail

REPO="${REA_REPO:-$HOME/Progetti/Github/rea}"
STATE="${XDG_CACHE_HOME:-$HOME/.cache}/rea-mcp"
STAMP="$STATE/stamp"
LOG="$STATE/build.log"
DIST="$REPO/dist/application"
mkdir -p "$STATE"

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
  shift
fi

HEAD_SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "nogit")"
DIRTY_SHA="$(git -C "$REPO" status --porcelain --untracked-files=no 2>/dev/null | sha1sum | cut -c1-12)"
SIG="$HEAD_SHA-$DIRTY_SHA"

needs_build=0
if [ ! -f "$STAMP" ] || [ ! -d "$DIST" ]; then
  needs_build=1
elif [ "$(cat "$STAMP")" != "$SIG" ]; then
  needs_build=1
fi

if [ "$CHECK_ONLY" = 1 ]; then
  echo "repo: $REPO"
  echo "signature: $SIG"
  if [ "$needs_build" = 1 ]; then echo "rebuild: yes"; else echo "rebuild: no"; fi
  exit 0
fi

if [ "$needs_build" = 1 ] && [ "${REA_MCP_SKIP_BUILD:-0}" != "1" ]; then
  echo "[rea-mcp] $(date -Is) rebuild start ($SIG)" >&2
  if ( cd "$REPO" && npm run build ) >>"$LOG" 2>&1; then
    printf '%s\n' "$SIG" >"$STAMP"
    echo "[rea-mcp] $(date -Is) rebuild done" >&2
  else
    echo "[rea-mcp] $(date -Is) rebuild FAILED (see $LOG), serving existing dist" >&2
    if [ ! -d "$DIST" ]; then
      echo "[rea-mcp] no dist available, aborting" >&2
      exit 1
    fi
  fi
fi

exec node "$REPO/scripts/rea.mjs" mcp "$@"
