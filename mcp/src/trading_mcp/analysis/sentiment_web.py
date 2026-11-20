"""Web sentiment: yfinance news, Finviz fallback and the WSB hotlist (SIG-09).

Headline scoring (documented heuristic, unvalidated):

- Phrases are matched on word boundaries, never as substrings ("cut" does
  not match "cutting-edge").
- BOTH bullish and bearish phrases are checked in every headline.
- A negation ("not", "no", "never", "fails to", "unable to", "without")
  within the three words before a phrase flips its sign.
- Rating changes: a headline with "upgrade(s|d)" or "downgrade(s|d)" is
  scored by that verb only; rating words ("buy", "hold", "sell",
  "outperform"...) in it are ignored ("downgrades X from Buy to Hold" is bearish).
- Contrast: in "A but B" (also "however", "yet", "although") the last
  clause counts fully and the earlier clauses count half
  ("beats estimates but cuts guidance" is bearish).
- A headline counts as bullish or bearish by the sign of its total; the
  score is 50 + 40 x (bullish - bearish) / (headlines with a sign).

News requests: yfinance news goes through the shared Yahoo token bucket
(:data:`trading_mcp.data.http_policy.YAHOO_BUCKET`) with a 15-minute cache;
Finviz and Reddit have per-host circuit breakers (:mod:`trading_mcp.analysis.circuit`).

Social attention (WSB): heavy retail attention is NOT scored as bullish.
Attention-driven retail buying is followed by negative returns on average
(Barber & Odean 2008, Review of Financial Studies 21(2); Barber, Huang,
Odean & Schwarz 2022, Journal of Finance 77(6)), so attention maps to a
mildly bearish score: high 40, medium 45, low 48.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from trading_mcp.analysis.circuit import breaker
from trading_mcp.data.http_policy import YAHOO_BUCKET, UpstreamFailure, call_with_retry, classify_exception

BULLISH_PHRASES = [
    "beat", "beats", "tops", "upgrade", "upgrades", "upgraded", "raises guidance", "raised guidance",
    "raises outlook", "raises forecast", "raises target", "raised target", "record", "surge", "surges",
    "soar", "soars", "rally", "rallies", "jump", "jumps", "bullish", "strong demand", "profit rises",
    "revenue growth", "buyback", "dividend increase", "raises dividend", "approval", "approved",
    "partnership", "contract win", "wins contract", "expansion", "outperform", "overweight", "buy rating",
]

BEARISH_PHRASES = [
    "miss", "misses", "missed", "downgrade", "downgrades", "downgraded", "cuts guidance", "cut guidance",
    "lowers guidance", "cuts outlook", "lowers outlook", "cuts forecast", "cuts target", "lowered target",
    "plunge", "plunges", "crash", "crashes", "slump", "slumps", "tumble", "tumbles", "drop", "drops",
    "bearish", "layoff", "layoffs", "lawsuit", "sued", "fine", "fined", "investigation", "probe", "recall",
    "bankruptcy", "insolvent", "loss widens", "warning", "warns", "profit warning", "underperform",
    "underweight", "sell rating", "dividend cut", "cuts dividend",
]

RATING_WORDS = {
    "buy", "sell", "hold", "neutral", "outperform", "underperform", "overweight", "underweight",
    "strong buy", "strong sell", "market perform", "equal weight", "equal-weight", "buy rating", "sell rating",
}
NEGATIONS = ("not", "no", "never", "without", "fails to", "failed to", "unable to", "n't")
CONTRAST = re.compile(r"\b(?:but|however|yet|although)\b", re.IGNORECASE)

WSB_KEYWORDS = [
    "yolo", "diamond hands", "paper hands", "to the moon",
    "tendies", "stonk", "stonks", "bagholder", "bagholding",
    "short squeeze", "gamma squeeze", "moon", "rocket", "rockets",
    "pump", "dump", "apes", "inverse cramer",
]

_NEWS_TTL_S = 900.0
_news_cache: dict[str, tuple[float, tuple[float | None, str]]] = {}
_news_lock = threading.Lock()


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![a-z])", re.IGNORECASE)


_BULL = [(p, _phrase_pattern(p)) for p in sorted(BULLISH_PHRASES, key=len, reverse=True)]
_BEAR = [(p, _phrase_pattern(p)) for p in sorted(BEARISH_PHRASES, key=len, reverse=True)]


def _negated(text: str, start: int) -> bool:
    """True when a negation is among the three words before ``start``."""
    before = re.findall(r"[a-z']+", text[:start].lower())[-3:]
    if any(word.endswith("n't") for word in before):
        return True
    joined = " " + " ".join(before) + " "
    return any(f" {neg} " in joined for neg in NEGATIONS if neg != "n't")


def _clause_polarity(clause: str, rating_change: bool) -> float:
    total = 0.0
    taken: list[tuple[int, int]] = []
    for sign, patterns in ((1.0, _BULL), (-1.0, _BEAR)):
        for phrase, pattern in patterns:
            if rating_change and phrase in RATING_WORDS:
                continue
            for match in pattern.finditer(clause):
                span = (match.start(), match.end())
                if any(a < span[1] and span[0] < b for a, b in taken):
                    continue
                taken.append(span)
                total += -sign if _negated(clause, match.start()) else sign
    return total


def headline_polarity(headline: str) -> float:
    """Signed polarity of one headline (see the module docstring)."""
    text = headline.strip()
    lowered = text.lower()
    rating_change = bool(re.search(r"\b(?:up|down)grade[sd]?\b", lowered))
    if rating_change:
        up = len(re.findall(r"\bupgrade[sd]?\b", lowered))
        down = len(re.findall(r"\bdowngrade[sd]?\b", lowered))
        if up != down:
            return 1.0 if up > down else -1.0
    clauses = [c for c in CONTRAST.split(text) if c.strip()]
    total = 0.0
    for index, clause in enumerate(clauses):
        weight = 1.0 if index == len(clauses) - 1 else 0.5
        total += weight * _clause_polarity(clause, rating_change)
    return total


def _score_headlines(headlines: list[str]) -> tuple[float, str]:
    bull = bear = 0
    for headline in headlines:
        polarity = headline_polarity(headline)
        if polarity > 0:
            bull += 1
        elif polarity < 0:
            bear += 1
    total = bull + bear
    if total == 0:
        return 50.0, f"No sentiment phrases in {len(headlines)} headlines"
    score = min(100.0, max(0.0, 50.0 + (bull - bear) / total * 40.0))
    tone = "bullish" if bull > bear else "bearish" if bear > bull else "neutral"
    return round(score, 1), f"{bull}B vs {bear}S ({tone}) | {len(headlines)} headlines"


def _yf_news(ticker: str) -> Any:
    import yfinance as yf  # pylint: disable=import-outside-toplevel

    return yf.Ticker(ticker).news


def fetch_yfinance_news(ticker: str, timeout: int = 8) -> tuple[float | None, str]:
    """Score recent yfinance headlines (15-minute cache; shared Yahoo bucket).

    Returns (score 0-100, detail) or (None, reason).
    """
    del timeout
    key = ticker.upper()
    now = time.time()
    with _news_lock:
        entry = _news_cache.get(key)
    if entry is not None and now - entry[0] < _NEWS_TTL_S:
        return entry[1]
    try:
        news = call_with_retry(lambda: _yf_news(key), what=f"news {key}", bucket=YAHOO_BUCKET, max_attempts=2)
    except UpstreamFailure as exc:
        return None, f"yfinance news error: {exc.kind}"
    headlines: list[str] = []
    for item in (news or [])[:20]:
        title = item.get("title", "") or (item.get("content") or {}).get("title", "")
        if title and len(title) > 10:
            headlines.append(str(title))
    result: tuple[float | None, str] = (_score_headlines(headlines) if headlines
                                        else (None, "No news from yfinance"))
    with _news_lock:
        _news_cache[key] = (now, result)
    return result


def fetch_finviz_news(ticker: str, timeout: int = 8) -> tuple[float | None, str]:
    """Score Finviz headlines (fallback when yfinance news is empty); per-host breaker."""
    gate = breaker("finviz.com")
    if not gate.allow():
        return None, "Finviz breaker open"
    try:
        import urllib.request  # pylint: disable=import-outside-toplevel

        req = urllib.request.Request(f"https://finviz.com/quote.ashx?t={ticker}")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        req.add_header("Accept", "text/html,application/xhtml+xml")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:  # pylint: disable=broad-exception-caught
        gate.record_failure(classify_exception(e)[0])
        return None, f"Finviz HTTP error: {type(e).__name__}"
    gate.record_success()
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
        return None, "No Finviz headlines found"
    return _score_headlines(headlines)


# ── WSB hotlist TTL cache ─────────────────────────────────────────────
# One Reddit fetch per ~30 min, shared by the scanner and sentiment_6d.
_WSB_HOTLIST_CACHE: dict[str, Any] | None = None
_WSB_HOTLIST_CACHE_TIME: float = 0.0
_WSB_HOTLIST_CACHE_TTL: float = 1800.0  # 30 minutes


def fetch_wsb_hotlist(timeout: int = 8) -> dict[str, Any] | None:
    """WallStreetBets mentions from the Reddit public JSON (30-minute cache, per-host breaker)."""
    global _WSB_HOTLIST_CACHE, _WSB_HOTLIST_CACHE_TIME  # pylint: disable=global-statement

    now = time.time()
    if _WSB_HOTLIST_CACHE is not None and (now - _WSB_HOTLIST_CACHE_TIME) <= _WSB_HOTLIST_CACHE_TTL:
        return _WSB_HOTLIST_CACHE
    gate = breaker("reddit.com")
    if not gate.allow():
        return None
    try:
        import urllib.request  # pylint: disable=import-outside-toplevel

        req = urllib.request.Request("https://www.reddit.com/r/wallstreetbets/hot.json?limit=100")
        req.add_header("User-Agent", "trading-mcp/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:  # pylint: disable=broad-exception-caught
        gate.record_failure(classify_exception(e)[0])
        return None
    gate.record_success()

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
        text = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"
        score = post_data.get("score", 0)
        num_comments = post_data.get("num_comments", 0)
        wsb_word_hits = sum(1 for w in WSB_KEYWORDS if w.lower() in text.lower())
        found = set()
        for m in ticker_re.finditer(text):
            ticker_found = m.group(1) or m.group(2)
            if ticker_found and ticker_found.upper() not in stopwords:
                found.add(ticker_found.upper())
        for tick in found:
            weight = score / 100 + wsb_word_hits * 2 + num_comments / 5
            item = ticker_mentions.setdefault(tick, {"count": 0, "weight": 0.0, "wsb_keywords": 0})
            item["count"] += 1
            item["weight"] += weight
            item["wsb_keywords"] += wsb_word_hits

    if ticker_mentions:
        _WSB_HOTLIST_CACHE = ticker_mentions
        _WSB_HOTLIST_CACHE_TIME = now
        return ticker_mentions
    return None


def compute_social_sentiment(
    ticker: str, wsb_hotlist: dict[str, dict] | None
) -> tuple[float | None, str]:
    """Retail-attention score from the WSB hotlist (contrarian; see the module docstring)."""
    if wsb_hotlist is None:
        return None, "No WSB data"
    data = wsb_hotlist.get(ticker.upper())
    if data is None:
        return None, "Not in WSB hotlist"
    count = data.get("count", 0)
    wsb_kw = data.get("wsb_keywords", 0)
    weight = data.get("weight", 0.0)
    if count >= 5 or wsb_kw >= 5 or weight > 50:
        level, score = "high", 40.0
    elif count >= 3 or wsb_kw >= 3 or weight > 10:
        level, score = "medium", 45.0
    else:
        level, score = "low", 48.0
    return score, f"WSB attention {level}: mentions {count} | keywords {wsb_kw} | weight {weight:.1f} (contrarian)"
