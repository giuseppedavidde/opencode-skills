#!/usr/bin/env python3
"""Backtest CLI: evaluate OHLCV-only signals point-in-time.

Usage:
    python scripts/run_backtest.py --ticker AAPL --horizons 20,60,180
    python scripts/run_backtest.py --ticker NOOB --diagnostic  # short history

The backtest computes forward returns at each horizon from strictly
future data only. The signal is the CANONICAL Volume Profile composite
score from ``trading_mcp.analysis.volume_profile.get_profile_levels``.

P0 August 2026: explicit build status, per-horizon capability, VP window
coverage, diagnostic mode for short histories.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))


def _resolve_mcp_src() -> Path:
    """Resolve trading_mcp source path robustly.

    Searches in order:
    1. TRADING_MCP_SRC environment variable
    2. ../mcp/src relative to opencode-skills repo root
    3. PYTHONPATH / installed package (skip path injection)
    """
    env_path = os.environ.get("TRADING_MCP_SRC")
    if env_path:
        p = Path(env_path)
        if (p / "trading_mcp").exists():
            return p

    # Walk up from skill root to find opencode-skills/mcp/src
    candidate = _SKILL_ROOT
    for _ in range(6):
        mcp_src = candidate / "mcp" / "src"
        if (mcp_src / "trading_mcp").exists():
            return mcp_src
        candidate = candidate.parent

    # Fallback: try import directly — may already be on PYTHONPATH
    return Path(".")


def fetch_ohlcv(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Fetch OHLCV from yfinance."""
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"No data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.index = pd.to_datetime(df.index)
    return df.rename(columns={c: c.capitalize() for c in df.columns})


