#!/usr/bin/env python3
"""
Market Accumulation Scanner
Scans US/EU tickers through 6-dimension scoring (Wyckoff, VP, PA,
Competitive Positioning, Sentiment, Fundamentals) with Earnings Quality
Modifier, Value Trap Check, Rally Velocity, and Price vs Consensus.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"

# Import the 6-dimension sentiment engine
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from sentiment_engine import compute_sentiment as compute_sentiment_6d
from sentiment_engine import earnings_proximity_adjustment

# Cache SPX data for momentum comparison (shared across all tickers)
_SPX_HIST: pd.DataFrame | None = None

# Global flags for news and social sentiment
_FETCH_NEWS: bool = False
_WSB_HOTLIST: dict | None = None


def load_universe(name: str) -> list[dict]:
    if name == "us_large":
        return _load_csv(DATA_DIR / "us_tickers.csv", None)
    elif name == "us_tech":
        return _load_per_market_or_fallback("us_tech_tickers.csv",
                                            "us_tickers.csv", "Information Technology")
    elif name == "italy":
        return _load_per_market_or_fallback("italy_tickers.csv",
                                            "europe_tickers.csv", "Italy")
    elif name == "germany":
        return _load_per_market_or_fallback("germany_tickers.csv",
                                            "europe_tickers.csv", "Germany")
    elif name == "france":
        return _load_per_market_or_fallback("france_tickers.csv",
                                            "europe_tickers.csv", "France")
    elif name == "uk":
        return _load_per_market_or_fallback("uk_tickers.csv",
                                            "europe_tickers.csv", "UK")
    elif name == "spain":
        return _load_per_market_or_fallback("spain_tickers.csv",
                                            "europe_tickers.csv", "Spain")
    elif name == "all":
        us = _load_csv(DATA_DIR / "us_tickers.csv", None)
        eu = _load_all_european()
        return us + eu
    elif name == "crypto":
        return _load_crypto_csv()
    else:
        raise ValueError(f"Unknown universe: {name}")


def _load_all_european() -> list[dict]:
    eu_markets = ["italy", "germany", "france", "uk", "spain"]
    eu_files = [
        "italy_tickers.csv", "germany_tickers.csv", "france_tickers.csv",
        "uk_tickers.csv", "spain_tickers.csv",
    ]
    rows: list[dict] = []
    for filename in eu_files:
        filepath = DATA_DIR / filename
        rows.extend(_load_csv(filepath, None))
    if not rows:
        rows = _load_csv(DATA_DIR / "europe_tickers.csv", None)
    return rows


def _load_per_market_or_fallback(new_file: str, fallback_file: str,
                                  filter_value: str) -> list[dict]:
    new_path = DATA_DIR / new_file
    if new_path.exists():
        return _load_csv(new_path, None)
    fallback_path = DATA_DIR / fallback_file
    log.warning("New ticker file %s not found, falling back to %s (filter=%s)",
                new_file, fallback_file, filter_value)
    return _load_csv(fallback_path, None, market=filter_value)


def _load_csv(path: Path, allowed_symbols: set | None, market: str | None = None) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if allowed_symbols and row["symbol"] not in allowed_symbols:
                continue
            if market and row.get("market", "") != market:
                continue
            rows.append(row)
    return rows


def _load_crypto_csv() -> list[dict]:
    path = DATA_DIR / "crypto_tickers.csv"
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["symbol"].strip()
            if not symbol.endswith("-USD"):
                symbol = f"{symbol}-USD"
            rows.append({
                "symbol": symbol,
                "name": row.get("name", "").strip(),
                "suffix": row.get("suffix", "").strip(),
                "market": "CRYPTO",
            })
    return rows


def compute_crypto_analysis(ticker: yf.Ticker, hist: pd.DataFrame) -> tuple[int, str]:
    """
    Alert-Predict-Confirm framework (Crypto Technical Analysis - John & Law).
    3-indicator validation: Alert (RSI divergence), Predict (MACD crossover),
    Confirm (Volume confirmation). All 3 aligned = strong signal.
    """
    if hist.empty or len(hist) < 50:
        return 50, "Insufficient crypto data"

    score = 50
    details = []
    close = hist["Close"]
    volume = hist["Volume"]

    alert_bullish = False
    alert_bearish = False
    predict_bullish = False
    predict_bearish = False
    confirm_bullish = False
    confirm_bearish = False

    if len(close) >= 15:
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rsi = 100 - (100 / (1 + ma_up / ma_down))
        rsi_now = float(rsi.iloc[-1])
        rsi_prev = float(rsi.iloc[-5])

        if rsi_now < 30 and rsi_prev < 35:
            alert_bullish = True
            details.append(f"ALERT: RSI {rsi_now:.0f} oversold")
        elif rsi_now > 70 and rsi_prev > 65:
            alert_bearish = True
            details.append(f"ALERT: RSI {rsi_now:.0f} overbought")

    if len(close) >= 26:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()

        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
            predict_bullish = True
            details.append("PREDICT: MACD bullish crossover")
        elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
            predict_bearish = True
            details.append("PREDICT: MACD bearish crossover")

    if len(volume) >= 20:
        vol_ma = volume.rolling(20).mean()
        vol_now = float(volume.iloc[-1])
        vol_avg = float(vol_ma.iloc[-1])

        if vol_now > vol_avg * 1.5 and close.iloc[-1] > close.iloc[-2]:
            confirm_bullish = True
            details.append(f"CONFIRM: Volume {vol_now/vol_avg:.1f}x + price up")
        elif vol_now > vol_avg * 1.5 and close.iloc[-1] < close.iloc[-2]:
            confirm_bearish = True
            details.append(f"CONFIRM: Volume {vol_now/vol_avg:.1f}x + price down")

    bullish_count = sum([alert_bullish, predict_bullish, confirm_bullish])
    bearish_count = sum([alert_bearish, predict_bearish, confirm_bearish])

    if bullish_count == 3:
        score += 35
        details.append("Alert-Predict-Confirm: ALL BULLISH (+35)")
    elif bullish_count == 2:
        score += 20
        details.append(f"Alert-Predict-Confirm: 2/3 bullish (+20)")
    elif bearish_count == 3:
        score -= 30
        details.append("Alert-Predict-Confirm: ALL BEARISH (-30)")
    elif bearish_count == 2:
        score -= 15
        details.append(f"Alert-Predict-Confirm: 2/3 bearish (-15)")
    else:
        details.append(f"Alert-Predict-Confirm: Mixed ({bullish_count}B/{bearish_count}S)")

    return min(100, max(0, score)), " | ".join(details)


def _get_spx_hist() -> pd.DataFrame:
    """Fetch SPX history once and cache globally."""
    global _SPX_HIST
    if _SPX_HIST is None:
        try:
            spx = yf.Ticker("^GSPC")
            _SPX_HIST = spx.history(period="1y")
        except Exception:
            _SPX_HIST = pd.DataFrame()
    return _SPX_HIST


def parse_custom_tickers(ticker_str: str) -> list[dict]:
    symbols = [t.strip().upper() for t in ticker_str.split(",") if t.strip()]
    return [{"symbol": s, "name": s, "suffix": "", "market": "CUSTOM"} for s in symbols]


def compute_wyckoff(hist, _info) -> tuple[int, str]:
    if hist.empty or len(hist) < 50:
        return 20, "Insufficient data"

    score = 20
    details = []
    price = float(hist["Close"].iloc[-1])
    high_1y = hist["High"].max()
    low_1y = hist["Low"].min()
    pos = ((price - low_1y) / (high_1y - low_1y)) * 100 if (high_1y - low_1y) > 0 else 50

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

    if len(hist) >= 50:
        ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
        ma200_val = float(hist["Close"].rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None
        if ma200_val and ma50 > ma200_val:
            score += 15
            details.append(f"MA50 > MA200 (+15)")

    if len(hist) >= 30:
        recent_30 = hist.tail(30)
        low_30 = recent_30["Low"].min()
        low_idx = recent_30["Low"].idxmin()
        if low_idx and low_idx < hist.index[-5]:
            if price > low_30 * 1.05:
                score += 30
                details.append("Spring detected (+30)")

    if len(hist) >= 90:
        vol_older = hist.tail(90).head(60)["Volume"].mean()
        vol_recent = hist.tail(30)["Volume"].mean()
        if vol_recent < vol_older * 0.8:
            score += 15
            details.append("Volume decreasing (absorption) (+15)")

    # Volume-Price Divergence (Wyckoff 4-quadrant)
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


def compute_volume_profile(hist) -> tuple[int, str]:
    if hist.empty or len(hist) < 20:
        return 10, "Insufficient data"

    score = 10
    details = []
    price = float(hist["Close"].iloc[-1])
    hist_range = hist["High"].max() - hist["Low"].min()
    n_bins = 20
    bin_w = hist_range / n_bins if hist_range > 0 else 1
    hist = hist.copy()
    hist["bin"] = ((hist["Close"] - hist["Low"].min()) / bin_w).astype(int).clip(0, n_bins - 1)
    vol_by_bin = hist.groupby("bin")["Volume"].sum()
    poc_bin = vol_by_bin.idxmax()
    poc_price = hist["Low"].min() + (poc_bin + 0.5) * bin_w
    total_vol = vol_by_bin.sum()
    cum, va_bins = 0, []
    for b, v in vol_by_bin.sort_values(ascending=False).items():
        cum += v
        va_bins.append(b)
        if cum / total_vol >= 0.7:
            break
    val = hist["Low"].min() + min(va_bins) * bin_w
    vah = hist["Low"].min() + (max(va_bins) + 1) * bin_w

    if val <= price <= vah:
        score += 20
        details.append(f"Price inside VA ({val:.2f}-{vah:.2f}) (+20)")
    elif price < val:
        score += 25
        details.append(f"Price below VAL ({val:.2f}) (+25)")
    else:
        score += 15
        details.append(f"Price above VAH ({vah:.2f}) (+15)")

    if abs(price - poc_price) / poc_price < 0.05:
        score += 10
        details.append(f"Near VPOC ${poc_price:.2f} (+10)")

    if len(hist) >= 21:
        vol_ratio = float(hist["Volume"].iloc[-1]) / float(hist["Volume"].iloc[-21:].mean())
        if vol_ratio > 2.0:
            score += 15
            details.append(f"Volume ratio {vol_ratio:.1f}x (+15)")
        elif vol_ratio > 1.0:
            score += 10
            details.append(f"Volume ratio {vol_ratio:.1f}x (+10)")

    pos_in_range = ((price - hist["Low"].min()) / hist_range) * 100 if hist_range > 0 else 50
    if 40 < pos_in_range < 60:
        score += 15
        details.append("D-Profile shape (balanced) (+15)")

    return min(score, 100), " | ".join(details)


def compute_price_action(hist) -> tuple[int, str]:
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
        rsi = 100 - (100 / (1 + ma_up / ma_down))
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

    hist = hist.copy()
    hist["ema25"] = hist["Close"].ewm(span=25).mean()
    if len(hist) >= 30:
        slope = (hist["ema25"].iloc[-1] - hist["ema25"].iloc[-5]) / hist["ema25"].iloc[-5]
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
        vr = vol / avg if avg > 0 else 1
        up = float(bar["Close"]) > float(prev["Close"])
        wide = (float(bar["High"]) - float(bar["Low"])) > (float(prev["High"]) - float(prev["Low"])) * 1.2
        high_vol = vr > 1.5
        if up and high_vol:
            vpa_net += 1
        elif not up and high_vol:
            vpa_net -= 1
        if up and vr < 0.6 and wide:
            vpa_net -= 1
        elif not up and vr < 0.6 and wide:
            vpa_net += 1

    if vpa_net > 2:
        score += 20
        details.append(f"VPA bullish ({vpa_net}) (+20)")
    elif vpa_net > 0:
        details.append(f"VPA mildly bullish ({vpa_net}) (+0)")

    # Rally Velocity & Exhaustion Check (nuovo — Jegadeesh 1990)
    if len(hist) >= 30:
        close_15d_ago = float(hist["Close"].iloc[-16])
        close_now = float(hist["Close"].iloc[-1])
        change_15d = (close_now / close_15d_ago - 1) * 100

        if change_15d > 50:
            score = max(score - 50, 0)
            details.append(f"⚠ Rally +{change_15d:.0f}% in 15d (vertical, -50)")
        elif change_15d > 30:
            score = max(score - 35, 0)
            details.append(f"⚠ Rally +{change_15d:.0f}% in 15d (exhaustion risk -35)")
        elif change_15d > 20:
            score = max(score - 20, 0)
            details.append(f"⚠ Rally +{change_15d:.0f}% in 15d (extension -20)")
        elif change_15d < 10 and change_15d > -3:
            vol_lately = float(hist.tail(5)["Volume"].mean())
            vol_20d = float(hist.tail(20)["Volume"].mean())
            if vol_lately > vol_20d * 1.2 and change_15d > 0:
                score += 15
                details.append(f"Gradual +{change_15d:.0f}% on rising vol (+15)")

        if len(hist) >= 10:
            closes = hist.tail(10)["Close"].values
            green_streak = 0
            for i in range(1, len(closes)):
                if closes[i] > closes[i-1]:
                    green_streak += 1
                else:
                    green_streak = 0
            if green_streak >= 5:
                score = max(score - 10, 0)
                details.append(f"{green_streak} consecutive green candles (-10)")

    return min(score, 100), " | ".join(details)


def compute_sentiment(info) -> tuple[int, str]:
    score = 25
    details = []

    si = info.get("shortPercentOfFloat")
    if si is not None:
        if si > 0.20:
            score += 35
            details.append(f"SI {si*100:.1f}% > 20% (+35)")
        elif si > 0.10:
            score += 20
            details.append(f"SI {si*100:.1f}% 10-20% (+20)")
        else:
            details.append(f"SI {si*100:.1f}% < 10% (+0)")
    else:
        details.append("SI N/A (+0)")

    inst = info.get("heldPercentInstitutions")
    if inst is not None and inst > 0.50:
        score += 15
        details.append(f"Inst {inst*100:.0f}% > 50% (+15)")

    dtc = info.get("shortRatio")
    if dtc is not None:
        if dtc > 7:
            score += 25
            details.append(f"DTC {dtc:.1f} > 7 (+25)")
        elif dtc > 3:
            score += 15
            details.append(f"DTC {dtc:.1f} > 3 (+15)")

    return min(score, 100), " | ".join(details)


def compute_fundamentals(info) -> tuple[int, str]:
    """
    5-dimension fundamentals with Earnings Quality Modifier (Sloan 1996),
    Value Trap Check, and Price vs Consensus divergence.
    """
    score = 10
    details = []

    # Step A — P/E base + Earnings Quality Modifier
    pe = info.get("trailingPE")
    earnings_growth = info.get("earningsGrowth")
    rev_growth = info.get("revenueGrowth")

    pe_base = 0
    if pe is not None and pe > 0:
        if pe < 12:
            pe_base = 30
        elif pe < 20:
            pe_base = 20
        elif pe < 30:
            pe_base = 10
        else:
            pe_base = 0

    eq_mod = 0
    if earnings_growth is not None:
        if earnings_growth > 0.15:
            eq_mod = 20
        elif earnings_growth > 0.05:
            eq_mod = 10
        elif earnings_growth > 0:
            eq_mod = 5
        elif earnings_growth < -0.10:
            eq_mod = -20
        elif earnings_growth < 0:
            eq_mod = -10

    score += pe_base + eq_mod
    if pe is not None and pe > 0:
        details.append(f"P/E {pe:.1f} base={pe_base} EQ mod={eq_mod:+d}")

    # Step B — Value Trap Check
    pe_low = pe is not None and 0 < pe < 15
    vt_count = 0
    if pe_low:
        if earnings_growth is not None and earnings_growth <= 0:
            score -= 20
            vt_count += 1
            details.append(f"⚠ Value Trap: P/E low + EPS falling (-20)")
        if rev_growth is not None and rev_growth < 0.02:
            score -= 15
            vt_count += 1
            details.append(f"⚠ Value Trap: P/E low + revenue < 2% (-15)")
        margins = info.get("profitMargins")
        if margins is not None and margins > 0:
            pass  # margins positive = less trap-like
        de = info.get("debtToEquity")
        if de is not None and de > 2.0:
            score -= 15
            vt_count += 1
            details.append(f"⚠ Value Trap: D/E {de:.2f} > 2.0 (-15)")
    if vt_count >= 2:
        score = min(score, 40)
        details.append(f"⚠ VALUE TRAP ALERT ({vt_count} signals) — score capped at 40")

    # Step C — Standard Fundamentals
    if rev_growth is not None and rev_growth > 0:
        score += 15
        details.append(f"Rev growth {rev_growth*100:.1f}% (+15)")

    margins = info.get("profitMargins")
    if margins is not None and margins > 0:
        score += 15
        details.append(f"Margins {margins*100:.1f}% (+15)")

    de = info.get("debtToEquity")
    if de is not None:
        if de < 0.5:
            score += 20
            details.append(f"D/E {de:.2f} < 0.5 (+20)")
        elif de < 1.0:
            score += 10
            details.append(f"D/E {de:.2f} < 1.0 (+10)")

    # Step E — Business quality / Competitive positioning (merged)
    roe = info.get("returnOnEquity")
    if roe is not None:
        if roe > 0.20:
            score += 15
            details.append(f"ROE {roe*100:.1f}% > 20% (moat +15)")
        elif roe > 0.15:
            score += 10
            details.append(f"ROE {roe*100:.1f}% > 15% (+10)")

    roa = info.get("returnOnAssets")
    if roa is not None:
        if roa > 0.10:
            score += 10
            details.append(f"ROA {roa*100:.1f}% > 10% (+10)")
        elif roa > 0.05:
            score += 5
            details.append(f"ROA {roa*100:.1f}% > 5% (+5)")

    op_margins = info.get("operatingMargins")
    if op_margins is not None:
        if op_margins > 0.20:
            score += 10
            details.append(f"Op margins {op_margins*100:.1f}% (efficient +10)")

    mcap = info.get("marketCap")
    if mcap is not None and mcap > 10e9:
        score += 10
        details.append(f"MCap ${mcap/1e9:.1f}B > $10B (+10)")

    # Step D — Price vs Consensus
    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    current = info.get("currentPrice")
    if target_mean and current and target_mean > 0 and current > 0:
        ratio = current / target_mean
        if ratio > 1.10:
            score -= 25
            details.append(f"Price ${current:.2f} > 110% of mean target ${target_mean:.2f} (-25)")
        elif ratio > 0.80 and target_high:
            ratio_high = current / target_high
            if ratio_high > 0.90:
                score -= 10
                details.append(f"Price near high target (priced for perfection -10)")
        elif ratio < 0.80:
            score += 15
            details.append(f"Price ${current:.2f} < 80% of mean target (+15)")
        elif ratio < 1.0:
            score += 5
            details.append(f"Price ${current:.2f} < mean target (+5)")

    return min(max(score, 0), 100), " | ".join(details)


def compute_competitive_positioning(info) -> tuple[int, str]:
    """
    Competitive Positioning (nuova dimensione, peso 10%).
    Proxy a livello scanner usando dati yfinance disponibili.
    """
    score = 30
    details = []

    roe = info.get("returnOnEquity")
    if roe is not None:
        if roe > 0.20:
            score += 20
            details.append(f"ROE {roe*100:.1f}% > 20% (moat proxy +20)")
        elif roe > 0.15:
            score += 10
            details.append(f"ROE {roe*100:.1f}% > 15% (+10)")
        else:
            details.append(f"ROE {roe*100:.1f}% (+0)")

    margins = info.get("profitMargins")
    if margins is not None:
        if margins > 0.20:
            score += 20
            details.append(f"Margins {margins*100:.1f}% > 20% (pricing power +20)")
        elif margins > 0.10:
            score += 10
            details.append(f"Margins {margins*100:.1f}% > 10% (+10)")

    roa = info.get("returnOnAssets")
    if roa is not None:
        if roa > 0.10:
            score += 15
            details.append(f"ROA {roa*100:.1f}% > 10% (+15)")
        elif roa > 0.05:
            score += 10
            details.append(f"ROA {roa*100:.1f}% > 5% (+10)")

    mcap = info.get("marketCap")
    if mcap is not None:
        if mcap > 200e9:
            score += 15
            details.append(f"MCap ${mcap/1e9:.0f}B > $200B (scale moat +15)")
        elif mcap > 50e9:
            score += 10
            details.append(f"MCap ${mcap/1e9:.0f}B $50-200B (+10)")
        elif mcap > 10e9:
            score += 5
            details.append(f"MCap ${mcap/1e9:.0f}B > $10B (+5)")

    op_margins = info.get("operatingMargins")
    if op_margins is not None:
        if op_margins > 0.20:
            score += 10
            details.append(f"Op margins {op_margins*100:.1f}% (efficient +10)")

    return min(score, 100), " | ".join(details)


def compute_multiframe_trend(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Multi-Timeframe Analysis (VPA Coulling).
    Aligns trend across 3 timeframes: fast (20d), primary (50d), slow (200d).
    All aligned = strong signal. Conflicting = weak/neutral.
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
        slope = (ma.iloc[-1] - ma.iloc[-5]) / ma.iloc[-5]
        if slope > 0.02:
            return "up"
        elif slope < -0.02:
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


def compute_sot_weis_wave(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Shortening of the Thrust + Weis Wave (Trades About to Happen - David Weis).
    SOT: 3+ impulse waves with diminishing progress = exhaustion.
    Weis Wave: cumulative volume waves, detect shortening.
    Crabel contraction: NR7, ID/NR4 patterns for entry timing.
    """
    if hist.empty or len(hist) < 60:
        return 50, "Insufficient data for SOT/Weis"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    volume = hist["Volume"].values

    impulses = []
    i = 0
    while i < len(close) - 5:
        if close[i + 1] > close[i]:
            start = i
            peak_idx = i
            for j in range(i + 1, min(i + 20, len(close))):
                if close[j] > close[peak_idx]:
                    peak_idx = j
                elif close[j] < close[peak_idx] * 0.97:
                    break
            impulse_len = peak_idx - start
            impulse_gain = (close[peak_idx] - close[start]) / close[start] if close[start] > 0 else 0
            if impulse_gain > 0.03 and impulse_len >= 2:
                impulses.append({"start": start, "peak": peak_idx, "gain": impulse_gain, "len": impulse_len})
            i = peak_idx + 1
        else:
            i += 1

    if len(impulses) >= 3:
        last3 = impulses[-3:]
        gains = [imp["gain"] for imp in last3]
        if gains[0] > gains[1] > gains[2] and gains[2] < gains[0] * 0.5:
            score += 25
            details.append(f"SOT detected: gains {[f'{g:.1%}' for g in gains]} (exhaustion +25)")
        elif gains[0] > gains[1] > gains[2]:
            score += 10
            details.append(f"Mild SOT: gains {[f'{g:.1%}' for g in gains]} (+10)")

    cum_vol = 0
    wave_vols = []
    wave_start = 0
    for i in range(1, len(close)):
        cum_vol += volume[i]
        if (close[i] > close[i - 1] and close[wave_start] > close[wave_start - 1] if wave_start > 0 else False) or \
           (close[i] < close[i - 1] and close[wave_start] < close[wave_start - 1] if wave_start > 0 else False):
            continue
        if i - wave_start >= 3:
            wave_vols.append(cum_vol)
            cum_vol = 0
            wave_start = i

    if len(wave_vols) >= 3:
        last3_vol = wave_vols[-3:]
        if last3_vol[0] > last3_vol[1] > last3_vol[2]:
            score += 15
            details.append(f"Weis Wave shortening: vols declining (+15)")

    if len(close) >= 7:
        ranges = [high[i] - low[i] for i in range(len(close))]
        last7_ranges = ranges[-7:]
        current_range = last7_ranges[-1]
        if current_range < min(last7_ranges[:-1]):
            score += 10
            details.append("NR7 (Crabel contraction) (+10)")

    if len(close) >= 4:
        last4_ranges = [high[i] - low[i] for i in range(-4, 0)]
        id_nr4 = False
        for i in range(1, len(last4_ranges)):
            if last4_ranges[i] < last4_ranges[i - 1] * 0.7:
                id_nr4 = True
                break
        if id_nr4:
            score += 5
            details.append("ID/NR4 contraction (+5)")

    return min(100, max(0, score)), " | ".join(details)


