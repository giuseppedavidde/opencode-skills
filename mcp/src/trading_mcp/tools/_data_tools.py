"""MCP tool registration: data fetch tools (stock and crypto)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastmcp import FastMCP

from trading_mcp.data.crypto import fetch_crypto_full
from trading_mcp.data.events import get_corporate_events
from trading_mcp.data.fundamentals_schema import debt_to_equity_ratio
from trading_mcp.data.quotes import Quote
from trading_mcp.data.stocks import fetch_stock_full
from trading_mcp.responses import (
    typed,
    CryptoDataResponse,
    StockDataResponse,
    error_payload,
)

VALID_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")
STOCK_SECTIONS = ("quote", "ohlcv", "info", "indicators", "events")
CRYPTO_SECTIONS = ("quote", "ohlcv", "market")
MAX_BARS_LIMIT = 2000
_NOT_RETRYABLE = {"not_found", "unresolved", "invalid_request"}

# Curated ``info`` keys (yfinance names) and their units. Prices and
# percent-coded vendor fields are left out on purpose: prices come from the
# quote, and ``dividendYield``/``debtToEquity`` are percents in yfinance.
CURATED_INFO_UNITS: dict[str, str] = {
    "longName": "text", "shortName": "text", "sector": "text", "industry": "text", "country": "text",
    "currency": "ISO 4217", "financialCurrency": "ISO 4217", "exchange": "text",
    "fullExchangeName": "text", "quoteType": "text",
    "marketCap": "currency", "sharesOutstanding": "shares", "floatShares": "shares", "beta": "ratio",
    "trailingPE": "ratio (TTM)", "forwardPE": "ratio (forward)", "priceToBook": "ratio (MRQ)",
    "trailingAnnualDividendYield": "fraction (TTM)", "payoutRatio": "fraction",
    "profitMargins": "fraction (TTM)", "operatingMargins": "fraction (TTM)",
    "revenueGrowth": "fraction (quarterly YoY)", "earningsGrowth": "fraction (quarterly YoY)",
    "returnOnEquity": "fraction (TTM)", "shortPercentOfFloat": "fraction",
    "fiftyTwoWeekHigh": "currency (raw, not adjusted)", "fiftyTwoWeekLow": "currency (raw, not adjusted)",
    "averageVolume": "shares per day (3 months)", "averageVolume10days": "shares per day (10 days)",
    "targetMeanPrice": "currency", "numberOfAnalystOpinions": "count", "recommendationKey": "text",
}
_QUOTE_FIELDS = ("symbol", "price", "bid", "ask", "mid", "currency", "previous_close", "as_of", "source",
                 "session_state", "market_state", "age_s", "freshness", "stale", "delayed_by_min",
                 "fetched_at", "extended_price", "extended_as_of", "extended_session", "error", "error_kind")


def _sections(fields: list[str] | str | None, allowed: tuple[str, ...], warnings: list[str]) -> list[str]:
    if fields is None:
        return list(allowed)
    requested = [f.strip().lower() for f in (fields.split(",") if isinstance(fields, str) else fields) if f.strip()]
    unknown = [f for f in requested if f not in allowed]
    if unknown:
        warnings.append(f"unknown fields ignored: {unknown}; allowed: {list(allowed)}")
    return [f for f in allowed if f in requested]


def _bar_limit(max_bars: int, warnings: list[str]) -> int:
    limit = max(1, min(int(max_bars), MAX_BARS_LIMIT))
    if limit != max_bars:
        warnings.append(f"max_bars clamped to {limit} (allowed 1..{MAX_BARS_LIMIT})")
    return limit


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4) if abs(number) >= 1 else round(number, 8)


def _bars(hist: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    has_adj = "Adj Close" in hist.columns
    for idx, row in hist.iterrows():
        volume = row.get("Volume")
        out.append({
            "date": idx.date().isoformat(),
            "open": _price(row["Open"]),
            "high": _price(row["High"]),
            "low": _price(row["Low"]),
            "close": _price(row["Close"]),
            "adj_close": _price(row["Adj Close"]) if has_adj else None,
            "volume": int(volume) if volume is not None and pd.notna(volume) else None,
        })
    return [bar for bar in out if None not in (bar["open"], bar["high"], bar["low"], bar["close"])]


def _quote_block(quote: Quote) -> dict[str, Any]:
    data = quote.model_dump()
    return {key: data.get(key) for key in _QUOTE_FIELDS}


def _retryable(kind: str | None) -> bool:
    return kind not in _NOT_RETRYABLE


def _curated_info(info: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    curated: dict[str, Any] = {}
    units: dict[str, str] = {}
    for key, unit in CURATED_INFO_UNITS.items():
        value = info.get(key)
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            continue
        curated[key] = value.item() if hasattr(value, "item") else value
        units[key] = unit
    ratio = debt_to_equity_ratio(info)
    if ratio is not None:
        curated["debt_to_equity_ratio"] = round(ratio, 4)
        units["debt_to_equity_ratio"] = "ratio (MRQ), from yfinance debtToEquity percent"
    return curated, units


def register_data_tools(mcp_server: FastMCP) -> None:
    """Register data fetch tools with the MCP server."""

    @mcp_server.tool()
    @typed(StockDataResponse)
    def fetch_stock_data(
        ticker: str,
        period: str = "1y",
        fields: list[str] | None = None,
        max_bars: int = 252,
    ) -> StockDataResponse:
        """Stock quote, complete daily OHLCV bars, curated fundamentals, indicators and corporate events.

        current_price comes from the quote (yfinance chart, data time in
        quote.as_of, freshness realtime/delayed/last_close/stale); it is null
        when no quote exists, never 0. Bars are complete sessions only
        (the open session bar is dropped): open/high/low/close are
        split-adjusted raw prices (they match broker charts) and adj_close
        also carries dividends. info is a curated subset with units in
        info_units (fractions, ratios, currency). events gives the next
        earnings window, ex-dividend date and dividend_yield as a fraction.

        Args:
            ticker: Yahoo symbol (e.g. 'AAPL', 'ENI.MI').
            period: History period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max.
            fields: Sections to return (default all): quote, ohlcv, info, indicators, events.
            max_bars: Newest bars to return (1..2000, default 252); see bars_available and truncated.
        """
        symbol = ticker.strip().upper()
        warnings: list[str] = []
        if period not in VALID_PERIODS:
            return error_payload(f"period must be one of {list(VALID_PERIODS)}", data_source="yfinance",
                                 ticker=symbol)
        sections = _sections(fields, STOCK_SECTIONS, warnings)
        limit = _bar_limit(max_bars, warnings)
        full = fetch_stock_full(symbol, period, include_info=bool({"info", "events"} & set(sections)))
        quote: Quote = full["quote"]
        hist: pd.DataFrame = full["hist"]
        meta = full["hist_meta"]
        info, info_meta = full["info"], full["info_meta"]
        if quote.price is None and hist.empty:
            kind = quote.error_kind or meta.error_kind
            return error_payload(
                f"No quote and no bars for '{symbol}': {quote.error or meta.error or 'no data'}",
                retryable=_retryable(kind), data_source="yfinance", ticker=symbol,
                warnings=warnings, sources=["yfinance"],
            )
        degraded = False
        sources = [s for s in (quote.source if quote.price is not None else None, meta.source) if s]
        if quote.price is None:
            degraded = True
            warnings.append(f"quote unavailable ({quote.error_kind}): current_price is null")
        elif quote.stale:
            warnings.append(f"quote freshness is {quote.freshness} (age {quote.age_s} s)")
        warnings.extend(quote.warnings)
        if hist.empty:
            degraded = True
            warnings.append(f"bars unavailable ({meta.error_kind})")
        elif meta.stale or meta.up_to_date is False:
            degraded = True
            warnings.append(f"bars end at {meta.last_bar_date}; the latest complete session is {meta.last_complete_session}")
        warnings.extend(meta.warnings)

        payload: dict[str, Any] = {
            "ticker": symbol,
            "current_price": quote.price,
            "as_of": quote.as_of if quote.price is not None else meta.as_of,
            "fields": sections,
            "bars_as_of": meta.as_of,
            "partial_bar_dropped": meta.partial_dropped,
            "price_adjustment": meta.price_adjustment,
            "data_quality": f"daily_complete_bars; quote {quote.freshness}",
        }
        if "quote" in sections:
            payload["quote"] = _quote_block(quote)
        if "ohlcv" in sections:
            bars = _bars(hist) if not hist.empty else []
            payload.update(ohlcv=bars[-limit:], bars_available=len(bars),
                           bars_returned=min(len(bars), limit), truncated=len(bars) > limit)
        if "info" in sections:
            curated, units = _curated_info(info)
            payload.update(info=curated, info_units=units, info_as_of=info_meta.as_of)
            if info:
                sources.append(str(info.get("_source") or "yfinance:info"))
            else:
                degraded = True
                warnings.append(f"info unavailable ({info_meta.error_kind})")
        if "indicators" in sections:
            payload["indicators"] = {**full["indicators"], "as_of": meta.as_of,
                                     "basis": "raw close of complete sessions"}
        if "events" in sections:
            events = get_corporate_events(symbol, spot=quote.price, spot_as_of=quote.as_of,
                                          spot_source=quote.source)
            payload["events"] = events.model_dump(mode="json")
            warnings.extend(f"events: {w}" for w in events.warnings)
            if events.error:
                degraded = True
        payload["sources"] = sorted(set(sources))
        payload["degraded"] = degraded
        payload["warnings"] = warnings
        return payload

    @mcp_server.tool()
    @typed(CryptoDataResponse)
    def fetch_crypto_data(
        coin_id: str,
        period: str = "1y",
        fields: list[str] | None = None,
        max_bars: int = 365,
    ) -> CryptoDataResponse:
        """Crypto price, CoinGecko market data and complete daily bars (UTC days).

        current_price_usd comes from the Yahoo quote (as_of = vendor data
        time), else from CoinGecko; it is null when no source answers, never
        0. symbol is the Yahoo symbol used (symbol_source tells how it was
        mapped; for example Uniswap is UNI7083-USD). Bars are complete UTC
        days (the current day is dropped). market_cap and total_volume are
        USD from CoinGecko (as of market_data_as_of; cached 60 s).

        Args:
            coin_id: CoinGecko id (e.g. 'bitcoin', 'ethereum') or Yahoo symbol (e.g. 'BTC-USD').
            period: History period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max.
            fields: Sections to return (default all): quote, ohlcv, market.
            max_bars: Newest bars to return (1..2000, default 365).
        """
        warnings: list[str] = []
        if period not in VALID_PERIODS:
            return error_payload(f"period must be one of {list(VALID_PERIODS)}", data_source="coingecko+yfinance",
                                 coin_id=coin_id)
        sections = _sections(fields, CRYPTO_SECTIONS, warnings)
        limit = _bar_limit(max_bars, warnings)
        full = fetch_crypto_full(coin_id, period)
        warnings.extend(full["warnings"])
        if full["error"]:
            return error_payload(full["error"], retryable=_retryable(full["error_kind"]),
                                 data_source="coingecko+yfinance", coin_id=coin_id,
                                 symbol=full["symbol"], warnings=warnings)
        quote: Quote = full["quote"]
        hist: pd.DataFrame = full["hist"]
        meta = full["hist_meta"]
        degraded = bool(full["warnings"]) or full["current_price_usd"] is None or hist.empty
        payload: dict[str, Any] = {
            "coin_id": coin_id,
            "symbol": full["symbol"],
            "symbol_source": full["symbol_source"],
            "current_price_usd": full["current_price_usd"],
            "price_source": full["price_source"],
            "as_of": full["price_as_of"],
            "fields": sections,
            "bars_as_of": meta.as_of if meta is not None else None,
            "sources": sorted({s for s in (full["price_source"], meta.source if meta else None,
                                           "coingecko:/coins" if full["coingecko"] else None) if s}),
        }
        if "quote" in sections and quote is not None:
            payload["quote"] = _quote_block(quote)
        if "market" in sections:
            payload.update(market_cap=full["market_cap"], total_volume=full["total_volume"],
                           market_data_as_of=full["market_data_as_of"])
        if "ohlcv" in sections:
            bars = _bars(hist) if not hist.empty else []
            payload.update(ohlcv=bars[-limit:], bars_available=len(bars),
                           bars_returned=min(len(bars), limit), truncated=len(bars) > limit)
        payload["degraded"] = degraded
        payload["warnings"] = warnings
        return payload
