"""Volume Profile analysis: POC, Value Area, profile shape classification."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_PROFILE_BINS = 40
_VALUE_AREA_FRACTION = 0.70


def _empty_profile(price: float = 0.0, detail: str = "Insufficient data") -> dict[str, Any]:
    return {
        "poc_price": 0.0,
        "val": 0.0,
        "vah": 0.0,
        "price": price,
        "price_position": "inside_va",
        "score": 50,
        "detail": detail,
    }


def _volume_histogram(df: pd.DataFrame, lo: float, hi: float) -> np.ndarray:
    """Distribute each bar's volume across the price bins it traded through.

    Assigning the whole daily volume to the close bin destroys the intraday
    distribution; spreading it over ``[Low, High]`` keeps the profile close to
    a true volume-at-price histogram.
    """
    bin_w = (hi - lo) / _PROFILE_BINS
    hist = np.zeros(_PROFILE_BINS, dtype=float)
    for _, row in df.iterrows():
        bar_lo = float(row["Low"]) if row["Low"] == row["Low"] else float(row["Close"])
        bar_hi = float(row["High"]) if row["High"] == row["High"] else float(row["Close"])
        bar_lo, bar_hi = min(bar_lo, bar_hi), max(bar_lo, bar_hi)
        volume = float(row["Volume"]) if row["Volume"] == row["Volume"] else 0.0
        if volume <= 0:
            continue
        first = int(np.clip((bar_lo - lo) / bin_w, 0, _PROFILE_BINS - 1))
        last = int(np.clip((bar_hi - lo) / bin_w, 0, _PROFILE_BINS - 1))
        span = last - first + 1
        hist[first:last + 1] += volume / span
    return hist


def _value_area(hist: np.ndarray) -> tuple[int, int]:
    """Expand contiguously from the POC until the value area is covered."""
    poc_bin = int(np.argmax(hist))
    total = float(hist.sum())
    if total <= 0:
        return poc_bin, poc_bin
    target = total * _VALUE_AREA_FRACTION
    acc = float(hist[poc_bin])
    left = right = poc_bin
    while acc < target and (left > 0 or right < _PROFILE_BINS - 1):
        vol_left = float(hist[left - 1]) if left > 0 else -1.0
        vol_right = float(hist[right + 1]) if right < _PROFILE_BINS - 1 else -1.0
        if vol_right >= vol_left:
            right += 1
            acc += float(hist[right])
        else:
            left -= 1
            acc += float(hist[left])
    return left, right


def _build_profile(hist: pd.DataFrame) -> dict[str, Any]:
    """Core volume profile calculation.

    ``score`` is an *extension* score in ``[0, 100]``: low means price sits
    below the value area (discount), high means price is extended above it.
    That single convention feeds ``signal_engine`` (VP <= 40 buys, VP >= 60
    avoids) and the scanner, which uses ``100 - score`` as bullish.
    """
    if hist.empty or len(hist) < 20:
        return _empty_profile(detail="Insufficient data")

    df = hist.dropna(subset=["Close"]).copy()
    if df.empty:
        return _empty_profile(detail="No valid price data")

    price = float(df["Close"].iloc[-1])
    lo = float(df["Low"].min())
    hi = float(df["High"].max())
    if hi <= lo:
        return _empty_profile(price=price, detail="No price range")

    volume_hist = _volume_histogram(df, lo, hi)
    if float(volume_hist.sum()) <= 0:
        return _empty_profile(price=price, detail="No volume data")

    bin_w = (hi - lo) / _PROFILE_BINS
    poc_bin = int(np.argmax(volume_hist))
    poc_price = lo + (poc_bin + 0.5) * bin_w

    left, right = _value_area(volume_hist)
    val = lo + left * bin_w
    vah = lo + (right + 1) * bin_w

    details: list[str] = []
    span = max(vah - val, 1e-9)
    # 1% buffer around the value-area edges: the edges are estimates, so a
    # price a fraction of a percent outside them must not flip the regime.
    buffer = 0.01 * price if price > 0 else 0.0
    if price < val - buffer:
        price_position = "below_val"
        score = 20.0
        details.append(f"Price below VAL ({val:.2f}): discount vs value area")
    elif price > vah + buffer:
        price_position = "above_vah"
        score = 80.0
        details.append(f"Price above VAH ({vah:.2f}): extended vs value area")
    else:
        price_position = "inside_va"
        score = 35.0 + 30.0 * (price - val) / span
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f})")
    details.append(f"POC ${poc_price:.2f}")

    # Sitting on the POC is the definition of balance.
    if price_position == "inside_va" and poc_price > 0 and abs(price - poc_price) / poc_price < 0.02:
        score = 0.5 * score + 0.5 * 50.0
        details.append("Near POC: balanced")

    # Quantise to a 5-point grid: the profile is a coarse regime indicator, and
    # a stable score avoids flip-flopping on a few marginal bars.
    score = int(max(0, min(100, 5 * round(score / 5.0))))
    return {
        "poc_price": round(poc_price, 2),
        "val": round(val, 2),
        "vah": round(vah, 2),
        "price": round(price, 2),
        "price_position": price_position,
        "score": score,
        "detail": " | ".join(details),
    }



def compute_volume_profile(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute Volume Profile score (0-100).

    Calculates POC, VAH/VAL from 1-year daily data using 20-bin profile.
    Evaluates price position relative to VA and POC, volume ratio, and profile shape.
    """
    profile = _build_profile(hist)
    return profile["score"], profile["detail"]


def get_profile_levels(hist: pd.DataFrame) -> dict[str, Any]:
    """Return POC, VAL, VAH, value area range and price position.

    Returns:
        {
            "poc_price": float,
            "val": float,
            "vah": float,
            "price_position": "below_val" | "inside_va" | "above_vah",
            "score": int,
            "detail": str,
        }
    """
    profile = _build_profile(hist)
    return {
        "poc_price": profile["poc_price"],
        "val": profile["val"],
        "vah": profile["vah"],
        "price": profile["price"],
        "price_position": profile["price_position"],
        "score": profile["score"],
        "detail": profile["detail"],
    }
