#!/usr/bin/env python3
"""
Watchlist Update Script
=======================
Reads the latest scan report CSV, cross-references with the persistent
watchlist state (watchlist_state.json), computes score deltas and trends,
generates alerts, and saves the updated state.

Usage:
    python3 watchlist_update.py
    python3 watchlist_update.py --report path/to/scan_report.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


SKILL_DIR = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = SKILL_DIR / "scripts" / "watchlist_state.json"
REPORTS_DIR = SKILL_DIR / "reports"

_PYDANTIC_AVAILABLE = False
try:
    sys.path.insert(0, str(
        Path("~/.config/opencode/skills/stock-crypto-analysis").expanduser()
    ))
    from schemas import (  # type: ignore[import-not-found]
        ScoreSnapshot,
        WatchlistEntry,
        WatchlistState,
    )
    _PYDANTIC_AVAILABLE = True
except ImportError:
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def find_latest_report() -> Optional[Path]:
    """Scan reports/*/ directories for the most recent scan_report CSV file."""
    best: Optional[Path] = None
    best_ts: Optional[datetime] = None

    if not REPORTS_DIR.exists():
        return None

    for universe_dir in sorted(REPORTS_DIR.iterdir()):
        if not universe_dir.is_dir():
            continue
        for report_file in sorted(universe_dir.glob("scan_report_*.csv")):
            try:
                stem = report_file.stem
                date_str = stem.replace("scan_report_", "")
                report_dt = datetime.strptime(date_str, "%Y-%m-%d_%H%M")
            except ValueError:
                continue
            if best_ts is None or report_dt > best_ts:
                best_ts = report_dt
                best = report_file

    return best


def load_watchlist_state(path: Optional[Path] = None) -> dict[str, Any]:
    """Load watchlist_state.json and return as a plain dict."""
    filepath = path or WATCHLIST_PATH
    if not filepath.exists():
        return {"last_updated": None, "tickers": {}}
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {"last_updated": None, "tickers": {}}


def save_watchlist_state(state: dict[str, Any], path: Optional[Path] = None) -> None:
    """Save watchlist state to JSON file."""
    filepath = path or WATCHLIST_PATH
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, default=str)
    print(f"Watchlist state saved to: {filepath}")


def load_report(report_path: Path) -> list[dict[str, str]]:
    """Load a scan report CSV and return a list of rows as dicts."""
    rows: list[dict[str, str]] = []
    with open(report_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def compute_snapshot(row: dict[str, str]) -> dict[str, Any]:
    """Build a ScoreSnapshot-compatible dict from a CSV row."""
    try:
        score = float(row.get("final_score", 0))
    except (ValueError, TypeError):
        score = 0.0

    dimensions: dict[str, float] = {}
    for dim_key in ("wyckoff", "volprof", "pa", "competitive", "sentiment", "fundamentals"):
        try:
            dimensions[dim_key] = float(row.get(dim_key, 0))
        except (ValueError, TypeError):
            dimensions[dim_key] = 0.0

    return {
        "date": _now().isoformat(),
        "score": score,
        "dimensions": dimensions,
    }


def find_snapshot_before(
    history: list[dict[str, Any]],
    days: int,
) -> Optional[dict[str, Any]]:
    """Find the most recent snapshot that is at least `days` days old."""
    now = _now()
    threshold = now - timedelta(days=days)
    best: Optional[dict[str, Any]] = None
    best_dt: Optional[datetime] = None

    for snap in history:
        snap_dt = _parse_dt(snap.get("date"))
        if snap_dt is None:
            continue
        if snap_dt <= threshold:
            if best_dt is None or snap_dt > best_dt:
                best_dt = snap_dt
                best = snap

    return best


def determine_trend(
    entry: dict[str, Any],
    new_snapshot: dict[str, Any],
    delta_7d: float,
    delta_30d: float,
    num_snapshots: int,
) -> str:
    """Determine trend for a ticker based on score evolution."""
    if num_snapshots <= 1:
        return "new"
    if delta_7d > 5:
        return "improving"
    if delta_7d < -5:
        return "deteriorating"
    return "stable"


def generate_alerts(
    entry: dict[str, Any],
    new_snapshot: dict[str, Any],
    delta_7d: float,
    delta_14d: float,
    num_snapshots: int,
) -> list[str]:
    """Generate human-readable alerts based on score evolution rules."""
    alerts: list[str] = []
    score = new_snapshot["score"]
    history: list[dict[str, Any]] = entry.get("history", [])

    if num_snapshots <= 1:
        pass

    if score > 70:
        prev_snapshot = history[-1] if history else None
        if prev_snapshot and prev_snapshot.get("score", 0) <= 70:
            alerts.append(
                f"BREAKOUT CANDIDATE: score crossed above 70 "
                f"({prev_snapshot.get('score', 0):.1f} → {score:.1f})"
            )

    prev_snapshot = history[-1] if history else None
    if prev_snapshot and score < 50 and prev_snapshot.get("score", 0) >= 60:
        alerts.append(
            f"DETERIORATING: score dropped below 50 after being above 60 "
            f"({prev_snapshot.get('score', 0):.1f} → {score:.1f})"
        )

    if delta_14d > 15:
        alerts.append(
            f"STRONG MOMENTUM: score improved {delta_14d:+.1f} pts in 14 days"
        )

    if num_snapshots >= 4:
        recent_4 = history[-3:] + [new_snapshot] if len(history) >= 3 else []
        if len(recent_4) >= 4:
            all_above_70 = all(s.get("score", 0) > 70 for s in recent_4[-4:])
            scores_last_4 = [s.get("score", 0) for s in recent_4[-4:]]
            max_diff = max(scores_last_4) - min(scores_last_4)
            if all_above_70 and max_diff < 5:
                alerts.append(
                    f"CONSOLIDATED BULLISH: score stable >70 for 4+ scans "
                    f"({min(scores_last_4):.1f}–{max(scores_last_4):.1f})"
                )

    return alerts


def process_report(
    report_path: Path,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Main processing: load report, update state, generate alerts."""
    rows = load_report(report_path)
    if not rows:
        print(f"Report is empty: {report_path}")
        return state

    all_alerts: list[str] = []
    tickers_updated = 0

    for row in rows:
        symbol = row.get("symbol", "").strip()
        if not symbol:
            continue

        snapshot = compute_snapshot(row)

        if symbol not in state["tickers"]:
            state["tickers"][symbol] = {
                "ticker": symbol,
                "history": [],
                "trend": "new",
                "score_delta_7d": 0.0,
                "score_delta_30d": 0.0,
                "alerts": [],
            }

        entry = state["tickers"][symbol]
        entry["history"].append(snapshot)
        num_snaps = len(entry["history"])

        snap_7d = find_snapshot_before(entry["history"], 7)
        snap_30d = find_snapshot_before(entry["history"], 30)
        snap_14d = find_snapshot_before(entry["history"], 14)

        score = snapshot["score"]
        delta_7d = score - snap_7d["score"] if snap_7d else 0.0
        delta_30d = score - snap_30d["score"] if snap_30d else 0.0
        delta_14d = score - snap_14d["score"] if snap_14d else 0.0

        entry["score_delta_7d"] = round(delta_7d, 2)
        entry["score_delta_30d"] = round(delta_30d, 2)

        trend = determine_trend(entry, snapshot, delta_7d, delta_30d, num_snaps)
        entry["trend"] = trend

        alerts = generate_alerts(entry, snapshot, delta_7d, delta_14d, num_snaps)
        entry["alerts"] = alerts

        if alerts:
            for alert in alerts:
                all_alerts.append(f"[{symbol}] {alert}")

        tickers_updated += 1

    state["last_updated"] = _now().isoformat()
    print(f"Processed {len(rows)} rows from report, updated {tickers_updated} tickers.")

    if all_alerts:
        print(f"\n{'─' * 60}")
        print(f"  ALERTS ({len(all_alerts)})")
        print(f"{'─' * 60}")
        for alert in all_alerts:
            print(f"  {alert}")
        print(f"{'─' * 60}")
    else:
        print("\nNo alerts generated.")

    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update watchlist state from latest scan report"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Path to a specific scan report CSV (auto-detected if omitted)",
    )
    args = parser.parse_args()

    if args.report:
        report_path = args.report.expanduser().resolve()
        if not report_path.exists():
            print(f"Error: report not found: {report_path}", file=sys.stderr)
            sys.exit(1)
    else:
        report_path = find_latest_report()
        if report_path is None:
            print(
                "Error: no scan reports found under reports/. "
                "Run a scan first or use --report to specify a path.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Auto-detected report: {report_path}")

    state = load_watchlist_state()
    previous_ticker_count = len(state.get("tickers", {}))

    state = process_report(report_path, state)
    save_watchlist_state(state)

    new_ticker_count = len(state.get("tickers", {}))
    print(f"\nTickers tracked: {previous_ticker_count} → {new_ticker_count}")


if __name__ == "__main__":
    main()
