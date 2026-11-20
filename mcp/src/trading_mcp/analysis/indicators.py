"""Technical indicators on one 0-100 scale (50 = neutral; documented, unvalidated rules).

Rules of this module (SIG-08, SIG-13, SIG-14, SIG-21):

- Every score is ``50 + points``, clipped to [0, 100]. Each bullish rule has
  a mirror bearish rule with the same points, so a driftless random walk
  gives a mean near 50 (tested in ``tests/test_signal_null.py``).
- Rules that carry no direction (Bollinger squeeze, doji clusters, range
  compression) are reported in the detail but add no points.
- The last row is the last COMPLETE session (the provider drops the open bar).
- ATR is Wilder's (see :mod:`trading_mcp.analysis.ta_core`); Bollinger bands
  use the population standard deviation (ddof=0), as in Bollinger's definition.
- No rule here was validated out of sample.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_mcp.analysis.ta_core import atr_last


def _clip(score: float) -> int:
    return int(round(min(100.0, max(0.0, score))))


def _streak(close: np.ndarray, max_bars: int = 30) -> tuple[str | None, int]:
    """Direction (``up``/``down``) and length of the CURRENT run of closes (no flat bar)."""
    if len(close) < 2:
        return None, 0
    last = float(close[-1]) - float(close[-2])
    if last == 0:
        return None, 0
    direction = "up" if last > 0 else "down"
    count = 0
    for i in range(len(close) - 1, max(0, len(close) - 1 - max_bars), -1):
        change = float(close[i]) - float(close[i - 1])
        if (direction == "up" and change > 0) or (direction == "down" and change < 0):
            count += 1
        else:
            break
    return direction, count


def _trend_sign(close: np.ndarray, bars: int = 20) -> int:
    """Sign of the close change over ``bars`` bars (0 when flat or too short)."""
    if len(close) <= bars:
        return 0
    change = float(close[-1]) - float(close[-1 - bars])
    return 1 if change > 0 else -1 if change < 0 else 0


def compute_candlestick_patterns(hist: pd.DataFrame) -> tuple[int, str]:
    """Hammer/shooting star, engulfing and morning/evening stars over the last 20 bars.

    Mirror pairs score +-5 (+-2 without volume above 0.8x the prior 20-bar
    average), +-7 (+-3) and +-10 (+-5). Doji clusters are reported, not scored.
    """
    if hist.empty or len(hist) < 10:
        return 50, "Insufficient data"

    score = 50.0
    details: list[str] = []
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    open_p = hist["Open"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)

    def body(i: int) -> float:
        return abs(close[i] - open_p[i])

    def upper(i: int) -> float:
        return high[i] - max(open_p[i], close[i])

    def lower(i: int) -> float:
        return min(open_p[i], close[i]) - low[i]

    def doji(i: int) -> bool:
        rng = high[i] - low[i]
        return rng > 0 and body(i) < rng * 0.05

    def hammer(i: int) -> bool:
        return high[i] > low[i] and lower(i) > body(i) * 2 and upper(i) < body(i) * 0.5

    def shooting_star(i: int) -> bool:
        return high[i] > low[i] and upper(i) > body(i) * 2 and lower(i) < body(i) * 0.5

    def bull_engulf(i: int) -> bool:
        return (close[i - 1] < open_p[i - 1] and close[i] > open_p[i]
                and close[i] > open_p[i - 1] and open_p[i] < close[i - 1])

    def bear_engulf(i: int) -> bool:
        return (close[i - 1] > open_p[i - 1] and close[i] < open_p[i]
                and close[i] < open_p[i - 1] and open_p[i] > close[i - 1])

    def morning_star(i: int) -> bool:
        return (close[i - 2] < open_p[i - 2] and doji(i - 1) and close[i] > open_p[i]
                and close[i] > (open_p[i - 2] + close[i - 2]) / 2)

    def evening_star(i: int) -> bool:
        return (close[i - 2] > open_p[i - 2] and doji(i - 1) and close[i] < open_p[i]
                and close[i] < (open_p[i - 2] + close[i - 2]) / 2)

    rules = (
        (hammer, 5, 2, "Hammer"), (shooting_star, -5, -2, "Shooting Star"),
        (bull_engulf, 7, 3, "Bullish Engulfing"), (bear_engulf, -7, -3, "Bearish Engulfing"),
        (morning_star, 10, 5, "Morning Star"), (evening_star, -10, -5, "Evening Star"),
    )
    doji_count = 0
    for i in range(max(2, len(close) - 20), len(close)):
        prior = volume[max(0, i - 20):i]
        vol_conf = len(prior) > 0 and volume[i] > prior.mean() * 0.8
        for rule, strong, weak, label in rules:
            if rule(i):
                points = strong if vol_conf else weak
                score += points
                details.append(f"{label} @ {i} ({points:+d})")
        doji_count += int(doji(i))
    if doji_count >= 3:
        details.append(f"{doji_count} doji (indecision, not scored)")
    if not details:
        details.append("No major patterns")
    return _clip(score), " | ".join(details)


def compute_fibonacci(hist: pd.DataFrame) -> tuple[int, str]:
    """Direction-aware Fibonacci zone of the last 60-bar swing.

    Up swing (low before high): a pullback into the 50-78.6% retracement
    zone scores +8, a pullback beyond 78.6% scores -8. Down swing: a bounce
    into the 50-78.6% zone scores -8, a bounce beyond 78.6% scores +8.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"
    recent = hist.tail(60)
    high_i = int(np.argmax(recent["High"].to_numpy(dtype=float)))
    low_i = int(np.argmin(recent["Low"].to_numpy(dtype=float)))
    swing_high = float(recent["High"].iloc[high_i])
    swing_low = float(recent["Low"].iloc[low_i])
    current = float(hist["Close"].iloc[-1])
    if swing_high <= swing_low:
        return 50, "No valid swing"
    span = swing_high - swing_low
    score = 50.0
    if low_i < high_i:
        frac = (swing_high - current) / span
        label = f"Up swing {swing_low:.2f}->{swing_high:.2f}, retracement {frac:.0%}"
        if 0.5 <= frac <= 0.786:
            score += 8
            label += " (golden zone support +8)"
        elif frac > 0.786:
            score -= 8
            label += " (swing failure -8)"
    else:
        frac = (current - swing_low) / span
        label = f"Down swing {swing_high:.2f}->{swing_low:.2f}, bounce {frac:.0%}"
        if 0.5 <= frac <= 0.786:
            score -= 8
            label += " (golden zone resistance -8)"
        elif frac > 0.786:
            score += 8
            label += " (swing failure +8)"
    return _clip(score), label


