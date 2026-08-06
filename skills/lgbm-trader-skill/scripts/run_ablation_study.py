#!/usr/bin/env python3
"""Real ablation study: retrain models without each feature group on OOS.

Uses the existing LGBMTrainer + walk-forward purged splits. The SAME
fold splits are used for baseline and all ablated models so that OOS
predictions are directly comparable.

For speed, we reduce n_estimators to 100 and n_splits to 3.
IC delta = baseline IC − ablated IC; positive delta means the group
contributes predictive power on OOS.
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

def _build_group_mapping(df_columns: list[str]) -> dict[str, list[str]]:
    """Map actual DataFrame columns to feature groups via prefix matching.

    This is dynamic: it detects which groups have available features
    and returns only the columns that actually exist in the data.
    """
    prefix_map = {
        "momentum_vol": [
            "mom_", "trend_", "vol_", "prc_",
        ],
        "price_pattern": [
            "ms_",
        ],
        "fundamentals": [
            "val_", "si_",
        ],
        "macro_options": [
            "opt_", "rs_",
        ],
    }
    groups: dict[str, list[str]] = {}
    for gname, prefixes in prefix_map.items():
        matched = []
        for col in df_columns:
            if any(col.startswith(p) for p in prefixes):
                matched.append(col)
        if matched:
            groups[gname] = sorted(matched)
    return groups

# Ablation-specific LightGBM params (reduced for speed, SAME across all models)
_ABLATION_PARAMS = {
    "boosting_type": "gbdt",
    "objective": "regression",
    "metric": "rmse",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
    "n_estimators": 100,
    "early_stopping_rounds": 20,
    "random_state": 69420,
    "n_jobs": 2,
}

_WF_CONFIG = {
    "n_splits": 3,
    "train_months": 24,
    "val_months": 6,
    "embargo_days": 21,
}

_TARGET_CONFIG = {
    "horizon": 5,
    "atr_multiplier": 3.0,
    "pt_sl": (2.0, 2.0),
}


def _get_available_features(df: pd.DataFrame, group_name: str) -> list[str]:
    """Return features from a group that actually exist in the DataFrame."""
    candidates = _FEATURE_GROUPS.get(group_name, [])
    return [c for c in candidates if c in df.columns]


def _train_and_collect_oos(
    X: pd.DataFrame,
    y: pd.Series,
    folds: list[dict],
    desc: str,
) -> tuple[pd.Series, pd.Series]:
    """Train LightGBM on each fold, return OOS predictions and dates.

    Uses the same pre-computed walk-forward folds for all models.
    Returns (scores, dates) as aligned pd.Series.
    """
    import lightgbm as lgb

    scores_list: list[pd.Series] = []

    for sp in folds:
        train_mask = X.index.isin(sp["train_idx"])
        val_mask = X.index.isin(sp["val_idx"])

        X_train = X.loc[train_mask]
        y_train = y.loc[train_mask]
        X_val = X.loc[val_mask]
        y_val = y.loc[val_mask]

        if len(X_train) < 21 or len(X_val) < 5:
            continue

        X_tr = X_train.values.astype(np.float32)
        y_tr = y_train.values.astype(np.float32)
        X_vl = X_val.values.astype(np.float32)

        model = lgb.LGBMRegressor(**_ABLATION_PARAMS)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_vl, y_val.values.astype(np.float32))],
            eval_metric="rmse",
        )

        raw_preds = model.predict(X_vl)
        # Sigmoid → 0-100 score (same as production)
        score = 1.0 / (1.0 + np.exp(-np.clip(raw_preds, -50.0, 50.0))) * 100.0
        scores_list.append(pd.Series(score, index=X_val.index, name="score"))

    if not scores_list:
        return pd.Series(dtype=float), pd.Series(dtype=object)

    all_scores = pd.concat(scores_list).sort_index()
    all_dates = pd.Series(all_scores.index, index=all_scores.index, name="date")
    return all_scores, all_dates


def _build_forward_returns(
    df: pd.DataFrame, horizon: int = 20
) -> pd.Series:
    """Build forward returns from Close prices using shift(-horizon).

    Returns a Series indexed by date, with forward_return values.
    Only future data is used (shift is negative).
    """
    if "close" in df.columns:
        price = df["close"]
    elif "Close" in df.columns:
        price = df["Close"]
    else:
        raise KeyError("No close/Close column found")

    fwd = price.pct_change(horizon).shift(-horizon)
    fwd.name = "forward_return"
    return fwd


def main():
    parser = argparse.ArgumentParser(
        description="Real ablation study: retrain without each feature group"
    )
    parser.add_argument("--tickers", default="AAPL,MSFT",
                        help="Comma-separated tickers")
    parser.add_argument("--output",
                        default="/tmp/opencode/backtest_results/ablation")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--seed", type=int, default=69420)
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Need both skill path and MCP path
    mcp_src = _SKILL_ROOT.parent / "mcp" / "src"
    if str(mcp_src) not in sys.path and mcp_src.exists():
        sys.path.insert(0, str(mcp_src))

    all_results: dict[str, dict] = {}

    for ticker in tickers:
        t0_ticker = time.time()
        print(f"\n{'='*60}")
        print(f"Ablation study: {ticker}")
        print(f"{'='*60}")

        # ── 1. Fetch data ─────────────────────────────────────────
        print(f"  Fetching OHLCV ({args.period})...")
        import yfinance as yf
        df_raw = yf.download(ticker, period=args.period, auto_adjust=True,
                             progress=False)
        if df_raw.empty:
            print(f"  ✗ No data for {ticker}")
            continue
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.droplevel(1)
        df_raw.index = pd.to_datetime(df_raw.index)
        df_raw = df_raw.rename(columns={c: c.lower() for c in df_raw.columns})
        print(f"  {len(df_raw)} bars")

        # ── 2. Compute features ──────────────────────────────────
        print(f"  Computing features...")
        from features.pipeline import compute_all_features
        try:
            df = compute_all_features(df_raw, macro_df=None, ticker=ticker,
                                      drop_na=False)
        except Exception as e:
            print(f"  ✗ Feature computation failed: {e}")
            continue

        dfs = df.copy()
        print(f"  {len(dfs)} rows, {len(dfs.columns)} feature columns")

        # ── 3. Build forward returns (label) ─────────────────────
        dfs["forward_return"] = _build_forward_returns(df_raw, horizon=20)
        fwd = dfs["forward_return"].dropna()
        label = (fwd > 0).astype(float)
        common_idx = dfs.index.intersection(label.index)
        print(f"  {len(common_idx)} rows with forward return label")

        # ── 4. Build walk-forward splits (shared) ─────────────────
        print(f"  Building walk-forward splits...")
        from models.lgbm_trainer import LGBMTrainer

        # Configure trainer just for its walk_forward_split method
        config = {
            "model": {
                "params": _ABLATION_PARAMS,
                "walk_forward": _WF_CONFIG,
            },
            "target": _TARGET_CONFIG,
        }
        trainer = LGBMTrainer(config)
        splits = trainer.walk_forward_split(
            dfs, n_splits=_WF_CONFIG["n_splits"],
            train_months=_WF_CONFIG["train_months"],
            val_months=_WF_CONFIG["val_months"],
            embargo_days=_WF_CONFIG["embargo_days"],
        )
        print(f"  {len(splits)} folds produced")

        if len(splits) == 0:
            print(f"  ✗ No valid folds for {ticker}")
            continue

        # ── 5. Determine available feature groups (dynamic prefix match) ──
        feature_cols = sorted(
            c for c in dfs.columns
            if c not in ["open", "high", "low", "close", "volume", "forward_return"]
        )
        available_groups = _build_group_mapping(feature_cols)
        all_features = sorted(set(
            f for feats in available_groups.values() for f in feats
        ))
        print(f"  Available groups: {list(available_groups.keys())}")
        print(f"  Total features: {len(all_features)}")

        X_all = dfs[all_features].loc[common_idx].copy()
        y_all = label.loc[common_idx].copy()
        date_idx = pd.Series(common_idx, index=common_idx, name="date")

        # ── 6. Baseline (all features) ────────────────────────────
        print(f"\n  Training BASELINE (all {len(all_features)} features)...")
        base_scores, base_dates = _train_and_collect_oos(
            X_all, y_all, splits, f"{ticker}_baseline"
        )
        n_base_oos = len(base_scores)
        print(f"  Baseline OOS predictions: {n_base_oos}")

        if n_base_oos < 30:
            print(f"  ✗ Insufficient OOS predictions for {ticker}")
            continue

        # ── 7. Ablated models ─────────────────────────────────────
        ablated_scores: dict[str, pd.Series] = {}
        ablated_counts: dict[str, int] = {}

        for gname, gfeats in available_groups.items():
            remaining = [f for f in all_features if f not in gfeats]
            if len(remaining) < 5:
                print(f"  Skipping {gname} (only {len(remaining)} features left)")
                continue

            X_ablated = X_all[remaining].copy()
            print(f"  Training without {gname} ({len(gfeats)} features removed)...")
            abl_scores, abl_dates = _train_and_collect_oos(
                X_ablated, y_all, splits, f"{ticker}_no_{gname}"
            )
            n_abl = len(abl_scores)
            print(f"    {gname}: {n_abl} OOS predictions")

            if n_abl >= 10:
                ablated_scores[gname] = abl_scores
                ablated_counts[gname] = n_abl

        # ── 8. Run ablation analysis ──────────────────────────────
        from calibration.ablation import run_ablation, AblationStatus

        fwd_aligned = fwd.loc[common_idx]
        dates_dt = pd.DatetimeIndex(common_idx)

        report = run_ablation(
            baseline_scores=base_scores,
            forward_returns=fwd_aligned,
            dates=dates_dt,
            oos_cutoff=str(dates_dt.min().date()),
            ablated_scores=ablated_scores if ablated_scores else None,
            feature_groups=available_groups,
            ticker=ticker,
            model_version=f"ablation_{args.seed}",
            min_oos=10,
        )

        # ── 9. Store & print ──────────────────────────────────────
        ticker_report = report.model_dump()
        ticker_report["n_baseline_oos"] = n_base_oos
        ticker_report["ablated_counts"] = ablated_counts
        ticker_report["elapsed_s"] = round(time.time() - t0_ticker, 1)
        all_results[ticker] = ticker_report

        print(f"\n  Ablation results for {ticker}:")
        print(f"  Status: {report.status.value}")
        print(f"  Baseline IC rank: {report.baseline_ic_rank}")
        print(f"  Baseline hit rate: {report.baseline_hit_rate}")
        print(f"  n OOS: {report.n_oos}")
        if report.ranked_by_importance:
            print(f"\n  Ranking (IC delta = baseline − ablated):")
            print(f"  {'Group':<20} {'IC delta':>10} {'n_OOS':>8} {'Status':<20}")
            print(f"  {'-'*60}")
            for g in report.groups:
                delta_str = f"{g.ic_rank_delta:+.4f}" if g.ic_rank_delta is not None else "N/A"
                print(f"  {g.group_name:<20} {delta_str:>10} {g.n_oos:>8} {g.status:<20}")
            print(f"\n  NOTE: IC deltas are computed without bootstrap or p-value.")
            print(f"  Delta magnitude <0.005 may be indistinguishable from noise.")
        else:
            print(f"  No ranking available — {report.warnings}")

    # ── Save aggregate report ──────────────────────────────────────
    aggregate = {
        "report_type": "ablation_study",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "n_estimators": _ABLATION_PARAMS["n_estimators"],
            "n_splits": _WF_CONFIG["n_splits"],
            "train_months": _WF_CONFIG["train_months"],
            "val_months": _WF_CONFIG["val_months"],
            "seed": args.seed,
            "note": (
                "n_estimators reduced to 100 for speed. "
                "Same random_state and fold splits across all models. "
                "IC deltas DO NOT include bootstrap confidence intervals. "
                "Interpret with caution."
            ),
        },
        "tickers": all_results,
        "summary": {
            n: r.get("ranked_by_importance", [])
            for n, r in all_results.items()
        },
    }

    json_path = out_dir / "ablation_report.json"
    with open(json_path, "w") as f:
        json.dump(aggregate, f, indent=2, default=str)
    print(f"\nReport saved: {json_path}")

    # CSV summary
    csv_rows = []
    for ticker, tr in all_results.items():
        for g in tr.get("groups", []):
            csv_rows.append({
                "ticker": ticker,
                "group": g["group_name"],
                "ic_rank_delta": g.get("ic_rank_delta"),
                "hit_rate_delta": g.get("hit_rate_delta"),
                "n_oos": g.get("n_oos"),
                "status": g.get("status"),
            })
    if csv_rows:
        csv_path = out_dir / "ablation_summary.csv"
        pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
        print(f"CSV summary: {csv_path}")


if __name__ == "__main__":
    main()
