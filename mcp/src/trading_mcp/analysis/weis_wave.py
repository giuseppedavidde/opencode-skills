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

    # Zig-zag legs: every reversal of >=3% starts a new leg. The leg volume is
    # the cumulative volume traded inside that leg, which is what a Weis wave
    # measures. Both directions are tracked so SOT can be scored with the
    # correct sign: exhaustion of up-legs is distribution (bearish), while
    # exhaustion of down-legs is accumulation (bullish).
    legs = _zigzag_legs(close, volume, threshold=0.03)

    up_legs = [leg for leg in legs if leg["direction"] == "up"]
    down_legs = [leg for leg in legs if leg["direction"] == "down"]

    if len(up_legs) >= 3:
        last3 = up_legs[-3:]
        gains = [leg["gain"] for leg in last3]
        if gains[0] > gains[1] > gains[2] and gains[2] < gains[0] * 0.5:
            score -= 25
            details.append(
                f"SOT on up-legs: gains {[f'{g:.1%}' for g in gains]} "
                f"(buyer exhaustion, bearish -25)"
            )
        elif gains[0] > gains[1] > gains[2] and gains[2] < gains[0] * 0.9:
            score -= 10
            details.append(f"Mild SOT on up-legs: gains {[f'{g:.1%}' for g in gains]} (-10)")

    if len(down_legs) >= 3:
        last3_down = down_legs[-3:]
        drops = [abs(leg["gain"]) for leg in last3_down]
        if drops[0] > drops[1] > drops[2] and drops[2] < drops[0] * 0.5:
            score += 25
            details.append(
                f"SOT on down-legs: drops {[f'{g:.1%}' for g in drops]} "
                f"(seller exhaustion, bullish +25)"
            )
        elif drops[0] > drops[1] > drops[2] and drops[2] < drops[0] * 0.9:
            score += 10
            details.append(f"Mild SOT on down-legs: drops {[f'{g:.1%}' for g in drops]} (+10)")

    # Weis wave shortening: volume contracting on three consecutive legs of
    # the same direction means the current move has no participation.
    if len(up_legs) >= 3:
        vols = [leg["volume"] for leg in up_legs[-3:]]
        if vols[0] > vols[1] > vols[2] and vols[2] < vols[0] * 0.9:
            score -= 10
            details.append("Weis wave shortening on up-legs: volume declining (-10)")
    if len(down_legs) >= 3:
        vols = [leg["volume"] for leg in down_legs[-3:]]
        if vols[0] > vols[1] > vols[2] and vols[2] < vols[0] * 0.9:
            score += 10
            details.append("Weis wave shortening on down-legs: selling drying up (+10)")

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


def _zigzag_legs(
    close: "np.ndarray", volume: "np.ndarray", threshold: float = 0.03
) -> list[dict]:
    """Split the price path into alternating legs at ``threshold`` reversals.

    Returns one dict per leg with ``direction`` (``up``/``down``), ``gain``
    (signed fractional move), ``volume`` (sum of traded volume inside the leg)
    and ``start``/``end`` bar indexes. Legs shorter than two bars are dropped
    because a single-bar wiggle is noise, not a wave.
    """
    if len(close) < 3:
        return []

    legs: list[dict] = []
    direction = "up" if close[1] >= close[0] else "down"
    start = 0
    extreme = float(close[0])
    extreme_idx = 0

    for i in range(1, len(close)):
        price = float(close[i])
        if direction == "up":
            if price > extreme:
                extreme = price
                extreme_idx = i
            elif price <= extreme * (1.0 - threshold):
                legs.append(_make_leg(direction, close, volume, start, extreme_idx))
                direction = "down"
                start = extreme_idx
                extreme = price
                extreme_idx = i
        else:
            if price < extreme:
                extreme = price
                extreme_idx = i
            elif price >= extreme * (1.0 + threshold):
                legs.append(_make_leg(direction, close, volume, start, extreme_idx))
                direction = "up"
                start = extreme_idx
                extreme = price
                extreme_idx = i

    legs.append(_make_leg(direction, close, volume, start, len(close) - 1))
    return [leg for leg in legs if leg["end"] - leg["start"] >= 2]


def _make_leg(
    direction: str, close: "np.ndarray", volume: "np.ndarray", start: int, end: int
) -> dict:
    """Build one leg record from its bar range."""
    base = float(close[start]) if float(close[start]) != 0.0 else 1.0
    gain = (float(close[end]) - base) / base
    traded = float(np.sum(volume[start:end + 1])) if end >= start else 0.0
    return {
        "direction": direction,
        "start": int(start),
        "end": int(end),
        "gain": float(gain),
        "volume": traded,
    }
