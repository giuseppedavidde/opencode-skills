"""Unified stock analysis for any ticker — produces Wyckoff + Volume Profile + Price Action + Sentiment + Fundamentals verdict."""
import argparse, json, sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Use the 6-dimension sentiment engine
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from sentiment_engine import compute_sentiment as compute_sentiment_6d


def heading(s: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {s}")
    print(f"{'='*60}")


def analyze(ticker: str, verbose: bool = True) -> dict:
    df, info = _fetch(ticker)
    if df is None or df.empty:
        return {"ticker": ticker, "error": "No data"}

    df = _compute_ma(df)

    wyckoff_phase, wyckoff_score, wyckoff_d = _wyckoff(df)
    vp_shape, vp_score, vp_d = _volume_profile(df)
    pa_verdict, pa_score, pa_d = _price_action(df)
    fund_score, fund_d = _fundamentals(info, ticker)

    # 6-dimension sentiment
    try:
        spx = yf.Ticker("^GSPC")
        spx_hist = spx.history(period="1y")
    except Exception:
        spx_hist = pd.DataFrame()
    t = yf.Ticker(ticker)
    sent_score, sent_d, sent_subs = compute_sentiment_6d(t, info, df, spx_hist)

    final, dims = _aggregate(wyckoff_score, vp_score, pa_score, sent_score, fund_score)

    verdict, direction, action = _verdict(final)

    if verbose:
        _print_report(ticker, df, info, wyckoff_phase, wyckoff_score, wyckoff_d,
                       vp_shape, vp_score, vp_d, pa_verdict, pa_score, pa_d,
                       sent_score, sent_d, fund_score, fund_d, final, verdict, direction, action, dims, sent_subs)

    return {
        "ticker": ticker,
        "date": datetime.now().isoformat(),
        "last_price": round(float(df["Close"].iloc[-1]), 2),
        "wyckoff": wyckoff_d | {"phase": wyckoff_phase, "score": round(wyckoff_score, 1)},
        "volume_profile": vp_d | {"shape": vp_shape, "score": round(vp_score, 1)},
        "price_action": pa_d | {"verdict": pa_verdict, "score": round(pa_score, 1)},
        "sentiment": sent_d | {"score": round(sent_score, 1)},
        "fundamentals": fund_d | {"score": round(fund_score, 1)},
        "final_score": round(final, 1),
        "verdict": verdict,
        "direction": direction,
        "action": action,
    }


def _fetch(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        df = t.history(period="1y")
        return df, info
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None, {}


def _compute_ma(df):
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    return df


def _rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=n - 1, adjust=True, min_periods=n).mean()
    ma_down = down.ewm(com=n - 1, adjust=True, min_periods=n).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))


