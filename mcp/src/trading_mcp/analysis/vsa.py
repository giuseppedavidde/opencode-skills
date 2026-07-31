"""Volume Spread Analysis: Wyckoff VSA climax and absorption detection.

Analyzes the relationship between volume and price range to detect
anomalous candles: climax (buying/selling), stopping volume, no demand/supply.

Based on linear regression of normalized volume vs normalized range.
Adapted for daily timeframe with norm_lookback=20 (~1 trading month).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scipy.stats import linregress


def _compute_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, lookback: int
) -> np.ndarray:
    """Compute ATR with pure numpy/pandas (no pandas_ta).

    Args:
        high: Array of high prices.
        low: Array of low prices.
        close: Array of close prices.
        lookback: Rolling window for ATR calculation.

    Returns:
        ATR values as numpy array (same length as input).
    """
    tr = np.maximum(
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    )
    tr_full = np.concatenate([[np.nan], tr])
    series = pd.Series(tr_full)
    return series.rolling(lookback, min_periods=1).mean().values


def _compute_range_deviation(
    hist: pd.DataFrame, norm_lookback: int = 20
) -> np.ndarray:
    """Compute range deviation for all bars via rolling linear regression.

    range_dev[i] = actual_norm_range[i] - predicted_norm_range[i]
    where predicted comes from linregress(norm_volume, norm_range) over window.

    Args:
        hist: OHLCV DataFrame.
        norm_lookback: Rolling window for ATR, median, and regression.

    Returns:
        Array of range deviations (same length as hist, NaN where insufficient data).
    """
    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values
    volume = hist["Volume"].values

    atr_arr = _compute_atr(high, low, close, norm_lookback)
    vol_med = pd.Series(volume).rolling(norm_lookback, min_periods=1).median().values

    norm_range = np.where(atr_arr > 0, (high - low) / atr_arr, 0.0)
    norm_vol = np.where(vol_med > 0, volume / vol_med, 0.0)

    range_dev = np.full(len(hist), np.nan, dtype=np.float64)
    min_start = norm_lookback * 2

    for i in range(min_start, len(hist)):
        window = slice(i - norm_lookback + 1, i + 1)
        nv = norm_vol[window]
        nr = norm_range[window]
        if np.any(np.isnan(nv)) or np.any(np.isnan(nr)):
            continue
        slope, intercept, r_val, _pv, _se = linregress(nv, nr)  # pylint: disable=unbalanced-tuple-unpacking
        if slope <= 0.0 or r_val < 0.2:
            range_dev[i] = 0.0
        else:
            predicted = intercept + slope * norm_vol[i]
            range_dev[i] = norm_range[i] - predicted

    return range_dev


def _classify_vsa_signal(
    dev: float, nvol: float, nrange: float, close_pos: float
) -> tuple[int, str]:
    """Classify VSA signal from normalized metrics on a single bar.

    Returns (score_offset, label) where score_offset is relative to 50.
    Positive values suggest bullish, negative bearish.
    """
    vol_high = bool(nvol > 1.5)
    vol_low = bool(nvol < 0.7)
    dev_high = bool(abs(dev) > 1.0)
    dev_low = bool(abs(dev) < 0.3)
    close_high = bool(close_pos > 0.66)
    close_low = bool(close_pos < 0.33)

    # SELLING CLIMAX (bullish reversal)
    if dev_high and vol_high and close_low and dev > 0:
        return 35, f"SELLING CLIMAX: range={nrange:.2f} (+{dev:.2f}sigma), vol={nvol:.1f}x"

    # BUYING CLIMAX (bearish reversal)
    if dev_high and vol_high and close_high and dev > 0:
        return -35, f"BUYING CLIMAX: range={nrange:.2f} (+{dev:.2f}sigma), vol={nvol:.1f}x"

    # STOPPING VOLUME (absorption)
    if dev_low and vol_high:
        if close_high:
            return 25, f"STOPPING VOLUME bull: vol={nvol:.1f}x, range={nrange:.2f}"
        if close_low:
            return -25, f"STOPPING VOLUME bear: vol={nvol:.1f}x, range={nrange:.2f}"
        return 0, f"High vol absorption: vol={nvol:.1f}x, range={nrange:.2f}"

    # NO DEMAND (bearish)
    if dev_low and vol_low and close_low:
        return -20, f"NO DEMAND: vol={nvol:.2f}x, range={nrange:.2f}"

    # NO SUPPLY (bullish)
    if dev_low and vol_low and close_high:
        return 20, f"NO SUPPLY: vol={nvol:.2f}x, range={nrange:.2f}"

    # Trend UP with normal volume
    if abs(dev) < 0.5 and nvol > 1.0 and close_high:
        return 15, f"Bullish follow-through: vol={nvol:.1f}x"

    # Trend DOWN with normal volume
    if abs(dev) < 0.5 and nvol > 1.0 and close_low:
        return -15, f"Bearish follow-through: vol={nvol:.1f}x"

    # Wide range limit
    if nrange > 3.0:
        return -20, f"Wide range {nrange:.1f}sigma"

    return 0, f"VSA normal: dev={dev:.2f}, vol={nvol:.2f}x"


def compute_vsa(hist: pd.DataFrame, norm_lookback: int = 20) -> tuple[int, str]:
    """Volume Spread Analysis dimension (0-100).

    Analyzes the relationship between volume and price range to detect
    Wyckoff VSA signals: climax, stopping volume, no demand/supply.

    Steps:
    1. ATR rolling on norm_lookback (pure numpy, no pandas_ta)
    2. Volume median rolling on norm_lookback
    3. norm_range = (High - Low) / ATR
    4. norm_volume = Volume / vol_median
    5. Per-bar linregress of norm_volume vs norm_range on window
    6. range_dev = actual_range - predicted_range
    7. Classify VSA signal on last bar

    Score ranges:
    - 75-90: Stopping volume bullish (range_dev negative, volume high, close high)
    - 60-74: No supply (tight range, low volume, close high)
    - 40-59: Neutral (no clear signal)
    - 25-39: No demand (tight range, low volume, close low)
    - 10-24: Selling climax bearish (range_dev positive, volume high, close low)

    Args:
        hist: OHLCV DataFrame.
        norm_lookback: Rolling window for normalization (default 20, ~1 month).

    Returns:
        (score 0-100, detail string).
    """
    if len(hist) < norm_lookback * 2 + 10:
        return 50, "Insufficient data for VSA"

    range_dev = _compute_range_deviation(hist, norm_lookback)

    close = hist["Close"].values
    low = hist["Low"].values
    high = hist["High"].values
    volume = hist["Volume"].values

    atr_arr = _compute_atr(high, low, close, norm_lookback)
    vol_med = pd.Series(volume).rolling(norm_lookback, min_periods=1).median().values

    norm_range = np.where(atr_arr > 0, (high - low) / atr_arr, 0.0)
    norm_vol = np.where(vol_med > 0, volume / vol_med, 0.0)

    last_dev = range_dev[-1]
    last_range = norm_range[-1]
    last_vol = norm_vol[-1]
    last_close_pos = (
        (close[-1] - low[-1]) / (high[-1] - low[-1])
        if (high[-1] - low[-1]) > 0
        else 0.5
    )

    if np.isnan(last_dev):
        return 50, "VSA: no data | dev=N/A"

    offset, label = _classify_vsa_signal(last_dev, last_vol, last_range, last_close_pos)

    dev_str = f"{last_dev:.2f}" if not np.isnan(last_dev) else "N/A"
    score = min(100, max(0, 50 + offset))
    detail = f"{label} | dev={dev_str}"

    return score, detail


def _detect_signal_type(
    rd_val: float, nvol: float, close_pos: float
) -> str:
    """Detect VSA signal type from normalized metrics.

    Returns one of: selling_climax, buying_climax, stopping_volume,
    no_demand, no_supply, or 'none'.
    """
    if rd_val > 1.0 and nvol > 1.5:
        if close_pos < 0.33:
            return "selling_climax"
        if close_pos > 0.66:
            return "buying_climax"
    if abs(rd_val) < 0.3:
        if nvol > 1.5:
            return "stopping_volume"
        if nvol < 0.7:
            if close_pos < 0.33:
                return "no_demand"
            if close_pos > 0.66:
                return "no_supply"
    return "none"


def _maybe_float(arr: np.ndarray, idx: int, default: float = 0.0) -> float:
    """Safely extract float from numpy array at index."""
    val = arr[idx]
    return float(val) if not np.isnan(val) else default


def get_vsa_signals(
    hist: pd.DataFrame, norm_lookback: int = 20
) -> dict:
    """Return complete VSA signals for recent bars.

    Computes range_dev for all bars and extracts signals from
    the last 5 bars where a VSA pattern is detected.

    Args:
        hist: OHLCV DataFrame.
        norm_lookback: Rolling window for normalization (default 20).

    Returns:
        Dict with current_deviation, current_norm_volume, current_norm_range,
        slope_valid, recent_signals (list), signal_count (int).
    """
    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values
    volume = hist["Volume"].values

    atr_arr = _compute_atr(high, low, close, norm_lookback)
    vol_med = pd.Series(volume).rolling(norm_lookback, min_periods=1).median().values
    norm_range = np.where(atr_arr > 0, (high - low) / atr_arr, 0.0)
    norm_vol = np.where(vol_med > 0, volume / vol_med, 0.0)
    range_dev = _compute_range_deviation(hist, norm_lookback)

    recent_signals: list[dict] = []
    n = len(hist)
    start = max(0, n - 5)

    for i in range(start, n):
        if np.isnan(range_dev[i]):
            continue
        cp = (
            (close[i] - low[i]) / (high[i] - low[i])
            if (high[i] - low[i]) > 0
            else 0.5
        )
        signal = _detect_signal_type(range_dev[i], norm_vol[i], cp)
        if signal != "none":
            recent_signals.append({
                "bar": i,
                "date": str(hist.index[i].date()),
                "signal": signal,
                "range_dev": round(float(range_dev[i]), 3),
                "norm_vol": round(float(norm_vol[i]), 2),
                "close_position": round(float(cp), 2),
            })

    return {
        "current_deviation": round(_maybe_float(range_dev, -1), 3),
        "current_norm_volume": round(_maybe_float(norm_vol, -1), 2),
        "current_norm_range": round(_maybe_float(norm_range, -1), 2),
        "slope_valid": not np.isnan(range_dev[-1]),
        "recent_signals": recent_signals,
        "signal_count": len(recent_signals),
    }
