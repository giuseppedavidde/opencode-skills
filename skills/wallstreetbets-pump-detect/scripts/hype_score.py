#!/usr/bin/env python3
"""Deterministic hype scoring for r/wallstreetbets pump detection (Phase 3).

Implements the 5-dimension hype score documented in `SKILL.md`:

    mention volume (25%), engagement (20%), sentiment polarity (15%),
    post authority (15%), squeeze setup (25%).

Whenever a dimension cannot be computed from real data (e.g. Reddit does not
expose `upvote_ratio`/flair, or market data for the squeeze setup is missing),
the dimension is marked *unavailable* and the remaining weights are
renormalized instead of injecting a misleading default. The report always
exposes which dimensions were available, so a score is never silently propped
up by fake data.

Squeeze-setup inputs (short interest %, borrow fee %, days to cover) are market
data: source them from the trading MCP / `market-data-fetch` skill and pass them
with `--squeeze-json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from pydantic import BaseModel, Field

import bladebro_client

WEIGHTS: dict[str, float] = {
    "mention_volume": 0.25,
    "engagement": 0.20,
    "sentiment_polarity": 0.15,
    "post_authority": 0.15,
    "squeeze_setup": 0.25,
}

BULLISH_WORDS = {
    "bullish", "moon", "tendies", "calls", "yolo", "squeeze", "breakout",
    "rocket", "long", "buy", "green", "pump", "rip", "higher", "fire",
    "explode", "surge", "rally", "bounce", "uptrend", "accumulation",
    "squeezing", "shortage", "undervalued", "load", "gamma",
}
BEARISH_WORDS = {
    "bearish", "rug", "dump", "baghold", "bagholder", "dead", "rugpull",
    "exit", "sell", "red", "crash", "tank", "dip", "collapse", "plunge",
    "downtrend", "manipulation", "dilution", "bankruptcy", "delist",
    "puts", "overvalued", "scam", "recession", "drill", "bag",
}
DD_FLAIRS = {"dd", "due diligence", "technical analysis", "thesis", "research"}
MEME_FLAIRS = {"meme", "shitpost", "yolo", "gain", "loss", "chart"}
WORD_PATTERN = re.compile(r"[a-z']{2,}")
TICKER_PATTERN_TEMPLATE = r"(?<![A-Za-z0-9])\$?{ticker}(?![A-Za-z0-9])"

SQUEEZE_FIELDS = ("short_interest_pct", "borrow_fee_pct", "days_to_cover")
SQUEEZE_ALIASES = {
    "short_interest": "short_interest_pct",
    "shortinterest": "short_interest_pct",
    "shortfloat": "short_interest_pct",
    "borrow_fee": "borrow_fee_pct",
    "borrowfee": "borrow_fee_pct",
    "fee": "borrow_fee_pct",
    "days_to_cover": "days_to_cover",
    "dtc": "days_to_cover",
}


class PostSignal(BaseModel):
    """Scoring signals extracted from a single post mentioning a ticker."""

    score: int = 0
    comments: int = 0
    upvote_ratio: float | None = None
    flair: str | None = None
    sentiment: float | None = None


class SqueezeMetrics(BaseModel):
    """Market-data inputs for the Squeeze Setup dimension (all optional)."""

    short_interest_pct: float | None = None
    borrow_fee_pct: float | None = None
    days_to_cover: float | None = None
    source: str = ""

    def has_any(self) -> bool:
        """Return True when at least one market metric is present."""
        return any(getattr(self, field) is not None for field in SQUEEZE_FIELDS)


class DimensionScore(BaseModel):
    """A single hype dimension result, available or explicitly not."""

    name: str
    weight: float
    available: bool
    score: float | None = None
    detail: str = ""


class HypeScore(BaseModel):
    """Aggregated hype score with renormalized weights over real dimensions."""

    ticker: str = ""
    mention_count: int = 0
    total_score: float = 0.0
    coverage: float = 0.0
    dimensions: list[DimensionScore] = Field(default_factory=list)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    unavailable: list[str] = Field(default_factory=list)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value into the inclusive [low, high] range."""
    return max(low, min(high, value))


