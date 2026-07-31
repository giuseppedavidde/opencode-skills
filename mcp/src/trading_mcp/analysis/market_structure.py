"""Market structure analysis via hierarchical ATR-adaptive extremes."""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_mcp.analysis.hierarchical_extremes import (
    HierarchicalExtremes,
    determine_trend,
)


def compute_market_structure(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute market structure score (0-100) from hierarchical extremes.

    Args:
        hist: OHLCV DataFrame with columns Open, High, Low, Close, Volume.

    Returns:
        (score 0-100, detail string).
    """
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data for market structure"

    he = HierarchicalExtremes(levels=4, atr_lookback=14)

    closes = hist["Close"].to_numpy()
    highs = hist["High"].to_numpy()
    lows = hist["Low"].to_numpy()

    for i in range(len(hist)):
        he.process_bar(float(highs[i]), float(lows[i]), float(closes[i]))

    current_atr = he.atr
    if current_atr <= 0:
        return 50, "ATR unavailable"

    last_close = float(closes[-1])
    score = 50
    details: list[str] = []
    trends: dict[int, str] = {}

    for level in range(4):
        l_highs = list(he.level_highs.get(level, []))
        l_lows = list(he.level_lows.get(level, []))
        trend = determine_trend(l_highs, l_lows)
        trends[level] = trend
        h_str = f"H: {l_highs[-2:]}" if l_highs else "H: none"
        l_str = f"L: {l_lows[-2:]}" if l_lows else "L: none"
        details.append(f"L{level} {trend} ({h_str}, {l_str})")

    # Aggregate trend signal
    trend_values = list(trends.values())
    uptrend_count = sum(1 for t in trend_values if t == "uptrend")
    downtrend_count = sum(1 for t in trend_values if t == "downtrend")
    range_count = sum(1 for t in trend_values if t == "range")

    if uptrend_count == 4:
        score = 85
        details.append("All levels uptrend → strong bullish structure")
    elif downtrend_count == 4:
        score = 15
        details.append("All levels downtrend → strong bearish structure")
    elif uptrend_count >= 3 and downtrend_count == 0:
        score = 75
        details.append("Most levels uptrend → bullish structure")
    elif downtrend_count >= 3 and uptrend_count == 0:
        score = 25
        details.append("Most levels downtrend → bearish structure")
    elif uptrend_count >= 2 and downtrend_count <= 1:
        score = 60
        details.append("Leaning bullish (mixed)")
    elif downtrend_count >= 2 and uptrend_count <= 1:
        score = 40
        details.append("Leaning bearish (mixed)")
    else:
        score = 50
        details.append("Mixed/range-bound structure")

    # Check if price is within level 2 structure
    l2_highs = he.level_highs.get(2, [])
    l2_lows = he.level_lows.get(2, [])

    if l2_highs and l2_lows:
        l2_resistance = max(l2_highs)
        l2_support = min(l2_lows)
        if l2_support < last_close < l2_resistance:
            score = min(100, score + 5)
            details.append(f"Price within L2 structure ({l2_support:.2f}-{l2_resistance:.2f}) (+5)")
        elif last_close > l2_resistance * 1.02:
            score = max(0, score - 10)
            details.append(f"Price breakout above L2 resistance ({l2_resistance:.2f}) (-10)")
        elif last_close < l2_support * 0.98:
            score = max(0, score - 10)
            details.append(f"Price breakdown below L2 support ({l2_support:.2f}) (-10)")

    details.append(f"ATR={current_atr:.4f}")
    return min(100, max(0, score)), " | ".join(details)


def get_structure_levels(hist: pd.DataFrame) -> dict[str, Any]:
    """Extract structured market-structure levels from hist.

    Returns a dict with trend, per-level highs/lows/trend, ATR,
    key support/resistance, and micro/macro trend.
    """
    if hist.empty or len(hist) < 20:
        return {
            "trend": "range",
            "levels": {},
            "atr": 0.0,
            "key_support": 0.0,
            "key_resistance": 0.0,
            "micro_trend": "range",
            "macro_trend": "range",
        }

    he = HierarchicalExtremes(levels=4, atr_lookback=14)

    closes = hist["Close"].to_numpy()
    highs_np = hist["High"].to_numpy()
    lows_np = hist["Low"].to_numpy()

    for i in range(len(hist)):
        he.process_bar(float(highs_np[i]), float(lows_np[i]), float(closes[i]))

    atr_val = he.atr
    levels_data: dict[int, dict[str, Any]] = {}
    trend_counts = {"uptrend": 0, "downtrend": 0, "range": 0}

    for level in range(4):
        l_highs = list(he.level_highs.get(level, []))
        l_lows = list(he.level_lows.get(level, []))
        trend = determine_trend(l_highs, l_lows)
        trend_counts[trend] += 1
        levels_data[level] = {
            "high": l_highs[-2:] if l_highs else [],
            "low": l_lows[-2:] if l_lows else [],
            "trend": trend,
        }

    overall_trend: str = "range"
    if trend_counts["uptrend"] >= 3 and trend_counts["downtrend"] == 0:
        overall_trend = "uptrend"
    elif trend_counts["downtrend"] >= 3 and trend_counts["uptrend"] == 0:
        overall_trend = "downtrend"

    l2_highs = he.level_highs.get(2, [])
    l2_lows = he.level_lows.get(2, [])
    key_resistance = float(max(l2_highs)) if l2_highs else 0.0
    key_support = float(min(l2_lows)) if l2_lows else 0.0
    micro_trend = levels_data.get(0, {}).get("trend", "range")
    macro_trend = levels_data.get(3, {}).get("trend", "range")

    return {
        "trend": overall_trend,
        "levels": levels_data,
        "atr": atr_val,
        "key_support": key_support,
        "key_resistance": key_resistance,
        "micro_trend": micro_trend,
        "macro_trend": macro_trend,
    }
