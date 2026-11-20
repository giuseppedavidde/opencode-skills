"""Upstream call policy: error classes, shared token bucket, backoff, single-flight.

- One :class:`TokenBucket` per upstream host is shared by every thread, so a
  50-ticker scan cannot exceed the configured request rate.
- :func:`call_with_retry` retries HTTP 429, HTTP 5xx, timeouts and broken
  connections with jittered exponential backoff. A 429 also blocks the whole
  bucket for the backoff time (a host-level cool-down).
- :class:`SingleFlight` collapses parallel calls for the same key into one
  upstream request.

Unknown symbols, empty payloads and DNS failures are not retried.
"""

from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, TypeVar

from trading_mcp.data.redact import redact

T = TypeVar("T")

ERROR_RATE_LIMITED = "rate_limited"
ERROR_UPSTREAM = "upstream_error"
ERROR_NETWORK = "network"
ERROR_NOT_FOUND = "not_found"
ERROR_EMPTY = "empty"
ERROR_LOCAL_LIMIT = "local_rate_limit"
ERROR_UNKNOWN = "unknown"

_NOT_FOUND_NAMES = {
    "YFPricesMissingError",
    "YFTzMissingError",
    "YFInvalidPeriodError",
    "YFTickerMissingError",
    "YFEarningsDateMissing",
}
_OFFLINE_MARKERS = (
    "could not resolve host",
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "getaddrinfo failed",
)


class UpstreamFailure(Exception):
    """A classified upstream failure (the message never contains secrets)."""

    def __init__(self, kind: str, message: str, *, retryable: bool, status: int | None = None) -> None:
        super().__init__(redact(message))
        self.kind = kind
        self.retryable = retryable
        self.status = status

    @property
    def message(self) -> str:
        """Redacted, human-readable reason."""
        return str(self)


