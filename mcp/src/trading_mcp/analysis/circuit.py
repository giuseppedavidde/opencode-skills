"""Per-host circuit breakers for the scanner and the web-sentiment fetches.

The DataProvider already retries with backoff under a shared token bucket
and caches failures for 30 s. A breaker adds a host-level stop, so a scan
does not send hundreds of requests to a host that is down:

- only HOST failures count (network, rate limit, 5xx, local budget). An
  unknown symbol or an empty answer is a symbol problem and never opens it;
- it opens after 8 consecutive host failures, or when at least 10 of the
  last 20 calls exist and 60% or more of them failed;
- open: calls are refused for the cool-down (20 s, doubled after each
  failed probe, at most 120 s); then ONE probe call is allowed (half-open).
  A successful probe closes the breaker and clears the window; a failed
  probe opens it again.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

HOST_FAILURE_KINDS = frozenset({"network", "rate_limited", "upstream_error", "local_rate_limit", "unknown"})

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class HostCircuitBreaker:
    """Circuit breaker of one upstream host (see the module docstring)."""

    def __init__(
        self,
        host: str,
        *,
        consecutive_threshold: int = 8,
        window: int = 20,
        min_calls: int = 10,
        failure_ratio: float = 0.6,
        cooldown_s: float = 20.0,
        max_cooldown_s: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host = host
        self._consecutive_threshold = consecutive_threshold
        self._window: deque[bool] = deque(maxlen=window)
        self._min_calls = min_calls
        self._failure_ratio = failure_ratio
        self._base_cooldown = cooldown_s
        self._max_cooldown = max_cooldown_s
        self._cooldown = cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CLOSED
        self._opened_at = 0.0
        self._consecutive = 0
        self._probe_in_flight = False
        self.opened_count = 0

    @property
    def state(self) -> str:
        """Current state (``closed``, ``open`` or ``half_open``)."""
        with self._lock:
            self._advance()
            return self._state

    def _advance(self) -> None:
        if self._state == OPEN and self._clock() - self._opened_at >= self._cooldown:
            self._state = HALF_OPEN
            self._probe_in_flight = False

    def allow(self) -> bool:
        """True when a call may go to the host now."""
        with self._lock:
            self._advance()
            if self._state == CLOSED:
                return True
            if self._state == HALF_OPEN and not self._probe_in_flight:
                self._probe_in_flight = True
                return True
            return False

    def _open(self) -> None:
        self._state = OPEN
        self._opened_at = self._clock()
        self._probe_in_flight = False
        self.opened_count += 1

    def record_success(self) -> None:
        """A call reached the host and got an answer (also an empty one)."""
        with self._lock:
            self._consecutive = 0
            if self._state == HALF_OPEN:
                self._state = CLOSED
                self._cooldown = self._base_cooldown
                self._window.clear()
            self._window.append(True)

    def record_failure(self, kind: str | None = "network") -> None:
        """A call failed; only host-level kinds count (see :data:`HOST_FAILURE_KINDS`)."""
        if kind not in HOST_FAILURE_KINDS:
            return
        with self._lock:
            self._consecutive += 1
            self._window.append(False)
            if self._state == HALF_OPEN:
                self._cooldown = min(self._max_cooldown, self._cooldown * 2)
                self._open()
                return
            failures = self._window.count(False)
            ratio_trip = len(self._window) >= self._min_calls and failures / len(self._window) >= self._failure_ratio
            if self._state == CLOSED and (self._consecutive >= self._consecutive_threshold or ratio_trip):
                self._open()

    def stats(self) -> dict[str, float | int | str]:
        """Snapshot for monitoring."""
        with self._lock:
            self._advance()
            return {"host": self.host, "state": self._state, "consecutive_failures": self._consecutive,
                    "window_calls": len(self._window), "window_failures": self._window.count(False),
                    "cooldown_s": self._cooldown, "opened_count": self.opened_count}


_BREAKERS: dict[str, HostCircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def breaker(host: str) -> HostCircuitBreaker:
    """The shared breaker of ``host`` (created on first use)."""
    with _REGISTRY_LOCK:
        item = _BREAKERS.get(host)
        if item is None:
            item = HostCircuitBreaker(host)
            _BREAKERS[host] = item
        return item


def reset_breakers() -> None:
    """Forget every breaker (tests)."""
    with _REGISTRY_LOCK:
        _BREAKERS.clear()
