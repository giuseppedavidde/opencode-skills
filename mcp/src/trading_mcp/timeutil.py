"""Timezone-aware time helpers.

Every timestamp that leaves the server is ISO 8601 with an explicit offset.
Naive datetimes are rejected instead of being silently read as local time.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

UTC = timezone.utc


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def is_aware(value: datetime) -> bool:
    """True when ``value`` carries a usable UTC offset."""
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def require_aware(value: datetime, name: str = "datetime") -> datetime:
    """Return ``value`` unchanged, or raise ``ValueError`` when it is naive."""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime, got {type(value).__name__}")
    if not is_aware(value):
        raise ValueError(f"{name} must be timezone-aware (got a naive datetime)")
    return value


def _as_tz(tz: tzinfo | str | None) -> tzinfo | None:
    if tz is None or isinstance(tz, tzinfo):
        return tz
    return ZoneInfo(tz)


def to_datetime(value: Any) -> datetime | None:
    """Convert a datetime, pandas Timestamp or ISO string into an aware datetime.

    Returns ``None`` for ``None``, empty strings, unparsable strings and naive
    values (a naive time has no defined instant).
    """
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value if is_aware(value) else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if is_aware(parsed) else None
    return None


def iso(value: Any, *, tz: tzinfo | str | None = None, timespec: str = "seconds") -> str | None:
    """Format an aware datetime as ISO 8601 with offset.

    Args:
        value: Aware datetime, pandas Timestamp or ISO string (``None`` passes through).
        tz: Optional target timezone (IANA name or tzinfo).
        timespec: ``datetime.isoformat`` precision.

    Raises:
        ValueError: When ``value`` is a naive datetime.
    """
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, str):
        parsed = to_datetime(value)
        if parsed is None:
            raise ValueError(f"not an ISO 8601 timestamp with offset: {value!r}")
        value = parsed
    require_aware(value)
    target = _as_tz(tz)
    if target is not None:
        value = value.astimezone(target)
    return value.isoformat(timespec=timespec)


def utc_iso(value: datetime | None = None) -> str:
    """ISO 8601 UTC string for ``value`` (default: now)."""
    return iso(value if value is not None else utc_now(), tz=UTC) or ""


def from_epoch(seconds: Any, tz: tzinfo | str | None = UTC) -> datetime | None:
    """Convert UNIX seconds into an aware datetime; ``None`` when invalid."""
    try:
        number = float(seconds)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    result = datetime.fromtimestamp(number, UTC)
    target = _as_tz(tz)
    return result.astimezone(target) if target is not None else result


def epoch_to_iso(seconds: Any, tz: tzinfo | str | None = UTC) -> str | None:
    """ISO 8601 string for UNIX seconds, or ``None`` when invalid."""
    value = from_epoch(seconds, tz)
    return iso(value) if value is not None else None


def age_seconds(as_of: Any, now: datetime | None = None) -> float | None:
    """Seconds elapsed since ``as_of`` (aware datetime or ISO string)."""
    moment = to_datetime(as_of)
    if moment is None:
        return None
    reference = now if now is not None else utc_now()
    require_aware(reference, "now")
    return round((reference - moment).total_seconds(), 3)


def date_in_tz(value: datetime, tz: tzinfo | str) -> date:
    """Calendar date of an aware datetime in the given timezone."""
    require_aware(value)
    target = _as_tz(tz)
    return value.astimezone(target).date()
