"""Shared market inputs of the options tools: spot, chains, rates, dividends, events.

One module builds the inputs of every options analysis, so all tools use the
same rules:

- **Spot** comes from :meth:`DataProvider.get_quote` with its data time and
  source. During the regular session option math is blocked when the spot is
  older than :data:`MAX_SPOT_AGE_S` (60 s) or has no data time. Outside the
  session the last close is used and labelled.
- **Chains** come from :meth:`DataProvider.get_options_chain`. Rows are
  normalised: a missing bid or ask is ``NaN`` (never 0), a zero bid stays 0
  (nobody buys), an ask of 0 is "no ask". Each chain keeps the backend id,
  ``fetched_at``, ``stale`` (expired cache served after a failure), its age
  and the vendor data time when the backend gives one.
- **Exercise style**: European for cash-settled index options, American for
  equities and ETFs. **Settlement**: AM for the standard monthly SPX, NDX and
  RUT expiries and for VIX, PM otherwise.
- **Rates**: the tenor curve (:func:`trading_mcp.data.risk_free.get_rate_curve`).
- **Dividends**: :mod:`trading_mcp.analysis.dividends` from
  :func:`trading_mcp.data.events.get_corporate_events`.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from trading_mcp.analysis import dividends as divmod_
from trading_mcp.analysis.pricing import STYLE_AMERICAN, STYLE_EUROPEAN
from trading_mcp.data import market_calendar as mcal
from trading_mcp.data import risk_free
from trading_mcp.timeutil import iso, to_datetime, utc_now

MAX_SPOT_AGE_S = 60.0
CONTRACT_MULTIPLIER = 100
EUROPEAN_INDEX = frozenset({
    "^SPX", "SPX", "^SPXW", "SPXW", "^XSP", "XSP", "^NDX", "NDX", "^NDXP", "^XND",
    "^RUT", "RUT", "^MRUT", "^VIX", "VIX", "^DJX", "DJX", "^XEO", "XEO",
})
_AM_MONTHLY = frozenset({"^SPX", "SPX", "^NDX", "NDX", "^RUT", "RUT", "^DJX", "DJX"})
_AM_ALWAYS = frozenset({"^VIX", "VIX"})


def provider() -> Any:
    """The DataProvider used by the options tools (tests replace it)."""
    from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

    return data_provider


def exercise_style(ticker: str) -> str:
    """``european`` for cash-settled index options, ``american`` otherwise."""
    return STYLE_EUROPEAN if str(ticker).upper() in EUROPEAN_INDEX else STYLE_AMERICAN


def _third_friday(day: date) -> bool:
    return day.weekday() == 4 and 15 <= day.day <= 21


def settlement(ticker: str, expiry: str | date) -> str:
    """``AM`` for standard monthly index expiries and VIX, ``PM`` otherwise."""
    symbol = str(ticker).upper()
    day = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry)[:10])
    if symbol in _AM_ALWAYS or (symbol in _AM_MONTHLY and _third_friday(day)):
        return mcal.SETTLEMENT_AM
    return mcal.SETTLEMENT_PM


class SpotCheck(BaseModel):
    """Spot quote plus the decision whether option math may use it."""

    symbol: str
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    as_of: str | None = None
    source: str | None = None
    age_s: float | None = None
    freshness: str | None = None
    session_state: str | None = None
    stale: bool | None = None
    cached: bool | None = None
    usable: bool = False
    block_reason: str | None = None
    max_age_s: float = MAX_SPOT_AGE_S
    warnings: list[str] = Field(default_factory=list)

    def stamp(self) -> dict[str, Any]:
        """Wire block (QuoteStamp fields)."""
        return self.model_dump(exclude={"max_age_s"})


def check_spot(ticker: str, *, now: datetime | None = None, source: Any = None) -> SpotCheck:
    """Read the spot quote and apply the 60-second rule of the regular session."""
    moment = now or utc_now()
    data = source if source is not None else provider()
    quote = data.get_quote(ticker)
    check = SpotCheck(
        symbol=str(ticker).upper(), price=quote.price, bid=quote.bid, ask=quote.ask,
        as_of=quote.as_of, source=quote.source, freshness=quote.freshness,
        session_state=mcal.session_state(ticker, moment), stale=quote.stale,
        cached=getattr(quote, "cached", None), warnings=list(getattr(quote, "warnings", []) or []),
    )
    stamp = to_datetime(quote.as_of)
    check.age_s = round((moment - stamp).total_seconds(), 3) if stamp is not None else None
    if quote.price is None:
        check.block_reason = f"no spot quote ({quote.error or 'vendor returned no price'})"
        return check
    if stamp is None:
        check.block_reason = "the spot quote has no data time"
        return check
    if check.session_state == mcal.SESSION_REGULAR:
        if check.age_s is not None and check.age_s > MAX_SPOT_AGE_S:
            check.block_reason = (
                f"spot is {check.age_s:.0f} s old during the regular session "
                f"(limit {MAX_SPOT_AGE_S:.0f} s); option math blocked, retry"
            )
            return check
    else:
        last_session = mcal.last_complete_session_date(ticker, moment)
        expected = mcal.bar_close(ticker, last_session)
        if (expected - stamp).total_seconds() > 600:
            check.block_reason = (
                f"spot ({quote.as_of}) is older than the last session close ({iso(expected)})"
            )
            return check
        check.warnings.append(
            f"market {check.session_state}: spot is the last price {quote.as_of}; "
            "option quotes may be from the last session"
        )
    check.usable = True
    return check


def _num(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _text(frame: pd.DataFrame, column: str) -> list[str | None]:
    if column not in frame.columns:
        return [None] * len(frame)
    out: list[str | None] = []
    for value in frame[column].tolist():
        stamp = to_datetime(value) if value is not None and not (isinstance(value, float) and math.isnan(value)) else None
        out.append(iso(stamp) if stamp is not None else None)
    return out


@dataclass
class SideQuotes:
    """One side (calls or puts) of a chain as aligned arrays, sorted by strike."""

    strike: np.ndarray
    bid: np.ndarray
    ask: np.ndarray
    last: np.ndarray
    volume: np.ndarray
    oi: np.ndarray
    vendor_iv: np.ndarray
    vendor_delta: np.ndarray
    vendor_gamma: np.ndarray
    last_trade: list[str | None]
    quote_time: list[str | None]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame | None) -> "SideQuotes":
        """Normalise a backend frame (see the module docstring)."""
        if frame is None or frame.empty or "strike" not in frame.columns:
            empty = np.zeros(0)
            return cls(empty, empty, empty, empty, empty, empty, empty, empty, empty, [], [])
        data = frame.copy()
        data["strike"] = pd.to_numeric(data["strike"], errors="coerce")
        data = data[np.isfinite(data["strike"].to_numpy(dtype=float)) & (data["strike"] > 0)]
        data = data.sort_values("strike").drop_duplicates(subset="strike", keep="first")
        bid = _num(data, "bid")
        bid = np.where(bid >= 0.0, bid, np.nan)
        ask = _num(data, "ask")
        ask = np.where(ask > 0.0, ask, np.nan)
        iv = _num(data, "impliedVolatility")
        iv = np.where(iv > 0.0, iv, np.nan)
        volume = np.nan_to_num(_num(data, "volume"), nan=0.0)
        oi = np.nan_to_num(_num(data, "openInterest"), nan=0.0)
        return cls(
            strike=data["strike"].to_numpy(dtype=float), bid=bid, ask=ask,
            last=np.where(_num(data, "lastPrice") > 0, _num(data, "lastPrice"), np.nan),
            volume=np.maximum(volume, 0.0), oi=np.maximum(oi, 0.0), vendor_iv=iv,
            vendor_delta=_num(data, "delta"), vendor_gamma=_num(data, "gamma"),
            last_trade=_text(data, "lastTradeDate"), quote_time=_text(data, "quoteTime"),
        )

    def __len__(self) -> int:
        return int(self.strike.shape[0])

    @property
    def quote_ok(self) -> np.ndarray:
        """Two-sided quote: an ask, a bid (0 allowed) and no crossed market."""
        return np.isfinite(self.ask) & np.isfinite(self.bid) & (self.ask >= self.bid)

    @property
    def mid(self) -> np.ndarray:
        """Mid price where the quote is two-sided, else NaN."""
        return np.where(self.quote_ok, 0.5 * (np.nan_to_num(self.bid) + np.nan_to_num(self.ask)), np.nan)

    @property
    def spread_pct(self) -> np.ndarray:
        """Bid-ask spread as a fraction of the mid (NaN without a two-sided quote)."""
        mid = self.mid
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(mid > 0, (self.ask - self.bid) / mid, np.nan)

    def index_of(self, strike: float) -> int | None:
        """Row of an exact listed strike (tolerance 1e-6 relative), or ``None``."""
        if not len(self):
            return None
        pos = int(np.argmin(np.abs(self.strike - strike)))
        return pos if abs(self.strike[pos] - strike) <= 1e-6 * max(1.0, abs(strike)) else None


@dataclass
class ChainView:
    """Normalised chain of one expiry with its provenance."""

    ticker: str
    expiry: str
    calls: SideQuotes
    puts: SideQuotes
    source: str
    fetched_at: str | None
    stale: bool
    age_s: float | None
    as_of: str | None
    as_of_basis: str | None
    greeks_are_native: bool = False
    multiplier: int = CONTRACT_MULTIPLIER
    warnings: list[str] = field(default_factory=list)

    def side(self, is_call: bool) -> SideQuotes:
        """Calls or puts."""
        return self.calls if is_call else self.puts

    def stamp(self) -> dict[str, Any]:
        """Wire block with the chain provenance."""
        return {
            "expiry": self.expiry, "source": self.source, "fetched_at": self.fetched_at,
            "age_s": self.age_s, "stale": self.stale, "as_of": self.as_of,
            "as_of_basis": self.as_of_basis, "greeks_are_native": self.greeks_are_native,
            "contract_multiplier": self.multiplier,
        }


def chain_view(ticker: str, expiry: str, chain: Any, now: datetime) -> ChainView:
    """Wrap a provider :class:`~trading_mcp.data.backends.base.ChainData`."""
    fetched_at = getattr(chain, "fetched_at", None)
    fetched = to_datetime(fetched_at)
    age = round((now - fetched).total_seconds(), 3) if fetched is not None else None
    view = ChainView(
        ticker=str(ticker).upper(), expiry=expiry,
        calls=SideQuotes.from_frame(getattr(chain, "calls", None)),
        puts=SideQuotes.from_frame(getattr(chain, "puts", None)),
        source=str(getattr(chain, "source", None) or "unknown"),
        fetched_at=iso(fetched) if fetched is not None else None,
        stale=bool(getattr(chain, "stale", False)), age_s=age,
        as_of=getattr(chain, "as_of", None), as_of_basis=getattr(chain, "as_of_basis", None),
        greeks_are_native=bool(getattr(chain, "greeks_are_native", False)),
        multiplier=int(getattr(chain, "contract_multiplier", None) or CONTRACT_MULTIPLIER),
    )
    if view.stale:
        view.warnings.append(
            f"chain {expiry} from {view.source} is an expired cache entry "
            f"(fetched {view.fetched_at}) served after a refresh failure"
        )
    if view.as_of is None:
        view.warnings.append(f"chain {expiry}: the vendor gives no quote time; fetched_at is shown")
    return view


def load_chains(ticker: str, expiries: list[str], *, now: datetime, source: Any = None,
                max_workers: int = 4) -> tuple[dict[str, ChainView], dict[str, str]]:
    """Fetch several expiries in parallel. Returns ``(views, errors)``."""
    data = source if source is not None else provider()
    views: dict[str, ChainView] = {}
    errors: dict[str, str] = {}
    unique = list(dict.fromkeys(expiries))
    if not unique:
        return views, errors

    def fetch(expiry: str) -> tuple[str, Any, str | None]:
        try:
            return expiry, data.get_options_chain(ticker, expiry), None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return expiry, None, f"{type(exc).__name__}: {exc}"

    workers = max(1, min(max_workers, len(unique)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, unique))
    for expiry, chain, error in results:
        if chain is None:
            errors[expiry] = error or "no backend returned the chain"
            continue
        view = chain_view(ticker, expiry, chain, now)
        if not len(view.calls) and not len(view.puts):
            errors[expiry] = "empty chain"
            continue
        views[expiry] = view
    return views, errors


def source_warnings(views: dict[str, ChainView]) -> list[str]:
    """One backend per analysis: flag a mix of sources."""
    sources = sorted({view.source for view in views.values()})
    if len(sources) > 1:
        return [f"chains come from different backends ({', '.join(sources)}); quotes may not be comparable"]
    return []


@dataclass
class MarketContext:
    """Every non-chain input of one options analysis."""

    ticker: str
    now: datetime
    spot: SpotCheck
    style: str
    events: Any
    dividends: divmod_.DividendModel
    curve: risk_free.RateCurve
    source: Any
    warnings: list[str] = field(default_factory=list)
    _schedule: tuple[list[float], list[float]] | None = None

    @property
    def price(self) -> float:
        """Spot price (only call when ``spot.usable``)."""
        return float(self.spot.price or 0.0)

    def rate(self, tenor_years: float) -> risk_free.TenorRate:
        """Curve rate for one tenor."""
        return self.curve.rate(tenor_years)

    def schedule(self) -> tuple[list[float], list[float]]:
        """Dividend ex-times (years from now) and amounts."""
        if self._schedule is None:
            self._schedule = self.dividends.schedule(self.ticker, self.now)
        return self._schedule

    def settlement(self, expiry: str) -> str:
        """AM or PM settlement of an expiry."""
        return settlement(self.ticker, expiry)

    def expiry_moment(self, expiry: str) -> datetime:
        """Time at which the option stops accruing time value."""
        return mcal.expiry_datetime(expiry, self.ticker, self.settlement(expiry))

    def tte(self, expiry: str, at: datetime | None = None) -> float:
        """ACT/365 years from ``at`` (default now) to the expiry moment (0 when expired)."""
        return mcal.year_fraction(at or self.now, self.expiry_moment(expiry))

    def dte(self, expiry: str) -> float:
        """Fractional calendar days to expiry."""
        return self.tte(expiry) * 365.0

    def dividend_stamp(self, horizon_T: float | None = None) -> dict[str, Any]:
        """Wire block of the dividend inputs."""
        block = self.dividends.model_dump()
        if horizon_T is not None and self.spot.price:
            rate = self.rate(horizon_T).value
            equivalent = self.dividends.equivalent_yield(self.price, horizon_T, rate, self.ticker, self.now)
            block["equivalent_continuous_yield"] = round(equivalent, 6) if equivalent is not None else None
        return block

    def earnings_before(self, moment: datetime) -> dict[str, Any] | None:
        """Next earnings window when it starts before ``moment``."""
        window = getattr(self.events, "next_earnings", None) if self.events is not None else None
        if window is None or window.start is None:
            return None
        start = to_datetime(window.start)
        if start is None or start > moment:
            return None
        return window.model_dump()


def build_context(ticker: str, *, horizon: date, now: datetime | None = None,
                  source: Any = None, spot: SpotCheck | None = None) -> MarketContext:
    """Spot, style, events, dividends and the rate curve of one analysis."""
    from trading_mcp.data.events import get_corporate_events  # pylint: disable=import-outside-toplevel

    moment = now or utc_now()
    data = source if source is not None else provider()
    checked = spot or check_spot(ticker, now=moment, source=data)
    warnings: list[str] = []
    events = None
    info: dict[str, Any] = {}
    try:
        events = get_corporate_events(
            ticker, provider=data, spot=checked.price, spot_as_of=checked.as_of,
            spot_source=checked.source, use_quote=False, now=moment,
        )
        info = data.get_info(ticker) or {}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        warnings.append(f"corporate events unavailable: {type(exc).__name__}")
    model = divmod_.build_dividend_model(ticker, events, info, horizon, moment)
    warnings.extend(model.warnings)
    curve = risk_free.get_rate_curve()
    if curve.fallback_reason:
        warnings.append(f"rate curve: {curve.fallback_reason}")
    return MarketContext(
        ticker=str(ticker).upper(), now=moment, spot=checked, style=exercise_style(ticker),
        events=events, dividends=model, curve=curve, source=data, warnings=warnings,
    )
