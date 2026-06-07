#!/usr/bin/env python3
"""
Backtesting framework for stock-crypto-analysis scoring engine.

Simulates the 6-dimensional scoring framework over historical dates
to validate whether composite scores predict future returns.

Usage:
    python3 backtest.py --ticker AAPL --lookback 252 --step 7
    python3 backtest.py --ticker BTC --crypto --lookback 180 --step 7
    python3 backtest.py --tickers AAPL,MSFT,NVDA --lookback 126 --step 7 --min-score 70
    python3 backtest.py --universe-file data/us_tickers.csv --lookback 90 --step 14 --top 10

Key design: avoids look-ahead bias by using ONLY data available at each
simulation date. The scoring is a Python approximation of the LLM-driven
analysis, using the same dimensions and weights.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# Runtime path manipulation for schemas import
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SKILL_DIR))
sys.path.insert(0, str(_SCRIPT_DIR))

# pylint: disable=import-error,wrong-import-position
from schemas import Direction, Verdict  # noqa: E402

# Import shared weight configuration
from weights_config import get_dynamic_weights, Regime

# Import backtest utilities
from backtest_utils import (  # noqa: E402
    BacktestMetrics,
    BacktestResult,
    Benchmark,
    TradeSimulation,
    fetch_historical_data,
    load_universe_tickers,
)


# ---------------------------------------------------------------------------
# Dimensional scoring (Python approximation)
# ---------------------------------------------------------------------------


def score_wyckoff(df: pd.DataFrame, idx: int) -> float:
    """Approximate Wyckoff phase score.

    Uses: range position, HH/HL structure, MA50/MA200 cross, volume trend.
    Returns 0-100.
    """
    if idx < 50:
        return 50.0  # Not enough data

    # Slice known data up to idx
    hist = df.iloc[:idx + 1].copy()
    close = hist["Close"]
    volume = hist["Volume"]
    high = hist["High"]
    low = hist["Low"]

    score = 50.0

    # Range position: where is price in the 200-bar range?
    rng_high = high.iloc[-200:].max()
    rng_low = low.iloc[-200:].min()
    if pd.notna(rng_high) and pd.notna(rng_low) and rng_high > rng_low:
        range_pos = (close.iloc[-1] - rng_low) / (rng_high - rng_low)
        # Accumulation zone (bottom 30%) + bonus
        if range_pos < 0.30:
            score += 20
        elif range_pos < 0.40:
            score += 10
        # Distribution zone (top 30%) - penalty
        elif range_pos > 0.70:
            score -= 20

    # MA50 vs MA200 position
    if len(close) >= 200:
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        if ma50 > ma200:
            score += 15
        else:
            score -= 15

    # Price vs MA50
    if len(close) >= 50:
        ma50 = close.rolling(50).mean().iloc[-1]
        if close.iloc[-1] > ma50:
            score += 10
        else:
            score -= 10

    # Volume trend: is volume decreasing in range? (accumulation sign)
    if len(volume) >= 50:
        vol_20_recent = volume.iloc[-20:].mean()
        vol_20_prior = volume.iloc[-40:-20].mean()
        if pd.notna(vol_20_prior) and pd.notna(vol_20_recent) and vol_20_prior > 0 and vol_20_recent < vol_20_prior * 0.85:
            score += 10  # Declining volume = accumulation
        elif pd.notna(vol_20_prior) and pd.notna(vol_20_recent) and vol_20_prior > 0 and vol_20_recent > vol_20_prior * 1.15:
            score -= 10  # Rising volume in distribution

    # Spring detection (simple): break below 20-low then recover
    if idx >= 25:
        twenty_low = low.iloc[-21:-1].min()
        if low.iloc[-1] < twenty_low and close.iloc[-1] > twenty_low:
            score += 25

    return max(0.0, min(100.0, score))


def score_volume_profile(df: pd.DataFrame, idx: int) -> float:
    """Approximate Volume Profile score.

    Uses: price vs VPOC, vol ratio, profile shape approximation.
    """
    if idx < 20:
        return 50.0

    hist = df.iloc[:idx + 1].copy()
    close = hist["Close"]
    volume = hist["Volume"]

    score = 50.0

    # Approximate VPOC: highest volume price in last 90 bars or available
    window = min(90, len(hist))
    recent = hist.iloc[-window:]
    # Group by price rounded to 2 decimals to find VPOC
    price_bins = (recent["Close"] * 100).dropna().astype(int)
    vol_by_price = recent.groupby(price_bins)["Volume"].sum()
    if not vol_by_price.empty:
        vpoc_bin = vol_by_price.idxmax()
        vpoc_price = vpoc_bin / 100.0
        if close.iloc[-1] > vpoc_price:
            score += 10  # Above VPOC = bullish
        else:
            score -= 10

    # Volume ratio: today's volume vs 20d average
    vol_20_avg = volume.iloc[-21:-1].mean() if len(volume) >= 21 else volume.mean()
    today_vol = volume.iloc[-1]
    if vol_20_avg > 0:
        vol_ratio = today_vol / vol_20_avg
        if vol_ratio < 0.7:
            score -= 10  # Low volume = low conviction
        elif vol_ratio > 1.5:
            if len(close) >= 2 and close.iloc[-1] > close.iloc[-2]:
                score += 10  # High vol up = bullish
            else:
                score -= 10  # High vol down = bearish

    # Profile shape approximation: if recent range % is tight vs lookback
    recent_range = (close.iloc[-20:].max() - close.iloc[-20:].min()) / close.iloc[-1]
    full_range = (close.max() - close.min()) / close.iloc[-1]
    if full_range > 0 and recent_range / full_range < 0.3:
        score += 5  # Tight range = possible accumulation

    return max(0.0, min(100.0, score))


def score_price_action(df: pd.DataFrame, idx: int) -> float:
    """Approximate Price Action score.

    Uses: RSI(14), 25ema slope, VPA validations, rally velocity.
    """
    if idx < 25:
        return 50.0

    hist = df.iloc[:idx + 1].copy()
    close = hist["Close"]
    volume = hist["Volume"]

    score = 50.0

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(com=13, adjust=False).mean().iloc[-1]
    if avg_loss > 0:
        rs_ = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs_))
        if rsi < 30:
            score += 15  # Oversold
        elif rsi > 70:
            score -= 15  # Overbought
        elif 40 <= rsi <= 60:
            score += 5  # Healthy

    # 25ema slope
    if len(close) >= 25:
        ema25 = close.ewm(span=25, adjust=False).mean()
        slope = (ema25.iloc[-1] - ema25.iloc[-5]) / ema25.iloc[-5] if len(ema25) >= 5 else 0
        if slope > 0.01:
            score += 10
        elif slope < -0.01:
            score -= 10

    # VPA validations: last 5 daily bars
    bullish_val = 0
    bearish_val = 0
    for i in range(max(0, idx - 9), idx + 1):
        if i < 1:
            continue
        price_up = close.iloc[i] > close.iloc[i - 1]
        vol_avg = volume.iloc[max(0, i - 20):i].mean()
        vol_high = volume.iloc[i] > vol_avg * 1.1 if vol_avg > 0 else False
        if price_up and vol_high:
            bullish_val += 1
        elif not price_up and vol_high:
            bearish_val += 1
    score += (bullish_val - bearish_val) * 5

    # Rally velocity check
    if idx >= 15:
        rally_15d = (close.iloc[-1] - close.iloc[-15]) / close.iloc[-15] * 100
        if rally_15d > 20:
            score -= 20
        elif rally_15d > 30:
            score -= 35
        elif rally_15d > 50:
            score -= 50

    return max(0.0, min(100.0, score))


def score_fundamentals(info: dict) -> float:
    """Approximate Fundamentals score from yfinance info.

    Uses: P/E ratio, revenue growth, margins, D/E from info dict.
    """
    score = 50.0

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        if pe < 12:
            score += 25
        elif pe < 20:
            score += 15
        elif pe < 30:
            score += 5
        elif pe > 40:
            score -= 15

    # Revenue growth
    rev_growth = info.get("revenueGrowth", 0)
    if rev_growth and rev_growth > 0.05:
        score += 10
    elif rev_growth and rev_growth < 0:
        score -= 10

    # Debt/Equity
    de_ratio = info.get("debtToEquity")
    if de_ratio is not None:
        if de_ratio < 50.0:
            score += 10
        elif de_ratio > 150.0:
            score -= 15

    return max(0.0, min(100.0, score))


def score_competitive(info: dict) -> float:
    """Approximate Competitive Positioning score from fundamentals data.

    Uses: ROE, profit margins, market cap as proxy for moat.
    """
    score = 50.0

    roe = info.get("returnOnEquity")
    if roe is not None:
        if roe > 0.20:
            score += 20
        elif roe > 0.10:
            score += 10
        elif roe < 0:
            score -= 20

    margins = info.get("profitMargins")
    if margins is not None:
        if margins > 0.15:
            score += 15
        elif margins < 0:
            score -= 15

    # Market cap as rough moat proxy
    mcap = info.get("marketCap", 0)
    if mcap > 100e9:
        score += 10  # Large cap = more moat potential
    elif mcap < 1e9:
        score -= 10

    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------


def compute_composite(ticker: str, df: pd.DataFrame, idx: int,
                      info: dict, is_crypto: bool = False,
                      regime: Regime = Regime.UNKNOWN) -> dict:
    """Compute composite score for a single backtest date."""
    weights = get_dynamic_weights(regime, is_crypto)

    wyckoff = score_wyckoff(df, idx)
    volprof = score_volume_profile(df, idx)
    pa = score_price_action(df, idx)
    fundamentals = score_fundamentals(info) if not is_crypto else 50.0
    competitive = score_competitive(info) if not is_crypto else 50.0
    crypto_layer = 50.0 if is_crypto else 0.0  # Placeholder

    # Sentiment: placeholder 50 (no historical sentiment data available)
    sentiment = 50.0

    composite = (
        wyckoff * weights["wyckoff"]
        + volprof * weights["volume_profile"]
        + pa * weights["price_action"]
        + sentiment * weights["sentiment"]
        + fundamentals * weights.get("fundamentals", 0)
        + competitive * weights.get("competitive", 0)
        + crypto_layer * weights.get("crypto_layer", 0)
    )

    # Map to verdict
    direction = Direction.LONG if composite >= 50 else Direction.NEUTRAL
    if composite >= 70:
        verdict = Verdict.LONG_TERM
    elif composite >= 50:
        verdict = Verdict.SHORT_TERM_BULL
    elif composite >= 30:
        verdict = Verdict.SHORT_TERM_NEUTRAL
    else:
        verdict = Verdict.AVOID

    return {
        "composite_score": round(composite, 1),
        "verdict": verdict.value,
        "direction": direction.value,
        "dimensions": {
            "wyckoff": round(wyckoff, 1),
            "volume_profile": round(volprof, 1),
            "price_action": round(pa, 1),
            "sentiment": round(sentiment, 1),
            "fundamentals": round(fundamentals, 1),
            "competitive": round(competitive, 1),
        },
    }


def simulate_trade(
    df: pd.DataFrame,
    entry_idx: int,
    direction: str,
    horizon_days: int,
) -> Optional[TradeSimulation]:
    """Simulate holding a position for horizon_days from entry_idx."""
    if entry_idx >= len(df) - 1:
        return None

    exit_idx = min(entry_idx + horizon_days, len(df) - 1)
    if exit_idx <= entry_idx:
        return None

    entry_price = float(df["Close"].iloc[entry_idx + 1])  # Enter next day
    exit_price = float(df["Close"].iloc[exit_idx])

    if direction == "Short":
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100
    else:
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100

    return TradeSimulation(
        entry_date=df.index[entry_idx + 1].isoformat(),
        exit_date=df.index[exit_idx].isoformat(),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        pnl_pct=round(pnl_pct, 2),
        holding_days=exit_idx - entry_idx,
        is_win=pnl_pct > 0,
    )


def backtest_ticker(
    ticker: str,
    df: pd.DataFrame,
    info: dict,
    start_idx: int,
    step: int,
    horizon_days: int,
    min_score: float,
    is_crypto: bool = False,
) -> BacktestResult:
    """Run backtest on a single ticker."""
    results = BacktestResult(ticker=ticker, scores=[], trades=[])

    for idx in range(start_idx, len(df) - horizon_days, step):
        score = compute_composite(ticker, df, idx, info, is_crypto)

        # Record all scores for calibration
        results.scores.append({
            "date": df.index[idx].isoformat(),
            "score": score["composite_score"],
        })

        # Only trade if above min_score threshold
        if score["composite_score"] < min_score:
            continue

        trade = simulate_trade(df, idx, score["direction"], horizon_days)
        if trade:
            trade.score = score["composite_score"]
            trade.verdict = score["verdict"]
            results.trades.append(trade)

    # Compute metrics
    if results.trades:
        pnls = [t.pnl_pct for t in results.trades]
        wins = [p for p in pnls if p > 0]
        results.metrics = BacktestMetrics(
            total_trades=len(results.trades),
            win_count=len(wins),
            loss_count=len(pnls) - len(wins),
            hit_rate=round(len(wins) / len(pnls) * 100, 1),
            avg_pnl=round(sum(pnls) / len(pnls), 2),
            best_pnl=round(max(pnls), 2),
            worst_pnl=round(min(pnls), 2),
        )

    return results


def run_backtest(
    tickers: list[str],
    lookback_days: int = 252,
    step_days: int = 7,
    horizon_days: int = 30,
    min_score: float = 50.0,
    is_crypto: bool = False,
    verbose: bool = True,
) -> list[BacktestResult]:
    """Run backtest on a list of tickers."""
    all_results = []

    for ticker in tickers:
        if verbose:
            print(f"  {ticker}...", end=" ")

        try:
            df, info = fetch_historical_data(ticker, lookback_days, is_crypto)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if verbose:
                print(f"SKIP (data error: {exc})")
            continue

        if df.empty or len(df) < 60:
            if verbose:
                print("SKIP (not enough data)")
            continue

        # Start backtest after first 60 bars (need warmup)
        start_idx = min(60, len(df) // 4)

        result = backtest_ticker(
            ticker, df, info,
            start_idx=start_idx,
            step=step_days,
            horizon_days=horizon_days,
            min_score=min_score,
            is_crypto=is_crypto,
        )

        if verbose:
            trades_count = result.metrics.total_trades if result.metrics else 0
            hit_rate = result.metrics.hit_rate if result.metrics else 0
            print(f"{trades_count} trades, hit rate {hit_rate:.0f}%")

        all_results.append(result)

    return all_results


def compare_to_benchmark(
    results: list[BacktestResult],
    tickers: list[str],
    lookback_days: int,
    horizon_days: int = 30,
) -> dict:
    """Compare strategy returns against rolling buy & hold benchmark.

    Uses rolling horizon-day windows for an apples-to-apples comparison
    instead of comparing short-term trades against a full-period buy & hold.
    """
    bnh_returns = []
    for ticker in tickers:
        try:
            df, _ = fetch_historical_data(ticker, lookback_days)
            if df.empty or len(df) < horizon_days + 5:
                bnh_returns.append(Benchmark.ZERO)
                continue
            closes = df["Close"].values
            rolling_returns = []
            for i in range(0, len(closes) - horizon_days, 7):  # step = 7 like backtest
                entry_p = float(closes[i])
                exit_p = float(closes[i + horizon_days])
                if entry_p > 0:
                    rolling_returns.append((exit_p / entry_p - 1) * 100)
            if rolling_returns:
                avg_bnh = sum(rolling_returns) / len(rolling_returns)
                bnh_returns.append(Benchmark(round(avg_bnh, 2)))
            else:
                bnh_returns.append(Benchmark.ZERO)
        except Exception:  # pylint: disable=broad-exception-caught
            bnh_returns.append(Benchmark.ZERO)
            continue

    # Aggregate all strategy trades
    all_pnls = []
    for r in results:
        if r.metrics:
            for t in r.trades:
                all_pnls.append(t.pnl_pct)

    strat_avg = sum(all_pnls) / len(all_pnls) if all_pnls else 0
    bnh_avg = sum(bnh_returns) / len(bnh_returns) if bnh_returns else 0

    return {
        "strategy_trades": len(all_pnls),
        "strategy_avg_pnl": round(strat_avg, 2),
        "benchmark_avg_return": round(bnh_avg, 2),
        "alpha": round(strat_avg - bnh_avg, 2),
        "benchmark_samples": len(bnh_returns),
        "benchmark_method": f"rolling {horizon_days}-day windows (step=7)",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def print_report(results: list[BacktestResult],
                 benchmark: dict, args: argparse.Namespace) -> None:
    """Print formatted backtest report."""
    print("\n" + "=" * 60)
    print("BACKTEST REPORT")
    print("=" * 60)
    print(f"Tickers: {', '.join(r.ticker for r in results)}")
    print(f"Lookback: {args.lookback}d | Step: {args.step}d | "
          f"Horizon: {args.horizon}d | Min score: {args.min_score}")
    print()

    all_trades = []
    for r in results:
        all_trades.extend(r.trades)

    if not all_trades:
        print("No trades generated. Try lowering --min-score or increasing --lookback.")
        return

    pnls = [t.pnl_pct for t in all_trades]
    wins = [p for p in pnls if p > 0]

    print(f"Total trades: {len(all_trades)}")
    print(f"Hit rate: {len(wins)/len(pnls)*100:.1f}% ({len(wins)}W / {len(pnls)-len(wins)}L)")
    print(f"Avg PnL: {sum(pnls)/len(pnls):+.2f}%")
    print(f"Best: {max(pnls):+.2f}% | Worst: {min(pnls):+.2f}%")

    if benchmark["benchmark_samples"] > 0:
        print(f"\nBenchmark (buy & hold): {benchmark['benchmark_avg_return']:+.2f}%")
        print(f"Alpha: {benchmark['alpha']:+.2f}%")

    # By verdict
    print("\n--- By Verdict ---")
    by_verdict: dict[str, list[float]] = {}
    for t in all_trades:
        by_verdict.setdefault(t.verdict, []).append(t.pnl_pct)
    for verdict, v_pnls in sorted(by_verdict.items()):
        avg = sum(v_pnls) / len(v_pnls)
        hr = len([p for p in v_pnls if p > 0]) / len(v_pnls) * 100
        print(f"  {verdict}: {len(v_pnls)} trades, {hr:.0f}% HR, avg {avg:+.2f}%")

    # Per ticker
    print("\n--- Per Ticker ---")
    for r in results:
        if r.metrics:
            m = r.metrics
            print(f"  {r.ticker}: {m.total_trades} trades, "
                  f"{m.hit_rate:.0f}% HR, avg {m.avg_pnl:+.2f}%")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Backtest the scoring engine")
    parser.add_argument("--ticker", type=str, help="Single ticker")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers")
    parser.add_argument("--crypto", action="store_true", help="Treat as crypto")
    parser.add_argument("--universe-file", type=str, help="CSV file with tickers")
    parser.add_argument("--lookback", type=int, default=252, help="Lookback days (min 20)")
    parser.add_argument("--step", type=int, default=7, help="Trading step days")
    parser.add_argument("--horizon", type=int, default=30, help="Holding period days")
    parser.add_argument("--min-score", type=int, default=60, help="Minimum score to trade")
    parser.add_argument("--top", type=int, default=0, help="Only top N tickers")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--crypto", action="store_true", help="Crypto mode")
    args = parser.parse_args()

    if args.lookback < 20:
        print("Error: --lookback must be at least 20", file=sys.stderr)
        sys.exit(1)

    # Resolve tickers
    tickers: list[str] = []
    if args.ticker:
        tickers = [args.ticker]
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    elif args.universe_file:
        tickers = load_universe_tickers(args.universe_file)[:20]  # Cap for speed

    if not tickers:
        parser.error("Specify --ticker, --tickers, or --universe-file")

    print(f"Backtesting {len(tickers)} ticker(s)...")
    results = run_backtest(
        tickers, args.lookback, args.step, args.horizon,
        args.min_score, args.crypto,
    )

    benchmark = compare_to_benchmark(results, tickers, args.lookback, args.horizon)

    if args.json:
        output = {
            "results": [
                {
                    "ticker": r.ticker,
                    "metrics": r.metrics.model_dump() if r.metrics else None,
                    "trades": [t.model_dump() for t in r.trades],
                }
                for r in results
            ],
            "benchmark": benchmark,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(results, benchmark, args)


if __name__ == "__main__":
    main()