def compute_bollinger(hist: pd.DataFrame) -> tuple[int, str]:
    """Bollinger(20, 2, population std): %B extremes and band walks; a squeeze is not scored."""
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50.0
    details: list[str] = []
    close = hist["Close"].astype(float)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std(ddof=0)
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20

    current = float(close.iloc[-1])
    band = float(upper.iloc[-1] - lower.iloc[-1])
    ma_now = float(ma20.iloc[-1])
    pct_b = (current - float(lower.iloc[-1])) / band if band > 0 else 0.5
    bandwidth = band / ma_now if ma_now > 0 else 0.0

    if len(hist) >= 40:
        avg_bw = float(((upper - lower) / ma20).tail(20).mean())
        if avg_bw > 0 and bandwidth < avg_bw * 0.5:
            details.append(f"BB squeeze bandwidth={bandwidth:.2%} (direction-neutral, not scored)")

    for threshold, points, label in ((0.95, 10, "overbought"), (0.8, 5, "extended")):
        if pct_b > threshold:
            score -= points
            details.append(f"%B={pct_b:.2f} >{threshold} ({label} -{points})")
            break
        if pct_b < 1 - threshold:
            score += points
            details.append(f"%B={pct_b:.2f} <{1 - threshold:.2f} ({'oversold' if points == 10 else 'cheap'} +{points})")
            break
    else:
        details.append(f"%B={pct_b:.2f} (neutral)")

    above = sum(1 for i in range(-5, 0) if float(close.iloc[i]) > float(upper.iloc[i]))
    below = sum(1 for i in range(-5, 0) if float(close.iloc[i]) < float(lower.iloc[i]))
    if above >= 3:
        score += 10
        details.append("Walking upper band (trend +10)")
    elif below >= 3:
        score -= 10
        details.append("Walking lower band (trend -10)")
    return _clip(score), " | ".join(details)


