"""Volume Profile analysis: POC, Value Area, profile shape classification."""

from __future__ import annotations

import pandas as pd


def compute_volume_profile(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute Volume Profile score (0-100).

    Calculates POC, VAH/VAL from 1-year daily data using 20-bin profile.
    Evaluates price position relative to VA and POC, volume ratio, and profile shape.
    """
    if hist.empty or len(hist) < 20:
        return 10, "Insufficient data"

    score = 10
    details = []
    price = float(hist["Close"].dropna().iloc[-1]) if not hist["Close"].dropna().empty else 0.0
    hist_range = float(hist["High"].max()) - float(hist["Low"].min())
    n_bins = 20
    bin_w = hist_range / n_bins if hist_range > 0 else 1
    hist_copy = hist.dropna(subset=["Close"]).copy()
    if hist_copy.empty:
        return 10, "No valid price data"
    hist_copy["bin"] = ((hist_copy["Close"] - hist_copy["Low"].min()) / bin_w).astype(int).clip(0, n_bins - 1)
    vol_by_bin = hist_copy.groupby("bin")["Volume"].sum()
    if vol_by_bin.empty:
        return 10, "No volume data"

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

    if val <= price <= vah:
        score += 20
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f}) (+20)")
    elif price < val:
        score += 25
        details.append(f"Price below VAL ({val:.2f}) (+25)")
    else:
        score += 15
        details.append(f"Price above VAH ({vah:.2f}) (+15)")

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

    return min(score, 100), " | ".join(details)
