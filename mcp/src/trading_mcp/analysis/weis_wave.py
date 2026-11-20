"""Weis Wave and Shortening of the Thrust on CONFIRMED legs (SIG-14; 0-100, 50 = neutral).

- Legs come from a close-only zigzag. The reversal threshold scales with
  volatility: 3 x Wilder ATR(14) / close, bounded to [1.5%, 15%] (the old
  fixed 3% fired on noise for volatile names and never for quiet ones).
- Only confirmed legs are scored: the last leg is still open (its end can
  move with the next bars), so it is dropped. The scored legs therefore do
  not repaint when new bars arrive.
- SOT: three consecutive up legs with shrinking gains score -25 (strong:
  last gain < half of the first) or -10; three shrinking down legs mirror
  it (+25 / +10). Weis shortening: three up legs with falling volume -10,
  three down legs with falling volume +10.
- NR7 and ID/NR4 contractions carry no direction: they are reported, not scored.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_mcp.analysis.ta_core import atr_last

MIN_THRESHOLD = 0.015
MAX_THRESHOLD = 0.15
ATR_MULTIPLE = 3.0


def reversal_threshold(hist: pd.DataFrame) -> float:
    """Zigzag reversal threshold: 3 ATR as a fraction of the close, bounded."""
    atr = atr_last(hist)
    close = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0
    if atr is None or close <= 0:
        return 0.03
    return float(min(MAX_THRESHOLD, max(MIN_THRESHOLD, ATR_MULTIPLE * atr / close)))


def compute_sot_weis_wave(hist: pd.DataFrame) -> tuple[int, str]:
    """SOT and Weis-wave score on confirmed zigzag legs (see the module docstring)."""
    if hist.empty or len(hist) < 60:
        return 50, "Insufficient data for SOT/Weis"

    score = 50
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    threshold = reversal_threshold(hist)
    legs = _zigzag_legs(close, volume, threshold=threshold, confirmed_only=True)
    details = [f"{len(legs)} confirmed legs (reversal {threshold:.1%})"]

    up_legs = [leg for leg in legs if leg["direction"] == "up"]
    down_legs = [leg for leg in legs if leg["direction"] == "down"]

    if len(up_legs) >= 3:
        gains = [leg["gain"] for leg in up_legs[-3:]]
        if gains[0] > gains[1] > gains[2]:
            points = 25 if gains[2] < gains[0] * 0.5 else 10 if gains[2] < gains[0] * 0.9 else 0
            if points:
                score -= points
                details.append(f"SOT on up-legs: gains {[f'{g:.1%}' for g in gains]} (buyer exhaustion -{points})")
    if len(down_legs) >= 3:
        drops = [abs(leg["gain"]) for leg in down_legs[-3:]]
        if drops[0] > drops[1] > drops[2]:
            points = 25 if drops[2] < drops[0] * 0.5 else 10 if drops[2] < drops[0] * 0.9 else 0
            if points:
                score += points
                details.append(f"SOT on down-legs: drops {[f'{g:.1%}' for g in drops]} (seller exhaustion +{points})")

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

    ranges = high - low
    if len(ranges) >= 7 and ranges[-1] < ranges[-7:-1].min():
        details.append("NR7 contraction (direction-neutral, not scored)")
    if len(ranges) >= 4 and any(ranges[k] < ranges[k - 1] * 0.7 for k in range(-3, 0)):
        details.append("ID/NR4 contraction (direction-neutral, not scored)")

    return min(100, max(0, score)), " | ".join(details)


def _zigzag_legs(
    close: "np.ndarray", volume: "np.ndarray", threshold: float = 0.03, confirmed_only: bool = True
) -> list[dict]:
    """Split the close path into alternating legs at ``threshold`` reversals.

    Returns one dict per leg with ``direction`` (``up``/``down``), ``gain``
    (signed fractional move), ``volume`` (traded inside the leg), ``start``/``end``
    bar indexes and ``confirmed_at`` (the bar that confirmed the reversal).
    The open last leg is dropped when ``confirmed_only``. Legs shorter than
    two bars are dropped (a single-bar wiggle is noise, not a wave).
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
                extreme, extreme_idx = price, i
            elif price <= extreme * (1.0 - threshold):
                legs.append(_make_leg(direction, close, volume, start, extreme_idx, confirmed_at=i))
                direction, start, extreme, extreme_idx = "down", extreme_idx, price, i
        else:
            if price < extreme:
                extreme, extreme_idx = price, i
            elif price >= extreme * (1.0 + threshold):
                legs.append(_make_leg(direction, close, volume, start, extreme_idx, confirmed_at=i))
                direction, start, extreme, extreme_idx = "up", extreme_idx, price, i

    if not confirmed_only:
        legs.append(_make_leg(direction, close, volume, start, len(close) - 1, confirmed_at=None))
    return [leg for leg in legs if leg["end"] - leg["start"] >= 2]


def _make_leg(
    direction: str, close: "np.ndarray", volume: "np.ndarray", start: int, end: int,
    confirmed_at: int | None = None,
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
        "confirmed_at": confirmed_at,
    }
