"""Daily ATM implied-volatility history per ticker, for a real IV rank.

The options tools record one 30-day constant-maturity ATM IV per ticker and
exchange session date (the latest observation of the day wins) in a private
JSON file (``$XDG_CACHE_HOME/trading_mcp/iv_history/<TICKER>.json`` or
``TRADING_IV_HISTORY_DIR``; mode 0600, atomic writes). Only answers built from
a usable spot and fresh quotes are recorded.

IV rank and IV percentile are computed only with at least one year of
history (:data:`MIN_HISTORY_DAYS` calendar days between the first and the last
point and :data:`MIN_POINTS` observations). Otherwise both are ``None`` and
``iv_history_days`` / ``iv_history_points`` say how much history exists. A
rank from the in-chain IV range or from realized volatility is never shown.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data.cache_paths import atomic_write_json, cache_dir, read_json
from trading_mcp.timeutil import iso, utc_now

logger = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 365
MIN_POINTS = 120
_WINDOW_DAYS = 365
_SCHEMA = 1
_ENV = "TRADING_IV_HISTORY_DIR"
_UNRESOLVED: Any = object()
_DIR: Any = _UNRESOLVED
_LOCK = threading.Lock()


class IvRank(BaseModel):
    """IV rank and percentile over the last year (``None`` with less than a year)."""

    current_iv: float | None = None
    iv_rank: float | None = Field(default=None, description="0-100: (IV - min) / (max - min) over 1 year")
    iv_percentile: float | None = Field(default=None, description="0-100: share of days with a lower IV")
    iv_history_days: int | None = None
    iv_history_points: int | None = None
    iv_history_first: str | None = None
    iv_history_last: str | None = None
    iv_1y_min: float | None = None
    iv_1y_max: float | None = None
    measure: str = "30-day constant-maturity ATM IV, own solve from mids"
    source: str = "local iv_history store"
    note: str | None = None


def _directory() -> Path | None:
    global _DIR  # pylint: disable=global-statement
    if _DIR is _UNRESOLVED:
        _DIR = cache_dir("iv_history", _ENV)
    return _DIR


def _path(ticker: str) -> Path | None:
    root = _directory()
    if root is None:
        return None
    safe = re.sub(r"[^A-Za-z0-9.^-]", "_", ticker.upper())[:40] or "_"
    return Path(root) / f"{safe.replace('^', 'IDX_')}.json"


def load(ticker: str) -> dict[str, dict[str, Any]]:
    """Stored points ``{session_date: {"iv": float, "recorded_at": str, "source": str}}``."""
    path = _path(ticker)
    if path is None:
        return {}
    document = read_json(path)
    if not isinstance(document, dict) or document.get("schema") != _SCHEMA:
        return {}
    points = document.get("points")
    if not isinstance(points, dict):
        return {}
    clean: dict[str, dict[str, Any]] = {}
    for day, entry in points.items():
        try:
            date.fromisoformat(day)
            value = float(entry["iv"])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isfinite(value) and 0.0 < value < 5.0:
            clean[day] = dict(entry)
    return clean


def record(ticker: str, session_date: date, atm_iv: float, *, source: str,
           now: datetime | None = None) -> bool:
    """Store the ATM IV of one session date (overwrites that date). Returns True on success."""
    if not (isinstance(atm_iv, (int, float)) and math.isfinite(atm_iv) and 0.0 < atm_iv < 5.0):
        return False
    path = _path(ticker)
    if path is None:
        return False
    with _LOCK:
        points = load(ticker)
        points[session_date.isoformat()] = {
            "iv": round(float(atm_iv), 6), "recorded_at": iso(now or utc_now()), "source": source,
        }
        document = {"schema": _SCHEMA, "ticker": ticker.upper(), "points": dict(sorted(points.items()))}
        return atomic_write_json(path, document)


def rank(ticker: str, current_iv: float | None, *, today: date) -> IvRank:
    """IV rank and percentile of ``current_iv`` against the stored year."""
    points = load(ticker)
    result = IvRank(current_iv=round(current_iv, 6) if current_iv is not None else None)
    if not points:
        result.iv_history_days, result.iv_history_points = 0, 0
        result.note = "no stored IV history for this ticker"
        return result
    days = sorted(points)
    first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    result.iv_history_first, result.iv_history_last = days[0], days[-1]
    result.iv_history_days = (last - first).days
    result.iv_history_points = len(days)
    if result.iv_history_days < MIN_HISTORY_DAYS or len(days) < MIN_POINTS or current_iv is None:
        result.note = (
            f"IV rank needs {MIN_HISTORY_DAYS} days and {MIN_POINTS} points of history; "
            f"stored {result.iv_history_days} days / {len(days)} points"
        )
        return result
    start = today - timedelta(days=_WINDOW_DAYS)
    window = [float(points[d]["iv"]) for d in days if date.fromisoformat(d) >= start]
    if len(window) < MIN_POINTS:
        result.note = f"only {len(window)} points in the last {_WINDOW_DAYS} days"
        return result
    low, high = min(window), max(window)
    result.iv_1y_min, result.iv_1y_max = round(low, 6), round(high, 6)
    if high > low:
        result.iv_rank = round(min(max((current_iv - low) / (high - low), 0.0), 1.0) * 100.0, 1)
    result.iv_percentile = round(sum(1 for v in window if v < current_iv) / len(window) * 100.0, 1)
    return result
