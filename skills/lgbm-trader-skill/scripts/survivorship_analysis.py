#!/usr/bin/env python3
"""Survivorship bias analysis: full vs point-in-time (PIT) universe.

Filters the prediction export by S&P 500 membership at each as_of date.
Compares metrics (IC, hit rate, n predictions) between:
- FULL: all predictions in the export CSV (current universe, survivorship-biased)
- PIT: only predictions where the ticker was an S&P 500 member at as_of

Persists JSON + CSV report in the output directory.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def load_predictions(csv_path: str) -> pd.DataFrame:
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"Predictions not found: {csv_path}")
    return pd.read_csv(csv_path)


def filter_pit(
    df: pd.DataFrame, universe_path: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Split predictions into PIT-valid and PIT-excluded.

    Returns:
        (df_pit, df_excluded, delisted_tickers)
    """
    from trading_mcp.data.universe import get_universe_members

    # Cache members by date to avoid repeated lookups
    member_cache: dict[str, set[str]] = {}
    all_dates = sorted(df["as_of"].unique())

    print(f"  Computing PIT membership for {len(all_dates)} unique dates...")
    for d in all_dates:
        members = get_universe_members(d, path=universe_path)
        member_cache[d] = set(members)

    pit_mask = df.apply(
        lambda row: row["ticker"].upper() in member_cache.get(row["as_of"], set()),
        axis=1,
    )
    df_pit = df[pit_mask].copy()
    df_excluded = df[~pit_mask].copy()

    excluded_tickers = sorted(set(df_excluded["ticker"].unique()))

    print(f"  PIT-valid: {len(df_pit)} predictions ({df_pit['ticker'].nunique()} tickers)")
    print(f"  PIT-excluded: {len(df_excluded)} predictions "
          f"({df_excluded['ticker'].nunique()} tickers)")
    if excluded_tickers:
        print(f"  Excluded tickers: {excluded_tickers[:20]}"
              + ("..." if len(excluded_tickers) > 20 else ""))

    return df_pit, df_excluded, excluded_tickers


