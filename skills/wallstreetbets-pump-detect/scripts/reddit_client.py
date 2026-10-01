#!/usr/bin/env python3
"""Reddit public-JSON client for fetching r/wallstreetbets content.

Fetches Reddit listings through the public `.json` endpoint over plain HTTP
(`urllib.request`), parses `data.children[]` into Pydantic models, and exposes
the helpers used by the skill scripts (`collect_reddit_children`,
`count_ticker_mentions`). No browser, daemon or external CLI is required.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_LIMIT = 100
DEFAULT_TARGET = 100
REDDIT_ROOT = "https://www.reddit.com"
REDDIT_USER_AGENT = "wsb-pump-detect/1.0 (reddit json client)"

__all__ = [
    "CollectError",
    "RedditFeedItem",
    "RedditFeed",
    "as_int",
    "as_float",
    "fetch_reddit_json_children",
    "fetch_feed",
    "fetch_feed_bulk",
    "collect_reddit_children",
    "count_ticker_mentions",
    "DEFAULT_TARGET",
    "REDDIT_USER_AGENT",
]


class CollectError(RuntimeError):
    """Raised when the Reddit public JSON endpoint cannot return a listing."""


def _parse_date_to_epoch(raw: str) -> float:
    """Parse a Reddit date string into a UNIX epoch (UTC); 0.0 when unknown."""
    text = (raw or "").strip()
    if not text:
        return 0.0
    if text.upper().endswith("UTC"):
        text = text[:-3].strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _epoch_to_date(value: Any) -> str:
    """Render a Reddit `created_utc` epoch as a `YYYY-MM-DD HH:MM` date string."""
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return ""
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def as_float(value: Any) -> float | None:
    """Coerce a value to float, returning None when it is missing or invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int:
    """Coerce a value to int, returning 0 when it is missing or invalid."""
    number = as_float(value)
    return int(number) if number is not None else 0


def _reddit_permalink(data: dict[str, Any]) -> str:
    """Build an absolute Reddit permalink from a child `data` mapping."""
    permalink = str(data.get("permalink") or "")
    if permalink.startswith("http"):
        return permalink
    if permalink.startswith("/"):
        return f"{REDDIT_ROOT}{permalink}"
    return str(data.get("url") or "")


class RedditFeedItem(BaseModel):
    """A single post entry from a Reddit listing."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    author: str = ""
    score: int = 0
    comments: int = 0
    date: str = ""
    subreddit: str = ""
    domain: str = ""
    url: str = ""
    content_href: str = ""
    type: str = ""
    id: str = ""
    upvote_ratio: float | None = None
    flair: str | None = None

    def created_utc(self) -> float:
        """Return the post timestamp as a UNIX epoch (seconds, UTC)."""
        return _parse_date_to_epoch(self.date)

    def dedupe_key(self) -> str:
        """Return a stable identity key used to de-duplicate accumulated posts."""
        return (
            self.id
            or self.content_href
            or self.url
            or f"{self.author}:{self.title}"
        )

    @classmethod
    def from_reddit_data(cls, data: dict[str, Any]) -> "RedditFeedItem":
        """Build a feed item from a Reddit `data.children[].data` mapping."""
        return cls(
            title=str(data.get("title") or ""),
            author=str(data.get("author") or ""),
            score=as_int(data.get("score")),
            comments=as_int(data.get("num_comments")),
            date=_epoch_to_date(data.get("created_utc")),
            subreddit=str(data.get("subreddit") or ""),
            domain=str(data.get("domain") or ""),
            url=str(data.get("url") or ""),
            content_href=_reddit_permalink(data),
            id=str(data.get("id") or ""),
            upvote_ratio=as_float(data.get("upvote_ratio")),
            flair=data.get("link_flair_text") or None,
        )

    def to_reddit_child(self) -> dict[str, Any]:
        """Represent this item in Reddit's `data.children` JSON shape."""
        return {
            "kind": "t3",
            "data": {
                "id": self.id,
                "title": self.title,
                "selftext": "",
                "author": self.author,
                "score": self.score,
                "upvote_ratio": self.upvote_ratio,
                "num_comments": self.comments,
                "created_utc": self.created_utc(),
                "link_flair_text": self.flair,
                "permalink": self.content_href or self.url,
                "url": self.url or self.content_href,
                "subreddit": self.subreddit.removeprefix("r/"),
                "domain": self.domain,
                "date": self.date,
            },
        }


class RedditFeed(BaseModel):
    """Reddit listing (feed) payload."""

    model_config = ConfigDict(extra="ignore")

    container: str = ""
    count: int = 0
    items: list[RedditFeedItem] = Field(default_factory=list)

    def to_reddit_children(self) -> list[dict[str, Any]]:
        """Convert the feed into Reddit's `data.children` entries."""
        return [item.to_reddit_child() for item in self.items]

    def dedupe(self) -> "RedditFeed":
        """Return a copy of the feed with duplicate posts removed, order kept."""
        seen: set[str] = set()
        unique: list[RedditFeedItem] = []
        for item in self.items:
            key = item.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return RedditFeed(container=self.container, count=len(unique), items=unique)


def _page_to_json(url: str, limit: int = DEFAULT_LIMIT) -> str:
    """Convert a Reddit listing page URL into its `.json` endpoint URL."""
    path = url.split("?", 1)[0]
    if not path.endswith(".json"):
        path = path.rstrip("/") + ".json"
    return f"{path}?limit={limit}"