def compute_obv(hist: pd.DataFrame) -> tuple[int, str]:
    """On-Balance Volume: divergence (+-15) or confirmation (+-10) over 20 bars, OBV vs its mean (+-5).

    The OBV change is normalized by the volume traded in the window, so it
    is in [-1, 1] and never divides by an OBV level near zero.
    """
    if hist.empty or len(hist) < 21:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    signed = np.sign(np.diff(close)) * volume[1:]
    obv = np.concatenate([[0.0], np.cumsum(signed)])
    traded = float(volume[-19:].sum())
    price_slope = (close[-1] - close[-20]) / close[-20] if close[-20] != 0 else 0.0
    obv_slope = (obv[-1] - obv[-20]) / traded if traded > 0 else 0.0

    score = 50.0
    if price_slope > 0.05 and obv_slope < 0:
        score -= 15
        detail = f"OBV bearish divergence: price {price_slope:+.1%}, OBV flow {obv_slope:+.2f} (-15)"
    elif price_slope < -0.05 and obv_slope > 0:
        score += 15
        detail = f"OBV bullish divergence: price {price_slope:+.1%}, OBV flow {obv_slope:+.2f} (+15)"
    elif price_slope > 0 and obv_slope > 0:
        score += 10
        detail = "OBV confirms the rise (+10)"
    elif price_slope < 0 and obv_slope < 0:
        score -= 10
        detail = "OBV confirms the fall (-10)"
    else:
        detail = f"OBV flow {obv_slope:+.2f} vs price {price_slope:+.1%}"
    adv = float(volume[-20:].mean())
    gap = obv[-1] - float(np.mean(obv[-20:]))
    if adv > 0 and gap > adv:
        score += 5
        detail += " | OBV above its 20-bar mean (+5)"
    elif adv > 0 and gap < -adv:
        score -= 5
        detail += " | OBV below its 20-bar mean (-5)"
    return _clip(score), detail


