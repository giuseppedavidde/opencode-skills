"""Pluggable options-data backend abstraction.

This module defines the *contract* all options data backends implement so the
:class:`~trading_mcp.data.provider.DataProvider` can chain them with graceful
degradation (ThetaData -> Polygon -> MarketData.app -> yfinance).

Conventions / units
-------------------
- ``gamma`` is **per share** (1 / unit of underlying), matching the local
  Black-Scholes gamma in :mod:`trading_mcp.analysis.pricing` and the GEX
  formula ``+/- gamma * OI * 100 * S^2 * 0.01``. Backends that expose
  per-contract gamma (x100) or dollar-gamma must normalise before returning.
- ``implied_volatility`` is an **annualised decimal** (e.g. ``0.20``). The
  options tools use it only as a cross-check: they solve their own IV from
  the mid.
- ``open_interest`` / ``volume`` are contract counts.
- ``contract_multiplier`` defaults to ``100`` (equity options).
- A missing ``bid``/``ask``/``implied_volatility`` is ``None`` and becomes
  ``NaN`` in the frames, never ``0.0``. A vendor bid of 0 stays 0 (no buyer).
- ``quote_time`` is the vendor time of the bid/ask, ``last_trade_time`` the
  time of the last trade (aware datetimes). ``OptionsChain.as_of`` is the
  latest quote time, else the latest trade time (``as_of_basis`` says which),
  else ``None``; ``fetched_at`` is the request time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, Field

# Protocol stub methods use ``...`` after their docstrings by design.
# pylint: disable=unnecessary-ellipsis


class OptionRight(StrEnum):
    """Option side."""

    CALL = "call"
    PUT = "put"


class BackendCapabilities(BaseModel):
    """Declared capabilities / limits of an options backend."""

    provides_greeks: bool = False
    provides_iv: bool = False
    provides_open_interest: bool = True
    historical: bool = False
    eod_only: bool = False
    us_only: bool = False
    requires_local_daemon: bool = False
    max_requests_per_minute: int = 0  # 0 = no explicit limit


class OptionQuote(BaseModel):
    """A single normalised option leg."""

    strike: float
    right: OptionRight
    expiry: date
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int = 0
    open_interest: int = 0
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    contract_multiplier: int = 100
    currency: str = "USD"
    quote_time: datetime | None = None
    last_trade_time: datetime | None = None


class OptionsChain(BaseModel):
    """Normalised option chain for a single expiry, from one backend."""

    ticker: str
    spot: float
    expiry: date
    quotes: list[OptionQuote] = Field(default_factory=list)
    as_of: datetime | None = None
    as_of_basis: str | None = None
    fetched_at: datetime | None = None
    source: str
    greeks_are_native: bool = False
    iv_is_native: bool = False
    truncated: bool = False

    def quotes_for(self, right: OptionRight) -> list[OptionQuote]:
        """Return the quotes for one option side."""
        return [quote for quote in self.quotes if quote.right is right]


def data_time(quotes: list[OptionQuote]) -> tuple[datetime | None, str | None]:
    """Latest vendor quote time, else latest trade time, with its basis."""
    quote_times = [q.quote_time for q in quotes if q.quote_time is not None and q.quote_time.tzinfo]
    if quote_times:
        return max(quote_times), "quote_time"
    trades = [q.last_trade_time for q in quotes if q.last_trade_time is not None and q.last_trade_time.tzinfo]
    if trades:
        return max(trades), "last_trade"
    return None, None


@runtime_checkable
class OptionsBackend(Protocol):
    """Structural contract for an options data source."""

    name: str
    capabilities: BackendCapabilities

    def is_available(self) -> bool:
        """Return True when the backend can be used (key present, daemon up)."""
        ...

    def get_expirations(self, ticker: str) -> list[str]:
        """Return listed expiry dates (``YYYY-MM-DD``), sorted ascending."""
        ...

    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None:
        """Return the normalised chain for ``expiry``, or ``None`` on failure."""
        ...


# Columns the local options pipeline (options_chain.py) consumes.
_FRAME_COLUMNS: list[str] = [
    "strike",
    "bid",
    "ask",
    "lastPrice",
    "volume",
    "openInterest",
    "impliedVolatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "quoteTime",
    "lastTradeDate",
]


def _nan(value: float | None) -> float:
    return float(value) if value is not None else float("nan")


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None and value.tzinfo is not None else None


def _quotes_to_frame(quotes: list[OptionQuote]) -> pd.DataFrame:
    """Build a pipeline-ready DataFrame from normalised quotes (missing values are NaN)."""
    rows = [
        {
            "strike": quote.strike,
            "bid": _nan(quote.bid),
            "ask": _nan(quote.ask),
            "lastPrice": _nan(quote.last),
            "volume": quote.volume,
            "openInterest": quote.open_interest,
            "impliedVolatility": _nan(quote.implied_volatility),
            "delta": quote.delta,
            "gamma": quote.gamma,
            "theta": quote.theta,
            "vega": quote.vega,
            "quoteTime": _stamp(quote.quote_time),
            "lastTradeDate": _stamp(quote.last_trade_time),
        }
        for quote in quotes
    ]
    return pd.DataFrame(rows, columns=_FRAME_COLUMNS)


@dataclass
class ChainData:
    """Provider-level chain payload (mirrors the yfinance namedtuple API).

    ``as_of`` is the vendor data time (ISO 8601) or ``None``; ``as_of_basis``
    is ``quote_time`` or ``last_trade``.
    """

    calls: pd.DataFrame
    puts: pd.DataFrame
    source: str
    greeks_are_native: bool = False
    spot: float = 0.0
    expiry: str | None = None
    as_of: str | None = None
    as_of_basis: str | None = None
    contract_multiplier: int = 100
    truncated: bool = False


def chain_to_chaindata(chain: OptionsChain) -> ChainData:
    """Bridge a normalised :class:`OptionsChain` to pipeline DataFrames."""
    as_of, basis = chain.as_of, chain.as_of_basis
    if as_of is None:
        as_of, basis = data_time(chain.quotes)
    multipliers = {quote.contract_multiplier for quote in chain.quotes}
    return ChainData(
        calls=_quotes_to_frame(chain.quotes_for(OptionRight.CALL)),
        puts=_quotes_to_frame(chain.quotes_for(OptionRight.PUT)),
        source=chain.source,
        greeks_are_native=chain.greeks_are_native,
        spot=chain.spot,
        expiry=chain.expiry.isoformat(),
        as_of=_stamp(as_of),
        as_of_basis=basis if as_of is not None else None,
        contract_multiplier=multipliers.pop() if len(multipliers) == 1 else 100,
        truncated=chain.truncated,
    )