def text_sentiment(text: str) -> float | None:
    """Return a 0-1 sentiment score for a text, or None when no term matches."""
    words = set(WORD_PATTERN.findall((text or "").lower()))
    bull = len(words & BULLISH_WORDS)
    bear = len(words & BEARISH_WORDS)
    total = bull + bear
    if total == 0:
        return None
    return bull / total


def _matches_ticker(text: str, ticker: str) -> bool:
    """Return True when the text mentions the ticker as a standalone token."""
    pattern = TICKER_PATTERN_TEMPLATE.format(ticker=re.escape(ticker.upper()))
    return bool(re.search(pattern, text or "", re.IGNORECASE))


def build_posts(
    children: list[dict[str, Any]], ticker: str
) -> list[PostSignal]:
    """Build scoring signals from the children mentioning `ticker`."""
    posts: list[PostSignal] = []
    for child in children:
        data = child.get("data", child)
        text = f"{data.get('title', '')} {data.get('selftext', '')}"
        if not _matches_ticker(text, ticker):
            continue
        flair = data.get("link_flair_text") or data.get("flair") or None
        posts.append(
            PostSignal(
                score=bladebro_client.as_int(data.get("score")),
                comments=bladebro_client.as_int(
                    data.get("num_comments", data.get("comments"))
                ),
                upvote_ratio=bladebro_client.as_float(data.get("upvote_ratio")),
                flair=str(flair) if flair else None,
                sentiment=text_sentiment(text),
            )
        )
    return posts


def _mention_volume(posts: list[PostSignal]) -> DimensionScore:
    """Dimension 1: post volume plus total comment pressure."""
    n_posts = len(posts)
    n_comments = sum(post.comments for post in posts)
    score = _clamp(n_posts * 10 + n_comments / 20)
    return DimensionScore(
        name="mention_volume",
        weight=WEIGHTS["mention_volume"],
        available=bool(posts),
        score=round(score, 2) if posts else None,
        detail=f"{n_posts} posts, {n_comments} comments",
    )


def _engagement(posts: list[PostSignal]) -> DimensionScore:
    """Dimension 2: average upvote ratio and score (needs upvote_ratio)."""
    ratios = [post.upvote_ratio for post in posts if post.upvote_ratio is not None]
    if not ratios:
        return DimensionScore(
            name="engagement",
            weight=WEIGHTS["engagement"],
            available=False,
            detail="upvote_ratio unavailable from source",
        )
    avg_ratio = sum(ratios) / len(ratios)
    avg_score = sum(post.score for post in posts) / len(posts)
    score = _clamp(avg_ratio * 80 + min(avg_score / 10, 20))
    return DimensionScore(
        name="engagement",
        weight=WEIGHTS["engagement"],
        available=True,
        score=round(score, 2),
        detail=f"avg_ratio={avg_ratio:.2f} over {len(ratios)}/{len(posts)} posts",
    )


def _sentiment_polarity(posts: list[PostSignal]) -> DimensionScore:
    """Dimension 3: bullish vs bearish ratio over the real post text."""
    scores = [post.sentiment for post in posts if post.sentiment is not None]
    if not scores:
        return DimensionScore(
            name="sentiment_polarity",
            weight=WEIGHTS["sentiment_polarity"],
            available=False,
            detail="no lexicon term matched in post text",
        )
    bull = sum(1 for value in scores if value > 0.5)
    bear = sum(1 for value in scores if value < 0.5)
    total = len(scores)
    score = _clamp((bull / total - bear / total + 1) * 50)
    return DimensionScore(
        name="sentiment_polarity",
        weight=WEIGHTS["sentiment_polarity"],
        available=True,
        score=round(score, 2),
        detail=f"{bull} bullish / {bear} bearish of {total} texts",
    )


