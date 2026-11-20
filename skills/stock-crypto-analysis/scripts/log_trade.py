#!/usr/bin/env python3
"""
Trade logger for the feedback loop.

Records trade entries and exits in trade_log.jsonl with the schemas of
stock-crypto-analysis. Every entry needs the fill price and the size, so
the exit can compute the P&L.

Usage:
    # Log a new trade (after stock-crypto-analysis produces a verdict)
    python3 log_trade.py new --ticker AAPL --verdict-file verdict.json --entry-price 151.20 --size-pct 2.5

    # Log an Avoid verdict as a signal with no position (size 0, side flat)
    python3 log_trade.py new --ticker AAPL --verdict-file verdict.json --entry-price 151.20 --size-pct 0

    # Close a trade (the id prefix from "list" is enough when it is unique)
    python3 log_trade.py exit --trade-id 1a2b3c4d --exit-price 165.00 --reason target_1

    # List open positions, show the history of a ticker, show a summary
    python3 log_trade.py list
    python3 log_trade.py history AAPL
    python3 log_trade.py summary
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
from schemas import PositionSide, TradeLogEntry, UnifiedVerdict, Verdict  # noqa: E402


def _default_data_file(name: str) -> Path:
    """Return the data file: $OPENCODE_SKILLS_DATA_DIR, the legacy data repo, then the XDG data folder."""
    override = os.environ.get("OPENCODE_SKILLS_DATA_DIR")
    if override:
        return Path(override).expanduser() / name
    legacy = Path.home() / "Progetti" / "Github" / "Data_for_Analysis"
    if legacy.is_dir():
        return legacy / name
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "opencode-skills" / name


DEFAULT_LOG_PATH = _default_data_file("trade_log.jsonl")


class TradeLogError(Exception):
    """Invalid input for the trade log."""


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


def _parse_when(text: Optional[str]) -> datetime:
    """Parse an ISO date or datetime (UTC when no zone); default now."""
    if not text:
        return datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TradeLogError(f"Invalid date {text!r}: use YYYY-MM-DD or an ISO datetime") from exc
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def position_side(entry: dict) -> str:
    """Side of a log entry. Old entries without 'position': Avoid = flat, Short = short, else long."""
    side = entry.get("position")
    if side in ("long", "short", "flat"):
        return side
    verdict = entry.get("verdict_snapshot", {})
    if verdict.get("verdict") == Verdict.AVOID.value or entry.get("position_size_pct") == 0:
        return "flat"
    return "short" if verdict.get("direction") == "Short" else "long"


def default_side(verdict: UnifiedVerdict) -> PositionSide:
    """Side implied by the verdict: Avoid and Neutral are flat."""
    if verdict.verdict == Verdict.AVOID or verdict.direction.value == "Neutral":
        return PositionSide.FLAT
    return PositionSide.SHORT if verdict.direction.value == "Short" else PositionSide.LONG


def build_entry(
    ticker: str,
    verdict: UnifiedVerdict,
    entry_price: float,
    size_pct: float,
    side: Optional[str] = None,
    quantity: Optional[float] = None,
    fees_pct: float = 0.0,
    entry_date: Optional[datetime] = None,
    notes: str = "",
) -> tuple[TradeLogEntry, list[str]]:
    """Validate the inputs and build a new open entry. Returns (entry, warnings)."""
    warnings: list[str] = []
    if entry_price is None or not entry_price > 0:
        raise TradeLogError("--entry-price is required and must be > 0")
    if size_pct is None or not 0 <= size_pct <= 100:
        raise TradeLogError("--size-pct is required: position value in % of equity, 0 to 100")
    if fees_pct < 0:
        raise TradeLogError("--fees-pct must be >= 0")
    pos = PositionSide(side) if side else default_side(verdict)
    if pos == PositionSide.FLAT and size_pct != 0:
        raise TradeLogError("A flat entry (Avoid or Neutral verdict) has --size-pct 0: no position")
    if pos != PositionSide.FLAT and size_pct == 0:
        raise TradeLogError(f"A {pos.value} position needs --size-pct > 0")
    if verdict.verdict == Verdict.AVOID and pos != PositionSide.FLAT:
        warnings.append("The verdict is Avoid / Wait but the position is not flat")
    if verdict.risk and pos != PositionSide.FLAT and size_pct > verdict.risk.max_position_pct:
        warnings.append(f"Size {size_pct:.2f}% is above the verdict limit {verdict.risk.max_position_pct:.2f}%")
    entry = TradeLogEntry(
        trade_id=str(uuid.uuid4()),
        ticker=ticker.upper(),
        verdict_snapshot=verdict,
        entry_date=entry_date or datetime.now(timezone.utc),
        entry_price=entry_price,
        position_size_pct=size_pct,
        position=pos,
        quantity=quantity,
        fees_pct=fees_pct,
        is_open=True,
        notes=notes,
    )
    return entry, warnings


def compute_pnl(entry_price: float, exit_price: float, side: str, fees_pct: float = 0.0) -> tuple[float, float]:
    """Return (underlying move %, position P&L % after fees). A flat entry has P&L 0."""
    if not entry_price or entry_price <= 0 or not exit_price or exit_price <= 0:
        raise TradeLogError("Entry and exit prices must be > 0")
    move = (exit_price / entry_price - 1.0) * 100.0
    if side == "flat":
        return move, 0.0
    gross = -move if side == "short" else move
    return move, gross - fees_pct


def close_entry(old: dict, exit_price: float, reason: str, exit_date: Optional[datetime] = None,
                entry_price: Optional[float] = None) -> dict:
    """Return the closed version of an open entry with move, P&L and P&L in % of equity."""
    new = dict(old)
    if entry_price is not None:
        new["entry_price"] = entry_price
    if new.get("entry_price") is None:
        raise TradeLogError(f"Trade {old.get('trade_id')} has no entry_price: give --entry-price with the exit")
    side = position_side(new)
    size = new.get("position_size_pct")
    if side != "flat" and not size:
        raise TradeLogError(f"Trade {old.get('trade_id')} has no position_size_pct: the P&L in % of equity is unknown")
    when = exit_date or datetime.now(timezone.utc)
    entry_when = new.get("entry_date")
    if entry_when and when < _parse_when(str(entry_when)):
        raise TradeLogError("The exit date is before the entry date")
    move, pnl = compute_pnl(float(new["entry_price"]), exit_price, side, float(new.get("fees_pct") or 0.0))
    new.update({
        "position": side,
        "exit_date": when.isoformat(),
        "exit_price": exit_price,
        "exit_reason": reason,
        "underlying_move_pct": round(move, 4),
        "pnl_pct": round(pnl, 4),
        "pnl_equity_pct": round(pnl * (size or 0.0) / 100.0, 6),
        "is_open": False,
    })
    TradeLogEntry.model_validate(new)
    return new


def _find_open(entries: list[dict], trade_id: str) -> tuple[int, dict]:
    """Find one open trade by id or by a unique id prefix."""
    hits = [(i, e) for i, e in enumerate(entries)
            if str(e.get("trade_id", "")).startswith(trade_id) and e.get("is_open", True)]
    if not hits:
        raise TradeLogError(f"No open trade found with ID {trade_id}")
    if len(hits) > 1:
        raise TradeLogError(f"ID prefix {trade_id} is not unique: give more characters")
    return hits[0]


def _rewrite_log(entries: list[dict], log_path: Path) -> None:
    """Rewrite the trade log atomically."""
    tmp = log_path.with_suffix(log_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, log_path)


def cmd_new(args: argparse.Namespace, log_path: Path) -> None:
    """Create a new trade log entry from a verdict JSON file."""
    if not os.path.exists(args.verdict_file):
        raise TradeLogError(f"Verdict file not found: {args.verdict_file}")
    with open(args.verdict_file, encoding="utf-8") as f:
        verdict = UnifiedVerdict.model_validate(json.load(f))
    entry, warnings = build_entry(
        args.ticker, verdict, args.entry_price, args.size_pct, args.side, args.quantity,
        args.fees_pct, _parse_when(args.entry_date) if args.entry_date else None, args.notes,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")
    print(f"Trade logged: {entry.trade_id} ({entry.ticker})")
    print(f"  Verdict: {verdict.verdict.value} | Position: {entry.position.value} "
          f"| Entry: {entry.entry_price} | Size: {entry.position_size_pct:.2f}% of equity")
    for w in warnings:
        print(f"  Warning: {w}")


def cmd_exit(args: argparse.Namespace, log_path: Path) -> None:
    """Mark a trade as closed and compute its P&L."""
    entries = _load_lines(log_path)
    idx, old = _find_open(entries, args.trade_id)
    new = close_entry(old, args.exit_price, args.reason,
                      _parse_when(args.exit_date) if args.exit_date else None, args.entry_price)
    if args.notes:
        new["notes"] = f"{new.get('notes') or ''}; {args.notes}".strip("; ")
    entries[idx] = new
    _rewrite_log(entries, log_path)
    print(f"Trade closed: {new['trade_id']} ({new['ticker']})")
    print(f"  Exit: {args.exit_price} | Reason: {args.reason} | Move: {new['underlying_move_pct']:+.2f}% "
          f"| P&L: {new['pnl_pct']:+.2f}% of position, {new['pnl_equity_pct']:+.3f}% of equity")


def cmd_list_open(log_path: Path) -> None:
    """List all open trades."""
    open_entries = [e for e in _load_lines(log_path) if e.get("is_open", True)]
    if not open_entries:
        print("No open trades.")
        return
    print(f"Open trades: {len(open_entries)}\n")
    for e in open_entries:
        verdict = e.get("verdict_snapshot", {})
        print(f"  [{e['trade_id'][:8]}] {e['ticker']} {position_side(e)} score={verdict.get('composite_score', '?')} "
              f"entry={e.get('entry_price', '?')} size={e.get('position_size_pct', '?')}% entered={e.get('entry_date', '?')}")


def cmd_history(ticker: str, log_path: Path) -> None:
    """Show trade history for a ticker."""
    rows = [e for e in _load_lines(log_path) if e["ticker"].upper() == ticker.upper()]
    if not rows:
        print(f"No trade history for {ticker}")
        return
    print(f"Trade history for {ticker}: {len(rows)} trade(s)\n")
    for e in rows:
        status = "OPEN" if e.get("is_open", True) else f"CLOSED ({e.get('exit_reason', '-')})"
        pnl = e.get("pnl_pct")
        pnl_str = f"P&L={pnl:+.2f}%" if pnl is not None else "P&L=N/A"
        print(f"  [{e['trade_id'][:8]}] {position_side(e)} | {status} | {pnl_str}")


def cmd_summary(log_path: Path) -> None:
    """Show a short summary. The full statistics are in feedback_loop.py."""
    entries = _load_lines(log_path)
    closed = [e for e in entries if not e.get("is_open", True)]
    traded = [e for e in closed if position_side(e) != "flat" and e.get("pnl_pct") is not None]
    print("Trade Log Summary")
    print(f"  Total entries: {len(entries)} | Open: {len(entries) - len(closed)} | Closed: {len(closed)}")
    print(f"  Closed positions with P&L: {len(traded)} | Flat signals: {len([e for e in closed if position_side(e) == 'flat'])}")
    if traded:
        pnls = [e["pnl_pct"] for e in traded]
        wins = [p for p in pnls if p > 0]
        print(f"  Win rate: {len(wins) / len(pnls) * 100:.1f}% ({len(wins)}W / {len(pnls) - len(wins)}L)")
        print(f"  Avg P&L: {sum(pnls) / len(pnls):+.2f}% of position")
        eq = [e.get("pnl_equity_pct") for e in traded if e.get("pnl_equity_pct") is not None]
        if eq:
            print(f"  Sum of P&L: {sum(eq):+.3f}% of equity")
    print("  Run feedback_loop.py for the equity curve, the daily Sharpe and the drawdown.")


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Trade log manager")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="Path to trade_log.jsonl")
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="Log a new trade entry")
    p_new.add_argument("--ticker", required=True)
    p_new.add_argument("--verdict-file", required=True)
    p_new.add_argument("--entry-price", type=float, required=True, help="Fill price of the underlying")
    p_new.add_argument("--size-pct", type=float, required=True, help="Position value in %% of equity (0 = flat)")
    p_new.add_argument("--side", choices=[s.value for s in PositionSide], help="Default: from the verdict")
    p_new.add_argument("--quantity", type=float, help="Shares or units, for the record")
    p_new.add_argument("--fees-pct", type=float, default=0.0, help="Round-trip costs in %% of the position")
    p_new.add_argument("--entry-date", help="ISO date of the fill (default: now)")
    p_new.add_argument("--notes", default="")

    p_exit = sub.add_parser("exit", help="Close a trade")
    p_exit.add_argument("--trade-id", required=True, help="Trade id or a unique prefix")
    p_exit.add_argument("--exit-price", type=float, required=True)
    p_exit.add_argument("--reason", required=True,
                        choices=["target_1", "target_2", "stop_loss", "invalidation", "time", "manual"])
    p_exit.add_argument("--exit-date", help="ISO date of the exit (default: now)")
    p_exit.add_argument("--entry-price", type=float, help="Fill price, only for old entries without it")
    p_exit.add_argument("--notes", default="")

    sub.add_parser("list", help="List open trades")
    p_hist = sub.add_parser("history", help="Show trade history for a ticker")
    p_hist.add_argument("ticker")
    sub.add_parser("summary", help="Show a short performance summary")

    args = parser.parse_args(argv)
    log_path = Path(args.log_path)
    try:
        if args.command == "new":
            cmd_new(args, log_path)
        elif args.command == "exit":
            cmd_exit(args, log_path)
        elif args.command == "list":
            cmd_list_open(log_path)
        elif args.command == "history":
            cmd_history(args.ticker, log_path)
        elif args.command == "summary":
            cmd_summary(log_path)
        else:
            parser.print_help()
    except TradeLogError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
