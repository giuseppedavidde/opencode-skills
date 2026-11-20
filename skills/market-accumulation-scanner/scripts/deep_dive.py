#!/usr/bin/env python3
"""
Deep dive of one ticker — thin wrapper around the trading MCP analysis.

The analysis and the verdict come only from the trading MCP (the code of the
``analyze_stock`` tool, through ``trading_mcp.trading_cli.cmd_analyze``). This script
keeps no scoring rule of its own.

Usage:
    python3 deep_dive.py AAPL            # print the JSON
    python3 deep_dive.py AAPL --save     # also write reports/deep_dives/deep_dive_aapl.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
_MCP_SRC = SKILL_DIR.parents[1] / "mcp" / "src"


def analyze(ticker: str, fetch_news: bool = True) -> dict:
    """Return the MCP analysis of one ticker (verbose fields included)."""
    if (_MCP_SRC / "trading_mcp").is_dir() and str(_MCP_SRC) not in sys.path:
        sys.path.insert(0, str(_MCP_SRC))
    try:
        from trading_mcp.trading_cli import cmd_analyze  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise SystemExit(
            "deep_dive.py: the trading MCP is not importable. Use the trading MCP venv "
            f"(~/.local/share/opencode/trading-mcp-venv/bin/python). Cause: {exc}"
        ) from exc
    result = cmd_analyze(argparse.Namespace(ticker=ticker.upper(), fetch_news=fetch_news, verbose=True))
    result["source"] = "trading_mcp.analyze"
    result["date"] = datetime.now(timezone.utc).isoformat()
    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Deep dive of one ticker with the trading MCP")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--save", "-s", action="store_true", help="Save the JSON report")
    parser.add_argument("--no-news", action="store_true", help="Skip the news headlines")
    args = parser.parse_args(argv)
    result = analyze(args.ticker, fetch_news=not args.no_news)
    print(json.dumps(result, indent=2, default=str))
    if args.save:
        out_dir = SKILL_DIR / "reports" / "deep_dives"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"deep_dive_{args.ticker.lower()}.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"Saved: {path}", file=sys.stderr)
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
