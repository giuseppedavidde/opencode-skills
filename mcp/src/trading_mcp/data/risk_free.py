"""Risk-free rate from the 13-week T-bill (^IRX) with an explicit fallback.

The live value comes from the DataProvider quote layer, so ``as_of`` is the
data time of the ^IRX quote (never the fetch time). A failed refresh never
replaces the live snapshot:

1. If an earlier live snapshot exists, it is returned with ``stale=True``
   and a ``fallback_reason``.
2. Otherwise the configured constant (``FALLBACK_RISK_FREE_RATE``) is
   returned with ``as_of=None``, ``stale=True`` and a ``fallback_reason``.

A fallback answer is kept for 30 s only, so the next call retries the live
source. ``is_live`` is False for every fallback answer.

``get_risk_free_rate()`` keeps its contract: the ^IRX discount yield as a
decimal. Option pricing uses the tenor curve instead (:func:`get_rate_curve`,
:func:`tenor_rate`): ^IRX (13 weeks), ^FVX (5 years), ^TNX (10 years) and
^TYX (30 years), each converted to a continuously compounded rate and
interpolated linearly in tenor (flat outside 0.25-30 years). Every point keeps
its ``as_of`` and source; a missing point is skipped and named in
``fallback_reason``. With no live point the curve falls back to the 13-week
snapshot above (flagged).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional

from pydantic import BaseModel, Field

from trading_mcp.timeutil import epoch_to_iso, iso, to_datetime, utc_now

logger = logging.getLogger(__name__)

# Live snapshots are reused for 6 hours (by fetch time).
_RISK_FREE_TTL_SECONDS: int = 6 * 3600
# A fallback answer is reused for 30 seconds at most.
_FALLBACK_TTL_SECONDS: float = 30.0
# A live value older than this (by data time) is flagged stale.
_STALE_DATA_AGE_SECONDS: float = 4 * 86400.0

# Configured fallback (%): used only when no live value was ever fetched.
_FALLBACK_RATE_PCT: float = 4.5

_SOURCE_SYMBOL = "^IRX"


class RiskFreeSnapshot(BaseModel):
    """Point-in-time risk-free rate with provenance.

    Attributes:
        value: Rate as a DECIMAL (0.045 is 4.5%).
        source_ticker: Instrument (^IRX = 13-week T-bill discount yield).
        source: Data source label.
        tenor: Tenor of the instrument.
        as_of: Data time of the quote (ISO 8601 with offset); ``None`` for the
            configured fallback.
        fetched_at: When the value was fetched (ISO 8601 UTC).
        stale: True for every fallback and for old data.
        fallback_reason: Set only on the fallback paths.
    """

    value: float = Field(ge=0.0, le=1.0)
    source_ticker: str = _SOURCE_SYMBOL
    source: str = "yfinance:^IRX"
    tenor: str = "13W"
    as_of: Optional[str] = None
    fetched_at: Optional[str] = None
    stale: bool = False
    fallback_reason: Optional[str] = None

    def rate_decimal(self) -> float:
        """Return the rate as a decimal (for example 0.045)."""
        return self.value

    def rate_pct(self) -> float:
        """Return the rate as a percentage (for example 4.5)."""
        return self.value * 100.0

    @property
    def is_live(self) -> bool:
        """True only for a successful live fetch (never for a fallback)."""
        return self.fallback_reason is None

    @property
    def is_stale(self) -> bool:
        """True for a fallback or for an old live value."""
        return self.stale


def _fetch_quote():
    from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

    return data_provider.get_quote(_SOURCE_SYMBOL)


class RiskFreeProvider:
    """Thread-safe cached risk-free rate (see the module docstring)."""

    def __init__(self, ttl_seconds: int = _RISK_FREE_TTL_SECONDS, *, clock=time.time) -> None:
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._live: RiskFreeSnapshot | None = None
        self._live_fetched: float = 0.0
        self._fallback: RiskFreeSnapshot | None = None
        self._fallback_until: float = 0.0

    def get_rate(self, *, force_refresh: bool = False) -> RiskFreeSnapshot:
        """Return the current snapshot (live, or flagged fallback)."""
        now = self._clock()
        with self._lock:
            if not force_refresh and self._live is not None and now - self._live_fetched < self._ttl:
                return self._with_data_staleness(self._live.model_copy())
            if not force_refresh and self._fallback is not None and now < self._fallback_until:
                return self._fallback.model_copy()
        try:
            snapshot = self._fetch_live()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Risk-free rate fetch failed for %s: %s", _SOURCE_SYMBOL, type(exc).__name__)
            return self._remember_fallback(f"live ^IRX unavailable: {exc}", now)
        with self._lock:
            self._live = snapshot
            self._live_fetched = now
            self._fallback = None
        return self._with_data_staleness(snapshot.model_copy())

    def invalidate(self) -> None:
        """Forget cached and fallback snapshots; the next call fetches."""
        with self._lock:
            self._live = None
            self._live_fetched = 0.0
            self._fallback = None
            self._fallback_until = 0.0

    def _with_data_staleness(self, snapshot: RiskFreeSnapshot) -> RiskFreeSnapshot:
        moment = to_datetime(snapshot.as_of)
        if moment is not None and (utc_now() - moment).total_seconds() > _STALE_DATA_AGE_SECONDS:
            snapshot.stale = True
        return snapshot

    def _fetch_live(self) -> RiskFreeSnapshot:
        quote = _fetch_quote()
        if quote.price is None:
            raise ValueError(quote.error or "no ^IRX price")
        # ^IRX quotes the discount yield in percent (4.50 means 4.50%).
        rate = quote.price / 100.0
        if not 0.0 < rate < 0.25:
            raise ValueError(f"^IRX yield out of range: {quote.price}")
        return RiskFreeSnapshot(
            value=round(rate, 6),
            source=quote.source or "yfinance",
            as_of=quote.as_of,
            fetched_at=iso(utc_now()),
            stale=bool(quote.stale),
            fallback_reason=None,
        )

    def _remember_fallback(self, reason: str, now: float) -> RiskFreeSnapshot:
        with self._lock:
            if self._live is not None:
                fallback = self._live.model_copy(update={
                    "stale": True,
                    "fallback_reason": f"{reason}; last live value as of {self._live.as_of}",
                })
            else:
                fallback = RiskFreeSnapshot(
                    value=_FALLBACK_RATE_PCT / 100.0,
                    source="config:FALLBACK_RISK_FREE_RATE",
                    as_of=None,
                    fetched_at=epoch_to_iso(now),
                    stale=True,
                    fallback_reason=f"{reason}; configured {_FALLBACK_RATE_PCT}% used",
                )
            self._fallback = fallback
            self._fallback_until = now + _FALLBACK_TTL_SECONDS
            return fallback.model_copy()


_risk_free_provider: Optional[RiskFreeProvider] = None
_singleton_lock = threading.Lock()


def get_risk_free_provider(ttl_seconds: int = _RISK_FREE_TTL_SECONDS) -> RiskFreeProvider:
    """Return the module-level RiskFreeProvider singleton."""
    global _risk_free_provider  # pylint: disable=global-statement
    with _singleton_lock:
        if _risk_free_provider is None:
            _risk_free_provider = RiskFreeProvider(ttl_seconds=ttl_seconds)
        return _risk_free_provider


def get_risk_free_rate(force_refresh: bool = False) -> RiskFreeSnapshot:
    """Convenience: the current risk-free snapshot (check ``is_live``)."""
    return get_risk_free_provider().get_rate(force_refresh=force_refresh)


# ── Tenor curve for option pricing ───────────────────────────────────

# (symbol, tenor in years, quote convention). Yahoo quotes all four in percent.
CURVE_POINTS: tuple[tuple[str, float, str], ...] = (
    ("^IRX", 0.25, "discount"),
    ("^FVX", 5.0, "bond_equivalent"),
    ("^TNX", 10.0, "bond_equivalent"),
    ("^TYX", 30.0, "bond_equivalent"),
)
_CURVE_TTL_SECONDS: float = 15 * 60.0
_BILL_DAYS = 91.0


def discount_to_continuous(discount_yield: float, days: float = _BILL_DAYS) -> float:
    """T-bill bank-discount yield (decimal) to a continuously compounded rate."""
    price = 1.0 - discount_yield * days / 360.0
    if price <= 0.0:
        raise ValueError(f"discount yield out of range: {discount_yield}")
    return -math.log(price) / (days / 365.0)


def bey_to_continuous(bond_yield: float) -> float:
    """Semiannual bond-equivalent yield (decimal) to a continuously compounded rate."""
    return 2.0 * math.log(1.0 + bond_yield / 2.0)


class CurvePoint(BaseModel):
    """One curve instrument with its quote time and the converted rate."""

    symbol: str
    tenor_years: float
    convention: str
    quoted_pct: Optional[float] = None
    rate: Optional[float] = Field(default=None, description="Continuously compounded, decimal")
    as_of: Optional[str] = None
    source: Optional[str] = None
    stale: bool = True
    error: Optional[str] = None


class TenorRate(BaseModel):
    """Rate for one option tenor (continuously compounded decimal)."""

    value: float
    tenor_years: float
    compounding: str = "continuous"
    method: str = Field(description="linear | flat_short | flat_long | single_point | fallback_13w")
    points_used: list[str] = Field(default_factory=list)
    as_of: Optional[str] = Field(default=None, description="Oldest data time of the points used")
    source: str = "yfinance:treasury_yields"
    is_live: bool = True
    stale: bool = False
    fallback_reason: Optional[str] = None


class RateCurve(BaseModel):
    """Tenor curve snapshot (see the module docstring)."""

    points: list[CurvePoint] = Field(default_factory=list)
    fetched_at: Optional[str] = None
    fallback_reason: Optional[str] = None
    fallback: Optional[RiskFreeSnapshot] = None

    def usable(self) -> list[CurvePoint]:
        """Points with a rate, sorted by tenor."""
        return sorted((p for p in self.points if p.rate is not None), key=lambda p: p.tenor_years)

    def rate(self, tenor_years: float) -> TenorRate:
        """Interpolated rate for ``tenor_years`` (flat beyond the end points)."""
        tenor = max(float(tenor_years), 0.0)
        points = self.usable()
        if not points:
            snapshot = self.fallback or get_risk_free_rate()
            try:
                value = discount_to_continuous(snapshot.value)
            except ValueError:
                value = snapshot.value
            reason = self.fallback_reason or "no curve point available"
            if snapshot.fallback_reason:
                reason = f"{reason}; {snapshot.fallback_reason}"
            return TenorRate(
                value=round(value, 6), tenor_years=tenor, method="fallback_13w",
                points_used=[snapshot.source_ticker], as_of=snapshot.as_of, source=snapshot.source,
                is_live=snapshot.is_live, stale=True, fallback_reason=reason,
            )
        if len(points) == 1:
            only = points[0]
            return self._result(only.rate, tenor, "single_point", [only])
        if tenor <= points[0].tenor_years:
            return self._result(points[0].rate, tenor, "flat_short", [points[0]])
        if tenor >= points[-1].tenor_years:
            return self._result(points[-1].rate, tenor, "flat_long", [points[-1]])
        for left, right in zip(points, points[1:]):
            if left.tenor_years <= tenor <= right.tenor_years:
                weight = (tenor - left.tenor_years) / (right.tenor_years - left.tenor_years)
                value = left.rate + weight * (right.rate - left.rate)
                return self._result(value, tenor, "linear", [left, right])
        return self._result(points[-1].rate, tenor, "flat_long", [points[-1]])

    def _result(self, value: float, tenor: float, method: str, used: list[CurvePoint]) -> TenorRate:
        stamps = [p.as_of for p in used if p.as_of]
        oldest = min(stamps, key=lambda text: to_datetime(text) or utc_now()) if stamps else None
        return TenorRate(
            value=round(float(value), 6), tenor_years=round(tenor, 6), method=method,
            points_used=[p.symbol for p in used], as_of=oldest,
            source=",".join(sorted({p.source or "unknown" for p in used})),
            is_live=True, stale=any(p.stale for p in used), fallback_reason=self.fallback_reason,
        )


def _fetch_curve_quote(symbol: str):
    from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

    return data_provider.get_quote(symbol)


def _curve_point(symbol: str, tenor: float, convention: str) -> CurvePoint:
    point = CurvePoint(symbol=symbol, tenor_years=tenor, convention=convention)
    try:
        quote = _fetch_curve_quote(symbol)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        point.error = f"{type(exc).__name__}: {exc}"
        return point
    if quote is None or quote.price is None:
        point.error = getattr(quote, "error", None) or "no price"
        return point
    pct = float(quote.price)
    if not 0.0 < pct < 25.0:
        point.error = f"yield out of range: {pct}"
        return point
    moment = to_datetime(quote.as_of)
    if moment is None or (utc_now() - moment).total_seconds() > _STALE_DATA_AGE_SECONDS:
        point.error = "quote time unknown or older than 4 days"
        point.quoted_pct, point.as_of = pct, quote.as_of
        return point
    decimal = pct / 100.0
    point.quoted_pct = pct
    point.rate = round(discount_to_continuous(decimal) if convention == "discount" else bey_to_continuous(decimal), 6)
    point.as_of = quote.as_of
    point.source = quote.source
    point.stale = bool(quote.stale)
    return point


class RateCurveProvider:
    """Thread-safe cached tenor curve (live 15 min, partial or failed answers 30 s)."""

    def __init__(self, ttl_seconds: float = _CURVE_TTL_SECONDS, *, clock=time.time) -> None:
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._curve: RateCurve | None = None
        self._until: float = 0.0

    def get_curve(self, *, force_refresh: bool = False) -> RateCurve:
        """Return the cached curve or fetch every point again."""
        now = self._clock()
        with self._lock:
            if not force_refresh and self._curve is not None and now < self._until:
                return self._curve.model_copy(deep=True)
        points = [_curve_point(symbol, tenor, conv) for symbol, tenor, conv in CURVE_POINTS]
        missing = [p.symbol for p in points if p.rate is None]
        curve = RateCurve(points=points, fetched_at=iso(utc_now()))
        if missing:
            curve.fallback_reason = "curve points unavailable: " + ", ".join(missing)
        if not curve.usable():
            curve.fallback = get_risk_free_rate()
        with self._lock:
            self._curve = curve
            self._until = now + (self._ttl if not missing else _FALLBACK_TTL_SECONDS)
        return curve.model_copy(deep=True)

    def invalidate(self) -> None:
        """Forget the cached curve."""
        with self._lock:
            self._curve = None
            self._until = 0.0


_curve_provider: Optional[RateCurveProvider] = None


def get_rate_curve_provider() -> RateCurveProvider:
    """Return the module-level RateCurveProvider singleton."""
    global _curve_provider  # pylint: disable=global-statement
    with _singleton_lock:
        if _curve_provider is None:
            _curve_provider = RateCurveProvider()
        return _curve_provider


def get_rate_curve(force_refresh: bool = False) -> RateCurve:
    """The current tenor curve (check ``fallback_reason``)."""
    return get_rate_curve_provider().get_curve(force_refresh=force_refresh)


def tenor_rate(tenor_years: float) -> TenorRate:
    """Continuously compounded rate for one tenor in years."""
    return get_rate_curve().rate(tenor_years)