def _wyckoff(df):
    c = df["Close"]
    hi = df["High"]
    lo = df["Low"]
    v = df["Volume"]
    latest = df.iloc[-1]
    avg = df.tail(60)
    r_lo, r_hi = avg["Low"].min(), avg["High"].max()
    r_pct = (latest["Close"] - r_lo) / (r_hi - r_lo) * 100 if r_hi > r_lo else 50

    last30 = df.tail(30)
    hh = last30["High"].diff().gt(0).sum() > 15
    hl = last30["Low"].diff().gt(0).sum() > 15
    lh = last30["High"].diff().lt(0).sum() > 15
    ll = last30["Low"].diff().lt(0).sum() > 15

    spring = False
    for i in range(-10, -1):
        if df.iloc[i]["Low"] < r_lo and df.iloc[i+1]["Close"] > df.iloc[i]["Close"]:
            spring = True; break

    upthrust = False
    for i in range(-10, -1):
        if df.iloc[i]["High"] > r_hi and df.iloc[i+1]["Close"] < df.iloc[i]["Close"]:
            upthrust = True; break

    vol_60 = v.tail(60).mean()
    vol_20 = v.tail(20).mean()
    contracting = vol_20 < vol_60 * 0.8 if vol_60 else False

    sos = sum(1 for i in range(-20, 0) if v.iloc[i] > v.tail(20).mean() * 1.5 and df.iloc[i]["Close"] > df.iloc[i]["Open"])
    sow = sum(1 for i in range(-20, 0) if v.iloc[i] > v.tail(20).mean() * 1.5 and df.iloc[i]["Close"] < df.iloc[i]["Open"])

    if spring and sos >= sow:
        phase = "Phase C-D — Spring / Initial Effect"
        score = 82
    elif spring:
        phase = "Phase C — Spring"
        score = 78
    elif hh and hl and r_pct > 80 and sos >= sow:
        phase = "Phase D-E — Markup"
        score = 75
    elif upthrust:
        phase = "Phase C — Upthrust (Bearish)"
        score = 25
    elif contracting and sos >= sow:
        phase = "Phase B — Cause Building (Accumulation)"
        score = 60
    elif sos > sow:
        phase = "Phase D — SOS Bias (Accumulation)"
        score = 65
    elif sow > sos:
        phase = "Phase D — SOW Bias (Distribution)"
        score = 35
    elif hh and hl:
        phase = "Phase D — Early Markup"
        score = 70
    else:
        phase = "Phase A-B — Range / Cause Building"
        score = 50

    details = {
        "range_position_pct": round(r_pct, 1),
        "hh_hl_markup": hh and hl,
        "lh_ll_markdown": lh and ll,
        "spring_detected": spring,
        "upthrust_detected": upthrust,
        "volume_ratio_20v60": round(float(vol_20 / vol_60) * 100, 1) if vol_60 else 0,
        "sos_bars": sos,
        "sow_bars": sow,
    }
    return phase, score, details


def _volume_profile(df):
    vp = df.tail(63)
    if vp.empty:
        return "No Data", 50, {}

    pmin, pmax = vp["Low"].min(), vp["High"].max()
    bins, bw = 20, (pmax - pmin) / 20 if pmax > pmin else 1
    profile = {}
    for i in range(bins):
        lb, hb = pmin + i * bw, pmin + (i + 1) * bw
        mask = (vp["Close"] >= lb) & (vp["Close"] < hb)
        key = f"{lb:.2f}-{hb:.2f}"
        profile[key] = {"volume": float(vp.loc[mask, "Volume"].sum()), "count": int(mask.sum())}

    poc_bin = max(profile, key=lambda k: profile[k]["volume"])
    poc = sum(float(x) for x in poc_bin.split("-")) / 2

    total_vol = vp["Volume"].sum()
    sorted_bins = sorted(profile.items(), key=lambda x: x[1]["volume"], reverse=True)
    cum, va_keys = 0, []
    for kk, vv in sorted_bins:
        cum += vv["volume"]; va_keys.append(kk)
        if cum / total_vol >= 0.7: break
    va_prices = [float(x) for k in va_keys for x in k.split("-")]
    val, vah = min(va_prices), max(va_prices)

    close_vp = vp["Close"].iloc[-1]
    curr_vol = vp["Volume"].iloc[-1]
    avg_vol = vp["Volume"].tail(20).mean()

    top_count = sorted_bins[0][1]["count"]
    total_bars = len(vp)
    if top_count > total_bars * 0.25:
        shape, s_score = "D-Profile (Balanced)", 30
    elif close_vp > poc and curr_vol > avg_vol * 1.2:
        shape, s_score = "P-Profile (Bullish)", 50
    elif close_vp < poc and curr_vol > avg_vol * 1.2:
        shape, s_score = "b-Profile (Bearish)", -30
    else:
        trend = "up" if close_vp > vp["Close"].iloc[0] else "down"
        shape, s_score = f"Thin Profile (Trending {trend})", 20 if trend == "up" else -20

    vpoc_score = 20 if close_vp > poc else (-20 if close_vp < poc else 0)
    va_score = -15 if close_vp > vah else (-15 if close_vp < val else 0)
    total = s_score + vpoc_score + va_score
    norm = max(0, min(100, 50 + total))

    details = {
        "shape": shape,
        "poc_price": round(poc, 2),
        "val": round(val, 2),
        "vah": round(vah, 2),
        "price_vs_poc": "Bullish ▲" if close_vp > poc else "Bearish ▼",
        "price_vs_va": f"Extended above VAH (${vah:.2f})" if close_vp > vah else (f"Below VAL (${val:.2f})" if close_vp < val else "Inside VA"),
        "last_close": round(close_vp, 2),
        "raw_score": norm,
    }
    return shape, norm, details