def compute_support_resistance(hist: pd.DataFrame) -> tuple[int, str]:
    """Swing-cluster support/resistance: proximity (+-10 / +-5) and failed breaks (+-5).

    A cluster is two or more confirmed swing points (3 bars each side) within
    2%. Near support (<3% / <5%) scores +10 / +5, near resistance mirrors it.
    A poke above resistance in the last 10 bars that closed back below scores
    -5 (rejection); a poke below support that recovered scores +5.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    points: list[float] = []
    for i in range(3, len(close) - 3):
        if high[i] == high[i - 3:i + 4].max():
            points.append(float(high[i]))
        if low[i] == low[i - 3:i + 4].min():
            points.append(float(low[i]))
    if len(points) < 4:
        return 50, "Not enough swing points"
    clusters: list[dict] = []
    for value in sorted(points):
        if clusters and abs(value - clusters[-1]["price"]) / clusters[-1]["price"] < 0.02:
            c = clusters[-1]
            c["count"] += 1
            c["price"] += (value - c["price"]) / c["count"]
        else:
            clusters.append({"price": value, "count": 1})
    clusters = [c for c in clusters if c["count"] >= 2]
    if not clusters:
        return 50, "No clear S/R levels"

    current = float(close[-1])
    supports = [c["price"] for c in clusters if c["price"] < current]
    resistances = [c["price"] for c in clusters if c["price"] > current]
    score = 50.0
    details: list[str] = []
    if supports:
        level = max(supports)
        dist = (current - level) / current
        if dist < 0.03:
            score += 10
            details.append(f"At support ${level:.2f} (+10)")
        elif dist < 0.05:
            score += 5
            details.append(f"Near support ${level:.2f} (+5)")
        if float(low[-10:].min()) < level * 0.99:
            score += 5
            details.append(f"Failed break below ${level:.2f}, recovered (+5)")
    if resistances:
        level = min(resistances)
        dist = (level - current) / current
        if dist < 0.03:
            score -= 10
            details.append(f"At resistance ${level:.2f} (-10)")
        elif dist < 0.05:
            score -= 5
            details.append(f"Near resistance ${level:.2f} (-5)")
        if float(high[-10:].max()) > level * 1.01:
            score -= 5
            details.append(f"Rejected above ${level:.2f} (-5)")
    if not details:
        details.append("S/R neutral")
    return _clip(score), " | ".join(details)


def compute_psychology_score(hist: pd.DataFrame) -> tuple[int, str]:
    """Contrarian streak rule and volume-spike rule (both mirrored).

    Current run of 7+ up closes -20 (5+: -10); 7+ down closes +20 (5+: +10).
    A volume spike (>2.5x the prior 20-bar average) with a flat 5-bar move is
    absorption: -10 after a 20-bar rise, +10 after a fall. A spike with a
    5-bar move beyond +-5% scores +-10 (initiative). RSI is scored in Price Action.
    """
    if hist.empty or len(hist) < 21:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    score = 50.0
    details: list[str] = []
    direction, run = _streak(close, 20)
    if direction == "up" and run >= 5:
        points = 20 if run >= 7 else 10
        score -= points
        details.append(f"{run} consecutive up closes (exhaustion -{points})")
    elif direction == "down" and run >= 5:
        points = 20 if run >= 7 else 10
        score += points
        details.append(f"{run} consecutive down closes (capitulation +{points})")

    prior = float(volume[-21:-1].mean())
    move_5 = (close[-1] - close[-6]) / close[-6] if close[-6] != 0 else 0.0
    if prior > 0 and volume[-1] > prior * 2.5:
        if abs(move_5) < 0.02:
            sign = _trend_sign(close)
            if sign > 0:
                score -= 10
                details.append("Volume spike with no progress after a rise (absorption -10)")
            elif sign < 0:
                score += 10
                details.append("Volume spike with no progress after a fall (absorption +10)")
        elif move_5 > 0.05:
            score += 10
            details.append("Volume spike on a strong rise (initiative +10)")
        elif move_5 < -0.05:
            score -= 10
            details.append("Volume spike on a strong fall (initiative -10)")
    if not details:
        details.append("Psychology neutral")
    return _clip(score), " | ".join(details)


def compute_ichimoku(hist: pd.DataFrame) -> tuple[int, str]:
    """Ichimoku: cloud position (+-15, inside +-5), Tenkan/Kijun cross (+-15), Chikou (+-10).

    The cloud plotted at today is built from data 26 bars ago (no look-ahead).
    Chikou compares today's close with the close 26 bars ago (the lagging line
    plotted 26 bars back): above +10, below -10.
    """
    if hist.empty or len(hist) < 78:
        return 50, "Insufficient data (<78 bars)"
    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    score = 50.0
    details: list[str] = []
    current = float(close.iloc[-1])
    a, b = span_a.iloc[-1], span_b.iloc[-1]
    if pd.notna(a) and pd.notna(b):
        top, bottom = max(float(a), float(b)), min(float(a), float(b))
        green = float(a) >= float(b)
        if current > top:
            score += 15
            details.append("Price above cloud (+15)")
        elif current < bottom:
            score -= 15
            details.append("Price below cloud (-15)")
        elif green:
            score += 5
            details.append("Price inside a green cloud (+5)")
        else:
            score -= 5
            details.append("Price inside a red cloud (-5)")
    t_now, k_now = float(tenkan.iloc[-1]), float(kijun.iloc[-1])
    t_prev, k_prev = float(tenkan.iloc[-2]), float(kijun.iloc[-2])
    if t_prev <= k_prev and t_now > k_now:
        score += 15
        details.append("Tenkan/Kijun bullish cross (+15)")
    elif t_prev >= k_prev and t_now < k_now:
        score -= 15
        details.append("Tenkan/Kijun bearish cross (-15)")
    lagged = float(close.iloc[-27])
    if current > lagged:
        score += 10
        details.append("Chikou above the price 26 bars ago (+10)")
    elif current < lagged:
        score -= 10
        details.append("Chikou below the price 26 bars ago (-10)")
    if not details:
        details.append("Ichimoku neutral")
    return _clip(score), " | ".join(details)


def compute_risk_reward(hist: pd.DataFrame, current_price: float) -> tuple[int, str]:
    """Room to the 60-bar high vs a 2x Wilder-ATR stop (informational; not in the composite).

    The trade plan (:mod:`trading_mcp.analysis.signal_engine`) computes the
    real reward/risk; this score is kept for the indicator table only.
    """
    if hist.empty or len(hist) < 20 or not current_price or current_price <= 0:
        return 50, "Insufficient data"
    atr = atr_last(hist)
    if atr is None:
        return 50, "ATR unavailable"
    swing_high = float(hist.tail(60)["High"].max())
    reward = max(0.0, swing_high - current_price)
    rrr = reward / (2 * atr)
    if rrr >= 3.0:
        score = 70
    elif rrr >= 2.0:
        score = 60
    elif rrr >= 1.0:
        score = 50
    else:
        score = 35
    return score, f"Room to 60-bar high {reward:.2f} vs 2 ATR {2 * atr:.2f}: {rrr:.1f}:1 | ATR14(Wilder)={atr:.2f}"


def compute_psychology_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """Climax and anchoring rules (mirrored); the streak itself is scored by :func:`compute_psychology_score`.

    Volume > 3x the prior 20-bar average after 3+ down closes: +20 (selling
    climax); after 3+ up closes: -20 (buying climax). Volume < 0.5x with 3+
    down closes: +10 (selling dries up); with 3+ up closes: -10. Price in the
    bottom 15% of the 60-bar close range +15, top 15% -15 (anchoring, contrarian).
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    volume = hist["Volume"].to_numpy(dtype=float)
    score = 50.0
    details: list[str] = []
    direction, run = _streak(close, 30)
    prior = float(volume[-21:-1].mean())
    ratio = volume[-1] / prior if prior > 0 else 1.0
    if run >= 3:
        if ratio > 3.0:
            points = 20 if direction == "down" else -20
            details.append(f"{'Selling' if direction == 'down' else 'Buying'} climax (vol {ratio:.1f}x after {run} "
                           f"{direction} closes, {points:+d})")
            score += points
        elif ratio < 0.5:
            points = 10 if direction == "down" else -10
            details.append(f"{'Selling' if direction == 'down' else 'Buying'} dries up (vol {ratio:.1f}x, {points:+d})")
            score += points
    if len(close) >= 20 and close[-1] != 0:
        range_5 = (max(close[-5:]) - min(close[-5:])) / close[-1]
        range_20 = (max(close[-20:]) - min(close[-20:])) / close[-1]
        if range_20 > 0 and range_5 < range_20 * 0.2:
            details.append("Range compression (direction-neutral, not scored)")
    if len(close) >= 60:
        h60, l60 = max(close[-60:]), min(close[-60:])
        pos = (close[-1] - l60) / (h60 - l60) if h60 != l60 else 0.5
        if pos < 0.15:
            score += 15
            details.append(f"Near the 60-bar low ({pos:.0%}) (+15)")
        elif pos > 0.85:
            score -= 15
            details.append(f"Near the 60-bar high ({pos:.0%}) (-15)")
    if not details:
        details.append("Psychology advanced neutral")
    return _clip(score), " | ".join(details)


