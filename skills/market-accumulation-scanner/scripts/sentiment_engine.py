"""
Sentiment Engine — 9-Dimension Scoring Module
===============================================
Computes a 0-100 sentiment score from 9 independent sub-dimensions.
Designed to be called in parallel (each ticker independent).

Sub-dimensions:
  1. Short Interest (SI% + DTC from yfinance info, dynamic thresholds by market cap)
  2. Options Sentiment (Put/Call volume, IV skew from option_chain)
  3. Insider Trading (recent buy/sell transactions) [TODO: Phase 2 refinement]
  4. Retail Sentiment (WSB heuristic: volume, beta, analyst gap) [TODO: Phase 4]
  5. Institutional (holdings + buyback, institutional ownership from yfinance)
  6. Relative Momentum (vs SPY on 1mo/3mo/6mo via 20/50/200-day price data)
  7. Web News Sentiment (fallback chain: Finviz → Yahoo RSS → Google News RSS → MarketBeat → generic)
  8. Social Media Sentiment (WSB hotlist cross-reference) [TODO: Phase 4]
  9. Earnings Quality (earnings surprise trend) [TODO: earnings surprise trend]

Output: (score: int, detail_str: str, sub_dimensions: dict with all 9 sub-scores)
"""

import logging
import re
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Weights for the 9 sub-dimensions
# ─────────────────────────────────────────────
WEIGHTS = {
    "short_interest": 0.12,
    "options_sentiment": 0.12,
    "insider_trading": 0.12,
    "retail_sentiment": 0.08,
    "institutional": 0.12,
    "momentum": 0.08,
    "web_news": 0.08,
    "social_media": 0.08,
    "earnings_quality": 0.20,
}


def compute_sentiment(
    ticker: yf.Ticker,
    info: dict,
    hist: pd.DataFrame,
    spx_hist: pd.DataFrame | None = None,
    wsb_hotlist: dict | None = None,
    fetch_news: bool = False,
) -> tuple[int, str, dict]:
    """
    Main entry point — runs all 9 sub-dimensions and aggregates with confidence weighting.

    Args:
        ticker: yfinance Ticker object (used for options chain, insider txns)
        info: yfinance Ticker.info dict
        hist: 1-year daily OHLCV DataFrame
        spx_hist: Optional SPY/SPX daily OHLCV for momentum comparison
        wsb_hotlist: Optional dict of {ticker: {hype_score, fomo_phase, sentiment}}
                      from wallstreetbets-pump-detect
        fetch_news: Whether to fetch Finviz news (slower, skip for large scans)

    Returns:
        (score: int 0-100, detail_str: str, sub_dimensions: dict)
    """
    scores: dict[str, int | None] = {}
    sub_details: dict[str, str] = {}

    scores["short_interest"], sub_details["short_interest"] = _short_interest(info)
    scores["options_sentiment"], sub_details["options_sentiment"] = _options_sentiment(ticker, info)
    scores["insider_trading"], sub_details["insider_trading"] = _insider_sentiment(ticker)
    scores["retail_sentiment"], sub_details["retail_sentiment"] = _retail_sentiment(info)
    scores["institutional"], sub_details["institutional"] = _institutional(info)
    scores["momentum"], sub_details["momentum"] = _momentum(hist, spx_hist)

    # Web News (fallback chain) + Social Media + Earnings Quality
    symbol = info.get("symbol", ticker.ticker if hasattr(ticker, "ticker") else "?")
    scores["web_news"], sub_details["web_news"] = _web_news_sentiment(symbol, fetch=fetch_news)
    scores["social_media"], sub_details["social_media"] = _social_media_sentiment(symbol, wsb_hotlist=wsb_hotlist)
    scores["earnings_quality"], sub_details["earnings_quality"] = _earnings_quality(info, hist)

    # Aggregate with confidence weighting
    available = {k: v for k, v in scores.items() if v is not None}
    if not available:
        return 50, "No sentiment data available", scores

    used_weight = sum(WEIGHTS[k] for k in available)
    weighted = sum(scores[k] * WEIGHTS[k] for k in available)
    final = round(weighted / used_weight) if used_weight > 0 else 50

    n_avail = len(available)
    if n_avail <= 2:
        confidence = "low"
    elif n_avail <= 4:
        confidence = "medium"
    else:
        confidence = "high"

    detail_parts = [sub_details[k] for k in sorted(available)]
    detail_str = f"[{confidence}] " + " | ".join(detail_parts)

    return min(100, max(0, final)), detail_str, scores


