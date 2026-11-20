"""Volume Profile: POC, value area, HVN/LVN and an extension score (SIG-15).

Method (documented, unvalidated):

- Window: the last 252 complete daily bars (one year). The volume of each
  bar is spread uniformly over the bins between its Low and High (no
  intraday data, so this is an approximation of volume at price).
- Bin width: 0.25 x Wilder ATR(14), bounded so the profile has 24 to 240
  bins. The bin width follows the volatility of the name instead of a fixed
  bin count over the range.
- Value area: 70% of the volume, grown from the POC with the two-row rule
  (CBOT Market Profile): compare the volume of the next two rows above with
  the next two rows below and add the larger pair; a tie adds both pairs.
- HVN/LVN: local maxima/minima of the histogram smoothed with a Gaussian
  kernel (sigma 1.5 bins); a node needs a prominence of 10% of the peak.
- Extension score (0-100): price below VAL - 0.25 ATR gives 20, above
  VAH + 0.25 ATR gives 80, inside the value area 35 + 30 x position (0 at
  VAL, 1 at VAH); within 0.5 ATR of the POC the score moves halfway to 50.
  The score is rounded to a 5-point grid. Low = discount, high = extended.
- Bin sensitivity: the score is also computed at 0.5x and 2x the bin width.
  ``zone_stable`` is False when the zone (<=40, 40-60, >=60) changes.

Without enough bars, a price range or volume, ``available`` is False and
every level is ``None`` (never 0.0).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trading_mcp.analysis.ta_core import atr_last

PROFILE_BARS = 252
MIN_BARS = 20
VALUE_AREA_FRACTION = 0.70
BIN_ATR_FRACTION = 0.25
MIN_BINS = 24
MAX_BINS = 240
SMOOTH_SIGMA_BINS = 1.5
NODE_PROMINENCE = 0.10
EDGE_BUFFER_ATR = 0.25
POC_BALANCE_ATR = 0.5
SENSITIVITY_FACTORS = (0.5, 2.0)


def zone_of(score: float | None) -> str | None:
    """Action zone of an extension score: ``discount`` (<=40), ``extended`` (>=60) or ``inside``."""
    if score is None:
        return None
    if score <= 40:
        return "discount"
    if score >= 60:
        return "extended"
    return "inside"


def _empty_profile(price: float | None = None, detail: str = "Insufficient data") -> dict[str, Any]:
    return {
        "available": False,
        "poc_price": None,
        "val": None,
        "vah": None,
        "price": round(price, 4) if price is not None else None,
        "price_position": None,
        "score": None,
        "zone": None,
        "detail": detail,
        "hvn": [],
        "lvn": [],
        "atr": None,
        "bin_width": None,
        "n_bins": 0,
        "bars_used": 0,
        "sensitivity": None,
    }


def _volume_histogram(low: np.ndarray, high: np.ndarray, volume: np.ndarray,
                      lo: float, bin_w: float, n_bins: int) -> np.ndarray:
    """Spread each bar's volume uniformly over the bins between its Low and High."""
    first = np.clip(((low - lo) / bin_w).astype(int), 0, n_bins - 1)
    last = np.clip(((high - lo) / bin_w).astype(int), 0, n_bins - 1)
    span = last - first + 1
    share = volume / span
    diff = np.zeros(n_bins + 1, dtype=float)
    np.add.at(diff, first, share)
    np.add.at(diff, last + 1, -share)
    return np.cumsum(diff[:-1])


def _value_area(hist: np.ndarray) -> tuple[int, int]:
    """Two-row value-area expansion from the POC (ties add both pairs)."""
    n = len(hist)
    poc = int(np.argmax(hist))
    total = float(hist.sum())
    if total <= 0:
        return poc, poc
    target = total * VALUE_AREA_FRACTION
    acc = float(hist[poc])
    lo = hi = poc
    while acc < target and (lo > 0 or hi < n - 1):
        up = float(hist[hi + 1:min(hi + 3, n)].sum()) if hi < n - 1 else -1.0
        down = float(hist[max(lo - 2, 0):lo].sum()) if lo > 0 else -1.0
        if up > down:
            hi = min(hi + 2, n - 1)
            acc += up
        elif down > up:
            lo = max(lo - 2, 0)
            acc += down
        else:
            hi, lo = min(hi + 2, n - 1), max(lo - 2, 0)
            acc += up + down
    return lo, hi


def _smooth(hist: np.ndarray) -> np.ndarray:
    radius = int(np.ceil(3 * SMOOTH_SIGMA_BINS))
    x = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (x / SMOOTH_SIGMA_BINS) ** 2)
    kernel /= kernel.sum()
    return np.convolve(np.pad(hist, radius, mode="edge"), kernel, mode="valid")


def _nodes(hist: np.ndarray, lo: float, bin_w: float) -> tuple[list[float], list[float]]:
    """HVN and LVN prices from the smoothed histogram (at most five each)."""
    from scipy.signal import find_peaks  # pylint: disable=import-outside-toplevel

    smooth = _smooth(hist)
    peak = float(smooth.max())
    if peak <= 0:
        return [], []
    prominence = NODE_PROMINENCE * peak
    hvn_idx, hvn_props = find_peaks(smooth, prominence=prominence, distance=2)
    lvn_idx, lvn_props = find_peaks(-smooth, prominence=prominence, distance=2)
    order_h = np.argsort(hvn_props.get("prominences", np.zeros(len(hvn_idx))))[::-1][:5]
    order_l = np.argsort(lvn_props.get("prominences", np.zeros(len(lvn_idx))))[::-1][:5]
    hvn = sorted(round(lo + (int(hvn_idx[i]) + 0.5) * bin_w, 4) for i in order_h)
    lvn = sorted(round(lo + (int(lvn_idx[i]) + 0.5) * bin_w, 4) for i in order_l)
    return hvn, lvn


