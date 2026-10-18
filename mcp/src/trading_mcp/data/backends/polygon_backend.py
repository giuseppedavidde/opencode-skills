"""Polygon.io options backend.

REST API (``api.polygon.io``), Bearer API key (``POLYGON_API_KEY``). Free tier
is throttled to ~5 requests/min and options snapshots are delayed/EOD, so the
shared :class:`TokenBucket` and the provider TTL cache matter here.

Availability = key present. Field mapping follows the v3 snapshot/reference
schemas; greeks are native on plans that expose them.
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

_BASE = "https://api.polygon.io"


class PolygonBackend(RestOptionsBackend):
    """Options backend backed by Polygon.io (free tier: ~5 req/min)."""

    name = "polygon"
    capabilities = BackendCapabilities(
        provides_greeks=True,
        provides_iv=True,
        provides_open_interest=True,
        historical=True,
        us_only=True,
        max_requests_per_minute=5,
    )
    timeout: float = 15.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {config.POLYGON_API_KEY}"}

    def is_available(self) -> bool:
        """True when a Polygon API key is configured."""
        return bool(config.POLYGON_API_KEY)

    def _paginate(
        self, url: str, params: dict[str, Any] | None, max_pages: int = 3
    ) -> list[dict[str, Any]]:
        """Collect ``results`` across up to ``max_pages`` pages."""
        rows: list[dict[str, Any]] = []
        next_url: str | None = url
        next_params = params
        pages = 0
        while next_url and pages < max_pages:
            payload = self._request(next_url, next_params, self._headers())
            pages += 1
            if not isinstance(payload, dict):
                break
            results = payload.get("results")
            if isinstance(results, list):
                rows.extend(item for item in results if isinstance(item, dict))
            next_url = payload.get("next_url")
            next_params = None
        return rows

    def get_expirations(self, ticker: str) -> list[str]:
        """Return distinct option expirations for ``ticker``."""
        rows = self._paginate(
            f"{_BASE}/v3/reference/options/contracts",
            {"underlying_ticker": ticker.upper(), "expired": "false", "limit": 1000},
        )
        expiries = sorted(
            {date_str(row.get("expiration_date")) for row in rows if row.get("expiration_date")}
        )
        return expiries

    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None:
        """Return the normalised snapshot chain for ``expiry``."""
        rows = self._paginate(
            f"{_BASE}/v3/snapshot/options/{ticker.upper()}",
            {"expiration_date": expiry, "limit": 250},
        )
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
        details = row.get("details") or {}
        strike = to_float(details.get("strike_price"))
        right = normalize_right(details.get("contract_type"))
        if strike is None or strike <= 0 or right is None:
            return None
        quote_block = row.get("last_quote") or {}
        day = row.get("day") or {}
        greeks = row.get("greeks") or {}
        return OptionQuote(
            strike=strike,
            right=right,
            expiry=expiry,
            bid=to_float(quote_block.get("bid")),
            ask=to_float(quote_block.get("ask")),
            last=to_float(day.get("close")),
            volume=to_int(day.get("volume")),
            open_interest=to_int(row.get("open_interest")),
            implied_volatility=to_float(row.get("implied_volatility")),
            delta=to_float(greeks.get("delta")),
            gamma=to_float(greeks.get("gamma")),
            theta=to_float(greeks.get("theta")),
            vega=to_float(greeks.get("vega")),
        )
