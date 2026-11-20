"""Volume Spread Analysis with background trend (SIG-16; 0-100, 50 = neutral).

Each bar is described by:

- ``nvol``: volume / rolling 20-bar median volume;
- ``nrange``: (High - Low) / Wilder ATR(20), so ranges are in ATR UNITS (not sigma);
- ``dev``: ``nrange`` minus the range predicted by a rolling 20-bar linear
  regression of ``nrange`` on ``nvol`` (0 when the fit has no positive slope
  or r < 0.2): positive = wider than the volume suggests, negative = narrower;
- ``close_pos``: position of the close in the bar range (0 = low, 1 = high);
- background: sign of the 20-bar close change (``up``/``down``/``flat``).

Mirror rules on the LAST complete bar (documented, unvalidated):

- climax (nvol > 1.5 and a wide bar: nrange > 1.5 or dev > 1):
  down bar after a decline that closes off the low (close_pos >= 0.4) is a
  SELLING CLIMAX (+25); up bar after an advance that closes off the high
  (close_pos <= 0.6) is a BUYING CLIMAX (-25); otherwise a wide down bar that
  closes near the low is high-volume weakness (-15) and a wide up bar that
  closes near the high is high-volume strength (+15);
- stopping volume (nvol > 1.5, dev < -0.3): after a decline with
  close_pos >= 0.5 +20; after an advance with close_pos <= 0.5 -20;
- no supply / no demand (nvol < 0.7, |dev| < 0.3): a down bar in a decline
  that closes in the upper half is NO SUPPLY (+15); an up bar in an advance
  that closes in the lower half is NO DEMAND (-15).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import linregress

from trading_mcp.analysis.ta_core import wilder_atr

NORM_LOOKBACK = 20


def _normalized(hist: pd.DataFrame, norm_lookback: int) -> tuple[np.ndarray, np.ndarray]:
    atr = wilder_atr(hist, norm_lookback).to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    vol_med = pd.Series(volume).rolling(norm_lookback, min_periods=1).median().to_numpy()
    spread = (hist["High"] - hist["Low"]).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        norm_range = np.where(atr > 0, spread / atr, np.nan)
        norm_vol = np.where(vol_med > 0, volume / vol_med, np.nan)
    return norm_range, norm_vol


def _compute_range_deviation(hist: pd.DataFrame, norm_lookback: int = NORM_LOOKBACK) -> np.ndarray:
    """Range deviation per bar (ATR units, NaN where the window is incomplete)."""
    norm_range, norm_vol = _normalized(hist, norm_lookback)
    range_dev = np.full(len(hist), np.nan, dtype=np.float64)
    for i in range(norm_lookback * 2, len(hist)):
        window = slice(i - norm_lookback + 1, i + 1)
        nv, nr = norm_vol[window], norm_range[window]
        if np.any(np.isnan(nv)) or np.any(np.isnan(nr)) or np.ptp(nv) == 0:
            continue
        slope, intercept, r_val, _pv, _se = linregress(nv, nr)  # pylint: disable=unbalanced-tuple-unpacking
        if slope <= 0.0 or r_val < 0.2:
            range_dev[i] = 0.0
        else:
            range_dev[i] = norm_range[i] - (intercept + slope * norm_vol[i])
    return range_dev


def _background(close: np.ndarray, i: int, bars: int = 20) -> str:
    if i - bars < 0:
        return "flat"
    change = close[i] - close[i - bars]
    return "up" if change > 0 else "down" if change < 0 else "flat"


def classify_bar(dev: float, nvol: float, nrange: float, close_pos: float,
                 bar_dir: int, background: str) -> tuple[int, str, str]:
    """``(score offset, signal name, label)`` of one bar (see the module docstring)."""
    if any(np.isnan(x) for x in (dev, nvol, nrange)):
        return 0, "none", "VSA: no data"
    wide = nrange > 1.5 or dev > 1.0
    if nvol > 1.5 and wide:
        if bar_dir < 0 and background == "down" and close_pos >= 0.4:
            return 25, "selling_climax", f"SELLING CLIMAX: range {nrange:.2f} ATR, vol {nvol:.1f}x, close off the low"
        if bar_dir > 0 and background == "up" and close_pos <= 0.6:
            return -25, "buying_climax", f"BUYING CLIMAX: range {nrange:.2f} ATR, vol {nvol:.1f}x, close off the high"
        if bar_dir < 0 and close_pos < 0.33:
            return -15, "high_volume_weakness", f"High-volume weakness: range {nrange:.2f} ATR, vol {nvol:.1f}x"
        if bar_dir > 0 and close_pos > 0.66:
            return 15, "high_volume_strength", f"High-volume strength: range {nrange:.2f} ATR, vol {nvol:.1f}x"
    if nvol > 1.5 and dev < -0.3:
        if background == "down" and close_pos >= 0.5:
            return 20, "stopping_volume", f"STOPPING VOLUME bull: vol {nvol:.1f}x, dev {dev:+.2f} ATR"
        if background == "up" and close_pos <= 0.5:
            return -20, "stopping_volume_bear", f"STOPPING VOLUME bear: vol {nvol:.1f}x, dev {dev:+.2f} ATR"
    if nvol < 0.7 and abs(dev) < 0.3:
        if bar_dir < 0 and background == "down" and close_pos >= 0.5:
            return 15, "no_supply", f"NO SUPPLY: vol {nvol:.2f}x, range {nrange:.2f} ATR"
        if bar_dir > 0 and background == "up" and close_pos <= 0.5:
            return -15, "no_demand", f"NO DEMAND: vol {nvol:.2f}x, range {nrange:.2f} ATR"
    return 0, "none", f"VSA normal: dev {dev:+.2f} ATR, vol {nvol:.2f}x"


def _bar_inputs(hist: pd.DataFrame, i: int, range_dev: np.ndarray, norm_range: np.ndarray,
                norm_vol: np.ndarray) -> tuple[float, float, float, float, int, str]:
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    spread = high[i] - low[i]
    close_pos = (close[i] - low[i]) / spread if spread > 0 else 0.5
    bar_dir = int(np.sign(close[i] - close[i - 1])) if i > 0 else 0
    return float(range_dev[i]), float(norm_vol[i]), float(norm_range[i]), float(close_pos), bar_dir, \
        _background(close, i)


def compute_vsa(hist: pd.DataFrame, norm_lookback: int = NORM_LOOKBACK) -> tuple[int, str]:
    """VSA score of the last complete bar (0-100, 50 = neutral)."""
    if len(hist) < norm_lookback * 2 + 10:
        return 50, "Insufficient data for VSA"
    range_dev = _compute_range_deviation(hist, norm_lookback)
    norm_range, norm_vol = _normalized(hist, norm_lookback)
    i = len(hist) - 1
    if np.isnan(range_dev[i]):
        return 50, "VSA: no data | dev=N/A"
    inputs = _bar_inputs(hist, i, range_dev, norm_range, norm_vol)
    offset, _signal, label = classify_bar(*inputs)
    return int(min(100, max(0, 50 + offset))), f"{label} | background {inputs[5]}"


def _maybe_float(arr: np.ndarray, idx: int) -> float | None:
    val = arr[idx]
    return float(val) if not np.isnan(val) else None


def get_vsa_signals(hist: pd.DataFrame, norm_lookback: int = NORM_LOOKBACK) -> dict:
    """VSA signals of the last 5 complete bars (informational; the score uses the last bar)."""
    if hist is None or len(hist) < norm_lookback * 2 + 1:
        return {"current_deviation": None, "current_norm_volume": None, "current_norm_range": None,
                "slope_valid": False, "recent_signals": [], "signal_count": 0, "units": "ATR"}
    range_dev = _compute_range_deviation(hist, norm_lookback)
    norm_range, norm_vol = _normalized(hist, norm_lookback)
    recent: list[dict] = []
    n = len(hist)
    for i in range(max(1, n - 5), n):
        if np.isnan(range_dev[i]):
            continue
        inputs = _bar_inputs(hist, i, range_dev, norm_range, norm_vol)
        offset, signal, _label = classify_bar(*inputs)
        if signal != "none":
            recent.append({
                "bar": i,
                "date": str(hist.index[i].date()) if hasattr(hist.index[i], "date") else str(hist.index[i]),
                "signal": signal,
                "score_offset": offset,
                "range_dev_atr": round(inputs[0], 3),
                "norm_vol": round(inputs[1], 2),
                "close_position": round(inputs[3], 2),
                "background": inputs[5],
            })
    dev_last = _maybe_float(range_dev, -1)
    vol_last = _maybe_float(norm_vol, -1)
    range_last = _maybe_float(norm_range, -1)
    return {
        "current_deviation": round(dev_last, 3) if dev_last is not None else None,
        "current_norm_volume": round(vol_last, 2) if vol_last is not None else None,
        "current_norm_range": round(range_last, 2) if range_last is not None else None,
        "slope_valid": dev_last is not None,
        "recent_signals": recent,
        "signal_count": len(recent),
        "units": "ATR",
    }
