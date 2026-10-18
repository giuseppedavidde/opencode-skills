"""yfinance options backend — last-resort / emergency fallback.

Wraps the previous default behaviour (``yf.Ticker(...).option_chain``). Yahoo
does not expose greeks, so ``greeks_are_native`` stays ``False`` and the local
Black-Scholes path computes them downstream.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from math import isfinite

import yfinance as yf

from trading_mcp.data.backends.base import (
    BackendCapabilities,
    OptionsChain,
    OptionQuote,
    OptionRight,
)

logger = logging.getLogger(__name__)


def _parse_expiry(expiry: str) -> date:
    """Parse a ``YYYY-MM-DD`` expiry string into a date."""
    return datetime.strptime(expiry, "%Y-%m-%d").date()  # noqa: DTZ007


def _finite(value: object) -> float | None:
    """Return ``value`` as a finite float, or ``None``."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _row_to_quote(row: object, right: OptionRight, expiry: date) -> OptionQuote | None:
    """Map a yfinance chain row to a normalised quote."""
    strike = _finite(row.get("strike"))  # type: ignore[attr-defined]
    if strike is None or strike <= 0:
        return None
    volume = _finite(row.get("volume"))  # type: ignore[attr-defined]
    open_interest = _finite(row.get("openInterest"))  # type: ignore[attr-defined]
    return OptionQuote(
        strike=strike,
        right=right,
        expiry=expiry,
        bid=_finite(row.get("bid")),  # type: ignore[attr-defined]
        ask=_finite(row.get("ask")),  # type: ignore[attr-defined]
        last=_finite(row.get("lastPrice")),  # type: ignore[attr-defined]
        volume=int(volume) if volume and volume > 0 else 0,
        open_interest=int(open_interest) if open_interest and open_interest > 0 else 0,
        implied_volatility=_finite(row.get("impliedVolatility")),  # type: ignore[attr-defined]
    )


class YFinanceBackend:
    """Options backend backed by yfinance (no native greeks)."""

    name = "yfinance"
    capabilities = BackendCapabilities(
        provides_greeks=False,
        provides_iv=True,
        provides_open_interest=True,
        historical=False,
        us_only=False,
        requires_local_daemon=False,
        max_requests_per_minute=0,
    )

    def is_available(self) -> bool:
        """yfinance is always available (no key required)."""
        return True

    def get_expirations(self, ticker: str) -> list[str]:
        """Return listed expirations for ``ticker`` (yfinance order preserved)."""
        try:
            return list(yf.Ticker(ticker).options)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("yfinance expirations failed for %s: %s", ticker, exc)
            return []

    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None:
        """Return the normalised chain for ``expiry`` from yfinance."""
        try:
            raw = yf.Ticker(ticker).option_chain(expiry)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("yfinance chain failed for %s/%s: %s", ticker, expiry, exc)
            return None
        try:
            expiry_date = _parse_expiry(expiry)
        except (TypeError, ValueError):
            return None

        quotes: list[OptionQuote] = []
        for frame, right in ((raw.calls, OptionRight.CALL), (raw.puts, OptionRight.PUT)):
            for row in frame.to_dict("records"):
                quote = _row_to_quote(row, right, expiry_date)
                if quote is not None:
                    quotes.append(quote)
        if not quotes:
            return None
        return OptionsChain(
            ticker=ticker,
            spot=self._spot(ticker),
            expiry=expiry_date,
            quotes=quotes,
            as_of=datetime.now(),
            source=self.name,
            greeks_are_native=False,
            iv_is_native=True,
        )

    @staticmethod
    def _spot(ticker: str) -> float:
        """Best-effort spot price (informational; the provider sets the real one)."""
        try:
            price = yf.Ticker(ticker).fast_info.get("lastPrice")
            return float(price) if price else 0.0
        except Exception:  # pylint: disable=broad-exception-caught
            return 0.0
