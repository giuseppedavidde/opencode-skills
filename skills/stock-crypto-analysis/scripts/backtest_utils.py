"""
Backtest utilities: data fetching, types, and helpers.

Used by backtest.py to fetch historical data and manage simulation state
without look-ahead bias.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class Benchmark(float):
    """Benchmark return percentage."""

    ZERO = 0.0


class TradeSimulation(BaseModel):
    """A single simulated trade in backtesting."""

    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    holding_days: int
    is_win: bool
    score: float = 0.0
    verdict: str = ""


class BacktestMetrics(BaseModel):
    """Aggregate backtest metrics."""

    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    hit_rate: float = 0.0
    avg_pnl: float = 0.0
    best_pnl: float = 0.0
    worst_pnl: float = 0.0


class BacktestResult(BaseModel):
    """Complete backtest result for one ticker."""

    ticker: str
    scores: list[dict] = Field(default_factory=list)
    trades: list[TradeSimulation] = Field(default_factory=list)
    metrics: BacktestMetrics | None = None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_historical_data(ticker: str, lookback_days: int,
                          is_crypto: bool = False) -> tuple[pd.DataFrame, dict]:
    """Fetch historical OHLCV data and fundamentals for a ticker.

    Returns (DataFrame, info_dict). info_dict may be empty if unavailable.
    Avoids look-ahead by returning all data; the backtest engine slices by index.
    """
    info: dict = {}

    try:
        import yfinance as yf  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        symbol = ticker
        if is_crypto and "-" not in ticker:
            symbol = f"{ticker}-EUR"

        ticker_obj = yf.Ticker(symbol)
        period_map = {30: "1mo", 90: "3mo", 180: "6mo", 252: "1y", 500: "2y", 1000: "5y"}
        period = period_map.get(lookback_days, "1y")

        df = ticker_obj.history(period=period, interval="1d")
        if df.empty:
            raise ValueError("No data returned from yfinance")

        # Get fundamentals
        try:
            info = ticker_obj.info or {}
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return df, info

    except ImportError:
        print("Error: yfinance not installed. Install with: pip install yfinance",
              file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise RuntimeError(f"Failed to fetch data for {ticker}: {exc}") from exc


def fetch_benchmark_data(ticker: str, lookback_days: int) -> Benchmark:
    """Fetch buy & hold return over the lookback period."""
    try:
        import yfinance as yf  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel
        tk = yf.Ticker(ticker)
        df = tk.history(period=f"{lookback_days}d", interval="1d")
        if df.empty or len(df) < 2:
            return Benchmark.ZERO
        pct = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1) * 100
        return Benchmark(round(pct, 2))
    except Exception:  # pylint: disable=broad-exception-caught
        return Benchmark.ZERO


def load_universe_tickers(filepath: str) -> list[str]:
    """Load ticker symbols from a CSV file.

    Expects first column to be the ticker symbol, or a column named 'ticker'/'Symbol'.
    """
    tickers = []
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return tickers

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try common column names
            ticker = row.get("ticker") or row.get("Symbol") or row.get("symbol") or ""
            if not ticker:
                # Use first column
                ticker = list(row.values())[0] if row.values() else ""
            ticker = ticker.strip()
            if ticker and not ticker.startswith("#"):
                tickers.append(ticker)

    return tickers
