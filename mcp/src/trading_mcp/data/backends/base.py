"""Pluggable options-data backend abstraction.

This module defines the *contract* all options data backends implement so the
:class:`~trading_mcp.data.provider.DataProvider` can chain them with graceful
degradation (ThetaData -> Polygon -> MarketData.app -> yfinance).

Conventions / units
-------------------
- ``gamma`` is **per share** (1 / unit of underlying), matching the local
  Black-Scholes gamma in :mod:`trading_mcp.data.options_chain` and the GEX
  formula ``+/- gamma * OI * 100 * S^2 * 0.01``. Backends that expose
  per-contract gamma (x100) or dollar-gamma must normalise before returning.
- ``implied_volatility`` is an **annualised decimal** (e.g. ``0.20``).
- ``open_interest`` / ``volume`` are contract counts.
- ``contract_multiplier`` defaults to ``100`` (equity options).
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


class OptionsChain(BaseModel):
    """Normalised option chain for a single expiry, from one backend."""

    ticker: str
    spot: float
    expiry: date
    quotes: list[OptionQuote] = Field(default_factory=list)
    as_of: datetime
    source: str
    greeks_are_native: bool = False
    iv_is_native: bool = False

    def quotes_for(self, right: OptionRight) -> list[OptionQuote]:
        """Return the quotes for one option side."""
        return [quote for quote in self.quotes if quote.right is right]


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
    "volume",
    "openInterest",
    "impliedVolatility",
    "delta",
    "gamma",
    "theta",
    "vega",
]


def _quotes_to_frame(quotes: list[OptionQuote]) -> pd.DataFrame:
    """Build a pipeline-ready DataFrame from normalised quotes."""
    rows = [
        {
            "strike": quote.strike,
            "bid": quote.bid if quote.bid is not None else 0.0,
            "ask": quote.ask if quote.ask is not None else 0.0,
            "volume": quote.volume,
            "openInterest": quote.open_interest,
            "impliedVolatility": (
                quote.implied_volatility if quote.implied_volatility is not None else 0.0
            ),
            "delta": quote.delta,
            "gamma": quote.gamma,
            "theta": quote.theta,
            "vega": quote.vega,
        }
        for quote in quotes
    ]
    return pd.DataFrame(rows, columns=_FRAME_COLUMNS)


@dataclass
class ChainData:
    """Provider-level chain payload (mirrors the yfinance namedtuple API)."""

    calls: pd.DataFrame
    puts: pd.DataFrame
    source: str
    greeks_are_native: bool = False
    spot: float = 0.0


def chain_to_chaindata(chain: OptionsChain) -> ChainData:
    """Bridge a normalised :class:`OptionsChain` to pipeline DataFrames."""
    return ChainData(
        calls=_quotes_to_frame(chain.quotes_for(OptionRight.CALL)),
        puts=_quotes_to_frame(chain.quotes_for(OptionRight.PUT)),
        source=chain.source,
        greeks_are_native=chain.greeks_are_native,
        spot=chain.spot,
    )
