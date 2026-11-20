#!/usr/bin/env python3
"""
Market Accumulation Scanner — thin wrapper around the trading MCP scanner.

The scoring lives only in the trading MCP (``mcp/src/trading_mcp/analysis/scanner.py``),
the same code as the ``scan_market`` tool. This script keeps no weights and no scoring
rules. It loads the universe with the MCP loader, scores every ticker with the MCP
functions, applies the MCP macro-regime multiplier, and writes the CSV/HTML reports
that scheduler.py, watchlist_update.py and compare_reports.py read.

Usage:
    python3 scanner.py --universe us_large --min-score 50 --top 15
    python3 scanner.py --tickers AAPL,MSFT --json-output
    python3 scanner.py --universe italy --list-tickers

Run it with the trading MCP venv (~/.local/share/opencode/trading-mcp-venv/bin/python)
or from this repository with the MCP dependencies installed.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
_MCP_SRC = SKILL_DIR.parents[1] / "mcp" / "src"

# MCP dimension names → flat report columns (the column names of the old reports)
DIM_COLUMNS = {
    "Wyckoff Phase": "wyckoff",
    "Volume Profile": "volprof",
    "Price Action": "pa",
    "Sentiment": "sentiment",
    "Fundamentals": "fundamentals",
    "Crypto APC": "crypto_apc",
}
# MCP sentiment sub-scores → report columns
SENT_COLUMNS = {
    "short_interest": "sent_si",
    "options_sentiment": "sent_options",
    "insider_trading": "sent_insider",
    "retail_sentiment": "sent_retail",
    "institutional": "sent_institutional",
    "momentum": "sent_momentum",
    "earnings_quality": "sent_earnings_quality",
    "web_news": "sent_web_news",
    "social_media": "sent_social_media",
}
UNIVERSES = ["us_large", "us_tech", "all", "italy", "germany", "france", "uk", "spain", "crypto"]
INDICATORS = ["candlestick", "fibonacci", "bollinger", "obv", "support_resistance", "psychology",
              "ichimoku", "risk_reward", "point_figure"]
CSV_COLUMNS = (["rank", "symbol", "name", "market", "sector", "price", "final_score",
                "wyckoff", "volprof", "pa", "competitive", "sentiment", "fundamentals", "crypto_apc", "pattern", "flags"]
               + list(SENT_COLUMNS.values()) + INDICATORS)


def tickers_dir() -> Path:
    """Universe CSV folder: $TRADING_TICKERS_DIR (the MCP override), else the data folder of this skill."""
    override = os.environ.get("TRADING_TICKERS_DIR", "").strip()
    return Path(override).expanduser() if override else SKILL_DIR / "data"


def load_universe(mcp: Any, args: argparse.Namespace) -> tuple[list[dict], str]:
    """Load the universe with the MCP loader. An empty universe is an error."""
    if args.tickers:
        return mcp.parse_custom_tickers(args.tickers), "custom"
    universe = mcp.load_universe(args.universe, str(tickers_dir()))
    if not universe:
        raise SystemExit(f"scanner.py: universe {args.universe!r} is empty or unknown in {tickers_dir()}")
    return universe, args.universe


def load_mcp() -> Any:
    """Import the MCP scanner module (lazy, so --help works without the MCP)."""
    if (_MCP_SRC / "trading_mcp").is_dir() and str(_MCP_SRC) not in sys.path:
        sys.path.insert(0, str(_MCP_SRC))
    try:
        # pylint: disable=import-outside-toplevel
        from trading_mcp.analysis import scanner as mcp_scanner
    except ImportError as exc:
        raise SystemExit(
            "scanner.py: the trading MCP is not importable. Use the trading MCP venv "
            "(~/.local/share/opencode/trading-mcp-venv/bin/python) or run setup-trading-mcp.sh. "
            f"Cause: {exc}"
        ) from exc
    return mcp_scanner


def flatten(result: dict) -> dict:
    """One flat row from an MCP scanner result, with the columns of the report consumers."""
    row: dict[str, Any] = {
        "symbol": result.get("symbol", ""),
        "ticker": result.get("symbol", ""),
        "name": result.get("name", ""),
        "market": result.get("market", ""),
        "sector": result.get("sector", ""),
        "price": result.get("price"),
        "final_score": result.get("final_score"),
        "pattern": result.get("pattern", ""),
        "flags": ";".join(result.get("flags", []) or []),
        "competitive": result.get("competitive_score"),
    }
    for dim in result.get("dimensions", []) or []:
        column = DIM_COLUMNS.get(dim.get("name"))
        if column:
            row[column] = dim.get("score")
    for key, column in SENT_COLUMNS.items():
        row[column] = (result.get("sentiment_breakdown") or {}).get(key)
    for key in INDICATORS:
        row[key] = (result.get("indicators") or {}).get(key)
    return row


def write_csv(rows: list[dict], output_dir: Path, stamp: str) -> Path:
    """Write scan_report_<stamp>.csv (read by watchlist_update.py and compare_reports.py)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"scan_report_{stamp}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            writer.writerow({**row, "rank": i})
    return path


