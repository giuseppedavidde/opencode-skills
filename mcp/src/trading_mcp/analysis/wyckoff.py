"""Wyckoff phase analysis and 6-Clue accumulation/distribution test."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_wyckoff(hist: pd.DataFrame, info: dict[str, Any]) -> tuple[int, str]:
    """Compute Wyckoff phase score (0-100).

    Evaluates position within 1-year range, HH/HL or LH/LL structure,
    MA crossovers, Spring detection, volume absorption, and volume-price divergence.

    Args:
        hist: OHLCV DataFrame with at least 50 bars.
        info: yfinance info dict (unused currently).
    """
    if hist.empty or len(hist) < 50:
        return 20, "Insufficient data"

    score = 20
    details = []
    price = float(hist["Close"].iloc[-1])
    high_1y = float(hist["High"].max())
    low_1y = float(hist["Low"].min())
    price_range = high_1y - low_1y
    pos = ((price - low_1y) / price_range) * 100 if price_range > 0 else 50

    if pos < 30:
        score += 15
        details.append("Bottom 30% of 1Y range (+15)")
    elif pos < 60:
        score += 30
        details.append("Accumulation zone 30-60% of range (+30)")
    else:
        details.append("Upper 40% of range (+0)")

    recent = hist.tail(60)
    if len(recent) >= 20:
        highs = recent["High"].values
        lows = recent["Low"].values
        half = len(highs) // 2
        if highs[-1] > highs[half] and lows[-1] > lows[half]:
            score += 40
            details.append("HH/HL pattern (Markup) (+40)")
        elif highs[-1] < highs[half] and lows[-1] < lows[half]:
            score -= 20
            details.append("LH/LL pattern (Markdown) (-20)")

    if len(hist) >= 200:
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
        ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        if ma50 > ma200:
            score += 15
            details.append("MA50 > MA200 (+15)")
    elif len(hist) >= 50:
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
        details.append(f"MA50: {ma50:.2f}")

    if len(hist) >= 30:
        recent_30 = hist.tail(30)
        low_30 = float(recent_30["Low"].min())
        low_pos = int(recent_30["Low"].values.argmin())
        if low_pos < 25 and price > low_30 * 1.05:
            score += 30
            details.append("Spring detected (+30)")

    if len(hist) >= 90:
        vol_older = float(hist.tail(90).head(60)["Volume"].mean())
        vol_recent = float(hist.tail(30)["Volume"].mean())
        if vol_recent < vol_older * 0.8:
            score += 15
            details.append("Volume decreasing (absorption) (+15)")

    if len(hist) >= 30:
        vol_first = float(hist.iloc[-30:-15]["Volume"].mean())
        vol_second = float(hist.iloc[-15:]["Volume"].mean())
        price_first = float(hist.iloc[-30:-15]["Close"].mean())
        price_second = float(hist.iloc[-15:]["Close"].mean())
        vol_trend = vol_second / vol_first if vol_first > 0 else 1.0
        price_trend = price_second / price_first if price_first > 0 else 1.0

        if vol_trend > 1.15 and price_trend < 1.0:
            score += 25
            details.append("Rising vol + falling price (Accumulation) (+25)")
        elif vol_trend < 0.85 and price_trend > 1.0:
            score -= 20
            details.append("Falling vol + rising price (Distribution) (-20)")
        elif vol_trend > 1.15 and price_trend > 1.0:
            score += 15
            details.append("Rising vol + rising price (Markup) (+15)")
        elif vol_trend < 0.85 and price_trend < 1.0:
            score -= 15
            details.append("Falling vol + falling price (Markdown) (-15)")

    return min(score, 100), " | ".join(details)


def compute_6clue_test(hist: pd.DataFrame, info: dict[str, Any]) -> tuple[int, str]:
    """Wyckoff 6-Clue Accumulation/Distribution Test.

    Scores 6 clues for accumulation (bullish) vs distribution (bearish).
    """
    if hist.empty or len(hist) < 90:
        return 50, "Insufficient data for 6-Clue Test"

    score = 50
    details = []
    clues_bullish = 0
    clues_bearish = 0

    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    volume = hist["Volume"].values

    if len(close) >= 60:
        support_zone = float(np.min(low[-60:]))
        current = float(close[-1])
        if current > support_zone * 1.05 and current < support_zone * 1.15:
            clues_bullish += 1
            details.append("Clue 1: Price testing support (spring zone)")
        elif current < support_zone:
            clues_bearish += 1
            details.append("Clue 1: Price breaking support")

    if len(close) >= 60:
        down_vol = sum(float(volume[i]) for i in range(-60, 0) if close[i] < close[i - 1])
        up_vol = sum(float(volume[i]) for i in range(-60, 0) if close[i] > close[i - 1])
        if up_vol > down_vol * 1.2:
            clues_bullish += 1
            ratio = up_vol / down_vol if down_vol > 0 else float("inf")
            details.append(f"Clue 2: Up vol > Down vol ({ratio:.2f}x)")
        elif down_vol > up_vol * 1.2:
            clues_bearish += 1
            ratio = down_vol / up_vol if up_vol > 0 else float("inf")
            details.append(f"Clue 2: Down vol > Up vol ({ratio:.2f}x)")

    if len(close) >= 30:
        vol_first = float(np.mean(volume[-30:-15]))
        vol_second = float(np.mean(volume[-15:]))
        price_first = float(np.mean(close[-30:-15]))
        price_second = float(np.mean(close[-15:]))
        vol_trend = vol_second / vol_first if vol_first > 0 else 1.0
        price_trend = price_second / price_first if price_first > 0 else 1.0

        if vol_trend > 1.15 and price_trend < 1.0:
            clues_bullish += 1
            details.append("Clue 3: Rising vol + falling price (accumulation)")
        elif vol_trend < 0.85 and price_trend > 1.0:
            clues_bearish += 1
            details.append("Clue 3: Falling vol + rising price (distribution)")

    target_mean = info.get("targetMeanPrice")
    current_price = info.get("currentPrice") or (float(close[-1]) if len(close) > 0 else None)
    if target_mean and current_price and float(target_mean) > float(current_price) * 1.1:
        clues_bullish += 1
        details.append(f"Clue 4: Analyst target ${float(target_mean):.0f} > price ${float(current_price):.0f}")
    elif target_mean and current_price and float(target_mean) < float(current_price) * 0.9:
        clues_bearish += 1
        details.append(f"Clue 4: Analyst target ${float(target_mean):.0f} < price ${float(current_price):.0f}")

    if len(close) >= 60:
        half = len(close[-60:]) // 2
        first_half_high = float(np.max(high[-60:-60 + half]))
        first_half_low = float(np.min(low[-60:-60 + half]))
        second_half_high = float(np.max(high[-60 + half:]))
        second_half_low = float(np.min(low[-60 + half:]))
        if second_half_high > first_half_high and second_half_low > first_half_low:
            clues_bullish += 1
            details.append("Clue 5: HH/HL structure (markup)")
        elif second_half_high < first_half_high and second_half_low < first_half_low:
            clues_bearish += 1
            details.append("Clue 5: LH/LL structure (markdown)")

    if len(close) >= 120:
        range_120 = float(np.max(high[-120:]) - np.min(low[-120:]))
        range_60 = float(np.max(high[-60:]) - np.min(low[-60:]))
        if range_60 < range_120 * 0.6:
            clues_bullish += 1
            details.append("Clue 6: Narrowing range (accumulation time)")
        elif range_60 > range_120 * 0.8:
            clues_bearish += 1
            details.append("Clue 6: Wide range (distribution volatility)")

    net_clues = clues_bullish - clues_bearish
    if net_clues >= 4:
        score += 30
        details.append(f"6-Clue Test: {clues_bullish}B/{clues_bearish}S = STRONG ACCUMULATION (+30)")
    elif net_clues >= 2:
        score += 15
        details.append(f"6-Clue Test: {clues_bullish}B/{clues_bearish}S = Mild accumulation (+15)")
    elif net_clues <= -4:
        score -= 30
        details.append(f"6-Clue Test: {clues_bullish}B/{clues_bearish}S = STRONG DISTRIBUTION (-30)")
    elif net_clues <= -2:
        score -= 15
        details.append(f"6-Clue Test: {clues_bullish}B/{clues_bearish}S = Mild distribution (-15)")
    else:
        details.append(f"6-Clue Test: {clues_bullish}B/{clues_bearish}S = Neutral (+0)")

    return min(100, max(0, score)), " | ".join(details)