def compute_squeeze_play(ticker: yf.Ticker, info: dict, hist: pd.DataFrame) -> tuple[int, str]:
    """
    Squeeze Play System (Trading Against the Crowd - John Summa).
    Combines sentiment oscillator (EMA of P/C ratio) with price breakout trigger.
    Smart Money vs Dumb Money divergence.
    """
    if hist.empty or len(hist) < 50:
        return 50, "Insufficient data for Squeeze Play"

    score = 50
    details = []

    try:
        exps = ticker.options
        if exps and len(exps) >= 2:
            pc_ratios = []
            for exp in exps[:4]:
                try:
                    chain = ticker.option_chain(exp)
                    calls, puts = chain.calls, chain.puts
                    if not calls.empty and not puts.empty:
                        c_vol = calls["volume"].sum() if "volume" in calls.columns else 0
                        p_vol = puts["volume"].sum() if "volume" in puts.columns else 0
                        if c_vol > 0:
                            pc_ratios.append(p_vol / c_vol)
                except Exception:
                    continue

            if len(pc_ratios) >= 2:
                pc_series = pd.Series(pc_ratios)
                ema_fast = pc_series.ewm(span=2).mean().iloc[-1]
                ema_slow = pc_series.ewm(span=4).mean().iloc[-1]

                if ema_fast < ema_slow * 0.8:
                    score += 20
                    details.append(f"Squeeze I: P/C EMA fast < slow (bullish divergence +20)")
                elif ema_fast > ema_slow * 1.2:
                    score -= 15
                    details.append(f"Squeeze I: P/C EMA fast > slow (bearish divergence -15)")
    except Exception:
        pass

    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    if len(close) >= 5:
        prev_high = max(high[-5:-1])
        prev_low = min(low[-5:-1])
        current_close = close[-1]

        if current_close > prev_high:
            score += 15
            details.append(f"Price trigger: close ${current_close:.2f} > 5d high ${prev_high:.2f} (bullish +15)")
        elif current_close < prev_low:
            score -= 15
            details.append(f"Price trigger: close ${current_close:.2f} < 5d low ${prev_low:.2f} (bearish -15)")

    si = info.get("shortPercentOfFloat")
    dtc = info.get("shortRatio")
    if si is not None and si > 0.15 and dtc is not None and dtc > 5:
        score += 10
        details.append(f"Smart Money divergence: SI {si:.1%} + DTC {dtc:.1f} (contrarian +10)")

    return min(100, max(0, score)), " | ".join(details)


