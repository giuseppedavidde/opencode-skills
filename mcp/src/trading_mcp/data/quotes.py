"""Quote snapshots: last price with its data time, source and freshness.

A quote never uses the fetch time as its data time. ``as_of`` comes from
Yahoo's ``regularMarketTime`` (chart metadata or the v7 quote inside
``info``). When the vendor gives no time, ``as_of`` is ``None``, the
freshness is ``unknown`` and the quote is ``stale``.

Freshness is computed when the quote is read, never when it is cached:

- ``realtime``: regular session and ``age_s`` <= 60.
- ``delayed``: regular session and the age stays inside the declared vendor
  delay (``delayed_by_min``) plus 5 minutes (Yahoo serves ^VIX and most
  European venues about 15 to 17 minutes late).
- ``last_close``: outside the regular session and the price is the close of
  the latest complete session (normal overnight, weekend and holiday state).
- ``stale``: anything older; ``unknown``: no data time.

``stale`` is True for ``stale`` and ``unknown``. Option math must still check
``age_s`` itself (for example: block when ``age_s > 60`` in the session).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data import market_calendar as mcal
from trading_mcp.timeutil import epoch_to_iso, iso, to_datetime

SOURCE_YF_CHART = "yfinance:chart"
SOURCE_YF_QUOTE = "yfinance:quote"

QUOTE_MAX_AGE_S = 60.0
DELAYED_MARGIN_S = 300.0
_CLOSE_TOLERANCE = timedelta(minutes=10)


class Quote(BaseModel):
    """Last-price snapshot for one symbol (see the module docstring)."""

    symbol: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    currency: str | None = None
    previous_close: float | None = None
    as_of: str | None = Field(default=None, description="Data time of price (ISO 8601 with offset)")
    source: str = "unknown"
    exchange: str | None = None
    session_state: str | None = None
    market_state: str | None = None
    delayed_by_min: float | None = None
    fetched_at: str | None = None
    age_s: float | None = None
    freshness: str = "unknown"
    stale: bool = True
    extended_price: float | None = None
    extended_as_of: str | None = None
    extended_session: str | None = None
    cached: bool = False
    error: str | None = None
    error_kind: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the quote carries a price."""
        return self.price is not None and self.error is None


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _size(value: Any) -> int | None:
    number = _positive(value)
    return int(number) if number is not None else None


def fields_from_chart_meta(symbol: str, meta: dict[str, Any] | None, frame: Any = None) -> dict[str, Any]:
    """Quote fields from Yahoo chart metadata (``regularMarketPrice/Time``).

    ``frame`` (daily bars of the same response) gives ``previous_close``: the
    last bar dated before the quote day.
    """
    meta = meta or {}
    ex = mcal.exchange_for(symbol)
    as_of = epoch_to_iso(meta.get("regularMarketTime"), ex.zone)
    previous_close = None
    if frame is not None and as_of is not None and not getattr(frame, "empty", True) and "Close" in frame:
        quote_day = to_datetime(as_of).astimezone(ex.zone).date()  # type: ignore[union-attr]
        earlier = [
            float(close) for ts, close in zip(frame.index, frame["Close"])
            if ts.date() < quote_day and _positive(close) is not None
        ]
        previous_close = earlier[-1] if earlier else None
    return {
        "symbol": symbol,
        "price": _positive(meta.get("regularMarketPrice")),
        "currency": meta.get("currency"),
        "previous_close": previous_close,
        "as_of": as_of,
        "source": SOURCE_YF_CHART,
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
    }


def fields_from_info(symbol: str, info: dict[str, Any] | None) -> dict[str, Any]:
    """Quote fields from a yfinance ``info`` dict (v7 quote endpoint fields)."""
    info = info or {}
    ex = mcal.exchange_for(symbol)
    bid, ask = _positive(info.get("bid")), _positive(info.get("ask"))
    out: dict[str, Any] = {
        "symbol": symbol,
        "price": _positive(info.get("regularMarketPrice")) or _positive(info.get("currentPrice")),
        "bid": bid,
        "ask": ask,
        "bid_size": _size(info.get("bidSize")),
        "ask_size": _size(info.get("askSize")),
        "currency": info.get("currency"),
        "previous_close": _positive(info.get("regularMarketPreviousClose")) or _positive(info.get("previousClose")),
        "as_of": epoch_to_iso(info.get("regularMarketTime"), ex.zone),
        "source": SOURCE_YF_QUOTE,
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "market_state": info.get("marketState"),
        "delayed_by_min": _positive(info.get("exchangeDataDelayedBy")),
    }
    for session, price_key, time_key in (
        ("post", "postMarketPrice", "postMarketTime"),
        ("pre", "preMarketPrice", "preMarketTime"),
    ):
        price = _positive(info.get(price_key))
        stamp = epoch_to_iso(info.get(time_key), ex.zone)
        if price is not None and stamp is not None:
            current = to_datetime(out.get("extended_as_of"))
            candidate = to_datetime(stamp)
            if current is None or (candidate is not None and candidate > current):
                out.update(extended_price=price, extended_as_of=stamp, extended_session=session)
    return out


def evaluate(fields: dict[str, Any], *, now: datetime, fetched_at: datetime | None, cached: bool) -> Quote:
    """Build a :class:`Quote` from raw fields, with freshness computed at ``now``."""
    quote = Quote(**{key: value for key, value in fields.items() if key in Quote.model_fields})
    symbol = quote.symbol
    ex = mcal.exchange_for(symbol)
    quote.session_state = mcal.session_state(ex, now)
    quote.fetched_at = iso(fetched_at) if fetched_at is not None else None
    quote.cached = cached
    if quote.bid is not None and quote.ask is not None and quote.ask >= quote.bid:
        quote.mid = round((quote.bid + quote.ask) / 2.0, 6)
    if quote.delayed_by_min is None and ex.vendor_delay_minutes:
        quote.delayed_by_min = float(ex.vendor_delay_minutes)
    moment = to_datetime(quote.as_of)
    if quote.price is None or moment is None:
        quote.freshness, quote.stale = "unknown", True
        if quote.price is not None:
            quote.warnings.append("vendor gave no quote time; the price age is unknown")
        return quote
    quote.age_s = round((now - moment).total_seconds(), 3)
    if quote.session_state == mcal.SESSION_REGULAR:
        delay_s = (quote.delayed_by_min or 0.0) * 60.0
        if quote.age_s <= QUOTE_MAX_AGE_S:
            quote.freshness = "realtime"
        elif delay_s > 0 and quote.age_s <= delay_s + DELAYED_MARGIN_S:
            quote.freshness = "delayed"
        else:
            quote.freshness = "stale"
    else:
        last_session = mcal.last_complete_session_date(ex, now)
        expected = mcal.bar_close(ex, last_session) - _CLOSE_TOLERANCE
        quote.freshness = "last_close" if moment >= expected else "stale"
    quote.stale = quote.freshness in ("stale", "unknown")
    return quote


def error_quote(symbol: str, message: str, kind: str, *, now: datetime) -> Quote:
    """A quote with no price and an explicit error."""
    return Quote(
        symbol=symbol,
        session_state=mcal.session_state(symbol, now),
        error=message,
        error_kind=kind,
        freshness="unknown",
        stale=True,
    )
