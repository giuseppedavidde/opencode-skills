#!/usr/bin/env python3
"""Generate Synthetic Long 2:1 strategy PDF report for any ticker.

Usage:
    python3 gen_report.py --ticker IGV --expiry 2026-12-18
    python3 gen_report.py --ticker HPQ --expiry 2026-12-18 --put-strike 25 --call-strike 30
    python3 gen_report.py --ticker AAPL --expiry 2026-12-18 --auto-strikes

Fetches live data via yfinance, auto-generates thesis text, computes Greeks,
and produces a professional PDF report.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from fpdf import FPDF

FONT_DIR = '/usr/share/fonts/TTF/'
FD = FONT_DIR + 'DejaVuSans.ttf'
FB = FONT_DIR + 'DejaVuSans-Bold.ttf'
FO = FONT_DIR + 'DejaVuSans-Oblique.ttf'
FM = FONT_DIR + 'DejaVuSansMono.ttf'
FMB = FONT_DIR + 'DejaVuSansMono-Bold.ttf'

R = 0.0425

# ── Sector color map ──
SECTOR_COLORS = {
    'Technology': (25, 60, 150),
    'Financial Services': (0, 100, 50),
    'Healthcare': (20, 110, 110),
    'Energy': (180, 90, 20),
    'Consumer Cyclical': (120, 40, 120),
    'Consumer Defensive': (0, 80, 60),
    'Communication Services': (40, 70, 160),
    'Industrials': (60, 60, 60),
    'Basic Materials': (100, 80, 30),
    'Real Estate': (70, 50, 90),
    'Utilities': (30, 70, 80),
    'ETF': (0, 100, 50),
}

DEFAULT_COLOR = (50, 50, 50)


def get_sector_color(info: dict) -> tuple:
    sector = info.get('sector') or info.get('category') or ''
    if info.get('quoteType') == 'ETF' or 'ETF' in sector:
        return SECTOR_COLORS['ETF']
    return SECTOR_COLORS.get(sector, DEFAULT_COLOR)


# ── Math helpers ──
def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def bs_greeks(S: float, K: float, T_: float, r: float, sigma: float, opt_type: str = 'c'):
    if sigma <= 0 or T_ <= 0:
        sigma = 0.50
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T_) / (sigma * math.sqrt(T_))
    d2 = d1 - sigma * math.sqrt(T_)
    N, n = norm_cdf, norm_pdf
    if opt_type == 'c':
        delta = N(d1)
        gamma = n(d1) / (S * sigma * math.sqrt(T_))
        theta = (-S * sigma * n(d1) / (2 * math.sqrt(T_))
                 - r * K * math.exp(-r * T_) * N(d2)) / 365
        vega = S * n(d1) * math.sqrt(T_) / 100
        prob = N(d2)
        price = S * N(d1) - K * math.exp(-r * T_) * N(d2)
    else:
        delta = N(d1) - 1
        gamma = n(d1) / (S * sigma * math.sqrt(T_))
        theta = (-S * sigma * n(d1) / (2 * math.sqrt(T_))
                 + r * K * math.exp(-r * T_) * N(-d2)) / 365
        vega = S * n(d1) * math.sqrt(T_) / 100
        prob = N(-d2)
        price = K * math.exp(-r * T_) * N(-d2) - S * N(-d1)
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega,
            'prob': prob, 'price': price}


# ── Data fetch ──
def fetch_news(ticker: str, max_headlines: int = 10) -> list[dict]:
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        anchors = []
        for a_tag in soup.find_all("a", class_=re.compile(r"tab-link-news", re.I)):
            text = a_tag.get_text(strip=True)
            if text and len(text) > 15:
                anchors.append(text)
            if len(anchors) >= max_headlines:
                break
        if not anchors:
            news_div = soup.find("div", class_=re.compile(r"fullview-news", re.I))
            if news_div:
                for a_tag in news_div.find_all("a", href=True):
                    text = a_tag.get_text(strip=True)
                    if text and len(text) > 15:
                        anchors.append(text)
                    if len(anchors) >= max_headlines:
                        break
        bullish_kw = {"upgrade", "buy", "bullish", "beat", "raised", "positive",
                       "growth", "strong", "record", "surge", "rally", "gain",
                       "launch", "profit", "revenue", "momentum"}
        bearish_kw = {"downgrade", "sell", "bearish", "miss", "cut", "negative",
                       "decline", "weak", "loss", "drop", "fall", "plunge", "crash",
                       "slump", "lawsuit", "investigation", "layoff", "debt"}
        for h in anchors:
            hl = h.lower()
            b = sum(1 for kw in bullish_kw if kw in hl)
            s = sum(1 for kw in bearish_kw if kw in hl)
            sentiment = 'bullish' if b > s else 'bearish' if s > b else 'neutral'
            results.append({'text': h[:120], 'sentiment': sentiment})
    except Exception:
        pass
    return results


WSB_CACHE: dict | None = None

def fetch_wsb_mentions(ticker: str) -> dict | None:
    """Scrape r/wallstreetbets for ticker mentions. Uses cache."""
    global WSB_CACHE
    if WSB_CACHE is None:
        WSB_CACHE = {}
        ttl_texts = []
        blocked = False

        # Try JSON endpoint
        try:
            resp = requests.get(
                'https://www.reddit.com/r/wallstreetbets/hot.json?limit=100',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                for post in data.get('data', {}).get('children', []):
                    p = post.get('data', {})
                    ttl_texts.append((p.get('title', ''), p.get('ups', 0)))
            elif resp.status_code == 403:
                blocked = True
        except Exception:
            pass

        # Fallback: old.reddit HTML
        if not ttl_texts and not blocked:
            try:
                resp = requests.get(
                    'https://old.reddit.com/r/wallstreetbets/hot/',
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=10
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for a_tag in soup.find_all('a', class_='title'):
                        text = a_tag.text.strip()
                        if text:
                            ttl_texts.append((text, 0))
                elif resp.status_code == 403:
                    blocked = True
            except Exception:
                pass

        WSB_CACHE['_posts'] = ttl_texts
        WSB_CACHE['_blocked'] = blocked

    posts = WSB_CACHE.get('_posts', [])
    blocked = WSB_CACHE.get('_blocked', False)

    if blocked and not posts:
        return {'error': 'rate_limited', 'mentions': 0, 'intensity': 'unknown'}

    if not posts:
        return None

    t_upper = ticker.upper()
    mentions = 0
    total_ups = 0
    found_posts = []
    for title, ups in posts:
        clean_words = set(w.upper().strip('$!?.,;:()[]{}') for w in title.split())
        if t_upper in clean_words or f'${t_upper}' in title.upper():
            mentions += 1
            total_ups += ups
            found_posts.append((title[:80], ups))

    if mentions == 0:
        return None

    avg_ups = total_ups / mentions if mentions > 0 else 0
    intensity = 'high' if mentions >= 5 or avg_ups > 500 else 'medium' if mentions >= 2 else 'low'
    return {
        'mentions': mentions,
        'total_ups': total_ups,
        'avg_ups': round(avg_ups),
        'intensity': intensity,
        'posts': found_posts[:3],
    }


def fetch_stocktwits_sentiment(ticker: str) -> dict | None:
    """Fetch recent messages from Stocktwits as social media proxy."""
    try:
        resp = requests.get(
            f'https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if resp.status_code == 429 or resp.status_code == 403:
            return {'error': 'rate_limited', 'total_messages': 0}
        if resp.status_code != 200:
            return None
        data = resp.json()
        messages = data.get('messages', [])
        if not messages:
            return {'total_messages': 0, 'bullish_score': 0, 'bearish_score': 0, 'sentiment': 'neutral'}

        bull_kw = {'bullish', 'long', 'buy', 'moon', 'rocket', 'breakout', 'rip', 'mooning', 'call'}
        bear_kw = {'bearish', 'short', 'sell', 'crash', 'dump', 'death', 'falling', 'put', 'btfd'}
        bullish = bearish = 0
        for m in messages[:50]:
            body = (m.get('body', '') + ' ' + (m.get('title', '') or '')).lower()
            words = set(body.split())
            for w in words & bull_kw:
                bullish += 1
            for w in words & bear_kw:
                bearish += 1

        total = len(messages[:50])
        sentiment = 'bullish' if bullish > bearish * 1.5 else 'bearish' if bearish > bullish * 1.5 else 'neutral'
        return {
            'total_messages': total,
            'bullish_score': bullish,
            'bearish_score': bearish,
            'sentiment': sentiment,
            'latest': messages[0].get('body', '')[:100] if messages else '',
        }
    except Exception:
        return None


def fetch_live_data(ticker: str):
    t = yf.Ticker(ticker)
    info = t.info or {}
    hist = t.history(period="1y")
    if hist.empty:
        raise ValueError(f"No price history for {ticker}")

    price = (info.get('currentPrice') or info.get('regularMarketPrice')
             or float(hist['Close'].iloc[-1]))
    name = info.get('shortName') or info.get('longName') or ticker
    sector = info.get('sector') or info.get('category') or 'N/A'
    industry = info.get('industry') or 'N/A'
    quote_type = info.get('quoteType', 'STOCK')

    return {
        'ticker': ticker.upper(),
        'name': name,
        'price': float(price),
        'info': info,
        'hist': hist,
        'sector': sector,
        'industry': industry,
        'quote_type': quote_type,
    }


def fetch_option_chain(ticker: str, expiry: str | None = None):
    t = yf.Ticker(ticker)
    exps = list(t.options) if t.options else []
    if not exps:
        return None

    if expiry:
        if expiry not in exps:
            # find closest
            ad = min(exps, key=lambda e: abs(datetime.strptime(e, '%Y-%m-%d')
                                             - datetime.strptime(expiry, '%Y-%m-%d')))
            expiry = ad
    else:
        # pick furthest out with good liquidity
        expiry = exps[-1]

    chain = t.option_chain(expiry)
    exp_date = datetime.strptime(expiry, '%Y-%m-%d')
    dte = (exp_date - datetime.now()).days
    return {
        'expiry': expiry,
        'dte': dte,
        'calls': chain.calls,
        'puts': chain.puts,
        'exps': exps,
    }


# ── Strike auto-select ──
def auto_select_strikes(data: dict, opt: dict) -> dict:
    price = data['price']
    calls = opt['calls'].copy()
    puts = opt['puts'].copy()

    # Filter for liquidity
    calls = calls[((calls['openInterest'] > 50) & (calls['bid'] > 0.05))
                  | (calls['volume'] > 20)]
    puts = puts[((puts['openInterest'] > 50) & (puts['bid'] > 0.05))
                | (puts['volume'] > 20)]

    if calls.empty or puts.empty:
        # Relax filter
        calls = opt['calls'].copy()
        puts = opt['puts'].copy()
        calls = calls[calls['bid'] > 0.05]
        puts = puts[puts['bid'] > 0.05]
    if calls.empty or puts.empty:
        raise ValueError("No liquid option strikes found")

    best = None
    best_score = -999

    for _, p_row in puts.iterrows():
        pk = float(p_row['strike'])
        p_mid = (float(p_row['bid']) + float(p_row['ask'])) / 2
        if p_mid <= 0.05:
            continue

        for _, c_row in calls.iterrows():
            ck = float(c_row['strike'])
            c_mid = (float(c_row['bid']) + float(c_row['ask'])) / 2
            if c_mid <= 0.05:
                continue

            # Put must be below spot (OTM) — 15-30% below ideal
            put_otm_pct = (price - pk) / price
            if pk > price * 0.96 or pk < price * 0.55:
                continue

            # Call must be at or above spot — 0-20% above ideal
            call_otm_pct = (ck - price) / price
            if ck < price or ck > price * 1.35:
                continue

            net = 2 * p_mid - c_mid

            # Score: ideal combo has put 12-22% OTM, call 0-15% OTM, net >= 0
            put_ideal = put_otm_pct >= 0.12 and put_otm_pct <= 0.22
            call_ideal = call_otm_pct >= 0.0 and call_otm_pct <= 0.15

            score = 0
            # Net: slight credit is nice, slight debit is OK
            if net >= 0:
                score += 2.0 + min(net * 0.5, 2.0)
            else:
                score += max(net, -1.0)  # small debit penalty

            # Put distance — ideal is 12-22% OTM (strong support but decent premium)
            put_quality = 1 - abs(put_otm_pct - 0.17) / 0.17
            score += 5.0 * max(put_quality, 0)

            # Call distance — ideal is 0-10% OTM (near ATM)
            call_quality = 1 - abs(call_otm_pct - 0.05) / 0.12
            score += 5.0 * max(call_quality, 0)

            # Put closer to spot than call → bad structure (inverted)
            inverted_penalty = 0
            if pk > price and ck > price:
                inverted_penalty = -10
            elif pk > price:
                inverted_penalty = -5
            score += inverted_penalty

            # Bonus for round strikes
            if pk % 5 == 0:
                score += 1.0
            if ck % 5 == 0:
                score += 0.5

            # Liquidity bonus (OI)
            put_oi = float(p_row['openInterest']) if 'openInterest' in p_row.index else 0
            call_oi = float(c_row['openInterest']) if 'openInterest' in c_row.index else 0
            if put_oi > 500:
                score += 1.0
            if call_oi > 500:
                score += 0.5

            if score > best_score:
                best_score = score
                best = {
                    'put_strike': pk,
                    'call_strike': ck,
                    'put_mid': round(p_mid, 2),
                    'call_mid': round(c_mid, 2),
                    'put_bid': float(p_row['bid']),
                    'put_ask': float(p_row['ask']),
                    'call_bid': float(c_row['bid']),
                    'call_ask': float(c_row['ask']),
                    'net': round(net, 2),
                }

    if best is None:
        raise ValueError("Could not find suitable strikes for Synthetic Long 2:1")

    # IV from nearest ATM option
    atm_idx = (calls['strike'] - price).abs().idxmin()
    if atm_idx in calls.index and 'impliedVolatility' in calls.columns:
        iv = float(calls.loc[atm_idx, 'impliedVolatility'])
        if iv and not math.isnan(iv):
            best['iv'] = iv
    if 'iv' not in best:
        iv_vals = calls['impliedVolatility'].dropna()
        best['iv'] = float(iv_vals.mean()) if not iv_vals.empty else 0.50

    return best


# ── Thesis generation ──
def compute_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean()
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))


def generate_thesis(data: dict, opt: dict, strikes: dict):
    info = data['info']
    hist = data['hist']
    price = data['price']
    ticker = data['ticker']

    sections = []

    # ── 1. Company Overview ──
    biz = info.get('longBusinessSummary', '')
    if biz:
        biz_short = biz[:500] + ('...' if len(biz) > 500 else '')
    else:
        biz_short = f"{data['name']} ({ticker}) — {data['sector']}/{data['industry']}"

    sections.append(("1.1 Panoramica", biz_short))

    # ── 2. Valuazione ──
    val_parts = []
    pe = info.get('trailingPE') or info.get('forwardPE')
    if pe and pe > 0:
        val_parts.append(f"P/E {pe:.1f}x")
    pb = info.get('priceToBook')
    if pb:
        val_parts.append(f"P/B {pb:.2f}x")
    rev_g = info.get('revenueGrowth')
    if rev_g is not None:
        val_parts.append(f"Crescita ricavi {rev_g*100:+.1f}%")
    margins = info.get('profitMargins')
    if margins is not None:
        val_parts.append(f"Margini {margins*100:.1f}%")
    de = info.get('debtToEquity')
    if de is not None:
        val_parts.append(f"D/E {de:.2f}")
    div = info.get('dividendYield')
    if div and div > 0:
        val_parts.append(f"Div Yield {div*100:.2f}%")
    mcap = info.get('marketCap')
    if mcap:
        val_parts.append(f"MCap ${mcap/1e9:.1f}B")
    fcf = info.get('freeCashflow')
    if fcf:
        fcf_yield = fcf / mcap * 100 if mcap else 0
        val_parts.append(f"FCF ${fcf/1e9:.1f}B ({fcf_yield:.1f}% yield)")

    val_text = " | ".join(val_parts) if val_parts else "Dati fondamentali non disponibili."
    sections.append(("1.2 Metriche di Valore", val_text))

    # ── 3. Posizione Tecnica ──
    tech_parts = []
    if not hist.empty:
        ma50 = float(hist['Close'].rolling(50).mean().iloc[-1])
        ma200 = float(hist['Close'].rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None
        rsi_val = float(compute_rsi(hist['Close']).iloc[-1])
        yr_high = hist['High'].max()
        yr_low = hist['Low'].min()
        yr_pos = (price - yr_low) / (yr_high - yr_low) * 100

        tech_parts.append(f"Prezzo ${price:.2f}")
        tech_parts.append(f"MA50 ${ma50:.2f} ({'sopra' if price > ma50 else 'sotto'})")
        if ma200:
            tech_parts.append(f"MA200 ${ma200:.2f} ({'sopra' if price > ma200 else 'sotto'})")
        tech_parts.append(f"RSI(14) {rsi_val:.1f}")
        tech_parts.append(f"Range 52w: ${yr_low:.2f}-${yr_high:.2f} (pos {yr_pos:.0f}%)")

        # Wyckoff phase estimate
        recent_60 = hist.tail(60)
        if len(recent_60) >= 60:
            half = len(recent_60) // 2
            fh_max, fh_min = recent_60['High'].iloc[:half].max(), recent_60['Low'].iloc[:half].min()
            sh_max, sh_min = recent_60['High'].iloc[half:].max(), recent_60['Low'].iloc[half:].min()
            if sh_max > fh_max and sh_min > fh_min:
                wyckoff_phase = "Fase C/D — Markup (HH/HL)"
            elif sh_max < fh_max and sh_min < fh_min:
                wyckoff_phase = "Fase A/B — Markdown (LH/LL)"
            else:
                wyckoff_phase = "Fase B — Range / Accumulazione"

            # Volume trend
            vol_old = hist.tail(90).head(60)['Volume'].mean()
            vol_new = hist.tail(30)['Volume'].mean()
            if vol_new < vol_old * 0.8:
                wyckoff_phase += ", volume in calo (supply si esaurisce)"
            else:
                wyckoff_phase += f", volume {vol_new/vol_old:.1f}x"

            tech_parts.append(f"Wyckoff: {wyckoff_phase}")

        # Volatility
        ret_30d = hist['Close'].tail(30).pct_change().dropna()
        vol_ann = float(ret_30d.std() * math.sqrt(252)) * 100
        tech_parts.append(f"Vol atterra: {vol_ann:.0f}%")
        ret_1m = (price / hist['Close'].iloc[-22] - 1) * 100 if len(hist) >= 22 else None
        ret_3m = (price / hist['Close'].iloc[-66] - 1) * 100 if len(hist) >= 66 else None
        if ret_1m is not None:
            tech_parts.append(f"1m: {ret_1m:+.1f}%")
        if ret_3m is not None:
            tech_parts.append(f"3m: {ret_3m:+.1f}%")

    sections.append(("1.3 Posizione Tecnica", " | ".join(tech_parts)))

    # ── 4. Sentiment ──
    sent_parts = []
    si = info.get('shortPercentOfFloat')
    if si is not None:
        si_label = f"Short Interest {si*100:.1f}% del float"
        if si > 0.20:
            si_label += " (elevato — potenziale squeeze)"
        elif si > 0.10:
            si_label += " (moderato)"
        sent_parts.append(si_label)

    inst = info.get('heldPercentInstitutions')
    if inst is not None:
        sent_parts.append(f"Istituzionale {inst*100:.0f}%")

    dtc = info.get('shortRatio')
    if dtc is not None:
        sent_parts.append(f"Days to Cover {dtc:.1f}")

    insider = info.get('insiderPercentHeld')
    if insider is not None:
        sent_parts.append(f"Insider {insider*100:.1f}%")

    # Options flow
    if opt and 'exps' in opt and opt['exps']:
        try:
            near_exp = opt['exps'][0]
            near_chain = yf.Ticker(ticker).option_chain(near_exp)
            v_c = near_chain.calls['volume'].sum() if 'volume' in near_chain.calls.columns else 0
            v_p = near_chain.puts['volume'].sum() if 'volume' in near_chain.puts.columns else 0
            oi_c = near_chain.calls['openInterest'].sum() if 'openInterest' in near_chain.calls.columns else 0
            oi_p = near_chain.puts['openInterest'].sum() if 'openInterest' in near_chain.puts.columns else 0
            pcv = v_p / max(v_c, 1)
            pco = oi_p / max(oi_c, 1)
            pcv_str = f"P/C Vol {pcv:.2f}" + (" (call-heavy)" if pcv < 0.7 else " (put-heavy)" if pcv > 1.3 else "")
            pco_str = f"P/C OI {pco:.2f}" + (" (call-heavy)" if pco < 0.7 else " (put-heavy)" if pco > 1.3 else "")
            sent_parts.append(pcv_str)
            sent_parts.append(pco_str)
        except Exception:
            pass

    # News sentiment
    news = fetch_news(ticker)
    if news:
        bull = sum(1 for n in news if n['sentiment'] == 'bullish')
        bear = sum(1 for n in news if n['sentiment'] == 'bearish')
        sent_parts.append(f"News: {bull}B/{bear}S/{len(news)}T")
    else:
        sent_parts.append("News: N/A")

    # Social Media — Reddit WSB
    wsb = fetch_wsb_mentions(ticker)
    if wsb and wsb.get('error'):
        sent_parts.append("WSB: rate limit (API bloccato)")
    elif wsb and wsb.get('mentions', 0) > 0:
        intensity_map = {'high': '🔥🔥', 'medium': '🔥', 'low': '▫'}
        icon = intensity_map.get(wsb['intensity'], '')
        sent_parts.append(
            f"WSB: {wsb['mentions']} post ({wsb['avg_ups']} avg ups) {icon}")
    else:
        sent_parts.append("WSB: nessuna menzione recente")

    # Social Media — Stocktwits (proxy per X/Twitter)
    st = fetch_stocktwits_sentiment(ticker)
    if st and st.get('error'):
        sent_parts.append("Stocktwits: rate limit")
    elif st and st.get('total_messages', 0) > 0:
        st_icon = '🟢' if st['sentiment'] == 'bullish' else '🔴' if st['sentiment'] == 'bearish' else '⚪'
        sent_parts.append(
            f"Stocktwits: {st['total_messages']} msg ({st['bullish_score']}B/{st['bearish_score']}S) {st_icon}")
    else:
        sent_parts.append("Stocktwits: dati non disponibili")

    sections.append(("1.4 Sentiment", " | ".join(sent_parts)))

    # ── 5. Catalyst / Thesis ──
    thesis_parts = []

    # Build narrative based on available data
    catalysts = []

    if pe and pe < 15:
        catalysts.append(f"valutazione compressa (P/E {pe:.1f}x)")
    if rev_g and rev_g > 0.10:
        catalysts.append(f"crescita ricavi a {rev_g*100:.0f}%")
    if rsi_val and rsi_val < 35:
        catalysts.append(f"RSI {rsi_val:.0f} in zona ipervenduto")
    if rsi_val and rsi_val > 65:
        catalysts.append(f"momentum rialzista (RSI {rsi_val:.0f})")
    if si and si > 0.15:
        catalysts.append(f"short squeeze potenziale ({si*100:.1f}% float)")
    if inst and inst > 0.80:
        catalysts.append(f"forte presenza istituzionale ({inst*100:.0f}%)")
    if fcf and fcf > 0:
        catalysts.append(f"FCF positivo ${fcf/1e9:.1f}B")
    if news:
        bull_ratio = sum(1 for n in news if n['sentiment'] == 'bullish') / len(news)
        if bull_ratio > 0.5:
            catalysts.append("sentiment news positivo")
    if wsb and not wsb.get('error') and wsb.get('intensity') in ('high', 'medium'):
        catalysts.append(f"WSB buzz ({wsb['mentions']} post, avg {wsb['avg_ups']} ups)")
    if st and not st.get('error') and st.get('total_messages', 0) > 0:
        if st['sentiment'] == 'bullish' and st['total_messages'] >= 5:
            catalysts.append(f"Stocktwits bullish ({st['bullish_score']}/{st['bearish_score']})")
    if div and div > 0.03:
        catalysts.append(f"dividendo {div*100:.1f}% come floor")

    # Price action narrative
    if not hist.empty:
        recent = hist.tail(20)
        up_days = (recent['Close'] > recent['Open']).sum()
        if up_days >= 14:
            catalysts.append("forte pressione rialzista recente")
        elif up_days <= 6:
            catalysts.append("debolezza recente, possibile reversal")

    if catalysts:
        thesis_parts.append(
            f"{ticker} presenta catalizzatori interessanti: {', '.join(catalysts[:5])}."
        )

    # Social media context
    social_lines = []
    if wsb and not wsb.get('error') and wsb.get('intensity') in ('high', 'medium'):
        social_lines.append(
            f"Su Reddit r/wallstreetbets {ticker} e' menzionato {wsb['mentions']} volte "
            f"(media {wsb['avg_ups']} upvote) — {'interesse FEBBRILE' if wsb['intensity'] == 'high' else 'moderata attenzione retail'}.")
    if st and not st.get('error') and st.get('total_messages', 0) > 0 and st.get('sentiment') != 'neutral':
        direction = 'positivo' if st['sentiment'] == 'bullish' else 'negativo'
        social_lines.append(
            f"Su Stocktwits ({st['total_messages']} msg) il sentiment e' {direction} "
            f"({st['bullish_score']}B/{st['bearish_score']}S).")
    if social_lines:
        thesis_parts.append(' '.join(social_lines))

    # Spiegazione strategia
    thesis_parts.append(
        f"La Synthetic Long 2:1 (Sell 2x Put, Buy 1x Call) sfrutta l'asimmetria del profilo "
        f"payoff: se {ticker} sale sopra ${strikes['call_strike']:.0f} il guadagno e' illimitato, "
        f"se resta sopra ${strikes['put_strike']:.0f} la posizione e' profittevole o in pareggio."
    )

    # Asimmetria payoff
    if strikes['net'] >= 0:
        thesis_parts.append(
            f"L'entrata a credito di ${strikes['net']:.2f} fornisce un cuscinetto immediato: "
            f"il prezzo puo' scendere fino a ${strikes['put_strike'] - strikes['net']/2:.2f} "
            f"({(strikes['put_strike'] - strikes['net']/2)/price*100-100:.1f}%) prima di andare in perdita."
        )
    else:
        thesis_parts.append(
            f"L'entrata a debito di ${abs(strikes['net']):.2f} richiede che {ticker} salga "
            f"sopra ${strikes['call_strike'] + abs(strikes['net']):.2f} per raggiungere il break-even."
        )

    sections.append(("1.5 Tesi di Investimento", " ".join(thesis_parts)))

    # ── 6. Rischi ──
    risk_parts = []
    if pe and pe > 25:
        risk_parts.append(f"Valutazione non economica (P/E {pe:.1f}x)")
    if de and de > 1.5:
        risk_parts.append(f"Leverage elevato (D/E {de:.2f})")
    if margins is not None and margins < 0:
        risk_parts.append(f"Margini negativi ({margins*100:.1f}%)")
    if rev_g is not None and rev_g < 0:
        risk_parts.append(f"Ricavi in calo ({rev_g*100:.1f}%)")
    if si and si > 0.30:
        risk_parts.append("Short interest estremo — rischio gamma squeeze bilaterale")
    if wsb and not wsb.get('error') and wsb.get('intensity') == 'high':
        risk_parts.append("Elevata attenzione retail (WSB) — volatilita' imprevedibile da meme stock dynamics")
    risk_parts.append(f"Rischio settoriale: {data['sector']}/{data['industry']}")

    short_biz = (biz[:200] + '...') if biz and len(biz) > 200 else (biz or '')
    if 'lawsuit' in short_biz.lower() or 'investigation' in short_biz.lower():
        risk_parts.append("Rischio legale/regolatorio menzionato nel profilo aziendale")
    if 'debt' in short_biz.lower():
        risk_parts.append("Esposizione a debito menzionata nel profilo")

    sections.append(("1.6 Fattori di Rischio", ". ".join(risk_parts) if risk_parts else "Non identificati."))

    return sections


# ── PDF class ──
class PDF(FPDF):
    def __init__(self, ticker: str, name: str, color: tuple):
        super().__init__()
        self.ticker = ticker
        self.name = name
        self.accent = color
        self.add_font('DJ', '', FD)
        self.add_font('DJ', 'B', FB)
        self.add_font('DJ', 'I', FO)
        self.add_font('DJM', '', FM)
        self.add_font('DJM', 'B', FMB)

    def header(self):
        self.set_font('DJ', 'B', 9)
        self.set_text_color(120)
        self.cell(0, 6, f'{self.ticker} Synthetic Long 2:1  |  {self.name}  |  {date.today().strftime("%b %d, %Y")}', align='L')
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('DJ', 'I', 8)
        self.set_text_color(150)
        self.cell(0, 10, f'Pagina {self.page_no()}/{{nb}}', align='C')


# ── PDF generation ──
def generate_pdf(data: dict, opt: dict, strikes: dict, sections: list):
    ticker = data['ticker']
    name = data['name']
    price = data['price']
    color = get_sector_color(data['info'])
    dte = opt['dte']
    T = dte / 365.25
    iv = strikes.get('iv', 0.50)
    put_strike = strikes['put_strike']
    call_strike = strikes['call_strike']
    put_mid = strikes['put_mid']
    call_mid = strikes['call_mid']
    net = strikes['net']
    bpr = int(put_strike * 200 - net * 100)

    gP = bs_greeks(price, put_strike, T, R, iv, 'p')
    gC = bs_greeks(price, call_strike, T, R, iv, 'c')
    g_net = {k: gP[k] * (-2) + gC[k] * 1 for k in ['delta', 'gamma', 'theta', 'vega']}

    pdf = PDF(ticker, name, color)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ─── COVER ───
    pdf.set_font('DJ', 'B', 28)
    pdf.set_text_color(*color)
    pdf.cell(0, 14, f'{ticker} Synthetic Long 2:1', align='L')
    pdf.ln(12)
    pdf.set_font('DJ', '', 14)
    pdf.set_text_color(60)
    pdf.cell(0, 8, f'{name} — Analisi e Strategia Opzioni', align='L')
    pdf.ln(8)
    pdf.set_font('DJ', '', 10)
    pdf.cell(0, 6, f'Report generato il {date.today().strftime("%d %B %Y")} | Scadenza: {opt["expiry"]} ({dte} DTE)', align='L')
    pdf.ln(16)

    # Sinossi
    pdf.set_fill_color(*color)
    pdf.set_text_color(255)
    pdf.set_font('DJ', 'B', 13)
    pdf.cell(0, 10, '  SINOSSI', fill=True, align='L')
    pdf.ln(12)
    pdf.set_text_color(30)

    qt = data['quote_type']
    label = f"{ticker} ({qt})"
    sector_info = f"{data['sector']}/{data['industry']}"
    infos = [
        ('Ticker', label),
        ('Prezzo Spot', f'$ {price:.2f}'),
        ('Settore', sector_info),
        ('IV Media', f'{iv*100:.1f}%'),
        ('Esposizione', f'+{g_net["delta"]:.2f} Delta (~{int(abs(g_net["delta"])*100):,d} quote long)'),
        ('BPR (Margin)', f'$ {bpr:,d}'),
        ('Netto', f'$ {net:+.2f}  ({"credito" if net >= 0 else "debito"} all\'entrata)'),
        ('Break-Even Down', f'$ {put_strike - net/2:.2f}  ({(put_strike-net/2-price)/price*100:.1f}% sotto spot)'),
        ('Break-Even Up', 'nessun limite (upside illimitato)' if net >= 0 else f'$ {call_strike + abs(net):.2f}'),
        ('Theta', f'+$ {g_net["theta"]*100:.2f}/giorno'),
    ]
    for label_text, val in infos:
        pdf.set_font('DJM', '', 10)
        pdf.cell(42, 6, f'  {label_text}')
        pdf.set_font('DJM', 'B', 10)
        pdf.cell(0, 6, val)
        pdf.ln(5)

    # Struttura
    pdf.ln(6)
    pdf.set_fill_color(*tuple(min(c+30, 255) for c in color))
    pdf.set_text_color(30)
    pdf.set_font('DJ', 'B', 13)
    pdf.cell(0, 10, '  STRUTTURA', fill=True, align='L')
    pdf.ln(14)
    pdf.set_font('DJM', '', 10)
    cols = [('Gamba', 28), ('Qty', 12), ('Strike', 22), ('Prezzo', 22), ('Incasso/Costo', 32)]
    for c in cols:
        pdf.cell(c[1], 8, c[0], border=1, align='C')
    pdf.ln()
    rows_data = [
        ('Sell Put', '2x', f'${put_strike:.0f}', f'$ {put_mid:.2f}', f'+$ {put_mid*2*100:,.0f}'),
        ('Buy Call', '1x', f'${call_strike:.0f}', f'$ {call_mid:.2f}', f'-$ {call_mid*100:,.0f}'),
        ('NETTO', '', '', '', f'+$ {int(net*100):,d} {"CREDITO" if net >= 0 else "DEBITO"}'),
    ]
    for row in rows_data:
        bold = row[0] == 'NETTO'
        pdf.set_font('DJM', 'B' if bold else '', 10)
        for i, cell_val in enumerate(row):
            w = cols[i][1] if i < 4 else 32
            pdf.cell(w, 8, cell_val, border=1, align='C')
    pdf.ln(8)
    pdf.set_font('DJ', 'I', 9)
    pdf.set_text_color(100)
    theta_sign = 'positivo' if g_net['theta'] >= 0 else 'negativo'
    pdf.multi_cell(0, 5,
        f'Entrata a {"CREDITO" if net >= 0 else "DEBITO"} di ${abs(net)*100:,.0f}. Theta {theta_sign}: '
        f'la call (${call_strike:.0f}) bilanciata dalle 2 put OTM (${put_strike:.0f}).')

    # ═══════════════ 1. THESIS ═══════════════
    pdf.add_page()
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 18)
    pdf.cell(0, 12, '1. Quadro Teorico', align='L')
    pdf.ln(14)

    for title, body in sections:
        pdf.set_font('DJ', 'B', 11)
        pdf.set_text_color(*color)
        pdf.cell(0, 8, title, align='L')
        pdf.ln(9)
        pdf.set_text_color(40)
        pdf.set_font('DJ', '', 10)
        pdf.multi_cell(0, 5.5, body)
        pdf.ln(4)

    # ═══════════════ 2. GREEKS ═══════════════
    pdf.add_page()
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 18)
    pdf.cell(0, 12, '2. Greche - Pre-Trade', align='L')
    pdf.ln(14)
    pdf.set_text_color(30)

    pdf.set_font('DJM', '', 9)
    pdf.cell(52, 8, 'Struttura', border=1)
    for h in ['Delta', 'Gamma', 'Theta/d', 'Vega/%', 'Prob ITM']:
        pdf.cell(24, 8, h, border=1, align='C')
    pdf.ln()
    for label_g, qty, K, opt_type, mkt, g in [
        (f'Vendi 2x Put ${put_strike:.0f}', -2, put_strike, 'p', put_mid, gP),
        (f'Compra 1x Call ${call_strike:.0f}', 1, call_strike, 'c', call_mid, gC),
    ]:
        pdf.set_font('DJM', '', 9)
        pdf.cell(52, 7, f'  {label_g}', border=1)
        for k in ['delta', 'gamma', 'theta', 'vega']:
            pdf.cell(24, 7, f'{g[k]*qty:+.4f}', border=1, align='C')
        pdf.cell(24, 7, f'{g["prob"]*100:.1f}%', border=1, align='C')
        pdf.ln()
    pdf.set_font('DJM', 'B', 9)
    pdf.cell(52, 8, '  TOTALE COMBINATO', border=1)
    for k in ['delta', 'gamma', 'theta', 'vega']:
        pdf.cell(24, 8, f'{g_net[k]:+.4f}', border=1, align='C')
    pdf.cell(24, 8, '', border=1)
    pdf.ln(12)
    pdf.set_text_color(40)
    pdf.set_font('DJ', '', 10)
    pdf.multi_cell(0, 5.5,
        f'Delta {g_net["delta"]:+.2f} = ~{int(abs(g_net["delta"])*100):,d} quote {ticker} long. '
        f'Gamma {g_net["gamma"]:+.4f}: {"positiva (delta aumenta al rialzo)" if g_net["gamma"] >= 0 else "negativa (delta cala al rialzo)"}. '
        f'Theta {g_net["theta"]*100:+.2f}/giorno: {"la posizione guadagna" if g_net["theta"] >= 0 else "la posizione perde"} valore col tempo. '
        f'Vega {g_net["vega"]:+.4f}/%: {"favorisce" if g_net["vega"] >= 0 else "sfavorisce"} un aumento dell\'IV.')

    # Sensitivities
    pdf.ln(4)
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 12)
    pdf.cell(0, 10, '2.1  Sensitivita al Prezzo', align='L')
    pdf.ln(10)
    pdf.set_text_color(30)
    pdf.set_font('DJM', '', 9)
    for h, w in [('Spot $', 22), ('Delta', 28), ('Gamma', 28), ('Theta/d', 28), ('Vega/%', 28)]:
        pdf.cell(w, 8, h, border=1, align='C')
    pdf.ln()

    lo = max(price * 0.65, put_strike * 0.8)
    hi = price * 1.5
    step = max(5, round((hi - lo) / 14 / 5) * 5)
    sens_range = list(range(int(lo // step * step), int(hi // step * step + step), step))
    for sp in sens_range:
        gsp = bs_greeks(sp, put_strike, T, R, iv, 'p')
        gsc = bs_greeks(sp, call_strike, T, R, iv, 'c')
        d = gsp['delta'] * (-2) + gsc['delta'] * 1
        ga = gsp['gamma'] * (-2) + gsc['gamma'] * 1
        t = gsp['theta'] * (-2) + gsc['theta'] * 1
        v = gsp['vega'] * (-2) + gsc['vega'] * 1
        pdf.cell(22, 6, f'${sp:.0f}', border=1, align='C')
        pdf.cell(28, 6, f'{d:+.4f}', border=1, align='C')
        pdf.cell(28, 6, f'{ga:+.4f}', border=1, align='C')
        pdf.cell(28, 6, f'{t:+.4f}', border=1, align='C')
        pdf.cell(28, 6, f'{v:+.4f}', border=1, align='C')
        pdf.ln()

    # ═══════════════ 3. PAYOFF ═══════════════
    pdf.add_page()
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 18)
    pdf.cell(0, 12, '3. Payoff a Scadenza', align='L')
    pdf.ln(14)
    pdf.set_text_color(30)

    pdf.set_font('DJM', '', 8.5)
    ph = [('Prezzo', 18), ('P&L Put', 24), ('P&L Call', 24), ('P&L Totale', 28), ('ROI%', 18), ('Scenario', 50)]
    for h, w in ph:
        pdf.cell(w, 8, h, border=1, align='C')
    pdf.ln()

    payoff_prices = [0, price * 0.3, price * 0.5, price * 0.7, put_strike * 0.95,
                     put_strike - net/2, put_strike, price * 0.95, price,
                     price * 1.05, call_strike, call_strike + abs(net) if net < 0 else call_strike,
                     price * 1.2, price * 1.4]

    payoff_prices = sorted(set(round(p, 2) for p in payoff_prices if p > 0))
    payoff_prices = [p for p in payoff_prices if p <= price * 2.0]

    # Ensure key levels are present
    if put_strike - net/2 > 0:
        payoff_prices.append(round(put_strike - net / 2, 2))
    payoff_prices = sorted(set(payoff_prices))

    # Limit to ~15 rows
    if len(payoff_prices) > 18:
        payoff_prices = payoff_prices[::len(payoff_prices)//15][:15]
        payoff_prices[-1] = price * 1.5

    for p in payoff_prices:
        ppnl = -2 * max(0, put_strike - p) * 100
        cpnl = max(0, p - call_strike) * 100
        tot = ppnl + cpnl + int(net * 100)
        roi = tot / bpr * 100 if bpr > 0 else 0

        if p == 0:
            note = 'MAX LOSS'
        elif abs(p - (put_strike - net / 2)) < 0.05:
            note = 'BREAK-EVEN DOWN'
        elif abs(p - put_strike) < 0.05:
            note = 'Put OTM → keep premium'
        elif abs(p - price) < 0.05:
            note = 'FLAT → keep premium'
        elif abs(p - call_strike) < 0.05:
            note = 'Call ATM → keep premium'
        elif p > price * 1.3:
            note = 'UPSIDE ILLIMITATO'
        else:
            note = ''

        is_key = p == 0 or abs(p - (put_strike - net / 2)) < 0.05 or abs(p - price) < 0.05
        col_rgb = (200, 0, 0) if p == 0 else ((0, 150, 0) if p >= put_strike else (200, 100, 0))

        pdf.set_font('DJM', 'B' if is_key else '', 8.5)
        pdf.set_text_color(*col_rgb)
        pdf.cell(18, 6, f'${p:.2f}', border=1, align='C')
        pdf.cell(24, 6, f'{int(ppnl):+5,d}', border=1, align='C')
        pdf.cell(24, 6, f'{int(cpnl):+5,d}', border=1, align='C')
        pdf.cell(28, 6, f'${int(tot):+6,d}', border=1, align='C')
        pdf.cell(18, 6, f'{roi:+5.1f}%', border=1, align='C')
        pdf.cell(50, 6, note, border=1)
        pdf.ln()

    pdf.set_text_color(30)
    pdf.ln(6)
    pdf.set_font('DJ', 'I', 10)
    pdf.set_text_color(80)
    pdf.multi_cell(0, 5.5,
        f'Payoff asimmetrico. Max loss $-{abs(int(2*put_strike*100 - net*100)):,d} solo se {ticker}=$0. '
        f'Break-even a ${put_strike - net/2:.2f} ({(put_strike-net/2-price)/price*100:.1f}% dallo spot). '
        f'Sopra ${call_strike:.0f}, upside illimitato.')

    # ═══════════════ 4. THETA ═══════════════
    pdf.ln(4)
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 18)
    pdf.cell(0, 12, f'4. Decadimento Temporale (S=${price:.2f} fisso)', align='L')
    pdf.ln(14)
    pdf.set_text_color(30)

    td = [('DTE', 18), (f'2xPut ${put_strike:.0f}', 24), (f'1xCall ${call_strike:.0f}', 24),
          ('P&L vs Entry', 28), ('Theta Accumulato', 68)]
    pdf.set_font('DJM', '', 10)
    for h, w in td:
        pdf.cell(w, 8, h, border=1, align='C')
    pdf.ln()

    for days_left in [dte, int(dte * 0.75), int(dte * 0.6), int(dte * 0.45),
                      int(dte * 0.3), int(dte * 0.15), int(dte * 0.07)]:
        if days_left < 5:
            continue
        tr = days_left / 365.25
        gpd = bs_greeks(price, put_strike, tr, R, iv, 'p')
        gcd2 = bs_greeks(price, call_strike, tr, R, iv, 'c')
        pl_theta = int((-2 * (gpd['price'] - put_mid) + 1 * (gcd2['price'] - call_mid)) * 100)
        theta_note = f'+${pl_theta:,d} theta accumulato' if pl_theta >= 0 else f'-${abs(pl_theta):,d}'

        pdf.set_font('DJM', '', 10)
        pdf.cell(18, 6, f'{days_left}', border=1, align='C')
        pdf.cell(24, 6, f'${gpd["price"]:.2f}', border=1, align='C')
        pdf.cell(24, 6, f'${gcd2["price"]:.2f}', border=1, align='C')
        if pl_theta >= 0:
            pdf.set_text_color(0, 150, 0)
        else:
            pdf.set_text_color(200, 0, 0)
        pdf.set_font('DJM', 'B', 10)
        pdf.cell(28, 6, f'$ {pl_theta:+3,d}', border=1, align='C')
        pdf.set_text_color(30)
        pdf.set_font('DJ', '', 9)
        pdf.cell(68, 6, theta_note, border=1)
        pdf.ln()

    flat_ret = net * 100 / bpr * 100
    ann_ret = ((1 + net * 100 / bpr) ** (365 / dte) - 1) * 100 if net >= 0 else 0
    pdf.ln(6)
    pdf.set_text_color(80)
    pdf.set_font('DJ', 'I', 10)
    if net >= 0:
        pdf.multi_cell(0, 5.5,
            f'Se {ticker} rimane piatto a ${price:.2f} fino a scadenza: +${int(net*100):,d} = '
            f'{flat_ret:.1f}% sul BPR. Annualizzato: {ann_ret:.1f}%. Theta positivo: ogni giorno '
            f'che passa senza movimento significativo, la posizione guadagna valore. '
            f'Dopo 60 giorni flat: +${int(net*100*0.3):,d} accumulati.')
    else:
        pdf.multi_cell(0, 5.5,
            f'Se {ticker} rimane piatto a ${price:.2f}: la posizione perde ${abs(net)*100:.0f} '
            f'({flat_ret:.1f}% del BPR). Necessario rialzo per break-even.')

    # ═══════════════ 5. SCENARI ═══════════════
    pdf.add_page()
    pdf.set_text_color(*color)
    pdf.set_font('DJ', 'B', 18)
    pdf.cell(0, 12, '5. Scenari & Gestione', align='L')
    pdf.ln(14)
    pdf.set_text_color(30)

    bull_tgt = call_strike + (price - call_strike) * 0.5 if call_strike > price else price * 1.2
    mod_tgt = price * 1.05
    flat_lo = put_strike * 1.02
    pull_lo = put_strike * 0.98
    fail_lo = put_strike * 0.92

    def pnl_at(s):
        return int((-2 * max(0, put_strike - s) + max(0, s - call_strike) + net) * 100)

    scenarios = [
        (f'THESIS BULL (Prob 20%)', f'{ticker} > ${bull_tgt:.0f}',
         f'Catalizzatori positivi si concretizzano. P&L: +${pnl_at(bull_tgt):,d} a ${bull_tgt:.0f}, '
         f'+${pnl_at(price*1.3):,d} a ${price*1.3:.0f}, +${pnl_at(price*1.5):,d} a ${price*1.5:.0f}. '
         f'Tenere fino a scadenza; valutare roll se momentum continua.'),
        (f'RECOVERY MODERATO (Prob 30%)', f'{ticker} ${mod_tgt:.0f}-${bull_tgt:.0f}',
         f'Mercato stabile, tesi si sviluppa senza intoppi. '
         f'P&L: ${pnl_at(mod_tgt):,d} a ${mod_tgt:.0f}, ${pnl_at(bull_tgt):,d} a ${bull_tgt:.0f}. '
         f'Chiudere meta\' posizione a profitto per proteggere.'),
        (f'FLAT / CONSOLIDA (Prob 25%)', f'{ticker} ${flat_lo:.0f}-${mod_tgt:.0f}',
         f'Mercato laterale, prezzo oscilla senza trend. '
         f'P&L: ${pnl_at(flat_lo):,d} a ${flat_lo:.0f}, +${pnl_at(price):,d} a ${price:.0f}. '
         f'Lasciare scadere put, rollare call se OTM a 60gg.'),
        (f'PULLBACK TECNICO (Prob 15%)', f'{ticker} ${pull_lo:.0f}-${flat_lo:.0f}',
         f'Profit taking, test di supporto. '
         f'P&L: ${pnl_at(pull_lo):,d} a ${pull_lo:.0f}. '
         f'STOP LOSS se {ticker} chiude sotto ${pull_lo:.0f} per 2gg consecutivi.'),
        (f'THESIS FAIL (Prob 10%)', f'{ticker} < ${fail_lo:.0f}',
         f'Shock macro, settore in crisi, tesi non valida. '
         f'P&L: ${pnl_at(fail_lo):,d} a ${fail_lo:.0f}, ${pnl_at(put_strike*0.8):,d} a ${put_strike*0.8:.0f}, '
         f'-${abs(int(2*put_strike*100 - net*100)):,d} a $0. Stop loss sotto ${pull_lo:.0f}.'),
    ]
    for title, subtitle, body in scenarios:
        pdf.set_font('DJ', 'B', 12)
        pdf.set_text_color(*color)
        pdf.cell(0, 8, title, align='L')
        pdf.ln(8)
        pdf.set_font('DJ', 'B', 10)
        pdf.set_text_color(60)
        pdf.cell(0, 6, subtitle, align='L')
        pdf.ln(6)
        pdf.set_font('DJ', '', 10)
        pdf.set_text_color(40)
        pdf.multi_cell(0, 5.5, body)
        pdf.ln(5)

    # ═══════════════ 6. ESECUZIONE ═══════════════
    pdf.ln(4)
    pdf.set_fill_color(*color)
    pdf.set_text_color(255)
    pdf.set_font('DJ', 'B', 13)
    pdf.cell(0, 10, f'  ESECUZIONE  |  {date.today().strftime("%d %B %Y")}', fill=True, align='L')
    pdf.ln(14)
    pdf.set_text_color(30)

    net_target = net if net >= 0 else net
    orders = [
        (f'BUY  +1  {ticker} 100 Call ${call_strike:.0f} {opt["expiry"]} @ LIMIT ${call_mid:.2f}', (0, 100, 0), 'DJM', True),
        (f'SELL -2  {ticker} 100 Put  ${put_strike:.0f}  {opt["expiry"]} @ LIMIT ${put_mid:.2f}', (0, 100, 0), 'DJM', True),
        ('', (50, 50, 50), 'DJM', False),
        (f'Netto target:           $ {net:+.2f} credito (o meglio)', color, 'DJM', True),
        (f'Accettabile:            $ {max(net - 0.20, net * 0.8):+.2f} (worst case)', (50, 50, 50), 'DJM', False),
        (f'BPR impegnato:          $ {bpr:,d}', (50, 50, 50), 'DJM', False),
        (f'Max Loss:               $ {int(2*put_strike*100 - net*100):,d} ({ticker} = $0)', (50, 50, 50), 'DJM', False),
        (f'Stop Loss:              Chiudi se {ticker} < ${pull_lo:.0f} per 2gg consecutivi', (50, 50, 50), 'DJM', False),
        (f'Take Profit:            Chiudi 50% a ${bull_tgt:.0f}+', (50, 50, 50), 'DJM', False),
        (f'Roll:                   Se {ticker} > ${call_strike:.0f} a 60gg, rolla call in avanti', (50, 50, 50), 'DJM', False),
    ]
    for text, clr, font, bold in orders:
        pdf.set_font(font, 'B' if bold else '', 10)
        pdf.set_text_color(*clr)
        pdf.cell(0, 6, text)
        pdf.ln()

    # Disclaimer
    pdf.ln(10)
    pdf.set_font('DJ', 'I', 8)
    pdf.set_text_color(140)
    pdf.multi_cell(0, 4,
        'DISCLAIMER: Report generato da sistema automatico di analisi. Non costituisce consulenza finanziaria. '
        'Le opzioni comportano rischi significativi. Synthetic Long 2:1 comporta obbligo potenziale di acquisto '
        'delle quote al prezzo strike delle put vendute. Dati yfinance. '
        f'Report: {date.today().strftime("%d %B %Y")}.')

    # ═══ SAVE ═══
    slug = ticker.lower()
    outdir = Path(__file__).resolve().parent.parent / 'reports' / slug
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f'{ticker}_Synthetic_Long_2-1_{date.today().strftime("%Y%m%d")}.pdf'
    pdf.output(str(outpath))
    return str(outpath)


# ── CLI ──
def main():
    parser = argparse.ArgumentParser(
        description='Generate Synthetic Long 2:1 PDF report for any ticker')
    parser.add_argument('--ticker', '-t', required=True, help='Ticker symbol (e.g. IGV, HPQ)')
    parser.add_argument('--expiry', '-e', help='Option expiry date (YYYY-MM-DD). Auto-selects if omitted.')
    parser.add_argument('--put-strike', type=float, help='Put strike price. Auto-selected if omitted.')
    parser.add_argument('--call-strike', type=float, help='Call strike price. Auto-selected if omitted.')
    parser.add_argument('--iv', type=float, help='Implied volatility override (decimal).')
    args = parser.parse_args()

    ticker = args.ticker.upper()
    print(f"📡 Fetching data for {ticker}...")

    data = fetch_live_data(ticker)
    print(f"   Price: ${data['price']:.2f}")
    print(f"   Name: {data['name']}")
    print(f"   Sector: {data['sector']}")

    print(f"\n📡 Fetching options chain...")
    opt = fetch_option_chain(ticker, args.expiry)
    if opt is None:
        print(f"❌ No options available for {ticker}")
        sys.exit(1)
    print(f"   Expiry: {opt['expiry']} ({opt['dte']} DTE)")

    if args.put_strike and args.call_strike:
        # User-specified strikes
        puts = opt['puts']
        calls = opt['calls']
        p_row = puts[puts['strike'] == args.put_strike]
        c_row = calls[calls['strike'] == args.call_strike]
        if p_row.empty:
            print(f"❌ Put strike ${args.put_strike:.0f} not available")
            sys.exit(1)
        if c_row.empty:
            print(f"❌ Call strike ${args.call_strike:.0f} not available")
            sys.exit(1)

        p_row = p_row.iloc[0]
        c_row = c_row.iloc[0]
        strikes = {
            'put_strike': args.put_strike,
            'call_strike': args.call_strike,
            'put_mid': round((float(p_row['bid']) + float(p_row['ask'])) / 2, 2),
            'call_mid': round((float(c_row['bid']) + float(c_row['ask'])) / 2, 2),
            'put_bid': float(p_row['bid']),
            'put_ask': float(p_row['ask']),
            'call_bid': float(c_row['bid']),
            'call_ask': float(c_row['ask']),
            'net': round(2 * (float(p_row['bid']) + float(p_row['ask'])) / 2
                         - (float(c_row['bid']) + float(c_row['ask'])) / 2, 2),
        }
        if args.iv:
            strikes['iv'] = args.iv
        else:
            iv_vals = calls['impliedVolatility'].dropna()
            strikes['iv'] = float(iv_vals.mean()) if not iv_vals.empty else 0.50
    else:
        print(f"\n🤖 Auto-selecting optimal strikes...")
        strikes = auto_select_strikes(data, opt)

    print(f"   Put: ${strikes['put_strike']:.0f} @ ${strikes['put_mid']:.2f}")
    print(f"   Call: ${strikes['call_strike']:.0f} @ ${strikes['call_mid']:.2f}")
    print(f"   Net: ${strikes['net']:+.2f}")
    print(f"   IV: {strikes.get('iv', 0)*100:.1f}%")

    print(f"\n📝 Generating thesis...")
    sections = generate_thesis(data, opt, strikes)
    print(f"   {len(sections)} sections generated")

    print(f"\n📄 Generating PDF...")
    path = generate_pdf(data, opt, strikes, sections)
    print(f"\n✅ Report salvato: {path}")


if __name__ == '__main__':
    main()
