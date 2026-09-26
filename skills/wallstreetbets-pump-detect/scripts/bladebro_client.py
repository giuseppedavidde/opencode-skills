#!/usr/bin/env python3
"""Bladebro stealth-browser client for fetching r/wallstreetbets content.

Renders Reddit through the `bladebro` CLI (a real Chrome), parses the
`extract auto` / `act collect` / `act eval` payloads into Pydantic models, and
falls back to Reddit's public JSON endpoint when the browser path is blocked.

Reddit frequently serves a rate-limit/block interstitial and lazy-renders its
feeds (a single `see extract auto` yields only ~4 posts). This client therefore:
  * fetches the listing `.json` through the browser, which returns the full
    listing plus `upvote_ratio` and `link_flair_text`;
  * paginates via `act collect` / eased `act scroll` when only the rendered
    page is available;
  * detects block/challenge interstitials and retries with bounded backoff,
    raising a typed error instead of returning a silently empty dataset.
"""

# pylint: disable=too-many-lines,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-branches

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_BLADEBRO_BIN = os.path.expanduser(
    "~/.local/share/opencode/bladebro-node/bin/bladebro"
)
DEFAULT_CHROME_PATH = os.path.expanduser(
    "~/.local/share/opencode/bladebro-node/chrome"
)
DEFAULT_BLADE_HOME = "/tmp/opencode/wsb-blade"

EXTRACT_MARKER = "extract auto:"
COLLECT_MARKER = "collected"
ARTIFACT_PATTERN = re.compile(
    r"\((\d+)\s*bytes\)\s*(?:→|->)\s*(\S+?\.json)", re.IGNORECASE
)
TRUNCATION_MARKER_PATTERN = re.compile(r"…\s*\(\d+\s+more:[^)]*\)")
DIRECTIVE_PATTERN = re.compile(r"^\s*read the file for the full data\s*$", re.IGNORECASE)
BLOCK_TEXT_PATTERN = re.compile(
    r"rate[ _-]?limit|you'?ve been blocked|whoa there|too many requests|"
    r"verifying you are human|are you a robot|blocked by network security|"
    r"access denied|error\s*429|429\s*too many|please wait while we",
    re.IGNORECASE,
)
BLOCK_URL_PATTERN = re.compile(
    r"/(rate[-_]?limit|blocked|challenge|captcha)(/|$|\?)", re.IGNORECASE
)
LISTING_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?reddit\.com/r/[^/]+/(?:hot|new|top|rising)/?$",
    re.IGNORECASE,
)

RECOVERY_ATTEMPTS = 200
DEFAULT_TIMEOUT_SECONDS = 90
CHALLENGE_RETRIES = 2
BLOCK_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 30.0
SETTLE_MILLISECONDS = "3000"
REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_LIMIT = 100
DEFAULT_TARGET = 100
SCROLL_DELTA = "1400"
SCROLL_MAX_IDLE = 3
LISTING_ROTATION = ("hot", "new", "top")
FEED_DOMAINS = {"www.reddit.com", "reddit.com"}
REDDIT_ROOT = "https://www.reddit.com"

__all__ = [
    "BladebroError",
    "BladebroBlockedError",
    "CollectError",
    "RedditFeedItem",
    "RedditFeed",
    "RedditPost",
    "RedditComment",
    "RedditCommentThread",
    "find_bladebro_bin",
    "blade_home",
    "run_bladebro",
    "is_blocked_text",
    "as_int",
    "as_float",
    "parse_extract_output",
    "fetch_feed",
    "fetch_feed_url",
    "fetch_feed_bulk",
    "fetch_comment_thread",
    "collect_reddit_children",
    "count_ticker_mentions",
]


class BladebroError(RuntimeError):
    """Raised when a bladebro invocation fails or returns unparsable output."""


class CollectError(RuntimeError):
    """Raised when both bladebro and the Reddit JSON fallback fail."""


class BladebroBlockedError(BladebroError, CollectError):
    """Raised when Reddit serves a rate-limit/block/challenge interstitial."""