def compute_candlestick_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """Piercing line (+7) and dark cloud cover (-7) over the last 20 bars."""
    if hist.empty or len(hist) < 10:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    high = hist["High"].to_numpy(dtype=float)
    low = hist["Low"].to_numpy(dtype=float)
    open_p = hist["Open"].to_numpy(dtype=float)
    score = 50.0
    details: list[str] = []
    for i in range(max(4, len(close) - 20), len(close)):
        prev_body = abs(close[i - 1] - open_p[i - 1])
        if prev_body == 0:
            continue
        mid = (open_p[i - 1] + close[i - 1]) / 2
        if (close[i - 1] < open_p[i - 1] and close[i] > open_p[i] and open_p[i] < low[i - 1]
                and mid < close[i] < open_p[i - 1]):
            score += 7
            details.append(f"Piercing Pattern @ {i} (+7)")
        if (close[i - 1] > open_p[i - 1] and close[i] < open_p[i] and open_p[i] > high[i - 1]
                and open_p[i - 1] < close[i] < mid):
            score -= 7
            details.append(f"Dark Cloud Cover @ {i} (-7)")
    if not details:
        details.append("No advanced patterns")
    return _clip(score), " | ".join(details)


def _pf_columns(close: np.ndarray, box: float, reversal: int = 3) -> list[dict]:
    """Close-only Point & Figure columns (3-box reversal from the column extreme)."""
    columns: list[dict] = []
    direction: str | None = None
    extreme = start = float(close[0])
    for price in close[1:]:
        price = float(price)
        if direction is None:
            if abs(price - start) >= reversal * box:
                direction = "up" if price > start else "down"
                extreme = price
        elif direction == "up":
            if price > extreme:
                extreme = price
            elif extreme - price >= reversal * box:
                columns.append({"direction": "up", "high": extreme, "low": start})
                direction, start, extreme = "down", extreme, price
        else:
            if price < extreme:
                extreme = price
            elif price - extreme >= reversal * box:
                columns.append({"direction": "down", "high": start, "low": extreme})
                direction, start, extreme = "up", extreme, price
    if direction is not None:
        columns.append({"direction": direction, "high": max(start, extreme), "low": min(start, extreme),
                        "open": True})
    return columns


