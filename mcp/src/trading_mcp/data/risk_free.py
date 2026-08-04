"""Risk-free rate provider with ^IRX snapshot and fallback.

P1 August 2026: replaces hardcoded RISK_FREE_RATE from config.py.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default TTL: 6 hours
_RISK_FREE_TTL_SECONDS: int = 6 * 3600

# Fallback rate (%): used only when live fetch fails
_FALLBACK_RATE_PCT: float = 4.5


class RiskFreeSnapshot(BaseModel):
    """Point-in-time risk-free rate snapshot with provenance.

    Attributes:
        value: Rate as a DECIMAL (e.g. 0.045 for 4.5%).
        source_ticker: Instrument used (^IRX = 13-week T-bill).
        as_of: Date the rate was published/fetched.
        fetched_at: UTC timestamp of fetch.
        stale: True if elapsed > TTL since fetched_at.
        fallback_reason: Non-empty only on fallback path.
    """

    value: float = Field(default=0.045, ge=0.0, le=1.0)
    source_ticker: str = "^IRX"
    as_of: Optional[str] = None
    fetched_at: Optional[str] = None
    stale: bool = False
    fallback_reason: Optional[str] = None

    def rate_decimal(self) -> float:
        """Return the rate as a decimal (e.g. 0.045)."""
        return self.value

    def rate_pct(self) -> float:
        """Return the rate as a percentage (e.g. 4.5)."""
        return self.value * 100.0

    @property
    def is_live(self) -> bool:
        """True if this snapshot came from a live source (not fallback)."""
        return self.fallback_reason is None

    @property
    def is_stale(self) -> bool:
        """True if the snapshot has exceeded its TTL."""
        return self.stale


class RiskFreeProvider:
    """Cached risk-free rate provider.

    Prefers ^IRX (13-week T-bill). Falls back to a configurable
    hardcoded rate ONLY on explicit fetch failure.  Stale flag
    is set when elapsed > TTL since last successful fetch.
    """

    _snapshot: Optional[RiskFreeSnapshot] = None
    _ttl: float

    def __init__(self, ttl_seconds: int = _RISK_FREE_TTL_SECONDS) -> None:
        self._ttl = float(ttl_seconds)

    def get_rate(self, *, force_refresh: bool = False) -> RiskFreeSnapshot:
        """Return the current risk-free rate snapshot.

        On cache hit (within TTL), returns the cached snapshot
        updating the stale flag. On cache miss or force_refresh,
        attempts a live fetch. On fetch failure, uses explicit
        fallback.

        Args:
            force_refresh: Ignore cache, re-fetch immediately.
        """
        now_dt = datetime.now(timezone.utc)

        if not force_refresh and self._snapshot is not None:
            if self._snapshot.fetched_at is not None:
                fetched = datetime.fromisoformat(self._snapshot.fetched_at)
                elapsed = (now_dt - fetched).total_seconds()
                if elapsed < self._ttl:
                    snapshot = self._snapshot.model_copy()
                    snapshot.stale = elapsed > self._ttl * 0.8
                    return snapshot

        try:
            live_snapshot = self._fetch_live()
            live_snapshot.stale = False
            self._snapshot = live_snapshot
            return live_snapshot
        except Exception as exc:
            logger.warning(
                "Risk-free rate fetch failed for %s: %s. Using fallback.",
                "^IRX", exc,
            )
            fallback = self._build_fallback(
                reason=f"Fetch failed: {exc}. Using hardcoded {_FALLBACK_RATE_PCT}%."
            )
            self._snapshot = fallback
            return fallback

    def invalidate(self) -> None:
        """Clear cached snapshot, forcing next get_rate to re-fetch."""
        self._snapshot = None

    # ── private ────────────────────────────────────────────────────

    def _fetch_live(self) -> RiskFreeSnapshot:
        """Fetch ^IRX from yfinance. Returns RiskFreeSnapshot."""
        import yfinance as yf

        ticker_yf = yf.Ticker("^IRX")
        info = ticker_yf.info

        raw_price: Optional[float] = None
        if info and isinstance(info, dict):
            for key in ("regularMarketPrice", "previousClose"):
                val = info.get(key)
                if val is not None:
                    raw_price = float(val)
                    break

        if raw_price is None or raw_price <= 0.0:
            raise ValueError(f"^IRX yielded no valid price: {raw_price=}")

        # ^IRX quotes the yield as a whole-number percentage
        # (e.g. 4.50 means 4.50%). Convert to decimal.
        rate_decimal = raw_price / 100.0
        if rate_decimal <= 0.0 or rate_decimal > 1.0:
            raise ValueError(
                f"^IRX yield out of range: {raw_price} -> {rate_decimal}"
            )

        now_str = datetime.now(timezone.utc).isoformat()

        return RiskFreeSnapshot(
            value=round(rate_decimal, 6),
            source_ticker="^IRX",
            as_of=now_str,
            fetched_at=now_str,
            stale=False,
            fallback_reason=None,
        )

    def _build_fallback(self, reason: str) -> RiskFreeSnapshot:
        """Build a fallback snapshot with the hardcoded config value."""
        now_str = datetime.now(timezone.utc).isoformat()
        return RiskFreeSnapshot(
            value=_FALLBACK_RATE_PCT / 100.0,
            source_ticker="^IRX",
            as_of=None,
            fetched_at=now_str,
            stale=True,
            fallback_reason=reason,
        )


# Module-level singleton
_risk_free_provider: Optional[RiskFreeProvider] = None


def get_risk_free_provider(ttl_seconds: int = _RISK_FREE_TTL_SECONDS) -> RiskFreeProvider:
    """Return the module-level RiskFreeProvider singleton."""
    global _risk_free_provider
    if _risk_free_provider is None:
        _risk_free_provider = RiskFreeProvider(ttl_seconds=ttl_seconds)
    return _risk_free_provider


def get_risk_free_rate(force_refresh: bool = False) -> RiskFreeSnapshot:
    """Convenience: get the current risk-free rate snapshot."""
    return get_risk_free_provider().get_rate(force_refresh=force_refresh)
