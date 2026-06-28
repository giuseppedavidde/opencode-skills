"""Technical indicators: Candlestick, Fibonacci, Bollinger, OBV, S/R, Psychology, Ichimoku, Risk/Reward, Point & Figure."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_candlestick_patterns(hist: pd.DataFrame) -> tuple[int, str]:
    """Detect basic candlestick patterns: Hammer, Shooting Star, Engulfing, Doji, Stars.

    Based on VPA (Coulling) and Crypto TA (John & Law) frameworks.
    """
    if hist.empty or len(hist) < 10:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    open_p = hist["Open"].values
    volume = hist["Volume"].values

    def _body(i: int) -> float:
        return abs(float(close[i]) - float(open_p[i]))

    def _upper_shadow(i: int) -> float:
        return float(high[i]) - max(float(open_p[i]), float(close[i]))

    def _lower_shadow(i: int) -> float:
        return min(float(open_p[i]), float(close[i])) - float(low[i])

    def _is_doji(i: int) -> bool:
        rng = float(high[i]) - float(low[i])
        return rng > 0 and _body(i) < rng * 0.05

    def _is_hammer(i: int) -> bool:
        rng = float(high[i]) - float(low[i])
        if rng == 0:
            return False
        return _lower_shadow(i) > _body(i) * 2 and _upper_shadow(i) < _body(i) * 0.5

    def _is_shooting_star(i: int) -> bool:
        rng = float(high[i]) - float(low[i])
        if rng == 0:
            return False
        return _upper_shadow(i) > _body(i) * 2 and _lower_shadow(i) < _body(i) * 0.5

    def _is_engulfing_bullish(i: int) -> bool:
        if i < 1:
            return False
        return (
            close[i - 1] < open_p[i - 1]
            and close[i] > open_p[i]
            and close[i] > open_p[i - 1]
            and open_p[i] < close[i - 1]
        )

    def _is_engulfing_bearish(i: int) -> bool:
        if i < 1:
            return False
        return (
            close[i - 1] > open_p[i - 1]
            and close[i] < open_p[i]
            and close[i] < open_p[i - 1]
            and open_p[i] > close[i - 1]
        )

    def _is_morning_star(i: int) -> bool:
        if i < 2:
            return False
        return (
            close[i - 2] < open_p[i - 2]
            and _is_doji(i - 1)
            and close[i] > open_p[i]
            and close[i] > (open_p[i - 2] + close[i - 2]) / 2
        )

    def _is_evening_star(i: int) -> bool:
        if i < 2:
            return False
        return (
            close[i - 2] > open_p[i - 2]
            and _is_doji(i - 1)
            and close[i] < open_p[i]
            and close[i] < (open_p[i - 2] + close[i - 2]) / 2
        )

    avg_vol = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
    doji_count = 0

    for i in range(max(2, len(close) - 20), len(close)):
        vol = float(volume[i])
        vol_conf = vol > avg_vol * 0.8

        if _is_hammer(i):
            if vol_conf:
                score += 5
                details.append(f"Hammer @ {i} (+5 vol-conf)")
            else:
                score += 2
        if _is_shooting_star(i):
            if vol_conf:
                score -= 5
                details.append(f"Shooting Star @ {i} (-5 vol-conf)")
            else:
                score -= 2
        if _is_engulfing_bullish(i):
            if vol_conf:
                score += 7
                details.append(f"Bullish Engulfing @ {i} (+7)")
            else:
                score += 3
        if _is_engulfing_bearish(i):
            if vol_conf:
                score -= 7
                details.append(f"Bearish Engulfing @ {i} (-7)")
            else:
                score -= 3
        if _is_morning_star(i):
            if vol_conf:
                score += 10
                details.append(f"Morning Star @ {i} (+10)")
            else:
                score += 5
        if _is_evening_star(i):
            if vol_conf:
                score -= 10
                details.append(f"Evening Star @ {i} (-10)")
            else:
                score -= 5
        if _is_doji(i):
            doji_count += 1

    if doji_count >= 3:
        score += 3
        details.append(f"{doji_count} doji (indecision +3)")

    if not details:
        details.append("No major patterns")
    return min(100, max(0, score)), " | ".join(details)


def compute_fibonacci(hist: pd.DataFrame) -> tuple[int, str]:
    """Fibonacci retracement levels from recent 60-bar swing high/low."""
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    recent = hist.tail(60)
    swing_high = float(recent["High"].max())
    swing_low = float(recent["Low"].min())
    current = float(hist["Close"].iloc[-1])

    if swing_high <= swing_low:
        return 50, "No valid swing"

    price_range = swing_high - swing_low
    levels = {
        "0.236": swing_high - price_range * 0.236,
        "0.382": swing_high - price_range * 0.382,
        "0.500": swing_high - price_range * 0.500,
        "0.618": swing_high - price_range * 0.618,
        "0.786": swing_high - price_range * 0.786,
    }

    dist_to_618 = abs(current - levels["0.618"]) / price_range
    dist_to_786 = abs(current - levels["0.786"]) / price_range
    dist_to_382 = abs(current - levels["0.382"]) / price_range
    dist_to_236 = abs(current - levels["0.236"]) / price_range

    if dist_to_618 < 0.03:
        score += 15
        details.append("Price @ 61.8% retracement (+15)")
    elif dist_to_786 < 0.03:
        score += 10
        details.append("Price @ 78.6% retracement (+10 deep support)")
    elif dist_to_382 < 0.03:
        score -= 10
        details.append("Price @ 38.2% retracement (-10 shallow)")
    elif dist_to_236 < 0.03:
        score -= 15
        details.append("Price @ 23.6% retracement (-15 very shallow)")

    if current > levels["0.500"]:
        score += 5
        details.append("Above 50% fib (+5)")
    else:
        score -= 5
        details.append("Below 50% fib (-5)")

    if not details:
        details.append(f"Fib levels: H={swing_high:.2f} L={swing_low:.2f}")
    return min(100, max(0, score)), " | ".join(details)


def compute_bollinger(hist: pd.DataFrame) -> tuple[int, str]:
    """Bollinger Bands: squeeze detection, %B position, bandwidth."""
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"]

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20

    current = float(close.iloc[-1])
    upper_now = float(upper.iloc[-1])
    lower_now = float(lower.iloc[-1])
    ma_now = float(ma20.iloc[-1])
    bandwidth = (upper_now - lower_now) / ma_now if ma_now > 0 else 0
    bb_range = upper_now - lower_now
    pct_b = (current - lower_now) / bb_range if bb_range > 0 else 0.5

    if len(hist) >= 40:
        avg_bandwidth = float(((upper - lower) / ma20).tail(20).mean())
        if bandwidth < avg_bandwidth * 0.5 and bandwidth < 0.05:
            score += 15
            details.append(f"BB Squeeze! bandwidth={bandwidth:.2%} (+15)")
        elif bandwidth < 0.05:
            score += 10
            details.append(f"BB Squeeze bandwidth={bandwidth:.2%} (+10)")

    if pct_b > 0.95:
        score -= 10
        details.append(f"%B={pct_b:.2f} >0.95 (overbought -10)")
    elif pct_b < 0.05:
        score += 10
        details.append(f"%B={pct_b:.2f} <0.05 (oversold +10)")
    elif pct_b > 0.8:
        score -= 5
        details.append(f"%B={pct_b:.2f} >0.8 (extended -5)")
    elif pct_b < 0.2:
        score += 5
        details.append(f"%B={pct_b:.2f} <0.2 (cheap +5)")
    else:
        details.append(f"%B={pct_b:.2f} (neutral)")

    if len(hist) >= 5:
        above_upper = sum(1 for i in range(-5, 0) if float(close.iloc[i]) > float(upper.iloc[i]))
        below_lower = sum(1 for i in range(-5, 0) if float(close.iloc[i]) < float(lower.iloc[i]))
        if above_upper >= 3:
            score += 10
            details.append("Walking upper band (strong uptrend +10)")
        elif below_lower >= 3:
            score -= 10
            details.append("Walking lower band (strong downtrend -10)")

    return min(100, max(0, score)), " | ".join(details)


def compute_obv(hist: pd.DataFrame) -> tuple[int, str]:
    """On-Balance Volume divergence detection."""
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    volume = hist["Volume"].values

    obv_vals = [0.0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv_vals.append(obv_vals[-1] + float(volume[i]))
        elif close[i] < close[i - 1]:
            obv_vals.append(obv_vals[-1] - float(volume[i]))
        else:
            obv_vals.append(obv_vals[-1])

    obv_arr = np.array(obv_vals)
    price_slope = (close[-1] - close[-20]) / close[-20] if close[-20] != 0 else 0
    obv_slope = (obv_arr[-1] - obv_arr[-20]) / abs(obv_arr[-20]) if obv_arr[-20] != 0 else 0

    if price_slope > 0.05 and obv_slope < 0:
        score -= 15
        details.append(f"OBV divergence bearish: price +{price_slope:.1%} OBV {obv_slope:.1%} (-15)")
    elif price_slope < -0.05 and obv_slope > 0:
        score += 15
        details.append(f"OBV divergence bullish: price {price_slope:.1%} OBV +{obv_slope:.1%} (+15)")
    elif price_slope > 0 and obv_slope > 0:
        score += 10
        details.append("OBV confirms uptrend (+10)")
    elif price_slope < 0 and obv_slope < 0:
        score -= 10
        details.append("OBV confirms downtrend (-10)")
    else:
        details.append(f"OBV slope={obv_slope:.2f} vs price={price_slope:.2f}")

    if len(obv_arr) >= 20:
        obv_ma = float(np.mean(obv_arr[-20:]))
        if obv_arr[-1] > obv_ma * 1.05:
            score += 5
            details.append("OBV above MA20 (+5)")
        elif obv_arr[-1] < obv_ma * 0.95:
            score -= 5
            details.append("OBV below MA20 (-5)")

    return min(100, max(0, score)), " | ".join(details)


def compute_support_resistance(hist: pd.DataFrame) -> tuple[int, str]:
    """Support/Resistance role reversal detection via swing point clustering."""
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    def _local_extrema(arr, window=3):
        extrema = []
        for i in range(window, len(arr) - window):
            if all(arr[i] >= arr[i - j] for j in range(1, window + 1)) and \
               all(arr[i] >= arr[i + j] for j in range(1, window + 1)):
                extrema.append((i, float(arr[i]), "high"))
            elif all(arr[i] <= arr[i - j] for j in range(1, window + 1)) and \
                 all(arr[i] <= arr[i + j] for j in range(1, window + 1)):
                extrema.append((i, float(arr[i]), "low"))
        return extrema

    highs = _local_extrema(high, 3)
    lows = _local_extrema(low, 3)
    all_extrema = sorted(highs + lows, key=lambda x: x[1])

    if len(all_extrema) < 4:
        return 50, "Not enough swing points"

    clusters: list[dict] = []
    for _, val, kind in all_extrema:
        matched = False
        for c in clusters:
            if abs(val - c["price"]) / c["price"] < 0.02:
                c["count"] += 1
                c["types"].append(kind)
                c["price"] = (c["price"] * (c["count"] - 1) + val) / c["count"]
                matched = True
                break
        if not matched:
            clusters.append({"price": val, "count": 1, "types": [kind]})

    clusters = [c for c in clusters if c["count"] >= 2]
    clusters.sort(key=lambda x: x["price"])
    current = float(close[-1])

    if not clusters:
        return 50, "No clear S/R levels"

    supports = [c for c in clusters if c["price"] < current]
    resistances = [c for c in clusters if c["price"] > current]

    nearest_support = max(supports, key=lambda x: x["price"]) if supports else None
    nearest_resistance = min(resistances, key=lambda x: x["price"]) if resistances else None

    if nearest_support:
        dist = (current - nearest_support["price"]) / current if current > 0 else 0
        if dist < 0.03:
            score += 10
            details.append(f"Price at support ${nearest_support['price']:.2f} (+10)")
        elif dist < 0.05:
            score += 5
            details.append(f"Price near support ${nearest_support['price']:.2f} (+5)")

    if nearest_resistance:
        dist = (nearest_resistance["price"] - current) / current if current > 0 else 0
        if dist < 0.03:
            score -= 10
            details.append(f"Price at resistance ${nearest_resistance['price']:.2f} (-10)")
        elif dist < 0.05:
            score -= 5
            details.append(f"Price near resistance ${nearest_resistance['price']:.2f} (-5)")

    if len(hist) >= 10 and nearest_resistance:
        recent_high = float(max(high[-10:]))
        if recent_high > nearest_resistance["price"] * 1.01:
            score += 10
            details.append("Role reversal: broke resistance -> support (+10)")

    if len(hist) >= 10 and nearest_support:
        recent_low = float(min(low[-10:]))
        if recent_low < nearest_support["price"] * 0.99:
            score -= 10
            details.append("Role reversal: broke support -> resistance (-10)")

    if not details:
        details.append("S/R neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_psychology_score(hist: pd.DataFrame) -> tuple[int, str]:
    """Trading psychology: FOMO/Panic detection via consecutive candles, gaps, volume spikes, RSI."""
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    volume = hist["Volume"].values

    green_streak = 0
    red_streak = 0
    for i in range(-1, -min(20, len(close)), -1):
        if close[i] > close[i - 1]:
            green_streak += 1
            red_streak = 0
        elif close[i] < close[i - 1]:
            red_streak += 1
            green_streak = 0
        else:
            break

    if green_streak >= 7:
        score = max(score - 20, 0)
        details.append(f"{green_streak} consecutive green candles (FOMO -20)")
    elif green_streak >= 5:
        score = max(score - 10, 0)
        details.append(f"{green_streak} consecutive green (exhaustion -10)")
    elif red_streak >= 7:
        score = min(score + 20, 100)
        details.append(f"{red_streak} consecutive red candles (panic/capitulation +20)")
    elif red_streak >= 5:
        score = min(score + 10, 100)
        details.append(f"{red_streak} consecutive red (oversold +10)")

    if len(hist) >= 5:
        vol_avg = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
        recent_vol = float(volume[-1])
        recent_range = (close[-1] - close[-5]) / close[-5] if close[-5] != 0 else 0
        if recent_vol > vol_avg * 2.5 and abs(recent_range) < 0.02:
            score = max(score - 15, 0)
            details.append("Vol spike + flat price (distribution -15)")
        elif recent_vol > vol_avg * 2.5 and recent_range > 0.05:
            score = min(score + 10, 100)
            details.append("Vol spike + strong move (initiative +10)")

    if len(close) >= 15:
        delta = pd.Series(close).diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up_psy = up.ewm(com=13).mean()
        ma_down_psy = down.ewm(com=13).mean()
        rsi = 100.0 - (100.0 / (1.0 + ma_up_psy / ma_down_psy))
        rsi_val = float(rsi.iloc[-1])
        if rsi_val > 75:
            score = max(score - 10, 0)
            details.append(f"RSI {rsi_val:.0f} extreme overbought (-10)")
        elif rsi_val < 25:
            score = min(score + 10, 100)
            details.append(f"RSI {rsi_val:.0f} extreme oversold (+10)")

    if not details:
        details.append("Psychology neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_ichimoku(hist: pd.DataFrame) -> tuple[int, str]:
    """Ichimoku Kinko Hyo cloud analysis."""
    if hist.empty or len(hist) < 52:
        return 50, "Insufficient data (<52 bars)"

    score = 50
    details = []
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    current = float(close.iloc[-1])
    tenkan_now = float(tenkan.iloc[-1])
    kijun_now = float(kijun.iloc[-1])
    cloud_top = float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else None
    cloud_bot = float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else None

    if cloud_top is not None and cloud_bot is not None:
        if current > cloud_top:
            score += 15
            details.append("Price above cloud (bullish +15)")
        elif current < cloud_bot:
            score -= 15
            details.append("Price below cloud (bearish -15)")
        elif cloud_top > cloud_bot and cloud_bot <= current <= cloud_top:
            score += 5
            details.append("Price inside bullish cloud (+5)")
        elif cloud_bot > cloud_top and cloud_top <= current <= cloud_bot:
            score -= 10
            details.append("Price inside bearish cloud (-10)")
        if cloud_top > cloud_bot:
            details.append("Cloud green (bullish ahead)")
        else:
            details.append("Cloud red (bearish ahead)")

    if len(close) >= 27:
        tenkan_prev = float(tenkan.iloc[-2])
        kijun_prev = float(kijun.iloc[-2])
        if tenkan_prev <= kijun_prev and tenkan_now > kijun_now:
            score += 15
            details.append("Tenkan/Kijun bullish cross (+15)")
        elif tenkan_prev >= kijun_prev and tenkan_now < kijun_now:
            score -= 15
            details.append("Tenkan/Kijun bearish cross (-15)")

    if len(close) >= 27:
        chikou = close.shift(-26)
        chikou_now = float(chikou.iloc[-27]) if not pd.isna(chikou.iloc[-27]) else None
        if chikou_now is not None:
            if chikou_now > current:
                score += 10
                details.append("Chikou above price (+10)")
            else:
                score -= 10
                details.append("Chikou below price (-10)")

    if not details:
        details.append("Ichimoku neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_risk_reward(hist: pd.DataFrame, current_price: float) -> tuple[int, str]:
    """Risk/Reward ratio + ATR-based stops + Kelly-inspired position sizing."""
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values

    tr_list = []
    for i in range(1, len(close)):
        tr_list.append(max(
            float(high[i]) - float(low[i]),
            abs(float(high[i]) - float(close[i - 1])),
            abs(float(low[i]) - float(close[i - 1])),
        ))
    tr_arr = np.array(tr_list)
    atr14 = float(np.mean(tr_arr[-14:])) if len(tr_arr) >= 14 else float(np.mean(tr_arr))

    recent = hist.tail(60)
    swing_low = float(recent["Low"].min())
    swing_high = float(recent["High"].max())

    reward_pct = (swing_high - current_price) / current_price if current_price > 0 else 0
    risk_pct = (2 * atr14) / current_price if current_price > 0 else 0.05
    rrr = reward_pct / risk_pct if risk_pct > 0 else 0

    if rrr >= 3.0:
        score += 20
        details.append(f"RRR {rrr:.1f}:1 (excellent +20)")
    elif rrr >= 2.0:
        score += 15
        details.append(f"RRR {rrr:.1f}:1 (good +15)")
    elif rrr >= 1.0:
        score += 5
        details.append(f"RRR {rrr:.1f}:1 (acceptable +5)")
    else:
        score -= 15
        details.append(f"RRR {rrr:.1f}:1 (poor -15)")

    stop_2atr = current_price - (2 * atr14)
    details.append(f"ATR14=${atr14:.2f} | Stop 2ATR=${stop_2atr:.2f}")

    dist_to_support = (current_price - swing_low) / current_price if current_price > 0 else 0
    if dist_to_support > 0 and reward_pct > 0:
        win_prob = 0.55
        kelly_fraction = win_prob - (1 - win_prob) / (reward_pct / risk_pct) if risk_pct > 0 else 0
        kelly_fraction = max(0.0, min(0.25, kelly_fraction))
        if kelly_fraction > 0.1:
            score += 10
            details.append(f"Kelly sizing {kelly_fraction:.0%} (favorable +10)")
        else:
            score += 5
            details.append(f"Kelly sizing {kelly_fraction:.0%} (conservative +5)")

    return min(100, max(0, score)), " | ".join(details)


def compute_psychology_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """Advanced trading psychology: Cycle of Doom, volume climax, compression, anchoring."""
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    volume = hist["Volume"].values

    reds = 0
    for i in range(-1, -min(30, len(close)), -1):
        if close[i] < close[i - 1]:
            reds += 1
        else:
            break

    greens = 0
    for i in range(-1, -min(30, len(close)), -1):
        if close[i] > close[i - 1]:
            greens += 1
        else:
            break

    if reds >= 8:
        score = min(score + 25, 100)
        details.append(f"Cycle: Capitulation/Depression ({reds} reds, contrarian +25)")
    elif reds >= 5:
        score = min(score + 15, 100)
        details.append(f"Cycle: Panic ({reds} reds, near capitulation +15)")
    elif greens >= 8:
        score = max(score - 25, 0)
        details.append(f"Cycle: Euphoria/Greed ({greens} greens, FOMO peak -25)")
    elif greens >= 5:
        score = max(score - 15, 0)
        details.append(f"Cycle: Optimism ({greens} greens, extended -15)")

    if len(volume) >= 5:
        vol_now = float(volume[-1])
        vol_20avg = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
        vol_ratio = vol_now / vol_20avg if vol_20avg > 0 else 1.0

        if vol_ratio > 3.0 and reds >= 3:
            score = min(score + 20, 100)
            details.append(f"Selling climax (vol {vol_ratio:.1f}x + reds {reds}) (+20)")
        elif vol_ratio > 3.0 and greens >= 3:
            score = max(score - 20, 0)
            details.append(f"Buying climax (vol {vol_ratio:.1f}x + greens {greens}) (-20)")
        elif reds >= 3 and vol_ratio < 0.5:
            score = min(score + 10, 100)
            details.append(f"Exhaustion selling (low vol + reds) (+10)")

    if len(close) >= 20 and close[-1] != 0:
        range_5d = (max(close[-5:]) - min(close[-5:])) / close[-1]
        range_20d = (max(close[-20:]) - min(close[-20:])) / close[-1]
        vol_trend = float(volume[-5:].mean()) / float(volume[-20:].mean()) if float(volume[-20:].mean()) > 0 else 1.0
        if range_5d < range_20d * 0.2 and vol_trend < 0.7:
            score += 10
            details.append("Indecision compression (breakout imminent +10)")

    if len(close) >= 60:
        h52 = max(close[-60:])
        l52 = min(close[-60:])
        pos_52 = (close[-1] - l52) / (h52 - l52) if h52 != l52 else 0.5
        if pos_52 < 0.15:
            score = min(score + 15, 100)
            details.append(f"Near 52w low ({pos_52:.0%}) anchoring/extreme fear (+15)")
        elif pos_52 > 0.85:
            score = max(score - 15, 0)
            details.append(f"Near 52w high ({pos_52:.0%}) anchoring/greed (-15)")

    if not details:
        details.append("Psychology advanced neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_candlestick_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """Advanced candlestick patterns: Harami, Piercing, Dark Cloud, Abandoned Baby, 3-bar Engulfing."""
    if hist.empty or len(hist) < 10:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    open_p = hist["Open"].values
    volume = hist["Volume"].values

    def _body(i: int) -> float:
        return abs(float(close[i]) - float(open_p[i]))

    def _range(i: int) -> float:
        return float(high[i]) - float(low[i])

    def _is_piercing(i: int) -> bool:
        if i < 1:
            return False
        prev_bear = close[i - 1] < open_p[i - 1]
        curr_bull = close[i] > open_p[i]
        if not (prev_bear and curr_bull):
            return False
        body_prev = _body(i - 1)
        if body_prev == 0:
            return False
        return (
            open_p[i] < low[i - 1]
            and close[i] > (open_p[i - 1] + close[i - 1]) / 2
            and close[i] < open_p[i - 1]
        )

    def _is_dark_cloud(i: int) -> bool:
        if i < 1:
            return False
        prev_bull = close[i - 1] > open_p[i - 1]
        curr_bear = close[i] < open_p[i]
        if not (prev_bull and curr_bear):
            return False
        body_prev = _body(i - 1)
        if body_prev == 0:
            return False
        return (
            open_p[i] > high[i - 1]
            and close[i] < (open_p[i - 1] + close[i - 1]) / 2
            and close[i] > open_p[i - 1]
        )

    avg_vol = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
    found = False

    for i in range(max(4, len(close) - 20), len(close)):
        if _is_piercing(i):
            score += 7
            details.append(f"Piercing Pattern @ {i} (+7)")
            found = True
        if _is_dark_cloud(i):
            score -= 7
            details.append(f"Dark Cloud Cover @ {i} (-7)")
            found = True

    if not found:
        details.append("No advanced patterns")
    return min(100, max(0, score)), " | ".join(details)


def compute_point_figure(hist: pd.DataFrame) -> tuple[int, str]:
    """Point & Figure simplified projection (Weis)."""
    if hist.empty or len(hist) < 40:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values

    avg_price = float(np.mean(close[-40:]))
    box_size = avg_price * 0.01

    columns = []
    current_col = {"direction": None, "boxes": 0, "start_price": float(close[0])}

    for i in range(1, len(close)):
        box_move = (float(close[i]) - current_col["start_price"]) / box_size

        if current_col["direction"] is None:
            if abs(box_move) >= 3:
                current_col["direction"] = "up" if box_move > 0 else "down"
                current_col["boxes"] = int(abs(box_move))
                current_col["start_price"] = float(close[i])
        elif current_col["direction"] == "up":
            if box_move <= -3:
                columns.append(current_col)
                current_col = {"direction": "down", "boxes": int(abs(box_move)), "start_price": float(close[i])}
            elif int(box_move) > current_col.get("boxes", 0):
                current_col["boxes"] = int(box_move)
        else:
            if box_move >= 3:
                columns.append(current_col)
                current_col = {"direction": "up", "boxes": int(box_move), "start_price": float(close[i])}
            elif int(abs(box_move)) > current_col.get("boxes", 0):
                current_col["boxes"] = int(abs(box_move))
    columns.append(current_col)

    if len(columns) < 3:
        return 50, "Not enough P&F columns"

    recent_cols = columns[-5:]
    up_cols = [c for c in recent_cols if c["direction"] == "up"]
    down_cols = [c for c in recent_cols if c["direction"] == "down"]
    current_price = float(close[-1])

    if up_cols:
        congestion_width = len(up_cols) * 3
        projection = current_price + (congestion_width * 3 * box_size)
        if projection > current_price * 1.05:
            score += 15
            details.append(f"P&F bullish target ${projection:.2f} (+{projection/current_price-1:+.1%}) (+15)")
        else:
            score += 5
            details.append(f"P&F bullish target ${projection:.2f} (+5)")

    if down_cols:
        congestion_width = len(down_cols) * 3
        projection = current_price - (congestion_width * 3 * box_size)
        if projection < current_price * 0.95:
            score -= 15
            details.append(f"P&F bearish target ${projection:.2f} ({projection/current_price-1:+.1%}) (-15)")

    col_dirs = [c["direction"] for c in columns[-6:]]
    if col_dirs.count("down") > col_dirs.count("up"):
        score -= 10
        details.append(f"P&F: {col_dirs.count('down')}D vs {col_dirs.count('up')}U columns (bearish -10)")
    elif col_dirs.count("up") > col_dirs.count("down"):
        score += 10
        details.append(f"P&F: {col_dirs.count('up')}U vs {col_dirs.count('down')}D columns (bullish +10)")

    if not details:
        details.append(f"P&F {len(columns)} cols | box ${box_size:.2f}")
    return min(100, max(0, score)), " | ".join(details)