def compute_vp_signal_canonical(
    ohlcv: pd.DataFrame,
    window_days: int = 365,
    min_bars: int = 252,
    diagnostic: bool = False,
    vp_min_window_days: int = 20,
) -> pd.Series:
    """Volume Profile signal canonico (via ``trading_mcp``).

    Per ogni barra ``t``, calcola lo score VP usando una finestra
    rolling di ``window_days`` giorni che include SOLO dati fino a ``t``
    (incluso). Nessun look-ahead: la finestra e' ``[t - window_days, t]``.

    In modalita' diagnostica, usa una finestra adattiva >= vp_min_window_days.
    Il segnale e' etichettato come diagnostico, non comparabile alla
    calibrazione a 365d.

    Returns:
        Series allineata a ``ohlcv.index`` con score VP 0-100 dove
        disponibile, NaN per le prime barre.
    """
    try:
        from trading_mcp.analysis.volume_profile import get_profile_levels
    except ImportError as exc:
        raise RuntimeError(
            "Impossibile importare trading_mcp.analysis.volume_profile. "
            "Assicurati che il progetto opencode-skills/mcp sia installato "
            "o accessibile nel PYTHONPATH."
        ) from exc

    scores = pd.Series(np.nan, index=ohlcv.index, dtype=float)

    # In diagnostic mode, compute adaptive window based on available data
    effective_window = window_days
    if diagnostic:
        effective_window = max(vp_min_window_days, len(ohlcv) // 4)
        effective_window = min(effective_window, len(ohlcv))

    effective_min_bars = min(min_bars, len(ohlcv) // 2)
    if diagnostic:
        effective_min_bars = max(vp_min_window_days, effective_min_bars)

    start_i = max(effective_min_bars, effective_window)

    for i in range(start_i, len(ohlcv)):
        window = ohlcv.iloc[max(0, i - effective_window + 1) : i + 1]
        if len(window) < vp_min_window_days:
            continue
        try:
            levels = get_profile_levels(window)
            scores.iloc[i] = float(levels["score"])
        except (ValueError, KeyError, TypeError):
            continue

    return scores.dropna()


def main() -> None:
    """Backtest CLI entry point: fetch OHLCV, compute VP signal, evaluate."""
    # ── Lazy MCP_SRC resolution (only at CLI invocation, not import) ──
    mcp_src = _resolve_mcp_src()
    if str(mcp_src) not in sys.path and (mcp_src / "trading_mcp").exists():
        sys.path.insert(0, str(mcp_src))

    parser = argparse.ArgumentParser(
        description="Backtest OHLCV-only signals point-in-time (P0 v2)"
    )
    parser.add_argument(
        "--ticker", default="SPY", help="Ticker symbol (default: SPY)"
    )
    parser.add_argument(
        "--horizons",
        default="20,60,180",
        help="Forward horizons in trading days (comma-separated)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for CSV/JSON (default: ./backtest_results/)",
    )
    parser.add_argument(
        "--period",
        default="5y",
        help="yfinance history period (default: 5y)",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        default=False,
        help=(
            "Enable diagnostic/short-history mode: adaptive VP window "
            "(>=20 bars), results flagged as diagnostic-only."
        ),
    )
    parser.add_argument(
        "--vp-window",
        type=int,
        default=365,
        help="VP rolling window in days (default: 365 for canonical 252-trading-day)",
    )
    parser.add_argument(
        "--min-bars",
        type=int,
        default=252,
        help="Minimum bars for signal generation (default: 252)",
    )
    parser.add_argument(
        "--min-obs",
        type=int,
        default=30,
        help="Minimum OOS observations per horizon (default: 30)",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        default=False,
        help="Disable strict mode — allows backtest with fewer bars",
    )
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    out_dir = Path(args.output) if args.output else Path("backtest_results")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching OHLCV for {args.ticker} ({args.period})...")
    try:
        ohlcv = fetch_ohlcv(args.ticker, period=args.period)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    n_bars = len(ohlcv)
    print(f"  Downloaded: {n_bars} bars")

    from backtest.contract import (
        BacktestBuildStatus,
        BacktestConfig,
        build_predictions_from_ohlcv,
    )
    from backtest.evaluator import evaluate

    vp_window = args.vp_window if not args.diagnostic else max(
        args.vp_window // 12, 20, min(n_bars // 4, args.vp_window)
    )

    config = BacktestConfig(
        horizons_days=horizons,
        min_bars=args.min_bars,
        strict_mode=not args.no_strict,
        vp_window_days=args.vp_window,
        vp_min_window_days=20,
        min_horizon_observations=args.min_obs,
        diagnostic_only=args.diagnostic,
        permutation_control=True,
    )

    mode_label = "DIAGNOSTIC" if args.diagnostic else "CANONICAL"
    print(f"\n  Mode: {mode_label}")
    print(f"  VP window requested: {args.vp_window}d")
    print(f"  VP window effective: {vp_window}d")
    print(f"  Strict mode: {not args.no_strict}")
    print(f"  Min bars: {args.min_bars}")
    print(f"  Min observations per horizon: {args.min_obs}")

    print("\nComputing VP signal...")
    try:
        signal = compute_vp_signal_canonical(
            ohlcv,
            window_days=args.vp_window,
            min_bars=args.min_bars,
            diagnostic=args.diagnostic,
            vp_min_window_days=20,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    signal_bars = len(signal)
    print(f"  Signal bars produced: {signal_bars}")
    if signal_bars > 0:
        print(f"  Signal range: [{signal.min():.1f}, {signal.max():.1f}]")
        print(f"  Signal mean: {signal.mean():.1f}")
    else:
        print("  WARNING: No signal bars produced (insufficient data for VP)")

    print("\nBuilding point-in-time predictions...")
    build_result = build_predictions_from_ohlcv(
        ohlcv,
        horizons=horizons,
        signal=signal,
        ticker=args.ticker,
        min_bars=args.min_bars,
        config=config,
    )

    print(f"  Build status: {build_result.status.value}")
    print(f"  Available bars: {build_result.available_bars}")
    print(f"  Required bars: {build_result.required_bars}")
    print(f"  Reason: {build_result.reason}")
    print(f"  Diagnostic only: {build_result.diagnostic_only}")

    if build_result.status == BacktestBuildStatus.INSUFFICIENT_DATA:
        sep = "=" * 70
        print(f"\n{sep}")
        print("INSUFFICIENT DATA — no predictions generated")
        print(sep)
        print(f"Reason: {build_result.reason}")
        print("\nPer-horizon capability:")
        print(f"  {'Horizon':>8} {'Supported':>10} {'Need':>8} {'Have':>8}")
        print(f"  {'-'*45}")
        for hc in build_result.horizons:
            sup = "YES" if hc.supported else "NO"
            print(f"  {hc.horizon_days:>8} {sup:>10} {hc.required_bars:>8} "
                  f"{hc.available_bars:>8}")
        print("\nTo run with short history, use --diagnostic and --no-strict:")
        print(f"  python scripts/run_backtest.py --ticker {args.ticker} "
              f"--diagnostic --no-strict --period 1mo")
        sys.exit(0)

    print(f"  Supported horizons: "
          f"{[h.horizon_days for h in build_result.horizons if h.supported]}")
    print(f"  Total predictions: {len(build_result.predictions)}")

    result = evaluate(
        build_result,
        config=config,
        ticker=args.ticker,
        signal_description=(
            f"Volume Profile composite score ({mode_label}, via "
            "trading_mcp.analysis.volume_profile.get_profile_levels) — "
            f"rolling {vp_window}-day window, no look-ahead"
        ),
    )

    sep70 = "=" * 70
    print(f"\n{sep70}")
    print(f"Backtest Results: {args.ticker}  [{mode_label}]")
    print(f"Signal: {result.signal_description}")
    if result.diagnostic_only:
        print("** DIAGNOSTIC ONLY — NOT comparable to canonical 365d **")
    print(f"Period: {result.as_of_range[0]} -> {result.as_of_range[1]}")
    print(sep70)
    header = (
        "{:>8} {:>5} {:>18} {:>6} "
        "{:>8} {:>10} {:>9} {:>10} {:>10}"
    ).format(
        "Horizon", "Supp", "Status", "N",
        "IC Rank", "IC Pearson", "Hit Rate", "Mean Ret%", "Q5-Q1%"
    )
    print(header)
    print("-" * 85)
    for h in result.horizons:
        sup = "YES" if h.supported else "NO "
        st = h.status if h.status else ("ok" if h.supported else "insufficient_data")
        ic_r = f"{h.ic_rank:.4f}" if h.ic_rank is not None else "N/A"
        ic_p = f"{h.ic_pearson:.4f}" if h.ic_pearson is not None else "N/A"
        q5q1 = f"{h.quintile_spread:.4f}" if h.quintile_spread is not None else "N/A"
        print(
            f"{h.horizon_days:>8} {sup:>5} {st:>18} {h.n_observations:>6} "
            f"{ic_r:>8} {ic_p:>10} {h.hit_rate:>9.4f} "
            f"{h.mean_return_pct:>10.4f} {q5q1:>10}"
        )

    print("\nLimits:")
    for limit in result.limits:
        print(f"  - {limit}")

    csv_path = out_dir / f"{args.ticker}_backtest.csv"
    json_path = out_dir / f"{args.ticker}_backtest.json"

    rows = []
    for h in result.horizons:
        row = {
            "ticker": args.ticker,
            "horizon_days": h.horizon_days,
            "supported": h.supported,
            "status": h.status,
            "n_observations": h.n_observations,
            "ic_rank": h.ic_rank,
            "ic_pearson": h.ic_pearson,
            "hit_rate": h.hit_rate,
            "mean_return_pct": h.mean_return_pct,
            "quintile_spread": h.quintile_spread,
        }
        row.update({f"q_{k}": v for k, v in h.quintile_returns.items()})
        rows.append(row)
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    print(f"\nCSV written to {csv_path}")

    with json_path.open("w") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)
    print(f"JSON written to {json_path}")


if __name__ == "__main__":
    main()
