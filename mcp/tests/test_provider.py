"""DataProvider: partial bars, data-time freshness, failures, backoff, single-flight, copies."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trading_mcp.data import http_policy
from trading_mcp.data import provider as prov
from trading_mcp.data.provider import DataProvider

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


class YFRateLimitError(Exception):
    """Same class name as the yfinance 429 error."""


class YFPricesMissingError(Exception):
    """Same class name as the yfinance 'possibly delisted' error."""


def _ts(*args: int) -> float:
    return datetime(*args, tzinfo=UTC).timestamp()


def _bars(last: date, n: int = 30, tz: str = "America/New_York", start_price: float = 100.0) -> pd.DataFrame:
    days = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    index = pd.DatetimeIndex([pd.Timestamp(d.date()).tz_localize(tz) for d in days], name="Date")
    close = [start_price + i for i in range(n)]
    return pd.DataFrame(
        {
            "Open": close, "High": [c + 1 for c in close], "Low": [c - 1 for c in close],
            "Close": close, "Adj Close": [c * 0.98 for c in close], "Volume": [1_000 + i for i in range(n)],
        },
        index=index,
    )


class Upstream:
    """Scriptable fake for the yfinance calls of the provider."""

    def __init__(self) -> None:
        self.hist_calls = 0
        self.info_calls = 0
        self.frame: pd.DataFrame = _bars(date(2026, 11, 20))
        self.chart: dict = {"regularMarketPrice": 129.5, "regularMarketTime": int(_ts(2026, 11, 20, 19, 59, 30)),
                            "currency": "USD"}
        self.info: dict = {"quoteType": "EQUITY", "shortName": "Test", "regularMarketPrice": 129.4,
                           "regularMarketTime": int(_ts(2026, 11, 20, 19, 59, 0)), "bid": 129.3, "ask": 129.6,
                           "bidSize": 3, "askSize": 5, "marketState": "REGULAR", "exchangeDataDelayedBy": 0}
        self.hist_errors: list[BaseException] = []
        self.info_errors: list[BaseException] = []
        self.delay = 0.0

    def history(self, symbol: str, period: str, interval: str):
        self.hist_calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.hist_errors:
            raise self.hist_errors.pop(0)
        return self.frame.copy(), dict(self.chart)

    def get_info(self, symbol: str):
        self.info_calls += 1
        if self.info_errors:
            raise self.info_errors.pop(0)
        return dict(self.info)


@pytest.fixture()
def upstream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Upstream:
    fake = Upstream()
    monkeypatch.setattr(prov, "_yf_history", fake.history)
    monkeypatch.setattr(prov, "_yf_info", fake.get_info)
    monkeypatch.setattr(prov, "_fmp_info", lambda symbol: {})
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(http_policy, "backoff_delay", lambda *a, **k: 0.0)
    return fake


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _provider(clock: Clock) -> DataProvider:
    return DataProvider(clock=clock, bucket=None)


# ── partial bars and data time ───────────────────────────────────────

def test_open_session_bar_is_dropped(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))  # 15:00 New York
    frame, meta = _provider(clock).get_hist_with_meta("AAPL")
    assert frame.index[-1].date() == date(2026, 11, 19)
    assert meta.partial_dropped and meta.partial_bar_date == "2026-11-20"
    assert meta.as_of == "2026-11-19T16:00:00-05:00"
    assert meta.last_bar_complete is True
    assert meta.up_to_date is True
    assert meta.session_state == "regular"
    assert meta.price_adjustment.startswith("split_adjusted")


def test_include_partial_keeps_the_open_bar_with_vendor_time(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))
    frame, meta = _provider(clock).get_hist_with_meta("AAPL", include_partial=True)
    assert frame.index[-1].date() == date(2026, 11, 20)
    assert meta.last_bar_complete is False
    assert meta.as_of == "2026-11-20T14:59:30-05:00"


def test_bar_fetched_in_session_never_becomes_complete(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))
    provider = _provider(clock)
    provider.get_hist("AAPL")
    clock.now = _ts(2026, 11, 20, 22, 0)  # 17:00 New York, the bar is now final upstream
    upstream.hist_errors.append(YFRateLimitError("Too Many Requests"))
    upstream.hist_errors.append(YFRateLimitError("Too Many Requests"))
    upstream.hist_errors.append(YFRateLimitError("Too Many Requests"))
    frame, meta = provider.get_hist_with_meta("AAPL")
    assert meta.stale is True and meta.error_kind == "rate_limited"
    assert frame.index[-1].date() == date(2026, 11, 19)
    assert meta.up_to_date is False


def test_entry_is_refetched_after_the_session_completes(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))
    provider = _provider(clock)
    provider.get_hist("AAPL")
    provider.get_hist("AAPL")
    assert upstream.hist_calls == 1
    clock.now = _ts(2026, 11, 20, 21, 30)
    frame = provider.get_hist("AAPL")
    assert upstream.hist_calls == 2
    assert frame.index[-1].date() == date(2026, 11, 20)


def test_crypto_drops_the_current_utc_day(upstream: Upstream) -> None:
    upstream.frame = _bars(date(2026, 11, 20), tz="UTC")
    clock = Clock(_ts(2026, 11, 20, 10, 0))
    frame, meta = _provider(clock).get_hist_with_meta("BTC-USD")
    assert frame.index[-1].date() == date(2026, 11, 19)
    assert meta.as_of == "2026-11-20T00:00:00+00:00"


def test_disk_hit_keeps_the_original_fetch_time(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 21, 30))
    _provider(clock).get_hist("AAPL")
    clock.now += 100
    other = _provider(clock)
    frame, meta = other.get_hist_with_meta("AAPL")
    assert upstream.hist_calls == 1
    assert meta.cache == "disk"
    assert meta.fetched_at == "2026-11-20T21:30:00+00:00"
    assert meta.fetch_age_s == pytest.approx(100.0)
    assert not frame.empty


def test_data_freshness_reads_the_data_time(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 21, 30))
    provider = _provider(clock)
    provider.get_hist("AAPL")
    fresh = provider.get_data_freshness("AAPL")
    assert fresh["freshness"] == "current"
    assert fresh["as_of"] == "2026-11-20T16:00:00-05:00"
    clock.now = _ts(2026, 11, 24, 22, 0)  # two sessions later, no refetch
    assert provider.get_data_freshness("AAPL")["freshness"] == "stale"


# ── failures, retries and rate limits ────────────────────────────────

def test_429_is_retried_with_backoff(upstream: Upstream) -> None:
    upstream.hist_errors = [YFRateLimitError("Too Many Requests"), YFRateLimitError("Too Many Requests")]
    frame, meta = _provider(Clock(_ts(2026, 11, 20, 21, 30))).get_hist_with_meta("AAPL")
    assert upstream.hist_calls == 3
    assert meta.error is None and not frame.empty


def test_unknown_symbol_is_not_retried(upstream: Upstream) -> None:
    upstream.hist_errors = [YFPricesMissingError("possibly delisted")]
    frame, meta = _provider(Clock(_ts(2026, 11, 20, 21, 30))).get_hist_with_meta("NOPE")
    assert upstream.hist_calls == 1
    assert frame.empty and meta.error_kind == "not_found"


def test_failures_are_cached_for_30_seconds_only(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 21, 30))
    provider = _provider(clock)
    upstream.hist_errors = [YFPricesMissingError("possibly delisted")]
    assert provider.get_hist("AAPL").empty
    assert provider.get_hist("AAPL").empty
    assert upstream.hist_calls == 1
    clock.now += 31
    assert not provider.get_hist("AAPL").empty
    assert upstream.hist_calls == 2


def test_empty_answer_is_an_error_not_data(upstream: Upstream) -> None:
    upstream.frame = pd.DataFrame()
    frame, meta = _provider(Clock(_ts(2026, 11, 20, 21, 30))).get_hist_with_meta("AAPL")
    assert frame.empty and meta.error_kind == "empty"


def test_rate_limit_blocks_the_shared_bucket() -> None:
    bucket = http_policy.TokenBucket(100.0, 1.0)
    bucket.penalize(5.0)
    assert bucket.acquire(timeout=0.05) is False
    assert bucket.stats()["penalties"] == 1


# ── concurrency and copies ───────────────────────────────────────────

def test_single_flight_collapses_parallel_fetches(upstream: Upstream) -> None:
    upstream.delay = 0.2
    provider = _provider(Clock(_ts(2026, 11, 20, 21, 30)))
    frames: list[pd.DataFrame] = []
    lock = threading.Lock()

    def worker() -> None:
        frame = provider.get_hist("MSFT")
        with lock:
            frames.append(frame)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert upstream.hist_calls == 1
    assert len(frames) == 8
    assert len({id(frame) for frame in frames}) == 8


def test_callers_get_deep_copies(upstream: Upstream) -> None:
    provider = _provider(Clock(_ts(2026, 11, 20, 21, 30)))
    frame = provider.get_hist("AAPL")
    frame.iloc[-1, frame.columns.get_loc("Close")] = -1.0
    info = provider.get_info("AAPL")
    info["shortName"] = "MUTATED"
    assert provider.get_hist("AAPL")["Close"].iloc[-1] > 0
    assert provider.get_info("AAPL")["shortName"] == "Test"
    assert upstream.info_calls == 1


def test_history_request_is_not_auto_adjusted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append(kwargs)
            return _bars(date(2026, 11, 20))

    monkeypatch.setattr(prov.yf, "Ticker", FakeTicker)
    frame, _ = prov._yf_history("AAPL", "1y", "1d")
    assert calls[0]["auto_adjust"] is False
    assert "Adj Close" in frame.columns


# ── quotes ───────────────────────────────────────────────────────────

def test_quote_data_time_comes_from_the_vendor(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))
    quote = _provider(clock).get_quote("AAPL")
    assert quote.price == 129.5
    assert quote.as_of == "2026-11-20T14:59:30-05:00"
    assert quote.source == "yfinance:chart"
    assert quote.age_s == pytest.approx(30.0)
    assert quote.freshness == "realtime" and quote.stale is False
    assert quote.session_state == "regular"
    assert quote.previous_close == 128.0


def test_quote_older_than_60s_in_session_is_stale(upstream: Upstream) -> None:
    upstream.chart["regularMarketTime"] = int(_ts(2026, 11, 20, 19, 50))
    quote = _provider(Clock(_ts(2026, 11, 20, 20, 0))).get_quote("AAPL")
    assert quote.age_s == pytest.approx(600.0)
    assert quote.stale is True and quote.freshness == "stale"


def test_quote_after_the_close_is_the_last_close(upstream: Upstream) -> None:
    upstream.chart["regularMarketTime"] = int(_ts(2026, 11, 20, 21, 0, 1))
    quote = _provider(Clock(_ts(2026, 11, 21, 15, 0))).get_quote("AAPL")
    assert quote.session_state == "closed"
    assert quote.freshness == "last_close" and quote.stale is False


def test_quote_cache_ttl_is_30_seconds(upstream: Upstream) -> None:
    clock = Clock(_ts(2026, 11, 20, 20, 0))
    provider = _provider(clock)
    provider.get_quote("AAPL")
    assert provider.get_quote("AAPL").cached is True
    clock.now += 31
    assert provider.get_quote("AAPL").cached is False
    assert upstream.hist_calls == 2


def test_quote_with_book_reads_bid_and_ask(upstream: Upstream) -> None:
    quote = _provider(Clock(_ts(2026, 11, 20, 20, 0))).get_quote("AAPL", with_book=True)
    assert (quote.bid, quote.ask, quote.mid) == (129.3, 129.6, 129.45)
    assert quote.market_state == "REGULAR" and quote.source == "yfinance:quote"


def test_failed_quote_has_no_price(upstream: Upstream) -> None:
    upstream.hist_errors = [YFPricesMissingError("possibly delisted")]
    quote = _provider(Clock(_ts(2026, 11, 20, 20, 0))).get_quote("NOPE")
    assert quote.price is None
    assert quote.error_kind == "not_found" and quote.stale is True


def test_info_seeds_a_fresh_quote(upstream: Upstream) -> None:
    provider = _provider(Clock(_ts(2026, 11, 20, 20, 0)))
    provider.get_info("AAPL")
    quote = provider.get_quote("AAPL")
    assert quote.cached is True and quote.bid == 129.3
    assert upstream.hist_calls == 0


def test_fmp_is_not_asked_for_indices(upstream: Upstream, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []
    monkeypatch.setattr(prov, "_fmp_info", lambda symbol: asked.append(symbol) or {})
    upstream.info = {"trailingPegRatio": None}
    provider = _provider(Clock(_ts(2026, 11, 20, 20, 0)))
    info, meta = provider.get_info_with_meta("^VIX")
    assert info == {} and meta.error_kind == "not_found"
    provider.get_info("ZZZZ")
    assert asked == ["ZZZZ"]


def test_clear_symbols_drops_memory_and_disk(upstream: Upstream, tmp_path: Path) -> None:
    clock = Clock(_ts(2026, 11, 20, 21, 30))
    provider = _provider(clock)
    provider.get_hist("^VIX")
    assert list(tmp_path.glob("hist__VIX_*.json"))
    removed = provider.clear_symbols(["^VIX"])
    assert removed["memory"] == 1 and removed["disk"] >= 1
    assert not list(tmp_path.glob("hist__VIX_*.json"))
    provider.get_hist("^VIX")
    assert upstream.hist_calls == 2
