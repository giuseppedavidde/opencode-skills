"""JSON over HTTP for keyless public APIs (CoinGecko, alternative.me).

- HTTP 429 blocks the host bucket for ``Retry-After`` seconds (default 60)
  and fails fast with ``rate_limited``.
- HTTP 5xx and network errors are retried with jittered backoff.
- HTTP 404 is ``not_found`` (never retried).
- :class:`TTLCache` keeps short-lived answers and 30 s negative entries.
"""

from __future__ import annotations

import copy
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from trading_mcp.data.http_policy import (
    ERROR_NETWORK,
    ERROR_NOT_FOUND,
    ERROR_RATE_LIMITED,
    ERROR_UPSTREAM,
    TokenBucket,
    UpstreamFailure,
    call_with_retry,
)

USER_AGENT = "trading-mcp/1.0"

# CoinGecko demo/public tier: about 30 calls per minute.
COINGECKO_BUCKET = TokenBucket(0.4, 5.0)
ALTERNATIVE_ME_BUCKET = TokenBucket(0.5, 3.0)

_MAX_RETRY_AFTER_S = 300.0


def _retry_after_seconds(error: urllib.error.HTTPError) -> float:
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(1.0, min(_MAX_RETRY_AFTER_S, float(header)))
    except (TypeError, ValueError):
        return 60.0


def _fetch_once(url: str, headers: dict[str, str], timeout: float, bucket: TokenBucket | None, what: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https only)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        if status == 429:
            wait = _retry_after_seconds(exc)
            if bucket is not None:
                bucket.penalize(wait)
            raise UpstreamFailure(ERROR_RATE_LIMITED, f"{what}: HTTP 429 (retry after {wait:.0f} s)",
                                  retryable=False, status=429) from exc
        if status == 404:
            raise UpstreamFailure(ERROR_NOT_FOUND, f"{what}: HTTP 404", retryable=False, status=404) from exc
        raise UpstreamFailure(ERROR_UPSTREAM, f"{what}: HTTP {status}", retryable=status >= 500,
                              status=status) from exc
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        offline = any(m in reason.lower() for m in ("name or service not known", "temporary failure in name resolution",
                                                     "nodename nor servname"))
        raise UpstreamFailure(ERROR_NETWORK, f"{what}: {type(exc).__name__}: {reason[:120]}",
                              retryable=not offline) from exc
    except (TimeoutError, OSError) as exc:
        raise UpstreamFailure(ERROR_NETWORK, f"{what}: {type(exc).__name__}", retryable=True) from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise UpstreamFailure(ERROR_UPSTREAM, f"{what}: invalid JSON", retryable=True) from exc


def get_json(
    url: str,
    *,
    what: str,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    bucket: TokenBucket | None = None,
    max_attempts: int = 2,
    acquire_timeout: float = 5.0,
) -> Any:
    """GET ``url`` and decode JSON under the retry policy.

    Raises:
        UpstreamFailure: Classified failure (message without secrets).
    """
    return call_with_retry(
        lambda: _fetch_once(url, headers or {}, timeout, bucket, what),
        what=what,
        bucket=bucket,
        max_attempts=max_attempts,
        base_delay=0.5,
        max_delay=4.0,
        acquire_timeout=acquire_timeout,
    )


class TTLCache:
    """Thread-safe key/value cache with per-entry TTL and negative entries."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[Any, tuple[float, float, Any, UpstreamFailure | None]] = {}

    def get(self, key: Any) -> tuple[Any, float, UpstreamFailure | None] | None:
        """Return ``(value_copy, stored_at, failure)`` while fresh, else ``None``."""
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            stored_at, ttl, value, failure = item
            if self._clock() - stored_at >= ttl:
                self._items.pop(key, None)
                return None
            return copy.deepcopy(value), stored_at, failure

    def set(self, key: Any, value: Any, ttl: float) -> None:
        """Store a deep copy of ``value`` for ``ttl`` seconds."""
        with self._lock:
            self._items[key] = (self._clock(), ttl, copy.deepcopy(value), None)

    def set_failure(self, key: Any, failure: UpstreamFailure, ttl: float = 30.0) -> None:
        """Remember a failure for at most 30 s."""
        with self._lock:
            self._items[key] = (self._clock(), min(ttl, 30.0), None, failure)

    def clear(self) -> None:
        """Drop every entry."""
        with self._lock:
            self._items.clear()