def write_html(rows: list[dict], output_dir: Path, stamp: str, universe: str, scanned: int) -> Path:
    """Write a simple HTML table of the candidates (every value is escaped)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"scan_report_{stamp}.html"
    cols = ["symbol", "name", "sector", "final_score", "wyckoff", "volprof", "pa", "sentiment", "fundamentals", "pattern", "flags"]
    body = "".join(
        "<tr><td>" + str(i) + "</td>" + "".join(f"<td>{html.escape(str(r.get(c, '') if r.get(c) is not None else ''))}</td>" for c in cols) + "</tr>"
        for i, r in enumerate(rows, 1)
    )
    head = "".join(f"<th>{html.escape(c)}</th>" for c in ["#", *cols])
    path.write_text(
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Market scan "
        f"{html.escape(stamp)}</title></head><body><h1>Market Accumulation Scan</h1>"
        f"<p>Universe: {html.escape(universe)} · scanned: {scanned} · candidates: {len(rows)} · {html.escape(stamp)}. "
        "Scores from the trading MCP (scan_market). A score is not a verdict: use analyze_stock for the verdict, stop and target.</p>"
        f"<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\"><tr>{head}</tr>{body}</table></body></html>",
        encoding="utf-8",
    )
    return path


def run_scan(args: argparse.Namespace) -> tuple[list[dict], int, int, str]:
    """Score the universe with the MCP functions. Returns (rows >= min score, scanned, failures, universe name)."""
    mcp = load_mcp()
    universe, name = load_universe(mcp, args)
    results, failures = [], 0
    t0 = time.time()
    for i, ticker in enumerate(universe, 1):
        if ticker.get("market") == "CRYPTO":
            result = mcp.process_crypto_ticker(ticker, fetch_news=args.fetch_news)
        else:
            result = mcp.process_ticker(ticker, fetch_news=args.fetch_news)
        if result and result.get("final_score") is not None:
            results.append(result)
        else:
            failures += 1
        if not args.json_output:
            sys.stdout.write(f"\r   Progress: {i}/{len(universe)} | candidates: {len(results)} | {time.time() - t0:.0f}s   ")
            sys.stdout.flush()
    results = mcp.apply_macro_regime(results, args.regime)
    results.sort(key=lambda r: r["final_score"], reverse=True)
    rows = [flatten(r) for r in results if r["final_score"] >= args.min_score]
    return rows, len(universe), failures, name


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Market Accumulation Scanner (thin wrapper of the trading MCP scanner)")
    parser.add_argument("--universe", default="us_large", choices=UNIVERSES, help="Universe name")
    parser.add_argument("--tickers", help="Custom comma-separated ticker list")
    parser.add_argument("--min-score", type=float, default=50, help="Minimum score")
    parser.add_argument("--top", type=int, default=15, help="Top N to print")
    parser.add_argument("--output-dir", default=".", help="Output directory (default: reports/<universe>)")
    parser.add_argument("--list-tickers", action="store_true", help="Print the ticker symbols as JSON and exit")
    parser.add_argument("--json-output", action="store_true", help="Print the rows as JSON to stdout, no files")
    parser.add_argument("--fetch-news", action="store_true", help="Fetch news headlines for the sentiment (slower)")
    parser.add_argument("--regime", default="NORMAL", choices=["FULL", "NORMAL", "SELECTIVE", "DEFENSIVE"],
                        help="Macro window for the MCP post-aggregation multiplier")
    parser.add_argument("--batch-size", type=int, default=20, help=argparse.SUPPRESS)
    parser.add_argument("--batch-sleep", type=float, default=1.0, help=argparse.SUPPRESS)
    parser.add_argument("--wsb-hotlist", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.wsb_hotlist:
        print("Warning: --wsb-hotlist is ignored. The MCP scanner has no WSB input.", file=sys.stderr)

    if args.list_tickers:
        universe, _ = load_universe(load_mcp(), args)
        print(json.dumps([t["symbol"] for t in universe]))
        return 0

    rows, scanned, failures, name = run_scan(args)
    if args.json_output:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    print(f"\n\nScanned {scanned} tickers ({name}) · failures {failures} · candidates >= {args.min_score}: {len(rows)}")
    if not rows:
        print("No candidates. Lower --min-score to see more tickers.")
        return 0
    for i, r in enumerate(rows[:args.top], 1):
        print(f"{i:>3}  {r['symbol']:<10} {r['final_score']:>6}  {str(r.get('pattern', ''))[:28]:<28} {str(r.get('sector', ''))[:24]}")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    output_dir = SKILL_DIR / "reports" / name if args.output_dir == "." else Path(args.output_dir)
    print(f"\nCSV report: {write_csv(rows, output_dir, stamp)}")
    print(f"HTML report: {write_html(rows, output_dir, stamp, name, scanned)}")
    print("A scan score is not a verdict. analyze_stock gives the verdict, the stop and the target.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