def compute_earnings_surprise(ticker: yf.Ticker) -> tuple[int, str]:
    """
    Earnings Surprise Trend (beat/miss streak).
    Analyzes last 4-8 quarters of earnings to detect consistent beats or misses.
    """
    score = 50
    details = []

    try:
        earnings = ticker.earnings_history
        if earnings is None or earnings.empty:
            return None, "No earnings history"

        if "surprisePercent" in earnings.columns:
            surprises = earnings["surprisePercent"].dropna().values
            if len(surprises) == 0:
                return None, "No surprise data"

            recent = surprises[:min(8, len(surprises))]
            beats = sum(1 for s in recent if s > 0)
            misses = sum(1 for s in recent if s < 0)

            streak = 0
            for s in recent:
                if s > 0:
                    streak += 1 if streak >= 0 else 1
                elif s < 0:
                    streak -= 1 if streak <= 0 else 1
                else:
                    break

            if streak >= 4:
                score += 25
                details.append(f"Earnings beat streak: {streak}Q (+25)")
            elif streak >= 2:
                score += 15
                details.append(f"Earnings beat streak: {streak}Q (+15)")
            elif streak <= -4:
                score -= 25
                details.append(f"Earnings miss streak: {abs(streak)}Q (-25)")
            elif streak <= -2:
                score -= 15
                details.append(f"Earnings miss streak: {abs(streak)}Q (-15)")

            avg_surprise = sum(recent) / len(recent)
            if avg_surprise > 5:
                score += 10
                details.append(f"Avg surprise +{avg_surprise:.1f}% (+10)")
            elif avg_surprise < -5:
                score -= 10
                details.append(f"Avg surprise {avg_surprise:.1f}% (-10)")

            details.append(f"Beats: {beats}/{len(recent)}, Misses: {misses}/{len(recent)}")
        else:
            return None, "No surprisePercent column"

    except Exception as e:
        return None, f"Earnings history error: {e}"

    return min(100, max(0, score)), " | ".join(details)


