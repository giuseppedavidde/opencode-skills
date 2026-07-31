"""Volatility Hawkes process: regime detection and signal generation.

Adapted from VolatilityHawkes library for daily timeframe.
Uses a Hawkes self-exciting process on ATR-normalized daily range
to detect volatility clustering, silence, spikes, and breakout signals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_NORM_LOOKBACK = 20
_HAWKES_KAPPA = 0.3
_SIGNAL_LOOKBACK = 10


def _compute_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, lookback: int
) -> np.ndarray:
    """Compute ATR with pure numpy/pandas (no pandas_ta)."""
    tr = np.maximum(
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    )
    tr_full = np.concatenate([[np.nan], tr])
    series = pd.Series(tr_full)
    return series.rolling(lookback, min_periods=1).mean().values


def _hawkes_process(arr: np.ndarray, kappa: float) -> np.ndarray:
    """Hawkes self-exciting process.

    Args:
        arr: Input array of normalized ranges.
        kappa: Decay parameter (higher = faster decay).

    Returns:
        Hawkes process values (same length as input).
    """
    alpha = np.exp(-kappa)
    output = np.full_like(arr, np.nan, dtype=np.float64)
    for i in range(1, len(arr)):
        if np.isnan(output[i - 1]):
            output[i] = arr[i] if not np.isnan(arr[i]) else np.nan
        else:
            output[i] = output[i - 1] * alpha + (
                arr[i] if not np.isnan(arr[i]) else 0.0
            )
    return output * kappa


def _compute_hawkes_state(hist: pd.DataFrame) -> dict:
    """Compute all Hawkes state variables from OHLCV data.

    Returns a dict with arrays and scalars consumed by
    compute_volatility_hawkes and get_vol_regime.
    """
    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values

    atr_values = _compute_atr(high, low, close, _NORM_LOOKBACK)

    norm_range = np.full_like(high, np.nan, dtype=np.float64)
    valid = atr_values > 0
    norm_range[valid] = (high[valid] - low[valid]) / atr_values[valid]

    hawkes_values = _hawkes_process(norm_range, _HAWKES_KAPPA)

    hawkes_series = pd.Series(hawkes_values)
    q05 = (
        hawkes_series.rolling(_SIGNAL_LOOKBACK, min_periods=_SIGNAL_LOOKBACK)
        .quantile(0.05)
        .values
    )
    q95 = (
        hawkes_series.rolling(_SIGNAL_LOOKBACK, min_periods=_SIGNAL_LOOKBACK)
        .quantile(0.95)
        .values
    )

    # Signal detection loop
    n = len(close)
    signal = np.zeros(n, dtype=np.float64)
    last_below = -1
    curr_sig = 0.0

    for i in range(n):
        if np.isnan(q05[i]) or np.isnan(q95[i]) or np.isnan(hawkes_values[i]):
            signal[i] = curr_sig
            continue

        if hawkes_values[i] < q05[i]:
            last_below = i
            curr_sig = 0.0

        if (
            hawkes_values[i] > q95[i]
            and i > 0
            and not np.isnan(hawkes_values[i - 1])
            and not np.isnan(q95[i - 1])
            and hawkes_values[i - 1] <= q95[i - 1]
            and last_below >= 0
        ):
            delta = close[i] - close[last_below]
            curr_sig = 1.0 if delta > 0.0 else -1.0

        signal[i] = curr_sig

    return {
        "n": n,
        "close": close,
        "atr_values": atr_values,
        "norm_range": norm_range,
        "hawkes_values": hawkes_values,
        "hawkes_series": hawkes_series,
        "q05": q05,
        "q95": q95,
        "signal": signal,
    }


def compute_volatility_hawkes(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute volatility Hawkes score (0-100).

    Detects volatility breakout signals using a Hawkes self-exciting
    process on ATR-normalized daily ranges.

    Args:
        hist: OHLCV DataFrame with columns Open, High, Low, Close, Volume.

    Returns:
        (score 0-100, detail string).
    """
    if hist.empty or len(hist) < _NORM_LOOKBACK:
        return 50, "Insufficient data for volatility Hawkes"

    state = _compute_hawkes_state(hist)
    n: int = state["n"]
    close: np.ndarray = state["close"]
    hawkes_values: np.ndarray = state["hawkes_values"]
    q05: np.ndarray = state["q05"]
    q95: np.ndarray = state["q95"]
    signal: np.ndarray = state["signal"]
    atr_values: np.ndarray = state["atr_values"]

    current_hawkes = float(hawkes_values[-1])
    q05_val = float(q05[-1]) if not np.isnan(q05[-1]) else 0.0
    q95_val = float(q95[-1]) if not np.isnan(q95[-1]) else 0.0
    current_atr = float(atr_values[-1]) if not np.isnan(atr_values[-1]) else 0.0

    detail_parts: list[str] = [f"HW={current_hawkes:.4f}"]

    # Detect most recent signal in last 5 bars (closest to now)
    recent_signal: str | None = None
    recent_signal_bar = -1
    for i in range(n - 1, max(0, n - 6) - 1, -1):
        if signal[i] == 1.0:
            recent_signal = "long"
            recent_signal_bar = i
            break
        if signal[i] == -1.0:
            recent_signal = "short"
            recent_signal_bar = i
            break

    score = 50

    # Price trend in last 5 bars for signal confirmation
    price_rising = False
    price_falling = False
    if n >= 6:
        price_rising = bool(close[-1] > close[-6])
        price_falling = bool(close[-1] < close[-6])

    # --- Hierarchical score assignment ---
    if recent_signal == "long" and price_rising:
        score = 75
        detail_parts.append("LONG signal + price rising (75)")
    elif recent_signal == "short" and price_falling:
        score = 25
        detail_parts.append("SHORT signal + price falling (25)")
    else:
        hawkes_rising = False
        hawkes_flat_low = False

        if n >= 4:
            h_val_last = hawkes_values[-1]
            h_val_4ago = hawkes_values[-4]
            if not np.isnan(h_val_last) and not np.isnan(h_val_4ago):
                slope = (h_val_last - h_val_4ago) / max(abs(h_val_4ago), 1e-10)
                if slope > 0.1:
                    hawkes_rising = True
                elif abs(slope) < 0.05 and current_hawkes < 0.5:
                    hawkes_flat_low = True

        if hawkes_rising:
            score = 30
            detail_parts.append("Vol clustering (rising Hawkes) (30)")
        elif hawkes_flat_low:
            score = 70
            detail_parts.append("Low vol calm regime (70)")
        else:
            detail_parts.append("No clear signal (50)")

    # --- Bonus/penalty for recent price movement ---
    if n >= 6:
        recent_return = (float(close[-1]) - float(close[-6])) / float(close[-6])
        if recent_return > 0.02:
            bonus = min(10, int(recent_return * 100))
            score = min(100, score + bonus)
            detail_parts.append(f"Bullish momentum (+{bonus})")
        elif recent_return < -0.02:
            penalty = min(10, int(abs(recent_return) * 100))
            score = max(0, score - penalty)
            detail_parts.append(f"Bearish momentum (-{penalty})")

    score = min(100, max(0, score))

    detail_parts.append(f"Q05={q05_val:.4f} Q95={q95_val:.4f}")
    detail_parts.append(f"ATR={current_atr:.4f}")

    if recent_signal:
        bars_ago = n - 1 - recent_signal_bar
        detail_parts.append(f"Signal: {recent_signal} ({bars_ago}b ago)")

    return score, " | ".join(detail_parts)


