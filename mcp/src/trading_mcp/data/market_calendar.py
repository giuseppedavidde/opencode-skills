"""Exchange calendars built from rules (no third-party calendar package).

The exchange of a ticker comes from its Yahoo suffix: no suffix is the US
(NYSE/Nasdaq) market, ``.MI`` Borsa Italiana, ``.DE`` Xetra, ``.F``
Frankfurt, ``.PA``/``.AS``/``.BR`` Euronext, ``.L`` London, ``.SW`` SIX,
``.MC`` BME and ``.TO`` Toronto. ``-USD`` (and the other crypto quote
currencies) is crypto: 24/7, and the daily bar closes at 00:00 UTC.

Holidays:

- US (NYSE): complete rules (New Year with the Saturday rule, MLK,
  Presidents, Good Friday, Memorial, Juneteenth from 2022, Independence,
  Labor, Thanksgiving, Christmas, weekend observance), the 13:00 early
  closes (3 July, the day after Thanksgiving, 24 December) and the known
  unscheduled closures since 2001.
- Other exchanges: the regular annual closures only. Unscheduled closures
  are not modelled. A missing holiday only makes ``session_state`` report
  ``regular`` on that day; it never invents a bar.

All public functions take a ticker (or an :class:`Exchange`) and aware
datetimes, and return aware datetimes in the exchange timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from trading_mcp.timeutil import UTC, require_aware, utc_now

SESSION_PRE = "pre"
SESSION_REGULAR = "regular"
SESSION_POST = "post"
SESSION_CLOSED = "closed"

SETTLEMENT_AM = "AM"
SETTLEMENT_PM = "PM"

_SECONDS_PER_YEAR = 365.0 * 86400.0


@dataclass(frozen=True)
class Exchange:
    """Trading hours of one venue, in its local timezone.

    ``settle_minutes`` is the delay after the close before the daily bar is
    final (closing auction plus vendor publication delay).
    ``vendor_delay_minutes`` is the usual Yahoo quote delay for the venue; it
    only labels a quote as ``delayed`` instead of ``stale``. ``overnight``
    venues open the evening before the trade date. ``always_open`` venues
    (crypto) trade 24/7 and their daily bar closes at 00:00 UTC.
    """

    code: str
    name: str
    tz: str
    open: time
    close: time
    early_close: time | None = None
    pre_open: time | None = None
    post_close: time | None = None
    early_post_close: time | None = None
    settle_minutes: int = 15
    vendor_delay_minutes: int = 0
    overnight: bool = False
    always_open: bool = False
    holiday_rule: str = "none"

    @property
    def zone(self) -> ZoneInfo:
        """IANA timezone of the venue."""
        return ZoneInfo(self.tz)


NYSE = Exchange(
    code="XNYS", name="NYSE / Nasdaq", tz="America/New_York",
    open=time(9, 30), close=time(16, 0), early_close=time(13, 0),
    pre_open=time(4, 0), post_close=time(20, 0), early_post_close=time(17, 0),
    holiday_rule="nyse",
)
CBOE_INDEX = Exchange(
    code="CBOE_INDEX", name="Cboe volatility indices", tz="America/New_York",
    open=time(9, 30), close=time(16, 15), early_close=time(13, 15),
    vendor_delay_minutes=15, holiday_rule="nyse",
)
ICE_US = Exchange(
    code="IFUS", name="ICE Futures US (US Dollar Index)", tz="America/New_York",
    open=time(20, 0), close=time(17, 0), overnight=True, settle_minutes=30, vendor_delay_minutes=15, holiday_rule="nyse",
)
TSX = Exchange(
    code="XTSE", name="Toronto Stock Exchange", tz="America/Toronto",
    open=time(9, 30), close=time(16, 0), early_close=time(13, 0), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="tsx",
)
BORSA_ITALIANA = Exchange(
    code="XMIL", name="Euronext Milan (Borsa Italiana)", tz="Europe/Rome",
    open=time(9, 0), close=time(17, 30), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="borsa_italiana",
)
XETRA = Exchange(
    code="XETR", name="Xetra", tz="Europe/Berlin",
    open=time(9, 0), close=time(17, 30), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="xetra",
)
FRANKFURT = Exchange(
    code="XFRA", name="Boerse Frankfurt", tz="Europe/Berlin",
    open=time(8, 0), close=time(22, 0), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="xetra",
)
EURONEXT_PARIS = Exchange(
    code="XPAR", name="Euronext Paris", tz="Europe/Paris",
    open=time(9, 0), close=time(17, 30), early_close=time(14, 5), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="euronext",
)
EURONEXT_AMSTERDAM = Exchange(
    code="XAMS", name="Euronext Amsterdam", tz="Europe/Amsterdam",
    open=time(9, 0), close=time(17, 30), early_close=time(14, 5), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="euronext",
)
EURONEXT_BRUSSELS = Exchange(
    code="XBRU", name="Euronext Brussels", tz="Europe/Brussels",
    open=time(9, 0), close=time(17, 30), early_close=time(14, 5), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="euronext",
)
LSE = Exchange(
    code="XLON", name="London Stock Exchange", tz="Europe/London",
    open=time(8, 0), close=time(16, 30), early_close=time(12, 30), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="lse",
)
SIX = Exchange(
    code="XSWX", name="SIX Swiss Exchange", tz="Europe/Zurich",
    open=time(9, 0), close=time(17, 30), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="six",
)
BME = Exchange(
    code="XMAD", name="BME Madrid", tz="Europe/Madrid",
    open=time(9, 0), close=time(17, 30), settle_minutes=30, vendor_delay_minutes=15, holiday_rule="bme",
)
CRYPTO = Exchange(
    code="CRYPTO", name="Crypto (24/7, daily bar at 00:00 UTC)", tz="UTC",
    open=time(0, 0), close=time(0, 0), settle_minutes=2, always_open=True,
)

EXCHANGES: dict[str, Exchange] = {
    ex.code: ex
    for ex in (
        NYSE, CBOE_INDEX, ICE_US, TSX, BORSA_ITALIANA, XETRA, FRANKFURT,
        EURONEXT_PARIS, EURONEXT_AMSTERDAM, EURONEXT_BRUSSELS, LSE, SIX, BME, CRYPTO,
    )
}

SUFFIX_EXCHANGES: dict[str, Exchange] = {
    ".MI": BORSA_ITALIANA,
    ".DE": XETRA,
    ".F": FRANKFURT,
    ".PA": EURONEXT_PARIS,
    ".AS": EURONEXT_AMSTERDAM,
    ".BR": EURONEXT_BRUSSELS,
    ".L": LSE,
    ".SW": SIX,
    ".MC": BME,
    ".TO": TSX,
}

# Index and futures symbols whose venue cannot be read from a suffix.
SYMBOL_EXCHANGES: dict[str, Exchange] = {
    "^VIX": CBOE_INDEX,
    "^VIX3M": CBOE_INDEX,
    "^VIX9D": CBOE_INDEX,
    "^VVIX": CBOE_INDEX,
    "DX-Y.NYB": ICE_US,
    "^GDAXI": XETRA,
    "^STOXX50E": XETRA,
    "^FCHI": EURONEXT_PARIS,
    "^AEX": EURONEXT_AMSTERDAM,
    "^FTSE": LSE,
    "^IBEX": BME,
    "^SSMI": SIX,
    "^GSPTSE": TSX,
}

_CRYPTO_QUOTE_SUFFIXES = ("-USD", "-USDT", "-USDC", "-EUR", "-GBP", "-BTC", "-ETH")
_MARKET_ALIASES = {"US": NYSE, "USA": NYSE, "CRYPTO": CRYPTO}


def exchange_for(ticker: str | Exchange | None) -> Exchange:
    """Return the venue of a ticker (default: US).

    Args:
        ticker: Yahoo symbol (``AAPL``, ``ENI.MI``, ``BTC-USD``), a market
            alias (``US``, ``CRYPTO``), an exchange code (``XMIL``) or an
            :class:`Exchange`.
    """
    if isinstance(ticker, Exchange):
        return ticker
    if not ticker:
        return NYSE
    symbol = str(ticker).strip().upper()
    if symbol in _MARKET_ALIASES:
        return _MARKET_ALIASES[symbol]
    if symbol in EXCHANGES:
        return EXCHANGES[symbol]
    if symbol in SYMBOL_EXCHANGES:
        return SYMBOL_EXCHANGES[symbol]
    if symbol.endswith(_CRYPTO_QUOTE_SUFFIXES):
        return CRYPTO
    if "." in symbol:
        suffix = symbol[symbol.rfind("."):]
        if suffix in SUFFIX_EXCHANGES:
            return SUFFIX_EXCHANGES[suffix]
    return NYSE


def is_crypto(ticker: str | Exchange | None) -> bool:
    """True when the ticker trades 24/7 on the crypto calendar."""
    return exchange_for(ticker).always_open


# ── Holiday rules ────────────────────────────────────────────────────

def easter_sunday(year: int) -> date:
    """Western (Gregorian) Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """``n``-th ``weekday`` (Monday=0) of a month; ``n=-1`` is the last one."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    following = date(year + month // 12, month % 12 + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _us_observed(day: date) -> date:
    """US rule: Saturday holidays move to Friday, Sunday holidays to Monday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _next_weekday(day: date, taken: set[date]) -> date:
    """First weekday on or after ``day`` that is not already a holiday."""
    while day.weekday() >= 5 or day in taken:
        day += timedelta(days=1)
    return day