def compute_6clue_test(hist: pd.DataFrame, info: dict) -> tuple[int, str]:
    """
    Wyckoff 6-Clue Accumulation/Distribution Test (Wyckoff 2.0 - Villahermosa).
    Formal test for accumulation (bullish) vs distribution (bearish).
    6 clues scored individually, net score determines phase.
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
        support_zone = min(low[-60:])
        current = close[-1]
        if current > support_zone * 1.05 and current < support_zone * 1.15:
            clues_bullish += 1
            details.append("Clue 1: Price testing support (spring zone)")
        elif current < support_zone:
            clues_bearish += 1
            details.append("Clue 1: Price breaking support")

    if len(close) >= 60:
        down_vol = sum(volume[i] for i in range(-60, 0) if close[i] < close[i - 1])
        up_vol = sum(volume[i] for i in range(-60, 0) if close[i] > close[i - 1])
        if up_vol > down_vol * 1.2:
            clues_bullish += 1
            details.append(f"Clue 2: Up vol > Down vol ({up_vol/down_vol:.2f}x)")
        elif down_vol > up_vol * 1.2:
            clues_bearish += 1
            details.append(f"Clue 2: Down vol > Up vol ({down_vol/up_vol:.2f}x)")

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
    if target_mean and current_price and target_mean > current_price * 1.1:
        clues_bullish += 1
        details.append(f"Clue 4: Analyst target ${target_mean:.0f} > price ${current_price:.0f}")
    elif target_mean and current_price and target_mean < current_price * 0.9:
        clues_bearish += 1
        details.append(f"Clue 4: Analyst target ${target_mean:.0f} < price ${current_price:.0f}")

    if len(close) >= 60:
        half = len(close[-60:]) // 2
        first_half_high = max(high[-60:-60 + half])
        first_half_low = min(low[-60:-60 + half])
        second_half_high = max(high[-60 + half:])
        second_half_low = min(low[-60 + half:])

        if second_half_high > first_half_high and second_half_low > first_half_low:
            clues_bullish += 1
            details.append("Clue 5: HH/HL structure (markup)")
        elif second_half_high < first_half_high and second_half_low < first_half_low:
            clues_bearish += 1
            details.append("Clue 5: LH/LL structure (markdown)")

    if len(close) >= 120:
        range_120 = max(high[-120:]) - min(low[-120:])
        range_60 = max(high[-60:]) - min(low[-60:])
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


# ────────────────────────────────────────────────
#  NEW CRITICAL CONCEPTS (from trading book skills)
# ────────────────────────────────────────────────


def compute_candlestick_patterns(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Candlestick Pattern Detection (VPA + Crypto TA).
    Detects Hammer, Shooting Star, Engulfing, Doji, Morning/Evening Star
    with volume confirmation.
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

    def _body(i):
        return abs(close[i] - open_p[i])

    def _upper_shadow(i):
        return high[i] - max(open_p[i], close[i])

    def _lower_shadow(i):
        return min(open_p[i], close[i]) - low[i]

    def _is_doji(i):
        return _body(i) < (high[i] - low[i]) * 0.05

    def _is_hammer(i):
        body = _body(i)
        range_ = high[i] - low[i]
        if range_ == 0:
            return False
        lower = _lower_shadow(i)
        upper = _upper_shadow(i)
        return lower > body * 2 and upper < body * 0.5 and lower / range_ > 0.5

    def _is_shooting_star(i):
        body = _body(i)
        range_ = high[i] - low[i]
        if range_ == 0:
            return False
        upper = _upper_shadow(i)
        lower = _lower_shadow(i)
        return upper > body * 2 and lower < body * 0.5 and upper / range_ > 0.5

    def _is_engulfing_bullish(i):
        if i < 1:
            return False
        prev_bear = close[i - 1] < open_p[i - 1]
        curr_bull = close[i] > open_p[i]
        return prev_bear and curr_bull and close[i] > open_p[i - 1] and open_p[i] < close[i - 1]

    def _is_engulfing_bearish(i):
        if i < 1:
            return False
        prev_bull = close[i - 1] > open_p[i - 1]
        curr_bear = close[i] < open_p[i]
        return prev_bull and curr_bear and close[i] < open_p[i - 1] and open_p[i] > close[i - 1]

    def _is_morning_star(i):
        if i < 2:
            return False
        return (
            close[i - 2] < open_p[i - 2]
            and _is_doji(i - 1)
            and close[i] > open_p[i]
            and close[i] > (open_p[i - 2] + close[i - 2]) / 2
        )

    def _is_evening_star(i):
        if i < 2:
            return False
        return (
            close[i - 2] > open_p[i - 2]
            and _is_doji(i - 1)
            and close[i] < open_p[i]
            and close[i] < (open_p[i - 2] + close[i - 2]) / 2
        )

    avg_vol = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
    pattern_count = {"hammer": 0, "shooting_star": 0, "engulfing_bull": 0,
                   "engulfing_bear": 0, "morning_star": 0, "evening_star": 0,
                   "doji": 0}

    for i in range(max(2, len(close) - 20), len(close)):
        vol = float(volume[i])
        vol_conf = vol > avg_vol * 0.8

        if _is_hammer(i):
            pattern_count["hammer"] += 1
            if vol_conf:
                score += 5
                details.append(f"Hammer @ {i} (+5 vol-conf)")
            else:
                score += 2
        if _is_shooting_star(i):
            pattern_count["shooting_star"] += 1
            if vol_conf:
                score -= 5
                details.append(f"Shooting Star @ {i} (-5 vol-conf)")
            else:
                score -= 2
        if _is_engulfing_bullish(i):
            pattern_count["engulfing_bull"] += 1
            if vol_conf:
                score += 7
                details.append(f"Bullish Engulfing @ {i} (+7)")
            else:
                score += 3
        if _is_engulfing_bearish(i):
            pattern_count["engulfing_bear"] += 1
            if vol_conf:
                score -= 7
                details.append(f"Bearish Engulfing @ {i} (-7)")
            else:
                score -= 3
        if _is_morning_star(i):
            pattern_count["morning_star"] += 1
            if vol_conf:
                score += 10
                details.append(f"Morning Star @ {i} (+10)")
            else:
                score += 5
        if _is_evening_star(i):
            pattern_count["evening_star"] += 1
            if vol_conf:
                score -= 10
                details.append(f"Evening Star @ {i} (-10)")
            else:
                score -= 5
        if _is_doji(i):
            pattern_count["doji"] += 1

    if pattern_count["doji"] >= 3:
        score += 3
        details.append(f"{pattern_count['doji']} doji (indecision +3)")

    if not details:
        details.append("No major patterns")
    return min(100, max(0, score)), " | ".join(details)


def compute_fibonacci(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Fibonacci Retracement levels from recent swing high/low.
    Measures where current price sits relative to 0.236, 0.382, 0.5, 0.618, 0.786.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    recent = hist.tail(60)
    swing_high = float(recent["High"].max())
    swing_low = float(recent["Low"].min())
    current = float(close[-1])

    if swing_high <= swing_low:
        return 50, "No valid swing"

    range_ = swing_high - swing_low
    levels = {
        "0.236": swing_high - range_ * 0.236,
        "0.382": swing_high - range_ * 0.382,
        "0.500": swing_high - range_ * 0.500,
        "0.618": swing_high - range_ * 0.618,
        "0.786": swing_high - range_ * 0.786,
    }

    # Score: price near 0.618 or 0.786 after pullback = bullish
    # price near 0.236 or 0.382 after rally = bearish
    dist_to_618 = abs(current - levels["0.618"]) / range_
    dist_to_786 = abs(current - levels["0.786"]) / range_
    dist_to_382 = abs(current - levels["0.382"]) / range_
    dist_to_236 = abs(current - levels["0.236"]) / range_

    if dist_to_618 < 0.03:
        score += 15
        details.append(f"Price @ 61.8% retracement (+15)")
    elif dist_to_786 < 0.03:
        score += 10
        details.append(f"Price @ 78.6% retracement (+10 deep support)")
    elif dist_to_382 < 0.03:
        score -= 10
        details.append(f"Price @ 38.2% retracement (-10 shallow)")
    elif dist_to_236 < 0.03:
        score -= 15
        details.append(f"Price @ 23.6% retracement (-15 very shallow)")

    # Trend direction bonus
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
    """
    Bollinger Bands analysis: squeeze detection, %B position, bandwidth.
    """
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

    # %B
    bb_range = upper_now - lower_now
    pct_b = (current - lower_now) / bb_range if bb_range > 0 else 0.5

    # Squeeze: bandwidth < 5% of 20d average
    if len(hist) >= 40:
        avg_bandwidth = ((upper - lower) / ma20).tail(20).mean()
        if bandwidth < avg_bandwidth * 0.5 and bandwidth < 0.05:
            score += 15
            details.append(f"BB Squeeze! bandwidth={bandwidth:.2%} (+15 volatility expansion soon)")
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
        details.append(f"%B={pct_b:.2f} (neutral zone)")

    # Walking the bands (trend)
    if len(hist) >= 5:
        above_upper = sum(1 for i in range(-5, 0) if close.iloc[i] > upper.iloc[i])
        below_lower = sum(1 for i in range(-5, 0) if close.iloc[i] < lower.iloc[i])
        if above_upper >= 3:
            score += 10
            details.append(f"Walking upper band (strong uptrend +10)")
        elif below_lower >= 3:
            score -= 10
            details.append(f"Walking lower band (strong downtrend -10)")

    return min(100, max(0, score)), " | ".join(details)


def compute_obv(hist: pd.DataFrame) -> tuple[int, str]:
    """
    On-Balance Volume (OBV) — volume flow indicator.
    Detects OBV divergence with price.
    """
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    volume = hist["Volume"].values

    obv = [0.0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv.append(obv[-1] + volume[i])
        elif close[i] < close[i - 1]:
            obv.append(obv[-1] - volume[i])
        else:
            obv.append(obv[-1])

    obv = np.array(obv)
    price_slope = (close[-1] - close[-20]) / close[-20] if len(close) >= 20 and close[-20] != 0 else 0
    obv_slope = (obv[-1] - obv[-20]) / abs(obv[-20]) if len(obv) >= 20 and obv[-20] != 0 else 0

    # Divergence detection
    if price_slope > 0.05 and obv_slope < 0:
        score -= 15
        details.append(f"OBV divergence bearish: price +{price_slope:.1%} OBV {obv_slope:.1%} (-15)")
    elif price_slope < -0.05 and obv_slope > 0:
        score += 15
        details.append(f"OBV divergence bullish: price {price_slope:.1%} OBV +{obv_slope:.1%} (+15)")
    elif price_slope > 0 and obv_slope > 0:
        score += 10
        details.append(f"OBV confirms uptrend (+10)")
    elif price_slope < 0 and obv_slope < 0:
        score -= 10
        details.append(f"OBV confirms downtrend (-10)")
    else:
        details.append(f"OBV slope={obv_slope:.2f} vs price slope={price_slope:.2f}")

    # OBV trend vs MA
    if len(obv) >= 20:
        obv_ma = np.mean(obv[-20:])
        if obv[-1] > obv_ma * 1.05:
            score += 5
            details.append("OBV above MA20 (+5)")
        elif obv[-1] < obv_ma * 0.95:
            score -= 5
            details.append("OBV below MA20 (-5)")

    return min(100, max(0, score)), " | ".join(details)


def compute_support_resistance(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Support/Resistance Role Reversal detection.
    Finds recent swing points and checks if price is testing/ breaking them.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    # Find local maxima/minima
    def _local_extrema(arr, window=3):
        extrema = []
        for i in range(window, len(arr) - window):
            if all(arr[i] >= arr[i - j] for j in range(1, window + 1)) and \
               all(arr[i] >= arr[i + j] for j in range(1, window + 1)):
                extrema.append((i, arr[i], "high"))
            elif all(arr[i] <= arr[i - j] for j in range(1, window + 1)) and \
                 all(arr[i] <= arr[i + j] for j in range(1, window + 1)):
                extrema.append((i, arr[i], "low"))
        return extrema

    highs = _local_extrema(high, 3)
    lows = _local_extrema(low, 3)
    # Combine and sort by value
    all_extrema = sorted(highs + lows, key=lambda x: x[1])
    if len(all_extrema) < 4:
        return 50, "Not enough swing points"

    # Group into clusters (support/resistance levels)
    clusters = []
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
    current = close[-1]

    if not clusters:
        return 50, "No clear S/R levels"

    # Find nearest support and resistance
    supports = [c for c in clusters if c["price"] < current]
    resistances = [c for c in clusters if c["price"] > current]

    nearest_support = max(supports, key=lambda x: x["price"]) if supports else None
    nearest_resistance = min(resistances, key=lambda x: x["price"]) if resistances else None

    if nearest_support:
        dist = (current - nearest_support["price"]) / current
        if dist < 0.03:
            score += 10
            details.append(f"Price at support ${nearest_support['price']:.2f} (+10)")
        elif dist < 0.05:
            score += 5
            details.append(f"Price near support ${nearest_support['price']:.2f} (+5)")

    if nearest_resistance:
        dist = (nearest_resistance["price"] - current) / current
        if dist < 0.03:
            score -= 10
            details.append(f"Price at resistance ${nearest_resistance['price']:.2f} (-10)")
        elif dist < 0.05:
            score -= 5
            details.append(f"Price near resistance ${nearest_resistance['price']:.2f} (-5)")

    # Role reversal: did price break above former resistance?
    if len(hist) >= 10 and nearest_resistance:
        recent_high = max(high[-10:])
        if recent_high > nearest_resistance["price"] * 1.01:
            score += 10
            details.append("Role reversal: broke resistance → support (+10)")

    if len(hist) >= 10 and nearest_support:
        recent_low = min(low[-10:])
        if recent_low < nearest_support["price"] * 0.99:
            score -= 10
            details.append("Role reversal: broke support → resistance (-10)")

    if not details:
        details.append("S/R neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_psychology_score(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Trading Psychology / FOMO-Panic Detection.
    Measures consecutive candles, gap size, RSI extremes, volume spikes.
    """
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    volume = hist["Volume"].values

    # Consecutive streak
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

    # Gap analysis
    if len(hist) >= 2:
        gaps = []
        for i in range(-min(10, len(close)), 0):
            gap = (close[i] - close[i - 1]) / close[i - 1] if close[i - 1] != 0 else 0
            if abs(gap) > 0.05:
                gaps.append(gap)
        if len(gaps) >= 2:
            score = max(score - 10, 0)
            details.append(f"{len(gaps)} gaps >5% in 10d (instability -10)")

    # Volume spike with no follow-through = distribution
    if len(volume) >= 5:
        vol_avg = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
        recent_vol = float(volume[-1])
        recent_range = (close[-1] - close[-5]) / close[-5] if close[-5] != 0 else 0
        if recent_vol > vol_avg * 2.5 and abs(recent_range) < 0.02:
            score = max(score - 15, 0)
            details.append("Vol spike + flat price (distribution -15)")
        elif recent_vol > vol_avg * 2.5 and recent_range > 0.05:
            score = min(score + 10, 100)
            details.append("Vol spike + strong move (initiative +10)")

    # RSI extremes
    if len(close) >= 15:
        delta = pd.Series(close).diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(com=13).mean()
        ma_down = down.ewm(com=13).mean()
        rsi = 100 - (100 / (1 + ma_up / ma_down))
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
    """
    Ichimoku Kinko Hyo — cloud analysis.
    Tenkan-sen (9), Kijun-sen (26), Senkou Span A (52ahead),
    Senkou Span B (52ahead), Chikou Span (26lag).
    """
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

    # Price vs Cloud
    if cloud_top is not None and cloud_bot is not None:
        if current > cloud_top:
            score += 15
            details.append(f"Price above cloud (bullish +15)")
        elif current < cloud_bot:
            score -= 15
            details.append(f"Price below cloud (bearish -15)")
        elif cloud_top > cloud_bot and cloud_bot <= current <= cloud_top:
            score += 5
            details.append(f"Price inside bullish cloud (+5)")
        elif cloud_bot > cloud_top and cloud_top <= current <= cloud_bot:
            score -= 10
            details.append(f"Price inside bearish cloud (-10)")

        # Cloud color: green=ahead bullish, red=ahead bearish
        if cloud_top > cloud_bot:
            details.append("Cloud green (bullish ahead)")
        else:
            details.append("Cloud red (bearish ahead)")

    # Tenkan/Kijun cross
    if len(close) >= 27:
        tenkan_prev = float(tenkan.iloc[-2])
        kijun_prev = float(kijun.iloc[-2])
        if tenkan_prev <= kijun_prev and tenkan_now > kijun_now:
            score += 15
            details.append("Tenkan/Kijun bullish cross (+15)")
        elif tenkan_prev >= kijun_prev and tenkan_now < kijun_now:
            score -= 15
            details.append("Tenkan/Kijun bearish cross (-15)")

    # Chikou span
    if len(close) >= 27:
        chikou = close.shift(-26)
        chikou_now = float(chikou.iloc[-27]) if not pd.isna(chikou.iloc[-27]) else None
        if chikou_now is not None:
            if chikou_now > current:
                score += 10
                details.append("Chikou above price (+10 confirmation)")
            else:
                score -= 10
                details.append("Chikou below price (-10)")

    # Future cloud thickness (next 26 bars projection)
    if len(close) >= 78:
        future_26 = int(min(26, len(close) - 52))
        if future_26 > 0:
            future_top = float(senkou_a.iloc[-1])
            future_bot = float(senkou_b.iloc[-1])
            cloud_width = abs(future_top - future_bot) / current if current > 0 else 0
            if cloud_width < 0.03:
                score += 10
                details.append(f"Thin future cloud ({cloud_width:.1%}) — weak S/R ahead (+10)")
            elif cloud_width > 0.15:
                score += 5
                details.append(f"Thick future cloud ({cloud_width:.1%}) — strong S/R (+5)")

    if not details:
        details.append("Ichimoku neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_candlestick_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Advanced Candlestick Patterns: Harami, Abandoned Baby, Piercing Pattern,
    Dark Cloud Cover, 3-bar Engulfing, Tweezer Tops/Bottoms.
    Builds on top of compute_candlestick_patterns.
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

    def _body(i):
        return abs(close[i] - open_p[i])

    def _range(i):
        return high[i] - low[i]

    # Harami: small body inside previous large body
    def _is_harami_bullish(i):
        if i < 1:
            return False
        prev_bear = close[i - 1] < open_p[i - 1]
        prev_body = _body(i - 1)
        curr_body = _body(i)
        curr_bull = close[i] > open_p[i]
        if not (prev_bear and curr_bull and prev_body > 0):
            return False
        return curr_body < prev_body * 0.5 and open_p[i] > close[i - 1] and close[i] < open_p[i - 1]

    def _is_harami_bearish(i):
        if i < 1:
            return False
        prev_bull = close[i - 1] > open_p[i - 1]
        prev_body = _body(i - 1)
        curr_body = _body(i)
        curr_bear = close[i] < open_p[i]
        if not (prev_bull and curr_bear and prev_body > 0):
            return False
        return curr_body < prev_body * 0.5 and open_p[i] < close[i - 1] and close[i] > open_p[i - 1]

    # Piercing Pattern: bear day -> bull day opens below, closes >50% into prev body
    def _is_piercing(i):
        if i < 1:
            return False
        prev_bear = close[i - 1] < open_p[i - 1]
        curr_bull = close[i] > open_p[i]
        if not (prev_bear and curr_bull):
            return False
        prev_body = _body(i - 1)
        if prev_body == 0:
            return False
        open_below = open_p[i] < low[i - 1]
        close_into = close[i] > (open_p[i - 1] + close[i - 1]) / 2
        return open_below and close_into and close[i] < open_p[i - 1]

    # Dark Cloud Cover: bull day -> bear day opens above, closes <50% into prev body
    def _is_dark_cloud(i):
        if i < 1:
            return False
        prev_bull = close[i - 1] > open_p[i - 1]
        curr_bear = close[i] < open_p[i]
        if not (prev_bull and curr_bear):
            return False
        prev_body = _body(i - 1)
        if prev_body == 0:
            return False
        open_above = open_p[i] > high[i - 1]
        close_into = close[i] < (open_p[i - 1] + close[i - 1]) / 2
        return open_above and close_into and close[i] > open_p[i - 1]

    # Abandoned Baby: doji gap on both sides
    def _is_abandoned_baby_bullish(i):
        if i < 2:
            return False
        prev_bear = close[i - 2] < open_p[i - 2]
        curr_bull = close[i] > open_p[i]
        doji = _body(i - 1) < _range(i - 1) * 0.05
        gap_down = low[i - 1] < min(low[i - 2], low[i])
        gap_up = high[i] > high[i - 1] and low[i] > high[i - 1]
        return prev_bear and curr_bull and doji and gap_down and gap_up

    def _is_abandoned_baby_bearish(i):
        if i < 2:
            return False
        prev_bull = close[i - 2] > open_p[i - 2]
        curr_bear = close[i] < open_p[i]
        doji = _body(i - 1) < _range(i - 1) * 0.05
        gap_up = high[i - 1] > max(high[i - 2], high[i])
        gap_down = low[i] < low[i - 1] and high[i] < low[i - 1]
        return prev_bull and curr_bear and doji and gap_up and gap_down

    # 3-bar Engulfing: 3 consecutive candles engulfing
    def _is_3bar_engulfing_bullish(i):
        if i < 3:
            return False
        three_bear = all(close[j] < open_p[j] for j in range(i - 3, i))
        curr_bull = close[i] > open_p[i]
        if not (three_bear and curr_bull):
            return False
        return close[i] > max(open_p[i - 1], open_p[i - 2], open_p[i - 3])

    def _is_3bar_engulfing_bearish(i):
        if i < 3:
            return False
        three_bull = all(close[j] > open_p[j] for j in range(i - 3, i))
        curr_bear = close[i] < open_p[i]
        if not (three_bull and curr_bear):
            return False
        return close[i] < min(close[i - 1], close[i - 2], close[i - 3])

    avg_vol = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())

    for i in range(max(4, len(close) - 20), len(close)):
        vol = float(volume[i])
        vol_conf = vol > avg_vol * 0.8

        if _is_harami_bullish(i):
            score += 5
            details.append(f"Harami Bullish @ {i} (+5)")
        if _is_harami_bearish(i):
            score -= 5
            details.append(f"Harami Bearish @ {i} (-5)")
        if _is_piercing(i):
            score += 7
            details.append(f"Piercing Pattern @ {i} (+7)")
        if _is_dark_cloud(i):
            score -= 7
            details.append(f"Dark Cloud Cover @ {i} (-7)")
        if _is_abandoned_baby_bullish(i):
            score += 12
            details.append(f"Abandoned Baby Bullish @ {i} (+12 strong reversal)")
        if _is_abandoned_baby_bearish(i):
            score -= 12
            details.append(f"Abandoned Baby Bearish @ {i} (-12 strong reversal)")
        if _is_3bar_engulfing_bullish(i):
            score += 8
            details.append(f"3-Bar Engulfing Bullish @ {i} (+8)")
        if _is_3bar_engulfing_bearish(i):
            score -= 8
            details.append(f"3-Bar Engulfing Bearish @ {i} (-8)")

    if not details:
        details.append("No advanced patterns")
    return min(100, max(0, score)), " | ".join(details)