def get_vol_regime(hist: pd.DataFrame) -> dict:
    """Extract volatility regime from Hawkes process analysis.

    Args:
        hist: OHLCV DataFrame with columns Open, High, Low, Close, Volume.

    Returns:
        Dict with hawkes_value, hawkes_q05, hawkes_q95, norm_range,
        regime, atr, signal, signal_bars_ago.
    """
    if hist.empty or len(hist) < _NORM_LOOKBACK:
        return {
            "hawkes_value": 0.0,
            "hawkes_q05": 0.0,
            "hawkes_q95": 0.0,
            "norm_range": 0.0,
            "regime": "normal",
            "atr": 0.0,
            "signal": "none",
            "signal_bars_ago": None,
        }

    state = _compute_hawkes_state(hist)
    n: int = state["n"]
    hawkes_values: np.ndarray = state["hawkes_values"]
    hawkes_series: pd.Series = state["hawkes_series"]
    q05: np.ndarray = state["q05"]
    q95: np.ndarray = state["q95"]
    norm_range: np.ndarray = state["norm_range"]
    signal: np.ndarray = state["signal"]
    atr_values: np.ndarray = state["atr_values"]

    current_hawkes = float(hawkes_values[-1])
    q05_val = float(q05[-1]) if not np.isnan(q05[-1]) else 0.0
    q95_val = float(q95[-1]) if not np.isnan(q95[-1]) else 0.0
    current_norm = float(norm_range[-1]) if not np.isnan(norm_range[-1]) else 0.0
    current_atr = float(atr_values[-1]) if not np.isnan(atr_values[-1]) else 0.0

    # Additional rolling quantiles for regime classification
    q70 = (
        hawkes_series.rolling(_SIGNAL_LOOKBACK, min_periods=_SIGNAL_LOOKBACK)
        .quantile(0.70)
        .values
    )
    q50 = (
        hawkes_series.rolling(_SIGNAL_LOOKBACK, min_periods=_SIGNAL_LOOKBACK)
        .quantile(0.50)
        .values
    )
    q30 = (
        hawkes_series.rolling(_SIGNAL_LOOKBACK, min_periods=_SIGNAL_LOOKBACK)
        .quantile(0.30)
        .values
    )

    regime = "normal"

    # vol_spike: hawkes > q95 now AND was below q50 3 bars ago
    if (
        current_hawkes > q95_val
        and n >= 4
        and not np.isnan(hawkes_values[-4])
        and not np.isnan(q50[-4])
        and hawkes_values[-4] < q50[-4]
    ):
        regime = "vol_spike"

    # high_vol_cluster: hawkes > q70 AND rising last 3 bars
    if regime == "normal":
        q70_val = float(q70[-1]) if not np.isnan(q70[-1]) else 0.0
        if current_hawkes > q70_val and n >= 4:
            h = hawkes_values
            if (
                not np.isnan(h[-1])
                and not np.isnan(h[-2])
                and not np.isnan(h[-3])
                and h[-1] > h[-2]
                and h[-2] > h[-3]
            ):
                regime = "high_vol_cluster"

    # low_vol_silence: hawkes < q30 for last 5 bars
    if regime == "normal" and n >= 5:
        q30_val = float(q30[-1]) if not np.isnan(q30[-1]) else 0.0
        recent = hawkes_values[-5:]
        if not np.any(np.isnan(recent)) and np.all(recent < q30_val):
            regime = "low_vol_silence"

    # Recent signal in last 5 bars
    signal_str = "none"
    signal_bars: int | None = None
    for i in range(n - 1, max(0, n - 6) - 1, -1):
        if signal[i] == 1.0:
            signal_str = "long"
            signal_bars = n - 1 - i
            break
        if signal[i] == -1.0:
            signal_str = "short"
            signal_bars = n - 1 - i
            break

    return {
        "hawkes_value": round(current_hawkes, 6),
        "hawkes_q05": round(q05_val, 6),
        "hawkes_q95": round(q95_val, 6),
        "norm_range": round(current_norm, 6),
        "regime": regime,
        "atr": round(current_atr, 6),
        "signal": signal_str,
        "signal_bars_ago": signal_bars,
    }
