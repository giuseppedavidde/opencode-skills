"""Centralized market-data provider: one fetch per key, honest data times.

Every component reads market data from :data:`data_provider`. Rules:

- **Quotes** (:meth:`DataProvider.get_quote`): last price, optional bid/ask,
  ``as_of`` from Yahoo ``regularMarketTime`` (never the fetch time), source,
  ``session_state``, ``age_s`` and ``stale`` (see :mod:`trading_mcp.data.quotes`).
  Cache TTL is 30 s. Every spot price must come from here, not from
  ``info["currentPrice"]``.
- **History** (:meth:`DataProvider.get_hist`): ``auto_adjust=False``.
  ``Open/High/Low/Close`` are split-adjusted raw prices (they match broker
  charts); ``Adj Close`` also carries dividends. Use
  :func:`trading_mcp.data.prices.returns` for returns and the raw OHLC for
  levels. Daily (and weekly/monthly) history drops the open session bar by
  default (``include_partial=False``). A bar counts as complete only when it
  was *fetched* after its session close plus the venue settle delay, so a
  cached intraday bar never turns into a "complete" bar later.
  :meth:`DataProvider.get_hist_with_meta` returns a :class:`HistMeta` with
  ``as_of`` (close time of the last bar), ``fetched_at``, ``partial_dropped``
  and the source.
- **Freshness** is computed when the data is read. The cache stores the fetch
  time and the data time; a disk hit keeps the original fetch time.
- **Failures** are cached for 30 s only (``NEGATIVE_TTL_S``); HTTP 429/5xx and
  timeouts are retried with jittered exponential backoff under one token
  bucket shared by all threads; parallel calls for one key share one fetch
  (single-flight); callers always receive deep copies; readers take the lock.
- **Disk cache**: JSON files (no pickle) in a private 0700 directory
  (``$XDG_CACHE_HOME/trading_mcp/data`` or ``TRADING_DATA_CACHE_DIR``).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import yfinance as yf
from pydantic import BaseModel, Field

from trading_mcp.data import market_calendar as mcal
from trading_mcp.data.backends.base import ChainData, OptionsBackend, chain_to_chaindata
from trading_mcp.data.backends.registry import build_backends
from trading_mcp.data.cache_paths import atomic_write_json, cache_dir, read_json
from trading_mcp.data.frame_codec import decode_frame, encode_frame, jsonable
from trading_mcp.data.fundamentals_schema import Fundamentals, from_yfinance, merge
from trading_mcp.data.http_policy import (
    ERROR_EMPTY,
    ERROR_NOT_FOUND,
    YAHOO_BUCKET,
    SingleFlight,
    TokenBucket,
    UpstreamFailure,
    call_with_retry,
)
from trading_mcp.data.prices import PRICE_ADJUSTMENT
from trading_mcp.data.quotes import (
    Quote,
    error_quote,
    evaluate,
    fields_from_chart_meta,
    fields_from_info,
)
from trading_mcp.timeutil import UTC, epoch_to_iso, from_epoch, iso, to_datetime

logger = logging.getLogger(__name__)

SOURCE_YF_HISTORY = "yfinance:history"
SOURCE_YF_INFO = "yfinance:info"
SOURCE_FMP = "fmp"

QUOTE_TTL_S = 30.0
NEGATIVE_TTL_S = 30.0
DAILY_MAX_AGE_S = 6 * 3600.0
INTRADAY_TTL_S = 120.0
PARTIAL_TTL_S = 120.0
INFO_TTL_S = 6 * 3600.0
OPTIONS_EXPIRATIONS_TTL_S = 3600.0
OPTIONS_CHAIN_TTL_S = 60.0

_DISK_SCHEMA = 2
_DATA_CACHE_ENV = "TRADING_DATA_CACHE_DIR"
_UNRESOLVED: Any = object()
# Resolved on first disk use; tests may assign a directory (or None).
_DATA_CACHE_DIR: Any = _UNRESOLVED

_INTRADAY_SUFFIXES = ("m", "h")
_MULTI_DAY_INTERVALS = {"5d", "1wk", "1mo", "3mo"}


# ── Models ───────────────────────────────────────────────────────────

class HistMeta(BaseModel):
    """Provenance of one history read (see the module docstring)."""

    symbol: str
    period: str
    interval: str
    source: str = SOURCE_YF_HISTORY
    exchange: str | None = None
    timezone: str | None = None
    price_adjustment: str = PRICE_ADJUSTMENT
    fetched_at: str | None = None
    fetch_age_s: float | None = None
    bars: int = 0
    first_bar_date: str | None = None
    last_bar_date: str | None = None
    last_bar_complete: bool | None = None
    as_of: str | None = Field(default=None, description="Data time of the last bar (ISO 8601 with offset)")
    include_partial: bool = False
    partial_dropped: bool = False
    partial_bar_date: str | None = None
    session_state: str | None = None
    last_complete_session: str | None = None
    up_to_date: bool | None = None
    stale: bool = False
    cache: str | None = None
    error: str | None = None
    error_kind: str | None = None
    warnings: list[str] = Field(default_factory=list)


class InfoMeta(BaseModel):
    """Provenance of one ``info`` read."""

    symbol: str
    source: str | None = None
    fetched_at: str | None = None
    fetch_age_s: float | None = None
    as_of: str | None = None
    stale: bool = False
    cache: str | None = None
    error: str | None = None
    error_kind: str | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass
class CacheEntry:
    """One cached payload with its fetch time (epoch seconds) and TTL."""

    data: Any
    fetched_at: float
    ttl: float
    source: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    origin: str = "network"
    negative: bool = False
    error: str | None = None
    error_kind: str | None = None

    def age(self, now: float) -> float:
        """Seconds since the fetch."""
        return max(0.0, now - self.fetched_at)

    def is_fresh(self, now: float) -> bool:
        """True while the entry is inside its TTL."""
        return self.age(now) < self.ttl

    @property
    def has_data(self) -> bool:
        """True when the entry holds a usable payload."""
        if self.negative or self.data is None:
            return False
        if isinstance(self.data, pd.DataFrame):
            return not self.data.empty
        return bool(self.data)


@dataclass
class TickerCache:
    """Per-symbol cache. ``failures`` holds short-lived negative entries."""

    hist: dict[tuple[str, str], CacheEntry] = field(default_factory=dict)
    info: CacheEntry | None = None
    quote: CacheEntry | None = None
    options_expirations: CacheEntry | None = None
    options_chains: dict[str, CacheEntry] = field(default_factory=dict)
    fundamentals: dict[bool, CacheEntry] = field(default_factory=dict)
    failures: dict[Any, CacheEntry] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


# ── Upstream calls (module level so tests can replace them) ──────────

def _chart_metadata(ticker: Any) -> dict[str, Any]:
    """Chart metadata of the last ``history()`` call (no extra request)."""
    history = getattr(ticker, "_price_history", None)
    meta = getattr(history, "_history_metadata", None)
    return dict(meta) if isinstance(meta, dict) else {}


_YF_THREAD = threading.local()
_YF_CONFIG_LOCK = threading.Lock()


class _YfDebugOptions(dict):
    """yfinance ``config.debug`` options with a per-thread ``hide_exceptions`` override."""

    def get(self, key: Any, default: Any = None) -> Any:
        if key == "hide_exceptions" and getattr(_YF_THREAD, "raise_errors", False):
            return False
        return super().get(key, default)


def _yf_raise_in_this_thread() -> bool:
    """Install the per-thread override once; True when yfinance now raises in this thread.

    yfinance 1.5 deprecates ``history(raise_errors=True)`` in favour of the
    process-wide ``yf.config.debug.hide_exceptions = False``. A process-wide
    switch also changes ``info`` and the option calls of other threads, so
    the switch applies only to the thread inside :func:`_yf_history`.
    """
    config = getattr(yf, "config", None)
    try:
        with _YF_CONFIG_LOCK:
            _ = config.debug.hide_exceptions  # loads the yfinance defaults
            options = config.options
            if not isinstance(options.get("debug"), _YfDebugOptions):
                options["debug"] = _YfDebugOptions(options.get("debug") or {})
        return config.debug.hide_exceptions is False
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def _yf_history(symbol: str, period: str, interval: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Download raw (split-adjusted, not dividend-adjusted) bars and the chart metadata.

    Upstream errors (HTTP 429, network, unknown symbol) raise instead of
    giving an empty frame, so the retry policy can classify them; the
    switch is per thread (see :func:`_yf_raise_in_this_thread`).
    """
    ticker = yf.Ticker(symbol)
    kwargs: dict[str, Any] = {"period": period, "interval": interval, "auto_adjust": False, "actions": False}
    _YF_THREAD.raise_errors = True
    try:
        if not _yf_raise_in_this_thread():
            logger.warning("yfinance errors cannot be made visible per thread; an error gives an empty frame")
        frame = ticker.history(**kwargs)
    finally:
        _YF_THREAD.raise_errors = False
    return frame, _chart_metadata(ticker)


