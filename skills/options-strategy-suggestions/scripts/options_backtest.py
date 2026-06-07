#!/usr/bin/env python3
"""
Options Strategy Backtester

Backtests covered call and synthetic long 2:1 strategies on historical data.

Usage:
    python3 options_backtest.py --ticker AAPL --strategy covered_call --dte 30 --lookback 365
    python3 options_backtest.py --ticker AAPL --strategy synthetic_long --ratio 2:1 --lookback 180
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime
from typing import Optional

# pylint: disable=import-error
# yfinance and pydantic are imported lazily below
# pylint: enable=import-error

from pydantic import BaseModel, Field

RISK_FREE_RATE = 0.05
DEFAULT_SIGMA_WINDOW = 20
TRADING_DAYS = 252
MULTIPLIER = 100


# ---- Pydantic Models ----


class BacktestTrade(BaseModel):
    """A single simulated trade."""

    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    strike: float
    premium: float
    cost: float
    exit_value: float
    pnl: float
    pnl_pct: float


class BacktestResult(BaseModel):
    """Full backtest result."""

    ticker: str
    strategy: str
    dte: int
    lookback_days: int
    total_trades: int
    win_rate: float
    avg_pnl_pct: float
    best_pnl_pct: float
    worst_pnl_pct: float
    total_pnl_pct: float
    buy_hold_pnl_pct: float
    outperformed: bool
    avg_premium: float
    trades: list[BacktestTrade] = Field(default_factory=list)
    error: Optional[str] = None


# ---- Lazy Imports ----


def _get_yfinance():
    """Lazy import yfinance to avoid import errors when not available."""
    # pylint: disable=import-outside-toplevel
    import yfinance as yf
    return yf


# ---- Black-Scholes Helpers ----


def _bs_call_price(spot: float, strike: float, time_to_expiry: float,
                   rate: float, sigma: float) -> float:
    """Black-Scholes call price."""
    if time_to_expiry <= 0 or sigma <= 0:
        return max(0.0, spot - strike)
    from scipy.stats import norm
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma ** 2) * time_to_expiry) / \
         (sigma * math.sqrt(time_to_expiry))
    d2 = d1 - sigma * math.sqrt(time_to_expiry)
    return spot * norm.cdf(d1) - strike * math.exp(-rate * time_to_expiry) * norm.cdf(d2)


def _bs_put_price(spot: float, strike: float, time_to_expiry: float,
                  rate: float, sigma: float) -> float:
    """Black-Scholes put price."""
    if time_to_expiry <= 0 or sigma <= 0:
        return max(0.0, strike - spot)
    from scipy.stats import norm
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma ** 2) * time_to_expiry) / \
         (sigma * math.sqrt(time_to_expiry))
    d2 = d1 - sigma * math.sqrt(time_to_expiry)
    return strike * math.exp(-rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def _estimate_historical_sigma(prices, window: int = DEFAULT_SIGMA_WINDOW) -> float:
    """Estimate annualized historical volatility from price series."""
    if len(prices) < max(window, 10):
        return 0.3
    recent = prices[-window:]
    returns = [math.log(recent[i] / recent[i - 1]) for i in range(1, len(recent))]
    if not returns:
        return 0.3
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    daily_std = math.sqrt(max(variance, 1e-9))
    annual_vol = daily_std * math.sqrt(TRADING_DAYS)
    return min(max(annual_vol, 0.05), 1.5)


# ---- Strategy: Covered Call ----


def backtest_covered_call(hist, dte: int, lookback_days: int) -> BacktestResult:
    """
    Backtest covered call strategy.

    Every dte days, buy 100 shares and sell 1 ATM call.
    Hold to expiration and compute PnL.
    """
    trades = []
    if hist.empty or len(hist) < dte + 20:
        return BacktestResult(
            ticker="",
            strategy="covered_call",
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=0.0,
            outperformed=False,
            avg_premium=0.0,
            error="Insufficient data",
        )

    closes = hist["Close"].tolist()
    dates_list = hist.index.tolist()

    total_returns = []
    premiums = []

    step = dte
    for entry_idx in range(0, len(closes) - dte, step):
        exit_idx = entry_idx + dte
        if exit_idx >= len(closes):
            break

        entry_price = closes[entry_idx]
        exit_price = closes[exit_idx]
        entry_date = dates_list[entry_idx]
        exit_date = dates_list[exit_idx]

        if isinstance(entry_date, (datetime, date)):
            entry_date_str = entry_date.strftime("%Y-%m-%d")
        else:
            entry_date_str = str(entry_date)[:10]

        if isinstance(exit_date, (datetime, date)):
            exit_date_str = exit_date.strftime("%Y-%m-%d")
        else:
            exit_date_str = str(exit_date)[:10]

        strike = round(entry_price)
        if strike <= 0:
            strike = entry_price

        # Estimate sigma
        lookback_prices = closes[max(0, entry_idx - DEFAULT_SIGMA_WINDOW):entry_idx]
        sigma = _estimate_historical_sigma(lookback_prices, DEFAULT_SIGMA_WINDOW)
        tte = dte / 365.0

        premium = _bs_call_price(entry_price, strike, tte, RISK_FREE_RATE, sigma)

        entry_cost = entry_price * MULTIPLIER
        premium_received = premium * MULTIPLIER

        # At expiration
        if exit_price > strike:
            exit_value = strike * MULTIPLIER  # Shares called away at strike
        else:
            exit_value = exit_price * MULTIPLIER  # Keep shares

        total_exit_value = exit_value + premium_received
        pnl = total_exit_value - entry_cost
        pnl_pct = (pnl / entry_cost) * 100

        trade = BacktestTrade(
            entry_date=entry_date_str,
            entry_price=round(entry_price, 2),
            exit_date=exit_date_str,
            exit_price=round(exit_price, 2),
            strike=float(strike),
            premium=round(premium, 3),
            cost=round(entry_cost, 2),
            exit_value=round(exit_value, 2),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
        )
        trades.append(trade)
        total_returns.append(pnl_pct)
        premiums.append(premium)

    # Buy & hold comparison
    if closes:
        buy_hold_pnl = (closes[-1] - closes[0]) / closes[0] * 100
    else:
        buy_hold_pnl = 0.0

    return _build_result(
        trades=trades,
        total_returns=total_returns,
        premiums=premiums,
        buy_hold_pnl=buy_hold_pnl,
        strategy="covered_call",
        dte=dte,
        lookback_days=lookback_days,
    )


# ---- Strategy: Synthetic Long 2:1 ----


def backtest_synthetic_long(hist, dte: int, lookback_days: int) -> BacktestResult:
    """
    Backtest synthetic long 2:1 strategy.

    Every dte days: buy 2 slightly ITM calls, sell 1 ATM call.
    Hold to expiration and compute PnL.
    """
    trades = []
    if hist.empty or len(hist) < dte + 20:
        return BacktestResult(
            ticker="",
            strategy="synthetic_long",
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=0.0,
            outperformed=False,
            avg_premium=0.0,
            error="Insufficient data",
        )

    closes = hist["Close"].tolist()
    dates_list = hist.index.tolist()

    total_returns = []
    premiums = []

    step = dte
    for entry_idx in range(0, len(closes) - dte, step):
        exit_idx = entry_idx + dte
        if exit_idx >= len(closes):
            break

        entry_price = closes[entry_idx]
        exit_price = closes[exit_idx]
        entry_date = dates_list[entry_idx]
        exit_date = dates_list[exit_idx]

        if isinstance(entry_date, (datetime, date)):
            entry_date_str = entry_date.strftime("%Y-%m-%d")
        else:
            entry_date_str = str(entry_date)[:10]

        if isinstance(exit_date, (datetime, date)):
            exit_date_str = exit_date.strftime("%Y-%m-%d")
        else:
            exit_date_str = str(exit_date)[:10]

        itm_strike = round(entry_price * 0.95, 2)
        atm_strike = round(entry_price)

        lookback_prices = closes[max(0, entry_idx - DEFAULT_SIGMA_WINDOW):entry_idx]
        sigma = _estimate_historical_sigma(lookback_prices, DEFAULT_SIGMA_WINDOW)
        tte = dte / 365.0

        premium_itm = _bs_call_price(entry_price, itm_strike, tte, RISK_FREE_RATE, sigma)
        premium_atm = _bs_call_price(entry_price, atm_strike, tte, RISK_FREE_RATE, sigma)

        # Buy 2 ITM calls, sell 1 ATM call
        initial_cost = (2 * premium_itm - premium_atm) * MULTIPLIER

        # At expiration value
        itm_value = max(0.0, exit_price - itm_strike) * 2 * MULTIPLIER
        atm_value = -max(0.0, exit_price - atm_strike) * MULTIPLIER
        final_value = itm_value + atm_value

        pnl = final_value - initial_cost
        pnl_pct = (pnl / abs(initial_cost)) * 100 if initial_cost != 0 else 0.0

        entry_cost = abs(initial_cost)
        avg_premium = (2 * premium_itm + -premium_atm) / 3

        trade = BacktestTrade(
            entry_date=entry_date_str,
            entry_price=round(entry_price, 2),
            exit_date=exit_date_str,
            exit_price=round(exit_price, 2),
            strike=atm_strike,
            premium=round(avg_premium, 3),
            cost=round(entry_cost, 2),
            exit_value=round(final_value, 2),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
        )
        trades.append(trade)
        total_returns.append(pnl_pct)
        premiums.append(abs(avg_premium))

    # Buy & hold comparison
    if closes:
        buy_hold_pnl = (closes[-1] - closes[0]) / closes[0] * 100
    else:
        buy_hold_pnl = 0.0

    return _build_result(
        trades=trades,
        total_returns=total_returns,
        premiums=premiums,
        buy_hold_pnl=buy_hold_pnl,
        strategy="synthetic_long",
        dte=dte,
        lookback_days=lookback_days,
    )


# ---- Common Result Builder ----


def _build_result(
    trades: list[BacktestTrade],
    total_returns: list[float],
    premiums: list[float],
    buy_hold_pnl: float,
    strategy: str,
    dte: int,
    lookback_days: int,
) -> BacktestResult:
    """Build BacktestResult from trade data."""
    n_trades = len(trades)
    if n_trades == 0 or not total_returns:
        return BacktestResult(
            ticker="",
            strategy=strategy,
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=round(buy_hold_pnl, 2),
            outperformed=False,
            avg_premium=0.0,
            trades=trades,
        )

    wins = sum(1 for r in total_returns if r > 0)
    win_rate = (wins / n_trades) * 100
    avg_pnl = sum(total_returns) / n_trades
    best_pnl = max(total_returns)
    worst_pnl = min(total_returns)
    total_pnl_pct = sum(total_returns)
    avg_prem = sum(premiums) / n_trades if premiums else 0.0

    return BacktestResult(
        ticker="",
        strategy=strategy,
        dte=dte,
        lookback_days=lookback_days,
        total_trades=n_trades,
        win_rate=round(win_rate, 1),
        avg_pnl_pct=round(avg_pnl, 2),
        best_pnl_pct=round(best_pnl, 2),
        worst_pnl_pct=round(worst_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        buy_hold_pnl_pct=round(buy_hold_pnl, 2),
        outperformed=total_pnl_pct > buy_hold_pnl,
        avg_premium=round(avg_prem, 3),
        trades=trades,
    )


# ---- Output Formatting ----

def format_output_text(result: BacktestResult) -> str:
    """Format BacktestResult as readable text output."""
    lines = []

    header = (
        f"  {result.ticker}  |  {result.strategy.upper()}  |  "
        f"DTE={result.dte}  |  Lookback={result.lookback_days}d"
    )
    lines.append("")
    lines.append("=" * 80)
    lines.append(header)
    lines.append("=" * 80)
    lines.append("")

    if result.error:
        lines.append(f"  ERROR: {result.error}")
        lines.append("")
        return "\n".join(lines)

    # ---- Summary Metrics ----
    lines.append(f"  Total Trades:    {result.total_trades}")
    lines.append(f"  Win Rate:        {result.win_rate:.1f}%")
    lines.append(f"  Avg PnL / Trade: {result.avg_pnl_pct:+.2f}%")
    lines.append(f"  Best Trade:      {result.best_pnl_pct:+.2f}%")
    lines.append(f"  Worst Trade:     {result.worst_pnl_pct:+.2f}%")
    lines.append(f"  Total PnL:       {result.total_pnl_pct:+.2f}%")
    lines.append(f"  Avg Premium:     ${result.avg_premium:.2f}")
    lines.append("")
    lines.append(f"  Buy & Hold PnL:  {result.buy_hold_pnl_pct:+.2f}%")
    if result.outperformed:
        lines.append(
            f"  → Strategy OUTPERFORMED buy & hold by "
            f"{result.total_pnl_pct - result.buy_hold_pnl_pct:+.2f}%"
        )
    else:
        lines.append(
            f"  → Strategy UNDERPERFORMED buy & hold by "
            f"{result.buy_hold_pnl_pct - result.total_pnl_pct:+.2f}%"
        )
    lines.append("")

    # ---- Trades Table ----
    lines.append(f"  {'── Trade Log ──':^70s}")
    header_row = (
        f"  {'Entry':>10s}  {'Entry$':>9s}  "
        f"{'Exit':>10s}  {'Exit$':>9s}  "
        f"{'Strike':>8s}  {'Prem':>7s}  "
        f"{'Cost':>9s}  {'ExitVal':>9s}  "
        f"{'PnL$':>8s}  {'PnL%':>7s}"
    )
    lines.append(header_row)
    lines.append("  " + "-" * 96)

    for trade in result.trades:
        lines.append(
            f"  {trade.entry_date:>10s}  {trade.entry_price:>9.2f}  "
            f"{trade.exit_date:>10s}  {trade.exit_price:>9.2f}  "
            f"${trade.strike:>7.0f}  {trade.premium:>7.2f}  "
            f"${trade.cost:>8.2f}  ${trade.exit_value:>8.2f}  "
            f"${trade.pnl:>7.2f}  {trade.pnl_pct:>+6.2f}%"
        )

    lines.append("")
    lines.append("  " + "─" * 60)
    lines.append("  Model: Black-Scholes with r=5%")
    lines.append("  Sigma: 20-day rolling historical volatility")
    lines.append("  Engine: Python (yfinance + scipy)")
    lines.append("")

    return "\n".join(lines)


def format_output_json(result: BacktestResult) -> str:
    """Format BacktestResult as JSON string."""
    import json

    return json.dumps(
        result.model_dump(),
        indent=2,
        default=str,
    )


# ---- Main ----


def run_backtest(
    ticker_symbol: str,
    strategy: str,
    dte: int,
    lookback_days: int,
) -> BacktestResult:
    """
    Run backtest for a given ticker and strategy.

    Args:
        ticker_symbol: Stock ticker symbol.
        strategy: 'covered_call' or 'synthetic_long'.
        dte: Days to expiration for each trade.
        lookback_days: Number of days of historical data.

    Returns:
        BacktestResult.
    """
    yf = _get_yfinance()
    yf_ticker = yf.Ticker(ticker_symbol)

    try:
        period_days = max(lookback_days, dte + 60)
        if period_days <= 365:
            period_str = "1y"
        elif period_days <= 730:
            period_str = "2y"
        elif period_days <= 1825:
            period_str = "5y"
        else:
            period_str = "max"

        hist = yf_ticker.history(period=period_str)
    except Exception as exc:
        return BacktestResult(
            ticker=ticker_symbol,
            strategy=strategy,
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=0.0,
            outperformed=False,
            avg_premium=0.0,
            error=f"Failed to fetch historical data: {exc}",
        )

    if hist.empty or len(hist) < max(dte, 20):
        return BacktestResult(
            ticker=ticker_symbol,
            strategy=strategy,
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=0.0,
            outperformed=False,
            avg_premium=0.0,
            error="Insufficient historical data",
        )

    if strategy == "covered_call":
        result = backtest_covered_call(hist, dte, lookback_days)
    elif strategy == "synthetic_long":
        result = backtest_synthetic_long(hist, dte, lookback_days)
    else:
        return BacktestResult(
            ticker=ticker_symbol,
            strategy=strategy,
            dte=dte,
            lookback_days=lookback_days,
            total_trades=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            best_pnl_pct=0.0,
            worst_pnl_pct=0.0,
            total_pnl_pct=0.0,
            buy_hold_pnl_pct=0.0,
            outperformed=False,
            avg_premium=0.0,
            error=f"Unknown strategy: {strategy}",
        )

    result.ticker = ticker_symbol
    return result


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backtest option strategies on historical data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 options_backtest.py --ticker AAPL --strategy covered_call --dte 30 --lookback 365
  python3 options_backtest.py --ticker AAPL --strategy synthetic_long --dte 45 --lookback 365
  python3 options_backtest.py --ticker MSFT --strategy covered_call --lookback 180 --json
        """,
    )
    parser.add_argument(
        "--ticker", type=str, required=True, help="Stock ticker symbol (e.g. AAPL)"
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=["covered_call", "synthetic_long"],
        help="Strategy to backtest",
    )
    parser.add_argument(
        "--dte",
        type=int,
        default=30,
        help="Days to expiration for each trade window (default: 30)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=365,
        help="Number of days of historical data (default: 365)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results in JSON format",
    )
    args = parser.parse_args()

    ticker_symbol = args.ticker.strip().upper()
    if not ticker_symbol:
        print("Error: ticker must not be empty", file=sys.stderr)
        sys.exit(1)

    if args.dte < 5:
        print("Error: --dte must be >= 5", file=sys.stderr)
        sys.exit(1)

    if args.lookback < args.dte + 20:
        print(
            f"Error: --lookback ({args.lookback}) must be >= --dte ({args.dte}) + 20",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Backtesting {args.strategy} on {ticker_symbol} "
        f"(DTE={args.dte}, lookback={args.lookback}d)...",
        file=sys.stderr,
    )

    result = run_backtest(
        ticker_symbol=ticker_symbol,
        strategy=args.strategy,
        dte=args.dte,
        lookback_days=args.lookback,
    )

    if result.error:
        print(f"\nError: {result.error}", file=sys.stderr)

    if args.json:
        print(format_output_json(result))
    else:
        print(format_output_text(result))

    if result.error:
        sys.exit(1)


if __name__ == "__main__":
    main()
