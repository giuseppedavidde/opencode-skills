#!/usr/bin/env python3
"""Manage pump detection history: record, learn patterns, predict, and summarize."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


HISTORY_FILE = os.path.expanduser("~/Progetti/Github/Data_for_Analysis/pump_history.jsonl")


class PumpRecord(BaseModel):
    """A single pump detection record."""

    ticker: str
    detected_at: str
    fomo_phase: str = "unknown"
    hype_score: float = 0.0
    mention_count: int = 0
    sentiment: float = 0.0
    price_at_detection: float = 0.0
    peak_price: float | None = None
    peak_date: str | None = None
    pump_result: str = "unknown"


class PatternSummary(BaseModel):
    """Summary of learned pump patterns."""

    total_records: int
    successful_pumps: int
    failed_pumps: int
    success_rate: float
    avg_peak_gain_pct: float
    top_tickers: list[dict[str, Any]]
    patterns: list[dict[str, Any]]


def _ensure_history_file() -> str:
    """Ensure the history file directory exists."""
    history_dir = os.path.dirname(HISTORY_FILE)
    os.makedirs(history_dir, exist_ok=True)
    return HISTORY_FILE


def _read_history() -> list[dict[str, Any]]:
    """Read all records from the history file."""
    filepath = _ensure_history_file()
    records: list[dict[str, Any]] = []
    if not os.path.exists(filepath):
        return records
    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _write_record(record: PumpRecord) -> None:
    """Append a single record to the history file."""
    filepath = _ensure_history_file()
    with open(filepath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.model_dump(mode="json"), default=str) + "\n")


def cmd_record(args: argparse.Namespace) -> None:
    """Record a new pump detection."""
    record = PumpRecord(
        ticker=args.ticker.upper(),
        detected_at=datetime.now(timezone.utc).isoformat(),
        fomo_phase=args.fomo,
        hype_score=args.score,
        mention_count=args.mentions,
        sentiment=0.0,
        price_at_detection=args.price,
    )
    _write_record(record)
    print(f"Recorded pump detection for ${record.ticker}:")
    print(f"  Phase: {record.fomo_phase}")
    print(f"  Hype Score: {record.hype_score}")
    print(f"  Mentions: {record.mention_count}")
    print(f"  Price at detection: ${record.price_at_detection:.2f}")


def _analyze_friday_pumps(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Check if >50% of pumps were detected on Friday afternoons."""
    friday_pumps = 0
    total_with_dates = 0
    for rec in records:
        try:
            dt = datetime.fromisoformat(rec.get("detected_at", ""))
            if dt.weekday() == 4 and dt.hour >= 12:
                friday_pumps += 1
            total_with_dates += 1
        except (ValueError, TypeError):
            continue

    active = total_with_dates > 0 and (friday_pumps / total_with_dates) > 0.5
    ratio = friday_pumps / total_with_dates if total_with_dates > 0 else 0.0
    return {
        "name": "Friday afternoon pump",
        "description": ">50% of pumps detected on Friday afternoons (12:00+)",
        "active": active,
        "ratio": round(ratio, 2),
        "count": friday_pumps,
        "total": total_with_dates,
    }


