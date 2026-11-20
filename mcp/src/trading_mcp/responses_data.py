"""Wire models of the data tools (``fetch_stock_data``, ``fetch_crypto_data``)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from trading_mcp.responses import PayloadModel, QuoteStamp, ToolResponse


class OhlcvBar(PayloadModel):
    """One daily OHLCV bar.

    ``open/high/low/close`` are split-adjusted raw prices (they match broker
    charts); ``adj_close`` also carries dividends (use it for returns).
    """

    date: str
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    volume: int | None = None


class StockDataResponse(ToolResponse):
    """Output of ``fetch_stock_data``.

    ``current_price`` comes from ``quote`` (never from ``info``); ``null``
    when no quote is available. ``ohlcv`` holds complete sessions only
    (``partial_bar_dropped``); ``bars_available``/``bars_returned``/
    ``truncated`` describe the cut to ``max_bars``. ``info`` is a curated
    subset with units in ``info_units``.
    """
    data_source: str = "yfinance"
    data_quality: str = "daily_complete_bars"

    ticker: str
    current_price: float | None = None
    quote: QuoteStamp | None = None
    ohlcv: list[OhlcvBar] = Field(default_factory=list)
    bars_available: int | None = None
    bars_returned: int = 0
    truncated: bool = False
    bars_as_of: str | None = None
    partial_bar_dropped: bool | None = None
    price_adjustment: str | None = None
    info: dict[str, Any] = Field(default_factory=dict)
    info_units: dict[str, str] = Field(default_factory=dict)
    info_as_of: str | None = None
    indicators: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] | None = None
    fields: list[str] = Field(default_factory=list)
    error: str | None = None


class CryptoDataResponse(ToolResponse):
    """Output of ``fetch_crypto_data``.

    ``symbol`` is the Yahoo symbol used for bars and quotes
    (``symbol_source`` says how it was resolved). ``current_price_usd`` is
    ``null`` when no price source answers, never ``0.0``.
    """
    data_source: str = "coingecko+yfinance"
    data_quality: str = "daily_complete_bars"

    coin_id: str
    symbol: str | None = None
    symbol_source: str | None = None
    current_price_usd: float | None = None
    price_source: str | None = None
    quote: QuoteStamp | None = None
    market_cap: float | None = None
    total_volume: float | None = None
    market_data_as_of: str | None = None
    ohlcv: list[OhlcvBar] = Field(default_factory=list)
    bars_available: int | None = None
    bars_returned: int = 0
    truncated: bool = False
    bars_as_of: str | None = None
    fields: list[str] = Field(default_factory=list)
    error: str | None = None