# ─────────────────────────────────────────────
# 1. Short Interest (dynamic thresholds)
# ─────────────────────────────────────────────
def _short_interest(info: dict) -> tuple[int | None, str]:
    si = info.get("shortPercentOfFloat")
    dtc = info.get("shortRatio")
    mcap = info.get("marketCap")

    if si is None and dtc is None:
        return None, "No SI data"

    score = 25  # base

    # Dynamic thresholds based on market cap
    if mcap is not None and mcap < 2e9:
        thr_high, thr_mod = 0.15, 0.08
    elif mcap is not None and mcap < 10e9:
        thr_high, thr_mod = 0.10, 0.05
    else:
        thr_high, thr_mod = 0.05, 0.03

    parts = []
    if si is not None:
        if si > thr_high:
            score += 35
            parts.append(f"SI {si*100:.1f}% > {thr_high*100:.0f}% (+35)")
        elif si > thr_mod:
            score += 20
            parts.append(f"SI {si*100:.1f}% > {thr_mod*100:.0f}% (+20)")
        else:
            parts.append(f"SI {si*100:.1f}% < {thr_mod*100:.0f}% (+0)")

    if dtc is not None:
        if dtc > 10:
            score += 25
            parts.append(f"DTC {dtc:.1f} > 10 (+25)")
        elif dtc > 5:
            score += 15
            parts.append(f"DTC {dtc:.1f} > 5 (+15)")
        elif dtc > 3:
            score += 10
            parts.append(f"DTC {dtc:.1f} > 3 (+10)")
        else:
            parts.append(f"DTC {dtc:.1f} (+0)")

    return min(score, 100), " | ".join(parts)