def _post_authority(posts: list[PostSignal]) -> DimensionScore:
    """Dimension 4: DD/Technical flair ratio vs meme flair ratio."""
    flairs = [post.flair.strip().lower() for post in posts if post.flair]
    if not flairs:
        return DimensionScore(
            name="post_authority",
            weight=WEIGHTS["post_authority"],
            available=False,
            detail="link_flair_text unavailable from source",
        )
    total = len(flairs)
    dd_ratio = sum(1 for flair in flairs if flair in DD_FLAIRS) / total
    meme_ratio = sum(1 for flair in flairs if flair in MEME_FLAIRS) / total
    score = _clamp(dd_ratio * 60 + (1 - meme_ratio) * 40)
    return DimensionScore(
        name="post_authority",
        weight=WEIGHTS["post_authority"],
        available=True,
        score=round(score, 2),
        detail=f"dd_ratio={dd_ratio:.2f}, meme_ratio={meme_ratio:.2f} over {total}",
    )


def _squeeze_setup(squeeze: SqueezeMetrics | None) -> DimensionScore:
    """Dimension 5: short interest, borrow fee and days to cover (market data)."""
    if squeeze is None or not squeeze.has_any():
        return DimensionScore(
            name="squeeze_setup",
            weight=WEIGHTS["squeeze_setup"],
            available=False,
            detail="no market data (short interest / borrow fee / days to cover)",
        )
    components: list[tuple[float, float]] = []
    if squeeze.short_interest_pct is not None:
        components.append((min(squeeze.short_interest_pct * 2, 50), 50))
    if squeeze.borrow_fee_pct is not None:
        components.append((min(squeeze.borrow_fee_pct * 10, 30), 30))
    if squeeze.days_to_cover is not None:
        components.append((min(squeeze.days_to_cover * 5, 20), 20))
    gained = sum(value for value, _ in components)
    possible = sum(limit for _, limit in components)
    score = _clamp(gained / possible * 100) if possible else 0.0
    detail = ", ".join(
        f"{field}={getattr(squeeze, field)}" for field in SQUEEZE_FIELDS
        if getattr(squeeze, field) is not None
    )
    return DimensionScore(
        name="squeeze_setup",
        weight=WEIGHTS["squeeze_setup"],
        available=True,
        score=round(score, 2),
        detail=(detail + (f" [{squeeze.source}]" if squeeze.source else "")),
    )


def compute_hype_score(
    posts: list[PostSignal],
    squeeze: SqueezeMetrics | None = None,
    ticker: str = "",
) -> HypeScore:
    """Compute the 5-dimension hype score, renormalizing unavailable weights."""
    dimensions = [
        _mention_volume(posts),
        _engagement(posts),
        _sentiment_polarity(posts),
        _post_authority(posts),
        _squeeze_setup(squeeze),
    ]
    active = [dim for dim in dimensions if dim.available and dim.score is not None]
    total_weight = sum(dim.weight for dim in active)
    if total_weight <= 0:
        return HypeScore(
            ticker=ticker,
            mention_count=len(posts),
            total_score=0.0,
            coverage=0.0,
            dimensions=dimensions,
            effective_weights={},
            unavailable=[dim.name for dim in dimensions],
        )
    weighted = sum(dim.score * dim.weight for dim in active) / total_weight
    return HypeScore(
        ticker=ticker,
        mention_count=len(posts),
        total_score=round(weighted, 2),
        coverage=round(total_weight, 2),
        dimensions=dimensions,
        effective_weights={
            dim.name: round(dim.weight / total_weight, 4) for dim in active
        },
        unavailable=[dim.name for dim in dimensions if not dim.available],
    )


def parse_squeeze(raw: str | None) -> SqueezeMetrics | None:
    """Parse a squeeze JSON string (or `@file`) into `SqueezeMetrics`."""
    if not raw:
        return None
    text = raw
    if raw.startswith("@"):
        with open(raw[1:], "r", encoding="utf-8") as handle:
            text = handle.read()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid --squeeze-json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("--squeeze-json must be a JSON object")
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = str(key).strip().lower()
        canonical = (
            key_lower
            if key_lower in SQUEEZE_FIELDS
            else SQUEEZE_ALIASES.get(key_lower)
        )
        if canonical:
            normalized[canonical] = value
    return SqueezeMetrics(**normalized)