def _price_action(df):
    v20 = df.tail(20)
    c, v = v20["Close"], v20["Volume"]
    a20 = v.mean()
    a_range = (c.max() - c.min()) / 20

    val_bull = sum(1 for i in range(-10, 0)
                   if df.iloc[i]["Close"] > df.iloc[i]["Open"] and df.iloc[i]["Volume"] > a20 * 1.3)
    val_bear = sum(1 for i in range(-10, 0)
                   if df.iloc[i]["Close"] < df.iloc[i]["Open"] and df.iloc[i]["Volume"] > a20 * 1.3)
    rev = sum(1 for i in range(-9, 0)
              if (df.iloc[i]["Close"] > df.iloc[i-1]["Close"] and df.iloc[i-1]["Close"] < df.iloc[i-1]["Open"])
              or (df.iloc[i]["Close"] < df.iloc[i-1]["Close"] and df.iloc[i-1]["Close"] > df.iloc[i-1]["Open"]))
    vpa = (val_bull - val_bear) * 5 + (rev * 10 if rev > 2 else 0)

    er = 0
    for i in range(-5, 0):
        br = df.iloc[i]["High"] - df.iloc[i]["Low"]
        wr, nr = br > a_range * 1.2, br < a_range * 0.8
        hv = df.iloc[i]["Volume"] > a20 * 1.3
        lv = df.iloc[i]["Volume"] < a20 * 0.7
        er += 5 if (wr and hv) else (-5 if (nr and hv) else (-10 if (wr and lv) else 0))

    ema25 = c.ewm(span=25).mean()
    ema_up = ema25.iloc[-1] > ema25.iloc[-5]
    ema_s = 15 if ema_up else -15

    recent_r = v20["High"].max() - v20["Low"].min()
    tight = (v20["High"] - v20["Low"]).tail(5).mean() < recent_r * 0.15 if recent_r > 0 else False
    bld = 30 if tight else 0

    ws = 0
    for i in range(-15, -2):
        bar, nxt = df.iloc[i], df.iloc[i+1]
        prev = df.iloc[i-1]
        if bar["Low"] < prev["Low"] and nxt["Close"] > nxt["Open"]:
            ws += 20; break

    pa_raw = (vpa + er + ema_s + bld + ws) / 4
    pa_norm = max(0, min(100, 50 + pa_raw))
    pa_v = "Bullish" if pa_norm > 60 else ("Neutral" if pa_norm >= 40 else "Bearish")

    details = {
        "vpa_bullish": val_bull, "vpa_bearish": val_bear, "vpa_reversal": rev,
        "vpa_score": vpa, "er_score": er,
        "ema25_slope_up": bool(ema_up), "buildup": tight,
        "weis_score": ws, "score": round(pa_norm, 1),
    }
    return pa_v, pa_norm, details


def _sentiment(info, ticker):
    score = 50
    sr = info.get("shortRatio") or info.get("shortPercentOfFloat")
    inst = info.get("heldPercentInstitutions")
    if sr is not None:
        if sr > 3: score += 30
        elif sr < 1: score -= 10
    if inst is not None:
        if inst > 0.7: score += 15
        elif inst < 0.3: score -= 10
    details = {"short_ratio": sr, "institutional_ownership": round(inst * 100, 1) if inst else None}
    return max(0, min(100, score)), details


