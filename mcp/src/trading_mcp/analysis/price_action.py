"""Price action analysis: RSI, EMA slope, VPA net, velocity (one 0-100 scale, 50 = neutral)."""

from __future__ import annotations

import pandas as pd

from trading_mcp.analysis.ta_core import rsi_last

# Annualised pace a moving average must clear before it counts as a trend.
_MA_SLOPE_ANNUAL_THRESHOLD = 0.10


def compute_price_action(hist: pd.DataFrame) -> tuple[int, str]:
    """Price action score (0-100, 50 = neutral; mirrored, unvalidated rules).

    - Wilder RSI(14): < 30 +10, 30-40 +5, 60-70 -5, > 70 -10 (contrarian).
    - EMA(25) over 5 bars: rising (> +0.1%) +10, falling (< -0.1%) -10.
    - VPA net of the last 20 bars (high-volume up bars minus high-volume down
      bars; low-volume wide bars count against their direction): > 2 +10, < -2 -10.
    - 15-bar velocity: a rise above 20% / 30% / 50% scores -10 / -15 / -20
      (vertical extension); a fall below -20% / -30% / -50% scores +10 / +15 / +20.
      A gradual move (|change| < 10%) on rising volume (5-bar mean > 1.2x the
      20-bar mean) scores +10 when up and -10 when down.

    The streak rule lives in :func:`~trading_mcp.analysis.indicators.compute_psychology_score`.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50.0
    details: list[str] = []
    close = hist["Close"].astype(float)

    rsi_val = rsi_last(close)
    if rsi_val is not None:
        for low, high, points in ((0, 30, 10), (30, 40, 5), (60, 70, -5), (70, 101, -10)):
            if low <= rsi_val < high:
                score += points
                details.append(f"RSI {rsi_val:.0f} ({points:+d})")
                break
        else:
            details.append(f"RSI {rsi_val:.0f} (neutral)")

    ema25 = close.ewm(span=25, adjust=False).mean()
    slope = float(ema25.iloc[-1]) / float(ema25.iloc[-5]) - 1.0 if float(ema25.iloc[-5]) else 0.0
    if slope > 0.001:
        score += 10
        details.append(f"25ema rising {slope:+.2%} (+10)")
    elif slope < -0.001:
        score -= 10
        details.append(f"25ema falling {slope:+.2%} (-10)")

    last_20 = hist.tail(21)
    vol = last_20["Volume"].to_numpy(dtype=float)
    closes = last_20["Close"].to_numpy(dtype=float)
    ranges = (last_20["High"] - last_20["Low"]).to_numpy(dtype=float)
    avg = float(vol[1:].mean()) if len(vol) > 1 else 0.0
    vpa_net = 0
    for i in range(1, len(last_20)):
        vr = vol[i] / avg if avg > 0 else 1.0
        up = closes[i] > closes[i - 1]
        down = closes[i] < closes[i - 1]
        wide = ranges[i] > ranges[i - 1] * 1.2
        if vr > 1.5:
            vpa_net += 1 if up else -1 if down else 0
        elif vr < 0.6 and wide:
            vpa_net += -1 if up else 1 if down else 0
    if vpa_net > 2:
        score += 10
        details.append(f"VPA net {vpa_net:+d} (+10)")
    elif vpa_net < -2:
        score -= 10
        details.append(f"VPA net {vpa_net:+d} (-10)")

    change_15d = (float(close.iloc[-1]) / float(close.iloc[-16]) - 1.0) * 100.0
    for limit, points in ((50, 20), (30, 15), (20, 10)):
        if change_15d > limit:
            score -= points
            details.append(f"WARN: rally {change_15d:+.0f}% in 15d (extension -{points})")
            break
        if change_15d < -limit:
            score += points
            details.append(f"WARN: drop {change_15d:+.0f}% in 15d (capitulation +{points})")
            break
    else:
        if abs(change_15d) < 10:
            vol_lately = float(hist.tail(5)["Volume"].mean())
            vol_20d = float(hist.tail(20)["Volume"].mean())
            if vol_20d > 0 and vol_lately > vol_20d * 1.2:
                if change_15d > 0:
                    score += 10
                    details.append(f"Gradual {change_15d:+.0f}% on rising volume (+10)")
                elif change_15d < 0:
                    score -= 10
                    details.append(f"Gradual {change_15d:+.0f}% on rising volume (-10)")

    if not details:
        details.append("Price action neutral")
    return int(round(min(100.0, max(0.0, score)))), " | ".join(details)


def compute_multiframe_trend(hist: pd.DataFrame) -> tuple[int, str]:
    """Multi-Timeframe Analysis (VPA Coulling), 50 = neutral.

    Aligns trend across 3 timeframes: fast (20d), primary (50d), slow (200d).
    All available TFs up: +30 (+40 with all three); mostly up: +15; the
    bearish cases mirror them.
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
        # The slope always spans five bars, whatever the MA window, so the
        # threshold is a price pace, not a window-dependent number: 0.02 over
        # five bars meant ~100% annualised and labelled almost every durable
        # trend "flat". Require instead ~10% annualised (5/252 of a year).
        threshold = _MA_SLOPE_ANNUAL_THRESHOLD * 5.0 / 252.0
        if slope > threshold:
            return "up"
        if slope < -threshold:
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
        points = 40 if len(trends) == 3 else 30
        score += points
        details.append(f"All TFs bullish ({'/'.join(trends)}) (+{points})")
    elif up_count >= 2 and down_count == 0:
        score += 15
        details.append(f"Mostly bullish ({'/'.join(trends)}) (+15)")
    elif down_count == len(trends) and len(trends) >= 2:
        points = 40 if len(trends) == 3 else 30
        score -= points
        details.append(f"All TFs bearish ({'/'.join(trends)}) (-{points})")
    elif down_count >= 2 and up_count == 0:
        score -= 15
        details.append(f"Mostly bearish ({'/'.join(trends)}) (-15)")
    else:
        details.append(f"Mixed TFs ({'/'.join(trends)}) (+0)")

    return min(100, max(0, score)), " | ".join(details)
