#!/usr/bin/env python3
"""Export point-in-time VP predictions for multiple tickers.

Usage:
    python scripts/export_predictions.py \\
        --tickers-file ../market-accumulation-scanner/data/us_tickers.csv \\
        --limit 50 --period 5y --horizons 20,60,180 \\
        --output /tmp/opencode/backtest_results/vp_calibration_export/ \\
        --workers 4

Produces:
    predictions.csv    — all ticker/as_of/horizon predictions
    manifest.json      — metadata: n_tickers, date range, failures
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def _resolve_mcp_src() -> Path:
    env_path = os.environ.get("TRADING_MCP_SRC")
    if env_path:
        p = Path(env_path)
        if (p / "trading_mcp").exists():
            return p
    candidate = _SKILL_ROOT
    for _ in range(6):
        mcp_src = candidate / "mcp" / "src"
        if (mcp_src / "trading_mcp").exists():
            return mcp_src
        candidate = candidate.parent
    return Path(".")


def load_tickers_from_csv(path: str, limit: int = 0) -> list[str]:
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        tickers = df["symbol"].tolist()
    elif "ticker" in df.columns:
        tickers = df["ticker"].tolist()
    else:
        tickers = df.iloc[:, 0].tolist()
    tickers = [str(t).strip() for t in tickers if str(t).strip() and str(t).lower() != "nan"]
    if limit > 0:
        tickers = tickers[:limit]
    return tickers


def fetch_ohlcv(ticker: str, period: str = "5y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"No data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.index = pd.to_datetime(df.index)
    return df.rename(columns={c: c.capitalize() for c in df.columns})


def compute_vp_signal(
    ohlcv: pd.DataFrame,
    window_days: int = 365,
    min_bars: int = 252,
    vp_min_window_days: int = 20,
) -> pd.Series:
    from trading_mcp.analysis.volume_profile import get_profile_levels

    scores = pd.Series(np.nan, index=ohlcv.index, dtype=float)
    start_i = max(min_bars, window_days)
    for i in range(start_i, len(ohlcv)):
        window = ohlcv.iloc[max(0, i - window_days + 1) : i + 1]
        if len(window) < vp_min_window_days:
            continue
        try:
            levels = get_profile_levels(window)
            scores.iloc[i] = float(levels["score"])
        except (ValueError, KeyError, TypeError):
            continue
    return scores.dropna()


def process_single_ticker(
    ticker: str,
    horizons: list[int],
    period: str,
    min_bars: int,
    vp_window_days: int,
) -> dict:
    try:
        ohlcv = fetch_ohlcv(ticker, period=period)
    except RuntimeError as exc:
        return {"ticker": ticker, "status": "failed", "error": str(exc)}

    available_bars = len(ohlcv)
    max_horizon = max(horizons)
    required_bars = min_bars + max_horizon

    if available_bars < required_bars:
        return {
            "ticker": ticker,
            "status": "insufficient_data",
            "available_bars": available_bars,
            "required_bars": required_bars,
        }

    signal = compute_vp_signal(ohlcv, window_days=vp_window_days, min_bars=min_bars)
    if signal.empty or len(signal) < min_bars:
        return {
            "ticker": ticker,
            "status": "insufficient_data",
            "available_bars": available_bars,
            "required_bars": required_bars,
            "error": f"Signal bars={len(signal)}, need >={min_bars}",
        }

    close = ohlcv["Close"]
    rows = []
    supported_horizons = [h for h in horizons if available_bars >= min_bars + h]

    for h in supported_horizons:
        fwd_price = close.shift(-h)
        fwd_return = close.pct_change(h).shift(-h)
        max_i = len(close) - h
        for i in range(max_i):
            as_of_date = close.index[i]
            score_val = signal.get(as_of_date, np.nan)
            fwd_p = fwd_price.iloc[i]
            fwd_r = fwd_return.iloc[i]
            if pd.isna(score_val) or pd.isna(fwd_p) or pd.isna(fwd_r):
                continue
            rows.append({
                "ticker": ticker,
                "as_of": str(as_of_date.date()),
                "signal_score": float(score_val),
                "horizon_days": h,
                "forward_return": float(fwd_r),
                "forward_price": float(fwd_p),
            })

    return {
        "ticker": ticker,
        "status": "ok",
        "available_bars": available_bars,
        "n_predictions": len(rows),
        "predictions": rows,
    }


def main():
    mcp_src = _resolve_mcp_src()
    if str(mcp_src) not in sys.path and (mcp_src / "trading_mcp").exists():
        sys.path.insert(0, str(mcp_src))

    parser = argparse.ArgumentParser(
        description="Export VP point-in-time predictions for multi-ticker calibration"
    )
    parser.add_argument("--tickers-file", required=True, help="CSV with ticker symbols")
    parser.add_argument("--limit", type=int, default=60, help="Max tickers (default 60)")
    parser.add_argument("--period", default="5y", help="yfinance period (default 5y)")
    parser.add_argument("--horizons", default="20,60,180", help="Comma-separated horizons")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--vp-window", type=int, default=365, help="VP rolling window days")
    parser.add_argument("--min-bars", type=int, default=252, help="Min bars for signal")
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    tickers = load_tickers_from_csv(args.tickers_file, limit=args.limit)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting predictions for {len(tickers)} tickers")
    print(f"  Horizons: {horizons}")
    print(f"  Period: {args.period}")
    print(f"  Output: {out_dir}")
    print(f"  Workers: {args.workers}")

    t0 = time.time()
    all_predictions: list[dict] = []
    failures: list[dict] = []
    ok_tickers = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for t in tickers:
            f = pool.submit(
                process_single_ticker, t, horizons, args.period,
                args.min_bars, args.vp_window,
            )
            futures[f] = t

        for f in as_completed(futures):
            t = futures[f]
            try:
                result = f.result(timeout=120)
            except Exception as exc:
                failures.append({
                    "ticker": t,
                    "status": "failed",
                    "error": str(exc),
                })
                continue

            if result["status"] == "ok":
                all_predictions.extend(result["predictions"])
                ok_tickers += 1
                print(f"  ✓ {t}: {result['n_predictions']} predictions "
                      f"({result['available_bars']} bars)")
            else:
                failures.append(result)
                print(f"  ✗ {t}: {result['status']} — "
                      f"{result.get('available_bars', '?')} bars "
                      f"(need {result.get('required_bars', '?')})")

    elapsed = time.time() - t0

    df = pd.DataFrame(all_predictions)
    csv_path = out_dir / "predictions.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nPredictions saved: {csv_path} ({len(df)} rows)")

    as_of_min = df["as_of"].min() if not df.empty else "N/A"
    as_of_max = df["as_of"].max() if not df.empty else "N/A"

    manifest = {
        "signal_version": "vp_canonical_365d",
        "signal_description": (
            "Volume Profile composite score (rolling 365-day window, "
            "no look-ahead)"
        ),
        "n_tickers_requested": len(tickers),
        "n_tickers_ok": ok_tickers,
        "n_tickers_failed": len(failures),
        "total_predictions": len(df),
        "date_range": [as_of_min, as_of_max],
        "horizons": horizons,
        "period": args.period,
        "vp_window_days": args.vp_window,
        "min_bars": args.min_bars,
        "elapsed_seconds": round(elapsed, 1),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "failures": [
            {"ticker": f["ticker"], "status": f["status"],
             "error": f.get("error", "")}
            for f in failures
        ],
    }

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest saved: {manifest_path}")

    print(f"\nDone: {ok_tickers} tickers OK, {len(failures)} failed, "
          f"{elapsed:.1f}s")


if __name__ == "__main__":
    main()
