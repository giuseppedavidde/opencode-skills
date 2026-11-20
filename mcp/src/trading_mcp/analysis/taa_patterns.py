"""TAA Pattern Detectors — Head & Shoulders, Flags/Pennants, Harmonic, S/R.

Adapted from TechnicalAnalysisAutomation pattern detection for daily OHLCV data.
Each detector follows the pattern: detect_*(hist) -> dict, compute_*(hist) -> tuple[int, str].

Scoring rules (SIG-13, SIG-14; 0-100, 50 = neutral, mirrored, unvalidated):

- Only RECENT patterns count: an H&S/IHS whose neckline break is within the
  last 5 bars, a flag/pennant whose breakout is within the last 10 bars, a
  harmonic whose D point is within the last 10 bars. A pattern from months
  ago does not move today's score.
- Harmonic ratios must match within a log-space RMS error of 0.10 (the old
  0.5 matched about 35 patterns a year on random walks).
- Flags and pennants use two trend lines (through the chunk highs and the
  chunk lows of the consolidation): converging lines are a pennant, parallel
  counter-trend lines are a flag.
- The KDE support/resistance block is reported but NOT scored here: the
  swing-cluster S/R indicator already scores support/resistance.
- ATR is Wilder's (:mod:`trading_mcp.analysis.ta_core`).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.stats import gaussian_kde

from trading_mcp.analysis.ta_core import wilder_atr

logger = logging.getLogger(__name__)

HS_RECENT_BARS = 5
FLAG_RECENT_BARS = 10
HARMONIC_RECENT_BARS = 10
HARMONIC_ERR_THRESH = 0.10

# ---------------------------------------------------------------------------
# Helper functions (inline, no external deps beyond numpy/pandas/scipy)
# ---------------------------------------------------------------------------


def _rw_extremes(
    data: np.ndarray, order: int
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Find rolling window tops and bottoms.

    A top is a point that is higher than ``order`` points to its left and right.
    A bottom is a point that is lower than ``order`` points to its left and right.
    """
    tops: list[tuple[int, float]] = []
    bottoms: list[tuple[int, float]] = []
    for i in range(order, len(data) - order):
        v = data[i]
        left = data[i - order : i]
        right = data[i + 1 : i + order + 1]
        if np.all(left < v) and np.all(right < v):
            tops.append((i, float(v)))
        if np.all(left > v) and np.all(right > v):
            bottoms.append((i, float(v)))
    return tops, bottoms


def _directional_change(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    sigma: float,
) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    """ATR-free directional change: zigzag turns when price retraces ``sigma`` %.

    Returns:
        tops: list of (bar_index, extreme_index, price) for swing highs.
        bottoms: list of (bar_index, extreme_index, price) for swing lows.
    """
    tops: list[tuple[int, int, float]] = []
    bottoms: list[tuple[int, int, float]] = []
    up_zig = True
    tmp_max = float(high[0])
    tmp_min = float(low[0])
    tmp_max_i = 0
    tmp_min_i = 0

    for i in range(len(close)):
        if up_zig:
            if high[i] > tmp_max:
                tmp_max = float(high[i])
                tmp_max_i = i
            elif close[i] < tmp_max * (1.0 - sigma):
                tops.append((i, tmp_max_i, tmp_max))
                up_zig = False
                tmp_min = float(low[i])
                tmp_min_i = i
        else:
            if low[i] < tmp_min:
                tmp_min = float(low[i])
                tmp_min_i = i
            elif close[i] > tmp_min * (1.0 + sigma):
                bottoms.append((i, tmp_min_i, tmp_min))
                up_zig = True
                tmp_max = float(high[i])
                tmp_max_i = i
    return tops, bottoms


def _fit_trendline(
    data: np.ndarray,
) -> tuple[np.ndarray, int, int]:
    """Fit a simple linear trendline via numpy polyfit.

    Returns:
        (coefs, upper_pivot, lower_pivot) where coefs = [slope, intercept].
    """
    x = np.arange(len(data), dtype=float)
    coefs = np.polyfit(x, data, 1)
    line = coefs[0] * x + coefs[1]
    diffs = data - line
    upper_pivot = int(np.argmax(diffs))
    lower_pivot = int(np.argmin(diffs))
    return coefs, upper_pivot, lower_pivot