def compute_risk_reward(hist: pd.DataFrame, current_price: float) -> tuple[int, str]:
    """
    Risk/Reward Ratio calculation.
    Computes RRR based on nearest support/resistance, ATR-based stops,
    and Kelly-inspired position sizing recommendation.
    """
    if hist.empty or len(hist) < 20:
        return 50, "Insufficient data"

    score = 50
    details = []
    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values

    # ATR(14)
    tr = []
    for i in range(1, len(close)):
        tr.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        ))
    tr = np.array(tr)
    atr14 = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)

    # Nearest swing support/resistance
    recent = hist.tail(60)
    swing_low = float(recent["Low"].min())
    swing_high = float(recent["High"].max())
    range_ = swing_high - swing_low

    # Distance to support and resistance
    dist_to_support = (current_price - swing_low) / current_price if current_price > 0 else 0
    dist_to_resistance = (swing_high - current_price) / current_price if current_price > 0 else 0

    # RRR calculation: reward = dist to resistance, risk = ATR-based or dist to support
    reward_pct = dist_to_resistance
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

    # ATR-based stop suggestion
    stop_2atr = current_price - (2 * atr14)
    stop_1atr = current_price - (1 * atr14)
    details.append(f"ATR14=${atr14:.2f} | Stop 1ATR=${stop_1atr:.2f} | Stop 2ATR=${stop_2atr:.2f}")

    # Position sizing (Kelly-inspired)
    if dist_to_support > 0 and dist_to_resistance > 0:
        win_prob = 0.55  # base probability
        kelly_fraction = win_prob - (1 - win_prob) / (reward_pct / risk_pct) if risk_pct > 0 else 0
        kelly_fraction = max(0, min(0.25, kelly_fraction))
        if kelly_fraction > 0.1:
            score += 10
            details.append(f"Kelly sizing {kelly_fraction:.0%} (favorable +10)")
        else:
            score += 5
            details.append(f"Kelly sizing {kelly_fraction:.0%} (conservative +5)")

    return min(100, max(0, score)), " | ".join(details)


