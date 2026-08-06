#!/usr/bin/env python3
"""Print performance report from prediction log.

Loads the append-only JSONL prediction log and prints aggregated
performance metrics via monitoring.prediction_log.PredictionLogger.
Supports filtering by ticker, horizon, cutoff, and min_required.

Usage:
    python scripts/performance_report.py \\
        --log ~/.config/opencode/predictions/prediction_log.jsonl \\
        --min-required 20 --cutoff 2024-06-30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Performance report from prediction log")
    parser.add_argument("--log",
                        default=str(Path.home() / ".config/opencode/predictions/prediction_log.jsonl"))
    parser.add_argument("--ticker", default=None, help="Filter by ticker")
    parser.add_argument("--horizon", type=int, default=None, help="Filter by horizon_days")
    parser.add_argument("--cutoff", default=None, help="Only records with as_of > cutoff")
    parser.add_argument("--min-required", type=int, default=20)
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        print("Backfill first: python scripts/backfill_prediction_log.py --predictions ...")
        sys.exit(1)

    from monitoring.prediction_log import PredictionLogger

    # Load and filter
    plog = PredictionLogger(str(log_path))
    all_records = plog._read_all()

    filtered = all_records
    if args.ticker:
        filtered = [r for r in filtered if r.ticker == args.ticker.upper()]
    if args.horizon is not None:
        filtered = [r for r in filtered if r.horizon_days == args.horizon]
    if args.cutoff:
        filtered = [r for r in filtered if r.as_of > args.cutoff]

    # Write filtered records to temp log for performance_report
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in filtered:
            f.write(r.model_dump_json() + "\n")
        tmp_path = f.name

    try:
        tmp_logger = PredictionLogger(tmp_path)
        report = tmp_logger.performance_report(min_required=args.min_required)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Print
    print(f"\n{'='*60}")
    print("PREDICTION LOG — PERFORMANCE REPORT")
    print(f"{'='*60}")
    print(f"  Log:       {log_path}")
    print(f"  Ticker:    {args.ticker or 'ALL'}")
    print(f"  Horizon:   {args.horizon or 'ALL'}")
    print(f"  Cutoff:    {args.cutoff or 'none'}")
    print(f"  n_total:   {report.n_total}")
    print(f"  n_resolved:{report.n_resolved}")
    print(f"  n_pending: {report.n_pending}")
    print(f"  min_required: {report.min_required}")
    if report.overlap_factor:
        print(f"  overlap_factor: {report.overlap_factor:.1f}x")
        print(f"  n_independent_est: ~{report.n_independent_estimate:.0f}")
    print(f"  Status:    {report.status}")
    print()
    if report.status == "ok":
        print("  ── Directional metrics (always valid) ──")
        print(f"  Hit rate:          {report.hit_rate:.4f}" if report.hit_rate else "  Hit rate:          N/A")
        print(f"  Mean return:       {report.mean_return:.6f}" if report.mean_return else "  Mean return:       N/A")
        print(f"  IC rank:           {report.ic_rank:.4f}" if report.ic_rank else "  IC rank:           N/A")
        print(f"  Directional p-val: {report.directional_p_value:.6f}" if report.directional_p_value is not None else "  Directional p-val: N/A")
        print()
        print("  ── Risk-adjusted metrics ──")
        if report.sharpe_annualized is not None:
            print(f"  Sharpe (ann):      {report.sharpe_annualized:.4f}")
        elif report.sharpe_biased_raw is not None:
            print(f"  Sharpe (ann):      INVALID (overlap)")
            print(f"  Sharpe biased raw: {report.sharpe_biased_raw:.4f} (DIAGNOSTIC ONLY)")
        if report.warnings:
            print("\n  Warnings:")
            for w in report.warnings:
                print(f"    ⚠ {w}")
    else:
        print("  (Metrics unavailable — insufficient resolved outcomes)")


if __name__ == "__main__":
    main()