def _analyze_meme_resurrection(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Check for tickers that returned after >30 days of silence."""
    ticker_dates: dict[str, list[datetime]] = defaultdict(list)
    for rec in records:
        try:
            dt = datetime.fromisoformat(rec.get("detected_at", ""))
            ticker_dates[rec.get("ticker", "").upper()].append(dt)
        except (ValueError, TypeError):
            continue

    resurrections = 0
    for dates in ticker_dates.values():
        dates.sort()
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            if gap > 30:
                resurrections += 1
                break

    return {
        "name": "Meme resurrection",
        "description": "Ticker returned after >30 days of silence",
        "active": resurrections > 0,
        "resurrection_count": resurrections,
        "unique_tickers": len(ticker_dates),
    }


def _analyze_hype_decay(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Average days for hype score to halve (proxy: time between same ticker detections)."""
    ticker_scores: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for rec in records:
        try:
            dt = datetime.fromisoformat(rec.get("detected_at", ""))
            score = float(rec.get("hype_score", 0))
            ticker_scores[rec.get("ticker", "").upper()].append((dt, score))
        except (ValueError, TypeError):
            continue

    decay_days: list[float] = []
    for entries in ticker_scores.values():
        entries.sort(key=lambda x: x[0])
        for i in range(1, len(entries)):
            prev_score = entries[i - 1][1]
            curr_score = entries[i][1]
            if prev_score > 0 and curr_score < prev_score:
                days = (entries[i][0] - entries[i - 1][0]).days
                if days > 0:
                    reduction = prev_score - curr_score
                    if reduction >= prev_score / 2:
                        decay_days.append(float(days))

    avg_decay = sum(decay_days) / len(decay_days) if decay_days else 0.0
    return {
        "name": "Hype decay rate",
        "description": "Average days for hype score to halve",
        "avg_days": round(avg_decay, 1),
        "sample_count": len(decay_days),
    }


def cmd_learn(_args: argparse.Namespace) -> None:
    """Analyze history to extract pump detection patterns."""
    records = _read_history()
    if not records:
        print("No pump history found. Record some pumps first with --record.")
        return

    patterns = [
        _analyze_friday_pumps(records),
        _analyze_meme_resurrection(records),
        _analyze_hype_decay(records),
    ]

    print(f"Analyzing {len(records)} pump records...\n")
    print("Learned Patterns:")
    print("=" * 60)
    for pat in patterns:
        active_str = "ACTIVE" if pat.get("active") else "inactive"
        print(f"\n  {pat['name']} [{active_str}]")
        print(f"  {pat['description']}")
        details = {k: v for k, v in pat.items() if k not in ("name", "description", "active")}
        for key, val in details.items():
            print(f"    {key}: {val}")

    # Also print post-earnings sympathy placeholder
    print("\n  Post-earnings sympathy [check manually]")
    print("  Ticker pumped within 3 days of a competitor's earnings")
    print("    (requires earnings calendar data — not computed automatically)")


def _compute_pump_probability(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    ticker: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    ticker_upper = ticker.upper()
    ticker_records = [r for r in records if r.get("ticker", "").upper() == ticker_upper]

    probability = 0.0
    factors: list[dict[str, Any]] = []

    # Factor 1: Has this ticker pumped before?
    if ticker_records:
        successes = sum(1 for r in ticker_records if r.get("pump_result") == "successful")
        prev_rate = successes / len(ticker_records) if ticker_records else 0
        probability += prev_rate * 35
        factors.append({
            "factor": "Previous pump history",
            "detail": f"{successes}/{len(ticker_records)} successful",
            "contribution": round(prev_rate * 35, 1),
        })
    else:
        factors.append({
            "factor": "Previous pump history",
            "detail": "No prior records",
            "contribution": 0,
        })

    # Factor 2: Friday afternoon pattern active?
    friday_pumps = 0
    total_dated = 0
    for rec in records:
        try:
            dt = datetime.fromisoformat(rec.get("detected_at", ""))
            if dt.weekday() == 4 and dt.hour >= 12:
                friday_pumps += 1
            total_dated += 1
        except (ValueError, TypeError):
            continue
    if total_dated > 0 and (friday_pumps / total_dated) > 0.5:
        now = datetime.now(timezone.utc)
        if now.weekday() == 4 and now.hour >= 12:
            probability += 20
            factors.append({
                "factor": "Friday afternoon pattern",
                "detail": "It is Friday afternoon, pattern is active",
                "contribution": 20,
            })
        else:
            factors.append({
                "factor": "Friday afternoon pattern",
                "detail": "Pattern exists but not Friday afternoon now",
                "contribution": 5,
            })
            probability += 5
    else:
        factors.append({
            "factor": "Friday afternoon pattern",
            "detail": "Pattern not active in history",
            "contribution": 0,
        })

    # Factor 3: Meme resurrection check
    if ticker_records:
        dates = []
        for r in ticker_records:
            try:
                dates.append(datetime.fromisoformat(r.get("detected_at", "")))
            except (ValueError, TypeError):
                continue
        dates.sort()
        if len(dates) >= 2:
            last_gap = (datetime.now(timezone.utc) - dates[-1]).days
            if last_gap > 30:
                probability += 25
                factors.append({
                    "factor": "Meme resurrection",
                    "detail": f"Last mention {last_gap} days ago (>30 threshold)",
                    "contribution": 25,
                })
            elif last_gap > 14:
                probability += 10
                factors.append({
                    "factor": "Meme resurrection",
                    "detail": f"Last mention {last_gap} days ago (>14, <30)",
                    "contribution": 10,
                })

    # Factor 4: Sentiment trend (recent records)
    recent_ticker = [r for r in ticker_records if r.get("sentiment", 0) > 0.5]
    if recent_ticker:
        avg_sentiment = sum(r.get("sentiment", 0) for r in recent_ticker) / len(recent_ticker)
        contribution = min(avg_sentiment * 20, 20)
        probability += contribution
        factors.append({
            "factor": "Historical sentiment",
            "detail": f"Avg sentiment: {avg_sentiment:.2f}",
            "contribution": round(contribution, 1),
        })

    probability = min(probability, 100.0)
    return {
        "ticker": ticker_upper,
        "probability": round(probability, 1),
        "factors": factors,
        "has_history": len(ticker_records) > 0,
        "history_count": len(ticker_records),
    }


def cmd_predict(args: argparse.Namespace) -> None:
    """Predict pump probability for a ticker."""
    records = _read_history()
    result = _compute_pump_probability(args.ticker, records)

    print(f"Pump Probability Prediction for ${result['ticker']}")
    print("=" * 50)
    print(f"Probability Score: {result['probability']}/100")
    print(f"Historical Records: {result['history_count']}")
    print()
    print("Contributing Factors:")
    for factor in result["factors"]:
        print(f"  [{factor['contribution']:>5.1f}] {factor['factor']}: {factor['detail']}")

    print()
    if result["probability"] >= 70:
        print("Verdict: HIGH pump probability — monitor closely.")
        print("Recommendation: Consider early entry with tight stop loss.")
    elif result["probability"] >= 40:
        print("Verdict: MODERATE pump probability — watch and wait.")
        print("Recommendation: Set alerts, wait for confirmation signals.")
    else:
        print("Verdict: LOW pump probability — no action recommended.")
        print("Recommendation: Allocate attention elsewhere.")


def cmd_stats(_args: argparse.Namespace) -> None:  # pylint: disable=too-many-locals
    """Print summary statistics from pump history."""
    records = _read_history()
    if not records:
        print("No pump history found.")
        return

    total = len(records)
    successful = sum(1 for r in records if r.get("pump_result") == "successful")
    failed = sum(1 for r in records if r.get("pump_result") == "failed")
    unknown = total - successful - failed

    # Top tickers
    ticker_counts: dict[str, int] = defaultdict(int)
    for r in records:
        ticker_counts[r.get("ticker", "?").upper()] += 1
    top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Average peak gain
    gains: list[float] = []
    for r in records:
        price_at = r.get("price_at_detection", 0)
        peak = r.get("peak_price")
        if price_at and peak and price_at > 0:
            gain_pct = ((peak - price_at) / price_at) * 100
            gains.append(gain_pct)
    avg_gain = sum(gains) / len(gains) if gains else 0.0

    # FOMO phase distribution
    phase_counts: dict[str, int] = defaultdict(int)
    for r in records:
        phase_counts[r.get("fomo_phase", "unknown")] += 1

    print("WallStreetBets Pump History Summary")
    print("=" * 50)
    print(f"Total pumps recorded:    {total}")
    print(f"Successful pumps:        {successful}")
    print(f"Failed pumps:            {failed}")
    print(f"Unknown outcome:         {unknown}")
    if total > 0:
        print(f"Success rate:            {successful / total * 100:.1f}%")
    else:
        print("Success rate:            N/A")
    print(f"Avg peak gain:           {avg_gain:+.1f}%")
    print()
    print("Top Tickers by Pump Count:")
    for ticker, count in top_tickers:
        bar_chars = "█" * min(count, 20)
        print(f"  {ticker:<6} {count:>3} {bar_chars}")
    print()
    print("FOMO Phase Distribution:")
    for phase, count in sorted(phase_counts.items()):
        print(f"  {phase:<10} {count:>3}")
    print()
    print(f"History file: {HISTORY_FILE}")


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        description="Manage WSB pump detection history: record, analyze, predict",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 pump_history.py --record GME --score 82 --fomo early --mentions 47 --price 24.50
  python3 pump_history.py --learn
  python3 pump_history.py --predict GME
  python3 pump_history.py --stats
        """,
    )
    parser.add_argument("--record", "-r", metavar="TICKER",
                        help="Record a pump detection")
    parser.add_argument("--score", type=float, default=0.0,
                        help="Hype score (used with --record)")
    parser.add_argument("--fomo", type=str, default="unknown",
                        help="FOMO phase (used with --record)")
    parser.add_argument("--mentions", type=int, default=0,
                        help="Mention count (used with --record)")
    parser.add_argument("--price", type=float, default=0.0,
                        help="Price at detection (used with --record)")
    parser.add_argument("--learn", action="store_true",
                        help="Analyze history and extract patterns")
    parser.add_argument("--predict", "-p", metavar="TICKER",
                        help="Predict pump probability for a ticker")
    parser.add_argument("--stats", "-s", action="store_true",
                        help="Show pattern summary statistics")
    args = parser.parse_args()

    if args.record:
        cmd_record(args)
    elif args.learn:
        cmd_learn(args)
    elif args.predict:
        # Reuse args namespace with ticker attribute
        args.ticker = args.predict
        cmd_predict(args)
    elif args.stats:
        cmd_stats(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
