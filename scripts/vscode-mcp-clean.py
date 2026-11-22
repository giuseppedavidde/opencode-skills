#!/usr/bin/env python3
"""Remove stale extension MCP servers from the VS Code agent-host snapshots.

VS Code copies the customizations of a workspace into a plugin folder for each
Copilot CLI agent-host session:

    ~/.config/Code/agentPlugins/vscode-synced-customization-agent-host-*/*/.mcp.json

That copy is static. An extension can contribute an HTTP MCP server on an
ephemeral localhost port with a per-session token. The frozen copy keeps the old
port, and the next session cannot connect:

    failed to initialize MCP client: transport failure during send initialize
    request: ... error sending request for url (http://localhost:38961/stream)

Pylance contributes exactly such a server (`pylance mcp server`,
`http://localhost:<port>/stream`). This script removes that entry from every
snapshot. VS Code builds the entry again for each session, so the live server
stays available to VS Code itself.

Run it while VS Code is closed when possible. VS Code can rewrite a snapshot
during a session; the rewrite contains a fresh port, so it is safe to run the
script again later.

Usage:
    scripts/vscode-mcp-clean.py                 # remove the stale entries
    scripts/vscode-mcp-clean.py --dry-run       # print the plan only
    scripts/vscode-mcp-clean.py --verify        # exit 1 while a stale entry stays
    scripts/vscode-mcp-clean.py --server name   # also remove another server name
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_SERVERS = ("pylance mcp server",)
PRODUCTS = ("Code", "Code - Insiders", "Code - OSS", "VSCodium")
SNAPSHOT_GLOB = "agentPlugins/vscode-synced-customization-agent-host-*/*/.mcp.json"
MCP_KEYS = ("mcpServers", "servers")


def product_dirs() -> list[Path]:
    """Return the VS Code product folders: `agentPlugins` sits next to `User`."""
    override = os.environ.get("VSCODE_USER_DIR")
    if override:
        return [Path(override).expanduser()]
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    dirs = [config_home / product for product in PRODUCTS]
    dirs.append(Path.home() / ".vscode-server" / "data")
    return dirs


def snapshot_files() -> list[Path]:
    """Return every agent-host snapshot MCP file, newest first."""
    found: list[Path] = []
    for product_dir in product_dirs():
        found.extend(path for path in product_dir.glob(SNAPSHOT_GLOB) if path.is_file())
    return sorted(found, key=lambda path: path.stat().st_mtime, reverse=True)


def remove_stale(path: Path, names: set[str], dry_run: bool) -> list[str]:
    """Remove the named servers from one snapshot; return the removed names."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    removed: list[str] = []
    for key in MCP_KEYS:
        servers = data.get(key)
        if not isinstance(servers, dict):
            continue
        for name in sorted(set(servers) & names):
            del servers[name]
            removed.append(name)
    if removed and not dry_run:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return removed


def main(argv: list[str] | None = None) -> int:
    """Remove the stale snapshots entries and report the result."""
    parser = argparse.ArgumentParser(
        description="Remove stale extension MCP servers from VS Code agent-host snapshots."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; change nothing")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Exit 1 while a named server entry remains in a snapshot",
    )
    parser.add_argument(
        "--server",
        action="append",
        default=[],
        help="Server name to remove (repeatable; default: pylance mcp server)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print every snapshot")
    args = parser.parse_args(argv)

    names = set(args.server) or set(DEFAULT_SERVERS)
    files = snapshot_files()
    if args.verbose:
        print(f"snapshots: {len(files)} under {', '.join(str(d) for d in product_dirs())}")

    total = 0
    for path in files:
        removed = remove_stale(path, names, args.verify or args.dry_run)
        if removed:
            total += len(removed)
            action = "REMAINS" if args.verify else ("DRY" if args.dry_run else "REMOVED")
            print(f"{action} {', '.join(removed)} from {path}")
        elif args.verbose:
            print(f"OK   {path}")

    if args.verify:
        if total:
            noun = "entry remains" if total == 1 else "entries remain"
            print(f"\n{total} stale {noun}; run scripts/vscode-mcp-clean.py")
            return 1
        print(f"\nNo stale extension MCP entry in {len(files)} snapshot(s).")
        return 0

    verb = "would remove" if args.dry_run else "removed"
    print(f"\n{verb} {total} entr{'y' if total == 1 else 'ies'} from {len(files)} snapshot(s).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
