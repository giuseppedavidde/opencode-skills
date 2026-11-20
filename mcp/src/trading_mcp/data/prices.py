"""Price-series conventions shared by every caller of the DataProvider.

The provider downloads history with ``auto_adjust=False``:

- ``Open``/``High``/``Low``/``Close`` are split-adjusted raw prices. They
  match broker charts, so levels (support, resistance, POC, stops, entries)
  must use them.
- ``Adj Close`` also carries the dividend adjustment. Returns, realized
  volatility and momentum must use it, otherwise every ex-dividend date
  shows a false loss.

Frames without ``Adj Close`` (synthetic test data, some vendors) fall back to
``Close``; :func:`has_adjusted_close` tells the caller which one was used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ADJ_CLOSE = "Adj Close"
CLOSE = "Close"
PRICE_ADJUSTMENT = "split_adjusted_ohlc+dividend_adjusted_adj_close"


def has_adjusted_close(hist: pd.DataFrame | None) -> bool:
    """True when ``hist`` carries a usable ``Adj Close`` column."""
    return (
        hist is not None
        and not hist.empty
        and ADJ_CLOSE in hist.columns
        and bool(hist[ADJ_CLOSE].notna().any())
    )


def adjusted_close(hist: pd.DataFrame) -> pd.Series:
    """Total-return price series: ``Adj Close``, or ``Close`` when it is absent."""
    if hist is None or hist.empty:
        return pd.Series(dtype=float)
    column = ADJ_CLOSE if has_adjusted_close(hist) else CLOSE
    series = pd.to_numeric(hist[column], errors="coerce").astype(float)
    return series.replace([np.inf, -np.inf], np.nan)


def returns(hist: pd.DataFrame, *, log: bool = False) -> pd.Series:
    """Per-bar total returns from :func:`adjusted_close` (NaN rows dropped).

    Args:
        hist: OHLCV frame from the DataProvider.
        log: Return log returns instead of simple returns.
    """
    series = adjusted_close(hist).dropna()
    series = series[series > 0]
    if len(series) < 2:
        return pd.Series(dtype=float)
    out = np.log(series).diff() if log else series.pct_change()
    return out.dropna()


def total_return(hist: pd.DataFrame, bars: int | None = None) -> float | None:
    """Total return over the last ``bars`` bars (whole series when ``None``).

    Returns ``None`` when the series is shorter than ``bars + 1`` points.
    """
    series = adjusted_close(hist).dropna()
    series = series[series > 0]
    if series.empty:
        return None
    if bars is None:
        start = float(series.iloc[0])
    else:
        if bars <= 0 or len(series) < bars + 1:
            return None
        start = float(series.iloc[-(bars + 1)])
    return float(series.iloc[-1]) / start - 1.0


def realized_volatility(hist: pd.DataFrame, window: int | None = None, periods_per_year: int = 252) -> float | None:
    """Annualized standard deviation of total returns (``None`` with < 10 returns)."""
    rets = returns(hist)
    if window is not None:
        rets = rets.tail(window)
    if len(rets) < 10:
        return None
    return float(rets.std() * np.sqrt(periods_per_year))
