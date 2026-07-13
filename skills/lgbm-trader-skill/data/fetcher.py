"""OHLCV and macro data fetcher backed by yfinance.

Provides a thin caching layer on top of yfinance to avoid hitting the
network repeatedly during development. Cache is in-memory per (ticker,
start, end) key and is intentionally lightweight.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from utils.logger import get_logger

logger = get_logger(__name__)

_CACHE: Dict[str, pd.DataFrame] = {}


def fetch_ohlcv(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
    auto_adjust: bool = True,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Download OHLCV data for a single ticker.

    Parameters
    ----------
    ticker:
        Yahoo Finance ticker (e.g. ``"AAPL"`` or ``"DRAM"``).
    start, end:
        ISO date strings. If both ``None`` and ``period`` is ``None``,
        defaults to ``period="max"``.
    period:
        yfinance period string (``"1y"``, ``"max"``...). Takes precedence
        over ``start``/``end`` when provided.
    auto_adjust:
        Whether to use auto-adjusted prices.
    use_cache:
        Reuse an in-memory cached frame if available.
    """
    cache_key = f"{ticker}|{start}|{end}|{period}|{auto_adjust}"
    if use_cache and cache_key in _CACHE:
        return _CACHE[cache_key].copy()

    tk = yf.Ticker(ticker)
    hist: pd.DataFrame
    if period is not None:
        hist = tk.history(period=period, auto_adjust=auto_adjust)
    else:
        s = start if start else "2018-01-01"
        hist = tk.history(start=s, end=end, auto_adjust=auto_adjust)

    if hist is None or hist.empty:
        logger.warning("No data returned for ticker %s", ticker)
        return pd.DataFrame()

    hist = _normalize_columns(hist)
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist = hist[~hist.index.duplicated(keep="last")]
    hist = hist.sort_index()

    if use_cache:
        _CACHE[cache_key] = hist.copy()
    logger.info("Fetched %s rows for %s", len(hist), ticker)
    return hist


def fetch_ohlcv_batch(
    tickers: List[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
    delay: float = 0.1,
) -> Dict[str, pd.DataFrame]:
    """Download OHLCV for a list of tickers, returning a dict keyed by ticker."""
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = fetch_ohlcv(t, start=start, end=end, period=period)
        if not df.empty:
            out[t] = df
        time.sleep(delay)
    return out


def fetch_macro(
    macro_tickers: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Download macro indicators and return them aligned on a common index.

    Columns are renamed to readable names: ``vix``, ``dxy``, ``yield_10y``,
    ``nasdaq``, ``shy``. Missing tickers are skipped with a warning.
    """
    if macro_tickers is None:
        macro_tickers = ["^VIX", "DX-Y.NYB", "^TNX", "^IXIC", "SHY"]

    name_map = {
        "^VIX": "vix",
        "DX-Y.NYB": "dxy",
        "^TNX": "yield_10y",
        "^IXIC": "nasdaq",
        "SHY": "shy",
    }

    frames: List[pd.Series] = []
    for mt in macro_tickers:
        df = fetch_ohlcv(mt, start=start, end=end)
        if df.empty:
            continue
        col_name = name_map.get(mt, mt)
        series = df["close"].rename(col_name)
        frames.append(series)

    if not frames:
        logger.warning("No macro data fetched for %s", macro_tickers)
        return pd.DataFrame()

    macro = pd.concat(frames, axis=1)
    macro.index = pd.to_datetime(macro.index).tz_localize(None)
    macro = macro[~macro.index.duplicated(keep="last")].sort_index()
    logger.info("Macro frame built: %s", list(macro.columns))
    return macro


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Adj Open": "open",
        "Adj High": "high",
        "Adj Low": "low",
        "Adj Close": "close",
        "Adj Volume": "volume",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].copy()