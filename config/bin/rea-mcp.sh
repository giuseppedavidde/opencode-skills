#!/usr/bin/env bash
# rea-mcp.sh — serve the LOCAL rea repo as a stdio MCP server, rebuilding only
# when the repo HEAD or the tracked working tree changes.
#
# Env vars:
#   REA_REPO            path to the rea checkout (default: $HOME/Progetti/Github/rea)
#   REA_MCP_SKIP_BUILD  set to 1 to never rebuild (serve existing dist)
#   REA_MCP_AUTO_UPDATE set to 0 to skip the git fetch/fast-forward step
#                       (default: 1); update runs only on branch main with a
#                       clean tracked tree and never in --check mode
#   REA_MCP_UPDATE_TIMEOUT  seconds allowed for each git fetch/merge
#                       (default: 60); failures fall back to the local checkout
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
AUTO_UPDATE="${REA_MCP_AUTO_UPDATE:-1}"
UPDATE_TIMEOUT="${REA_MCP_UPDATE_TIMEOUT:-60}"
mkdir -p "$STATE"

# Run a command with a timeout when `timeout` is available, otherwise run it
# unchanged; the exit code is propagated to the caller.
run_timed() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  else
    "$@"
  fi
}

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
  shift
fi

BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

# True when no tracked file is modified (untracked files are ignored).
tree_clean() {
  [ -z "$(git -C "$REPO" status --porcelain --untracked-files=no 2>/dev/null)" ]
}

# Fetch origin and fast-forward main; never fail the script, fall back to the
# local checkout on any error (offline, timeout, non fast-forwardable, ...).
update_from_origin() {
  local behind
  GIT_TERMINAL_PROMPT=0
  if [ -z "${GIT_SSH_COMMAND:-}" ]; then
    GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10"
  fi
  export GIT_TERMINAL_PROMPT GIT_SSH_COMMAND

  if ! run_timed "$UPDATE_TIMEOUT" git -C "$REPO" fetch --tags --prune origin >/dev/null 2>&1; then
    echo "[rea-mcp] fetch failed, serving local checkout" >&2
    return 0
  fi

  behind="$(git -C "$REPO" rev-list --count HEAD..origin/main 2>/dev/null || echo 0)"
  if [ "${behind:-0}" -gt 0 ] 2>/dev/null; then
    echo "[rea-mcp] updating: $behind commit(s) behind origin/main" >&2
    if ! run_timed "$UPDATE_TIMEOUT" git -C "$REPO" merge --ff-only origin/main >/dev/null 2>&1; then
      echo "[rea-mcp] fast-forward failed, serving local checkout" >&2
    fi
  fi
  return 0
}

if [ "$AUTO_UPDATE" != "0" ] && [ "$CHECK_ONLY" = 0 ]; then
  if ! git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    echo "[rea-mcp] not a git checkout, skipping auto-update" >&2
  elif [ "$BRANCH" != "main" ]; then
    echo "[rea-mcp] branch is '$BRANCH', skipping auto-update" >&2
  elif ! tree_clean; then
    echo "[rea-mcp] tracked files modified, skipping auto-update" >&2
  else
    update_from_origin
  fi
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
  if [ "$AUTO_UPDATE" != "0" ]; then echo "auto-update: enabled"; else echo "auto-update: disabled"; fi
  echo "branch: $BRANCH"
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