def _parse_date_to_epoch(raw: str) -> float:
    """Parse a bladebro date string into a UNIX epoch (UTC); 0.0 when unknown."""
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
    """Render a Reddit `created_utc` epoch as a bladebro-style date string."""
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
    """A single post entry from a rendered Reddit listing."""

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
    """Rendered Reddit listing (feed) payload."""

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


class RedditPost(BaseModel):
    """The opening post of a Reddit comment thread."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    author: str = ""
    subreddit: str = ""
    score: int = 0
    comments: int = 0
    date: str = ""
    url: str = ""
    body: str = ""


class RedditComment(BaseModel):
    """A single comment in a Reddit comment thread."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    author: str = ""
    score: int = 0
    date: str = ""
    depth: int = 0
    text: str = ""
    url: str = ""


class RedditCommentThread(BaseModel):
    """Rendered Reddit comment thread payload."""

    model_config = ConfigDict(extra="ignore")

    container: str = ""
    post: RedditPost = Field(default_factory=RedditPost)
    count: int = 0
    total: int = 0
    complete: bool = False
    note: str = ""
    items: list[RedditComment] = Field(default_factory=list)


def find_bladebro_bin() -> str:
    """Locate the bladebro executable (env override, default path, then PATH)."""
    override = os.environ.get("BLADEBRO_BIN")
    if override and os.path.exists(override):
        return override
    if os.path.exists(DEFAULT_BLADEBRO_BIN):
        return DEFAULT_BLADEBRO_BIN
    found = shutil.which("bladebro")
    if found:
        return found
    raise BladebroError("bladebro executable not found; set BLADEBRO_BIN")


def blade_home() -> str:
    """Return the BLADE_HOME used by bladebro (env override or default)."""
    return os.environ.get("BLADE_HOME") or DEFAULT_BLADE_HOME