def _fundamentals(info, ticker):
    score = 50; reasons = []
    pe = info.get("trailingPE")
    if pe is not None:
        if pe < 10: score += 30; reasons.append(f"P/E {pe:.1f} (deep value)")
        elif pe < 15: score += 20; reasons.append(f"P/E {pe:.1f} (value)")
        elif pe < 25: score += 10; reasons.append(f"P/E {pe:.1f} (fair)")
        elif pe > 40: score -= 20; reasons.append(f"P/E {pe:.1f} (expensive)")

    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None and rev_growth > 0:
        score += 15; reasons.append(f"Revenue growth +{rev_growth*100:.0f}%")
    elif rev_growth is not None:
        score -= 15

    inst = info.get("heldPercentInstitutions")
    if inst is not None and inst > 0.5:
        score += 10

    margins = info.get("profitMargins")
    if margins is not None:
        if margins > 0.15: score += 15; reasons.append(f"Margins {margins*100:.0f}%")
        elif margins < 0: score -= 15

    dte = info.get("debtToEquity")
    if dte is not None:
        if dte > 300: score -= 10
        elif dte < 50: score += 10

    fcf = info.get("freeCashflow")
    if fcf is not None and fcf > 0: score += 10

    details = {
        "pe_ratio": pe, "revenue_growth_pct": round(rev_growth*100, 1) if rev_growth else None,
        "institutional_ownership": round(inst*100, 1) if inst else None,
        "profit_margins_pct": round(margins*100, 1) if margins else None,
        "debt_to_equity": dte, "free_cashflow": fcf,
        "reasons": reasons, "score": round(score),
    }
    return max(0, min(100, score)), details


def _aggregate(w, vp, pa, s, f):
    weights = {"wyckoff": 0.25, "volprof": 0.20, "pa": 0.20, "sentiment": 0.15, "fundamentals": 0.20}
    dims = {"Wyckoff": (w, weights["wyckoff"]), "Volume Profile": (vp, weights["volprof"]),
            "Price Action": (pa, weights["pa"]), "Sentiment": (s, weights["sentiment"]),
            "Fundamentals": (f, weights["fundamentals"])}
    final = sum(sc * w for sc, w in dims.values())
    return final, dims


def _verdict(score):
    if score >= 70: return "LONG-TERM INVESTMENT", "Long", "Entry DCA o singolo, PT 6-12 mesi"
    if score >= 50: return "SHORT-TERM SPECULATION (Bullish)", "Long", "Entry tattico, PT 1-4 settimane, stop stretto"
    if score >= 30: return "SHORT-TERM SPECULATION (Neutrale)", "Neutrale", "Solo setup perfetto"
    return "AVOID / WAIT", "N/A", "Nessuna azione"


