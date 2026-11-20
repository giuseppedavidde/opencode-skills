"""Dividend model for option pricing: a discrete schedule or a continuous yield.

Sources: :func:`trading_mcp.data.events.get_corporate_events` (dividend yield as
a FRACTION, last ex-dividend date, forward annual rate) plus the yfinance
``info`` keys ``lastDividendValue`` and ``dividendRate``. Rules:

- ``discrete``: when the payment amount and frequency are known, the ex-dates
  before the horizon form a cash schedule for the escrowed-dividend model.
  An ex-date that the vendor publishes in the future is ``announced``; the
  later ones are ``projected`` (last ex-date plus whole periods). The pricer
  then uses ``q = 0`` so the same dividends are not counted twice.
- ``continuous``: the vendor yield (fraction) as ``q`` when no schedule can be
  built, and for cash indices.
- ``none``: the vendor reports no dividend (yield 0, no rate, no ex-date).
- An unknown dividend is never invented silently: ``q = 0`` is used with
  ``assumed = True`` and a warning, and the caller marks its answer degraded.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data import market_calendar as mcal

STANDARD_FREQUENCIES = (1, 2, 4, 12)
_FREQUENCY_TOLERANCE = 0.2
_MAX_YIELD = 0.20


class DividendEvent(BaseModel):
    """One cash dividend inside the pricing horizon."""

    ex_date: str
    amount: float
    status: str = Field(description="announced | projected")
    source: str


class DividendModel(BaseModel):
    """Dividend inputs of the pricer (see the module docstring)."""

    model: str = Field(description="discrete | continuous | none")
    q: float = Field(description="Continuous yield used by the pricer (decimal); 0 with the discrete model")
    q_source: str
    dividend_yield: float | None = Field(default=None, description="Vendor yield, FRACTION (0.004 = 0.4%)")
    dividend_yield_source: str | None = None
    frequency_per_year: int | None = None
    amount_per_payment: float | None = None
    amount_source: str | None = None
    events: list[DividendEvent] = Field(default_factory=list)
    next_ex_date: str | None = None
    last_ex_date: str | None = None
    assumed: bool = False
    warnings: list[str] = Field(default_factory=list)

    def schedule(self, ticker: str, now: datetime) -> tuple[list[float], list[float]]:
        """Ex-times (years from ``now``) and cash amounts of the future dividends."""
        times: list[float] = []
        amounts: list[float] = []
        for event in self.events:
            moment = ex_time(ticker, date.fromisoformat(event.ex_date))
            years = mcal.year_fraction(now, moment)
            if years > 0.0:
                times.append(years)
                amounts.append(float(event.amount))
        return times, amounts

    def equivalent_yield(self, spot: float, T: float, r: float, ticker: str, now: datetime) -> float | None:
        """Continuous yield with the same present value as the schedule (information only)."""
        if self.model != "discrete":
            return self.q
        if spot <= 0.0 or T <= 0.0:
            return None
        times, amounts = self.schedule(ticker, now)
        pv = sum(a * math.exp(-r * t) for t, a in zip(times, amounts) if t < T)
        if pv <= 0.0:
            return 0.0
        if pv >= spot:
            return None
        return -math.log(1.0 - pv / spot) / T


def ex_time(ticker: str, day: date) -> datetime:
    """The stock trades ex-dividend from the regular open of the ex-date."""
    opened = mcal.session_open(ticker, day)
    if opened is not None:
        return opened
    ex = mcal.exchange_for(ticker)
    return datetime.combine(day, ex.open if not ex.always_open else time(0, 0), tzinfo=ex.zone)


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    month += 1
    for candidate in range(day.day, 27, -1):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue
    return date(year, month, min(day.day, 28))


def infer_frequency(annual_rate: float | None, last_amount: float | None) -> int | None:
    """Payments per year from the annual rate and the last payment (``None`` when unclear)."""
    if annual_rate is None or last_amount is None or last_amount <= 0:
        return None
    ratio = annual_rate / last_amount
    best = min(STANDARD_FREQUENCIES, key=lambda f: abs(ratio - f))
    return best if abs(ratio - best) <= _FREQUENCY_TOLERANCE * best else None


def _continuous(events: Any, warnings: list[str]) -> DividendModel:
    yield_value = getattr(events, "dividend_yield", None) if events is not None else None
    source = getattr(events, "dividend_yield_source", None) if events is not None else None
    if yield_value is None:
        warnings.append(
            "dividend yield unknown: q = 0 assumed; calls are overpriced and puts underpriced "
            "if the stock pays dividends"
        )
        return DividendModel(model="continuous", q=0.0, q_source="assumed_zero", assumed=True,
                             warnings=warnings)
    return DividendModel(
        model="continuous" if yield_value > 0 else "none",
        q=float(yield_value),
        q_source=f"events.dividend_yield ({source})" if source else "events.dividend_yield",
        dividend_yield=float(yield_value),
        dividend_yield_source=source,
        warnings=warnings,
    )


def build_dividend_model(
    ticker: str,
    events: Any,
    info: dict[str, Any] | None,
    horizon: date,
    now: datetime,
) -> DividendModel:
    """Dividend inputs for options that expire on or before ``horizon``.

    Args:
        ticker: Yahoo symbol.
        events: :class:`~trading_mcp.data.events.CorporateEvents` (or ``None``).
        info: yfinance ``info`` dict (``lastDividendValue``, ``dividendRate``).
        horizon: Last expiry date of the position.
        now: Valuation time (aware).
    """
    warnings: list[str] = []
    info = info or {}
    quote_type = getattr(events, "quote_type", None) or info.get("quoteType")
    if quote_type in ("INDEX",):
        model = _continuous(events, warnings)
        if model.assumed:
            model.q_source = "assumed_zero (cash index: use the put-call parity carry when available)"
        return model
    annual = _positive(getattr(events, "dividend_rate", None)) or _positive(info.get("dividendRate"))
    last_amount = _positive(info.get("lastDividendValue"))
    trailing_rate = _positive(getattr(events, "trailing_annual_dividend_rate", None))
    yield_value = getattr(events, "dividend_yield", None)
    ex_text = getattr(events, "ex_dividend_date", None)
    if annual is None and last_amount is None and not ex_text and yield_value == 0.0:
        return DividendModel(model="none", q=0.0, q_source="vendor reports no dividend",
                             dividend_yield=0.0,
                             dividend_yield_source=getattr(events, "dividend_yield_source", None))
    frequency = infer_frequency(annual, last_amount) or infer_frequency(trailing_rate, last_amount)
    spot = getattr(events, "spot_used", None)
    if frequency is None or not ex_text:
        if annual is not None or last_amount is not None:
            warnings.append("dividend frequency or ex-date unknown: continuous yield used instead of a schedule")
        return _continuous(events, warnings)
    amount = annual / frequency if annual is not None else last_amount
    amount_source = "dividendRate / frequency" if annual is not None else "lastDividendValue"
    if spot and amount * frequency / spot > _MAX_YIELD:
        warnings.append("dividend schedule rejected: annual amount above 20% of spot")
        return _continuous(events, warnings)
    today = mcal.exchange_today(ticker, now)
    anchor = date.fromisoformat(str(ex_text)[:10])
    step = 12 // frequency
    out: list[DividendEvent] = []
    if anchor > today:
        out.append(DividendEvent(ex_date=anchor.isoformat(), amount=round(amount, 6), status="announced",
                                 source=f"exDividendDate; amount {amount_source}"))
    candidate = anchor
    for _ in range(240):
        candidate = _add_months(candidate, step)
        if candidate > horizon:
            break
        if candidate <= today:
            continue
        out.append(DividendEvent(ex_date=candidate.isoformat(), amount=round(amount, 6), status="projected",
                                 source=f"last ex-date + {step} months; amount {amount_source}"))
    out = [event for event in out if date.fromisoformat(event.ex_date) <= horizon]
    future = [event.ex_date for event in out] or [
        d.isoformat() for d in [_next_after(anchor, step, today)] if d is not None
    ]
    return DividendModel(
        model="discrete",
        q=0.0,
        q_source="discrete schedule (escrowed); q = 0",
        dividend_yield=yield_value,
        dividend_yield_source=getattr(events, "dividend_yield_source", None),
        frequency_per_year=frequency,
        amount_per_payment=round(amount, 6),
        amount_source=amount_source,
        events=out,
        next_ex_date=future[0] if future else None,
        last_ex_date=anchor.isoformat() if anchor <= today else None,
        warnings=warnings,
    )


def _next_after(anchor: date, step: int, today: date) -> date | None:
    candidate = anchor
    if candidate > today:
        return candidate
    for _ in range(240):
        candidate = _add_months(candidate, step)
        if candidate > today:
            return candidate
    return None


def ex_dividend_between(model: DividendModel, start: date, end: date) -> list[DividendEvent]:
    """Dividends with an ex-date in ``(start, end]``."""
    out = []
    for event in model.events:
        day = date.fromisoformat(event.ex_date)
        if start < day <= end:
            out.append(event)
    return out


__all__ = [
    "DividendEvent",
    "DividendModel",
    "build_dividend_model",
    "ex_dividend_between",
    "ex_time",
    "infer_frequency",
]

