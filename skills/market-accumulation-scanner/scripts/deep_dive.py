#!/usr/bin/env python3
"""Deep dive analysis on top 3 candidates using stock-crypto-analysis framework."""

import sys
import json
import yfinance as yf
import pandas as pd
import numpy as np

SKILL_DIR = "/home/giuseppe/.config/opencode/skills/market-accumulation-scanner"


def compute_rsi(series: pd.Series, periods: int = 14) -> float:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=periods - 1, adjust=True, min_periods=periods).mean()
    ma_down = down.ewm(com=periods - 1, adjust=True, min_periods=periods).mean()
    rs = ma_up / ma_down
    return float(100 - (100 / (1 + rs)).iloc[-1])


def wyckoff_phase(hist: pd.DataFrame) -> tuple[str, int, str]:
    if hist.empty or len(hist) < 50:
        return "Insufficient data", 40, "No data"
    price = float(hist["Close"].iloc[-1])
    high_1y = hist["High"].max()
    low_1y = hist["Low"].min()
    rangep = (price - low_1y) / (high_1y - low_1y) * 100 if (high_1y - low_1y) > 0 else 50

    recent = hist.tail(60)
    highs = recent["High"].values
    lows = recent["Low"].values
    half = len(highs) // 2
    hh_hl = highs[-1] > highs[half] and lows[-1] > lows[half]
    lh_ll = highs[-1] < highs[half] and lows[-1] < lows[half]

    spring = False
    recent_30 = hist.tail(30)
    low_30 = recent_30["Low"].min()
    low_idx = recent_30["Low"].idxmin()
    if low_idx and low_idx < hist.index[-5]:
        if price > low_30 * 1.05:
            spring = True

    vol_decreasing = False
    if len(hist) >= 90:
        vol_older = hist.tail(90).head(60)["Volume"].mean()
        vol_recent = hist.tail(30)["Volume"].mean()
        if vol_recent < vol_older * 0.8:
            vol_decreasing = True

    ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
    ma200_val = float(hist["Close"].rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None
    golden_cross = ma200_val and ma50 > ma200_val

    if spring and 30 <= rangep <= 60:
        phase = "Phase B-C (Accumulation with Spring)"
        score = 90
        detail = f"Spring confirmed at ${low_30:.2f}, price in accumulation zone ({rangep:.0f}% of range)"
    elif spring:
        phase = "Phase C (Spring / Shakeout)"
        score = 85
        detail = f"Spring detected at ${low_30:.2f}"
    elif hh_hl and golden_cross:
        phase = "Phase D-E (Markup)"
        score = 80
        detail = "HH/HL pattern with golden cross, markup phase"
    elif hh_hl:
        phase = "Phase D (Initial Effect / SOS)"
        score = 70
        detail = "HH/HL pattern, initial markup signal"
    elif 40 <= rangep <= 60 and vol_decreasing:
        phase = "Phase B (Cause Building / Accumulation)"
        score = 65
        detail = "Tight range {rangep:.0f}%, volume decreasing = absorption"
    elif 40 <= rangep <= 60:
        phase = "Phase B (Cause Building)"
        score = 50
        detail = "Neutral range at {rangep:.0f}%, no clear phase"
    elif lh_ll:
        phase = "Phase D-E (Markdown)"
        score = 15
        detail = "LH/LL pattern, distribution/markdown"
    else:
        phase = "Transitional"
        score = 40
        detail = f"Price at {rangep:.0f}% of range, no clear phase"

    return phase, score, detail


def volume_profile(hist: pd.DataFrame) -> tuple[str, int, str]:
    if hist.empty or len(hist) < 20:
        return "Insufficient", 30, "No data"

    price = float(hist["Close"].iloc[-1])
    h, l = hist["High"].max(), hist["Low"].min()
    span = h - l
    n_bins = 20
    bw = span / n_bins if span > 0 else 1
    df = hist.copy()
    df["bin"] = ((df["Close"] - l) / bw).astype(int).clip(0, n_bins - 1)
    vol_by_bin = df.groupby("bin")["Volume"].sum()
    poc_bin = vol_by_bin.idxmax()
    poc_price = l + (poc_bin + 0.5) * bw

    total_vol = vol_by_bin.sum()
    cum, va_bins = 0, []
    for b, v in vol_by_bin.sort_values(ascending=False).items():
        cum += v
        va_bins.append(b)
        if cum / total_vol >= 0.7:
            break
    val = l + min(va_bins) * bw
    vah = l + (max(va_bins) + 1) * bw

    pos_in_range = ((price - l) / span) * 100 if span > 0 else 50
    if 40 < pos_in_range < 60:
        shape = "D-Profile (Balanced)"
    elif price > vah and len(va_bins) > 5:
        shape = "P-Profile (Bullish tail)"
    elif price < val and len(va_bins) > 5:
        shape = "b-Profile (Bearish tail)"
    else:
        shape = "Mixed profile"

    vol_ratio = float(hist["Volume"].iloc[-1]) / float(hist["Volume"].iloc[-21:].mean()) if len(hist) >= 21 else 1.0

    if val <= price <= vah:
        pos_detail = f"Price inside VA (${val:.2f}-${vah:.2f})"
        pos_score = 60
    elif price < val:
        pos_detail = f"Price below VAL (${val:.2f}) — potential value zone"
        pos_score = 70
    else:
        pos_detail = f"Price above VAH (${vah:.2f}) — extended"
        pos_score = 40

    if abs(price - poc_price) / (poc_price or 1) < 0.05:
        pos_detail += f", near VPOC ${poc_price:.2f}"
        pos_score += 10

    score = pos_score
    detail = f"{shape} | {pos_detail} | Vol ratio: {vol_ratio:.1f}x"

    if vol_ratio > 2.0:
        detail += " (high)"
        score += 10
    elif vol_ratio > 1.5:
        detail += " (elevated)"
        score += 5

    return shape, min(score, 100), detail


def price_action(hist: pd.DataFrame) -> tuple[str, int, str]:
    if hist.empty or len(hist) < 20:
        return "Insufficient", 30, "No data"

    score = 40
    details = []

    rsi = compute_rsi(hist["Close"])
    if rsi < 30:
        rsi_desc = f"RSI {rsi:.0f} (oversold extreme)"
        details.append(rsi_desc)
    elif rsi < 40:
        rsi_desc = f"RSI {rsi:.0f} (oversold zone)"
        score += 15
        details.append(f"{rsi_desc} +15")
    elif rsi <= 60:
        rsi_desc = f"RSI {rsi:.0f} (neutral)"
        score += 5
        details.append(f"{rsi_desc} +5")
    else:
        rsi_desc = f"RSI {rsi:.0f} (overbought)"
        details.append(rsi_desc)

    hist2 = hist.copy()
    hist2["ema25"] = hist2["Close"].ewm(span=25).mean()
    if len(hist2) >= 30:
        slope = (hist2["ema25"].iloc[-1] - hist2["ema25"].iloc[-5]) / hist2["ema25"].iloc[-5]
        if abs(slope) < 0.002:
            details.append("25ema flat")
        elif slope > 0:
            score += 15
            details.append(f"25ema rising +15")
        else:
            details.append("25ema falling")

    last_20 = hist.tail(20)
    vpa_net = 0
    for i in range(1, len(last_20)):
        bar = last_20.iloc[i]
        prev = last_20.iloc[i - 1]
        vol = float(bar["Volume"])
        avg_v = float(last_20["Volume"].mean())
        vr = vol / avg_v if avg_v > 0 else 1
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
        details.append(f"VPA bullish (net {vpa_net}) +20")
    elif vpa_net > 0:
        score += 5
        details.append(f"VPA mildly bullish (net {vpa_net}) +5")
    elif vpa_net < -2:
        details.append(f"VPA bearish (net {vpa_net})")
    else:
        details.append(f"VPA mixed (net {vpa_net})")

    last_10 = hist.tail(10)
    vol_trend = "rising" if last_10["Volume"].iloc[-1] > last_10["Volume"].head(5).mean() else "stable/falling"

    close_series = hist["Close"]
    high_max = hist["High"].max()
    low_min = hist["Low"].min()
    buildup = 0
    for i in range(5, len(last_20)):
        window = last_20.iloc[i - 5:i]
        rng = window["High"].max() - window["Low"].min()
        wk_range = (high_max - low_min)
        if wk_range > 0 and rng / wk_range < 0.05:
            buildup += 1
    if buildup >= 2:
        score += 20
        details.append(f"Buildup detected ({buildup} tight clusters) +20")

    return f"VPA net {vpa_net}" if vpa_net else "Neutral", min(score, 100), " | ".join(details)


def sentiment(info: dict) -> tuple[int, str]:
    score = 40
    details = []

    si = info.get("shortPercentOfFloat")
    if si is not None:
        if si > 0.20:
            score += 30
            details.append(f"SI {si*100:.1f}% (high squeeze potential) +30")
        elif si > 0.10:
            score += 15
            details.append(f"SI {si*100:.1f}% (moderate) +15")
        else:
            details.append(f"SI {si*100:.1f}% (low)")
    else:
        details.append("SI N/A")

    inst = info.get("heldPercentInstitutions")
    if inst is not None:
        if inst > 0.70:
            score += 20
            details.append(f"Inst {inst*100:.0f}% (strong) +20")
        elif inst > 0.50:
            score += 10
            details.append(f"Inst {inst*100:.0f}% (moderate) +10")
        else:
            details.append(f"Inst {inst*100:.0f}% (low)")
    else:
        details.append("Inst N/A")

    dtc = info.get("shortRatio")
    if dtc is not None:
        if dtc > 7:
            score += 20
            details.append(f"DTC {dtc:.1f} (very high) +20")
        elif dtc > 3:
            score += 10
            details.append(f"DTC {dtc:.1f} (elevated) +10")
        else:
            details.append(f"DTC {dtc:.1f} (low)")

    return min(score, 100), " | ".join(details)


def fundamentals(info: dict) -> tuple[int, str]:
    score = 40
    details = []

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        if pe < 10:
            score += 30
            details.append(f"P/E {pe:.1f} (undervalued) +30")
        elif pe < 20:
            score += 20
            details.append(f"P/E {pe:.1f} (fair) +20")
        elif pe < 30:
            score += 10
            details.append(f"P/E {pe:.1f} (slight premium) +10")
        else:
            details.append(f"P/E {pe:.1f} (expensive)")
    else:
        details.append("P/E N/A")

    rev = info.get("revenueGrowth")
    if rev is not None:
        if rev > 0.10:
            score += 20
            details.append(f"Rev growth {rev*100:.0f}% (strong) +20")
        elif rev > 0:
            score += 10
            details.append(f"Rev growth {rev*100:.0f}% (positive) +10")
        else:
            details.append(f"Rev growth {rev*100:.0f}% (shrinking)")

    margins = info.get("profitMargins")
    if margins is not None:
        if margins > 0.15:
            score += 15
            details.append(f"Margins {margins*100:.0f}% (healthy) +15")
        elif margins > 0:
            score += 5
            details.append(f"Margins {margins*100:.0f}% (positive) +5")
        else:
            details.append(f"Margins {margins*100:.0f}% (negative)")

    de = info.get("debtToEquity")
    if de is not None:
        if de < 0.3:
            score += 15
            details.append(f"D/E {de:.2f} (low debt) +15")
        elif de < 1.0:
            score += 5
            details.append(f"D/E {de:.2f} (manageable) +5")
        elif de < 2.0:
            details.append(f"D/E {de:.2f} (moderate)")
        else:
            score -= 10
            details.append(f"D/E {de:.2f} (high leverage) -10")

    mcap = info.get("marketCap")
    if mcap is not None and mcap > 10e9:
        score += 5
        details.append(f"MCap ${mcap/1e9:.1f}B (large cap) +5")

    roe = info.get("returnOnEquity")
    if roe is not None and roe > 0.10:
        score += 10
        details.append(f"ROE {roe*100:.0f}% (strong) +10")

    return min(score, 100), " | ".join(details)


def analyze_ticker(symbol: str, name: str, scan_scores: dict):
    print(f"\n{'='*80}")
    print(f"  DEEP DIVE: {symbol} — {name}")
    print(f"  Scanner Score: {scan_scores['final_score']} | Pattern: {scan_scores['pattern']}")
    print(f"{'='*80}")

    t = yf.Ticker(symbol)
    info = t.info or {}
    hist = t.history(period="1y")

    if hist.empty:
        print("  ❌ No historical data available")
        return

    price = info.get("currentPrice") or float(hist["Close"].iloc[-1])
    price_prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
    change_pct = ((price - price_prev) / price_prev) * 100

    print(f"\n  📊 Prezzo: ${price:.2f} ({change_pct:+.2f}%)")
    print(f"  🏭 Settore: {info.get('sector', 'N/A')} | Industria: {info.get('industry', 'N/A')}")
    print(f"  💰 MCap: ${info.get('marketCap', 0)/1e9:.1f}B | EPS: {info.get('trailingEps', 'N/A')}")

    w_phase, w_score, w_detail = wyckoff_phase(hist)
    v_shape, v_score, v_detail = volume_profile(hist)
    pa_desc, pa_score, pa_detail = price_action(hist)
    s_score, s_detail = sentiment(info)
    f_score, f_detail = fundamentals(info)

    weights = {"wyckoff": 0.25, "volprof": 0.20, "pa": 0.20, "sentiment": 0.15, "fundamentals": 0.20}
    final = (
        w_score * weights["wyckoff"] +
        v_score * weights["volprof"] +
        pa_score * weights["pa"] +
        s_score * weights["sentiment"] +
        f_score * weights["fundamentals"]
    )

    if final >= 70:
        verdict = "LONG-TERM INVESTMENT 🟢"
    elif final >= 50:
        verdict = "SHORT-TERM SPECULATION 🟡"
    else:
        verdict = "AVOID / WAIT 🔴"

    print(f"\n  {'─'*60}")
    print(f"  📋 Unified Verdict: {verdict}")
    print(f"  Score: {final:.0f}% (pesato su 5 dimensioni)")
    print(f"  {'─'*60}")

    print(f"\n  ### Perché")
    print(f"  - **Wyckoff Phase** ({w_phase}): {w_detail} → [{w_score}/100]")
    print(f"  - **Volume Profile** ({v_shape}): {v_detail} → [{v_score}/100]")
    print(f"  - **Price Action** ({pa_desc}): {pa_detail} → [{pa_score}/100]")
    print(f"  - **Sentiment**: {s_detail} → [{s_score}/100]")
    print(f"  - **Fondamentali**: {f_detail} → [{f_score}/100]")

    print(f"\n  ### Raccomandazione Finale")

    mgmt = "DCA su weakness" if final >= 70 else "Singolo ingresso tattico"
    sl = f"${price * 0.92:.2f}" if final >= 50 else f"${price * 0.95:.2f}"
    t1 = f"${price * 1.10:.2f}"
    t2 = f"${price * 1.25:.2f}" if final >= 50 else f"${price * 1.10:.2f}"
    horizon = "6-12 mesi" if final >= 70 else "4-8 settimane"
    sizing = "5-8%" if final >= 70 else "2-3%" if final >= 50 else "1%"

    print(f"  | Azione | Entry | Stop Loss | Target 1 | Target 2 | Orizzonte | Sizing |")
    print(f"  |--------|-------|-----------|----------|----------|-----------|--------|")
    entry_range = f"${price * 0.95:.2f}-{price:.2f}" if final >= 50 else "$—"
    print(f"  | {'**Entry**' if final >= 50 else '**Wait/Avoid**'} | {entry_range} | {sl} | {t1} | {t2} | {horizon} | {sizing} |")

    print(f"\n  ### Rischio")
    risk = "Basso" if final >= 70 else "Medio" if final >= 50 else "Alto"
    risks = []
    if info.get("nextEarningsDate") and final >= 50:
        risks.append(f"Earnings il {info.get('nextEarningsDate')}")
    if w_score < 50:
        risks.append("Wyckoff debole — possibile distribuzione")
    if v_score < 40:
        risks.append("Struttura VP debole")
    if f_score < 40:
        risks.append("Fondamentali in deterioramento")
    if not risks:
        risks.append("Rischio di mercato generale")
    print(f"  Livello: {risk}")
    print(f"  Fattori: {', '.join(risks)}")


def main():
    print("\n" + "█" * 80)
    print("  STOCK-CRYPTO-ANALYSIS — DEEP DIVE TOP 3 EUROPEI")
    print("█" * 80)

    tickers = [
        {"symbol": "DBK.DE", "name": "Deutsche Bank AG", "scan_scores": {"final_score": 66.0, "pattern": "Accumulation Spring"}},
        {"symbol": "SGRO.L", "name": "Segro plc", "scan_scores": {"final_score": 65.0, "pattern": "Accumulation Spring"}},
        {"symbol": "PST.MI", "name": "Poste Italiane S.p.A.", "scan_scores": {"final_score": 63.8, "pattern": "Accumulation Spring"}},
    ]

    for t in tickers:
        analyze_ticker(t["symbol"], t["name"], t["scan_scores"])

    print(f"\n{'█'*80}")
    print("  DEEP DIVE COMPLETATO")
    print(f"{'█'*80}\n")


if __name__ == "__main__":
    main()