def _dedupe_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-duplicate Reddit children by post id/permalink/url, preserving order."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for child in children:
        data = child.get("data", {})
        key = str(
            data.get("id")
            or data.get("permalink")
            or data.get("url")
            or f"{data.get('author')}:{data.get('title')}"
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(child)
    return unique


def fetch_reddit_json_children(
    url: str,
    user_agent: str = REDDIT_USER_AGENT,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Fetch a Reddit listing through the public JSON endpoint (urllib).

    Raises `CollectError` on HTTP errors (including 403/429 rate limits) or on
    malformed payloads, so callers never mistake a failure for an empty feed.
    """
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise CollectError(f"reddit-json HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        raise CollectError(f"reddit-json request failed for {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise CollectError(f"reddit-json: unexpected payload shape for {url}")
    children = data.get("data", {}).get("children", [])
    return [child for child in children if isinstance(child, dict)]


def _feed_from_children(
    children: list[dict[str, Any]], container: str = "reddit-feed"
) -> RedditFeed:
    """Build a `RedditFeed` from Reddit-JSON-shaped children."""
    items = [
        RedditFeedItem.from_reddit_data(child.get("data", {}))
        for child in children
    ]
    return RedditFeed(container=container, count=len(items), items=items).dedupe()


def fetch_feed_bulk(
    subreddit: str = "wallstreetbets",
    listing: str = "hot",
    target: int = DEFAULT_TARGET,
) -> RedditFeed:
    """Fetch a full subreddit listing through the Reddit public JSON endpoint."""
    sub = subreddit.strip("/").removeprefix("r/")
    json_url = f"{REDDIT_ROOT}/r/{sub}/{listing}.json?limit={target}"
    children, _source = collect_reddit_children(
        json_url, REDDIT_USER_AGENT, target=target
    )
    return _feed_from_children(children[:target])


def fetch_feed(
    subreddit: str = "wallstreetbets",
    listing: str = "hot",
    limit: int = DEFAULT_LIMIT,
    target: int | None = None,
) -> RedditFeed:
    """Fetch a subreddit listing (`hot`, `new`, `top`, `rising`)."""
    return fetch_feed_bulk(subreddit, listing, target=target or limit)


def collect_reddit_children(
    url: str,
    user_agent: str = REDDIT_USER_AGENT,
    verbose: bool = False,
    limit: int = DEFAULT_LIMIT,
    target: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Collect Reddit listing children through the public JSON endpoint.

    Returns the Reddit-JSON-shaped children list and the source string
    (`"reddit_json"`). Raises `CollectError` when the endpoint is blocked or
    returns nothing, so callers never treat a failure as an empty dataset.
    """
    want = target or limit
    json_url = url if url.endswith(".json") else _page_to_json(url, want)
    children = fetch_reddit_json_children(json_url, user_agent)
    if not children:
        raise CollectError(f"reddit-json: empty listing from {json_url}")
    children = _dedupe_children(children)
    if verbose:
        print(f"  [reddit-json] {len(children)} posts from {json_url}", file=sys.stderr)
    return children[:want], "reddit_json"


def count_ticker_mentions(children: list[dict[str, Any]], ticker: str) -> int:
    """Count case-insensitive `$TICKER` word occurrences across the given posts."""
    pattern = re.compile(rf"\$?{re.escape(ticker)}\b", re.IGNORECASE)
    count = 0
    for child in children:
        data = child.get("data", {})
        text = f"{data.get('title', '')} {data.get('selftext', '')}"
        count += len(pattern.findall(text))
    return count


def _demo(target: int = DEFAULT_TARGET) -> None:
    """Print a quick feed summary when run as a script."""
    feed = fetch_feed("wallstreetbets", "hot", target=target)
    print(f"feed container={feed.container} count={feed.count} items={len(feed.items)}")
    for item in feed.items[:5]:
        ratio = f"{item.upvote_ratio:.2f}" if item.upvote_ratio is not None else "n/a"
        print(f"  [{item.score:>5}] ratio={ratio} flair={item.flair!r} {item.title[:60]}")


def main() -> None:
    """Parse arguments and run the feed client (useful for manual checks)."""
    parser = argparse.ArgumentParser(
        description="Fetch r/wallstreetbets listings via the Reddit public JSON endpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 reddit_client.py --subreddit wallstreetbets --listing hot --target 100
  python3 reddit_client.py --target 50 --json
        """,
    )
    parser.add_argument("--subreddit", "-s", default="wallstreetbets")
    parser.add_argument("--listing", "-l", default="hot",
                        choices=["hot", "new", "top", "rising"])
    parser.add_argument("--target", "-t", type=int, default=DEFAULT_TARGET,
                        help=f"Target post count (default: {DEFAULT_TARGET})")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output the feed as JSON")
    parser.add_argument("--demo", action="store_true",
                        help="Run the legacy feed/thread demo")
    args = parser.parse_args()

    if args.demo:
        _demo(args.target)
        return

    feed = fetch_feed_bulk(args.subreddit, args.listing, target=args.target)
    if args.json:
        print(json.dumps(feed.model_dump(mode="json"), indent=2, default=str))
        return
    print(f"{feed.count} posts from r/{args.subreddit}/{args.listing}")
    ratios = [i.upvote_ratio for i in feed.items if i.upvote_ratio is not None]
    flairs = [i.flair for i in feed.items if i.flair]
    print(f"  upvote_ratio available: {len(ratios)}/{feed.count}")
    print(f"  flair available:        {len(flairs)}/{feed.count}")
    for item in feed.items[:10]:
        ratio = f"{item.upvote_ratio:.2f}" if item.upvote_ratio is not None else "n/a"
        print(f"  [{item.score:>5}] ratio={ratio} flair={item.flair!r} {item.title[:55]}")


if __name__ == "__main__":
    main()
