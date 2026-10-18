"""Shared helpers for REST-based options backends (rate limiting + HTTP)."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from trading_mcp.data.backends.base import BackendCapabilities, OptionsChain, OptionRight

logger = logging.getLogger(__name__)

# A function ``(url, params, headers, timeout) -> parsed JSON``. Injectable so
# tests can exercise backends without touching the network.
HttpGet = Callable[[str, dict[str, Any] | None, dict[str, str] | None, float], Any]


def default_http_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> Any:
    """GET ``url`` and parse the JSON body (stdlib only, no extra dependency)."""
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class TokenBucket:
    """Simple rate limiter honouring ``max_requests_per_minute``.

    ``clock``/``sleep`` are injectable for deterministic tests. A limit of 0
    or less disables throttling entirely.
    """

    # pylint: disable=too-few-public-methods

    def __init__(
        self,
        max_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._limit = max(0, max_per_minute)
        self._interval = 60.0 / self._limit if self._limit else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block (via ``sleep``) until a new request slot is available."""
        if self._limit <= 0:
            return
        with self._lock:
            now = self._clock()
            if self._last is not None:
                wait = self._interval - (now - self._last)
                if wait > 0:
                    self._sleep(wait)
                    now = self._clock()
            self._last = now


def to_float(value: Any) -> float | None:
    """Coerce ``value`` to a finite float, or ``None``."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def to_int(value: Any) -> int:
    """Coerce ``value`` to a non-negative int, defaulting to 0."""
    number = to_float(value)
    return int(number) if number is not None and number > 0 else 0


def date_str(value: Any) -> str:
    """Return ``YYYY-MM-DD`` from a date/datetime/ISO string (best effort)."""
    if value is None:
        return ""
    text = str(value).strip()
    return text[:10]


def pick(row: dict[str, Any], *names: str) -> Any:
    """Return the first present, non-null value among ``names``."""
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def normalize_right(value: Any) -> "OptionRight | None":
    """Map a vendor right/type token to :class:`OptionRight` (or ``None``)."""
    text = str(value).strip().lower()
    if text in ("call", "c", "calls"):
        return OptionRight.CALL
    if text in ("put", "p", "puts"):
        return OptionRight.PUT
    return None


def parse_expiry(expiry: str) -> date | None:
    """Parse a ``YYYY-MM-DD`` expiry into a date (``None`` when malformed)."""
    try:
        return datetime.strptime(expiry, "%Y-%m-%d").date()  # noqa: DTZ007
    except (TypeError, ValueError):
        return None


def build_options_chain(
    ticker: str, source: str, expiry: date | None, quotes: list
) -> OptionsChain | None:
    """Assemble an :class:`OptionsChain` from parsed quotes (``None`` if empty)."""
    if expiry is None or not quotes:
        return None
    return OptionsChain(
        ticker=ticker,
        spot=0.0,
        expiry=expiry,
        quotes=quotes,
        as_of=datetime.now(),
        source=source,
        greeks_are_native=any(quote.gamma is not None for quote in quotes),
        iv_is_native=True,
    )


class RestOptionsBackend:
    """Base class for HTTP/REST options backends.

    Sub-classes set ``name``/``capabilities`` and implement
    :meth:`is_available`, :meth:`get_expirations`, :meth:`get_chain`.
    HTTP is injected (``http_get``) so tests run fully offline.
    """

    name: str = ""
    capabilities: BackendCapabilities = BackendCapabilities()
    timeout: float = 10.0

    def __init__(self, http_get: HttpGet | None = None, rpm: int | None = None) -> None:
        self._http_get = http_get or default_http_get
        limit = rpm if rpm is not None else self.capabilities.max_requests_per_minute
        self._bucket = TokenBucket(limit)

    def _request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Rate-limited GET returning parsed JSON, or ``None`` on any error."""
        self._bucket.acquire()
        try:
            return self._http_get(url, params, headers, self.timeout)
        except urllib.error.HTTPError as exc:
            logger.warning("%s: HTTP %s for %s", self.name, exc.code, url)
            return None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("%s: request failed for %s: %s", self.name, url, exc)
            return None

    def is_available(self) -> bool:  # pragma: no cover - overridden
        """Return True when the backend can be used."""
        return False

    def get_expirations(self, ticker: str) -> list[str]:  # pragma: no cover
        """Return listed expirations (``YYYY-MM-DD``)."""
        raise NotImplementedError

    def get_chain(self, ticker: str, expiry: str):  # pragma: no cover
        """Return the normalised chain for ``expiry``."""
        raise NotImplementedError
