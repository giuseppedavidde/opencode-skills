"""Alpha Vantage fundamentals for the MCP server.

Free tier: 25 API calls per day and 5 per minute. The limiter is shared by
every thread (lock) and, best effort, by every process of the same user: the
daily count is stored in the private cache (``alpha_vantage/usage.json``).

Loads the API key from:
1. TRADING_AV_API_KEY env var
2. ALPHA_VANTAGE_API_KEY env var
3. ~/.config/opencode/alpha_vantage_key.txt

The key travels in the query string, so only exception types and redacted
messages are logged. :func:`fetch_av_normalized` maps only documented
``OVERVIEW`` keys (checked against a recorded payload, see
``tests/fixtures/av_overview_IBM.json``) into the typed
:class:`~trading_mcp.data.fundamentals_schema.Fundamentals`;
:func:`fetch_av_fundamentals` renders it in yfinance keys and units.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from trading_mcp.data.cache_paths import atomic_write_json, cache_dir, read_json
from trading_mcp.data.fundamentals_schema import Fundamentals, from_alpha_vantage
from trading_mcp.data.redact import install_log_redaction, redact

logger = logging.getLogger(__name__)
install_log_redaction()

AV_BASE = "https://www.alphavantage.co/query"
AV_TIMEOUT = 10  # seconds


class RateLimiter:
    """Thread-safe free-tier limiter (5 per minute, 25 per UTC day).

    The daily count is persisted in the private cache so parallel server
    processes share one budget (best effort: no inter-process lock).
    """

    def __init__(self, max_per_minute: int = 5, max_per_day: int = 25, persist: bool = True) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_day = max_per_day
        self._persist = persist
        self._lock = threading.Lock()
        self._minute: list[float] = []
        self._memory_day = ""
        self._memory_count = 0

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _usage_path(self) -> Path | None:
        if not self._persist:
            return None
        directory = cache_dir("alpha_vantage")
        return directory / "usage.json" if directory is not None else None

    def _read_day_count(self) -> int:
        path = self._usage_path()
        data = read_json(path) if path is not None else None
        if not isinstance(data, dict) or data.get("day") != self._today():
            return self._memory_day_count()
        try:
            return max(int(data.get("count", 0)), self._memory_day_count())
        except (TypeError, ValueError):
            return self._memory_day_count()

    def _memory_day_count(self) -> int:
        return self._memory_count if self._memory_day == self._today() else 0

    def try_acquire(self) -> bool:
        """Reserve one call when both limits allow it."""
        with self._lock:
            now = time.time()
            self._minute = [stamp for stamp in self._minute if now - stamp < 60]
            used = self._read_day_count()
            if used >= self.max_per_day or len(self._minute) >= self.max_per_minute:
                return False
            self._minute.append(now)
            self._memory_day, self._memory_count = self._today(), used + 1
            path = self._usage_path()
            if path is not None:
                atomic_write_json(path, {"day": self._memory_day, "count": self._memory_count})
            return True

    def remaining_today(self) -> int:
        """Calls left today (shared count)."""
        with self._lock:
            return max(0, self.max_per_day - self._read_day_count())


_av_limiter = RateLimiter()


def _load_api_key() -> str | None:
    """Load the Alpha Vantage API key from the standard locations."""
    for name in ("TRADING_AV_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        key = os.environ.get(name)
        if key:
            return key
    key_file = Path.home() / ".config" / "opencode" / "alpha_vantage_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return None


def _av_get(function: str, symbol: str) -> dict[str, Any] | None:
    """Call Alpha Vantage once under the shared limiter; ``None`` on failure."""
    key = _load_api_key()
    if not key:
        return None
    if not _av_limiter.try_acquire():
        logger.debug("AV limit reached: %d calls remaining today", _av_limiter.remaining_today())
        return None
    try:
        response = requests.get(
            AV_BASE,
            params={"function": function, "symbol": symbol, "apikey": key},
            timeout=AV_TIMEOUT,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("AV %s request failed for %s: %s", function, symbol, type(exc).__name__)
        return None
    if not isinstance(data, dict) or not data:
        return None
    for marker in ("Error Message", "Note", "Information"):
        if marker in data:
            logger.warning("AV %s for %s: %s", marker, symbol, redact(data[marker])[:160])
            return None
    return data


def fetch_av_normalized(symbol: str) -> Fundamentals | None:
    """Typed Alpha Vantage OVERVIEW fundamentals (one API call), or ``None``."""
    overview = _av_get("OVERVIEW", symbol)
    if not overview:
        return None
    result = from_alpha_vantage(symbol, overview)
    if not result.fields:
        return None
    logger.info("AV fundamentals for %s: %d fields (remaining %d/%d)", symbol, len(result.fields),
                _av_limiter.remaining_today(), _av_limiter.max_per_day)
    return result


def fetch_av_fundamentals(symbol: str) -> dict[str, Any]:
    """Alpha Vantage fundamentals in yfinance keys AND yfinance units (``{}`` without data)."""
    normalized = fetch_av_normalized(symbol)
    if normalized is None:
        return {}
    legacy = normalized.to_legacy_info()
    legacy["_fundamentals_source"] = "alpha_vantage"
    return legacy


def fetch_av_historical(symbol: str) -> dict[str, Any]:
    """Historical statements for point-in-time studies (two API calls).

    Returns ``_av_annual_reports`` (last 5 years), ``_av_quarterly_reports``
    (last 8 quarters) and ``_av_earnings_history`` (last 8 quarters).
    """
    result: dict[str, Any] = {}
    income = _av_get("INCOME_STATEMENT", symbol)
    if income and "annualReports" in income:
        result["_av_annual_reports"] = income["annualReports"][:5]
        result["_av_quarterly_reports"] = income.get("quarterlyReports", [])[:8]
    earnings = _av_get("EARNINGS", symbol)
    if earnings and "annualEarnings" in earnings:
        result["_av_earnings_history"] = earnings.get("quarterlyEarnings", [])[:8]
    return result


def remaining_calls_today() -> int:
    """Alpha Vantage calls left today (free tier, shared count)."""
    return _av_limiter.remaining_today()
