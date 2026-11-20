"""Corporate events: next earnings window, ex-dividend date, dividend yield (fraction).

Source: the yfinance ``info`` dict (6 h cache in the DataProvider). Rules:

- ``next_earnings`` comes from ``earningsTimestampStart``/``earningsTimestampEnd``
  (aware datetimes in the exchange timezone). A window in the past is the
  *last* earnings, not the next one: ``next_earnings`` is then ``None`` and a
  warning says that the vendor has not published the next date.
- ``ex_dividend_date`` is a calendar date. Yahoo stores it at 00:00 UTC.
- ``dividend_yield`` is a FRACTION (0.0045 is 0.45%). The candidates are
  ``trailingAnnualDividendYield`` (fraction), then ``dividendRate / spot``,
  then the ETF ``yield`` field. A value above 0.20 is rejected as a unit
  error and flagged. When the trailing and forward candidates disagree by
  more than 1.5x, the one that matches the vendor ``dividendYield`` (a
  PERCENT in yfinance 1.5.1, used only as a cross-check) wins, else the
  forward one; ``dividend_yield_conflict`` is then True.
- ``dividendYield`` itself is never returned as a fraction.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data import market_calendar as mcal
from trading_mcp.timeutil import epoch_to_iso, from_epoch, iso, utc_now

MAX_DIVIDEND_YIELD = 0.20
_CONFLICT_RATIO = 1.5
_SOURCE = "yfinance:info"


class EarningsWindow(BaseModel):
    """Announcement window of the next earnings release."""

    start: str | None = None
    end: str | None = None
    is_estimate: bool | None = None
    timing: str | None = Field(default=None, description="before_open | during_session | after_close | unknown_time")
    days_until: float | None = None
    source_keys: list[str] = Field(default_factory=list)


class CorporateEvents(BaseModel):
    """Corporate events of one ticker (see the module docstring)."""

    ticker: str
    exchange: str | None = None
    quote_type: str | None = None
    currency: str | None = None
    next_earnings: EarningsWindow | None = None
    last_earnings: str | None = None
    ex_dividend_date: str | None = None
    ex_dividend_in_future: bool | None = None
    dividend_payment_date: str | None = None
    dividend_rate: float | None = None
    trailing_annual_dividend_rate: float | None = None
    dividend_yield: float | None = Field(default=None, description="FRACTION, 0.0045 = 0.45%")
    dividend_yield_source: str | None = None
    forward_dividend_yield: float | None = None
    trailing_dividend_yield: float | None = None
    dividend_yield_conflict: bool = False
    spot_used: float | None = None
    spot_as_of: str | None = None
    spot_source: str | None = None
    source: str = _SOURCE
    as_of: str | None = Field(default=None, description="Data time of the info snapshot")
    fetched_at: str | None = None
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_kind: str | None = None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _event_date(seconds: Any, ex: mcal.Exchange) -> str | None:
    """Calendar date of a vendor date stamp (00:00 UTC stamps keep the UTC date)."""
    moment = from_epoch(seconds)
    if moment is None:
        return None
    if moment.time() == time(0, 0):
        return moment.date().isoformat()
    return moment.astimezone(ex.zone).date().isoformat()


def _timing(moment: datetime, ex: mcal.Exchange) -> str:
    local = moment.astimezone(ex.zone)
    if ex.always_open or local.time() == time(0, 0):
        return "unknown_time"
    if local.time() < ex.open:
        return "before_open"
    if local.time() >= ex.close:
        return "after_close"
    return "during_session"


def _earnings(info: dict[str, Any], ex: mcal.Exchange, now: datetime, out: CorporateEvents) -> None:
    start = from_epoch(info.get("earningsTimestampStart"))
    end = from_epoch(info.get("earningsTimestampEnd"))
    single = from_epoch(info.get("earningsTimestamp"))
    keys = [k for k in ("earningsTimestampStart", "earningsTimestampEnd") if info.get(k) is not None]
    if start is None and end is not None:
        start = end
    if end is None and start is not None:
        end = start
    if start is None and single is not None and single > now:
        start = end = single
        keys = ["earningsTimestamp"]
    if single is not None and single <= now:
        out.last_earnings = iso(single, tz=ex.zone)
    if start is None:
        if out.quote_type == "EQUITY":
            out.warnings.append("next earnings date not published by the vendor")
            out.degraded = True
        return
    if end is not None and end < now:
        out.last_earnings = out.last_earnings or iso(end, tz=ex.zone)
        if out.quote_type == "EQUITY":
            out.warnings.append(
                f"vendor earnings window {iso(start, tz=ex.zone)} is in the past; next date not published"
            )
            out.degraded = True
        return
    out.next_earnings = EarningsWindow(
        start=iso(start, tz=ex.zone),
        end=iso(end, tz=ex.zone) if end is not None else None,
        is_estimate=info.get("isEarningsDateEstimate") if isinstance(info.get("isEarningsDateEstimate"), bool) else None,
        timing=_timing(start, ex),
        days_until=round((start - now).total_seconds() / 86400.0, 3),
        source_keys=keys,
    )


def _check(name: str, value: float | None, out: CorporateEvents) -> float | None:
    if value is None:
        return None
    if value < 0:
        out.warnings.append(f"{name} {value} is negative; ignored")
        return None
    if value > MAX_DIVIDEND_YIELD:
        out.warnings.append(f"{name} {value:.4f} > {MAX_DIVIDEND_YIELD:.2f} rejected as a unit error")
        out.degraded = True
        return None
    return value


def _dividend_yield(info: dict[str, Any], out: CorporateEvents) -> None:
    trailing = _check("trailingAnnualDividendYield", _finite(info.get("trailingAnnualDividendYield")), out)
    forward = None
    if out.dividend_rate is not None and out.spot_used is not None:
        forward = _check("dividendRate/spot", out.dividend_rate / out.spot_used, out)
    etf_yield = _check("yield", _finite(info.get("yield")), out)
    vendor_pct = _finite(info.get("dividendYield"))
    reference = vendor_pct / 100.0 if vendor_pct is not None and 0 <= vendor_pct / 100.0 <= MAX_DIVIDEND_YIELD else None
    out.trailing_dividend_yield = round(trailing, 8) if trailing is not None else None
    out.forward_dividend_yield = round(forward, 8) if forward is not None else None

    choice: tuple[str, float] | None = None
    if trailing is not None and forward is not None:
        low, high = sorted((trailing, forward))
        if high > 0 and (low == 0 or high / low > _CONFLICT_RATIO):
            out.dividend_yield_conflict = True
            options = {"trailingAnnualDividendYield": trailing, "dividendRate/spot": forward}
            if reference is not None:
                choice = min(options.items(), key=lambda item: abs(item[1] - reference))
            else:
                choice = ("dividendRate/spot", forward)
            out.warnings.append(
                f"trailing ({trailing:.4f}) and forward ({forward:.4f}) dividend yields disagree; "
                f"{choice[0]} used"
            )
        else:
            choice = ("trailingAnnualDividendYield", trailing)
    elif trailing is not None:
        choice = ("trailingAnnualDividendYield", trailing)
    elif forward is not None:
        choice = ("dividendRate/spot", forward)
    elif etf_yield is not None:
        choice = ("yield", etf_yield)
    if choice is None:
        out.warnings.append("dividend yield unavailable")
        out.degraded = True
        return
    out.dividend_yield_source, out.dividend_yield = choice[0], round(choice[1], 8)


def parse_corporate_events(
    ticker: str,
    info: dict[str, Any] | None,
    *,
    spot: float | None = None,
    spot_as_of: str | None = None,
    spot_source: str | None = None,
    now: datetime | None = None,
) -> CorporateEvents:
    """Build :class:`CorporateEvents` from an ``info`` dict (pure; no network).

    Args:
        ticker: Yahoo symbol.
        info: yfinance ``info`` (a recorded payload in tests).
        spot: Spot price for ``dividendRate / spot``; the info snapshot price
            is used when ``None``.
        spot_as_of: Data time of ``spot``.
        spot_source: Source label of ``spot``.
        now: Reference time (default: now, UTC).
    """
    moment = now or utc_now()
    ex = mcal.exchange_for(ticker)
    info = info or {}
    out = CorporateEvents(ticker=ticker.upper(), exchange=ex.code)
    if not info:
        out.error, out.error_kind, out.degraded = "info unavailable", "upstream", True
        return out
    out.quote_type = info.get("quoteType")
    out.currency = info.get("currency")
    out.as_of = epoch_to_iso(info.get("regularMarketTime"), ex.zone)
    out.fetched_at = info.get("_fetched_at")
    if spot is None:
        spot = _positive(info.get("regularMarketPrice")) or _positive(info.get("currentPrice"))
        spot_as_of, spot_source = out.as_of, _SOURCE
    out.spot_used, out.spot_as_of, out.spot_source = _positive(spot), spot_as_of, spot_source

    _earnings(info, ex, moment, out)

    out.ex_dividend_date = _event_date(info.get("exDividendDate"), ex)
    if out.ex_dividend_date is not None:
        today = moment.astimezone(ex.zone).date().isoformat()
        out.ex_dividend_in_future = out.ex_dividend_date > today
    out.dividend_payment_date = _event_date(info.get("dividendDate"), ex)
    out.dividend_rate = _positive(info.get("dividendRate"))
    out.trailing_annual_dividend_rate = _finite(info.get("trailingAnnualDividendRate"))
    if out.quote_type in ("INDEX", "CRYPTOCURRENCY", "CURRENCY", "FUTURE"):
        out.dividend_yield, out.dividend_yield_source = None, None
        return out
    _dividend_yield(info, out)
    return out


def get_corporate_events(
    ticker: str,
    *,
    provider: Any | None = None,
    spot: float | None = None,
    spot_as_of: str | None = None,
    spot_source: str | None = None,
    use_quote: bool = True,
    now: datetime | None = None,
) -> CorporateEvents:
    """Corporate events of ``ticker`` from the DataProvider (info + quote).

    Args:
        ticker: Yahoo symbol.
        provider: DataProvider (default: the module singleton).
        spot: Spot already known by the caller (avoids a quote request).
        spot_as_of: Data time of ``spot``.
        spot_source: Source label of ``spot``.
        use_quote: Read the spot from :meth:`DataProvider.get_quote` when
            ``spot`` is ``None``.
        now: Reference time (tests).
    """
    if provider is None:
        from trading_mcp.data.provider import data_provider as provider  # pylint: disable=import-outside-toplevel
    info, meta = provider.get_info_with_meta(ticker)
    if spot is not None and spot_source is None:
        spot_source = "caller"
    if spot is None and use_quote:
        quote = provider.get_quote(ticker)
        if quote.price is not None:
            spot, spot_as_of, spot_source = quote.price, quote.as_of, quote.source
    events = parse_corporate_events(ticker, info, spot=spot, spot_as_of=spot_as_of,
                                    spot_source=spot_source, now=now)
    if meta.error and not info:
        events.error, events.error_kind = meta.error, meta.error_kind
    if meta.stale:
        events.warnings.append("info served from an expired cache entry after an upstream failure")
        events.degraded = True
    if events.fetched_at is None:
        events.fetched_at = meta.fetched_at
    events.source = info.get("_source") or _SOURCE
    return events