def evaluate_pooled(
    df: pd.DataFrame, horizons: list[int], label: str,
) -> dict[int, dict]:
    """Evaluate pooled metrics for each horizon."""
    from backtest.contract import BacktestConfig, CostModel
    from backtest.evaluator import evaluate
    from backtest.contract import BacktestPrediction

    cm = CostModel()
    results = {}

    for h in horizons:
        sub = df[df["horizon_days"] == h]
        if len(sub) == 0:
            results[h] = {"n": 0, "ic_rank": None, "hit_rate": None,
                          "mean_return_pct": None, "quintile_spread": None}
            continue

        preds = []
        for _, row in sub.iterrows():
            preds.append(BacktestPrediction(
                ticker=str(row["ticker"]),
                as_of=str(row["as_of"]),
                signal_score=float(row["signal_score"]),
                horizon_days=int(row["horizon_days"]),
                forward_return=float(row["forward_return"]),
                forward_price=float(row["forward_price"]),
            ))

        cfg = BacktestConfig(
            horizons_days=[h], apply_costs=False, cost_model=cm,
            min_horizon_observations=10, strict_mode=False,
            permutation_control=False,
        )
        result = evaluate(preds, config=cfg, ticker=label)
        for hr in result.horizons:
            if hr.horizon_days == h:
                results[h] = {
                    "n": hr.n_observations,
                    "ic_rank": hr.ic_rank,
                    "ic_pearson": hr.ic_pearson,
                    "hit_rate": hr.hit_rate,
                    "mean_return_pct": hr.mean_return_pct,
                    "quintile_spread": hr.quintile_spread,
                }
                break
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Survivorship bias analysis: full vs PIT universe"
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--horizons", default="20,60,180")
    parser.add_argument("--universe-file", default=None,
                        help="Path to historical_universe_sp500.csv")
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading: {args.predictions}")
    t0 = time.time()
    df = load_predictions(args.predictions)
    print(f"  {len(df)} predictions, {df['ticker'].nunique()} tickers")

    # PIT filter
    print(f"\nFiltering by PIT membership...")
    df_pit, df_excluded, delisted_tickers = filter_pit(df, args.universe_file)

    # Evaluate both
    print(f"\nEvaluating FULL...")
    metrics_full = evaluate_pooled(df, horizons, "FULL")
    print(f"Evaluating PIT...")
    metrics_pit = evaluate_pooled(df_pit, horizons, "PIT")

    # Comparison
    comparison = {}
    for h in horizons:
        f = metrics_full.get(h, {})
        p = metrics_pit.get(h, {})
        ic_full = f.get("ic_rank")
        ic_pit = p.get("ic_rank")
        ic_delta = (
            round(abs(ic_pit) - abs(ic_full) if ic_full and ic_pit else None, 6)
            if (ic_full is not None and ic_pit is not None) else None
        )
        comparison[h] = {
            "horizon_days": h,
            "full": f,
            "pit": p,
            "n_excluded": int(len(df_excluded[df_excluded["horizon_days"] == h])),
            "n_full": f.get("n", 0),
            "n_pit": p.get("n", 0),
            "retention_pct": round(p.get("n", 0) / max(f.get("n", 1), 1) * 100, 1),
            "ic_delta_abs": ic_delta,
            "hit_rate_delta": (
                round(p.get("hit_rate", 0) - f.get("hit_rate", 0), 4)
                if (f.get("hit_rate") and p.get("hit_rate")) else None
            ),
        }

    # Build report
    n_tickers_full = df["ticker"].nunique()
    n_tickers_pit = df_pit["ticker"].nunique()

    report = {
        "report_type": "survivorship_analysis",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_predictions_full": int(len(df)),
        "n_predictions_pit": int(len(df_pit)),
        "n_predictions_excluded": int(len(df_excluded)),
        "n_tickers_full": n_tickers_full,
        "n_tickers_pit": n_tickers_pit,
        "n_tickers_excluded": len(delisted_tickers),
        "delisted_tickers": delisted_tickers,
        "retention_pct": round(len(df_pit) / max(len(df), 1) * 100, 1),
        "horizons": horizons,
        "universe_file": args.universe_file or "default (sp500_historical)",
        "comparison": comparison,
        "summary": {
            "survivorship_matters": any(
                c.get("ic_delta_abs") is not None and abs(c["ic_delta_abs"]) > 0.005
                for c in comparison.values()
            ),
            "note": (
                "PIT filter excludes tickers not yet in S&P 500 or already delisted "
                "at each as_of date. Full (current universe) includes all tickers "
                "regardless of historical membership → survivorship bias."
            ),
        },
        "limits": [
            "Historical universe from Wikipedia (503 active + 4 delisted)",
            "Only major 2020-2026 delistings added manually (CIT, FRC, SBNY, SIVB)",
            "Routine index additions/removals may not be fully captured",
            "Wikipedia may lag S&P announcements by 1-3 days",
        ],
    }

    # Save
    json_path = out_dir / "survivorship_analysis.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON: {json_path}")

    csv_rows = []
    for h in horizons:
        c = comparison.get(h, {})
        csv_rows.append({
            "horizon_days": h,
            "n_full": c.get("n_full"),
            "n_pit": c.get("n_pit"),
            "n_excluded": c.get("n_excluded"),
            "retention_pct": c.get("retention_pct"),
            "ic_full": (c.get("full") or {}).get("ic_rank"),
            "ic_pit": (c.get("pit") or {}).get("ic_rank"),
            "ic_delta_abs": c.get("ic_delta_abs"),
            "hit_rate_full": (c.get("full") or {}).get("hit_rate"),
            "hit_rate_pit": (c.get("pit") or {}).get("hit_rate"),
            "hit_rate_delta": c.get("hit_rate_delta"),
        })
    csv_path = out_dir / "survivorship_summary.csv"
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"CSV: {csv_path}")

    # Terminal
    print(f"\n{'='*70}")
    print("SURVIVORSHIP BIAS ANALYSIS")
    print(f"{'='*70}")
    print(f"  Full: {len(df)} preds, {n_tickers_full} tickers")
    print(f"  PIT:  {len(df_pit)} preds, {n_tickers_pit} tickers")
    print(f"  Excluded: {len(df_excluded)} preds, {len(delisted_tickers)} tickers")
    print(f"  Delisted: {delisted_tickers}")

    for h in horizons:
        c = comparison[h]
        print(f"\n── Horizon {h}d ──")
        print(f"  n: {c['n_pit']}/{c['n_full']} ({c['retention_pct']}% retained)")
        ic_f = (c.get("full") or {}).get("ic_rank")
        ic_p = (c.get("pit") or {}).get("ic_rank")
        print(f"  IC full: {ic_f:.4f}" if ic_f else "  IC full: N/A")
        print(f"  IC pit:  {ic_p:.4f}" if ic_p else "  IC pit:  N/A")
        if c["ic_delta_abs"] is not None:
            print(f"  IC delta: {c['ic_delta_abs']:+.6f}")
        print(f"  Hit rate full: {(c.get('full') or {}).get('hit_rate', 0):.4f}")
        print(f"  Hit rate pit:  {(c.get('pit') or {}).get('hit_rate', 0):.4f}")

    impact = "YES — metrics differ" if report["summary"]["survivorship_matters"] else "negligible"
    print(f"\nSurvivorship impact: {impact}")

    elapsed = time.time() - t0
    print(f"Elapsed: {elapsed:.1f}s")
    print(f"Reports: {out_dir}/")


if __name__ == "__main__":
    main()
