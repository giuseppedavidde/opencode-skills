"""Price action analysis: RSI, EMA slope, VPA net, rally velocity, exhaustion."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_price_action(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute price action score (0-100).

    Evaluates RSI, 25ema slope, VPA bar-by-bar net, rally velocity check,
    and consecutive green candle exhaustion.
    """
    if hist.empty or len(hist) < 20:
        return 10, "Insufficient data"

    score = 10
    details = []

    if len(hist) >= 15:
        delta = hist["Close"].diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rsi = 100.0 - (100.0 / (1.0 + ma_up / ma_down))
        rsi_val = float(rsi.iloc[-1])
        if 40 <= rsi_val <= 60:
            score += 10
            details.append(f"RSI {rsi_val:.0f} (neutral) (+10)")
        elif 30 <= rsi_val < 40:
            score += 20
            details.append(f"RSI {rsi_val:.0f} (oversold zone) (+20)")
        elif rsi_val < 30:
            score += 10
            details.append(f"RSI {rsi_val:.0f} (extreme) (+10)")
        else:
            details.append(f"RSI {rsi_val:.0f} (+0)")

    hist_copy = hist.copy()
    hist_copy["ema25"] = hist_copy["Close"].ewm(span=25).mean()
    if len(hist) >= 30:
        slope = (float(hist_copy["ema25"].iloc[-1]) - float(hist_copy["ema25"].iloc[-5])) / float(hist_copy["ema25"].iloc[-5])
        if slope > 0:
            score += 15
            details.append("25ema rising (+15)")
        else:
            details.append("25ema flat/falling (+0)")

    last_20 = hist.tail(20)
    vpa_net = 0
    for i in range(1, len(last_20)):
        bar = last_20.iloc[i]
        prev = last_20.iloc[i - 1]
        vol = float(bar["Volume"])
        avg = float(last_20["Volume"].mean())
        vr = vol / avg if avg > 0 else 1.0
        up_c = float(bar["Close"]) > float(prev["Close"])
        wide = (float(bar["High"]) - float(bar["Low"])) > (float(prev["High"]) - float(prev["Low"])) * 1.2
        high_vol = vr > 1.5
        if up_c and high_vol:
            vpa_net += 1
        elif not up_c and high_vol:
            vpa_net -= 1
        if up_c and vr < 0.6 and wide:
            vpa_net -= 1
        elif not up_c and vr < 0.6 and wide:
            vpa_net += 1

    if vpa_net > 2:
        score += 20
        details.append(f"VPA bullish ({vpa_net}) (+20)")
    elif vpa_net > 0:
        details.append(f"VPA mildly bullish ({vpa_net}) (+0)")

    if len(hist) >= 30:
        close_15d_ago = float(hist["Close"].iloc[-16])
        close_now = float(hist["Close"].iloc[-1])
        change_15d = (close_now / close_15d_ago - 1) * 100

        if change_15d > 50:
            score = max(score - 50, 0)
            details.append(f"WARN: Rally +{change_15d:.0f}% in 15d (vertical, -50)")
        elif change_15d > 30:
            score = max(score - 35, 0)
            details.append(f"WARN: Rally +{change_15d:.0f}% in 15d (exhaustion risk -35)")
        elif change_15d > 20:
            score = max(score - 20, 0)
            details.append(f"WARN: Rally +{change_15d:.0f}% in 15d (extension -20)")
        elif -3 < change_15d < 10:
            vol_lately = float(hist.tail(5)["Volume"].mean())
            vol_20d = float(hist.tail(20)["Volume"].mean())
            if vol_lately > vol_20d * 1.2 and change_15d > 0:
                score += 15
                details.append(f"Gradual +{change_15d:.0f}% on rising vol (+15)")

        if len(hist) >= 10:
            closes = hist.tail(10)["Close"].values
            green_streak = 0
            for j in range(1, len(closes)):
                if closes[j] > closes[j - 1]:
                    green_streak += 1
                else:
                    green_streak = 0
            if green_streak >= 5:
                score = max(score - 10, 0)
                details.append(f"{green_streak} consecutive green candles (-10)")

    return min(score, 100), " | ".join(details)


def compute_multiframe_trend(hist: pd.DataFrame) -> tuple[int, str]:
    """Multi-Timeframe Analysis (VPA Coulling).

    Aligns trend across 3 timeframes: fast (20d), primary (50d), slow (200d).
    """
    if hist.empty or len(hist) < 50:
        return 50, "Insufficient data for MTF"

    score = 50
    details = []
    close = hist["Close"]

    def _trend(series: pd.Series, window: int) -> str:
        if len(series) < window:
            return "unknown"
        ma = series.rolling(window).mean()
        if len(ma) < 5:
            return "unknown"
        slope = (float(ma.iloc[-1]) - float(ma.iloc[-5])) / float(ma.iloc[-5])
        if slope > 0.02:
            return "up"
        if slope < -0.02:
            return "down"
        return "flat"

    fast = _trend(close, 20)
    primary = _trend(close, 50)
    slow = _trend(close, 200) if len(close) >= 200 else "unknown"

    trends = [t for t in [fast, primary, slow] if t != "unknown"]
    if not trends:
        return 50, "No trend data"

    up_count = trends.count("up")
    down_count = trends.count("down")

    if up_count == len(trends) and len(trends) >= 2:
        score += 30
        details.append(f"All TFs bullish ({'/'.join(trends)}) (+30)")
    elif up_count >= 2 and down_count == 0:
        score += 15
        details.append(f"Mostly bullish ({'/'.join(trends)}) (+15)")
    elif down_count == len(trends) and len(trends) >= 2:
        score -= 25
        details.append(f"All TFs bearish ({'/'.join(trends)}) (-25)")
    elif down_count >= 2 and up_count == 0:
        score -= 15
        details.append(f"Mostly bearish ({'/'.join(trends)}) (-15)")
    else:
        details.append(f"Mixed TFs ({'/'.join(trends)}) (+0)")

    if slow == "up" and fast == "up" and primary == "up":
        score += 10
        details.append("Triple alignment (Coulling) (+10)")

    return min(100, max(0, score)), " | ".join(details)