def _yf_info(symbol: str) -> dict[str, Any]:
    """Download the yfinance ``info`` dict (quoteSummary + v7 quote)."""
    return dict(yf.Ticker(symbol).info or {})


def _fmp_info(symbol: str) -> dict[str, Any]:
    """FMP fundamentals in yfinance keys and yfinance units (fallback only)."""
    from trading_mcp.data.fmp_fetcher import fetch_fmp_fundamentals  # pylint: disable=import-outside-toplevel

    return fetch_fmp_fundamentals(symbol)


def _fmp_eligible(symbol: str) -> bool:
    """FMP covers listed equities only (no indices, FX or crypto)."""
    return not symbol.startswith("^") and "=" not in symbol and not mcal.is_crypto(symbol)


def _info_usable(info: dict[str, Any] | None) -> bool:
    """True when ``info`` is more than the yfinance placeholder for a bad symbol."""
    if not info:
        return False
    keys = ("quoteType", "shortName", "longName", "regularMarketPrice", "currentPrice", "marketCap")
    return any(info.get(key) not in (None, "") for key in keys)


# ── Disk cache (JSON, private directory) ─────────────────────────────

def _disk_dir() -> Path | None:
    global _DATA_CACHE_DIR  # pylint: disable=global-statement
    if _DATA_CACHE_DIR is _UNRESOLVED:
        _DATA_CACHE_DIR = cache_dir("data", _DATA_CACHE_ENV)
    return _DATA_CACHE_DIR


def _safe_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]", "_", symbol.upper())[:40] or "_"


def _disk_path(kind: str, symbol: str, key: str) -> Path | None:
    root = _disk_dir()
    if root is None:
        return None
    digest = hashlib.sha1(f"{kind}:{key}".encode("utf-8")).hexdigest()[:20]
    return Path(root) / f"{kind}_{_safe_symbol(symbol)}_{digest}.json"


def _disk_save(kind: str, symbol: str, key: str, entry: CacheEntry, payload: Any) -> None:
    path = _disk_path(kind, symbol, key)
    if path is None:
        return
    document = {
        "schema": _DISK_SCHEMA,
        "kind": kind,
        "symbol": symbol,
        "key": key,
        "fetched_at": entry.fetched_at,
        "source": entry.source,
        "meta": jsonable(entry.meta),
        "payload": payload,
    }
    atomic_write_json(path, document)


