#!/usr/bin/env python3
"""Fetch social sentiment for a ticker from multiple platforms and compute a weighted score."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import requests
from pydantic import BaseModel


REDDIT_USER_AGENT = "wsb-pump-detect/1.0 (sentiment analysis bot)"

BULLISH_PATTERNS = [
    r"\b(bullish|moon|tendies|calls|yolo|squeeze|breakout|rocket|long|buy|green|pump|rip higher)\b",
    r"🚀|📈|💎|🙌|🔥|💪",
]

BEARISH_PATTERNS = [
    r"\b(bearish|rug|dump|baghold|short|dead|rugpull|exit|sell|red|crash|tank|dip)\b",
    r"📉|💩|🤡|🐻|🔻",
]

STOCKTWITS_API_URL = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"

REDDIT_SUBREDDITS = {
    "wallstreetbets": {"weight": 0.35, "endpoint": "r/wallstreetbets/hot.json?limit=100"},
    "investing": {"weight": 0.15, "endpoint": "r/investing/hot.json?limit=100"},
    "stocks": {"weight": 0.15, "endpoint": "r/stocks/hot.json?limit=100"},
}

STOCKTWITS_WEIGHT = 0.20
TWITTER_WEIGHT = 0.15


class SourceResult(BaseModel):  # pylint: disable=too-many-instance-attributes
    """Result from a single sentiment source."""

    source: str
    weight: float
    mentions: int = 0
    total_posts: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    sentiment: float = 0.0
    raw_score: int = 50
    available: bool = False
    error: str | None = None


class SentimentReport(BaseModel):
    """Full sentiment analysis report."""

    ticker: str
    score: int = 50
    sources: list[SourceResult] = []
    base_score: int = 50


def _compile_patterns() -> tuple[list[re.Pattern], list[re.Pattern]]:
    """Compile bullish and bearish regex patterns."""
    bullish = [re.compile(p, re.IGNORECASE) for p in BULLISH_PATTERNS]
    bearish = [re.compile(p, re.IGNORECASE) for p in BEARISH_PATTERNS]
    return bullish, bearish


def _classify_text(
    text: str, bullish_patterns: list[re.Pattern], bearish_patterns: list[re.Pattern]
) -> int:
    """Classify text as 1 (bullish), -1 (bearish), or 0 (neutral)."""
    if not text:
        return 0
    bull_matches = sum(1 for pat in bullish_patterns if pat.search(text))
    bear_matches = sum(1 for pat in bearish_patterns if pat.search(text))
    if bull_matches > bear_matches:
        return 1
    if bear_matches > bull_matches:
        return -1
    return 0


def _fetch_reddit(subreddit: str, endpoint: str, ticker: str, verbose: bool) -> SourceResult:  # pylint: disable=too-many-locals
    """Fetch sentiment from a Reddit subreddit."""
    url = f"https://www.reddit.com/{endpoint}"
    headers = {"User-Agent": REDDIT_USER_AGENT}
    weight = REDDIT_SUBREDDITS[subreddit]["weight"]
    result = SourceResult(source=f"Reddit r/{subreddit}", weight=weight)

    try:
        if verbose:
            print(f"  Fetching {url} ...", file=sys.stderr)
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        result.error = str(exc)
        if verbose:
            print(f"  [SKIP] Reddit r/{subreddit}: {exc}", file=sys.stderr)
        return result

    children = data.get("data", {}).get("children", [])
    result.total_posts = len(children)
    bullish_patterns, bearish_patterns = _compile_patterns()
    ticker_pattern_lower = ticker.lower()

    for child in children:
        post_data = child.get("data", {})
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        combined = f"{title} {selftext}"
        if ticker_pattern_lower not in combined.lower():
            # Also check for $TICKER pattern
            dollar_ticker = f"${ticker}"
            if dollar_ticker.lower() not in combined.lower():
                continue
        result.mentions += 1
        classification = _classify_text(combined, bullish_patterns, bearish_patterns)
        if classification == 1:
            result.bullish_count += 1
        elif classification == -1:
            result.bearish_count += 1

    if result.mentions > 0:
        result.sentiment = (result.bullish_count - result.bearish_count) / result.mentions
        # Scale to 0-100 with base 50
        result.raw_score = int(50 + result.sentiment * 50)
        result.available = True

    if verbose:
        print(
            f"  Reddit r/{subreddit}: {result.mentions} mentions, "
            f"{result.bullish_count}B/{result.bearish_count}Be, "
            f"sentiment={result.sentiment:.2f}",
            file=sys.stderr,
        )
    return result


def _fetch_stocktwits(ticker: str, verbose: bool) -> SourceResult:  # pylint: disable=too-many-locals,too-many-branches
    """Fetch sentiment from Stocktwits API."""
    url = STOCKTWITS_API_URL.format(ticker=ticker.upper())
    result = SourceResult(source="Stocktwits", weight=STOCKTWITS_WEIGHT)

    try:
        if verbose:
            print(f"  Fetching {url} ...", file=sys.stderr)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        result.error = str(exc)
        if verbose:
            print(f"  [SKIP] Stocktwits: {exc}", file=sys.stderr)
        return result

    messages = data.get("messages", [])
    result.total_posts = len(messages)
    ticker_upper = ticker.upper()

    for msg in messages:
        body = msg.get("body", "")
        if ticker_upper in body.upper():
            result.mentions += 1
            # Stocktwits may have sentiment from entities
            entities = msg.get("entities", {}).get("sentiment", {})
            if entities.get("basic") == "Bullish":
                result.bullish_count += 1
            elif entities.get("basic") == "Bearish":
                result.bearish_count += 1
            else:
                bullish_patterns, bearish_patterns = _compile_patterns()
                classification = _classify_text(body, bullish_patterns, bearish_patterns)
                if classification == 1:
                    result.bullish_count += 1
                elif classification == -1:
                    result.bearish_count += 1

    if result.mentions > 0:
        total_sentiment_posts = result.bullish_count + result.bearish_count
        if total_sentiment_posts > 0:
            result.sentiment = (result.bullish_count - result.bearish_count) / total_sentiment_posts
        result.raw_score = int(50 + result.sentiment * 50)
        result.available = True

    if verbose:
        print(
            f"  Stocktwits: {result.mentions} mentions, "
            f"{result.bullish_count}B/{result.bearish_count}Be, "
            f"sentiment={result.sentiment:.2f}",
            file=sys.stderr,
        )
    return result


def _twitter_instruction(_ticker: str) -> SourceResult:
    """Return placeholder for X/Twitter sentiment (requires manual websearch)."""
    result = SourceResult(source="X/Twitter", weight=TWITTER_WEIGHT)
    result.available = True
    result.mentions = "*"
    result.sentiment = 0.0
    result.raw_score = 50
    return result


def _normalize_score(sources: list[SourceResult]) -> SentimentReport:
    """Compute weighted score normalized by available sources."""
    available = [s for s in sources if s.available]
    if not available:
        return SentimentReport(ticker="UNKNOWN", score=50, sources=sources)

    total_weight = sum(s.weight for s in available)
    if total_weight == 0:
        return SentimentReport(ticker="UNKNOWN", score=50, sources=sources)

    weighted_score = sum(s.raw_score * s.weight for s in available) / total_weight
    return SentimentReport(
        ticker=available[0].source.split()[-1] if available else "UNKNOWN",
        score=int(round(weighted_score)),
        sources=sources,
    )


def analyze_ticker(ticker: str, verbose: bool = False) -> SentimentReport:
    """Run full multi-platform sentiment analysis for a ticker."""
    ticker = ticker.upper().strip()
    if verbose:
        print(f"Analyzing sentiment for ${ticker} across multiple platforms...", file=sys.stderr)

    sources: list[SourceResult] = []

    # 1. Reddit sources
    for subreddit, config in REDDIT_SUBREDDITS.items():
        result = _fetch_reddit(subreddit, config["endpoint"], ticker, verbose)
        sources.append(result)
        time.sleep(1)

    # 2. Stocktwits
    stocktwits_result = _fetch_stocktwits(ticker, verbose)
    sources.append(stocktwits_result)
    time.sleep(1)

    # 3. X/Twitter instruction
    twitter_result = _twitter_instruction(ticker)
    sources.append(twitter_result)
    if verbose:
        print(
            f'  X/Twitter: use websearch for "${ticker} stock" to gauge sentiment manually',
            file=sys.stderr,
        )

    report = _normalize_score(sources)
    report.ticker = ticker
    return report


def _format_output(report: SentimentReport) -> str:
    """Format sentiment report as human-readable text."""
    lines = [
        f"Multi-Platform Sentiment Report for ${report.ticker}",
        f"{'=' * 55}",
        f"Weighted Sentiment Score: {report.score}/100  (base=50, >50 bullish, <50 bearish)",
        "",
        f"{'Source':<22} {'Weight':>6} {'Mentions':>8} {'Sentiment':>10} {'Score':>6} {'Status'}",
        f"{'-' * 22} {'-' * 6} {'-' * 8} {'-' * 10} {'-' * 6} {'-' * 12}",
    ]

    for src in report.sources:
        if src.available:
            status = "OK"
        elif src.error:
            status = f"SKIP ({src.error})"
        else:
            status = "SKIP"
        mentions = str(src.mentions) if src.mentions != "*" else src.mentions
        sentiment_str = f"{src.sentiment:+.2f}" if src.available else "N/A"
        score_str = str(src.raw_score) if src.available else "N/A"
        row = (
            f"{src.source:<22} {src.weight:>6.2f} "
            f"{mentions:>8} {sentiment_str:>10} {score_str:>6} {status}"
        )
        lines.append(row)

    lines.extend([
        "",
        "Interpretation:",
        "  Score > 70: Strong bullish sentiment, potential pump candidate",
        "  Score 50-70: Mildly bullish, monitor closely",
        "  Score 30-50: Mildly bearish or neutral",
        "  Score < 30: Strong bearish sentiment, avoid or contrarian play",
    ])

    return "\n".join(lines)


def main() -> None:
    """Parse arguments and run sentiment analysis."""
    parser = argparse.ArgumentParser(
        description="Multi-platform social sentiment analysis for stocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 multi_platform_sentiment.py --ticker GME
  python3 multi_platform_sentiment.py --ticker GME --json
  python3 multi_platform_sentiment.py --ticker GME --verbose
        """,
    )
    parser.add_argument("--ticker", "-t", required=True, help="Stock ticker symbol (e.g., GME)")
    parser.add_argument("--json", "-j", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed fetch progress")
    args = parser.parse_args()

    report = analyze_ticker(args.ticker, verbose=args.verbose)

    if args.json:
        output = report.model_dump(mode="json")
        # Convert SourceResult error to string for JSON serialization
        for src in output.get("sources", []):
            if "error" in src and src["error"] is None:
                del src["error"]
        print(json.dumps(output, indent=2, default=str))
    else:
        print(_format_output(report))


if __name__ == "__main__":
    main()
