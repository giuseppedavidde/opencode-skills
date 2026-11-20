"""Wyckoff phase evidence on swing structure, and a deduplicated clue test (SIG-16).

Both scores are on one 0-100 scale (50 = neutral) with mirrored rules, so a
driftless random walk has no bullish drift. None of the rules has an
out-of-sample test: the labels ("Spring", "Upthrust") are descriptions of a
price pattern, not evidence of an edge.

Definitions:

- Swing points: confirmed pivots with 5 bars on each side
  (:func:`trading_mcp.analysis.ta_core.swing_pivots`), so they never repaint.
- Trading range: support = lowest confirmed swing low and resistance =
  highest confirmed swing high of the last 90 bars, excluding the last 10.
- Background trend: the total return of the 120 bars before that range
  (below -10% = decline, above +10% = advance).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trading_mcp.analysis.ta_core import atr_last, swing_pivots

_PIVOT_ORDER = 5
_RANGE_BARS = 90
_EVENT_BARS = 10
_BACKGROUND_BARS = 120
_BACKGROUND_MOVE = 0.10


def _background(close: np.ndarray) -> tuple[str, float | None]:
    """``decline``, ``advance`` or ``flat`` for the bars before the range window."""
    end = len(close) - _RANGE_BARS
    start = end - _BACKGROUND_BARS
    if start < 0 or close[start] <= 0:
        return "unknown", None
    move = float(close[end] / close[start] - 1.0)
    if move < -_BACKGROUND_MOVE:
        return "decline", move
    if move > _BACKGROUND_MOVE:
        return "advance", move
    return "flat", move


def compute_wyckoff(hist: pd.DataFrame, info: dict[str, Any] | None = None) -> tuple[int, str]:
    """Wyckoff structure score (0-100, 50 = neutral).

    Rules (mirror pairs, documented, unvalidated):

    - Spring: in the last 10 bars a low below range support by at most
      1.5 ATR, and the last close back above support: +20 (+10 more after a
      background decline). Upthrust mirrors it at resistance: -20 (-10 more
      after an advance).
    - Swing structure: last two confirmed swing highs AND lows higher (HH/HL,
      markup) +15; both lower (LH/LL, markdown) -15.
    - Range position: bottom quarter of the range after a decline +10
      (accumulation zone); top quarter after an advance -10 (distribution zone).

    Args:
        hist: Complete daily bars (at least 60).
        info: Unused (kept for the call signature).
    """
    del info
    if hist.empty or len(hist) < 60:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    atr = atr_last(hist) or 0.0
    score = 50.0
    details: list[str] = []
    background, move = _background(close)
    details.append(f"Background {background}" + (f" ({move:+.0%})" if move is not None else ""))

    n = len(close)
    window_start = max(0, n - _RANGE_BARS)
    piv_highs, piv_lows = swing_pivots(high, low, _PIVOT_ORDER)
    range_highs = [p for i, p in piv_highs if window_start <= i < n - _EVENT_BARS]
    range_lows = [p for i, p in piv_lows if window_start <= i < n - _EVENT_BARS]
    phase = "range"
    if range_highs and range_lows and atr > 0:
        support, resistance = min(range_lows), max(range_highs)
        recent_low = float(low[-_EVENT_BARS:].min())
        recent_high = float(high[-_EVENT_BARS:].max())
        last = float(close[-1])
        if support - 1.5 * atr <= recent_low < support and last > support:
            points = 30 if background == "decline" else 20
            score += points
            phase = "accumulation"
            details.append(f"Spring detected: low {recent_low:.2f} under support {support:.2f}, close back above (+{points})")
        elif resistance < recent_high <= resistance + 1.5 * atr and last < resistance:
            points = 30 if background == "advance" else 20
            score -= points
            phase = "distribution"
            details.append(f"Upthrust: high {recent_high:.2f} over resistance {resistance:.2f}, close back below (-{points})")
        if resistance > support:
            pos = (last - support) / (resistance - support)
            if pos < 0.25 and background == "decline":
                score += 10
                details.append(f"Bottom quarter of the range after a decline ({pos:.0%}, +10)")
            elif pos > 0.75 and background == "advance":
                score -= 10
                details.append(f"Top quarter of the range after an advance ({pos:.0%}, -10)")
    if len(piv_highs) >= 2 and len(piv_lows) >= 2:
        hh = piv_highs[-1][1] > piv_highs[-2][1]
        hl = piv_lows[-1][1] > piv_lows[-2][1]
        if hh and hl:
            score += 15
            phase = "markup" if phase == "range" else phase
            details.append("HH/HL swing structure (markup +15)")
        elif not hh and not hl:
            score -= 15
            phase = "markdown" if phase == "range" else phase
            details.append("LH/LL swing structure (markdown -15)")
    details.append(f"Phase: {phase}")
    return int(round(min(100.0, max(0.0, score)))), " | ".join(details)


def compute_6clue_test(hist: pd.DataFrame, info: dict[str, Any] | None = None) -> tuple[int, str]:
    """Wyckoff clue test (0-100, 50 = neutral), without the clues that other dimensions score.

    Clues kept (each bullish or bearish): 1. testing support (close 5-15%
    above the 60-bar low) vs testing resistance (5-15% below the 60-bar
    high); 2. up-bar volume vs down-bar volume over 60 bars (ratio > 1.2);
    3. effort vs result over 30 bars (rising volume on falling price =
    absorption, bullish; falling volume on rising price = no demand,
    bearish); 6. range narrowing (60 vs 120 bars) after a decline (bullish)
    or after an advance (bearish). Clue 4 (analyst target) is scored in
    Fundamentals and clue 5 (HH/HL) in Market Structure, so they are not
    counted here. Net clues +-4 give +-30, +-2..3 give +-15.

    Args:
        hist: Complete daily bars (at least 90).
        info: Unused (kept for the call signature).
    """
    del info
    if hist.empty or len(hist) < 90:
        return 50, "Insufficient data for the clue test"
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    bull = bear = 0
    details: list[str] = []

    current = float(close[-1])
    low_60, high_60 = float(np.min(low[-60:])), float(np.max(high[-60:]))
    if low_60 * 1.05 < current < low_60 * 1.15:
        bull += 1
        details.append("Clue 1: testing support")
    if high_60 * 0.85 < current < high_60 * 0.95:
        bear += 1
        details.append("Clue 1: testing resistance")

    changes = np.diff(close[-61:])
    up_vol = float(volume[-60:][changes > 0].sum())
    down_vol = float(volume[-60:][changes < 0].sum())
    if up_vol > down_vol * 1.2:
        bull += 1
        details.append(f"Clue 2: up volume {up_vol / max(down_vol, 1.0):.2f}x down volume")
    elif down_vol > up_vol * 1.2:
        bear += 1
        details.append(f"Clue 2: down volume {down_vol / max(up_vol, 1.0):.2f}x up volume")

    vol_first, vol_second = float(np.mean(volume[-30:-15])), float(np.mean(volume[-15:]))
    price_first, price_second = float(np.mean(close[-30:-15])), float(np.mean(close[-15:]))
    vol_trend = vol_second / vol_first if vol_first > 0 else 1.0
    price_trend = price_second / price_first if price_first > 0 else 1.0
    if vol_trend > 1.15 and price_trend < 1.0:
        bull += 1
        details.append("Clue 3: rising volume on falling price (absorption)")
    elif vol_trend < 0.85 and price_trend > 1.0:
        bear += 1
        details.append("Clue 3: falling volume on rising price (no demand)")

    if len(close) >= 120:
        range_120 = float(np.max(high[-120:]) - np.min(low[-120:]))
        range_60 = float(np.max(high[-60:]) - np.min(low[-60:]))
        prior_move = float(close[-60] / close[-120] - 1.0) if close[-120] > 0 else 0.0
        if range_120 > 0 and range_60 < range_120 * 0.6:
            if prior_move < -_BACKGROUND_MOVE:
                bull += 1
                details.append("Clue 6: range narrowing after a decline (accumulation)")
            elif prior_move > _BACKGROUND_MOVE:
                bear += 1
                details.append("Clue 6: range narrowing after an advance (distribution)")

    net = bull - bear
    if net >= 4:
        score, label = 80, "STRONG ACCUMULATION (+30)"
    elif net >= 2:
        score, label = 65, "Mild accumulation (+15)"
    elif net <= -4:
        score, label = 20, "STRONG DISTRIBUTION (-30)"
    elif net <= -2:
        score, label = 35, "Mild distribution (-15)"
    else:
        score, label = 50, "Neutral (+0)"
    details.append(f"Clue test: {bull}B/{bear}S = {label}")
    return score, " | ".join(details)
