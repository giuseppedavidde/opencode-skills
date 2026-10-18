"""MarketData.app options backend.

REST API (``api.marketdata.app``), Bearer token (``MARKETDATA_API_KEY``).
Free tier is roughly 100 requests/day, so caching dominates. Chains are
returned as column-oriented arrays which are zipped into records.

Availability = key present.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from trading_mcp import config
from trading_mcp.data.backends.base import (
    BackendCapabilities,
    OptionsChain,
    OptionQuote,
)
from trading_mcp.data.backends.rest import (
    RestOptionsBackend,
    build_options_chain,
    date_str,
    normalize_right,
    parse_expiry,
    to_float,
    to_int,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.marketdata.app/v1"


def _zipped_rows(payload: Any) -> list[dict[str, Any]]:
    """Zip MarketData.app column-arrays (or pass through list-of-records)."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    columns = {key: value for key, value in payload.items() if isinstance(value, list)}
    if not columns:
        return []
    length = max(len(values) for values in columns.values())
    return [
        {key: (values[index] if index < len(values) else None) for key, values in columns.items()}
        for index in range(length)
    ]


class MarketDataBackend(RestOptionsBackend):
    """Options backend backed by MarketData.app."""

    name = "marketdata"
    capabilities = BackendCapabilities(
        provides_greeks=True,
        provides_iv=True,
        provides_open_interest=True,
        historical=True,
        us_only=True,
        max_requests_per_minute=60,
    )
    timeout: float = 15.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {config.MARKETDATA_API_KEY}"}

    def is_available(self) -> bool:
        """True when a MarketData.app token is configured."""
        return bool(config.MARKETDATA_API_KEY)

    def get_expirations(self, ticker: str) -> list[str]:
        """Return listed expirations for ``ticker``."""
        payload = self._request(
            f"{_BASE}/options/expirations/{ticker.upper()}/", None, self._headers()
        )
        if not isinstance(payload, dict):
            return []
        expiries = payload.get("expirations")
        if not isinstance(expiries, list):
            return []
        return sorted({date_str(item) for item in expiries if date_str(item)})

    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None:
        """Return the normalised chain for ``expiry``."""
        payload = self._request(
            f"{_BASE}/options/chain/{ticker.upper()}/",
            {"expiration": expiry},
            self._headers(),
        )
        rows = _zipped_rows(payload)
        expiry_date = parse_expiry(expiry)
        if expiry_date is None:
            return None
        quotes = []
        for row in rows:
            quote = self._row_to_quote(row, expiry_date)
            if quote is not None:
                quotes.append(quote)
        return build_options_chain(ticker, self.name, expiry_date, quotes)

    @staticmethod
    def _row_to_quote(row: dict[str, Any], expiry: date) -> OptionQuote | None:
        strike = to_float(row.get("strike"))
        right = normalize_right(row.get("side"))
        if strike is None or strike <= 0 or right is None:
            return None
        return OptionQuote(
            strike=strike,
            right=right,
            expiry=expiry,
            bid=to_float(row.get("bid")),
            ask=to_float(row.get("ask")),
            last=to_float(row.get("last")),
            volume=to_int(row.get("volume")),
            open_interest=to_int(row.get("openInterest")),
            implied_volatility=to_float(row.get("iv")),
            delta=to_float(row.get("delta")),
            gamma=to_float(row.get("gamma")),
            theta=to_float(row.get("theta")),
            vega=to_float(row.get("vega")),
        )
