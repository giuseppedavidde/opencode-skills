"""yfinance options backend — last-resort / emergency fallback.

Wraps ``yf.Ticker(...).option_chain``. Yahoo does not expose greeks, so
``greeks_are_native`` stays ``False`` and :mod:`trading_mcp.analysis.pricing`
computes them downstream. Yahoo gives no bid/ask time: the chain ``as_of`` is
the latest trade time (``as_of_basis = "last_trade"``). The spot is never read
here; the options tools take it from the DataProvider quote layer.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from math import isfinite

import yfinance as yf

from trading_mcp.data.backends.base import (
    BackendCapabilities,
    OptionsChain,
    OptionQuote,
    OptionRight,
    data_time,
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


def _trade_time(value: object) -> datetime | None:
    """Aware datetime of yfinance ``lastTradeDate`` (a UTC Timestamp), or ``None``."""
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except (TypeError, ValueError):
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return None


def _row_to_quote(row: object, right: OptionRight, expiry: date) -> OptionQuote | None:
    """Map a yfinance chain row to a normalised quote.

    Yahoo gives no bid/ask time, so ``quote_time`` stays ``None``; the last
    trade time is kept. An implied volatility of 0 is a missing value.
    """
    strike = _finite(row.get("strike"))  # type: ignore[attr-defined]
    if strike is None or strike <= 0:
        return None
    volume = _finite(row.get("volume"))  # type: ignore[attr-defined]
    open_interest = _finite(row.get("openInterest"))  # type: ignore[attr-defined]
    vendor_iv = _finite(row.get("impliedVolatility"))  # type: ignore[attr-defined]
    return OptionQuote(
        strike=strike,
        right=right,
        expiry=expiry,
        bid=_finite(row.get("bid")),  # type: ignore[attr-defined]
        ask=_finite(row.get("ask")),  # type: ignore[attr-defined]
        last=_finite(row.get("lastPrice")),  # type: ignore[attr-defined]
        volume=int(volume) if volume and volume > 0 else 0,
        open_interest=int(open_interest) if open_interest and open_interest > 0 else 0,
        implied_volatility=vendor_iv if vendor_iv is not None and vendor_iv > 0 else None,
        last_trade_time=_trade_time(row.get("lastTradeDate")),  # type: ignore[attr-defined]
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
        as_of, basis = data_time(quotes)
        return OptionsChain(
            ticker=ticker,
            spot=0.0,
            expiry=expiry_date,
            quotes=quotes,
            as_of=as_of,
            as_of_basis=basis,
            fetched_at=datetime.now(timezone.utc),
            source=self.name,
            greeks_are_native=False,
            iv_is_native=True,
        )
