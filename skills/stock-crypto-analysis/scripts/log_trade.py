#!/usr/bin/env python3
"""
Trade logger for the feedback loop.

Records trade entries and exits in the trade_log.jsonl file,
using the structured schemas from stock-crypto-analysis.

Usage:
    # Log a new trade entry (after stock-crypto-analysis produces a verdict)
    python3 log_trade.py --ticker AAPL --verdict-file /tmp/verdict.json

    # Mark an exit
    python3 log_trade.py --trade-id abc123 --exit 165.00 --reason target_1

    # List open positions
    python3 log_trade.py --list-open

    # Show trade history for a ticker
    python3 log_trade.py --history AAPL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent dir to path so we can import schemas
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SKILL_DIR))

# We use the Pydantic schemas from our own skill
# pylint: disable=import-error,wrong-import-position
from schemas import TradeLogEntry, UnifiedVerdict  # noqa: E402


DEFAULT_LOG_PATH = Path.home() / "Progetti" / "Github" / "Data_for_Analysis" / "trade_log.jsonl"


def _load_lines(path: Path) -> list[dict]:
    """Load all trade log entries."""
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _find_open(entries: list[dict], trade_id: str) -> Optional[tuple[int, dict]]:
    """Find an open trade entry by trade_id. Returns (index, entry)."""
    for i, entry in enumerate(entries):
        if entry.get("trade_id") == trade_id and entry.get("is_open", True):
            return i, entry
    return None


def cmd_new(ticker: str, verdict_file: str, log_path: Path, notes: str = "") -> None:
    """Create a new trade log entry from a verdict JSON file."""
    if not os.path.exists(verdict_file):
        print(f"Error: Verdict file not found: {verdict_file}", file=sys.stderr)
        sys.exit(1)

    with open(verdict_file, encoding="utf-8") as f:
        verdict_data = json.load(f)

    verdict = UnifiedVerdict.model_validate(verdict_data)

    entry = TradeLogEntry(
        trade_id=str(uuid.uuid4()),
        ticker=ticker,
        verdict_snapshot=verdict,
        entry_date=datetime.now(timezone.utc),
        entry_price=None,
        position_size_pct=verdict.risk.max_position_pct if verdict.risk else None,
        is_open=True,
        notes=notes,
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")

    print(f"Trade logged: {entry.trade_id} ({ticker})")
    print(f"  Verdict: {verdict.verdict.value}")
    print(f"  Direction: {verdict.direction.value}")
    print(f"  Max position: {verdict.risk.max_position_pct:.1f}%")


def _compute_pnl(entry_price: float, exit_price: float, direction: str) -> float:
    """Compute PnL percentage given entry, exit and direction."""
    if direction == "Short":
        return ((entry_price - exit_price) / entry_price) * 100
    return ((exit_price - entry_price) / entry_price) * 100


def _rewrite_log(entries: list[dict], log_path: Path) -> None:
    """Rewrite the entire trade log file."""
    with open(log_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _build_closed_entry(old_entry: dict, exit_price: float, reason: str) -> dict:
    """Build a closed trade entry from an open one."""
    new_entry = dict(old_entry)
    new_entry["exit_date"] = datetime.now(timezone.utc).isoformat()
    new_entry["exit_price"] = exit_price
    new_entry["exit_reason"] = reason
    new_entry["is_open"] = False
    return new_entry


def cmd_exit(
    trade_id: str,
    exit_price: float,
    reason: str,
    log_path: Path,
    notes: str = "",
) -> None:
    """Mark a trade as closed."""
    entries = _load_lines(log_path)

    result = _find_open(entries, trade_id)
    if result is None:
        print(f"Error: No open trade found with ID {trade_id}", file=sys.stderr)
        sys.exit(1)

    idx, old_entry = result
    entry_price = old_entry.get("entry_price")

    # Calculate PnL
    pnl_pct = None
    if entry_price is None:
        print(f"Warning: No entry price for {trade_id}. Cannot calculate PnL.")
    else:
        direction = old_entry.get("verdict_snapshot", {}).get("direction", "Long")
        pnl_pct = _compute_pnl(entry_price, exit_price, direction)

    new_entry = _build_closed_entry(old_entry, exit_price, reason)
    new_entry["pnl_pct"] = round(pnl_pct, 2) if pnl_pct is not None else None

    if notes:
        existing_notes = new_entry.get("notes", "")
        new_entry["notes"] = f"{existing_notes}; {notes}".strip("; ")

    entries[idx] = new_entry
    _rewrite_log(entries, log_path)

    pnl_str = f"{pnl_pct:+.2f}%" if pnl_pct is not None else "N/A"
    print(f"Trade closed: {trade_id} ({old_entry['ticker']})")
    print(f"  Exit: {exit_price} | Reason: {reason} | PnL: {pnl_str}")


def cmd_list_open(log_path: Path) -> None:
    """List all open trades."""
    entries = _load_lines(log_path)
    open_entries = [e for e in entries if e.get("is_open", True)]

    if not open_entries:
        print("No open trades.")
        return

    print(f"Open trades: {len(open_entries)}\n")
    for e in open_entries:
        ticker = e["ticker"]
        trade_id = e["trade_id"]
        verdict = e.get("verdict_snapshot", {})
        direction = verdict.get("direction", "?")
        score = verdict.get("composite_score", "?")
        est_size = e.get("position_size_pct", "?")
        entry_dt = e.get("entry_date", "?")
        print(f"  [{trade_id[:8]}] {ticker} {direction} score={score} "
              f"size={est_size}% entered={entry_dt}")


def cmd_history(ticker: str, log_path: Path) -> None:
    """Show trade history for a ticker."""
    entries = _load_lines(log_path)
    ticker_entries = [e for e in entries if e["ticker"].upper() == ticker.upper()]

    if not ticker_entries:
        print(f"No trade history for {ticker}")
        return

    print(f"Trade history for {ticker}: {len(ticker_entries)} trade(s)\n")
    for e in ticker_entries:
        trade_id = e["trade_id"]
        verdict = e.get("verdict_snapshot", {})
        direction = verdict.get("direction", "?")
        is_open = e.get("is_open", True)
        pnl = e.get("pnl_pct", None)
        exit_reason = e.get("exit_reason", "-")

        status = "OPEN" if is_open else f"CLOSED ({exit_reason})"
        pnl_str = f"PnL={pnl:+.2f}%" if pnl is not None else "PnL=N/A"

        print(f"  [{trade_id[:8]}] {direction} | {status} | {pnl_str}")


def cmd_summary(log_path: Path) -> None:
    """Show a summary of all trading activity."""
    entries = _load_lines(log_path)

    closed = [e for e in entries if not e.get("is_open", True)]
    open_ = [e for e in entries if e.get("is_open", True)]

    print("Trade Log Summary")
    print(f"  Total trades: {len(entries)}")
    print(f"  Open: {len(open_)}")
    print(f"  Closed: {len(closed)}")

    if closed:
        wins = [e for e in closed if e.get("pnl_pct", 0) and e["pnl_pct"] > 0]
        losses = [e for e in closed if e.get("pnl_pct", 0) and e["pnl_pct"] <= 0]
        win_rate = len(wins) / len(closed) * 100 if closed else 0

        pnls = [e["pnl_pct"] for e in closed if e.get("pnl_pct") is not None]
        if pnls:
            avg_pnl = sum(pnls) / len(pnls)
            print(f"\n  Win rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
            print(f"  Avg PnL: {avg_pnl:+.2f}%")
            print(f"  Best: {max(pnls):+.2f}%")
            print(f"  Worst: {min(pnls):+.2f}%")

            # By verdict type
            print("\n  By Verdict:")
            by_verdict = {}
            for e in closed:
                v = e.get("verdict_snapshot", {}).get("verdict", "Unknown")
                by_verdict.setdefault(v, []).append(e)
            for v, trades in sorted(by_verdict.items()):
                v_pnls = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
                if v_pnls:
                    avg = sum(v_pnls) / len(v_pnls)
                    print(f"    {v}: {len(trades)} trades, avg PnL {avg:+.2f}%")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Trade log manager")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH),
                        help="Path to trade_log.jsonl")

    sub = parser.add_subparsers(dest="command")

    # New trade
    p_new = sub.add_parser("new", help="Log a new trade entry")
    p_new.add_argument("--ticker", required=True)
    p_new.add_argument("--verdict-file", required=True)
    p_new.add_argument("--notes", default="")

    # Exit trade
    p_exit = sub.add_parser("exit", help="Close a trade")
    p_exit.add_argument("--trade-id", required=True)
    p_exit.add_argument("--exit-price", type=float, required=True)
    p_exit.add_argument("--reason", required=True,
                        choices=["target_1", "target_2", "stop_loss",
                                 "invalidation", "time", "manual"])
    p_exit.add_argument("--notes", default="")

    # List open
    sub.add_parser("list", help="List open trades")

    # History
    p_hist = sub.add_parser("history", help="Show trade history for a ticker")
    p_hist.add_argument("ticker")

    # Summary
    sub.add_parser("summary", help="Show trade performance summary")

    args = parser.parse_args()
    log_path = Path(args.log_path)

    if args.command == "new":
        cmd_new(args.ticker, args.verdict_file, log_path, args.notes)
    elif args.command == "exit":
        cmd_exit(args.trade_id, args.exit_price, args.reason, log_path, args.notes)
    elif args.command == "list":
        cmd_list_open(log_path)
    elif args.command == "history":
        cmd_history(args.ticker, log_path)
    elif args.command == "summary":
        cmd_summary(log_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
