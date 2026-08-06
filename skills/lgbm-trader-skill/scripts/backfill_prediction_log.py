#!/usr/bin/env python3
"""Backfill prediction log from an export CSV.

Reads the point-in-time prediction export and writes resolved records
into the append-only JSONL prediction log. Supports deduplication,
OOS-only filtering, and per-ticker filtering.

Usage:
    python scripts/backfill_prediction_log.py \\
        --predictions /tmp/.../predictions.csv \\
        --log ~/.config/opencode/predictions/prediction_log.jsonl

    # OOS only, deduplication
    python scripts/backfill_prediction_log.py \\
        --predictions ...csv --cutoff 2024-06-30 --dedupe --ticker AAPL
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def load_predictions(csv_path: str) -> pd.DataFrame:
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {csv_path}")
    return pd.read_csv(csv_path)


def load_existing_keys(log_path: str) -> set[tuple[str, str, int]]:
    """Load existing (ticker, as_of, horizon_days) keys from the log."""
    p = Path(log_path)
    if not p.exists():
        return set()
    keys: set[tuple[str, str, int]] = set()
    with open(p, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                import json
                rec = json.loads(line)
                keys.add((
                    str(rec.get("ticker", "")),
                    str(rec.get("as_of", "")),
                    int(rec.get("horizon_days", 0)),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return keys


def main():
    parser = argparse.ArgumentParser(description="Backfill prediction log from export CSV")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--log",
                        default=str(Path.home() / ".config/opencode/predictions/prediction_log.jsonl"))
    parser.add_argument("--cutoff", default=None, help="Only backfill OOS (as_of > cutoff)")
    parser.add_argument("--ticker", default=None, help="Filter single ticker")
    parser.add_argument("--dedupe", action="store_true",
                        help="Skip records already in log (by ticker+as_of+horizon)")
    parser.add_argument("--model-version", default="vp_canonical_365d")
    args = parser.parse_args()

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading predictions: {args.predictions}")
    df = load_predictions(args.predictions)
    n_loaded = len(df)
    print(f"  {n_loaded} predictions loaded")

    if args.cutoff:
        df = df[df["as_of"] > args.cutoff]
        print(f"  After cutoff >{args.cutoff}: {len(df)} predictions")

    if args.ticker:
        df = df[df["ticker"] == args.ticker.upper()]
        print(f"  After ticker filter: {len(df)} predictions")

    existing_keys = load_existing_keys(str(log_path)) if args.dedupe else set()
    if existing_keys:
        print(f"  Existing log entries: {len(existing_keys)}")

    written = 0
    skipped_dedupe = 0
    skipped_missing = 0

    with open(log_path, "a") as f:
        for _, row in df.iterrows():
            key = (str(row["ticker"]), str(row["as_of"]), int(row["horizon_days"]))
            if args.dedupe and key in existing_keys:
                skipped_dedupe += 1
                continue

            fwd_ret = row.get("forward_return")
            if pd.isna(fwd_ret):
                skipped_missing += 1
                continue

            import json
            rec = {
                "ticker": str(row["ticker"]),
                "as_of": str(row["as_of"]),
                "model_version": args.model_version,
                "score": float(row["signal_score"]),
                "calibrated_probability": None,
                "horizon_days": int(row["horizon_days"]),
                "status": "resolved",
                "forward_return": float(fwd_ret),
                "resolved_at": None,
            }
            f.write(json.dumps(rec) + "\n")
            written += 1
            if args.dedupe:
                existing_keys.add(key)

    print(f"\nDone:")
    print(f"  Written:  {written}")
    if skipped_dedupe:
        print(f"  Skipped (dedupe): {skipped_dedupe}")
    if skipped_missing:
        print(f"  Skipped (missing forward_return): {skipped_missing}")
    print(f"  Log: {log_path}")


if __name__ == "__main__":
    main()