def compute_psychology_advanced(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Advanced Trading Psychology: Cycle of Doom detection, cognitive biases,
    sentiment extreme oscillation, volume climax exhaustion.
    """
    if hist.empty or len(hist) < 30:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values
    volume = hist["Volume"].values

    # Cycle of Doom stages: Hope -> Panic -> Capitulation -> Anger -> Depression
    # Detect via consecutive red candles, volume patterns, price acceleration
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

    # Volume climax exhaustion
    if len(volume) >= 5:
        vol_now = float(volume[-1])
        vol_20avg = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
        vol_ratio = vol_now / vol_20avg if vol_20avg > 0 else 1

        if vol_ratio > 3.0 and reds >= 3:
            score = min(score + 20, 100)
            details.append(f"Selling climax (vol {vol_ratio:.1f}x + reds {reds}) (+20)")
        elif vol_ratio > 3.0 and greens >= 3:
            score = max(score - 20, 0)
            details.append(f"Buying climax (vol {vol_ratio:.1f}x + greens {greens}) (-20)")
        elif reds >= 3 and vol_ratio < 0.5:
            score = min(score + 10, 100)
            details.append(f"Exhaustion selling (low vol + reds) (+10)")

    # Disposition effect proxy: price stuck in narrow range on declining vol
    if len(close) >= 20:
        range_5d = (max(close[-5:]) - min(close[-5:])) / close[-1] if close[-1] != 0 else 0
        range_20d = (max(close[-20:]) - min(close[-20:])) / close[-1] if close[-1] != 0 else 0
        vol_trend = float(volume[-5:].mean()) / float(volume[-20:].mean()) if float(volume[-20:].mean()) > 0 else 1

        if range_5d < range_20d * 0.2 and vol_trend < 0.7:
            score += 10
            details.append("Indecision compression (breakout imminent +10)")

    # Anchoring bias: price far from 52w high = capitulation
    if len(close) >= 60:
        h52 = max(high[-60:])
        l52 = min(low[-60:])
        pos_52 = (close[-1] - l52) / (h52 - l52) if h52 != l52 else 0.5
        if pos_52 < 0.15:
            score = min(score + 15, 100)
            details.append(f"Near 52w low ({pos_52:.0%}) — anchoring/extreme fear (+15)")
        elif pos_52 > 0.85:
            score = max(score - 15, 0)
            details.append(f"Near 52w high ({pos_52:.0%}) — anchoring/greed (-15)")

    if not details:
        details.append("Psychology advanced neutral")
    return min(100, max(0, score)), " | ".join(details)


def compute_point_figure(hist: pd.DataFrame) -> tuple[int, str]:
    """
    Point & Figure simplified projection (Trades About to Happen - Weis).
    Uses box count method: 1% box size, 3-box reversal, horizontal count
    for projection targets.
    """
    if hist.empty or len(hist) < 40:
        return 50, "Insufficient data"

    score = 50
    details = []
    close = hist["Close"].values
    high = hist["High"].values

    # Box size: 1% of average price
    avg_price = np.mean(close[-40:])
    box_size = avg_price * 0.01  # 1% box

    # Build P&F columns using high-based method (simplified)
    columns = []
    current_col = {"direction": None, "boxes": 0, "start_price": close[0]}

    for i in range(1, len(close)):
        box_move = (close[i] - current_col["start_price"]) / box_size

        if current_col["direction"] is None:
            if abs(box_move) >= 3:
                current_col["direction"] = "up" if box_move > 0 else "down"
                current_col["boxes"] = int(abs(box_move))
                current_col["start_price"] = close[i]
        elif current_col["direction"] == "up":
            if box_move <= -3:
                columns.append(current_col)
                current_col = {"direction": "down", "boxes": int(abs(box_move)),
                             "start_price": close[i]}
            elif box_move > current_col["boxes"]:
                current_col["boxes"] = int(box_move)
        else:  # down
            if box_move >= 3:
                columns.append(current_col)
                current_col = {"direction": "up", "boxes": int(box_move),
                             "start_price": close[i]}
            elif abs(box_move) > current_col["boxes"]:
                current_col["boxes"] = int(abs(box_move))
    columns.append(current_col)

    if len(columns) < 3:
        return 50, "Not enough P&F columns"

    # Horizontal count projection (bullish)
    recent_cols = columns[-5:]
    up_cols = [c for c in recent_cols if c["direction"] == "up"]
    down_cols = [c for c in recent_cols if c["direction"] == "down"]

    if up_cols:
        # Bullish count: width of congestion × box × 3 = projection up
        congestion_up = sorted(up_cols, key=lambda x: x["boxes"], reverse=True)
        if len(congestion_up) >= 3:
            congestion_width = len(up_cols) * 3  # 3-column reversal
            horizontal_count = congestion_width * 3  # standard P&F multiplier
            projection = close[-1] + (horizontal_count * box_size)
            if projection > close[-1] * 1.05:
                score += 15
                details.append(f"P&F bullish target ${projection:.2f} (+{projection/close[-1]-1:+.1%}) (+15)")
            else:
                score += 5
                details.append(f"P&F bullish target ${projection:.2f} (+5)")

    if down_cols:
        congestion_down = sorted(down_cols, key=lambda x: x["boxes"], reverse=True)
        if len(congestion_down) >= 3:
            congestion_width = len(down_cols) * 3
            horizontal_count = congestion_width * 3
            projection = close[-1] - (horizontal_count * box_size)
            if projection < close[-1] * 0.95:
                score -= 15
                details.append(f"P&F bearish target ${projection:.2f} ({projection/close[-1]-1:+.1%}) (-15)")

    # Column sequence analysis: lower highs = distribution
    col_dirs = [c["direction"] for c in columns[-6:]]
    if col_dirs.count("down") > col_dirs.count("up"):
        score -= 10
        details.append(f"P&F: {col_dirs.count('down')}D vs {col_dirs.count('up')}U columns (bearish -10)")
    elif col_dirs.count("up") > col_dirs.count("down"):
        score += 10
        details.append(f"P&F: {col_dirs.count('up')}U vs {col_dirs.count('down')}D columns (bullish +10)")

    if not details:
        details.append(f"P&F {len(columns)} columns | box size ${box_size:.2f}")
    return min(100, max(0, score)), " | ".join(details)


def process_crypto_ticker(ticker_dict: dict) -> dict | None:
    symbol = ticker_dict["symbol"]
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None

        price = float(hist["Close"].iloc[-1])
        if price < 0.01:
            return None

        wyckoff_score, wyckoff_d = compute_wyckoff(hist, {})
        volprof_score, volprof_d = compute_volume_profile(hist)
        pa_score, pa_d = compute_price_action(hist)
        crypto_score, crypto_d = compute_crypto_analysis(t, hist)
        mtf_score, mtf_d = compute_multiframe_trend(hist)
        sot_score, sot_d = compute_sot_weis_wave(hist)

        candle_score, candle_d = compute_candlestick_patterns(hist)
        fib_score, fib_d = compute_fibonacci(hist)
        bb_score, bb_d = compute_bollinger(hist)
        obv_score, obv_d = compute_obv(hist)
        sr_score, sr_d = compute_support_resistance(hist)
        psych_score, psych_d = compute_psychology_score(hist)

        # NEW v2: Ichimoku, Adv Candles, Risk/Reward, Psych Adv, P&F
        ichi_score, ichi_d = compute_ichimoku(hist)
        candle_adv_score, candle_adv_d = compute_candlestick_advanced(hist)
        risk_reward_score, risk_reward_d = compute_risk_reward(hist, price)
        psych_adv_score, psych_adv_d = compute_psychology_advanced(hist)
        pf_score, pf_d = compute_point_figure(hist)

        mtf_mod = (mtf_score - 50) * 0.2
        sot_mod = (sot_score - 50) * 0.2
        wyckoff_adj = min(100, max(0, wyckoff_score + sot_mod))
        pa_adj = min(100, max(0, pa_score + mtf_mod))

        new_mod = (
            (candle_score - 50) * 0.10 +
            (fib_score - 50) * 0.10 +
            (bb_score - 50) * 0.10 +
            (obv_score - 50) * 0.10 +
            (sr_score - 50) * 0.10 +
            (psych_score - 50) * 0.10 +
            (ichi_score - 50) * 0.06 +
            (candle_adv_score - 50) * 0.06 +
            (risk_reward_score - 50) * 0.06 +
            (psych_adv_score - 50) * 0.06 +
            (pf_score - 50) * 0.06
        )

        final = (
            wyckoff_adj * 0.25 + volprof_score * 0.25 +
            pa_adj * 0.20 + crypto_score * 0.30 +
            new_mod
        )
        final = min(100, max(0, round(final, 1)))

        return {
            "symbol": symbol,
            "name": ticker_dict["name"],
            "market": "CRYPTO",
            "sector": "Cryptocurrency",
            "price": round(price, 4),
            "final_score": round(final, 1),
            "wyckoff": wyckoff_score,
            "volprof": volprof_score,
            "pa": pa_score,
            "sentiment": crypto_score,
            "fundamentals": 0,
            "competitive": 0,
            "pattern": "Crypto APC",
            "wyckoff_detail": wyckoff_d,
            "volprof_detail": volprof_d,
            "pa_detail": pa_d,
            "sentiment_detail": crypto_d,
            "fundamentals_detail": "N/A (crypto)",
            "competitive_detail": "N/A (crypto)",
            "mtf": mtf_score,
            "mtf_detail": mtf_d,
            "sot_weis": sot_score,
            "sot_weis_detail": sot_d,
            "squeeze": None,
            "squeeze_detail": "N/A (crypto)",
            "earnings_surprise": None,
            "earnings_surprise_detail": "N/A (crypto)",
            "clue6": None,
            "clue6_detail": "N/A (crypto)",
            "earnings_proximity": None,
            "sentiment_sub_si": None,
            "sentiment_sub_options": None,
            "sentiment_sub_insider": None,
            "sentiment_sub_retail": None,
            "sentiment_sub_institutional": None,
            "sentiment_sub_momentum": None,
            "sentiment_sub_earnings_quality": None,
            "sentiment_sub_web_news": None,
            "sentiment_sub_social_media": None,
            "candlestick": candle_score,
            "candlestick_detail": candle_d,
            "fibonacci": fib_score,
            "fibonacci_detail": fib_d,
            "bollinger": bb_score,
            "bollinger_detail": bb_d,
            "obv": obv_score,
            "obv_detail": obv_d,
            "support_resistance": sr_score,
            "support_resistance_detail": sr_d,
            "psychology": psych_score,
            "psychology_detail": psych_d,
            # NEW v2: Ichimoku, Adv Candles, Risk/Reward, Psych Adv, P&F
            "ichimoku": ichi_score,
            "ichimoku_detail": ichi_d,
            "candlestick_advanced": candle_adv_score,
            "candlestick_advanced_detail": candle_adv_d,
            "risk_reward": risk_reward_score,
            "risk_reward_detail": risk_reward_d,
            "psychology_advanced": psych_adv_score,
            "psychology_advanced_detail": psych_adv_d,
            "point_figure": pf_score,
            "point_figure_detail": pf_d,
        }
    except Exception:
        return None


def identify_pattern(wyckoff_score, volprof_score, pa_score, sentiment_score, fundamentals_score, info, wyckoff_detail: str, sentiment_subs: dict | None = None):
    si = info.get("shortPercentOfFloat", 0) or 0

    # Extract sentiment sub-scores for accurate pattern matching
    web_news = sentiment_subs.get("web_news") if sentiment_subs else None
    social = sentiment_subs.get("social_media") if sentiment_subs else None

    if wyckoff_score >= 70 and "Spring" in wyckoff_detail:
        return "Accumulation Spring"
    if volprof_score >= 70 and fundamentals_score >= 60:
        return "D-Profile Value Zone"
    if volprof_score >= 70 and pa_score >= 70 and social is not None and social >= 60:
        return "P-Profile Breakout"
    if social is not None and social >= 70 and pa_score >= 50:
        return "WSB Hype Confirmation"
    if web_news is not None and web_news >= 80 and wyckoff_score <= 70 and 40 <= pa_score <= 60:
        return "News Catalyst Buildup"
    if pa_score >= 70 and sentiment_score >= 50:
        return "P-Profile Breakout"
    if sentiment_score >= 70 and si > 0.20:
        return "Squeeze Setup"
    if wyckoff_score >= 65 and fundamentals_score >= 60:
        return "Golden Cross Accumulation"
    if volprof_score < 30:
        return "b-Profile Trap"
    return "Mixed / No dominant pattern"


def apply_macro_regime(results: list[dict], regime: str = "NORMAL") -> list[dict]:
    """Apply post-aggregation macro regime multiplier with sector awareness."""
    defensive_sectors = {"Utilities", "Consumer Defensive", "Healthcare", "Real Estate"}
    cyclical_sectors = {"Energy", "Financial Services", "Consumer Cyclical",
                         "Industrials", "Basic Materials", "Communication Services"}

    regime = regime.upper()
    for r in results:
        sector = r.get("sector", "")
        base = r["final_score"]

        if regime == "FULL":
            r["final_score"] = min(100, round(base * 1.08, 1))
        elif regime == "SELECTIVE":
            if sector in defensive_sectors:
                r["final_score"] = min(100, round(base * 1.05, 1))
            elif sector in cyclical_sectors:
                r["final_score"] = round(base * 0.90, 1)
        elif regime == "DEFENSIVE":
            r["final_score"] = min(60, round(base * 0.85, 1))
        # NORMAL: no change

    return results


def process_ticker(ticker_dict: dict) -> dict | None:
    symbol = ticker_dict["symbol"]
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        hist = t.history(period="1y")
        if hist.empty:
            return None

        price = info.get("currentPrice") or float(hist["Close"].iloc[-1])
        if price is None or price < 1.0:
            return None

        wyckoff_score, wyckoff_d = compute_wyckoff(hist, info)
        volprof_score, volprof_d = compute_volume_profile(hist)
        pa_score, pa_d = compute_price_action(hist)
        fundamentals_score, fundamentals_d = compute_fundamentals(info)
        competitive_score, competitive_d = compute_competitive_positioning(info)

        mtf_score, mtf_d = compute_multiframe_trend(hist)
        sot_score, sot_d = compute_sot_weis_wave(hist)
        squeeze_score, squeeze_d = compute_squeeze_play(t, info, hist)
        earnings_surprise_score, earnings_surprise_d = compute_earnings_surprise(t)
        clue6_score, clue6_d = compute_6clue_test(hist, info)

        # NEW: Candlestick, Fibonacci, Bollinger, OBV, S/R, Psychology
        candle_score, candle_d = compute_candlestick_patterns(hist)
        fib_score, fib_d = compute_fibonacci(hist)
        bb_score, bb_d = compute_bollinger(hist)
        obv_score, obv_d = compute_obv(hist)
        sr_score, sr_d = compute_support_resistance(hist)
        psych_score, psych_d = compute_psychology_score(hist)

        # NEW v2: Ichimoku, Advanced Candles, Risk/Reward, Psych Advanced, P&F
        ichi_score, ichi_d = compute_ichimoku(hist)
        candle_adv_score, candle_adv_d = compute_candlestick_advanced(hist)
        risk_reward_score, risk_reward_d = compute_risk_reward(hist, price)
        psych_adv_score, psych_adv_d = compute_psychology_advanced(hist)
        pf_score, pf_d = compute_point_figure(hist)

        # 8-dimension sentiment engine (news + social + traditional)
        spx_hist = _get_spx_hist()
        sentiment_score, sentiment_d, sentiment_subs = compute_sentiment_6d(
            t, info, hist, spx_hist,
            wsb_hotlist=_WSB_HOTLIST,
            fetch_news=_FETCH_NEWS,
        )

        earnings_adj = None
        earnings_dates = info.get("earningsDate")
        if earnings_dates:
            try:
                next_earn = earnings_dates[0] if isinstance(earnings_dates, list) else earnings_dates
                if hasattr(next_earn, "timestamp"):
                    days_to = int((next_earn.timestamp() - time.time()) / 86400)
                else:
                    days_to = None
                iv_rank_val = info.get("impliedVolatility")
                if iv_rank_val is not None:
                    iv_rank_val = min(100, max(0, iv_rank_val * 100))
                earnings_adj = earnings_proximity_adjustment(symbol, days_to, iv_rank_val)
            except Exception:
                pass

        # 5-dimension weighted scoring (Competitive merged into Fundamentals)
        # New dimensions act as modifiers on existing scores (±10 pts each)
        mtf_mod = (mtf_score - 50) * 0.2
        sot_mod = (sot_score - 50) * 0.2
        squeeze_mod = (squeeze_score - 50) * 0.2
        es_mod = (earnings_surprise_score - 50) * 0.2 if earnings_surprise_score is not None else 0
        clue6_mod = (clue6_score - 50) * 0.2

        wyckoff_adj = min(100, max(0, wyckoff_score + sot_mod + clue6_mod))
        pa_adj = min(100, max(0, pa_score + mtf_mod))
        sentiment_adj = min(100, max(0, sentiment_score + squeeze_mod))
        fundamentals_adj = min(100, max(0, fundamentals_score + es_mod))

        # New book-concept scores: candlestick, fibonacci, bollinger, obv, s/r, psychology
        # + ichimoku, advanced candles, risk/reward, psych advanced, point & figure
        # Each contributes a small modifier (±5 pts max) to keep the 5-dimension base intact
        new_mod = (
            (candle_score - 50) * 0.10 +
            (fib_score - 50) * 0.10 +
            (bb_score - 50) * 0.10 +
            (obv_score - 50) * 0.10 +
            (sr_score - 50) * 0.10 +
            (psych_score - 50) * 0.10 +
            (ichi_score - 50) * 0.06 +
            (candle_adv_score - 50) * 0.06 +
            (risk_reward_score - 50) * 0.06 +
            (psych_adv_score - 50) * 0.06 +
            (pf_score - 50) * 0.06
        )

        final = (
            wyckoff_adj * 0.20 + volprof_score * 0.20 +
            pa_adj * 0.15 + sentiment_adj * 0.20 +
            fundamentals_adj * 0.25 +
            new_mod
        )
        final = min(100, max(0, round(final, 1)))

        pattern = identify_pattern(
            wyckoff_score, volprof_score, pa_score,
            sentiment_score, fundamentals_score, info, wyckoff_d,
            sentiment_subs
        )

        return {
            "symbol": symbol,
            "name": ticker_dict["name"],
            "market": ticker_dict.get("market", "US"),
            "sector": info.get("sector", ""),
            "price": round(price, 2),
            "final_score": round(final, 1),
            "wyckoff": wyckoff_score,
            "volprof": volprof_score,
            "pa": pa_score,
            "sentiment": sentiment_score,
            "fundamentals": fundamentals_score,
            "competitive": competitive_score,  # merged into fundamentals, kept for backward compat
            "pattern": pattern,
            "wyckoff_detail": wyckoff_d,
            "volprof_detail": volprof_d,
            "pa_detail": pa_d,
            "sentiment_detail": sentiment_d,
            "fundamentals_detail": fundamentals_d,
            "competitive_detail": competitive_d,
            "mtf": mtf_score,
            "mtf_detail": mtf_d,
            "sot_weis": sot_score,
            "sot_weis_detail": sot_d,
            "squeeze": squeeze_score,
            "squeeze_detail": squeeze_d,
            "earnings_surprise": earnings_surprise_score,
            "earnings_surprise_detail": earnings_surprise_d,
            "clue6": clue6_score,
            "clue6_detail": clue6_d,
            # Sub-dimension breakdown
            "sentiment_sub_si": sentiment_subs.get("short_interest"),
            "sentiment_sub_options": sentiment_subs.get("options_sentiment"),
            "sentiment_sub_insider": sentiment_subs.get("insider_trading"),
            "sentiment_sub_retail": sentiment_subs.get("retail_sentiment"),
            "sentiment_sub_institutional": sentiment_subs.get("institutional"),
            "sentiment_sub_momentum": sentiment_subs.get("momentum"),
            "sentiment_sub_earnings_quality": sentiment_subs.get("earnings_quality"),
            "sentiment_sub_web_news": sentiment_subs.get("web_news"),
            "sentiment_sub_social_media": sentiment_subs.get("social_media"),
            "earnings_proximity": earnings_adj,
            # NEW book-concept scores
            "candlestick": candle_score,
            "candlestick_detail": candle_d,
            "fibonacci": fib_score,
            "fibonacci_detail": fib_d,
            "bollinger": bb_score,
            "bollinger_detail": bb_d,
            "obv": obv_score,
            "obv_detail": obv_d,
            "support_resistance": sr_score,
            "support_resistance_detail": sr_d,
            "psychology": psych_score,
            "psychology_detail": psych_d,
            # NEW v2: Ichimoku, Adv Candles, Risk/Reward, Psych Adv, P&F
            "ichimoku": ichi_score,
            "ichimoku_detail": ichi_d,
            "candlestick_advanced": candle_adv_score,
            "candlestick_advanced_detail": candle_adv_d,
            "risk_reward": risk_reward_score,
            "risk_reward_detail": risk_reward_d,
            "psychology_advanced": psych_adv_score,
            "psychology_advanced_detail": psych_adv_d,
            "point_figure": pf_score,
            "point_figure_detail": pf_d,
        }
    except Exception:
        return None


def print_table(results: list[dict], top_n: int):
    print(f"\n{'#' * 130}")
    print(f"  Top {top_n} Candidates")
    print(f"{'#' * 130}")
    print(f"{'#':<4} {'Ticker':<8} {'Name':<20} {'Scr':<4} {'W':<3} {'V':<3} {'P':<3} {'S':<3} {'F':<3} {'Ca':<3} {'Fi':<3} {'BB':<3} {'Ob':<3} {'SR':<3} {'Ps':<3} {'I':<3} {'RR':<3} {'PF':<3} {'Pattern':<18}")
    print(f"{'─' * 4} {'─' * 8} {'─' * 20} {'─' * 4} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 3} {'─' * 18}")

    for i, r in enumerate(results[:top_n], 1):
        name = r["name"][:18]
        print(f"{i:<4} {r['symbol']:<8} {name:<20} {r['final_score']:<4} {r['wyckoff']:<3} {r['volprof']:<3} {r['pa']:<3} {r['sentiment']:<3} {r['fundamentals']:<3} {r.get('candlestick', 0):<3} {r.get('fibonacci', 0):<3} {r.get('bollinger', 0):<3} {r.get('obv', 0):<3} {r.get('support_resistance', 0):<3} {r.get('psychology', 0):<3} {r.get('ichimoku', 0):<3} {r.get('risk_reward', 0):<3} {r.get('point_figure', 0):<3} {r['pattern']:<18}")


def generate_csv(results: list[dict], output_dir: str | Path) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(str(output_dir), f"scan_report_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "symbol", "name", "market", "sector", "price", "final_score",
                     "wyckoff", "volprof", "pa", "competitive", "sentiment", "fundamentals", "pattern",
                     "sent_si", "sent_options", "sent_insider", "sent_retail",
                     "sent_institutional", "sent_momentum",
                     "sent_earnings_quality", "sent_web_news", "sent_social_media",
                     "candlestick", "fibonacci", "bollinger", "obv", "support_resistance", "psychology",
                     "ichimoku", "candlestick_advanced", "risk_reward", "psychology_advanced", "point_figure"])
        for i, r in enumerate(results, 1):
            w.writerow([i, r["symbol"], r["name"], r["market"], r.get("sector", ""), r["price"],
                        r["final_score"], r["wyckoff"], r["volprof"], r["pa"],
                        r.get("competitive", ""), r["sentiment"], r["fundamentals"], r["pattern"],
                        r.get("sentiment_sub_si", ""), r.get("sentiment_sub_options", ""),
                        r.get("sentiment_sub_insider", ""), r.get("sentiment_sub_retail", ""),
                        r.get("sentiment_sub_institutional", ""), r.get("sentiment_sub_momentum", ""),
                        r.get("sentiment_sub_earnings_quality", ""), r.get("sentiment_sub_web_news", ""),
                        r.get("sentiment_sub_social_media", ""),
                        r.get("candlestick", ""), r.get("fibonacci", ""), r.get("bollinger", ""),
                        r.get("obv", ""), r.get("support_resistance", ""), r.get("psychology", ""),
                        r.get("ichimoku", ""), r.get("candlestick_advanced", ""),
                        r.get("risk_reward", ""), r.get("psychology_advanced", ""),
                        r.get("point_figure", "")])
    return path


def generate_html(results: list[dict], output_dir: str | Path, universe_name: str, total_scanned: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(str(output_dir), f"scan_report_{ts}.html")

    def color(val, max_val=100):
        ratio = val / max_val
        if ratio >= 0.7:
            return f"hsl({120 * ratio}, 70%, 85%)"
        elif ratio >= 0.5:
            return f"hsl({120 * ratio}, 50%, 90%)"
        else:
            return f"hsl(0, 60%, 92%)"

    rows_html = ""
    for i, r in enumerate(results, 1):
        rows_html += f"""<tr>
            <td>{i}</td>
            <td><strong>{r['symbol']}</strong></td>
            <td>{r['name'][:30]}</td>
            <td>{r.get('sector', '')[:20]}</td>
            <td style="background:{color(r['final_score'])}"><strong>{r['final_score']}</strong></td>
            <td style="background:{color(r['wyckoff'])}">{r['wyckoff']}</td>
            <td style="background:{color(r['volprof'])}">{r['volprof']}</td>
            <td style="background:{color(r['pa'])}">{r['pa']}</td>
            <td style="background:{color(r['sentiment'])}">{r['sentiment']}</td>
            <td style="background:{color(r['fundamentals'])}">{r['fundamentals']}</td>
            <td style="background:{color(r.get('candlestick', 0))}">{r.get('candlestick', 0)}</td>
            <td style="background:{color(r.get('fibonacci', 0))}">{r.get('fibonacci', 0)}</td>
            <td style="background:{color(r.get('bollinger', 0))}">{r.get('bollinger', 0)}</td>
            <td style="background:{color(r.get('obv', 0))}">{r.get('obv', 0)}</td>
            <td style="background:{color(r.get('support_resistance', 0))}">{r.get('support_resistance', 0)}</td>
            <td style="background:{color(r.get('psychology', 0))}">{r.get('psychology', 0)}</td>
            <td style="background:{color(r.get('ichimoku', 0))}">{r.get('ichimoku', 0)}</td>
            <td style="background:{color(r.get('risk_reward', 0))}">{r.get('risk_reward', 0)}</td>
            <td style="background:{color(r.get('point_figure', 0))}">{r.get('point_figure', 0)}</td>
            <td>{r['pattern']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Market Accumulation Scan - {ts}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; }}
