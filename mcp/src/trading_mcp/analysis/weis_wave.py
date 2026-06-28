"""Weis Wave and Shortening of the Thrust (SOT) analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_sot_weis_wave(hist: pd.DataFrame) -> tuple[int, str]:
    """Shortening of the Thrust + Weis Wave + Crabel contraction analysis.

    SOT: 3+ impulse waves with diminishing progress = exhaustion.
    Weis Wave: cumulative volume waves detect shortening.
    Crabel: NR7, ID/NR4 patterns for entry timing.
    """
    if hist.empty or len(hist) < 60:
        return 50, "Insufficient data for SOT/Weis"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    volume = hist["Volume"].values

    impulses: list[dict] = []
    i = 0
    while i < len(close) - 5:
        if close[i + 1] > close[i]:
            start = i
            peak_idx = i
            for j in range(i + 1, min(i + 20, len(close))):
                if close[j] > close[peak_idx]:
                    peak_idx = j
                elif close[j] < close[peak_idx] * 0.97:
                    break
            impulse_len = peak_idx - start
            impulse_gain = (close[peak_idx] - close[start]) / close[start] if close[start] > 0 else 0
            if impulse_gain > 0.03 and impulse_len >= 2:
                impulses.append({"start": start, "peak": peak_idx, "gain": impulse_gain, "len": impulse_len})
            i = peak_idx + 1
        else:
            i += 1

    if len(impulses) >= 3:
        last3 = impulses[-3:]
        gains = [imp["gain"] for imp in last3]
        if gains[0] > gains[1] > gains[2] and gains[2] < gains[0] * 0.5:
            score += 25
            details.append(f"SOT detected: gains {[f'{g:.1%}' for g in gains]} (exhaustion +25)")
        elif gains[0] > gains[1] > gains[2]:
            score += 10
            details.append(f"Mild SOT: gains {[f'{g:.1%}' for g in gains]} (+10)")

    cum_vol = 0.0
    wave_vols: list[float] = []
    wave_start = 0
    for i in range(1, len(close)):
        cum_vol += float(volume[i])
        if i == len(close) - 1:
            if i - wave_start >= 3:
                wave_vols.append(cum_vol)
            break
    if len(wave_vols) >= 3:
        last3_vol = wave_vols[-3:]
        if last3_vol[0] > last3_vol[1] > last3_vol[2]:
            score += 15
            details.append("Weis Wave shortening: vols declining (+15)")

    if len(close) >= 7:
        ranges = [float(high[i]) - float(low[i]) for i in range(len(close))]
        last7_ranges = ranges[-7:]
        current_range = last7_ranges[-1]
        if current_range < min(last7_ranges[:-1]):
            score += 10
            details.append("NR7 (Crabel contraction) (+10)")

    if len(close) >= 4:
        last4_ranges = [float(high[i]) - float(low[i]) for i in range(-4, 0)]
        id_nr4 = False
        for k in range(1, len(last4_ranges)):
            if last4_ranges[k] < last4_ranges[k - 1] * 0.7:
                id_nr4 = True
                break
        if id_nr4:
            score += 5
            details.append("ID/NR4 contraction (+5)")

    return min(100, max(0, score)), " | ".join(details)