def _print_report(ticker, df, info, wp, ws, wd, vs, vsc, vd, pv, ps, pd,
                  ss, sd, fs, fd, final, verdict, direction, action, dims, sent_subs=None):
    last = df.iloc[-1]
    rsi14 = _rsi(df["Close"]).iloc[-1]
    avg_vol = df["Volume"].tail(20).mean()
    c_ma50 = last["Close"] > last.get("MA50", 0) if "MA50" in df.columns else True
    c_ma200 = last["Close"] > last.get("MA200", 0) if "MA200" in df.columns else True

    heading(f"{ticker} — DATA")
    print(f"  Prezzo:    ${last['Close']:.2f}")
    print(f"  MA50:      ${df['MA50'].iloc[-1]:.2f}  {'▲' if c_ma50 else '▼'}" if 'MA50' in df.columns else "")
    print(f"  MA200:     ${df['MA200'].iloc[-1]:.2f}  {'▲' if c_ma200 else '▼'}" if 'MA200' in df.columns else "")
    print(f"  RSI(14):   {rsi14:.1f}")
    print(f"  Volume:    {avg_vol:,.0f}")
    print(f"  Name:      {info.get('longName', info.get('shortName', ticker))}")
    print(f"  Mkt Cap:   ${info.get('marketCap', 0):,}")
    print(f"  Settore:   {info.get('sector', 'N/A')} | {info.get('industry', '')}")

    heading("WYCKOFF")
    print(f"  Phase: {wp}")
    print(f"  Score: {ws:.0f}/100")
    print(f"  Range: {wd['range_position_pct']:.0f}% from low")
    print(f"  Spring: {'✅' if wd['spring_detected'] else '❌'} | Upthrust: {'✅' if wd['upthrust_detected'] else '❌'}")
    print(f"  SOS/SOW: {wd['sos_bars']}/{wd['sow_bars']} | Vol ratio: {wd['volume_ratio_20v60']}%")

    heading("VOLUME PROFILE")
    print(f"  Shape:  {vs}")
    print(f"  POC:    ${vd.get('poc_price', 'N/A')}")
    print(f"  VA:     ${vd.get('val', 'N/A')} — ${vd.get('vah', 'N/A')}")
    print(f"  Price:  {vd.get('price_vs_va', '')}")
    print(f"  Score:  {vsc:.0f}/100")

    heading("PRICE ACTION")
    print(f"  VPA:  Bull={pd['vpa_bullish']} Bear={pd['vpa_bearish']} Rev={pd['vpa_reversal']} → {pd['vpa_score']:+d}")
    print(f"  E/R:  {pd['er_score']:+d} | EMA25: {'▲' if pd['ema25_slope_up'] else '▼'} | Buildup: {'✅' if pd['buildup'] else '❌'}")
    print(f"  Weis: {pd['weis_score']:+d}")
    print(f"  Score: {ps:.0f}/100 ({pv})")

    heading("SENTIMENT (6-dimension)")
    print(f"  Score: {ss:.0f}/100")
    if sent_subs:
        labels = {"short_interest": "SI", "options": "Options", "insider": "Insider",
                   "retail": "Retail", "institutional": "Institutional", "momentum": "Momentum"}
        for k, label in labels.items():
            v = sent_subs.get(k)
            if v is not None:
                bar = "█" * (v // 10) + "░" * (10 - v // 10)
                print(f"  {label:<14} {bar} {v:>3}/100")

    heading("FUNDAMENTALS")
    print(f"  P/E: {fd.get('pe_ratio', 'N/A')}")
    print(f"  Revenue Growth: {fd.get('revenue_growth_pct', 'N/A')}%")
    print(f"  Margins: {fd.get('profit_margins_pct', 'N/A')}%")
    print(f"  D/E:   {fd.get('debt_to_equity', 'N/A')}")
    if fd.get("reasons"):
        for r in fd["reasons"]: print(f"    → {r}")
    print(f"  Score: {fs:.0f}/100")

    heading("SCORING")
    print(f"{'Dimensione':<20} {'Score':>6} {'Peso':>6} {'Contributo':>10}")
    print("-" * 45)
    for name, (sc, w) in dims.items():
        print(f"{name:<20} {sc:>6.0f} {w:>5.2f} {sc*w:>10.1f}")
    print("-" * 45)
    print(f"{'TOTALE':<20} {'':>6} {'1.00':>6} {final:>10.1f}")

    heading(f"VERDETTO: {verdict}")
    print(f"  Score:     {final:.1f}%")
    print(f"  Direzione: {direction}")
    print(f"  Azione:    {action}")


def main():
    parser = argparse.ArgumentParser(description="Deep dive stock analysis")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--save", "-s", action="store_true", help="Save JSON report")
    args = parser.parse_args()

    result = analyze(args.ticker)
    if args.save and "error" not in result:
        out_dir = Path("/home/giuseppe/Progetti/Github/opencode-skills/skills/market-accumulation-scanner/reports/us_large")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"deep_dive_{args.ticker.lower()}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Report salvato: {path}")


if __name__ == "__main__":
    main()