def _disk_load(kind: str, symbol: str, key: str) -> dict[str, Any] | None:
    path = _disk_path(kind, symbol, key)
    if path is None:
        return None
    document = read_json(path)
    if not isinstance(document, dict):
        return None
    if document.get("schema") != _DISK_SCHEMA or document.get("kind") != kind or document.get("key") != key:
        return None
    try:
        float(document["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return document


def _disk_delete_symbol(symbol: str) -> int:
    root = _disk_dir()
    if root is None:
        return 0
    removed = 0
    for kind in ("hist", "info"):
        for path in Path(root).glob(f"{kind}_{_safe_symbol(symbol)}_*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


# ── Helpers ──────────────────────────────────────────────────────────

def _is_intraday(interval: str) -> bool:
    return interval.lower().endswith(_INTRADAY_SUFFIXES)


def _interval_delta(interval: str) -> timedelta | None:
    match = re.fullmatch(r"(\d+)(m|h)", interval.lower())
    if not match:
        return None
    value = int(match.group(1))
    return timedelta(minutes=value) if match.group(2) == "m" else timedelta(hours=value)


def _period_last_day(day: date, interval: str) -> date:
    if interval in ("5d", "1wk"):
        return day + timedelta(days=6)
    months = 1 if interval == "1mo" else 3
    year, month = divmod(day.month - 1 + months, 12)
    return date(day.year + year, month + 1, 1) - timedelta(days=1)


def _normalize_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Sorted, de-duplicated, timezone-aware DatetimeIndex frame."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.DatetimeIndex(pd.to_datetime(out.index, utc=True))
    if out.index.tz is None:
        out.index = out.index.tz_localize(mcal.exchange_for(symbol).zone)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _norm_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


# ── Provider ─────────────────────────────────────────────────────────

class DataProvider:
    """Centralized, thread-safe data provider (see the module docstring).

    Args:
        ttl_overrides: Override entries of :attr:`DEFAULT_TTL` (seconds).
        backends: Options backends (resolved lazily when ``None``).
        clock: Epoch-seconds clock (injectable for tests).
        bucket: Token bucket for Yahoo requests (``None`` disables it).
        disk: Use the JSON disk cache.
    """

    DEFAULT_TTL: dict[str, float] = {
        "hist": DAILY_MAX_AGE_S,
        "intraday": INTRADAY_TTL_S,
        "partial": PARTIAL_TTL_S,
        "info": INFO_TTL_S,
        "quote": QUOTE_TTL_S,
        "options": OPTIONS_EXPIRATIONS_TTL_S,
        "options_chain": OPTIONS_CHAIN_TTL_S,
        "negative": NEGATIVE_TTL_S,
    }

    def __init__(
        self,
        ttl_overrides: dict[str, float] | None = None,
        backends: list[OptionsBackend] | None = None,
        *,
        clock: Callable[[], float] = time.time,
        bucket: TokenBucket | None = YAHOO_BUCKET,
        disk: bool = True,
    ) -> None:
        self._cache: dict[str, TickerCache] = {}
        self._global_lock = threading.RLock()
        self._ttl = dict(self.DEFAULT_TTL)
        if ttl_overrides:
            self._ttl.update(ttl_overrides)
        self._ttl["negative"] = min(self._ttl["negative"], NEGATIVE_TTL_S)
        self._ttl["quote"] = min(self._ttl["quote"], 60.0)
        self._backends: list[OptionsBackend] | None = backends
        self._backends_lock = threading.Lock()
        self._clock = clock
        self._bucket = bucket
        self._use_disk = disk
        self._flights = SingleFlight()
        self._stats = {"network": 0, "memory_hits": 0, "disk_hits": 0, "failures": 0, "stale_served": 0}
        self._stats_lock = threading.Lock()

    # ── infrastructure ──────────────────────────────────────────────

    def _now(self) -> float:
        return float(self._clock())

    def _now_dt(self) -> datetime:
        return datetime.fromtimestamp(self._now(), UTC)

    def _count(self, key: str) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + 1

    def _ensure_ticker_cache(self, symbol: str) -> TickerCache:
        with self._global_lock:
            cache = self._cache.get(symbol)
            if cache is None:
                cache = TickerCache()
                self._cache[symbol] = cache
            return cache

    def _resolve_backends(self) -> list[OptionsBackend]:
        if self._backends is None:
            with self._backends_lock:
                if self._backends is None:
                    self._backends = build_backends()
        return self._backends

    def _remember_failure(self, cache: TickerCache, key: Any, failure: UpstreamFailure) -> CacheEntry:
        entry = CacheEntry(
            data=None, fetched_at=self._now(), ttl=self._ttl["negative"], negative=True,
            error=failure.message, error_kind=failure.kind,
        )
        with cache.lock:
            cache.failures[key] = entry
        self._count("failures")
        return entry

    def _recent_failure(self, cache: TickerCache, key: Any) -> CacheEntry | None:
        with cache.lock:
            entry = cache.failures.get(key)
            if entry is not None and not entry.is_fresh(self._now()):
                cache.failures.pop(key, None)
                return None
            return entry

    def _call(self, fn: Callable[[], Any], what: str, attempts: int = 3) -> Any:
        self._count("network")
        return call_with_retry(fn, what=what, bucket=self._bucket, max_attempts=attempts)

    # ── history ─────────────────────────────────────────────────────

    def get_hist(
        self, symbol: str, period: str = "1y", interval: str = "1d", include_partial: bool = False
    ) -> pd.DataFrame:
        """OHLCV history (a copy). See :meth:`get_hist_with_meta`."""
        frame, _ = self.get_hist_with_meta(symbol, period=period, interval=interval,
                                           include_partial=include_partial)
        return frame

    def get_hist_with_meta(
        self, symbol: str, period: str = "1y", interval: str = "1d", include_partial: bool = False
    ) -> tuple[pd.DataFrame, HistMeta]:
        """OHLCV history plus its :class:`HistMeta`.

        Args:
            symbol: Yahoo symbol (``AAPL``, ``ENI.MI``, ``BTC-USD``).
            period: yfinance period (``5d``, ``1mo``, ``1y``, ``max``...).
            interval: yfinance interval (``1d``, ``1wk``, ``1h``...).
            include_partial: Keep the bar of the open session (daily and
                longer intervals). Intraday intervals always keep every bar.

        Returns:
            ``(frame, meta)``. On failure the frame is empty and
            ``meta.error``/``meta.error_kind`` say why; an expired copy is
            served (``meta.stale=True``) when one exists.
        """
        sym = _norm_symbol(symbol)
        key = (period, interval)
        cache = self._ensure_ticker_cache(sym)
        with cache.lock:
            entry = cache.hist.get(key)
        if entry is not None and self._hist_valid(sym, interval, entry, include_partial):
            self._count("memory_hits")
            return self._render_hist(sym, period, interval, entry, include_partial, cache="memory")

        disk_entry = self._load_hist_from_disk(sym, period, interval)
        if disk_entry is not None and self._hist_valid(sym, interval, disk_entry, include_partial):
            with cache.lock:
                cache.hist[key] = disk_entry
            self._count("disk_hits")
            return self._render_hist(sym, period, interval, disk_entry, include_partial, cache="disk")
        if entry is None or (disk_entry is not None and disk_entry.fetched_at > entry.fetched_at):
            entry = disk_entry

        failure = self._recent_failure(cache, ("hist", key))
        if failure is None:
            try:
                fresh = self._flights.do(
                    ("hist", sym, period, interval),
                    lambda: self._fetch_hist_entry(sym, period, interval),
                )
                return self._render_hist(sym, period, interval, fresh, include_partial, cache=None)
            except UpstreamFailure as exc:
                failure = self._remember_failure(cache, ("hist", key), exc)
        return self._hist_after_failure(sym, period, interval, entry, failure, include_partial)

    def _hist_valid(self, symbol: str, interval: str, entry: CacheEntry, include_partial: bool) -> bool:
        if not entry.has_data:
            return False
        now = self._now()
        age = entry.age(now)
        if _is_intraday(interval):
            return age < self._ttl["intraday"]
        if include_partial:
            return age < self._ttl["partial"]
        if age >= self._ttl["hist"]:
            return False
        moment = datetime.fromtimestamp(now, UTC)
        latest = mcal.last_complete_session_date(symbol, moment)
        return entry.fetched_at >= mcal.bar_complete_after(symbol, latest).timestamp()

    def _fetch_hist_entry(self, symbol: str, period: str, interval: str) -> CacheEntry:
        fetched_at = self._now()
        frame, chart = self._call(
            lambda: _yf_history(symbol, period, interval), what=f"history {symbol} {period}/{interval}"
        )
        frame = _normalize_frame(frame, symbol)
        if frame.empty:
            raise UpstreamFailure(ERROR_EMPTY, f"history {symbol} {period}/{interval}: no bars", retryable=False)
        keep = ("regularMarketPrice", "regularMarketTime", "currency", "exchangeName",
                "fullExchangeName", "exchangeTimezoneName", "instrumentType")
        meta = {"chart": {k: chart.get(k) for k in keep if chart.get(k) is not None}}
        entry = CacheEntry(data=frame, fetched_at=fetched_at, ttl=self._ttl["hist"],
                           source=SOURCE_YF_HISTORY, meta=meta)
        cache = self._ensure_ticker_cache(symbol)
        with cache.lock:
            cache.hist[(period, interval)] = entry
            cache.failures.pop(("hist", (period, interval)), None)
        if self._use_disk:
            _disk_save("hist", symbol, f"hist:{symbol}:{period}:{interval}", entry, encode_frame(frame))
        fields = fields_from_chart_meta(symbol, meta["chart"], frame if interval == "1d" else None)
        self._seed_quote(symbol, fields, fetched_at, has_book=False)
        return entry

    def _load_hist_from_disk(self, symbol: str, period: str, interval: str) -> CacheEntry | None:
        if not self._use_disk:
            return None
        document = _disk_load("hist", symbol, f"hist:{symbol}:{period}:{interval}")
        if document is None:
            return None
        try:
            frame = decode_frame(document["payload"])
        except (ValueError, KeyError, TypeError):
            return None
        if frame.empty:
            return None
        return CacheEntry(
            data=frame, fetched_at=float(document["fetched_at"]), ttl=self._ttl["hist"],
            source=str(document.get("source") or SOURCE_YF_HISTORY),
            meta=dict(document.get("meta") or {}), origin="disk",
        )

    @staticmethod
    def _period_close_day(symbol: str, day: date, interval: str) -> date:
        """Last trading day covered by a bar (the bar date itself for ``1d``)."""
        if interval not in _MULTI_DAY_INTERVALS:
            return day
        last = _period_last_day(day, interval)
        while last > day and not mcal.is_trading_day(symbol, last):
            last -= timedelta(days=1)
        return last

    def _bar_complete(self, symbol: str, interval: str, stamp: pd.Timestamp, fetched: datetime) -> bool:
        close_day = self._period_close_day(symbol, stamp.date(), interval)
        return mcal.is_bar_complete(symbol, close_day, at=fetched)

    def _render_hist(
        self,
        symbol: str,
        period: str,
        interval: str,
        entry: CacheEntry,
        include_partial: bool,
        *,
        cache: str | None,
        stale: bool = False,
        failure: CacheEntry | None = None,
    ) -> tuple[pd.DataFrame, HistMeta]:
        frame: pd.DataFrame = entry.data
        now = self._now_dt()
        fetched = from_epoch(entry.fetched_at) or now
        ex = mcal.exchange_for(symbol)
        intraday = _is_intraday(interval)
        total = len(frame)
        complete = total
        if not intraday:
            while complete > 0 and not self._bar_complete(symbol, interval, frame.index[complete - 1], fetched):
                complete -= 1
        keep = total if (intraday or include_partial) else complete
        out = frame.iloc[:keep].copy(deep=True)
        meta = HistMeta(
            symbol=symbol, period=period, interval=interval, source=entry.source or SOURCE_YF_HISTORY,
            exchange=ex.code, timezone=ex.tz, fetched_at=iso(fetched),
            fetch_age_s=round(entry.age(self._now()), 3), bars=len(out),
            include_partial=include_partial, session_state=mcal.session_state(ex, now),
            stale=stale, cache=cache,
        )
        if failure is not None:
            meta.error, meta.error_kind = failure.error, failure.error_kind
        if not intraday and complete < total:
            meta.partial_bar_date = frame.index[total - 1].date().isoformat()
            meta.partial_dropped = not include_partial
        if not out.empty:
            first, last = out.index[0], out.index[-1]
            meta.first_bar_date = first.date().isoformat()
            meta.last_bar_date = last.date().isoformat()
            chart_time = epoch_to_iso((entry.meta.get("chart") or {}).get("regularMarketTime"), ex.zone)
            if intraday:
                step = _interval_delta(interval)
                bar_end = last.to_pydatetime() + step if step is not None else None
                meta.last_bar_complete = bar_end is not None and bar_end <= fetched
                meta.as_of = iso(bar_end, tz=ex.zone) if meta.last_bar_complete else chart_time
            else:
                meta.last_bar_complete = keep <= complete
                if meta.last_bar_complete:
                    close_day = self._period_close_day(symbol, last.date(), interval)
                    meta.as_of = iso(mcal.bar_close(ex, close_day), tz=ex.zone)
                else:
                    meta.as_of = chart_time
                    if chart_time is None:
                        meta.warnings.append("open session bar has no vendor time; as_of unknown")
                latest = mcal.last_complete_session_date(ex, now)
                meta.last_complete_session = latest.isoformat()
                last_complete_day = out.index[min(keep, complete) - 1].date() if min(keep, complete) else None
                meta.up_to_date = last_complete_day is not None and last_complete_day >= latest
        if stale:
            self._count("stale_served")
            meta.warnings.append(
                f"served history fetched {meta.fetch_age_s:.0f} s ago after an upstream failure"
            )
        return out, meta

    def _hist_after_failure(
        self, symbol: str, period: str, interval: str, entry: CacheEntry | None,
        failure: CacheEntry, include_partial: bool,
    ) -> tuple[pd.DataFrame, HistMeta]:
        if entry is not None and entry.has_data:
            return self._render_hist(symbol, period, interval, entry, include_partial,
                                     cache=entry.origin, stale=True, failure=failure)
        ex = mcal.exchange_for(symbol)
        meta = HistMeta(
            symbol=symbol, period=period, interval=interval, exchange=ex.code, timezone=ex.tz,
            include_partial=include_partial, session_state=mcal.session_state(ex, self._now_dt()),
            error=failure.error, error_kind=failure.error_kind,
        )
        return pd.DataFrame(), meta

    def last_hist_meta(self, symbol: str, period: str = "1y", interval: str = "1d",
                       include_partial: bool = False) -> HistMeta | None:
        """Metadata of the cached history entry (no fetch), or ``None``."""
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        with cache.lock:
            entry = cache.hist.get((period, interval))
        if entry is None or not entry.has_data:
            return None
        return self._render_hist(sym, period, interval, entry, include_partial, cache=entry.origin)[1]

    # ── quotes ──────────────────────────────────────────────────────

    def _seed_quote(self, symbol: str, fields: dict[str, Any], fetched_at: float, *, has_book: bool) -> None:
        if fields.get("price") is None or fields.get("as_of") is None:
            return
        cache = self._ensure_ticker_cache(symbol)
        new_time = to_datetime(fields["as_of"])
        with cache.lock:
            current = cache.quote
            if current is not None and current.data.get("as_of") is not None:
                old_time = to_datetime(current.data["as_of"])
                if old_time is not None and new_time is not None and old_time > new_time:
                    return
                if current.meta.get("has_book") and not has_book and current.is_fresh(self._now()):
                    return
            cache.quote = CacheEntry(
                data=dict(fields), fetched_at=fetched_at, ttl=self._ttl["quote"],
                source=str(fields.get("source")), meta={"has_book": has_book},
            )

    def get_quote(self, symbol: str, *, with_book: bool = False) -> Quote:
        """Return the latest :class:`~trading_mcp.data.quotes.Quote` (TTL 30 s).

        Args:
            symbol: Yahoo symbol.
            with_book: Also get bid/ask, market state, vendor delay and the
                extended-hours price from the v7 quote (two requests instead
                of one; it also refreshes the ``info`` cache).

        Never raises: a failure returns a quote with ``price=None`` and
        ``error``/``error_kind`` set (or the last known quote plus a warning).
        """
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        now = self._now()
        with cache.lock:
            entry = cache.quote
        if entry is not None and entry.is_fresh(now) and (not with_book or entry.meta.get("has_book")):
            self._count("memory_hits")
            return self._render_quote(entry, cached=True)
        failure = self._recent_failure(cache, ("quote", with_book))
        if failure is None:
            try:
                fresh = self._flights.do(("quote", sym, with_book), lambda: self._fetch_quote_entry(sym, with_book))
                return self._render_quote(fresh, cached=False)
            except UpstreamFailure as exc:
                failure = self._remember_failure(cache, ("quote", with_book), exc)
        if entry is not None and entry.has_data:
            quote = self._render_quote(entry, cached=True)
            quote.warnings.append(f"quote refresh failed ({failure.error_kind}); last known quote shown")
            return quote
        return error_quote(sym, failure.error or "quote unavailable", failure.error_kind or "unknown",
                           now=self._now_dt())

    def _render_quote(self, entry: CacheEntry, *, cached: bool) -> Quote:
        return evaluate(copy.deepcopy(entry.data), now=self._now_dt(),
                        fetched_at=from_epoch(entry.fetched_at), cached=cached)

    def _fetch_quote_entry(self, symbol: str, with_book: bool) -> CacheEntry:
        warnings: list[str] = []
        if with_book:
            try:
                info_entry = self._fetch_info_entry(symbol, allow_fallback=False)
                fields = fields_from_info(symbol, info_entry.data)
                if fields.get("price") is not None:
                    return self._store_quote(symbol, fields, info_entry.fetched_at, has_book=True)
                warnings.append("v7 quote had no price; chart price used")
            except UpstreamFailure as exc:
                warnings.append(f"order book unavailable ({exc.kind}); chart price used")
        hist_entry = self._fetch_hist_entry(symbol, "5d", "1d")
        fields = fields_from_chart_meta(symbol, hist_entry.meta.get("chart"), hist_entry.data)
        if fields.get("price") is None:
            raise UpstreamFailure(ERROR_EMPTY, f"quote {symbol}: vendor returned no price", retryable=False)
        fields["warnings"] = warnings
        return self._store_quote(symbol, fields, hist_entry.fetched_at, has_book=False)

    def _store_quote(self, symbol: str, fields: dict[str, Any], fetched_at: float, *, has_book: bool) -> CacheEntry:
        entry = CacheEntry(data=dict(fields), fetched_at=fetched_at, ttl=self._ttl["quote"],
                           source=str(fields.get("source")), meta={"has_book": has_book})
        cache = self._ensure_ticker_cache(symbol)
        with cache.lock:
            cache.quote = entry
            cache.failures.pop(("quote", has_book), None)
        return entry

    # ── info ────────────────────────────────────────────────────────

    def get_info(self, symbol: str) -> dict[str, Any]:
        """yfinance ``info`` (deep copy) with ``_fetched_at``, ``_source``, ``_stale``.

        Fundamentals snapshot with a 6 h TTL. Do not read prices from it: use
        :meth:`get_quote`. Returns ``{}`` when nothing is available.
        """
        return self.get_info_with_meta(symbol)[0]

    def get_info_with_meta(self, symbol: str) -> tuple[dict[str, Any], InfoMeta]:
        """``info`` plus its :class:`InfoMeta` (fetch time, data time, source)."""
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        now = self._now()
        with cache.lock:
            entry = cache.info
        if entry is not None and entry.has_data and entry.is_fresh(now):
            self._count("memory_hits")
            return self._render_info(sym, entry, cache="memory")
        disk_entry = self._load_info_from_disk(sym)
        if disk_entry is not None and disk_entry.is_fresh(now):
            with cache.lock:
                cache.info = disk_entry
            self._count("disk_hits")
            return self._render_info(sym, disk_entry, cache="disk")
        if entry is None or (disk_entry is not None and disk_entry.fetched_at > entry.fetched_at):
            entry = disk_entry
        failure = self._recent_failure(cache, ("info",))
        if failure is None:
            try:
                fresh = self._flights.do(("info", sym), lambda: self._fetch_info_entry(sym))
                return self._render_info(sym, fresh, cache=None)
            except UpstreamFailure as exc:
                failure = self._remember_failure(cache, ("info",), exc)
        if entry is not None and entry.has_data:
            return self._render_info(sym, entry, cache=entry.origin, stale=True, failure=failure)
        meta = InfoMeta(symbol=sym, error=failure.error, error_kind=failure.error_kind)
        return {}, meta

    def _fetch_info_entry(self, symbol: str, allow_fallback: bool = True) -> CacheEntry:
        fetched_at = self._now()
        source = SOURCE_YF_INFO
        try:
            if self._bucket is not None and not self._bucket.acquire(timeout=60.0):
                raise UpstreamFailure("local_rate_limit", f"info {symbol}: request budget exhausted", retryable=True)
            info = self._call(lambda: _yf_info(symbol), what=f"info {symbol}", attempts=2)
            if not _info_usable(info):
                raise UpstreamFailure(ERROR_NOT_FOUND, f"info {symbol}: empty payload", retryable=False)
        except UpstreamFailure:
            if not allow_fallback or not _fmp_eligible(symbol):
                raise
            info = {}
            try:
                info = _fmp_info(symbol)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("FMP fallback failed for %s: %s", symbol, type(exc).__name__)
            if not info:
                raise
            source = SOURCE_FMP
        entry = CacheEntry(data=dict(info), fetched_at=fetched_at, ttl=self._ttl["info"], source=source)
        cache = self._ensure_ticker_cache(symbol)
        with cache.lock:
            cache.info = entry
            cache.failures.pop(("info",), None)
        if self._use_disk:
            _disk_save("info", symbol, f"info:{symbol}", entry, jsonable(entry.data))
        if source == SOURCE_YF_INFO:
            self._seed_quote(symbol, fields_from_info(symbol, entry.data), fetched_at, has_book=True)
        return entry

    def _load_info_from_disk(self, symbol: str) -> CacheEntry | None:
        if not self._use_disk:
            return None
        document = _disk_load("info", symbol, f"info:{symbol}")
        if document is None or not isinstance(document.get("payload"), dict) or not document["payload"]:
            return None
        return CacheEntry(
            data=dict(document["payload"]), fetched_at=float(document["fetched_at"]),
            ttl=self._ttl["info"], source=str(document.get("source") or SOURCE_YF_INFO), origin="disk",
        )

    def _render_info(
        self, symbol: str, entry: CacheEntry, *, cache: str | None,
        stale: bool = False, failure: CacheEntry | None = None,
    ) -> tuple[dict[str, Any], InfoMeta]:
        data = copy.deepcopy(entry.data)
        fetched = from_epoch(entry.fetched_at)
        data["_fetched_at"] = iso(fetched)
        data["_source"] = entry.source
        data["_stale"] = stale
        meta = InfoMeta(
            symbol=symbol, source=entry.source, fetched_at=iso(fetched),
            fetch_age_s=round(entry.age(self._now()), 3),
            as_of=epoch_to_iso(entry.data.get("regularMarketTime"), mcal.exchange_for(symbol).zone),
            stale=stale, cache=cache,
        )
        if failure is not None:
            meta.error, meta.error_kind = failure.error, failure.error_kind
            meta.warnings.append(f"served info fetched {meta.fetch_age_s:.0f} s ago after an upstream failure")
        return data, meta

    def get_fundamentals(self, symbol: str, *, enrich: bool = False) -> Fundamentals:
        """Normalized fundamentals: unit, period and source per field (a copy).

        yfinance is the primary source. With ``enrich=True`` the gaps (never
        the present values) are filled from Alpha Vantage, then FMP. Results
        are cached for 6 h like ``info``. An empty :class:`Fundamentals` with
        a warning is returned when no source answers.
        """
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        now = self._now()
        with cache.lock:
            entry = cache.fundamentals.get(enrich)
        if entry is not None and entry.is_fresh(now):
            return entry.data.copy_deep()
        info, meta = self.get_info_with_meta(sym)
        if info.get("_source") == SOURCE_FMP:
            from trading_mcp.data.fmp_fetcher import fetch_fmp_normalized  # pylint: disable=import-outside-toplevel

            result = fetch_fmp_normalized(sym) or Fundamentals(symbol=sym)
        else:
            result = from_yfinance(sym, info)
        result.fetched_at = meta.fetched_at
        if meta.error and not info:
            result.warnings.append(f"yfinance info unavailable: {meta.error_kind}")
        if enrich:
            from trading_mcp.data.alpha_vantage_fetcher import fetch_av_normalized  # pylint: disable=import-outside-toplevel
            from trading_mcp.data.fmp_fetcher import fetch_fmp_normalized  # pylint: disable=import-outside-toplevel

            result = merge(result, fetch_av_normalized(sym), fetch_fmp_normalized(sym))
        if not result.fields:
            result.warnings.append("no fundamentals available")
        else:
            with cache.lock:
                cache.fundamentals[enrich] = CacheEntry(
                    data=result.copy_deep(), fetched_at=now, ttl=self._ttl["info"], source=",".join(result.sources)
                )
        return result

    def get_ticker(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> tuple[yf.Ticker, dict[str, Any], pd.DataFrame]:
        """Return ``(yfinance.Ticker, info, complete-bar history)`` (scanner API)."""
        sym = _norm_symbol(symbol)
        return yf.Ticker(sym), self.get_info(sym), self.get_hist(sym, period=period, interval=interval)

    def get_crypto_hist(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Daily crypto history (complete UTC days only)."""
        return self.get_hist(symbol, period=period)

    # ── options (backend chain) ─────────────────────────────────────

    def get_options_expirations(self, symbol: str) -> list[str]:
        """Expirations from the first backend that answers (1 h TTL, failures 30 s)."""
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        now = self._now()
        with cache.lock:
            entry = cache.options_expirations
        if entry is not None and entry.has_data and entry.is_fresh(now):
            return list(entry.data)
        failure = self._recent_failure(cache, ("expirations",))
        expirations: list[str] = []
        if failure is None:
            expirations = self._flights.do(("expirations", sym), lambda: self._fetch_options_expirations(sym))
        if expirations:
            with cache.lock:
                cache.options_expirations = CacheEntry(
                    data=list(expirations), fetched_at=now, ttl=self._ttl["options"], source="backends"
                )
            return list(expirations)
        if failure is None:
            self._remember_failure(cache, ("expirations",), UpstreamFailure(
                ERROR_EMPTY, f"expirations {sym}: no backend answered", retryable=True))
        if entry is not None and entry.has_data:
            logger.debug("Serving stale expirations for %s", sym)
            return list(entry.data)
        return []

    def _fetch_options_expirations(self, symbol: str) -> list[str]:
        """Ask each backend for expirations; the first non-empty answer wins."""
        for backend in self._resolve_backends():
            if self._bucket is not None:
                self._bucket.acquire(timeout=30.0)
            try:
                expirations = backend.get_expirations(symbol)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Backend %s expirations failed for %s: %s",
                               backend.name, symbol, type(exc).__name__)
                continue
            if expirations:
                return list(expirations)
        logger.warning("No backend returned expirations for %s", symbol)
        return []

    def get_options_chain(self, symbol: str, expiry: str) -> ChainData | None:
        """Chain from the first backend that resolves it (60 s TTL, failures 30 s).

        The returned :class:`ChainData` is a copy with two extra attributes:
        ``fetched_at`` (ISO 8601) and ``stale`` (True when an expired chain is
        served after a failure).
        """
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        now = self._now()
        with cache.lock:
            entry = cache.options_chains.get(expiry)
        if entry is not None and entry.has_data and entry.is_fresh(now):
            return self._chain_copy(entry, stale=False)
        failure = self._recent_failure(cache, ("chain", expiry))
        chain = None
        if failure is None:
            chain = self._flights.do(("chain", sym, expiry), lambda: self._fetch_chain_from_backends(sym, expiry))
        if chain is not None:
            fresh = CacheEntry(data=chain, fetched_at=now, ttl=self._ttl["options_chain"],
                               source=str(getattr(chain, "source", "")))
            with cache.lock:
                cache.options_chains[expiry] = fresh
            return self._chain_copy(fresh, stale=False)
        if failure is None:
            self._remember_failure(cache, ("chain", expiry), UpstreamFailure(
                ERROR_EMPTY, f"chain {sym} {expiry}: no backend answered", retryable=True))
        if entry is not None and entry.has_data:
            logger.debug("Serving stale chain for %s/%s", sym, expiry)
            return self._chain_copy(entry, stale=True)
        return None

    @staticmethod
    def _chain_copy(entry: CacheEntry, *, stale: bool) -> ChainData:
        chain: ChainData = entry.data
        out = dataclasses.replace(chain, calls=chain.calls.copy(deep=True), puts=chain.puts.copy(deep=True))
        setattr(out, "fetched_at", iso(from_epoch(entry.fetched_at)))
        setattr(out, "stale", stale)
        return out

    def chain_meta(self, symbol: str, expiry: str) -> dict[str, Any] | None:
        """Fetch time, age, source and staleness of a cached chain (no fetch)."""
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        with cache.lock:
            entry = cache.options_chains.get(expiry)
        if entry is None:
            return None
        now = self._now()
        return {
            "fetched_at": iso(from_epoch(entry.fetched_at)),
            "age_s": round(entry.age(now), 3),
            "source": entry.source,
            "fresh": entry.is_fresh(now),
        }

    def _fetch_chain_from_backends(self, symbol: str, expiry: str) -> ChainData | None:
        """Query each backend in priority order; the first success wins."""
        for backend in self._resolve_backends():
            if self._bucket is not None:
                self._bucket.acquire(timeout=30.0)
            try:
                chain = backend.get_chain(symbol, expiry)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Backend %s chain failed for %s/%s: %s",
                               backend.name, symbol, expiry, type(exc).__name__)
                continue
            if chain is not None:
                return chain_to_chaindata(chain)
        return None

    # ── macro inputs ────────────────────────────────────────────────

    def get_macro_context(self) -> dict[str, Any]:
        """Raw macro inputs in the legacy dict shape plus ``inputs`` (per-input provenance).

        See :func:`trading_mcp.data.macro_inputs.collect_macro_inputs`.
        """
        from trading_mcp.data.macro_inputs import collect_macro_inputs  # pylint: disable=import-outside-toplevel

        return collect_macro_inputs(self).legacy_dict()

    # ── cache control and monitoring ────────────────────────────────

    def clear(self, ticker: str | None = None) -> None:
        """Clear the memory cache of one ticker (or of every ticker)."""
        with self._global_lock:
            if ticker is None:
                self._cache.clear()
            else:
                self._cache.pop(_norm_symbol(ticker), None)

    def clear_symbols(self, symbols: Iterable[str], *, disk: bool = True) -> dict[str, int]:
        """Drop memory and disk entries of ``symbols``; returns what was removed."""
        removed = {"memory": 0, "disk": 0}
        for symbol in symbols:
            sym = _norm_symbol(symbol)
            with self._global_lock:
                if self._cache.pop(sym, None) is not None:
                    removed["memory"] += 1
            if disk:
                removed["disk"] += _disk_delete_symbol(sym)
        return removed

    def cache_stats(self) -> dict[str, Any]:
        """Counters and entry totals for monitoring."""
        now = self._now()
        total = fresh = 0
        with self._global_lock:
            caches = list(self._cache.values())
        for cache in caches:
            with cache.lock:
                entries = list(cache.hist.values()) + list(cache.options_chains.values())
                entries += [e for e in (cache.info, cache.quote, cache.options_expirations) if e is not None]
            for entry in entries:
                if entry.has_data:
                    total += 1
                    fresh += int(entry.is_fresh(now))
        with self._stats_lock:
            counters = dict(self._stats)
        bucket = self._bucket.stats() if self._bucket is not None else None
        return {"tickers_cached": len(caches), "total_entries": total, "fresh_entries": fresh,
                "counters": counters, "rate_limit": bucket}

    def get_data_freshness(self, symbol: str, data_type: str = "stock") -> dict[str, Any]:
        """Freshness of the cached daily history of ``symbol`` (no fetch).

        Returns ``freshness`` (``current`` when the series contains the latest
        complete session, ``stale`` when it misses one, ``unknown`` without
        data), ``last_data_date``, ``as_of`` (close time of the last bar),
        ``fetched_at`` and ``fetch_age_s``. ``data_type`` is kept for
        compatibility.
        """
        del data_type
        sym = _norm_symbol(symbol)
        cache = self._ensure_ticker_cache(sym)
        with cache.lock:
            keys = [key for key, entry in cache.hist.items() if entry.has_data and key[1] == "1d"]
        best: HistMeta | None = None
        for period, interval in keys:
            meta = self.last_hist_meta(sym, period, interval)
            if meta is not None and (best is None or (meta.last_bar_date or "") > (best.last_bar_date or "")):
                best = meta
        if best is None:
            return {"freshness": "unknown", "last_data_date": None, "as_of": None,
                    "fetched_at": None, "fetch_age_s": None}
        return {
            "freshness": "current" if best.up_to_date else "stale",
            "last_data_date": best.last_bar_date,
            "as_of": best.as_of,
            "fetched_at": best.fetched_at,
            "fetch_age_s": best.fetch_age_s,
        }


# ── Compatibility helpers ────────────────────────────────────────────

def freshness_label(
    last_ts: Any,
    now: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Age label (``live``/``recent``/``stale``/``cached``) of a DATA time.

    ``last_ts`` must be the data time (epoch seconds, aware datetime or ISO
    string), never a cache-insert time. ``None`` gives ``cached``.
    """
    if last_ts is None:
        return "cached"
    if isinstance(last_ts, (str, datetime)):
        moment = to_datetime(last_ts)
        if moment is None:
            return "cached"
        last_ts = moment.timestamp()
    limits = thresholds or {"live": 300, "recent": 3600, "stale": 86400}
    age = (time.time() if now is None else now) - float(last_ts)
    if age < limits["live"]:
        return "live"
    if age < limits["recent"]:
        return "recent"
    if age < limits["stale"]:
        return "stale"
    return "cached"


def get_last_data_date(hist: pd.DataFrame | None) -> str | None:
    """ISO date of the last bar, or ``None`` without data."""
    if hist is None or hist.empty:
        return None
    try:
        return hist.index[-1].date().isoformat()
    except (IndexError, AttributeError):
        return str(hist.index[-1])[:10]


# ── Module-level singleton ───────────────────────────────────────────

data_provider = DataProvider()