h1 {{ color: #1a1a2e; }}
.subtitle {{ color: #666; margin-bottom: 20px; }}
table {{ border-collapse: collapse; width: 100%; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
th {{ background: #1a1a2e; color: white; padding: 12px 8px; text-align: left; font-size: 13px; }}
td {{ padding: 8px; border-bottom: 1px solid #eee; font-size: 13px; }}
tr:hover {{ opacity: 0.9; }}
.summary {{ background: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
.summary span {{ margin-right: 30px; }}
.score-dist {{ margin: 20px 0; height: 40px; display: flex; border-radius: 4px; overflow: hidden; }}
.dist-bar {{ display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: bold; }}
</style>
</head>
<body>
<h1>📊 Market Accumulation Scan</h1>
<div class="summary">
    <span><strong>Universe:</strong> {universe_name}</span>
    <span><strong>Scanned:</strong> {total_scanned}</span>
    <span><strong>Candidates:</strong> {len(results)}</span>
    <span><strong>Generated:</strong> {ts}</span>
</div>
<div class="score-dist">
    {''.join(f'<div class="dist-bar" style="width:{sum(1 for r in results if r["final_score"] >= (i*10))/max(len(results),1)*100:.1f}%;background:hsl({i*12},60%,50%)">{sum(1 for r in results if r["final_score"] >= (i*10))}</div>' for i in range(10, 0, -1)) if results else ''}
</div>
<table>
<tr>
    <th>#</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Score</th><th>WYCK</th><th>VP</th><th>PA</th><th>SENT</th><th>FUND</th><th>CNDL</th><th>FIB</th><th>BB</th><th>OBV</th><th>SR</th><th>PSY</th><th>ICH</th><th>RR</th><th>PF</th><th>Pattern</th>
</tr>
{rows_html}
</table>
<p style="color:#999;font-size:12px;margin-top:10px;">Generated by market-accumulation-scanner</p>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main():
    parser = argparse.ArgumentParser(description="Market Accumulation Scanner")
    parser.add_argument("--universe", default="us_large", help="Universe name")
    parser.add_argument("--tickers", help="Custom comma-separated ticker list")
    parser.add_argument("--min-score", type=float, default=50, help="Minimum score")
    parser.add_argument("--top", type=int, default=15, help="Top N to show")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size")
    parser.add_argument("--batch-sleep", type=float, default=1.0, help="Seconds between batches")
    parser.add_argument("--list-tickers", action="store_true",
                        help="Output ticker symbols as JSON array and exit")
    parser.add_argument("--json-output", action="store_true",
                        help="Output results as JSON array to stdout")
    parser.add_argument("--fetch-news", action="store_true",
                        help="Fetch Finviz news headlines for web news sentiment (slower)")
    parser.add_argument("--wsb-hotlist",
                        help="Path to JSON file with WSB hotlist from wallstreetbets-pump-detect")
    parser.add_argument("--regime", default="NORMAL",
                        choices=["FULL", "NORMAL", "SELECTIVE", "DEFENSIVE"],
                        help="Macro regime for post-aggregation score multiplier")
    args = parser.parse_args()

    # Set global flags for sentiment engine
    global _FETCH_NEWS, _WSB_HOTLIST
    _FETCH_NEWS = args.fetch_news
    if args.wsb_hotlist:
        try:
            with open(args.wsb_hotlist, "r") as f:
                _WSB_HOTLIST = json.load(f)
            log.info("Loaded WSB hotlist: %d tickers", len(_WSB_HOTLIST))
        except Exception as e:
            log.warning("Failed to load WSB hotlist: %s", e)

    if args.tickers:
        universe = parse_custom_tickers(args.tickers)
        universe_name = "custom"
    else:
        universe = load_universe(args.universe)
        universe_name = args.universe

    if args.list_tickers:
        tickers = [t["symbol"] for t in universe]
        print(json.dumps(tickers))
        return

    if args.output_dir == ".":
        output_dir = SKILL_DIR / "reports" / universe_name
    else:
        output_dir = Path(args.output_dir)

    total = len(universe)
    if not args.json_output:
        print(f"\n📋 Scanning {universe_name} — {total} tickers...")
        print(f"   Batch: {args.batch_size} | Sleep: {args.batch_sleep}s | Min score: {args.min_score}")
        print(f"   Regime: {args.regime}")

    results = []
    failures = 0
    t0 = time.time()

    for i in range(0, total, args.batch_size):
        batch = universe[i:i + args.batch_size]
        for t_dict in batch:
            if t_dict.get("market") == "CRYPTO":
                result = process_crypto_ticker(t_dict)
            else:
                result = process_ticker(t_dict)
            if result:
                results.append(result)
            else:
                failures += 1

        if not args.json_output:
            elapsed = time.time() - t0
            pct = min(100, (i + len(batch)) / total * 100)
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            eta = (total - i - len(batch)) / rate if rate > 0 else 0
            sys.stdout.write(f"\r   Progress: {min(total, i + len(batch))}/{total} ({pct:.0f}%) | "
                             f"Found: {len(results)} | "
                            f"Rate: {rate:.1f} tickers/s | ETA: {eta:.0f}s   ")
            sys.stdout.flush()

        if i + len(batch) < total:
            time.sleep(args.batch_sleep)

    elapsed = time.time() - t0
    if not args.json_output:
        print(f"\n\n✅ Scan completed in {elapsed:.0f}s")
        print(f"   Tickers processed: {total} | Failures: {failures} | Candidates: {len(results)}")

    results.sort(key=lambda r: r["final_score"], reverse=True)
    results = apply_macro_regime(results, args.regime)
    results.sort(key=lambda r: r["final_score"], reverse=True)  # re-sort after regime adjustment
    filtered = [r for r in results if r["final_score"] >= args.min_score]

    if not filtered:
        if args.json_output:
            print("[]")
        else:
            print(f"\n⚠ No candidates found with score >= {args.min_score}")
            print("   Try lowering the threshold with --min-score")
        return

    if args.json_output:
        print(json.dumps(filtered, indent=2, default=str))
        return

    print(f"\n   Candidates with score >= {args.min_score}: {len(filtered)}")

    print_table(filtered, args.top)

    csv_path = generate_csv(filtered, output_dir)
    print(f"\n📄 CSV report: {csv_path}")

    html_path = generate_html(filtered, output_dir, universe_name, total)
    print(f"📄 HTML report: {html_path}")

    print(f"\n{'─' * 70}")
    print(f"  TOP {min(3, len(filtered))} CANDIDATES FOR DEEP DIVE")
    print(f"{'─' * 70}")
    for i, r in enumerate(filtered[:3], 1):
        si = r.get("sentiment_sub_si")
        op = r.get("sentiment_sub_options")
        ins = r.get("sentiment_sub_insider")
        eq_qual = r.get("sentiment_sub_earnings_quality")
        wb_news = r.get("sentiment_sub_web_news")
        soc = r.get("sentiment_sub_social_media")
        comp = r.get("competitive", "-")
        sub_sent = f" SI={si}" if si else ""
        sub_sent += f" OPT={op}" if op else ""
        sub_sent += f" INS={ins}" if ins else ""
        sub_sent += f" EQ={eq_qual}" if eq_qual is not None else ""
        sub_sent += f" NEWS={wb_news}" if wb_news is not None else ""
        sub_sent += f" SOC={soc}" if soc is not None else ""
        print(f"\n  #{i}: {r['symbol']} ({r['name']}) — Score: {r['final_score']}")
        print(f"      Pattern: {r['pattern']}")
        print(f"      Wyckoff: {r['wyckoff']} | VP: {r['volprof']} | PA: {r['pa']} | Comp(merged): {comp} | Sent: {r['sentiment']}{sub_sent} | Fund: {r['fundamentals']}")
        print(f"      → Load stock-crypto-analysis on ${r['symbol']} for full verdict")


if __name__ == "__main__":
    main()
