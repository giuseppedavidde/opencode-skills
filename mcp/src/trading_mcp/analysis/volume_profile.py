"""Volume Profile analysis: POC, Value Area, profile shape classification."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _build_profile(hist: pd.DataFrame) -> dict[str, Any]:
    """Core volume profile calculation.

    Returns a dict with poc_price, val, vah, price, price_position,
    score, and detail. Used by both compute_volume_profile and get_profile_levels.
    """
    if hist.empty or len(hist) < 20:
        return {
            "poc_price": 0.0,
            "val": 0.0,
            "vah": 0.0,
            "price": 0.0,
            "price_position": "inside_va",
            "score": 10,
            "detail": "Insufficient data",
        }

    score = 10
    details: list[str] = []
    price = float(hist["Close"].dropna().iloc[-1]) if not hist["Close"].dropna().empty else 0.0
    hist_range = float(hist["High"].max()) - float(hist["Low"].min())
    n_bins = 20
    bin_w = hist_range / n_bins if hist_range > 0 else 1
    hist_copy = hist.dropna(subset=["Close"]).copy()
    if hist_copy.empty:
        return {
            "poc_price": 0.0,
            "val": 0.0,
            "vah": 0.0,
            "price": price,
            "price_position": "inside_va",
            "score": 10,
            "detail": "No valid price data",
        }
    hist_copy["bin"] = ((hist_copy["Close"] - hist_copy["Low"].min()) / bin_w).astype(int).clip(0, n_bins - 1)
    vol_by_bin = hist_copy.groupby("bin")["Volume"].sum()
    if vol_by_bin.empty:
        return {
            "poc_price": 0.0,
            "val": 0.0,
            "vah": 0.0,
            "price": price,
            "price_position": "inside_va",
            "score": 10,
            "detail": "No volume data",
        }

    poc_bin = int(vol_by_bin.idxmax())
    poc_price = float(hist_copy["Low"].min()) + (poc_bin + 0.5) * bin_w
    total_vol = int(vol_by_bin.sum())
    cum = 0
    va_bins: list[int] = []
    for b_val, v_val in vol_by_bin.sort_values(ascending=False).items():
        cum += int(v_val)
        va_bins.append(int(b_val))
        if cum / total_vol >= 0.7:
            break
    val = float(hist_copy["Low"].min()) + min(va_bins) * bin_w
    vah = float(hist_copy["Low"].min()) + (max(va_bins) + 1) * bin_w

    price_position: str
    if val <= price <= vah:
        score += 20
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f}) (+20)")
        price_position = "inside_va"
    elif price < val:
        score += 25
        details.append(f"Price below VAL ({val:.2f}) (+25)")
        price_position = "below_val"
    else:
        score += 15
        details.append(f"Price above VAH ({vah:.2f}) (+15)")
        price_position = "above_vah"

    if poc_price > 0 and abs(price - poc_price) / poc_price < 0.05:
        score += 10
        details.append(f"Near VPOC ${poc_price:.2f} (+10)")

    if len(hist) >= 21:
        vol_ratio = float(hist["Volume"].iloc[-1]) / float(hist["Volume"].iloc[-21:].mean())
        if vol_ratio > 2.0:
            score += 15
            details.append(f"Volume ratio {vol_ratio:.1f}x (+15)")
        elif vol_ratio > 1.0:
            score += 10
            details.append(f"Volume ratio {vol_ratio:.1f}x (+10)")

    pos_in_range = ((price - float(hist_copy["Low"].min())) / hist_range) * 100 if hist_range > 0 else 50
    if 40 < pos_in_range < 60:
        score += 15
        details.append("D-Profile shape (balanced) (+15)")

    return {
        "poc_price": round(poc_price, 2),
        "val": round(val, 2),
        "vah": round(vah, 2),
        "price": round(price, 2),
        "price_position": price_position,
        "score": min(score, 100),
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