def _default_chrome_path() -> str:
    """Return the first existing Chrome path, preferring the bladebro install."""
    candidates = [
        DEFAULT_CHROME_PATH,
        os.path.expanduser(
            "~/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
        ),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def _bladebro_env() -> dict[str, str]:
    """Build the environment for bladebro, injecting Chrome and daemon paths."""
    env = dict(os.environ)
    env.setdefault("CHROME_PATH", _default_chrome_path())
    env["BLADE_HOME"] = blade_home()
    env["BLADE_NO_COMPRESS"] = "1"
    return env


def run_bladebro(args: list[str], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run the bladebro CLI and return stdout, raising BladebroError on failure."""
    binary = find_bladebro_bin()
    try:
        proc = subprocess.run(
            [binary, *args],
            env=_bladebro_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BladebroError(
            f"bladebro timed out after {timeout}s: {' '.join(args)}"
        ) from exc
    except OSError as exc:
        raise BladebroError(f"bladebro could not start: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise BladebroError(f"bladebro exit {proc.returncode}: {detail[:400]}")
    return proc.stdout


def is_blocked_text(text: str) -> bool:
    """Return True when a payload/URL looks like a Reddit block interstitial."""
    return bool(BLOCK_TEXT_PATTERN.search(text or ""))


def _classify_failure(text: str, url: str = "") -> BladebroError:
    """Return a typed error, flagging block/challenge pages explicitly."""
    if is_blocked_text(text) or BLOCK_URL_PATTERN.search(url or ""):
        return BladebroBlockedError(
            f"Reddit block/challenge interstitial detected ({url or 'page'})"
        )
    return BladebroError(f"bladebro returned an unparsable payload ({url or 'page'})")


def _resolve_artifact_path(raw_path: str) -> str:
    """Resolve an artifact path, relative to BLADE_HOME when not absolute."""
    candidate = os.path.expanduser(raw_path.strip())
    if os.path.isabs(candidate):
        return candidate
    return os.path.join(os.path.expanduser(blade_home()), candidate)


def _read_artifact_text(stdout: str) -> str | None:
    """Return the artifact file text referenced by a bladebro stdout, if any."""
    match = ARTIFACT_PATTERN.search(stdout)
    if not match:
        return None
    artifact_path = _resolve_artifact_path(match.group(2))
    try:
        with open(artifact_path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise BladebroError(f"artifact unreadable: {artifact_path}: {exc}") from exc


def _read_artifact_json(stdout: str) -> Any | None:
    """Read a bladebro artifact payload (dict, list or string), if referenced."""
    raw = _read_artifact_text(stdout)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BladebroError(f"artifact is not valid JSON: {exc}") from exc


def _clean_payload_text(payload_text: str) -> str:
    """Strip bladebro directives and deterministic truncation markers."""
    kept = [
        line
        for line in payload_text.splitlines()
        if not DIRECTIVE_PATTERN.match(line)
    ]
    return TRUNCATION_MARKER_PATTERN.sub("", "\n".join(kept)).strip()


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence from captured page text."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body[3:]
        first_newline = body.find("\n")
        if first_newline >= 0 and not body[:first_newline].strip().startswith("{"):
            body = body[first_newline + 1 :]
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


def _recover_truncated_json(
    payload_text: str,
) -> dict[str, Any] | None:
    """Best-effort recovery of a truncated JSON object.

    Cuts the payload at the last complete container boundary and closes any
    still-open containers, salvaging the items read before the cut.
    """
    depths: list[tuple[int, int]] = []
    candidates: list[int] = []
    depth_curly = 0
    depth_square = 0
    in_string = False
    escaped = False
    for char in payload_text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
            candidates.append(len(depths))
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square -= 1
            candidates.append(len(depths))
        depths.append((depth_curly, depth_square))
    for cut_index in reversed(candidates[-RECOVERY_ATTEMPTS:]):
        curly, square = depths[cut_index]
        suffix = "]" * max(square, 0) + "}" * max(curly, 0)
        try:
            recovered = json.loads(payload_text[: cut_index + 1] + suffix)
        except json.JSONDecodeError:
            continue
        if isinstance(recovered, dict):
            return recovered
    return None


def parse_extract_output(stdout: str) -> dict[str, Any]:
    """Parse an extract payload, whether inline or offloaded to an artifact file."""
    if EXTRACT_MARKER not in stdout:
        artifact = _read_artifact_json(stdout)
        if isinstance(artifact, dict):
            return artifact
    marker_index = stdout.rfind(EXTRACT_MARKER)
    payload_text = (
        stdout[marker_index + len(EXTRACT_MARKER) :]
        if marker_index >= 0
        else stdout.strip()
    )
    payload_text = _clean_payload_text(_strip_code_fences(payload_text))
    if not payload_text:
        raise BladebroError("bladebro returned no extract payload")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        recovered = _recover_truncated_json(payload_text)
        if recovered is not None:
            return recovered
        raise _classify_failure(payload_text) from exc
    if not isinstance(payload, dict):
        raise BladebroError("extract payload is not a JSON object")
    return payload


def _is_empty_payload(payload: dict[str, Any]) -> bool:
    """Return True when a payload carries no items (JS challenge or blank page)."""
    items = payload.get("items")
    if items is None:
        items = payload.get("comments")
    if isinstance(items, list) and items:
        return False
    count = payload.get("count")
    return not (isinstance(count, int) and count > 0)


def _listing_json_to_page(url: str) -> str:
    """Convert a Reddit listing `.json` URL into its rendered page URL."""
    path = url.split("?", 1)[0]
    path = re.sub(r"\.json$", "", path)
    if not path.endswith("/"):
        path += "/"
    return path


def _page_to_json(url: str, limit: int = DEFAULT_LIMIT) -> str:
    """Convert a Reddit listing page URL into its `.json` endpoint URL."""
    path = url.split("?", 1)[0]
    if not path.endswith(".json"):
        path = path.rstrip("/") + ".json"
    return f"{path}?limit={limit}"


def _listing_children(payload: Any) -> list[dict[str, Any]] | None:
    """Extract `data.children` from a Reddit Listing payload, or None."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        children = payload["data"].get("children")
        if isinstance(children, list):
            return [child for child in children if isinstance(child, dict)]
    return None


def _rotate_listing(url: str, attempt: int) -> str:
    """Rotate a listing page URL across hot/new/top to dodge soft blocks."""
    match = LISTING_URL_PATTERN.search(url or "")
    if not match:
        return url
    listing = LISTING_ROTATION[attempt % len(LISTING_ROTATION)]
    return re.sub(
        r"/(hot|new|top|rising)/?$", f"/{listing}/", url, flags=re.IGNORECASE
    )


def _backoff_sleep(attempt: int) -> None:
    """Sleep with an exponential, capped backoff for block/challenge retries."""
    if BACKOFF_BASE_SECONDS <= 0:
        return
    delay = min(BACKOFF_BASE_SECONDS * (2 ** attempt), BACKOFF_MAX_SECONDS)
    time.sleep(delay)


def _js_fetch_text(url: str) -> str:
    """Return a JS expression fetching `url` in the page and resolving to text."""
    target = json.dumps(url)
    return (
        f"fetch({target},{{credentials:'include',"
        "headers:{'Accept':'application/json'}}).then(r=>r.text())"
    )


def _safe_page_text(url: str, timeout: int) -> str:
    """Best-effort fetch of the current page text, for block classification."""
    try:
        if url:
            return run_bladebro(["see", url, "content", "--budget", "4000"], timeout=timeout)
        return run_bladebro(["see", "content", "--budget", "4000"], timeout=timeout)
    except BladebroError:
        return ""


def _body_from_eval_stdout(stdout: str) -> str:
    """Extract the fetched body text from an `act eval` stdout (artifact aware)."""
    artifact = _read_artifact_json(stdout)
    if artifact is None:
        return ""
    if isinstance(artifact, str):
        return artifact
    return json.dumps(artifact)


def fetch_listing_json_via_browser(
    json_url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Fetch a Reddit listing `.json` through the browser and return its children.

    Reddit blocks plain `requests` calls (HTTP 403) but serves the JSON to a
    real Chrome session, including `upvote_ratio` and `link_flair_text`.
    """
    page_url = _listing_json_to_page(json_url)
    run_bladebro(["act", "navigate", page_url], timeout=timeout)
    run_bladebro(["act", "wait", "settle", SETTLE_MILLISECONDS], timeout=timeout)
    stdout = run_bladebro(["act", "eval", _js_fetch_text(json_url)], timeout=timeout)
    if is_blocked_text(stdout):
        raise BladebroBlockedError(f"block interstitial while fetching {json_url}")
    body = _body_from_eval_stdout(stdout)
    if not body:
        raise BladebroError(f"bladebro returned no fetch result for {json_url}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _classify_failure(body, json_url) from exc
    children = _listing_children(payload)
    if children is None:
        raise _classify_failure(body, json_url)
    return children


def _parse_collect_items(stdout: str) -> list[dict[str, Any]]:
    """Parse `act collect` output (`collected N items:` + JSON array/artifact)."""
    artifact = _read_artifact_json(stdout)
    if isinstance(artifact, list):
        return [item for item in artifact if isinstance(item, dict)]
    if isinstance(artifact, dict):
        items = artifact.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    text = stdout
    marker = text.find(COLLECT_MARKER)
    if marker >= 0:
        text = text[text.find(":", marker) + 1 :]
    text = _clean_payload_text(_strip_code_fences(text))
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        recovered = _recover_truncated_json(text)
        if recovered is None:
            raise _classify_failure(text) from None
        payload = recovered
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    if not isinstance(payload, list):
        raise BladebroError("unexpected `act collect` payload shape")
    return [item for item in payload if isinstance(item, dict)]


def _children_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map generic collect items into Reddit-JSON-shaped children."""
    children: list[dict[str, Any]] = []
    for item in items:
        if "kind" in item and "data" in item:
            children.append(item)
            continue
        children.append(RedditFeedItem.model_validate(item).to_reddit_child())
    return children


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


def _collect_feed_children(
    page_url: str, target: int, timeout: int
) -> list[dict[str, Any]]:
    """Collect feed posts via `act collect` (infinite-scroll) up to `target`."""
    stdout = run_bladebro(
        ["act", "collect", page_url, "--max", str(target)], timeout=timeout
    )
    if is_blocked_text(stdout):
        raise BladebroBlockedError(f"block interstitial while collecting {page_url}")
    children = _children_from_items(_parse_collect_items(stdout))
    return _dedupe_children(children)


def _scroll_feed_children(
    page_url: str, target: int, timeout: int
) -> list[dict[str, Any]]:
    """Accumulate feed posts with eased `act scroll` + repeated extracts."""
    run_bladebro(["act", "navigate", page_url], timeout=timeout)
    run_bladebro(["act", "wait", "settle", SETTLE_MILLISECONDS], timeout=timeout)
    accumulated: list[dict[str, Any]] = []
    idle = 0
    max_scrolls = max(target // 10 + 5, SCROLL_MAX_IDLE + 1)
    for _ in range(max_scrolls):
        payload = parse_extract_output(
            run_bladebro(
                ["see", "extract", "auto", "--limit", str(target)], timeout=timeout
            )
        )
        before = len(accumulated)
        accumulated = _dedupe_children(
            accumulated
            + _children_from_items(list(payload.get("items") or []))
        )
        if len(accumulated) >= target:
            break
        idle = idle + 1 if len(accumulated) == before else 0
        if idle >= SCROLL_MAX_IDLE:
            break
        run_bladebro(["act", "scroll", "0", SCROLL_DELTA], timeout=timeout)
        run_bladebro(["act", "wait", "settle", "1200"], timeout=timeout)
    return accumulated


def _enrich_with_listing_json(
    children: list[dict[str, Any]], json_url: str, timeout: int
) -> list[dict[str, Any]]:
    """Fill upvote_ratio/flair on collected children from the listing JSON."""
    try:
        rich = fetch_listing_json_via_browser(json_url, timeout=timeout)
    except BladebroError:
        return children
    by_id = {
        str(child.get("data", {}).get("id")): child.get("data", {})
        for child in rich
        if child.get("data", {}).get("id")
    }
    for child in children:
        data = child.get("data", {})
        source = by_id.get(str(data.get("id")))
        if not source:
            continue
        data["upvote_ratio"] = source.get("upvote_ratio")
        if source.get("link_flair_text"):
            data["link_flair_text"] = source.get("link_flair_text")
    return children


def _extract_with_retry(
    url: str | None,
    limit: int,
    timeout: int,
    max_attempts: int = BLOCK_RETRIES + CHALLENGE_RETRIES,
) -> dict[str, Any]:
    """Extract the current/target page, retrying challenges and blocks."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            if attempt == 0 and url:
                args = ["see", url, "extract", "auto", "--limit", str(limit)]
            else:
                args = ["see", "extract", "auto", "--limit", str(limit)]
            stdout = run_bladebro(args, timeout=timeout)
            if is_blocked_text(stdout):
                last_error = BladebroBlockedError(
                    f"block interstitial on attempt {attempt + 1}"
                )
            else:
                payload = parse_extract_output(stdout)
                if not _is_empty_payload(payload):
                    return payload
                last_error = BladebroError(
                    "empty extract payload (possible JS challenge)"
                )
        except BladebroError as exc:
            last_error = exc
        if attempt == max_attempts - 1:
            break
        _backoff_sleep(attempt)
        if url and attempt > 0:
            url = _rotate_listing(url, attempt)
        try:
            run_bladebro(
                ["act", "wait", "settle", SETTLE_MILLISECONDS], timeout=timeout
            )
        except BladebroError:
            pass
    if isinstance(last_error, BladebroBlockedError):
        raise last_error
    page_text = _safe_page_text("", timeout)
    if is_blocked_text(page_text):
        raise BladebroBlockedError("Reddit block interstitial on final extract")
    raise BladebroError(str(last_error) if last_error else "extract failed")


def fetch_feed_url(
    page_url: str, limit: int = DEFAULT_LIMIT, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> RedditFeed:
    """Fetch a rendered Reddit listing by its page URL via bladebro."""
    payload = _extract_with_retry(page_url, limit, timeout)
    return RedditFeed.model_validate(payload)


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
    method: str = "auto",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> RedditFeed:
    """Fetch a full subreddit listing (browser JSON, `act collect` or scroll)."""
    sub = subreddit.strip("/").removeprefix("r/")
    page_url = f"{REDDIT_ROOT}/r/{sub}/{listing}/"
    json_url = f"{REDDIT_ROOT}/r/{sub}/{listing}.json?limit={target}"
    order = (
        ["browser-json", "collect", "scroll"]
        if method == "auto"
        else [method]
    )
    errors: list[str] = []
    blocked = False
    for candidate in order:
        try:
            if candidate == "browser-json":
                children = fetch_listing_json_via_browser(json_url, timeout=timeout)
            elif candidate == "collect":
                children = _collect_feed_children(page_url, target, timeout)
                children = _enrich_with_listing_json(children, json_url, timeout)
            elif candidate == "scroll":
                children = _scroll_feed_children(page_url, target, timeout)
            elif candidate == "requests":
                children = fetch_reddit_json_children(json_url, REDDIT_USER_AGENT)
            else:
                errors.append(f"{candidate}: unknown method")
                continue
            if children:
                return _feed_from_children(children[:target])
            errors.append(f"{candidate}: empty feed")
        except BladebroBlockedError as exc:
            blocked = True
            errors.append(f"{candidate}: blocked: {exc}")
        except BladebroError as exc:
            errors.append(f"{candidate}: {exc}")
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
    if blocked:
        raise BladebroBlockedError("; ".join(errors))
    raise CollectError("; ".join(errors) or "no listing source available")


def fetch_feed(
    subreddit: str = "wallstreetbets",
    listing: str = "hot",
    limit: int = DEFAULT_LIMIT,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    method: str = "auto",
    target: int | None = None,
) -> RedditFeed:
    """Fetch a subreddit listing with pagination (`hot`, `new`, `top`, ...)."""
    return fetch_feed_bulk(
        subreddit=subreddit,
        listing=listing,
        target=target or limit,
        method=method,
        timeout=timeout,
    )


def fetch_comment_thread(
    url: str, limit: int = 50, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> RedditCommentThread:
    """Fetch a rendered Reddit post and its comment tree via bladebro."""
    payload = _extract_with_retry(url, limit, timeout)
    if "items" not in payload and isinstance(payload.get("comments"), list):
        payload = {**payload, "items": payload["comments"]}
    return RedditCommentThread.model_validate(payload)


def fetch_reddit_json_children(url: str, user_agent: str) -> list[dict[str, Any]]:
    """Fetch a Reddit listing through the public JSON endpoint (fallback)."""
    response = requests.get(
        url, headers={"User-Agent": user_agent}, timeout=REQUEST_TIMEOUT_SECONDS
    )
    if response.status_code in (403, 429):
        raise BladebroBlockedError(
            f"reddit-json HTTP {response.status_code} (rate limited/blocked)"
        )
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("children", [])


def collect_reddit_children(
    url: str,
    user_agent: str,
    prefer_bladebro: bool = True,
    verbose: bool = False,
    limit: int = DEFAULT_LIMIT,
    target: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Collect listing children via bladebro, falling back to the public JSON.

    Returns the Reddit-JSON-shaped children list and the source that produced
    it. Raises `BladebroBlockedError` (never a silently empty dataset) when all
    sources are blocked, or `CollectError` when no source returns data.
    """
    want = target or limit
    json_url = url if url.endswith(".json") else _page_to_json(url, want)
    page_url = _listing_json_to_page(url)
    errors: list[str] = []
    blocked = False
    if prefer_bladebro:
        try:
            children = fetch_listing_json_via_browser(json_url, timeout=DEFAULT_TIMEOUT_SECONDS)
            children = _dedupe_children(children)
            if children:
                if verbose:
                    print(
                        f"  [bladebro-json] {len(children)} posts from {json_url}",
                        file=sys.stderr,
                    )
                return children[:want], "bladebro-json"
            errors.append("bladebro-json: empty listing")
        except BladebroBlockedError as exc:
            blocked = True
            errors.append(f"bladebro-json: blocked: {exc}")
        except BladebroError as exc:
            errors.append(f"bladebro-json: {exc}")
        try:
            children = _collect_feed_children(page_url, want, DEFAULT_TIMEOUT_SECONDS)
            children = _enrich_with_listing_json(
                children, json_url, DEFAULT_TIMEOUT_SECONDS
            )
            if children:
                if verbose:
                    print(
                        f"  [bladebro-collect] {len(children)} posts from {page_url}",
                        file=sys.stderr,
                    )
                return children[:want], "bladebro-collect"
            errors.append("bladebro-collect: empty feed")
        except BladebroBlockedError as exc:
            blocked = True
            errors.append(f"bladebro-collect: blocked: {exc}")
        except BladebroError as exc:
            errors.append(f"bladebro-collect: {exc}")
    try:
        children = fetch_reddit_json_children(url, user_agent)
        if verbose:
            print(f"  [reddit-json] {len(children)} posts from {url}", file=sys.stderr)
        return children, "reddit-json"
    except BladebroBlockedError as exc:
        blocked = True
        errors.append(f"reddit-json: {exc}")
    except (requests.RequestException, ValueError) as exc:
        errors.append(f"reddit-json: {exc}")
    message = "; ".join(errors) or "no data source available"
    if blocked:
        raise BladebroBlockedError(message)
    raise CollectError(message)


def count_ticker_mentions(children: list[dict[str, Any]], ticker: str) -> int:
    """Count case-insensitive `$TICKER` word occurrences across the given posts."""
    pattern = re.compile(rf"\$?{re.escape(ticker)}\b", re.IGNORECASE)
    count = 0
    for child in children:
        data = child.get("data", {})
        text = f"{data.get('title', '')} {data.get('selftext', '')}"
        count += len(pattern.findall(text))
    return count


REDDIT_USER_AGENT = "wsb-pump-detect/1.0 (bladebro client)"


def _demo(target: int = DEFAULT_TARGET) -> None:
    """Print a quick feed/thread summary when run as a script."""
    feed = fetch_feed("wallstreetbets", "hot", target=target)
    print(f"feed container={feed.container} count={feed.count} items={len(feed.items)}")
    for item in feed.items[:5]:
        ratio = f"{item.upvote_ratio:.2f}" if item.upvote_ratio is not None else "n/a"
        print(f"  [{item.score:>5}] ratio={ratio} flair={item.flair!r} {item.title[:60]}")
    thread = (
        fetch_comment_thread(str(feed.items[0].content_href), limit=5)
        if feed.items
        else None
    )
    if thread:
        print(
            f"thread post={thread.post.title[:60]!r} "
            f"comments={len(thread.items)} total={thread.total}"
        )


def main() -> None:
    """Parse arguments and run the feed client (useful for manual checks)."""
    parser = argparse.ArgumentParser(
        description="Fetch r/wallstreetbets listings via the bladebro browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 bladebro_client.py --subreddit wallstreetbets --listing hot --target 100
  python3 bladebro_client.py --method collect --target 50 --json
        """,
    )
    parser.add_argument("--subreddit", "-s", default="wallstreetbets")
    parser.add_argument("--listing", "-l", default="hot",
                        choices=["hot", "new", "top", "rising"])
    parser.add_argument("--target", "-t", type=int, default=DEFAULT_TARGET,
                        help=f"Target post count (default: {DEFAULT_TARGET})")
    parser.add_argument("--method", "-m", default="auto",
                        choices=["auto", "browser-json", "collect", "scroll", "requests"])
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output the feed as JSON")
    parser.add_argument("--demo", action="store_true",
                        help="Run the legacy feed/thread demo")
    args = parser.parse_args()

    if args.demo:
        _demo(args.target)
        return

    feed = fetch_feed_bulk(
        args.subreddit, args.listing, target=args.target, method=args.method
    )
    if args.json:
        print(json.dumps(feed.model_dump(mode="json"), indent=2, default=str))
        return
    print(f"{feed.count} posts from r/{args.subreddit}/{args.listing} [{args.method}]")
    ratios = [i.upvote_ratio for i in feed.items if i.upvote_ratio is not None]
    flairs = [i.flair for i in feed.items if i.flair]
    print(f"  upvote_ratio available: {len(ratios)}/{feed.count}")
    print(f"  flair available:        {len(flairs)}/{feed.count}")
    for item in feed.items[:10]:
        ratio = f"{item.upvote_ratio:.2f}" if item.upvote_ratio is not None else "n/a"
        print(f"  [{item.score:>5}] ratio={ratio} flair={item.flair!r} {item.title[:55]}")


if __name__ == "__main__":
    main()
