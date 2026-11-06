"""Export or verify the MCP wire contract snapshot.

The snapshot in ``docs/contract/tools.json`` is the reviewable form of every
tool's name, description, input schema and output schema. CI runs ``--check``:
any drift fails until the author either bumps ``CONTRACT_VERSION`` or
regenerates the snapshot, so a payload change can never land silently.

Usage
-----
    python scripts/export_contract.py            # write the snapshot
    python scripts/export_contract.py --check    # verify (CI)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from fastmcp import Client

from trading_mcp.mcp import initialize_mcp
from trading_mcp.responses import CONTRACT_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "contract" / "tools.json"
DEFAULT_SKILLS = PROJECT_ROOT.parent / "skills"


def build_document(skills_dir: Path, tickers_dir: Path) -> dict:
    """Return the deterministic contract document for the current server."""
    server = initialize_mcp(str(skills_dir), str(tickers_dir))

    async def _list() -> list:
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(_list())
    return {
        "contract_version": CONTRACT_VERSION,
        "tools": {
            tool.name: {
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema,
            }
            for tool in sorted(tools, key=lambda item: item.name)
        },
    }


def dump(document: dict) -> str:
    """Serialise with a stable key order and no timestamps."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def check(snapshot_path: Path, current: dict) -> list[str]:
    """Return the list of violations between the snapshot and the live contract."""
    if not snapshot_path.exists():
        return [f"missing snapshot: {snapshot_path} (run python scripts/export_contract.py)"]

    recorded = json.loads(snapshot_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    same_schema = recorded.get("tools") == current["tools"]
    same_version = recorded.get("contract_version") == current["contract_version"]

    if same_schema and same_version:
        return []
    if same_schema and not same_version:
        problems.append(
            "CONTRACT_VERSION changed but the schema did not; "
            f"regenerate the snapshot (recorded {recorded.get('contract_version')!r} "
            f"vs current {current['contract_version']!r})"
        )
    elif not same_schema and same_version:
        problems.append(
            "tool schemas changed without bumping CONTRACT_VERSION "
            f"({current['contract_version']!r}); bump it in trading_mcp/responses.py"
        )
    else:
        problems.append(
            "tool schemas changed; regenerate the snapshot after bumping CONTRACT_VERSION"
        )

    recorded_tools = set((recorded.get("tools") or {}).keys())
    current_tools = set(current["tools"].keys())
    for added in sorted(current_tools - recorded_tools):
        problems.append(f"tool added: {added}")
    for removed in sorted(recorded_tools - current_tools):
        problems.append(f"tool removed: {removed}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Write or check the contract snapshot."""
    parser = argparse.ArgumentParser(description="Export the MCP wire contract")
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args(argv)

    tickers_dir = args.skills_dir / "market-accumulation-scanner" / "data"
    if not args.skills_dir.exists():
        print(f"skills directory not found: {args.skills_dir}", file=sys.stderr)
        return 2

    document = build_document(args.skills_dir, tickers_dir)

    if args.check:
        problems = check(args.output, document)
        if problems:
            print("contract drift detected:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"contract OK ({document['contract_version']}, {len(document['tools'])} tools)")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dump(document), encoding="utf-8")
    print(f"wrote {args.output} ({document['contract_version']}, {len(document['tools'])} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
