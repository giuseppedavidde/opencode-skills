"""Shared technical-analysis primitives: one definition for research and production.

Conventions (SIG-10, SIG-21):

- Every frame holds complete daily bars only. The DataProvider drops the
  open session bar (``include_partial=False``), so ``iloc[-1]`` is the last
  complete session, never a partial bar (SIG-11).
- ATR and RSI use Wilder's smoothing (RMA): an EWM with ``alpha = 1/window``,
  ``adjust=False`` and ``min_periods=window``. This is the definition in
  ``research/breakout_calibration/features.py``.
- A volume comparison of bar ``t`` uses the average of the PRIOR ``window``
  bars (``t-window .. t-1``), so the tested bar is never inside its own
  reference (research: ``volume.rolling(20).mean().shift(1)``).
- Levels (support, resistance, stops) use the raw split-adjusted OHLC.
  Returns use :mod:`trading_mcp.data.prices` (``Adj Close``).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

ATR_WINDOW = 14
RSI_WINDOW = 14
VOLUME_WINDOW = 20
LIQUIDITY_WINDOW = 20


def true_range(hist: pd.DataFrame) -> pd.Series:
    """True range per bar (the first bar uses its high-low range)."""
    high = pd.to_numeric(hist["High"], errors="coerce").astype(float)
    low = pd.to_numeric(hist["Low"], errors="coerce").astype(float)
    prev_close = pd.to_numeric(hist["Close"], errors="coerce").astype(float).shift(1)
    return pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)


def wilder_atr(hist: pd.DataFrame, window: int = ATR_WINDOW) -> pd.Series:
    """Wilder ATR series (NaN for the first ``window - 1`` bars)."""
    if hist is None or hist.empty:
        return pd.Series(dtype=float)
    return true_range(hist).ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def atr_last(hist: pd.DataFrame, window: int = ATR_WINDOW) -> float | None:
    """Latest Wilder ATR, or ``None`` with fewer than ``window`` bars."""
    if hist is None or hist.empty or len(hist) < window:
        return None
    value = wilder_atr(hist, window).iloc[-1]
    return float(value) if pd.notna(value) and value > 0 else None


def wilder_rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """Wilder RSI series (100 when there is no loss in the window)."""
    close = pd.to_numeric(close, errors="coerce").astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(loss != 0.0, 100.0).where(gain.notna())


def rsi_last(close: pd.Series, window: int = RSI_WINDOW) -> float | None:
    """Latest Wilder RSI, or ``None`` when the series is too short."""
    if close is None or len(close) < window + 1:
        return None
    value = wilder_rsi(close, window).iloc[-1]
    return float(value) if pd.notna(value) else None


def prior_volume_average(volume: pd.Series, window: int = VOLUME_WINDOW) -> pd.Series:
    """Average volume of the ``window`` bars BEFORE each bar (excludes the bar itself)."""
    volume = pd.to_numeric(volume, errors="coerce").astype(float)
    return volume.rolling(window, min_periods=window).mean().shift(1)


def prior_high(high: pd.Series, lookback: int) -> pd.Series:
    """Highest high of the ``lookback`` bars before each bar (research breakout level)."""
    return pd.to_numeric(high, errors="coerce").astype(float).rolling(lookback, min_periods=lookback).max().shift(1)


def finite(value: Any) -> float | None:
    """``float(value)`` when it is a finite number, else ``None``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def liquidity(hist: pd.DataFrame, *, currency: str | None = None, window: int = LIQUIDITY_WINDOW) -> dict[str, Any]:
    """Average daily volume and dollar volume over the last ``window`` complete bars.

    ``median_dollar_volume`` is the median of ``Close x Volume`` (robust to one
    block trade). Prices quoted in pence (``GBp``/``GBX``) are converted to
    pounds, so the value is in ``currency_unit``.
    """
    out: dict[str, Any] = {
        "window_bars": window, "adv_shares": None, "median_dollar_volume": None,
        "mean_dollar_volume": None, "currency_unit": currency, "bars_used": 0,
    }
    if hist is None or hist.empty or "Volume" not in hist or "Close" not in hist:
        return out
    tail = hist.tail(window)
    volume = pd.to_numeric(tail["Volume"], errors="coerce").astype(float)
    close = pd.to_numeric(tail["Close"], errors="coerce").astype(float)
    valid = volume.notna() & close.notna()
    if int(valid.sum()) < min(window, 5):
        return out
    scale, unit = 1.0, currency
    if currency in ("GBp", "GBX"):
        scale, unit = 0.01, "GBP"
    traded = (close[valid] * scale) * volume[valid]
    out.update(
        adv_shares=round(float(volume[valid].mean()), 0),
        median_dollar_volume=round(float(traded.median()), 0),
        mean_dollar_volume=round(float(traded.mean()), 0),
        currency_unit=unit,
        bars_used=int(valid.sum()),
    )
    return out


def overnight_gaps(hist: pd.DataFrame, bars: int = 252) -> pd.Series:
    """Open-to-previous-close returns of the last ``bars`` complete bars."""
    if hist is None or hist.empty or "Open" not in hist:
        return pd.Series(dtype=float)
    tail = hist.tail(bars + 1)
    opens = pd.to_numeric(tail["Open"], errors="coerce").astype(float)
    prev_close = pd.to_numeric(tail["Close"], errors="coerce").astype(float).shift(1)
    return (opens / prev_close - 1.0).replace([np.inf, -np.inf], np.nan).dropna()


def event_gap_estimate(hist: pd.DataFrame, bars: int = 252, events_per_year: int = 4) -> float | None:
    """Proxy of an earnings-day gap: the median of the ``events_per_year`` largest |gaps|.

    Point-in-time earnings dates are not available for the history, so the
    largest overnight gaps of the last year stand in for the earnings gaps
    (a year has about four reports). ``None`` with fewer than 60 gaps.
    """
    gaps = overnight_gaps(hist, bars).abs()
    if len(gaps) < 60:
        return None
    largest = gaps.nlargest(events_per_year)
    return float(largest.median()) if not largest.empty else None


def swing_pivots(
    high: np.ndarray, low: np.ndarray, order: int
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Confirmed swing highs and lows.

    Bar ``i`` is a swing high when its high is the strict maximum of the
    ``order`` bars on each side (a swing low mirrors it). A pivot is known
    only ``order`` bars later, so the last ``order`` bars never hold a pivot:
    the list never changes when new bars arrive (no repaint).
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(order, len(high) - order):
        window_h = high[i - order:i + order + 1]
        window_l = low[i - order:i + order + 1]
        if high[i] == window_h.max() and int((window_h == high[i]).sum()) == 1:
            highs.append((i, float(high[i])))
        if low[i] == window_l.min() and int((window_l == low[i]).sum()) == 1:
            lows.append((i, float(low[i])))
    return highs, lows


def daily_volatility(hist: pd.DataFrame, window: int = 60) -> float | None:
    """Standard deviation of daily log closes over ``window`` bars (raw Close)."""
    if hist is None or hist.empty or len(hist) < window + 1:
        return None
    close = pd.to_numeric(hist["Close"], errors="coerce").astype(float)
    rets = np.log(close).diff().dropna().tail(window)
    if len(rets) < 10:
        return None
    value = float(rets.std())
    return value if math.isfinite(value) and value > 0 else None