def _load_children(feed_json: str) -> list[dict[str, Any]]:
    """Load Reddit children from a feed JSON file (children or item list)."""
    with open(feed_json, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        if "items" in payload:
            payload = payload["items"]
        elif "children" in payload:
            payload = payload["children"]
    if not isinstance(payload, list):
        raise ValueError("feed JSON must be a list or an object with items/children")
    children: list[dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, dict) and "data" in entry and "kind" in entry:
            children.append(entry)
        elif isinstance(entry, dict):
            children.append(bladebro_client.RedditFeedItem.model_validate(entry).to_reddit_child())
    return children


def _format_report(result: HypeScore) -> str:
    """Render a human-readable hype score report."""
    lines = [
        f"Hype Score for ${result.ticker}: {result.total_score}/100",
        f"  Mentioning posts: {result.mention_count}",
        f"  Weight coverage:  {result.coverage * 100:.0f}%"
        + (f"  (missing: {', '.join(result.unavailable)})" if result.unavailable else ""),
        "",
        f"  {'Dimension':<20} {'Weight':>7} {'Score':>7}  Status",
    ]
    for dim in result.dimensions:
        weight = f"{dim.weight:.2f}"
        if dim.available and dim.score is not None:
            status = dim.detail
            score = f"{dim.score:.1f}"
        else:
            status = f"UNAVAILABLE ({dim.detail})"
            score = "-"
        lines.append(f"  {dim.name:<20} {weight:>7} {score:>7}  {status}")
    lines.append("")
    lines.append("  Effective weights (renormalized over available dimensions):")
    for name, weight in result.effective_weights.items():
        lines.append(f"    {name:<20} {weight:.4f}")
    return "\n".join(lines)


def main() -> None:
    """Parse arguments and print the hype score for a ticker."""
    parser = argparse.ArgumentParser(
        description="Compute the Phase 3 hype score for a WSB ticker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 hype_score.py --ticker GME --target 100
  python3 hype_score.py --ticker GME --feed-json feed.json \\
    --squeeze-json '{"short_interest_pct": 25.1, "borrow_fee_pct": 18.3, "days_to_cover": 2.4}'
        """,
    )
    parser.add_argument("--ticker", "-t", required=True,
                        help="Stock ticker symbol (e.g., GME)")
    parser.add_argument("--subreddit", "-s", default="wallstreetbets")
    parser.add_argument("--listing", "-l", default="hot",
                        choices=["hot", "new", "top", "rising"])
    parser.add_argument("--target", "-n", type=int, default=bladebro_client.DEFAULT_TARGET,
                        help="Target post count to collect (default: 100)")
    parser.add_argument("--feed-json", default=None,
                        help="Use a saved feed JSON instead of fetching")
    parser.add_argument("--squeeze-json", default=None,
                        help="Market data JSON (or @file) for the squeeze dimension")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose fetch progress")
    args = parser.parse_args()

    squeeze = parse_squeeze(args.squeeze_json)
    if args.feed_json:
        children = _load_children(args.feed_json)
    else:
        try:
            children, source = bladebro_client.collect_reddit_children(
                f"https://www.reddit.com/r/{args.subreddit}/hot.json?limit={args.target}",
                bladebro_client.REDDIT_USER_AGENT,
                verbose=args.verbose,
                target=args.target,
            )
        except bladebro_client.CollectError as exc:
            print(f"fetch failed: {exc}", file=sys.stderr)
            sys.exit(2)
        if args.verbose:
            print(f"  source={source}", file=sys.stderr)
    posts = build_posts(children, args.ticker)
    result = compute_hype_score(posts, squeeze=squeeze, ticker=args.ticker.upper())
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        print(_format_report(result))


if __name__ == "__main__":
    main()