_NYSE_UNSCHEDULED: dict[date, str] = {
    date(2001, 9, 11): "September 11 attacks",
    date(2001, 9, 12): "September 11 attacks",
    date(2001, 9, 13): "September 11 attacks",
    date(2001, 9, 14): "September 11 attacks",
    date(2004, 6, 11): "National day of mourning (Reagan)",
    date(2007, 1, 2): "National day of mourning (Ford)",
    date(2012, 10, 29): "Hurricane Sandy",
    date(2012, 10, 30): "Hurricane Sandy",
    date(2018, 12, 5): "National day of mourning (G. H. W. Bush)",
    date(2025, 1, 9): "National day of mourning (Carter)",
}


def _nyse_holidays(year: int) -> dict[date, str]:
    result: dict[date, str] = {}
    new_year = date(year, 1, 1)
    # NYSE does not observe a Saturday New Year's Day on the Friday before.
    if new_year.weekday() == 6:
        result[date(year, 1, 2)] = "New Year's Day (observed)"
    elif new_year.weekday() != 5:
        result[new_year] = "New Year's Day"
    if year >= 1998:
        result[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    result[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    result[easter_sunday(year) - timedelta(days=2)] = "Good Friday"
    result[_nth_weekday(year, 5, 0, -1)] = "Memorial Day"
    if year >= 2022:
        result[_us_observed(date(year, 6, 19))] = "Juneteenth"
    result[_us_observed(date(year, 7, 4))] = "Independence Day"
    result[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    result[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    result[_us_observed(date(year, 12, 25))] = "Christmas Day"
    for day, name in _NYSE_UNSCHEDULED.items():
        if day.year == year:
            result[day] = name
    return result


def _nyse_early_closes(year: int, closed: dict[date, str]) -> set[date]:
    candidates: set[date] = set()
    if date(year, 7, 4).weekday() in (1, 2, 3, 4):
        candidates.add(date(year, 7, 3))
    candidates.add(_nth_weekday(year, 11, 3, 4) + timedelta(days=1))
    candidates.add(date(year, 12, 24))
    return {day for day in candidates if day.weekday() < 5 and day not in closed}


def _tsx_holidays(year: int) -> dict[date, str]:
    result: dict[date, str] = {}
    result[_next_weekday(date(year, 1, 1), set())] = "New Year's Day"
    if year >= 2008:
        result[_nth_weekday(year, 2, 0, 3)] = "Family Day"
    result[easter_sunday(year) - timedelta(days=2)] = "Good Friday"
    may24 = date(year, 5, 24)
    result[may24 - timedelta(days=may24.weekday())] = "Victoria Day"
    result[_next_weekday(date(year, 7, 1), set(result))] = "Canada Day"
    result[_nth_weekday(year, 8, 0, 1)] = "Civic Holiday"
    result[_nth_weekday(year, 9, 0, 1)] = "Labour Day"
    result[_nth_weekday(year, 10, 0, 2)] = "Thanksgiving Day"
    christmas = _next_weekday(date(year, 12, 25), set(result))
    result[christmas] = "Christmas Day"
    result[_next_weekday(date(year, 12, 26), set(result))] = "Boxing Day"
    return result


_LSE_UNSCHEDULED: dict[date, str] = {
    date(2020, 5, 8): "Early May bank holiday (VE Day)",
    date(2022, 6, 2): "Spring bank holiday (moved)",
    date(2022, 6, 3): "Platinum Jubilee",
    date(2022, 9, 19): "State funeral of Queen Elizabeth II",
    date(2023, 5, 8): "Coronation of King Charles III",
}


def _lse_holidays(year: int) -> dict[date, str]:
    easter = easter_sunday(year)
    result: dict[date, str] = {
        _next_weekday(date(year, 1, 1), set()): "New Year's Day",
        easter - timedelta(days=2): "Good Friday",
        easter + timedelta(days=1): "Easter Monday",
        _nth_weekday(year, 8, 0, -1): "Summer bank holiday",
    }
    if year != 2020:
        result[_nth_weekday(year, 5, 0, 1)] = "Early May bank holiday"
    if year != 2022:
        result[_nth_weekday(year, 5, 0, -1)] = "Spring bank holiday"
    taken = set(result)
    christmas = _next_weekday(date(year, 12, 25), taken)
    taken.add(christmas)
    boxing = _next_weekday(date(year, 12, 26), taken)
    result[christmas] = "Christmas Day"
    result[boxing] = "Boxing Day"
    for day, name in _LSE_UNSCHEDULED.items():
        if day.year == year:
            result[day] = name
    return result


def _fixed_european(year: int, extra: tuple[tuple[int, int, str], ...]) -> dict[date, str]:
    easter = easter_sunday(year)
    result: dict[date, str] = {
        date(year, 1, 1): "New Year's Day",
        easter - timedelta(days=2): "Good Friday",
        easter + timedelta(days=1): "Easter Monday",
        date(year, 5, 1): "Labour Day",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 26): "St. Stephen's Day",
    }
    for month, day, name in extra:
        result[date(year, month, day)] = name
    return result


def _six_holidays(year: int) -> dict[date, str]:
    easter = easter_sunday(year)
    result = _fixed_european(
        year,
        ((1, 2, "Berchtold's Day"), (8, 1, "Swiss National Day"),
         (12, 24, "Christmas Eve"), (12, 31, "New Year's Eve")),
    )
    result[easter + timedelta(days=39)] = "Ascension Day"
    result[easter + timedelta(days=50)] = "Whit Monday"
    return result


_EVE_DAYS = ((12, 24, "Christmas Eve"), (12, 31, "New Year's Eve"))


@lru_cache(maxsize=512)
def _calendar(rule: str, year: int) -> tuple[dict[date, str], dict[date, str]]:
    """Return ``(holidays, early_close_names)`` for one rule and year."""
    early: dict[date, str] = {}
    if rule == "nyse":
        closed = _nyse_holidays(year)
        early = {day: "early close" for day in _nyse_early_closes(year, closed)}
    elif rule == "tsx":
        closed = _tsx_holidays(year)
        eve = date(year, 12, 24)
        if eve.weekday() < 5 and eve not in closed:
            early[eve] = "Christmas Eve"
    elif rule == "lse":
        closed = _lse_holidays(year)
        for month, day, name in _EVE_DAYS:
            eve = date(year, month, day)
            if eve.weekday() < 5 and eve not in closed:
                early[eve] = name
    elif rule == "euronext":
        closed = _fixed_european(year, ())
        for month, day, name in _EVE_DAYS:
            eve = date(year, month, day)
            if eve.weekday() < 5:
                early[eve] = name
    elif rule == "borsa_italiana":
        closed = _fixed_european(year, ((8, 15, "Ferragosto"),) + _EVE_DAYS)
    elif rule == "xetra":
        closed = _fixed_european(year, _EVE_DAYS)
    elif rule == "bme":
        closed = _fixed_european(year, ())
    elif rule == "six":
        closed = _six_holidays(year)
    else:
        closed = {}
    return closed, early


def holidays(ticker: str | Exchange | None, year: int) -> dict[date, str]:
    """Full-day closures (weekdays and weekends) of the ticker's venue in a year."""
    return dict(_calendar(exchange_for(ticker).holiday_rule, year)[0])


def early_closes(ticker: str | Exchange | None, year: int) -> dict[date, time]:
    """Early-close days of the venue, with the local close time."""
    ex = exchange_for(ticker)
    if ex.early_close is None:
        return {}
    return {day: ex.early_close for day in _calendar(ex.holiday_rule, year)[1]}


def is_trading_day(ticker: str | Exchange | None, day: date) -> bool:
    """True when the venue holds a regular session on ``day``."""
    ex = exchange_for(ticker)
    if ex.always_open:
        return True
    if day.weekday() >= 5:
        return False
    return day not in _calendar(ex.holiday_rule, day.year)[0]


def previous_trading_day(ticker: str | Exchange | None, day: date) -> date:
    """Last trading day strictly before ``day``."""
    ex = exchange_for(ticker)
    day -= timedelta(days=1)
    while not is_trading_day(ex, day):
        day -= timedelta(days=1)
    return day


def next_trading_day(ticker: str | Exchange | None, day: date) -> date:
    """First trading day strictly after ``day``."""
    ex = exchange_for(ticker)
    day += timedelta(days=1)
    while not is_trading_day(ex, day):
        day += timedelta(days=1)
    return day


def _close_time(ex: Exchange, day: date) -> time:
    if ex.early_close is not None and day in _calendar(ex.holiday_rule, day.year)[1]:
        return ex.early_close
    return ex.close


def session_open(ticker: str | Exchange | None, day: date) -> datetime | None:
    """Start of the regular session for trade date ``day`` (``None`` on closed days)."""
    ex = exchange_for(ticker)
    if not is_trading_day(ex, day):
        return None
    if ex.always_open:
        return datetime.combine(day, time(0, 0), tzinfo=UTC)
    start_day = day - timedelta(days=1) if ex.overnight else day
    return datetime.combine(start_day, ex.open, tzinfo=ex.zone)


def session_close(ticker: str | Exchange | None, day: date) -> datetime | None:
    """End of the regular session for trade date ``day`` (``None`` on closed days)."""
    ex = exchange_for(ticker)
    if not is_trading_day(ex, day):
        return None
    if ex.always_open:
        return datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=UTC)
    return datetime.combine(day, _close_time(ex, day), tzinfo=ex.zone)


def _now(now: datetime | None) -> datetime:
    return require_aware(now, "now") if now is not None else utc_now()


def exchange_now(ticker: str | Exchange | None, now: datetime | None = None) -> datetime:
    """Current time in the venue timezone."""
    return _now(now).astimezone(exchange_for(ticker).zone)


def exchange_today(ticker: str | Exchange | None, now: datetime | None = None) -> date:
    """Current calendar date in the venue timezone."""
    return exchange_now(ticker, now).date()


def session_state(ticker: str | Exchange | None, now: datetime | None = None) -> str:
    """Return ``pre``, ``regular``, ``post`` or ``closed`` for the venue at ``now``.

    Crypto is always ``regular``. Venues without extended hours report
    ``closed`` outside the regular session.
    """
    ex = exchange_for(ticker)
    moment = _now(now)
    if ex.always_open:
        return SESSION_REGULAR
    local = moment.astimezone(ex.zone)
    day = local.date()
    if ex.overnight:
        for trade_day in (day, day + timedelta(days=1)):
            start, end = session_open(ex, trade_day), session_close(ex, trade_day)
            if start is not None and end is not None and start <= moment < end:
                return SESSION_REGULAR
        return SESSION_CLOSED
    start, end = session_open(ex, day), session_close(ex, day)
    if start is None or end is None:
        return SESSION_CLOSED
    if start <= moment < end:
        return SESSION_REGULAR
    if ex.pre_open is not None and datetime.combine(day, ex.pre_open, tzinfo=ex.zone) <= moment < start:
        return SESSION_PRE
    post_end = ex.post_close
    if post_end is not None and ex.early_post_close is not None and _close_time(ex, day) != ex.close:
        post_end = ex.early_post_close
    if post_end is not None and end <= moment < datetime.combine(day, post_end, tzinfo=ex.zone):
        return SESSION_POST
    return SESSION_CLOSED


def is_regular_session(ticker: str | Exchange | None, now: datetime | None = None) -> bool:
    """True during the regular session (always True for crypto)."""
    return session_state(ticker, now) == SESSION_REGULAR


# ── Daily bar completeness ───────────────────────────────────────────

def bar_close(ticker: str | Exchange | None, bar_date: date) -> datetime:
    """Close time of the daily bar dated ``bar_date`` (its data time).

    A bar that exists on a day the calendar lists as closed uses the regular
    close time, so a calendar gap can never hide a traded bar.
    """
    ex = exchange_for(ticker)
    if ex.always_open:
        return datetime.combine(bar_date + timedelta(days=1), time(0, 0), tzinfo=UTC)
    return datetime.combine(bar_date, _close_time(ex, bar_date), tzinfo=ex.zone)


def bar_complete_after(ticker: str | Exchange | None, bar_date: date) -> datetime:
    """Earliest time at which the daily bar dated ``bar_date`` is final.

    It is :func:`bar_close` plus the venue settle delay.
    """
    ex = exchange_for(ticker)
    return bar_close(ex, bar_date) + timedelta(minutes=ex.settle_minutes)


def is_bar_complete(
    ticker: str | Exchange | None, bar_date: date, at: datetime | None = None
) -> bool:
    """True when the bar dated ``bar_date`` was final at time ``at``.

    Pass the fetch time as ``at`` for cached data: a bar fetched during the
    session stays partial even after the session ends.
    """
    return _now(at) >= bar_complete_after(ticker, bar_date)


def last_complete_session_date(
    ticker: str | Exchange | None, now: datetime | None = None
) -> date:
    """Trade date of the most recent daily bar that is final at ``now``."""
    ex = exchange_for(ticker)
    moment = _now(now)
    if ex.always_open:
        shifted = (moment - timedelta(minutes=ex.settle_minutes)).astimezone(UTC)
        return shifted.date() - timedelta(days=1)
    day = moment.astimezone(ex.zone).date()
    for _ in range(31):
        if is_trading_day(ex, day) and bar_complete_after(ex, day) <= moment:
            return day
        day -= timedelta(days=1)
    return day


def next_bar_complete_after(
    ticker: str | Exchange | None, now: datetime | None = None
) -> datetime:
    """Next time after ``now`` at which a new daily bar becomes final."""
    ex = exchange_for(ticker)
    moment = _now(now)
    day = last_complete_session_date(ex, moment)
    day = day + timedelta(days=1) if ex.always_open else next_trading_day(ex, day)
    return bar_complete_after(ex, day)


# ── Options expiry and year fractions ────────────────────────────────

def _to_date(value: date | datetime | str, ex: Exchange) -> date:
    if isinstance(value, datetime):
        return require_aware(value, "expiry_date").astimezone(ex.zone).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def expiry_datetime(
    expiry_date: date | datetime | str,
    ticker: str | Exchange | None = "US",
    settlement: str = SETTLEMENT_PM,
    *,
    roll_back_holidays: bool = True,
) -> datetime:
    """Moment at which an option on ``ticker`` stops accruing time value.

    Args:
        expiry_date: Listed expiry (``YYYY-MM-DD``, date or aware datetime).
        ticker: Underlying (or venue). The default ``US`` gives the US
            equity-option convention.
        settlement: ``PM`` (default, US equity and ETF options): the session
            close of the expiry day, 16:00 America/New_York, or 13:00 on an
            early-close day. ``AM`` (for example SPX monthly or VIX options):
            the session open of the expiry day, 09:30 America/New_York, when
            the opening settlement value is set.
        roll_back_holidays: When the expiry day is a holiday, use the previous
            trading day (the OCC rule for a holiday Friday).

    Crypto underlyings use 08:00 UTC (the Deribit convention).
    """
    ex = exchange_for(ticker)
    day = _to_date(expiry_date, ex)
    if ex.always_open:
        return datetime.combine(day, time(8, 0), tzinfo=UTC)
    if roll_back_holidays and not is_trading_day(ex, day):
        day = previous_trading_day(ex, day)
    mode = str(settlement or SETTLEMENT_PM).strip().upper()
    if mode == SETTLEMENT_AM:
        return datetime.combine(day, ex.open, tzinfo=ex.zone)
    if mode == SETTLEMENT_PM:
        return datetime.combine(day, _close_time(ex, day), tzinfo=ex.zone)
    raise ValueError(f"settlement must be 'AM' or 'PM', got {settlement!r}")


def year_fraction(start: datetime, end: datetime) -> float:
    """ACT/365 year fraction between two aware datetimes, with fractional days.

    There is no one-day minimum: three hours give 3 / 8760. A non-positive
    interval (an expired option) gives 0.0; callers must reject expired legs.
    """
    require_aware(start, "start")
    require_aware(end, "end")
    seconds = (end - start).total_seconds()
    return 0.0 if seconds <= 0 else seconds / _SECONDS_PER_YEAR


def time_to_expiry(
    expiry_date: date | datetime | str,
    ticker: str | Exchange | None = "US",
    settlement: str = SETTLEMENT_PM,
    now: datetime | None = None,
) -> float:
    """ACT/365 years from ``now`` to :func:`expiry_datetime` (0.0 when expired)."""
    return year_fraction(_now(now), expiry_datetime(expiry_date, ticker, settlement))


def days_to_expiry(
    expiry_date: date | datetime | str,
    ticker: str | Exchange | None = "US",
    settlement: str = SETTLEMENT_PM,
    now: datetime | None = None,
) -> float:
    """Fractional calendar days from ``now`` to the expiry moment (0.0 when expired)."""
    return time_to_expiry(expiry_date, ticker, settlement, now) * 365.0