def _extension(price: float, val: float, vah: float, poc: float, atr: float) -> tuple[float, str, list[str]]:
    details: list[str] = []
    buffer = EDGE_BUFFER_ATR * atr
    span = max(vah - val, 1e-9)
    if price < val - buffer:
        position, score = "below_val", 20.0
        details.append(f"Price below VAL ({val:.2f}): discount vs value area")
    elif price > vah + buffer:
        position, score = "above_vah", 80.0
        details.append(f"Price above VAH ({vah:.2f}): extended vs value area")
    else:
        position = "inside_va"
        frac = min(1.0, max(0.0, (price - val) / span))
        score = 35.0 + 30.0 * frac
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f})")
        if abs(price - poc) <= POC_BALANCE_ATR * atr:
            score = 0.5 * score + 25.0
            details.append("Near POC: balanced")
    return float(5 * round(score / 5.0)), position, details


def _profile_core(df: pd.DataFrame, bin_w: float, atr: float, price: float) -> dict[str, Any] | None:
    low = df["Low"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    volume = df["Volume"].to_numpy(dtype=float)
    lo, hi = float(np.nanmin(low)), float(np.nanmax(high))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo or bin_w <= 0:
        return None
    n_bins = int(min(MAX_BINS, max(MIN_BINS, np.ceil((hi - lo) / bin_w))))
    bin_w = (hi - lo) / n_bins
    hist = _volume_histogram(low, high, volume, lo, bin_w, n_bins)
    if float(hist.sum()) <= 0:
        return None
    poc_bin = int(np.argmax(hist))
    left, right = _value_area(hist)
    poc = lo + (poc_bin + 0.5) * bin_w
    val = lo + left * bin_w
    vah = lo + (right + 1) * bin_w
    score, position, details = _extension(price, val, vah, poc, atr)
    return {"hist": hist, "lo": lo, "bin_w": bin_w, "n_bins": n_bins, "poc": poc, "val": val,
            "vah": vah, "score": score, "position": position, "details": details}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.dropna(subset=["Close"]).copy()
    for col in ("High", "Low"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(out["Close"])
    out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce").fillna(0.0).clip(lower=0.0)
    low, high = out["Low"].to_numpy(dtype=float), out["High"].to_numpy(dtype=float)
    out["Low"], out["High"] = np.minimum(low, high), np.maximum(low, high)
    return out


def build_profile(hist: pd.DataFrame, *, bars: int = PROFILE_BARS, sensitivity: bool = True) -> dict[str, Any]:
    """Volume profile of the last ``bars`` complete bars (see the module docstring)."""
    if hist is None or hist.empty or len(hist) < MIN_BARS:
        return _empty_profile(detail="Insufficient data")
    df = _clean(hist.tail(bars))
    if len(df) < MIN_BARS:
        return _empty_profile(detail="No valid price data")
    price = float(df["Close"].iloc[-1])
    atr = atr_last(df)
    if atr is None:
        return _empty_profile(price=price, detail="ATR unavailable")
    base_w = BIN_ATR_FRACTION * atr
    core = _profile_core(df, base_w, atr, price)
    if core is None:
        return _empty_profile(price=price, detail="No price range or no volume")
    hvn, lvn = _nodes(core["hist"], core["lo"], core["bin_w"])
    details = core["details"] + [f"POC ${core['poc']:.2f}", f"{core['n_bins']} bins of {core['bin_w']:.4f}"]
    sens: dict[str, Any] | None = None
    if sensitivity:
        scores: dict[str, float | None] = {"1x": core["score"]}
        for factor in SENSITIVITY_FACTORS:
            alt = _profile_core(df, base_w * factor, atr, price)
            scores[f"{factor:g}x"] = alt["score"] if alt is not None else None
        zones = {zone_of(s) for s in scores.values() if s is not None}
        sens = {"scores": scores, "zone_stable": len(zones) == 1}
        if len(zones) > 1:
            details.append("zone changes with the bin width (unstable)")
    score = int(core["score"])
    return {
        "available": True,
        "poc_price": round(core["poc"], 4),
        "val": round(core["val"], 4),
        "vah": round(core["vah"], 4),
        "price": round(price, 4),
        "price_position": core["position"],
        "score": score,
        "zone": zone_of(score),
        "detail": " | ".join(details),
        "hvn": hvn,
        "lvn": lvn,
        "atr": round(atr, 4),
        "bin_width": round(core["bin_w"], 6),
        "n_bins": core["n_bins"],
        "bars_used": len(df),
        "sensitivity": sens,
    }


def compute_volume_profile(hist: pd.DataFrame) -> tuple[int | None, str]:
    """Extension score (0-100, ``None`` without a profile) and detail string."""
    profile = build_profile(hist, sensitivity=False)
    return profile["score"], profile["detail"]


def get_profile_levels(hist: pd.DataFrame) -> dict[str, Any]:
    """Profile levels, extension score, HVN/LVN and bin sensitivity (see :func:`build_profile`)."""
    return build_profile(hist)