def compute_point_figure(hist: pd.DataFrame) -> tuple[int, str]:
    """Point & Figure (1% box, 3-box reversal): double-top breakout +15, double-bottom breakdown -15.

    The column majority of the last six columns adds +-5.
    """
    if hist.empty or len(hist) < 40:
        return 50, "Insufficient data"
    close = hist["Close"].to_numpy(dtype=float)
    box = float(np.mean(close[-40:])) * 0.01
    columns = _pf_columns(close, box)
    if len(columns) < 3:
        return 50, "Not enough P&F columns"
    score = 50.0
    details: list[str] = []
    current = columns[-1]
    same = [c for c in columns[:-1] if c["direction"] == current["direction"]]
    if same:
        if current["direction"] == "up" and current["high"] > same[-1]["high"]:
            score += 15
            details.append(f"P&F double-top breakout above {same[-1]['high']:.2f} (+15)")
        elif current["direction"] == "down" and current["low"] < same[-1]["low"]:
            score -= 15
            details.append(f"P&F double-bottom breakdown below {same[-1]['low']:.2f} (-15)")
    dirs = [c["direction"] for c in columns[-6:]]
    ups, downs = dirs.count("up"), dirs.count("down")
    if ups > downs:
        score += 5
        details.append(f"P&F {ups}U vs {downs}D columns (+5)")
    elif downs > ups:
        score -= 5
        details.append(f"P&F {ups}U vs {downs}D columns (-5)")
    if not details:
        details.append(f"P&F {len(columns)} columns | box {box:.2f}")
    return _clip(score), " | ".join(details)
