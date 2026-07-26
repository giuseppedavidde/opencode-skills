"""Stock data fetching via yfinance — backed by centralized DataProvider."""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_mcp.data.provider import data_provider


def fetch_stock(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV history for a stock ticker.

    Uses the centralized DataProvider with 1-hour TTL cache.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'ENI.MI').
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max).
        interval: Bar interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo).

    Returns:
        DataFrame with OHLCV data, empty if no data.
    """
    return data_provider.get_hist(ticker, period=period, interval=interval)


def fetch_stock_info(ticker: str) -> dict[str, Any]:
    """Fetch fundamental info for a stock ticker.

    Uses the centralized DataProvider with 6-hour TTL cache.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dictionary of info fields, empty dict if unavailable.
    """
    return data_provider.get_info(ticker)


def fetch_stock_full(
    ticker: str, period: str = "1y", interval: str = "1d"
) -> dict[str, Any]:
    """Fetch complete stock data: OHLCV history + fundamentals.

    Uses the centralized DataProvider cache.

    Args:
        ticker: Stock ticker symbol.
        period: Data period.
        interval: Bar interval.

    Returns:
        Dictionary with 'ticker', 'current_price', 'hist' (DataFrame),
        'info' (dict), and computed 'indicators'.
    """
    _, info, hist = data_provider.get_ticker(ticker, period=period, interval=interval)

    price = info.get("currentPrice")
    if price is None and not hist.empty:
        price = float(hist["Close"].iloc[-1])
    price = price or 0.0

    indicators: dict[str, float | None] = {
        "ma50": None,
        "ma200": None,
        "rsi14": None,
        "atr14": None,
    }

    if not hist.empty and len(hist) >= 15:
        close = hist["Close"]
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rs_series = ma_up / ma_down.replace(0, float("nan"))
        rsi = 100.0 - (100.0 / (1.0 + rs_series))
        indicators["rsi14"] = round(float(rsi.iloc[-1]), 1)

    if not hist.empty and len(hist) >= 50:
        indicators["ma50"] = round(float(hist["Close"].rolling(50).mean().iloc[-1]), 2)

    if not hist.empty and len(hist) >= 200:
        indicators["ma200"] = round(float(hist["Close"].rolling(200).mean().iloc[-1]), 2)

    if not hist.empty and len(hist) >= 14:
        high = hist["High"]
        low = hist["Low"]
        close_prev = hist["Close"].shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - close_prev).abs(),
                (low - close_prev).abs(),
            ],
            axis=1,
        ).max(axis=1)
        indicators["atr14"] = round(float(tr.rolling(14).mean().iloc[-1]), 2)

    return {
        "ticker": ticker,
        "current_price": round(price, 2),
        "hist": hist,
        "info": info,
        "indicators": indicators,
    }
