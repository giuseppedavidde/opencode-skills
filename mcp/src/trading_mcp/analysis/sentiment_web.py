"""Web sentiment: yfinance news + Finviz fallback + WSB hotlist.

Lightweight sentiment scoring for web_news and social_media sub-dimensions.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yfinance as yf

BULLISH_WORDS = [
    "beat", "beats", "upgrade", "upgraded", "outperform", "overweight",
    "buy", "strong buy", "positive", "growth", "record", "surge",
    "soar", "rally", "bull", "bullish", "raise", "raised", "raised target",
    "raised guidance", "momentum", "breakout",
    "accumulation", "undervalued", "cheap", "opportunity",
    "partnership", "contract", "approval", "launch", "expansion",
    "profit", "profitable", "revenue growth", "dividend", "buyback",
]

BEARISH_WORDS = [
    "miss", "misses", "downgrade", "downgraded", "underperform", "underweight",
    "sell", "strong sell", "negative", "decline", "drop", "plunge",
    "crash", "bear", "bearish", "cut", "lowered", "cuts target",
    "cuts guidance", "cuts outlook", "layoff", "layoffs", "restructuring",
    "lawsuit", "fine", "investigation", "probe", "recall",
    "debt", "bankruptcy", "insolvent", "loss", "unprofitable",
    "warning", "crisis", "risk", "uncertainty", "volatility",
]

WSB_KEYWORDS = [
    "yolo", "diamond hands", "paper hands", "to the moon",
    "tendies", "stonk", "stonks", "bagholder", "bagholding",
    "short squeeze", "gamma squeeze", "moon", "rocket", "rockets",
    "pump", "dump", "apes", "inverse cramer",
]


def fetch_yfinance_news(ticker: str, timeout: int = 8) -> tuple[float | None, str]:
    """Fetch recent news from yfinance ticker news feed.

    Returns (score 0-100, detail_string) or (None, error_reason).
    """
    try:
        t = yf.Ticker(ticker)
        news = t.news
        if not news:
            return None, "No news from yfinance"
    except Exception as e:
        return None, f"yfinance news error: {e}"

    headlines = []
    for item in news[:20]:
        title = item.get("title", "") or item.get("content", {}).get("title", "")
        if title and len(title) > 10:
            headlines.append(str(title))

    if not headlines:
        return None, "Empty headlines from yfinance"

    return _score_headlines(headlines)


def fetch_finviz_news(ticker: str, timeout: int = 8) -> tuple[float | None, str]:
    """Fetch Finviz news headlines (fallback when yfinance news is empty)."""
    try:
        import urllib.request

        url = f"https://finviz.com/quote.ashx?t={ticker}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        req.add_header("Accept", "text/html,application/xhtml+xml")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None, f"Finviz HTTP error: {e}"

    headlines: list[str] = []
    link_pattern = re.compile(
        r'<a[^>]*href="([^"]*)"[^>]*class="tab-link-news"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in link_pattern.finditer(html):
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if text and len(text) > 10:
            headlines.append(text)

    if not headlines:
        news_row_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
        for match in news_row_pattern.finditer(html):
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text and len(text) > 15 and not text.startswith("<"):
                headlines.append(text)

    if not headlines:
        return None, "No Finviz headlines found"

    return _score_headlines(headlines)


def fetch_wsb_hotlist(timeout: int = 8) -> dict[str, Any] | None:
    """Fetch WallStreetBets hot mentions from Reddit public JSON."""
    try:
        import urllib.request

        url = "https://www.reddit.com/r/wallstreetbets/hot.json?limit=100"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "trading-mcp/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    ticker_mentions: dict[str, dict] = {}
    ticker_re = re.compile(r"\$([A-Z]{1,5})\b|([A-Z]{2,5})")
    stopwords = {
        "A", "I", "DD", "WSB", "YOLO", "ETF", "IPO", "CEO", "CFO",
        "GDP", "CPI", "FOMC", "SEC", "FDA", "USA", "USD", "EUR",
        "AI", "IT", "PM", "AM", "UK", "US", "EU", "THE", "FOR",
        "AND", "NOT", "BUT", "ARE", "WAS", "HAS", "HAD",
    }

    for post in data.get("data", {}).get("children", []):
        post_data = post.get("data", {})
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        text = f"{title} {selftext}"
        score = post_data.get("score", 0)
        num_comments = post_data.get("num_comments", 0)

        found = set()
        wsb_word_hits = sum(1 for w in WSB_KEYWORDS if w.lower() in text.lower())

        for m in ticker_re.finditer(text):
            ticker_found = m.group(1) or m.group(2)
            if ticker_found and ticker_found.upper() not in stopwords:
                found.add(ticker_found.upper())

        for tick in found:
            weight = score / 100 + wsb_word_hits * 2 + num_comments / 5
            if tick not in ticker_mentions:
                ticker_mentions[tick] = {"count": 0, "weight": 0.0, "wsb_keywords": 0}
            ticker_mentions[tick]["count"] += 1
            ticker_mentions[tick]["weight"] += weight
            ticker_mentions[tick]["wsb_keywords"] += wsb_word_hits

    return ticker_mentions if ticker_mentions else None


def compute_social_sentiment(
    ticker: str, wsb_hotlist: dict[str, dict] | None
) -> tuple[float | None, str]:
    """Compute social media sentiment from WSB hotlist data."""
    if wsb_hotlist is None:
        return None, "No WSB data"

    ticker_upper = ticker.upper()
    if ticker_upper not in wsb_hotlist:
        return None, f"Not in WSB hotlist"

    data = wsb_hotlist[ticker_upper]
    count = data.get("count", 0)
    wsb_kw = data.get("wsb_keywords", 0)
    weight = data.get("weight", 0.0)

    score = 40.0
    if count >= 5:
        score += 20
    elif count >= 3:
        score += 10
    if wsb_kw >= 5:
        score += 20
    elif wsb_kw >= 3:
        score += 10
    if weight > 50:
        score += 15
    elif weight > 10:
        score += 10

    return min(100.0, score), f"WSB mentions: {count} | keywords: {wsb_kw} | weight: {weight:.1f}"


def _score_headlines(headlines: list[str]) -> tuple[float, str]:
    bull_count = 0
    bear_count = 0

    for headline in headlines:
        lowered = headline.lower()
        for word in BULLISH_WORDS:
            if word in lowered:
                bull_count += 1
                break
        else:
            for word in BEARISH_WORDS:
                if word in lowered:
                    bear_count += 1
                    break

    total = bull_count + bear_count
    if total == 0:
        return 50.0, f"No sentiment keywords in {len(headlines)} headlines"

    score = 50.0 + (bull_count - bear_count) / total * 40.0
    score = min(100.0, max(0.0, score))

    if bull_count > bear_count:
        parts = [f"{bull_count}B vs {bear_count}S (bullish)"]
    elif bear_count > bull_count:
        parts = [f"{bull_count}B vs {bear_count}S (bearish)"]
    else:
        parts = [f"{bull_count}B vs {bear_count}S (neutral)"]

    parts.append(f"{len(headlines)} headlines")
    return round(score, 1), " | ".join(parts)

