"""Score-to-signal translation.

A single hourly function that maps a numeric 0-100 score into a discrete
direction label ({strong_long, long, neutral, short, strong_short}) and a
strength scalar. The thresholds are symmetric around 50.
"""

from __future__ import annotations

from typing import Optional

DIRECTIONS = ("strong_short", "short", "neutral", "long", "strong_long")
_STRENGTH_MAP = {
    "strong_short": 1.0,
    "short": 0.6,
    "neutral": 0.0,
    "long": 0.6,
    "strong_long": 1.0,
}


def generate_signal(
    score: float,
    threshold: float = 55.0,
    confidence: Optional[float] = None,
) -> dict:
    """Convert a numeric score into a trading signal dictionary.

    Parameters
    ----------
    score:
        Score in the [0, 100] range.
    threshold:
        Symmetric cut-off around 50; defaults to ``55``.
    confidence:
        Optional confidence in [0, 1]. Forwarded through untouched.

    Returns
    -------
    dict
        Keys: ``direction``, ``strength``, ``score``, ``confidence``.
    """
    if score is None or not isinstance(score, (int, float)):
        return {
            "direction": "neutral",
            "strength": 0.0,
            "score": float("nan") if score is None else score,
            "confidence": confidence,
        }

    upper_long = threshold
    upper_strong = threshold + 15.0
    lower_short = 100.0 - threshold
    lower_strong = 100.0 - threshold - 15.0

    if score >= upper_strong:
        direction = "strong_long"
    elif score >= upper_long:
        direction = "long"
    elif score <= lower_strong:
        direction = "strong_short"
    elif score <= lower_short:
        direction = "short"
    else:
        direction = "neutral"

    return {
        "direction": direction,
        "strength": _STRENGTH_MAP[direction],
        "score": float(score),
        "confidence": confidence,
    }