# ─────────────────────────────────────────────
# 2. Options Sentiment (Put/Call + IV Skew)
# ─────────────────────────────────────────────
def _options_sentiment(ticker: yf.Ticker, info: dict) -> tuple[int | None, str]:
    try:
        exps = ticker.options
        if not exps:
            return None, "No options"
    except Exception:
        return None, "No options"

    # Pick the nearest monthly expiry (> 7 DTE to avoid gamma distortions)
    today = datetime.now().date()
    target_expiry = None
    for e in exps:
        ed = datetime.strptime(e, "%Y-%m-%d").date()
        dte = (ed - today).days
        if 7 <= dte <= 60:
            target_expiry = e
            break

    if target_expiry is None:
        target_expiry = exps[0]

    try:
        chain = ticker.option_chain(target_expiry)
    except Exception:
        return None, "Options chain error"

    calls, puts = chain.calls, chain.puts
    if calls.empty or puts.empty:
        return None, "Empty chain"

    score = 50
    parts = []

    vol_c = calls["volume"].sum() if "volume" in calls.columns and calls["volume"].notna().any() else 0
    vol_p = puts["volume"].sum() if "volume" in puts.columns and puts["volume"].notna().any() else 0
    oi_c = calls["openInterest"].sum() if "openInterest" in calls.columns and calls["openInterest"].notna().any() else 0
    oi_p = puts["openInterest"].sum() if "openInterest" in puts.columns and puts["openInterest"].notna().any() else 0
    total_vol = vol_c + vol_p

    # Minimum volume filter: if total < 500 contracts, volume ratio is unreliable
    vol_reliable = total_vol >= 500

    if vol_reliable:
        pc_vol = vol_p / max(vol_c, 1)
        if pc_vol > 1.5:
            score -= 15
            parts.append(f"P/C vol {pc_vol:.2f} (excess puts) (-15)")
        elif pc_vol > 1.0:
            score -= 5
            parts.append(f"P/C vol {pc_vol:.2f} (mild bearish) (-5)")
        elif pc_vol < 0.5:
            score += 15
            parts.append(f"P/C vol {pc_vol:.2f} (calls dominate) (+15)")
        else:
            parts.append(f"P/C vol {pc_vol:.2f} (neutral) (+0)")
    else:
        parts.append(f"Vol {total_vol:.0f}<500 (reliable P/C via OI only)")

    # Open Interest ratio (reliable even at low volume)
    if oi_c > 0 and oi_p > 0:
        pc_oi = oi_p / oi_c
        if pc_oi > 1.8:
            score -= 15
            parts.append(f"P/C OI {pc_oi:.2f} (excess puts positioned) (-15)")
        elif pc_oi > 1.2:
            score -= 5
            parts.append(f"P/C OI {pc_oi:.2f} (mild put bias) (-5)")
        elif pc_oi < 0.5:
            score += 15
            parts.append(f"P/C OI {pc_oi:.2f} (calls dominate OI) (+15)")
        elif pc_oi < 0.8:
            score += 5
            parts.append(f"P/C OI {pc_oi:.2f} (mild call bias) (+5)")
        else:
            parts.append(f"P/C OI {pc_oi:.2f} (neutral) (+0)")

    # IV Skew: Put IV vs Call IV at ATM
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is not None:
        nearest = round(price / 5) * 5
        near_calls = calls[calls["strike"] == nearest]
        near_puts = puts[puts["strike"] == nearest]
        if not near_calls.empty and not near_puts.empty:
            call_iv = near_calls["impliedVolatility"].mean()
            put_iv = near_puts["impliedVolatility"].mean()
            if call_iv and put_iv and call_iv > 0:
                skew = put_iv / call_iv
                if skew > 1.3:
                    score += 20
                    parts.append(f"IV skew {skew:.2f} (put premium=contrarian bullish) (+20)")
                elif skew > 1.1:
                    score += 10
                    parts.append(f"IV skew {skew:.2f} (mild put premium) (+10)")
                elif skew < 0.8:
                    score -= 10
                    parts.append(f"IV skew {skew:.2f} (call premium=complacency) (-10)")
                else:
                    parts.append(f"IV skew {skew:.2f} (neutral) (+0)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# 3. Insider Trading
# ─────────────────────────────────────────────
def _insider_sentiment(ticker: yf.Ticker) -> tuple[int | None, str]:
    score = 50
    parts = []

    # Method 1: insider_purchases summary (most reliable)
    try:
        summary = ticker.insider_purchases
        if summary is not None and not summary.empty:
            col_label = [c for c in summary.columns if "Insider" in c or "insider" in c][0]

            def _find_val(lbl):
                row = summary[summary[col_label].astype(str).str.strip().str.lower() == lbl.lower()]
                if not row.empty:
                    return row.iloc[0]
                return None

            purch = _find_val("Purchases")
            sales = _find_val("Sales")
            net_row = _find_val("Net Shares Purchased (Sold)")

            buys_txns = int(purch["Trans"]) if purch is not None and pd.notna(purch.get("Trans")) else 0
            sells_txns = int(sales["Trans"]) if sales is not None and pd.notna(sales.get("Trans")) else 0

            if buys_txns > 0 or sells_txns > 0:
                if buys_txns > sells_txns * 2 and buys_txns >= 3:
                    score += 30
                    parts.append(f"Insider buys={buys_txns} sells={sells_txns} (bullish) (+30)")
                elif buys_txns > sells_txns:
                    score += 15
                    parts.append(f"Insider buys={buys_txns} sells={sells_txns} (mild bullish) (+15)")
                elif sells_txns > buys_txns * 2 and sells_txns >= 3:
                    score -= 25
                    parts.append(f"Insider buys={buys_txns} sells={sells_txns} (heavy selling) (-25)")
                elif buys_txns == sells_txns:
                    parts.append(f"Insider buys={buys_txns} sells={sells_txns} (neutral) (+0)")
                else:
                    parts.append(f"Insider buys={buys_txns} sells={sells_txns} (mixed) (+0)")

                if net_row is not None:
                    net_col = [c for c in summary.columns if "%" in c or "Net" in c or "net" in c]
                    for c in net_col:
                        if c != col_label:
                            val = net_row[c]
                            if pd.notna(val):
                                try:
                                    net_pct = float(val)
                                    if net_pct > 0.01:
                                        score += 10
                                        parts.append(f"Net +{net_pct*100:.1f}% (+10)")
                                    elif net_pct < -0.01:
                                        score -= 10
                                        parts.append(f"Net {net_pct*100:.1f}% (selling) (-10)")
                                except (ValueError, TypeError):
                                    pass
                            break

                return min(100, max(0, score)), " | ".join(parts)
    except Exception:
        pass

    # Method 2: fall back to insider_transactions raw data
    try:
        txns = ticker.insider_transactions
    except Exception:
        return None, "No insider data"

    if txns is None or txns.empty:
        return None, "No insider transactions"

    today = datetime.now().date()
    cutoff = today - timedelta(days=180)
    if "Date" in txns.columns:
        txns["Date"] = pd.to_datetime(txns["Date"], errors="coerce")
        recent = txns[txns["Date"].dt.date >= cutoff]
    else:
        recent = txns.tail(50)

    if recent.empty:
        return None, "No insider txns in 6mo"

    buys = 0
    sells = 0
    for _, row in recent.iterrows():
        ttype = str(row.get("Transaction", row.get("transaction", ""))).lower()
        shares_raw = row.get("Shares", row.get("shares", 0))
        try:
            shares = abs(float(shares_raw)) if shares_raw is not None else 0
        except (ValueError, TypeError):
            continue
        if shares < 100:
            continue
        if "purchase" in ttype or "buy" in ttype:
            buys += 1
        elif "sale" in ttype:
            sells += 1

    if buys == 0 and sells == 0:
        return None, "No classified insider txns"

    if buys > sells * 2:
        score += 25
        parts.append(f"Insider buys={buys} sells={sells} (bullish) (+25)")
    elif buys > sells:
        score += 10
        parts.append(f"Insider buys={buys} sells={sells} (mild bullish) (+10)")
    elif sells > buys * 2:
        score -= 20
        parts.append(f"Insider buys={buys} sells={sells} (bearish) (-20)")
    else:
        parts.append(f"Insider buys={buys} sells={sells} (mixed) (+0)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# 4. Retail / Social Sentiment (WSB heuristic)
# ─────────────────────────────────────────────
def _retail_sentiment(info: dict) -> tuple[int | None, str]:
    """
    Heuristic-based retail sentiment.
    High retail attention is contrarian bearish (dumb money piling in).
    Low retail attention + accumulation = contrarian bullish (undiscovered gem).
    """
    score = 50
    parts = []
    signals = []

    si = info.get("shortPercentOfFloat")
    avg_vol = info.get("averageVolume")
    curr_vol = info.get("volume")
    target_price = info.get("targetMeanPrice")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    beta = info.get("beta")

    # High SI attracts retail (WSB effect)
    if si is not None and si > 0.20:
        signals.append("extreme_si")
        score -= 15
        parts.append(f"SI {si*100:.0f}% > 20% (retail magnet) (-15)")
    elif si is not None and si > 0.12:
        signals.append("high_si")
        score -= 5
        parts.append(f"SI {si*100:.0f}% > 12% (retail attention) (-5)")

    # Volume spike = retail FOMO
    if avg_vol and curr_vol:
        vol_ratio = curr_vol / avg_vol
        if vol_ratio > 3:
            signals.append("extreme_vol")
            score -= 15
            parts.append(f"Vol {vol_ratio:.1f}x avg (extreme FOMO) (-15)")
        elif vol_ratio > 2:
            signals.append("high_vol")
            score -= 5
            parts.append(f"Vol {vol_ratio:.1f}x avg (retail FOMO) (-5)")
        elif vol_ratio < 0.5:
            signals.append("low_vol")
            score += 10
            parts.append(f"Vol {vol_ratio:.1f}x avg (quiet accumulation) (+10)")

    # High beta attracts speculative retail
    if beta is not None and beta > 1.5:
        signals.append("high_beta")
        score -= 5
        parts.append(f"Beta {beta:.1f} > 1.5 (speculative) (-5)")

    # Analyst target far above price = institutions still interested, not retail
    if price and target_price and target_price > price * 1.3:
        signals.append("analyst_gap")
        score += 10
        parts.append(f"Target ${target_price:.0f} > price ${price:.0f} (+10)")

    if not signals:
        parts.append("No retail signal (neutral)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# 5. Institutional (holdings + buyback)
# ─────────────────────────────────────────────
def _institutional(info: dict) -> tuple[int | None, str]:
    inst = info.get("heldPercentInstitutions")
    buyback = info.get("buybackYield")
    shares_out = info.get("sharesOutstanding")
    shares_short = info.get("sharesShort")

    if inst is None and buyback is None:
        return None, "No institutional data"

    score = 50
    parts = []

    if inst is not None:
        if inst > 0.8:
            score += 25
            parts.append(f"Inst {inst*100:.0f}% > 80% (+25)")
        elif inst > 0.6:
            score += 15
            parts.append(f"Inst {inst*100:.0f}% > 60% (+15)")
        elif inst > 0.4:
            score += 5
            parts.append(f"Inst {inst*100:.0f}% > 40% (+5)")
        else:
            parts.append(f"Inst {inst*100:.0f}% (+0)")

    if buyback is not None:
        if buyback > 0.05:
            score += 20
            parts.append(f"Buyback {buyback*100:.1f}% > 5% (+20)")
        elif buyback > 0.02:
            score += 10
            parts.append(f"Buyback {buyback*100:.1f}% > 2% (+10)")
        else:
            parts.append(f"Buyback {buyback*100:.1f}% (+0)")

    if shares_out and shares_short and shares_out > 0:
        short_pct_of_out = shares_short / shares_out
        if short_pct_of_out > 0.10:
            score += 10
            parts.append(f"Short/Out {short_pct_of_out*100:.1f}% > 10% (+10)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# 6. Relative Momentum (vs SPX/SPY)
# ─────────────────────────────────────────────
def _momentum(hist: pd.DataFrame, spx_hist: pd.DataFrame | None = None) -> tuple[int | None, str]:
    if hist.empty or len(hist) < 20:
        return None, "Insufficient price history"

    close = hist["Close"]

    # If SPX data provided, compute relative strength
    if spx_hist is not None and not spx_hist.empty and len(spx_hist) >= 20:
        spx_close = spx_hist["Close"]
        spx_aligned = spx_close.reindex(close.index, method="ffill")

        rel = close / spx_aligned
    else:
        # Fallback: absolute momentum
        rel = pd.Series(1.0, index=close.index)

    score = 50
    parts = []

    # 1-month relative return
    if len(rel) >= 21:
        r1 = rel.iloc[-1] / rel.iloc[-21] - 1
        if r1 > 0.05:
            score += 15
            parts.append(f"1mo rel +{r1*100:.1f}% > 5% (+15)")
        elif r1 > 0.02:
            score += 10
            parts.append(f"1mo rel +{r1*100:.1f}% > 2% (+10)")
        elif r1 < -0.05:
            score -= 10
            parts.append(f"1mo rel {r1*100:.1f}% < -5% (-10)")
        else:
            parts.append(f"1mo rel {r1*100:+.1f}% (+0)")

    # 3-month relative return
    if len(rel) >= 63:
        r3 = rel.iloc[-1] / rel.iloc[-63] - 1
        if r3 > 0.10:
            score += 15
            parts.append(f"3mo rel +{r3*100:.1f}% > 10% (+15)")
        elif r3 > 0.05:
            score += 10
            parts.append(f"3mo rel +{r3*100:.1f}% > 5% (+10)")
        elif r3 < -0.10:
            score -= 10
            parts.append(f"3mo rel {r3*100:.1f}% < -10% (-10)")
        else:
            parts.append(f"3mo rel {r3*100:+.1f}% (+0)")

    # 6-month relative return
    if len(rel) >= 126:
        r6 = rel.iloc[-1] / rel.iloc[-126] - 1
        if r6 > 0.15:
            score += 10
            parts.append(f"6mo rel +{r6*100:.1f}% > 15% (+10)")
        elif r6 < -0.15:
            score -= 10
            parts.append(f"6mo rel {r6*100:.1f}% < -15% (-10)")
        else:
            parts.append(f"6mo rel {r6*100:+.1f}% (+0)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# 7. Web News Sentiment (fallback chain)
# ─────────────────────────────────────────────

# Rate-limiting: track last request time per domain
_LAST_REQUEST: dict[str, float] = {}
_RATE_DELAY = 1.0  # seconds between requests to same domain


def _rate_limit(domain: str) -> None:
    """Enforce min delay between requests to the same domain."""
    now = time.time()
    last = _LAST_REQUEST.get(domain, 0)
    elapsed = now - last
    if elapsed < _RATE_DELAY:
        time.sleep(_RATE_DELAY - elapsed)
    _LAST_REQUEST[domain] = time.time()


# Shared keyword sets for headline polarity scoring
_BULLISH_KEYWORDS = {
    "upgrade", "buy", "bullish", "outperform", "beat", "raised", "positive",
    "growth", "strong", "record", "surge", "rally", "gain", "soar", "jump",
    "launch", "approve", "partner", "contract", "expansion", "dividend",
    "buyback", "profit", "revenue", "guidance", "momentum", "breakout",
    "accumulate", "overweight", "target", "up", "green", "optimistic",
    "leap", "boost", "accelerate", "innovation", "leadership",
}

_BEARISH_KEYWORDS = {
    "downgrade", "sell", "bearish", "underperform", "miss", "cut", "negative",
    "decline", "weak", "loss", "drop", "fall", "plunge", "crash", "slump",
    "lawsuit", "investigation", "SEC", "fine", "penalty", "regulation",
    "warning", "caution", "risk", "uncertainty", "volatile", "downturn",
    "recession", "layoff", "restructuring", "debt", "default", "bankruptcy",
    "investigation", "probe", "charge", "write-down", "impairment",
    "suspension", "delay", "setback", "disappoint", "below estimate",
}


def _score_headlines(headlines: list[str]) -> tuple[int, str]:
    """Score a list of headline strings by keyword polarity."""
    if not headlines:
        return 50, "No headlines found"

    bullish_count = 0
    bearish_count = 0

    for h in headlines:
        h_lower = h.lower()
        h_bullish = sum(1 for kw in _BULLISH_KEYWORDS if kw in h_lower)
        h_bearish = sum(1 for kw in _BEARISH_KEYWORDS if kw in h_lower)

        if h_bullish > h_bearish:
            bullish_count += 1
        elif h_bearish > h_bullish:
            bearish_count += 1

    net = bullish_count - bearish_count
    total = len(headlines)

    if total >= 4 and net >= 3:
        return 90, f"4+ bullish headlines ({bullish_count}B/{bearish_count}S/{total}T) (+40)"
    if net >= 2:
        return 70, f"Mostly bullish ({bullish_count}B/{bearish_count}S/{total}T) (+20)"
    if net >= 1:
        return 60, f"Slightly bullish ({bullish_count}B/{bearish_count}S/{total}T) (+10)"
    if net == 0 and total > 0:
        return 50, f"Neutral/mixed ({bullish_count}B/{bearish_count}S/{total}T) (+0)"
    if net <= -2:
        return 30, f"Mostly bearish ({bullish_count}B/{bearish_count}S/{total}T) (-20)"
    if net <= -1:
        return 40, f"Slightly bearish ({bullish_count}B/{bearish_count}S/{total}T) (-10)"

    return 50, f"No clear polarity ({bullish_count}B/{bearish_count}S/{total}T) (+0)"


def _fetch_finviz_headlines(symbol: str) -> list[str] | None:
    """Try Finviz as primary news source."""
    _rate_limit("finviz.com")
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log.warning("Finviz HTTP %s for %s", resp.status_code, symbol)
            return None
    except requests.RequestException as e:
        log.warning("Finviz error for %s: %s", symbol, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    headlines = []

    for a_tag in soup.find_all("a", class_=re.compile(r"tab-link-news", re.I)):
        text = a_tag.get_text(strip=True)
        if text and len(text) > 10:
            headlines.append(text)
        if len(headlines) >= 10:
            break

    if not headlines:
        news_div = soup.find("div", id=re.compile(r"news", re.I))
        if not news_div:
            news_div = soup.find("div", class_=re.compile(r"fullview-news", re.I))
        if news_div:
            for a_tag in news_div.find_all("a", href=True):
                text = a_tag.get_text(strip=True)
                if text and len(text) > 10:
                    headlines.append(text)
                if len(headlines) >= 10:
                    break

    return headlines if headlines else None


def _fetch_yahoo_rss_headlines(symbol: str) -> list[str] | None:
    """Try Yahoo Finance RSS as fallback source #2."""
    _rate_limit("finance.yahoo.com")
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log.warning("Yahoo RSS HTTP %s for %s", resp.status_code, symbol)
            return None
    except requests.RequestException as e:
        log.warning("Yahoo RSS error for %s: %s", symbol, e)
        return None

    soup = BeautifulSoup(resp.text, "xml")
    headlines = []
    for item in soup.find_all("item")[:10]:
        title_tag = item.find("title")
        if title_tag:
            text = title_tag.get_text(strip=True)
            if text and len(text) > 10:
                headlines.append(text)

    return headlines if headlines else None


def _fetch_google_news_rss_headlines(symbol: str) -> list[str] | None:
    """Try Google News RSS as fallback source #3."""
    _rate_limit("news.google.com")
    url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log.warning("Google News RSS HTTP %s for %s", resp.status_code, symbol)
            return None
    except requests.RequestException as e:
        log.warning("Google News RSS error for %s: %s", symbol, e)
        return None

    soup = BeautifulSoup(resp.text, "xml")
    headlines = []
    for item in soup.find_all("item")[:10]:
        title_tag = item.find("title")
        if title_tag:
            text = title_tag.get_text(strip=True)
            if text and len(text) > 10:
                # Strip " - SourceName" suffix typical in Google News
                text = text.rsplit(" - ", 1)[0]
                headlines.append(text)

    return headlines if headlines else None


def _fetch_marketbeat_headlines(symbol: str) -> list[str] | None:
    """Try MarketBeat headlines as fallback source #4."""
    _rate_limit("www.marketbeat.com")
    symbol_upper = symbol.upper().replace(".MI", "").replace(".DE", "").replace(".PA", "")
    url = f"https://www.marketbeat.com/stocks/NYSE/{symbol_upper}/headlines/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log.warning("MarketBeat HTTP %s for %s", resp.status_code, symbol)
            return None
    except requests.RequestException as e:
        log.warning("MarketBeat error for %s: %s", symbol, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    headlines = []

    for a_tag in soup.find_all("a", href=True):
        text = a_tag.get_text(strip=True)
        if text and len(text) > 15 and not text.startswith("http"):
            # Filter out navigation links (short text, nav elements)
            parent = a_tag.parent
            if parent and parent.name in ("h2", "h3", "h4", "li", "div"):
                headlines.append(text)
        if len(headlines) >= 10:
            break

    return headlines if headlines else None


def _web_news_sentiment(symbol: str, fetch: bool = False) -> tuple[int | None, str]:
    """
    Fetch headlines via fallback chain and score polarity.

    Fallback order:
      1. Finviz (primary)
      2. Yahoo Finance RSS
      3. Google News RSS
      4. MarketBeat headlines
      5. Generic websearch stub

    Args:
        symbol: Ticker symbol (e.g. "AAPL")
        fetch: If False, skip all API calls and return None/neutral

    Returns:
        (score 0-100, detail string)
    """
    if not fetch:
        return None, "Web news skipped (fetch_news=False)"

    sources = [
        ("Finviz", _fetch_finviz_headlines),
        ("Yahoo RSS", _fetch_yahoo_rss_headlines),
        ("Google News RSS", _fetch_google_news_rss_headlines),
        ("MarketBeat", _fetch_marketbeat_headlines),
    ]

    for src_name, fetcher in sources:
        try:
            headlines = fetcher(symbol)
            if headlines:
                score, detail = _score_headlines(headlines)
                detail = f"[{src_name}] {detail}"
                return min(100, max(0, score)), detail
        except Exception as e:
            log.warning("%s failed for %s: %s", src_name, symbol, e)
            continue

    # Fallback #5: generic websearch stub
    print(f"websearch {symbol} stock news")
    return 50, "All sources exhausted; websearch stub (neutral 50)"


# ─────────────────────────────────────────────
# 8. Social Media Sentiment (WSB hotlist)
# ─────────────────────────────────────────────
def _social_media_sentiment(symbol: str, wsb_hotlist: dict | None = None) -> tuple[int | None, str]:
    """
    Cross-reference the ticker against the WSB hotlist from wallstreetbets-pump-detect.

    Args:
        symbol: Ticker symbol
        wsb_hotlist: dict of {ticker: {hype_score, fomo_phase, sentiment, mention_count}}
                      or {"ticker": hype_score} for simplified format

    Returns:
        (score 0-100, detail string)
    """
    if not wsb_hotlist:
        return None, "No WSB hotlist provided"

    # Normalise symbol
    sym_upper = symbol.upper().replace(".MI", "").replace(".DE", "").replace(".PA", "").replace(".L", "").replace(".MC", "")

    entry = wsb_hotlist.get(sym_upper) or wsb_hotlist.get(symbol.upper())
    if entry is None:
        return 50, "Not on WSB radar (neutral)"

    # Support both simplified (int) and detailed (dict) formats
    if isinstance(entry, dict):
        hype_score = entry.get("hype_score", 50)
        fomo_phase = entry.get("fomo_phase", "mid")
        wsb_sentiment = entry.get("sentiment", 50)
        mention_count = entry.get("mention_count", 0)
    else:
        # Assume entry is a hype score directly
        hype_score = int(entry) if entry else 50
        fomo_phase = "mid"
        wsb_sentiment = 50
        mention_count = 0

    score = 50

    # WSB phase scoring
    phase = str(fomo_phase).lower()
    if phase in ("early", "pre-pump"):
        score += 20
        phase_tag = "Early FOMO"
    elif phase == "mid":
        score += 10
        phase_tag = "Mid FOMO"
    elif phase in ("late", "exit"):
        score -= 20
        phase_tag = "Late FOMO (caution)"
    else:
        phase_tag = f"FOMO {fomo_phase}"

    # Hype magnitude
    if hype_score >= 70:
        score += 15
        hype_tag = "high hype"
    elif hype_score >= 40:
        score += 5
        hype_tag = "moderate hype"
    else:
        hype_tag = "low hype"
        score -= 5

    # WSB sentiment direction
    if wsb_sentiment >= 65:
        score += 10
        sent_tag = "bullish"
    elif wsb_sentiment <= 45:
        score -= 5
        sent_tag = "bearish"
    else:
        sent_tag = "neutral"

    # Mention volume adjustment
    if mention_count > 20:
        score -= 5  # saturated
    elif mention_count > 5:
        score += 5  # growing interest
    elif mention_count > 0:
        score += 10  # undiscovered

    score = min(100, max(0, score))
    detail = (
        f"WSB {phase_tag} hype={hype_score} ({hype_tag}), "
        f"sentiment={sent_tag}, mentions={mention_count} → score {score}"
    )

    return score, detail


# ─────────────────────────────────────────────
# 9. Earnings Quality Trend (Sloan 1996)
# ─────────────────────────────────────────────
def _earnings_quality(info: dict, hist: pd.DataFrame) -> tuple[int | None, str]:
    """
    Earnings Quality Modifier at sentiment level.
    Proxy: earningsGrowth (YoY), revenueGrowth, margin trend from hist P&L.

    Backtest: Sloan (1996) — earnings quality predicts returns with p<0.01.
    High accruals (low quality) → underperformance next 12mo.
    """
    earnings_growth = info.get("earningsGrowth")
    rev_growth = info.get("revenueGrowth")
    margins = info.get("profitMargins")
    fcf = info.get("freeCashflow")
    op_cf = info.get("operatingCashFlow")
    net_income = info.get("netIncomeToCommon")

    if earnings_growth is None and rev_growth is None:
        return None, "No earnings quality data"

    score = 50
    parts = []

    # Earnings trend (strongest signal)
    if earnings_growth is not None:
        if earnings_growth > 0.20:
            score += 25
            parts.append(f"EPS growth {earnings_growth*100:.0f}% > 20% (+25)")
        elif earnings_growth > 0.10:
            score += 15
            parts.append(f"EPS growth {earnings_growth*100:.0f}% > 10% (+15)")
        elif earnings_growth > 0:
            score += 5
            parts.append(f"EPS growth {earnings_growth*100:.0f}% (+) (+5)")
        elif earnings_growth < -0.10:
            score -= 20
            parts.append(f"EPS growth {earnings_growth*100:.0f}% (declining -20)")
        elif earnings_growth < 0:
            score -= 10
            parts.append(f"EPS growth {earnings_growth*100:.0f}% (slight decline -10)")

    # Revenue quality: growth with profit = real quality
    if rev_growth is not None and margins is not None:
        if rev_growth > 0.05 and margins > 0.10:
            score += 15
            parts.append(f"Revenue +{rev_growth*100:.0f}% + margins {margins*100:.0f}% (quality +15)")
        elif rev_growth > 0 and margins > 0:
            score += 5
            parts.append(f"Revenue +{rev_growth*100:.0f}% + positive margins (+5)")
        elif rev_growth > 0.10 and (margins < 0 or margins is None):
            score -= 10
            parts.append(f"Revenue growing but no margins (low quality -10)")

    # Cash flow vs earnings (accrual proxy)
    if op_cf is not None and net_income is not None and net_income > 0:
        accrual_ratio = 1 - (op_cf / net_income)
        if accrual_ratio < 0.3:
            score += 10
            parts.append(f"Low accruals (opCF/netIncome = {1-accrual_ratio:.2f}) (+10)")
        elif accrual_ratio > 0.7:
            score -= 15
            parts.append(f"High accruals (opCF/netIncome = {1-accrual_ratio:.2f}) (-15)")

    # Free cash flow positive = earnings quality
    if fcf is not None and fcf > 0:
        score += 10
        parts.append(f"FCF positive (+10)")

    return min(100, max(0, score)), " | ".join(parts)


# ─────────────────────────────────────────────
# Earnings Proximity Adjustment (Phase 3.4)
# ─────────────────────────────────────────────
def earnings_proximity_adjustment(
    ticker: str,
    days_to_earnings: int | None,
    iv_rank: float | None,
) -> dict:
    """
    Adjust option strategy selection based on earnings proximity and IV regime.

    Args:
        ticker: Ticker symbol
        days_to_earnings: Days until next earnings report (None if unknown)
        iv_rank: Implied volatility rank 0-100 (None if unknown)

    Returns:
        dict with:
          - strategy_modifier: str describing how to adjust strategy selection
          - rules: list[str] of specific rules triggered
    """
    if days_to_earnings is None:
        return {
            "strategy_modifier": "No earnings data; use default strategy selection",
            "rules": [],
        }

    rules = []
    modifier = ""

    if days_to_earnings < 7:
        if iv_rank is not None and iv_rank > 80:
            modifier = "Earnings imminent (<7d) with very high IV. SELL PREMIUM."
            rules.append("Sell premium (IV crush post-earnings expected)")
        elif iv_rank is not None and iv_rank < 30:
            modifier = "Earnings imminent (<7d) with low IV. BUY PREMIUM."
            rules.append("Buy premium (cheap vol, capture earnings move)")
        elif iv_rank is not None and 30 <= iv_rank <= 80:
            modifier = "Earnings imminent (<7d) with moderate IV. AVOID OPTIONS."
            rules.append("Avoid options; use underlying")
        else:
            modifier = "Earnings imminent (<7d). IV unknown; AVOID OPTIONS."
            rules.append("Avoid options; use underlying")
    elif 7 <= days_to_earnings <= 21:
        modifier = "Earnings within 3 weeks. PREFER DIRECTIONAL STRATEGIES."
        rules.append(
            "Avoid iron condors/butterflies; "
            "prefer covered calls or cash-secured puts"
        )
    elif days_to_earnings > 21:
        modifier = "Earnings distant. NO RESTRICTIONS."
        rules.append("No restriction; exit before earnings if profitable")

    return {
        "strategy_modifier": modifier,
        "rules": rules,
    }


# ─────────────────────────────────────────────
# Standalone usage
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python sentiment_engine.py <TICKER> [--news] [--wsb hotlist.json]")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    fetch_news_flag = "--news" in sys.argv

    # Optional WSB hotlist file
    wsb_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--wsb" and i + 1 < len(sys.argv):
            wsb_path = sys.argv[i + 1]
            break

    wsb_hotlist = None
    if wsb_path:
        try:
            with open(wsb_path, "r") as f:
                wsb_hotlist = json.load(f)
            print(f"Loaded WSB hotlist from {wsb_path} ({len(wsb_hotlist)} tickers)")
        except Exception as e:
            print(f"Error loading WSB hotlist: {e}")

    print(f"\nComputing 9-dimension sentiment for {symbol}...\n")

    t = yf.Ticker(symbol)
    info = t.info or {}

    try:
        spx = yf.Ticker("^GSPC")
        spx_hist = spx.history(period="1y")
    except Exception:
        spx_hist = None

    hist = t.history(period="1y")

    score, detail, subs = compute_sentiment(
        t, info, hist, spx_hist,
        wsb_hotlist=wsb_hotlist,
        fetch_news=fetch_news_flag,
    )

    print(f"Final Score: {score}/100")
    print(f"Detail:      {detail}")
    print()
    print("Sub-dimensions:")
    for k, v in subs.items():
        w = WEIGHTS.get(k, 0)
        status = f"{v}/100" if v is not None else "N/A"
        print(f"  {k:20s} {status:>8}  (weight {w:.0%})")