def _flag_lines(data: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Upper and lower trend lines of a consolidation: fits through chunk highs and chunk lows."""
    n = len(data)
    chunk = max(2, n // 4)
    hi_x: list[int] = []
    hi_y: list[float] = []
    lo_x: list[int] = []
    lo_y: list[float] = []
    for start in range(0, n, chunk):
        seg = data[start:start + chunk]
        if len(seg) == 0:
            continue
        hi_x.append(start + int(np.argmax(seg)))
        hi_y.append(float(np.max(seg)))
        lo_x.append(start + int(np.argmin(seg)))
        lo_y.append(float(np.min(seg)))
    if len(set(hi_x)) < 2 or len(set(lo_x)) < 2:
        return None
    upper = np.polyfit(hi_x, hi_y, 1)
    lower = np.polyfit(lo_x, lo_y, 1)
    return (float(upper[0]), float(upper[1])), (float(lower[0]), float(lower[1]))


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute R² (coefficient of determination)."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return float(1.0 - ss_res / ss_tot)


# ---------------------------------------------------------------------------
# Pattern A: Head & Shoulders
# ---------------------------------------------------------------------------


def detect_head_shoulders(hist: pd.DataFrame, order: int = 5) -> dict[str, Any]:
    """Detect Head & Shoulders and Inverse H&S patterns.

    Uses rolling-window extremes on Close prices, then validates via
    symmetry, neckline, and breakout rules identical to the original
    head_shoulders.py algorithm.

    Args:
        hist: Daily OHLCV DataFrame (Open, High, Low, Close, Volume).
        order: Rolling window order for extreme detection (default 5).

    Returns:
        Dict with ``hs_patterns``, ``ihs_patterns``, ``count``, ``recent``.
    """
    result: dict[str, Any] = {
        "hs_patterns": [],
        "ihs_patterns": [],
        "count": 0,
        "recent": False,
        "recent_hs": 0,
        "recent_ihs": 0,
    }

    if len(hist) < order * 4 + 10:
        return result

    close = hist["Close"].values.astype(float)
    log_close = np.log(close)

    tops, bottoms = _rw_extremes(log_close, order)

    # Build merged sorted list of all extremes with their types
    merged: list[dict] = []
    for idx, val in tops:
        merged.append({"index": int(idx), "price": float(val), "is_top": True})
    for idx, val in bottoms:
        merged.append({"index": int(idx), "price": float(val), "is_top": False})
    merged.sort(key=lambda x: x["index"])

    if len(merged) < 5:
        return result

    hs_list: list[dict] = []
    ihs_list: list[dict] = []

    for i in range(len(merged) - 5):
        window = merged[i : i + 6]
        _check_hs_pattern(
            window, log_close, hs_list, ihs_list, len(hist)
        )

    for p in hs_list:
        p["head_price"] = round(float(np.exp(p["head_price"])), 2)
        p["neckline_start"] = round(float(np.exp(p["neckline_start"])), 2)
        p["neckline_end"] = round(float(np.exp(p["neckline_end"])), 2)
        p["breakout_price"] = round(float(np.exp(p["breakout_price"])), 2)
        p["target"] = round(float(np.exp(p["target"])), 2) if p.get("target") else None
        p["stop"] = round(float(np.exp(p["stop"])), 2) if p.get("stop") else None

    for p in ihs_list:
        p["head_price"] = round(float(np.exp(p["head_price"])), 2)
        p["neckline_start"] = round(float(np.exp(p["neckline_start"])), 2)
        p["neckline_end"] = round(float(np.exp(p["neckline_end"])), 2)
        p["breakout_price"] = round(float(np.exp(p["breakout_price"])), 2)
        p["target"] = round(float(np.exp(p["target"])), 2) if p.get("target") else None
        p["stop"] = round(float(np.exp(p["stop"])), 2) if p.get("stop") else None

    n_bars = len(hist)

    def _recent(p: dict) -> bool:
        bi = p.get("breakout_index", 0)
        return bi > 0 and n_bars - 1 - bi < HS_RECENT_BARS

    result["hs_patterns"] = hs_list
    result["ihs_patterns"] = ihs_list
    result["count"] = len(hs_list) + len(ihs_list)
    result["recent_hs"] = sum(1 for p in hs_list if _recent(p))
    result["recent_ihs"] = sum(1 for p in ihs_list if _recent(p))
    result["recent"] = bool(result["recent_hs"] or result["recent_ihs"])

    return result


def _check_hs_pattern(
    window: list[dict],
    log_close: np.ndarray,
    hs_out: list[dict],
    ihs_out: list[dict],
    n_bars: int,
) -> None:
    """Check a 5-extreme window for H&S or IHS patterns.

    Window layout for bearish H&S:
      extremes[0] = left_shoulder (top)
      extremes[1] = trough_1    (bottom)
      extremes[2] = head        (top)
      extremes[3] = trough_2    (bottom)
      extremes[4] = right_shoulder (top)

    For bullish IHS the pattern is inverted.
    """
    if len(window) != 6:
        return

    # Check alternation: top-bottom-top-bottom-top
    is_hs_candidate = all(
        window[j]["is_top"] == (j % 2 == 0) for j in range(5)
    )
    is_ihs_candidate = all(
        window[j]["is_top"] == (j % 2 == 1) for j in range(5)
    )

    if is_hs_candidate:
        _validate_hs(window, log_close, hs_out, "bearish", n_bars)
    elif is_ihs_candidate:
        _validate_hs(window, log_close, ihs_out, "bullish", n_bars)


def _validate_hs(
    window: list[dict],
    log_close: np.ndarray,
    out_list: list[dict],
    pattern_type: str,
    n_bars: int,
) -> None:
    """Validate a candidate H&S / IHS pattern."""
    ls = window[0]
    t1 = window[1]
    hd = window[2]
    t2 = window[3]
    rs = window[4]

    head_price = hd["price"]
    ls_price = ls["price"]
    rs_price = rs["price"]

    # Head must be more extreme than both shoulders
    if pattern_type == "bearish":
        if not (head_price > ls_price and head_price > rs_price):
            return
    else:
        if not (head_price < ls_price and head_price < rs_price):
            return

    # Shoulders should be roughly symmetric in price
    shoulder_ratio = (
        abs(ls_price - rs_price) / abs(head_price - (ls_price + rs_price) / 2.0)
        if abs(head_price - (ls_price + rs_price) / 2.0) > 1e-10
        else 999
    )
    if shoulder_ratio > 0.5:
        return

    # Time symmetry: LS→head vs head→RS should be comparable
    time_left = hd["index"] - ls["index"]
    time_right = rs["index"] - hd["index"]
    if time_left <= 0 or time_right <= 0:
        return
    time_ratio = max(time_left, time_right) / min(time_left, time_right)
    if time_ratio > 2.5:
        return

    # Balance: compute neckline between t1 and t2
    t1_idx = t1["index"]
    t2_idx = t2["index"]
    t1_price = t1["price"]
    t2_price = t2["price"]
    if t2_idx <= t1_idx:
        return

    neck_slope = (t2_price - t1_price) / (t2_idx - t1_idx)
    n_b = t1_price - neck_slope * t1_idx

    # Compute R² of the 6-segment model
    try:
        r2_val = _compute_hs_r2(
            window, log_close, neck_slope, n_b, pattern_type
        )
    except Exception:
        r2_val = 0.0

    # Project neckline to right shoulder and beyond
    neckline_start = n_b + neck_slope * ls["index"]
    neckline_end = n_b + neck_slope * rs["index"]

    # Check breakout: price must cross neckline after right shoulder
    breakout_idx = -1
    breakout_price = 0.0
    for idx in range(rs["index"] + 1, min(n_bars, rs["index"] + 20)):
        neck_val = n_b + neck_slope * idx
        if pattern_type == "bearish":
            if log_close[idx] < neck_val:
                breakout_idx = idx
                breakout_price = log_close[idx]
                break
        else:
            if log_close[idx] > neck_val:
                breakout_idx = idx
                breakout_price = log_close[idx]
                break

    if breakout_idx < 0:
        return

    head_height = abs(head_price - neckline_start)
    target = (
        neckline_end - head_height if pattern_type == "bearish"
        else neckline_end + head_height
    )
    stop = rs_price

    out_list.append({
        "type": pattern_type,
        "head_price": head_price,
        "neckline_start": neckline_start,
        "neckline_end": neckline_end,
        "breakout_price": breakout_price,
        "breakout_index": breakout_idx,
        "head_height": head_height,
        "neck_slope": neck_slope,
        "r_squared": round(r2_val, 4),
        "target": target,
        "stop": stop,
    })


def _compute_hs_r2(
    window: list[dict],
    log_close: np.ndarray,
    neck_slope: float,
    neck_intercept: float,
    pattern_type: str,
) -> float:
    """Compute R² for the 6-segment H&S / IHS model.

    Model: connect LS→t1→head→t2→RS→breakout via straight-line segments,
    plus neckline projection.
    """
    ls = window[0]
    t1 = window[1]
    hd = window[2]
    t2 = window[3]
    rs = window[4]

    points = [
        (ls["index"], ls["price"]),
        (t1["index"], t1["price"]),
        (hd["index"], hd["price"]),
        (t2["index"], t2["price"]),
        (rs["index"], rs["price"]),
    ]
    if pattern_type == "bearish":
        breakout_target = neck_intercept + neck_slope * (rs["index"] + 5)
        points.append((rs["index"] + 5, breakout_target - 0.01))
    else:
        breakout_target = neck_intercept + neck_slope * (rs["index"] + 5)
        points.append((rs["index"] + 5, breakout_target + 0.01))

    start_idx = points[0][0]
    end_idx = points[-1][0]
    if end_idx <= start_idx or end_idx >= len(log_close):
        return 0.0

    actual = log_close[start_idx : end_idx + 1]
    x_model = np.arange(len(actual), dtype=float)
    y_model = np.zeros_like(x_model)

    for seg in range(len(points) - 1):
        s0 = points[seg]
        s1 = points[seg + 1]
        seg_len = s1[0] - s0[0]
        if seg_len <= 0:
            continue
        rel_start = s0[0] - start_idx
        rel_end = s1[0] - start_idx + 1
        seg_x = np.arange(rel_start, rel_end, dtype=float)
        seg_slope = (s1[1] - s0[1]) / seg_len
        y_model[rel_start:rel_end] = s0[1] + seg_slope * (seg_x - rel_start)

    return _r_squared(actual, y_model)


def compute_head_shoulders(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute H&S dimension score (0-100)."""
    if len(hist) < 60:
        return 50, "Insufficient data"
    try:
        result = detect_head_shoulders(hist)
    except Exception as e:
        logger.warning("Head & Shoulders detection failed: %s", e)
        return 50, f"H&S error: {e}"

    n_hs = result["recent_hs"]
    n_ihs = result["recent_ihs"]
    score = 50
    score += min(n_ihs * 15, 30)
    score -= min(n_hs * 15, 30)

    parts = []
    if n_ihs > 0:
        parts.append(f"IHS bull ({n_ihs})")
    if n_hs > 0:
        parts.append(f"H&S bear ({n_hs})")
    detail = " | ".join(parts) if parts else "No H&S patterns"
    return min(100, max(0, int(score))), detail


# ---------------------------------------------------------------------------
# Pattern B: Flags & Pennants
# ---------------------------------------------------------------------------


def detect_flags_pennants(hist: pd.DataFrame, order: int = 8) -> dict[str, Any]:
    """Detect Flags & Pennants via the trendline-based method.

    Identifies a directional pole followed by a counter-trend consolidation,
    then checks breakout rules.

    Args:
        hist: Daily OHLCV DataFrame.
        order: Rolling window order for pole/flag boundaries (default 8).

    Returns:
        Dict with bull_flags, bear_flags, bull_pennants, bear_pennants, count.
    """
    result: dict[str, Any] = {
        "bull_flags": [],
        "bear_flags": [],
        "bull_pennants": [],
        "bear_pennants": [],
        "count": 0,
        "recent_bull": 0,
        "recent_bear": 0,
    }

    if len(hist) < order * 6:
        return result

    close = hist["Close"].values.astype(float)
    log_close = np.log(close)
    n = len(log_close)

    tops, bottoms = _rw_extremes(log_close, order)

    merged: list[dict] = []
    for idx, val in tops:
        merged.append({"index": int(idx), "price": float(val), "is_top": True})
    for idx, val in bottoms:
        merged.append({"index": int(idx), "price": float(val), "is_top": False})
    merged.sort(key=lambda x: x["index"])

    if len(merged) < 3:
        return result

    for i in range(len(merged) - 2):
        a = merged[i]
        b = merged[i + 1]
        c_val = merged[i + 2]

        a_idx = a["index"]
        b_idx = b["index"]
        c_idx = c_val["index"]
        if b_idx - a_idx < order or c_idx - b_idx < order:
            continue

        if a["is_top"] and not b["is_top"] and c_val["is_top"]:
            # Pole: a→b (bearish move down)
            _check_flag_pattern(
                a, b, c_val, log_close, result, "bearish", order, n
            )
        elif not a["is_top"] and b["is_top"] and not c_val["is_top"]:
            # Pole: a→b (bullish move up)
            _check_flag_pattern(
                a, b, c_val, log_close, result, "bullish", order, n
            )

    result["count"] = (
        len(result["bull_flags"])
        + len(result["bear_flags"])
        + len(result["bull_pennants"])
        + len(result["bear_pennants"])
    )

    def _recent(entries: list[dict]) -> int:
        return sum(1 for e in entries if n - 1 - e.get("breakout_index", -10**9) < FLAG_RECENT_BARS)

    result["recent_bull"] = _recent(result["bull_flags"]) + _recent(result["bull_pennants"])
    result["recent_bear"] = _recent(result["bear_flags"]) + _recent(result["bear_pennants"])
    return result


def _check_flag_pattern(
    pole_start: dict,
    pole_end: dict,
    flag_end: dict,
    log_close: np.ndarray,
    result: dict[str, Any],
    direction: str,
    order: int,
    n_bars: int,
) -> None:
    """Validate a flag/pennant pattern after a directional pole."""
    pole_height = abs(pole_end["price"] - pole_start["price"])
    pole_width = pole_end["index"] - pole_start["index"]
    if pole_width < order or pole_height < 0.01:
        return

    flag_start_idx = pole_end["index"]
    flag_end_idx = flag_end["index"]
    if flag_end_idx - flag_start_idx < order:
        return

    flag_data = log_close[flag_start_idx : flag_end_idx + 1]
    if len(flag_data) < order:
        return

    lines = _flag_lines(flag_data)
    if lines is None:
        return
    (upper_slope, upper_icpt), (lower_slope, lower_icpt) = lines
    x_flag = np.arange(len(flag_data), dtype=float)
    upper_line = upper_slope * x_flag + upper_icpt
    lower_line = lower_slope * x_flag + lower_icpt
    flag_height = float(np.max(upper_line - lower_line))
    if flag_height <= 0 or flag_height > pole_height * 0.75:
        return

    if flag_end_idx - flag_start_idx > pole_width * 0.5:
        return

    is_pennant = bool(upper_slope < 0 < lower_slope)
    tolerance = max(abs(upper_slope), abs(lower_slope)) * 0.6 + 1e-5
    parallel = abs(upper_slope - lower_slope) <= tolerance
    if direction == "bullish":
        is_flag = parallel and upper_slope <= 0 and lower_slope <= 0
    else:
        is_flag = parallel and upper_slope >= 0 and lower_slope >= 0
    if not (is_pennant or is_flag):
        return
    resist_slope, support_slope = upper_slope, lower_slope

    # Breakout check against the projected trend lines
    breakout_idx = -1
    breakout_price = 0.0
    for idx in range(flag_end_idx + 1, min(n_bars, flag_end_idx + 15)):
        rel = idx - flag_start_idx
        resist_val = upper_slope * rel + upper_icpt
        support_val = lower_slope * rel + lower_icpt
        if direction == "bullish":
            if log_close[idx] > resist_val:
                breakout_idx = idx
                breakout_price = log_close[idx]
                break
        else:
            if log_close[idx] < support_val:
                breakout_idx = idx
                breakout_price = log_close[idx]
                break

    if breakout_idx < 0:
        return

    entry = {
        "pole_start": round(float(np.exp(pole_start["price"])), 2),
        "pole_end": round(float(np.exp(pole_end["price"])), 2),
        "flag_width_bars": int(flag_end_idx - flag_start_idx),
        "breakout_price": round(float(np.exp(breakout_price)), 2),
        "breakout_index": int(breakout_idx),
        "support_slope": round(float(support_slope), 6),
        "resist_slope": round(float(resist_slope), 6),
        "is_pennant": is_pennant,
        "target": round(float(np.exp(
            pole_end["price"] + pole_height * (1 if direction == "bullish" else -1)
        )), 2),
        "stop": round(float(np.exp(
            flag_data.min() if direction == "bullish" else flag_data.max()
        )), 2),
    }

    if direction == "bullish":
        if is_pennant:
            result["bull_pennants"].append(entry)
        else:
            result["bull_flags"].append(entry)
    else:
        if is_pennant:
            result["bear_pennants"].append(entry)
        else:
            result["bear_flags"].append(entry)


def compute_flags_pennants(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute Flags & Pennants dimension score (0-100)."""
    if len(hist) < 60:
        return 50, "Insufficient data"
    try:
        result = detect_flags_pennants(hist)
    except Exception as e:
        logger.warning("Flags/Pennants detection failed: %s", e)
        return 50, f"Flags error: {e}"

    n_bull = result["recent_bull"]
    n_bear = result["recent_bear"]
    score = 50
    score += min(n_bull * 10, 30)
    score -= min(n_bear * 10, 30)

    parts = []
    if n_bull > 0:
        parts.append(f"Bull flags/pennants ({n_bull})")
    if n_bear > 0:
        parts.append(f"Bear flags/pennants ({n_bear})")
    detail = " | ".join(parts) if parts else "No flags/pennants"
    return min(100, max(0, int(score))), detail


# ---------------------------------------------------------------------------
# Pattern C: Harmonic Patterns
# ---------------------------------------------------------------------------

# Fibonacci ratio maps for each pattern name.
# Each entry: {ratio_name: (target_ratio, tolerance)} or
# (target_low, target_high) for range-based matching.

HARMONIC_PATTERNS: dict[str, dict[str, Any]] = {
    "Gartley": {
        "XA_AB": (0.618, 0.05),
        "AB_BC": (0.382, 0.886),
        "BC_CD": (1.13, 1.618),
        "XA_AD": (0.786, 0.05),
    },
    "Bat": {
        "XA_AB": (0.382, 0.50),
        "AB_BC": (0.382, 0.886),
        "BC_CD": (1.618, 2.618),
        "XA_AD": (0.886, 0.05),
    },
    "Butterfly": {
        "XA_AB": (0.786, 0.05),
        "AB_BC": (0.382, 0.886),
        "BC_CD": (1.618, 2.24),
        "XA_AD": (1.27, 1.41),
    },
    "Crab": {
        "XA_AB": (0.382, 0.618),
        "AB_BC": (0.382, 0.886),
        "BC_CD": (2.618, 3.618),
        "XA_AD": (1.618, 0.05),
    },
    "DeepCrab": {
        "XA_AB": (0.886, 0.05),
        "AB_BC": (0.382, 0.886),
        "BC_CD": (2.0, 3.618),
        "XA_AD": (1.618, 0.05),
    },
    "Cypher": {
        "XA_AB": (0.382, 0.618),
        "AB_BC": (1.13, 1.41),
        "BC_CD": (1.27, 2.00),
        "XA_AD": (0.786, 0.05),
    },
    "Shark": {
        "XA_AB": None,
        "AB_BC": (1.13, 1.618),
        "BC_CD": (1.618, 2.24),
        "XA_AD": (0.886, 1.13),
    },
}


def detect_harmonic_patterns(
    hist: pd.DataFrame, sigma: float = 0.03, err_thresh: float = HARMONIC_ERR_THRESH
) -> dict[str, Any]:
    """Detect Harmonic Patterns (Gartley, Bat, Butterfly, Crab, etc.).

    Uses directional-change zigzag to find XABCD points, then matches
    Fibonacci ratios against 7 known harmonic pattern templates.

    Runs ensemble over sigma = [0.02, 0.03, 0.04] for robustness.

    Args:
        hist: Daily OHLCV DataFrame.
        sigma: Retracement threshold for directional change (default 0.03).
        err_thresh: Maximum log-space RMS match error (default 0.10).

    Returns:
        Dict with ``patterns``, ``count``, ``best_pattern``, ``best_error``.
    """
    result: dict[str, Any] = {
        "patterns": [],
        "count": 0,
        "best_pattern": None,
        "best_error": None,
        "recent_bull": 0,
        "recent_bear": 0,
    }

    if len(hist) < 20:
        return result

    high = hist["High"].values.astype(float)
    low = hist["Low"].values.astype(float)
    close = hist["Close"].values.astype(float)

    # Ensemble over 3 sigma values for robustness
    sigma_values = sorted(set([0.02, 0.03, 0.04, sigma]))
    all_patterns: list[dict] = []
    for s in sigma_values:
        try:
            patterns = _detect_harmonic_single(high, low, close, s, err_thresh)
            all_patterns.extend(patterns)
        except Exception as e:
            logger.debug("Harmonic detection sigma=%.2f failed: %s", s, e)

    # Deduplicate: keep unique by X index
    seen_x: set[int] = set()
    unique: list[dict] = []
    for p in sorted(all_patterns, key=lambda x: x.get("error", 999)):
        x_idx = p.get("_x_idx", -1)
        if x_idx > 0 and x_idx not in seen_x:
            seen_x.add(x_idx)
            clean = {k: v for k, v in p.items() if not k.startswith("_")}
            for ratio_key in ["XA_AB", "AB_BC", "BC_CD", "XA_AD"]:
                if ratio_key in clean.get("ratios", {}):
                    clean["ratios"][ratio_key] = round(
                        float(clean["ratios"][ratio_key]), 4
                    )
            unique.append(clean)

    unique.sort(key=lambda x: x.get("error", 999))

    n_bars = len(hist)
    recent = [p for p in unique if n_bars - 1 - int(p.get("d_index", -10**9)) < HARMONIC_RECENT_BARS]
    result["patterns"] = unique
    result["count"] = len(unique)
    result["recent_bull"] = sum(1 for p in recent if p.get("name", "").startswith("Bull"))
    result["recent_bear"] = sum(1 for p in recent if p.get("name", "").startswith("Bear"))
    if unique:
        result["best_pattern"] = unique[0].get("name")
        result["best_error"] = unique[0].get("error")

    return result


def _detect_harmonic_single(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    sigma: float,
    err_thresh: float,
) -> list[dict]:
    """Run harmonic detection at a single sigma value."""
    patterns: list[dict] = []

    tops, bottoms = _directional_change(high, low, close, sigma)

    # Build ordered zigzag list
    zigzag: list[tuple[int, float, bool]] = []
    for _, ext_i, price in tops:
        zigzag.append((ext_i, np.log(price), True))
    for _, ext_i, price in bottoms:
        zigzag.append((ext_i, np.log(price), False))
    zigzag.sort(key=lambda x: x[0])

    if len(zigzag) < 5:
        return patterns

    for i in range(len(zigzag) - 5):
        x_point = zigzag[i]
        a_point = zigzag[i + 1]
        b_point = zigzag[i + 2]
        c_val = zigzag[i + 3]
        d_point = zigzag[i + 4]

        # Must alternate
        if not (x_point[2] != a_point[2] and a_point[2] != b_point[2]
                and b_point[2] != c_val[2] and c_val[2] != d_point[2]):
            continue

        x_price = x_point[1]
        a_price = a_point[1]
        b_price = b_point[1]
        c_price = c_val[1]
        d_price = d_point[1]

        xa = abs(a_price - x_price)
        ab = abs(b_price - a_price)
        bc = abs(c_price - b_price)
        cd_len = abs(d_price - c_price)
        ad = abs(d_price - a_price)

        if xa < 1e-10 or ab < 1e-10 or bc < 1e-10:
            continue

        ratios: dict[str, float] = {
            "XA_AB": ab / xa,
            "AB_BC": bc / ab,
            "BC_CD": cd_len / bc if bc > 1e-10 else 0.0,
            "XA_AD": ad / xa,
        }

        is_bull = d_point[2] is False

        for pattern_name, targets in HARMONIC_PATTERNS.items():
            error = _get_pattern_error(ratios, targets)
            if error > err_thresh:
                continue

            name = f"{'Bull' if is_bull else 'Bear'}{pattern_name}"
            patterns.append({
                "name": name,
                "X": round(float(np.exp(x_price)), 2),
                "A": round(float(np.exp(a_price)), 2),
                "B": round(float(np.exp(b_price)), 2),
                "C": round(float(np.exp(c_price)), 2),
                "D": round(float(np.exp(d_price)), 2),
                "error": round(float(error), 4),
                "ratios": ratios,
                "d_index": int(d_point[0]),
                "_x_idx": x_point[0],
            })

    return patterns


def _get_pattern_error(
    ratios: dict[str, float], targets: dict[str, Any]
) -> float:
    """Compute total error between observed ratios and pattern targets.

    Uses log-space error (log ratio - log target)² for scale invariance.
    """
    total_error = 0.0
    n_matched = 0

    for ratio_name, target_val in targets.items():
        if ratio_name not in ratios:
            continue
        if target_val is None:
            n_matched += 1
            continue

        observed = ratios[ratio_name]
        if observed <= 0:
            continue

        log_obs = np.log(observed)
        if isinstance(target_val, tuple) and len(target_val) == 2:
            low, high = target_val
            if low >= high:  # single target with tolerance
                log_target = np.log(low)
                err = (log_obs - log_target) ** 2
            else:  # range
                log_low = np.log(low)
                log_high = np.log(high)
                if log_low <= log_obs <= log_high:
                    err = 0.0
                else:
                    dist = min(abs(log_obs - log_low), abs(log_obs - log_high))
                    err = dist ** 2
        else:
            log_target = np.log(float(target_val))
            err = (log_obs - log_target) ** 2

        total_error += err
        n_matched += 1

    if n_matched == 0:
        return 999.0
    return float(np.sqrt(total_error / n_matched))


def compute_harmonic_patterns(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute Harmonic Patterns dimension score (0-100)."""
    if len(hist) < 60:
        return 50, "Insufficient data"
    try:
        result = detect_harmonic_patterns(hist)
    except Exception as e:
        logger.warning("Harmonic detection failed: %s", e)
        return 50, f"Harmonic error: {e}"

    n_bull = result["recent_bull"]
    n_bear = result["recent_bear"]
    score = 50
    score += min(n_bull * 8, 24)
    score -= min(n_bear * 8, 24)

    parts = []
    if n_bull > 0:
        parts.append(f"Bull harmonic ({n_bull})")
    if n_bear > 0:
        parts.append(f"Bear harmonic ({n_bear})")
    if result.get("best_pattern"):
        parts.append(f"Best: {result['best_pattern']}")
    detail = " | ".join(parts) if parts else "No harmonic patterns"
    return min(100, max(0, int(score))), detail


# ---------------------------------------------------------------------------
# Pattern D: Support/Resistance via Market Profile (Gaussian KDE)
# ---------------------------------------------------------------------------


def detect_support_resistance(
    hist: pd.DataFrame, lookback: int = 90
) -> dict[str, Any]:
    """Detect support/resistance levels via Gaussian KDE on log-prices.

    Adapted from mp_support_resist.py: uses scipy.stats.gaussian_kde with an
    ATR-based bandwidth (2 x Wilder ATR as a fraction of price) and
    exponential recency weights.

    Signal (mirror rules): a close that crossed above a level during the last
    5 bars is a ``bullish`` breakout, a cross below is a ``bearish``
    breakdown. Without a cross, a 5-bar low within 0.5% of the support is a
    bullish bounce and a 5-bar high within 0.5% of the resistance a bearish
    rejection (both at once: neutral). Missing levels are ``None``.

    Args:
        hist: Daily OHLCV DataFrame.
        lookback: Number of bars to use for KDE (default 90).
    """
    result: dict[str, Any] = {
        "levels": [],
        "nearest_support": None,
        "nearest_resistance": None,
        "closest_levels": {"below": None, "above": None},
        "signal": "neutral",
        "n_levels": 0,
    }

    if len(hist) < lookback:
        return result

    close = hist["Close"].values.astype(float)
    log_close = np.log(close)
    window = log_close[-lookback:]

    atr = _compute_tr_atr(hist, lookback)
    if atr <= 0:
        atr = 0.01
    bw = atr * 2.0

    weights = np.exp(np.linspace(-1.0, 0.0, len(window)))
    weights /= weights.sum()
    std = float(np.std(window))
    try:
        kde = gaussian_kde(window, bw_method=bw / std if std > 0 else None, weights=weights)
    except Exception:  # pylint: disable=broad-exception-caught
        return result

    grid = np.linspace(window.min(), window.max(), 200)
    density = kde(grid)
    peaks, _ = find_peaks(density, height=density.max() * 0.3, distance=10)
    levels = sorted(float(np.exp(grid[p])) for p in peaks)

    current_price = float(close[-1])
    below = [lvl for lvl in levels if lvl < current_price]
    above = [lvl for lvl in levels if lvl > current_price]
    support = max(below) if below else None
    resistance = min(above) if above else None

    signal = "neutral"
    if len(close) >= 6:
        start = float(close[-6])
        crossed_up = any(start < lvl < current_price for lvl in levels)
        crossed_down = any(current_price < lvl < start for lvl in levels)
        if crossed_up and not crossed_down:
            signal = "bullish"
        elif crossed_down and not crossed_up:
            signal = "bearish"
        else:
            bounce = support is not None and float(close[-5:].min()) <= support * 1.005
            reject = resistance is not None and float(close[-5:].max()) >= resistance * 0.995
            if bounce and not reject:
                signal = "bullish"
            elif reject and not bounce:
                signal = "bearish"

    result["levels"] = [round(lvl, 2) for lvl in levels]
    result["nearest_support"] = round(support, 2) if support is not None else None
    result["nearest_resistance"] = round(resistance, 2) if resistance is not None else None
    result["closest_levels"] = {"below": result["nearest_support"], "above": result["nearest_resistance"]}
    result["signal"] = signal
    result["n_levels"] = len(levels)
    return result


def _compute_tr_atr(hist: pd.DataFrame, lookback: int) -> float:
    """Wilder ATR(14) as a fraction of the mean price of the window (for log-space use)."""
    if len(hist) < 15:
        return 0.0
    atr = wilder_atr(hist, 14).iloc[-1]
    if pd.isna(atr):
        return 0.0
    close_window = hist["Close"].values.astype(float)[-lookback:]
    close_window = close_window[close_window > 0]
    if len(close_window) == 0:
        return 0.0
    return float(atr) / float(np.exp(np.mean(np.log(close_window))))


def compute_support_resistance_score(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute S/R dimension score (0-100)."""
    if len(hist) < 60:
        return 50, "Insufficient data"
    try:
        result = detect_support_resistance(hist)
    except Exception as e:
        logger.warning("S/R detection failed: %s", e)
        return 50, f"S/R error: {e}"

    score = 50
    detail = f"S/R levels: {result['n_levels']}"

    if result["signal"] == "bullish":
        score += 15
        detail += " | bullish (breakout or bounce)"
    elif result["signal"] == "bearish":
        score -= 15
        detail += " | bearish (breakdown or rejection)"
    detail += f" | Nearest: S={result['nearest_support']} R={result['nearest_resistance']}"

    return min(100, max(0, int(score))), detail


# ---------------------------------------------------------------------------
# Main composite functions
# ---------------------------------------------------------------------------


def compute_taa_patterns(hist: pd.DataFrame) -> tuple[int, str]:
    """Composite TAA pattern score (0-100, 50 = neutral) from RECENT patterns only.

    Recent IHS +15 each / H&S -15 each (max +-30), recent bull / bear
    flags-pennants +-10 each (max +-30), recent bull / bear harmonics +-8 each
    (max +-24). The KDE support/resistance is reported by
    :func:`get_taa_patterns` but not scored here (no double counting with the
    swing-cluster S/R indicator).
    """
    if len(hist) < 60:
        return 50, "Insufficient data for TAA patterns"

    details: list[str] = []
    score = 50.0
    hs = detect_head_shoulders(hist)
    fp = detect_flags_pennants(hist)
    harm = detect_harmonic_patterns(hist)

    n_ihs, n_hs = hs.get("recent_ihs", 0), hs.get("recent_hs", 0)
    score += min(n_ihs * 15, 30) - min(n_hs * 15, 30)
    if n_ihs:
        details.append(f"Recent IHS ({n_ihs})")
    if n_hs:
        details.append(f"Recent H&S ({n_hs})")

    n_bf, n_bfr = fp.get("recent_bull", 0), fp.get("recent_bear", 0)
    score += min(n_bf * 10, 30) - min(n_bfr * 10, 30)
    if n_bf:
        details.append(f"Recent bull flags/pennants ({n_bf})")
    if n_bfr:
        details.append(f"Recent bear flags/pennants ({n_bfr})")

    n_bull_h, n_bear_h = harm.get("recent_bull", 0), harm.get("recent_bear", 0)
    score += min(n_bull_h * 8, 24) - min(n_bear_h * 8, 24)
    if n_bull_h:
        details.append(f"Recent bull harmonic ({n_bull_h})")
    if n_bear_h:
        details.append(f"Recent bear harmonic ({n_bear_h})")

    score = min(100.0, max(0.0, score))
    detail = " | ".join(details) if details else "No recent TAA patterns"
    return int(round(score)), detail


def get_taa_patterns(hist: pd.DataFrame) -> dict[str, Any]:
    """Return all TAA pattern detection results in structured format.

    Args:
        hist: Daily OHLCV DataFrame.

    Returns:
        Dict with keys: head_shoulders, flags_pennants, harmonic,
        support_resistance.
    """
    try:
        return {
            "head_shoulders": detect_head_shoulders(hist),
            "flags_pennants": detect_flags_pennants(hist),
            "harmonic": detect_harmonic_patterns(hist),
            "support_resistance": detect_support_resistance(hist),
        }
    except Exception as e:
        logger.error("get_taa_patterns failed: %s", e)
        return {
            "head_shoulders": {"count": 0, "hs_patterns": [],
                               "ihs_patterns": [], "recent": False, "recent_hs": 0, "recent_ihs": 0},
            "flags_pennants": {"bull_flags": [], "bear_flags": [],
                               "bull_pennants": [], "bear_pennants": [],
                               "count": 0, "recent_bull": 0, "recent_bear": 0},
            "harmonic": {"patterns": [], "count": 0,
                         "best_pattern": None, "best_error": None, "recent_bull": 0, "recent_bear": 0},
            "support_resistance": {"levels": [], "nearest_support": None,
                                   "nearest_resistance": None,
                                   "closest_levels": {"below": None, "above": None},
                                   "signal": "neutral", "n_levels": 0},
        }
