"""Technical features and breakout detection (no look-ahead).

Every indicator that feeds a signal at date ``t`` uses only data up to
and including ``t``; rolling highs and volume averages are shifted by
one bar so that the breakout comparison is strictly against *prior*
information.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    """Wilder's Average True Range."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int) -> pd.Series:
    """Wilder's Relative Strength Index."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(avg_loss.notna() | avg_gain.notna())


def forward_return(close: pd.Series, horizon: int) -> pd.Series:
    """Close-to-close forward return over ``horizon`` trading days."""
    return close.shift(-horizon) / close - 1.0


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach every indicator needed by the study to a single symbol frame."""
    out = frame.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]

    out["ret_1d"] = close.pct_change()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()
    out["atr14"] = atr(high, low, close, config.ATR_WINDOW)
    out["atr_pct"] = out["atr14"] / close
    out["rsi14"] = rsi(close, config.RSI_WINDOW)
    out["vol_ma20"] = volume.rolling(config.VOLUME_WINDOW).mean().shift(1)
    out["vol_ratio"] = volume / out["vol_ma20"]
    out["mom12"] = close / close.shift(config.MOMENTUM_WINDOW) - 1.0
    out["mom12_1m"] = close.shift(21) / close.shift(config.MOMENTUM_WINDOW) - 1.0
    out["dist_sma200"] = close / out["sma200"] - 1.0
    out["dist_sma50_atr"] = (close - out["sma50"]) / out["atr14"]
    out["above_sma200"] = close > out["sma200"]

    for lookback in config.BREAKOUT_LOOKBACKS:
        out[f"high{lookback}"] = high.rolling(lookback).max().shift(1)

    for horizon in config.HORIZONS:
        out[f"fwd{horizon}"] = forward_return(close, horizon)

    return out


def breakout_mask(frame: pd.DataFrame, lookback: int, volume_mult: float) -> pd.Series:
    """Boolean mask of breakout events at each date.

    A breakout requires close strictly above the prior ``lookback``-day
    high. When ``volume_mult > 0`` the day's volume must exceed
    ``volume_mult`` times the prior 20-day average volume.
    """
    prior_high = frame[f"high{lookback}"]
    mask = frame["Close"] > prior_high
    if volume_mult > 0:
        mask = mask & (frame["vol_ratio"] > volume_mult)
    return mask.fillna(False)


def raw_breakout_frame(frame: pd.DataFrame, lookback: int, volume_mult: float) -> pd.DataFrame:
    """Rows (with positional index) of breakout events for one config."""
    mask = breakout_mask(frame, lookback, volume_mult).to_numpy()
    positions = np.flatnonzero(mask)
    if positions.size == 0:
        return pd.DataFrame()
    return frame.iloc[positions]
