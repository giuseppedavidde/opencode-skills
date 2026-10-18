"""ThetaData options backend (primary source).

ThetaData exposes real open interest, implied vol and greeks for US equity
options through a **local Java "Theta Terminal" daemon** (default
``http://127.0.0.1:25510``). An API key (``THETADATA_API_KEY``) is required.

Availability = key present AND the daemon responds. When either is missing the
backend is simply excluded from the chain and the provider falls through to
Polygon / MarketData.app / yfinance.

NOTE: endpoint shapes target the ThetaData v3 REST API; field names are mapped
tolerantly because the daemon schema varies by version. Verified against the
live daemon only by the ``network``-marked test.
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
    OptionRight,
)
from trading_mcp.data.backends.rest import (
    HttpGet,
    RestOptionsBackend,
    build_options_chain,
    date_str,
    normalize_right,
    parse_expiry,
    pick,
    to_float,
    to_int,
)

logger = logging.getLogger(__name__)


def _rows_from_response(payload: Any) -> list[dict[str, Any]]:
    """Normalise a ThetaData response (records or column/header format)."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    header = payload.get("header")
    response = payload.get("response")
    if response is None:
        response = payload.get("data")
    if not isinstance(response, list):
        return []
    fmt = header.get("format") if isinstance(header, dict) else None
    if fmt and response and isinstance(response[0], list):
        return [dict(zip(fmt, row)) for row in response if isinstance(row, list)]
    return [row for row in response if isinstance(row, dict)]


class ThetaDataBackend(RestOptionsBackend):
    """Options backend backed by a local ThetaData terminal daemon."""

    name = "thetadata"
    capabilities = BackendCapabilities(
        provides_greeks=True,
        provides_iv=True,
        provides_open_interest=True,
        historical=True,
        us_only=True,
        requires_local_daemon=True,
        max_requests_per_minute=0,
    )
    timeout: float = 5.0

    def __init__(self, http_get: HttpGet | None = None, rpm: int | None = None) -> None:
        super().__init__(http_get=http_get, rpm=rpm)
        self._base = config.THETADATA_URL.rstrip("/")

    def _headers(self) -> dict[str, str]:
        key = config.THETADATA_API_KEY
        return {"Authorization": f"Bearer {key}"} if key else {}

    def is_available(self) -> bool:
        """True when an API key is set and the local daemon answers."""
        if not config.THETADATA_API_KEY:
            return False
        probe = self._request(
            f"{self._base}/v3/option/list/expirations",
            {"symbol": "SPY"},
            self._headers(),
        )
        return probe is not None

    def get_expirations(self, ticker: str) -> list[str]:
        """Return ThetaData expirations for ``ticker``."""
        payload = self._request(
            f"{self._base}/v3/option/list/expirations",
            {"symbol": ticker},
            self._headers(),
        )
        if payload is None:
            return []
        response = payload.get("response") if isinstance(payload, dict) else payload
        if not isinstance(response, list):
            return []
        expiries = sorted({date_str(item) for item in response if date_str(item)})
        return expiries

    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None:
        """Return the normalised chain from ThetaData greeks + open interest."""
        headers = self._headers()
        greeks_payload = self._request(
            f"{self._base}/v3/option/snapshot/greeks",
            {"symbol": ticker, "expiration": expiry},
            headers,
        )
        if greeks_payload is None:
            return None
        greek_rows = _rows_from_response(greeks_payload)

        oi_rows = _rows_from_response(
            self._request(
                f"{self._base}/v3/option/snapshot/open_interest",
                {"symbol": ticker, "expiration": expiry},
                headers,
            )
        )
        oi_by_key = self._index_oi(oi_rows)

        expiry_date = parse_expiry(expiry)
        if expiry_date is None:
            return None

        quotes = []
        for row in greek_rows:
            quote = self._row_to_quote(row, expiry_date, oi_by_key)
            if quote is not None:
                quotes.append(quote)
        return build_options_chain(ticker, self.name, expiry_date, quotes)

    @staticmethod
    def _key(row: dict[str, Any]) -> tuple[float | None, OptionRight | None]:
        return (
            to_float(pick(row, "strike", "strike_price", "K")),
            normalize_right(pick(row, "right", "option_type", "type")),
        )

    @classmethod
    def _index_oi(
        cls, rows: list[dict[str, Any]]
    ) -> dict[tuple[float | None, OptionRight | None], int]:
        indexed: dict[tuple[float | None, OptionRight | None], int] = {}
        for row in rows:
            indexed[cls._key(row)] = to_int(pick(row, "open_interest", "oi"))
        return indexed

    def _row_to_quote(
        self,
        row: dict[str, Any],
        expiry: date,
        oi_by_key: dict[tuple[float | None, OptionRight | None], int],
    ) -> OptionQuote | None:
        strike = to_float(pick(row, "strike", "strike_price", "K"))
        right = normalize_right(pick(row, "right", "option_type", "type"))
        if strike is None or strike <= 0 or right is None:
            return None
        key = (strike, right)
        oi = to_int(pick(row, "open_interest", "oi"))
        if not oi:
            oi = oi_by_key.get(key, 0)
        return OptionQuote(
            strike=strike,
            right=right,
            expiry=expiry,
            bid=to_float(pick(row, "bid")),
            ask=to_float(pick(row, "ask")),
            last=to_float(pick(row, "last", "last_price", "price")),
            volume=to_int(pick(row, "volume")),
            open_interest=oi,
            implied_volatility=to_float(pick(row, "implied_vol", "iv", "implied_volatility")),
            delta=to_float(pick(row, "delta")),
            gamma=to_float(pick(row, "gamma")),
            theta=to_float(pick(row, "theta")),
            vega=to_float(pick(row, "vega")),
        )