def classify_exception(exc: BaseException) -> tuple[str, bool, int | None]:
    """Return ``(kind, retryable, http_status)`` for an upstream exception."""
    if isinstance(exc, UpstreamFailure):
        return exc.kind, exc.retryable, exc.status
    name = type(exc).__name__
    text = str(exc).lower()
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    status = status if isinstance(status, int) else None
    if name == "YFRateLimitError" or status == 429 or "too many requests" in text:
        return ERROR_RATE_LIMITED, True, 429
    if status is not None and status >= 500:
        return ERROR_UPSTREAM, True, status
    if status == 404 or name in _NOT_FOUND_NAMES:
        return ERROR_NOT_FOUND, False, status
    if status in (401, 403):
        return ERROR_UPSTREAM, True, status
    if any(marker in text for marker in _OFFLINE_MARKERS):
        return ERROR_NETWORK, False, status
    if (
        isinstance(exc, (TimeoutError, ConnectionError))
        or "timeout" in name.lower()
        or "connection" in name.lower()
        or name in ("ConnectError", "SSLError", "ProxyError", "ChunkedEncodingError",
                    "RemoteDisconnected", "IncompleteRead", "CurlError")
    ):
        return ERROR_NETWORK, True, status
    if name == "JSONDecodeError" or (name == "YFDataException" and "down" in text):
        return ERROR_UPSTREAM, True, status
    return ERROR_UNKNOWN, False, status


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class TokenBucket:
    """Thread-safe token bucket with a host-level cool-down.

    Args:
        rate_per_s: Sustained requests per second.
        capacity: Burst size.
        clock: Monotonic clock (injectable for tests).
        sleep: Sleep function (injectable for tests).
    """

    def __init__(
        self,
        rate_per_s: float,
        capacity: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rate = float(rate_per_s)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._blocked_until = 0.0
        self._lock = threading.Lock()
        self.granted = 0
        self.penalties = 0

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._updated = now

    def acquire(self, timeout: float = 60.0) -> bool:
        """Take one token, waiting at most ``timeout`` seconds."""
        deadline = self._clock() + timeout
        while True:
            with self._lock:
                now = self._clock()
                self._refill(now)
                if now < self._blocked_until:
                    wait = self._blocked_until - now
                elif self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self.granted += 1
                    return True
                else:
                    wait = (1.0 - self._tokens) / self._rate
            if self._clock() + wait > deadline:
                return False
            self._sleep(min(wait, 1.0))

    def penalize(self, seconds: float) -> None:
        """Block every caller for ``seconds`` (after an HTTP 429)."""
        with self._lock:
            now = self._clock()
            self._blocked_until = max(self._blocked_until, now + seconds)
            self._tokens = 0.0
            self.penalties += 1

    def stats(self) -> dict[str, float]:
        """Snapshot for monitoring."""
        with self._lock:
            now = self._clock()
            self._refill(now)
            return {
                "rate_per_s": self._rate,
                "capacity": self._capacity,
                "tokens": round(self._tokens, 2),
                "blocked_for_s": round(max(0.0, self._blocked_until - now), 2),
                "granted": self.granted,
                "penalties": self.penalties,
            }


# One bucket for every Yahoo Finance call made through the provider (one
# token per call; ``info`` takes two because it makes about two HTTP requests).
# Override with TRADING_YF_RATE_PER_S and TRADING_YF_BURST.
YAHOO_BUCKET = TokenBucket(
    _env_float("TRADING_YF_RATE_PER_S", 10.0),
    _env_float("TRADING_YF_BURST", 20.0),
)


def backoff_delay(attempt: int, base: float, cap: float, rng: Callable[[float, float], float] = random.uniform) -> float:
    """Jittered exponential delay for retry ``attempt`` (0-based)."""
    return min(cap, base * (2 ** attempt)) * rng(0.5, 1.5)


def call_with_retry(
    fn: Callable[[], T],
    *,
    what: str,
    bucket: TokenBucket | None = YAHOO_BUCKET,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    acquire_timeout: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``fn`` under the bucket, retrying transient failures.

    Raises:
        UpstreamFailure: With the classified kind of the last failure.
    """
    last: UpstreamFailure | None = None
    for attempt in range(max(1, max_attempts)):
        if bucket is not None and not bucket.acquire(timeout=acquire_timeout):
            raise UpstreamFailure(ERROR_LOCAL_LIMIT, f"{what}: request budget exhausted", retryable=True)
        try:
            return fn()
        except UpstreamFailure as exc:
            last = exc
        except Exception as exc:  # pylint: disable=broad-exception-caught
            kind, retryable, status = classify_exception(exc)
            last = UpstreamFailure(
                kind, f"{what}: {type(exc).__name__}: {str(exc)[:200]}",
                retryable=retryable, status=status,
            )
        if not last.retryable or attempt == max_attempts - 1:
            raise last
        delay = backoff_delay(attempt, base_delay, max_delay)
        if last.kind == ERROR_RATE_LIMITED:
            delay = max(delay, backoff_delay(attempt, 2.0, 30.0))
            if bucket is not None:
                bucket.penalize(delay)
        sleep(delay)
    raise last if last is not None else UpstreamFailure(ERROR_UNKNOWN, what, retryable=False)


@dataclass
class _Flight:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class SingleFlight:
    """Run one call per key at a time; parallel callers share its outcome.

    Followers receive the same result object: callers must copy it before
    they hand it out.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: dict[Hashable, _Flight] = {}

    def do(self, key: Hashable, fn: Callable[[], T]) -> T:
        """Return ``fn()`` for the first caller of ``key``; others wait for it."""
        with self._lock:
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = _Flight()
                self._flights[key] = flight
        assert flight is not None
        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return flight.result
        try:
            flight.result = fn()
            return flight.result
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
            flight.event.set()

    def in_flight(self) -> int:
        """Number of keys with a call in progress."""
        with self._lock:
            return len(self._flights)
