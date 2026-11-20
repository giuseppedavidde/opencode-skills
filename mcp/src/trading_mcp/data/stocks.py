"""Stock data through the centralized DataProvider.

Prices follow the provider conventions: the current price comes from the
quote layer (``None`` when it is not available, never ``0.0``), bars are
complete sessions with split-adjusted raw OHLC and a dividend-adjusted
``Adj Close``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_mcp.data.provider import InfoMeta, data_provider


def fetch_stock(ticker: str, period: str = "1y", interval: str = "1d", include_partial: bool = False) -> pd.DataFrame:
    """OHLCV history (complete sessions unless ``include_partial``); empty on failure."""
    return data_provider.get_hist(ticker, period=period, interval=interval, include_partial=include_partial)


def fetch_stock_info(ticker: str) -> dict[str, Any]:
    """Fundamental ``info`` snapshot (6 h cache); ``{}`` when unavailable."""
    return data_provider.get_info(ticker)


def compute_basic_indicators(hist: pd.DataFrame) -> dict[str, float | None]:
    """MA50, MA200, Wilder RSI14 and ATR14 on raw closes (levels match broker charts).

    Each value is ``None`` when the history is too short.
    """
    indicators: dict[str, float | None] = {"ma50": None, "ma200": None, "rsi14": None, "atr14": None}
    if hist is None or hist.empty or "Close" not in hist:
        return indicators
    close = hist["Close"].astype(float)
    if len(close) >= 15:
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        rs = up.ewm(com=13).mean() / down.ewm(com=13).mean().replace(0, float("nan"))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        value = rsi.iloc[-1]
        indicators["rsi14"] = round(float(value), 1) if pd.notna(value) else None
    if len(close) >= 50:
        indicators["ma50"] = round(float(close.rolling(50).mean().iloc[-1]), 4)
    if len(close) >= 200:
        indicators["ma200"] = round(float(close.rolling(200).mean().iloc[-1]), 4)
    if len(close) >= 15 and {"High", "Low"} <= set(hist.columns):
        prev = close.shift(1)
        true_range = pd.concat(
            [hist["High"] - hist["Low"], (hist["High"] - prev).abs(), (hist["Low"] - prev).abs()], axis=1
        ).max(axis=1)
        value = true_range.rolling(14).mean().iloc[-1]
        indicators["atr14"] = round(float(value), 4) if pd.notna(value) else None
    return indicators


def fetch_stock_full(
    ticker: str, period: str = "1y", interval: str = "1d", *, include_info: bool = True
) -> dict[str, Any]:
    """Quote, complete-session history, ``info`` and basic indicators.

    Returns a dict with ``ticker``, ``current_price`` (quote price or
    ``None``), ``quote`` (:class:`~trading_mcp.data.quotes.Quote`), ``hist``,
    ``hist_meta`` (:class:`~trading_mcp.data.provider.HistMeta`), ``info``,
    ``info_meta`` and ``indicators`` (computed on the complete bars).
    ``include_info=False`` skips the ``info`` request (``info`` is then ``{}``).
    """
    hist, hist_meta = data_provider.get_hist_with_meta(ticker, period=period, interval=interval)
    if include_info:
        info, info_meta = data_provider.get_info_with_meta(ticker)
    else:
        info, info_meta = {}, InfoMeta(symbol=ticker.upper(), warnings=["info not requested"])
    quote = data_provider.get_quote(ticker)
    return {
        "ticker": ticker,
        "current_price": quote.price,
        "quote": quote,
        "hist": hist,
        "hist_meta": hist_meta,
        "info": info,
        "info_meta": info_meta,
        "indicators": compute_basic_indicators(hist),
    }
