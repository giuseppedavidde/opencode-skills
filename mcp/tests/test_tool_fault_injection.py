"""Fault injection through the MCP client: no invented numbers, explicit flags (DATA-02/06/07/09/13)."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastmcp import Client

from trading_mcp.data import crypto as crypto_mod
from trading_mcp.data import http_policy
from trading_mcp.data import macro_inputs
from trading_mcp.data import market_calendar as mcal
from trading_mcp.data import provider as prov
from trading_mcp.data import result_cache as rc
from trading_mcp.data.http_policy import UpstreamFailure
from trading_mcp.data.risk_free import get_risk_free_provider
from trading_mcp.mcp import initialize_mcp
from trading_mcp.tools import _market_tools, _stock_tools

# Numeric keys allowed in a failed answer: counters, parameter echoes and envelope metadata.
NUMERIC_METADATA = {
    "cache_age_s", "available_bars", "required_bars", "history_bars", "bars_returned", "bars_available",
    "tickers_scanned", "tickers_passed", "tickers_processed", "failures", "insufficient_data_count",
    "workers", "elapsed_seconds", "min_score_threshold", "coverage_pct", "deadline_s", "lookback_months",
    "target_vol", "num_quote_iv", "num_synthetic_iv", "num_fallback_iv", "max_custom_tickers",
    "max_universe_tickers", "max_top_n", "max_workers", "memory", "disk", "bullish", "total",
}


def invented_numbers(payload: Any, path: str = "") -> list[str]:
    """Paths of numeric values that are not counters or metadata."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in NUMERIC_METADATA or key == "limits":
                continue
            found.extend(invented_numbers(value, f"{path}.{key}"))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(invented_numbers(value, f"{path}[{index}]"))
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        found.append(f"{path}={payload}")
    return found


class YFPricesMissingError(Exception):
    """Same class name as the yfinance 'possibly delisted' error."""


def _daily(symbol: str, n: int, start: float, step: float) -> pd.DataFrame:
    ex = mcal.exchange_for(symbol)
    last = mcal.last_complete_session_date(ex)
    if ex.always_open:
        days = pd.date_range(end=pd.Timestamp(last), periods=n, freq="D")
    else:
        days = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    index = pd.DatetimeIndex([pd.Timestamp(d.date()).tz_localize(ex.tz) for d in days], name="Date")
    close = [start + step * i for i in range(n)]
    return pd.DataFrame({"Open": close, "High": [c * 1.01 for c in close], "Low": [c * 0.99 for c in close],
                         "Close": close, "Adj Close": [c * 0.99 for c in close],
                         "Volume": [1_000_000] * n}, index=index)


class Market:
    """Fake yfinance keyed by symbol: frames, chart prices and info dicts."""

    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {}
        self.prices: dict[str, float] = {}
        self.infos: dict[str, dict] = {}
        self.down: set[str] = set()

    def history(self, symbol: str, period: str, interval: str):
        if symbol in self.down or symbol not in self.frames:
            raise YFPricesMissingError(f"{symbol}: possibly delisted")
        meta = {"currency": "USD"}
        if symbol in self.prices:
            meta.update(regularMarketPrice=self.prices[symbol], regularMarketTime=int(time.time()) - 10)
        return self.frames[symbol].copy(), meta

    def info(self, symbol: str):
        if symbol in self.down:
            raise YFPricesMissingError(symbol)
        return dict(self.infos.get(symbol, {"trailingPegRatio": None}))


@pytest.fixture()
def market(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Market:
    fake = Market()
    monkeypatch.setattr(prov, "_yf_history", fake.history)
    monkeypatch.setattr(prov, "_yf_info", fake.info)
    monkeypatch.setattr(prov, "_fmp_info", lambda symbol: {})
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(http_policy, "backoff_delay", lambda *a, **k: 0.0)
    monkeypatch.setattr(rc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(rc, "CACHE_FILE", tmp_path / "result_cache.json")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    _reset()
    yield fake
    _reset()


def _reset() -> None:
    prov.data_provider.clear()
    rc.result_cache.clear_all()
    get_risk_free_provider().invalidate()
    macro_inputs.clear_crypto_context_cache()
    crypto_mod.clear_coingecko_cache()
    _market_tools._macro_cache = None
    _market_tools._macro_cache_time = 0.0


@pytest.fixture()
def call(tmp_path: Path):
    server = initialize_mcp(str(tmp_path), str(tmp_path))

    def _call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        async def _run() -> dict[str, Any]:
            async with Client(server) as client:
                result = await client.call_tool(name, args or {})
                return result.structured_content or {}
        return asyncio.run(_run())

    return _call


# ── fetch_stock_data ─────────────────────────────────────────────────

def test_stock_failure_has_no_price_and_an_error(market: Market, call) -> None:
    payload = call("fetch_stock_data", {"ticker": "ZZZZ"})
    assert payload["error"] and payload["error_kind"] == "blocking"
    assert payload["current_price"] is None
    assert payload["degraded"] is True and payload["error_retryable"] is False
    assert invented_numbers(payload) == []


def test_stock_without_quote_is_degraded_not_zero(market: Market, call) -> None:
    market.frames["AAPL"] = _daily("AAPL", 300, 100.0, 0.1)
    payload = call("fetch_stock_data", {"ticker": "AAPL", "fields": ["quote", "ohlcv"]})
    assert payload["current_price"] is None and payload["degraded"] is True
    assert payload["quote"]["price"] is None and payload["quote"]["error_kind"] == "empty"
    assert payload["bars_returned"] == 252 and payload["truncated"] is True
    assert any("quote unavailable" in w for w in payload["warnings"])


def test_stock_success_contract(market: Market, call) -> None:
    market.frames["AAPL"] = _daily("AAPL", 300, 100.0, 0.1)
    market.prices["AAPL"] = 131.5
    market.infos["AAPL"] = {"quoteType": "EQUITY", "shortName": "Apple", "currentPrice": 999.0,
                            "regularMarketPrice": 130.0, "dividendYield": 0.31,
                            "trailingAnnualDividendYield": 0.0030, "debtToEquity": 84.3, "marketCap": 3e12}
    payload = call("fetch_stock_data", {"ticker": "aapl", "max_bars": 50})
    assert payload["current_price"] == 131.5
    assert payload["as_of"] == payload["quote"]["as_of"] and payload["as_of"][-6] in "+-"
    assert payload["bars_returned"] == 50 and payload["bars_available"] == 300 and payload["truncated"]
    assert payload["ohlcv"][-1]["adj_close"] is not None
    info = payload["info"]
    assert "currentPrice" not in info and "dividendYield" not in info and "debtToEquity" not in info
    assert info["debt_to_equity_ratio"] == pytest.approx(0.843)
    assert payload["info_units"]["trailingAnnualDividendYield"].startswith("fraction")
    assert payload["events"]["dividend_yield"] == pytest.approx(0.003)
    assert payload["partial_bar_dropped"] in (True, False)
    assert payload["computed_at"].endswith("+00:00")
    assert "yfinance:chart" in payload["sources"]


def test_stock_fields_filter(market: Market, call) -> None:
    market.frames["AAPL"] = _daily("AAPL", 60, 100.0, 0.1)
    market.prices["AAPL"] = 105.0
    payload = call("fetch_stock_data", {"ticker": "AAPL", "fields": ["quote", "bogus"]})
    assert payload["fields"] == ["quote"]
    assert payload["ohlcv"] == [] and payload["bars_returned"] == 0
    assert any("unknown fields" in w for w in payload["warnings"])


# ── fetch_crypto_data ────────────────────────────────────────────────

def test_unknown_coin_is_an_error_not_a_made_up_symbol(market: Market, call, monkeypatch) -> None:
    def not_found(*args, **kwargs):
        raise UpstreamFailure("not_found", "coingecko coin: HTTP 404", retryable=False, status=404)

    monkeypatch.setattr(crypto_mod, "get_json", not_found)
    payload = call("fetch_crypto_data", {"coin_id": "not-a-coin"})
    assert payload["error"] and payload["symbol"] is None
    assert payload["current_price_usd"] is None and payload["error_retryable"] is False
    assert invented_numbers(payload) == []


def test_coingecko_down_uses_the_yahoo_quote(market: Market, call) -> None:
    market.frames["BTC-USD"] = _daily("BTC-USD", 40, 90000.0, 10.0)
    market.prices["BTC-USD"] = 91234.5
    payload = call("fetch_crypto_data", {"coin_id": "bitcoin", "max_bars": 10})
    assert payload["symbol"] == "BTC-USD" and payload["symbol_source"] == "curated_map"
    assert payload["current_price_usd"] == 91234.5 and payload["price_source"] == "yfinance:chart"
    assert payload["market_cap"] is None and payload["degraded"] is True
    assert any("coingecko unavailable" in w for w in payload["warnings"])
    last_bar = payload["ohlcv"][-1]["date"]
    assert last_bar < mcal.exchange_today("BTC-USD").isoformat()


def test_numeric_suffix_symbols_are_mapped() -> None:
    assert crypto_mod.resolve_symbol("uniswap", None) == ("UNI7083-USD", "curated_map")
    assert crypto_mod.resolve_symbol("BTC-USD", None) == ("BTC-USD", "yahoo_symbol")
    assert crypto_mod.resolve_symbol("foo", {"symbol": "foo"}) == ("FOO-USD", "coingecko_symbol_unverified")


# ── macro ────────────────────────────────────────────────────────────

def test_macro_offline_is_degraded_unknown_and_defensive(market: Market, call) -> None:
    payload = call("get_macro_context")
    assert payload["vix"] is None and payload["fed_rate"] is None and payload["dxy_trend"] is None
    assert "configured" in payload["fallback_reason"]
    assert payload["detected_regime"] == "unknown" and payload["macro_window"] == "DEFENSIVE"
    assert payload["degraded"] is True
    assert payload["inputs"]["vix"]["value"] is None and payload["inputs"]["vix"]["error_kind"]
    again = call("get_macro_context")
    assert again["cached"] is False


def _macro_market(market: Market, vix: float) -> None:
    market.frames["^GSPC"] = _daily("^GSPC", 260, 5000.0, 4.0)
    market.frames["DX-Y.NYB"] = _daily("DX-Y.NYB", 22, 100.0, 0.0)
    for symbol, price in (("^VIX", vix), ("^VIX3M", vix - 2), ("^IRX", 4.2), ("DX-Y.NYB", 100.0),
                          ("BTC-USD", 90000.0), ("^GSPC", 6040.0)):
        market.prices[symbol] = price
        market.frames.setdefault(symbol, _daily(symbol, 10, price, 0.0))


def test_macro_live_inputs_have_data_times(market: Market, call) -> None:
    _macro_market(market, 30.0)
    payload = call("get_macro_context")
    assert payload["vix"] == 30.0 and payload["fed_rate"] == pytest.approx(4.2)
    assert payload["equity_trend"] == "up" and payload["dxy_trend"] == "neutral"
    assert payload["detected_regime"] == "high_volatility" and payload["macro_window"] == "SELECTIVE"
    assert payload["inputs"]["vix"]["as_of"] and payload["inputs"]["spx"]["as_of"]
    assert payload["fed_rate_as_of"] and payload["fallback_reason"] is None
    assert payload["degraded"] is False and payload["as_of"]
    assert payload["btc_dominance"] is None  # crypto context offline: null, not invented
    assert call("get_macro_context")["cached"] is True


def test_clear_macro_cache_reaches_the_provider(market: Market, call) -> None:
    _macro_market(market, 15.0)
    first = call("get_macro_context")
    assert first["vix"] == 15.0
    market.prices["^VIX"] = 40.0
    assert call("get_macro_context")["vix"] == 15.0  # 60 s answer cache
    cleared = call("clear_macro_cache")
    assert cleared["status"] == "ok" and cleared["cleared_entries"]["memory"] >= 1
    assert "^VIX" in cleared["cleared_symbols"]
    fresh = call("get_macro_context")
    assert fresh["vix"] == 40.0 and fresh["detected_regime"] == "crisis"


# ── scan_market envelope ─────────────────────────────────────────────

def _row(symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "final_score": 70.0, "sector": "Technology", "price": 10.0,
            "price_as_of": "2026-11-20T15:59:00-05:00", "price_source": "yfinance:chart",
            "dimensions": [{"name": "Wyckoff Phase", "score": 70, "detail": ""}],
            "modifiers": {}, "indicators": {}, "flags": [], "pattern": "", "sentiment_breakdown": None}


def test_partial_scan_is_degraded_and_never_cached(market: Market, call, monkeypatch) -> None:
    calls: list[str] = []

    def fake_process(t_dict, fetch_news=False, regime=None):
        calls.append(t_dict["symbol"])
        if t_dict["symbol"] == "CCC":
            raise RuntimeError("boom")
        return _row("AAA") if t_dict["symbol"] == "AAA" else None

    monkeypatch.setattr(_stock_tools, "process_ticker", fake_process)
    payload = call("scan_market", {"tickers": "AAA,BBB,CCC", "min_score": 0})
    assert payload["degraded"] is True and payload["failures"] == 2
    assert payload["coverage_pct"] == pytest.approx(33.3)
    reasons = {item["ticker"]: item["reason"] for item in payload["failed_tickers"]}
    assert set(reasons) == {"BBB", "CCC"} and "RuntimeError" in reasons["CCC"]
    assert [row["ticker"] for row in payload["results"]] == ["AAA"]
    assert payload["results"][0]["price_as_of"]
    call("scan_market", {"tickers": "AAA,BBB,CCC", "min_score": 0})
    assert len(calls) == 6  # the degraded scan was not cached


def test_scan_with_no_result_is_an_error(market: Market, call, monkeypatch) -> None:
    monkeypatch.setattr(_stock_tools, "process_ticker", lambda t, fetch_news=False, regime=None: None)
    payload = call("scan_market", {"tickers": "AAA,BBB"})
    assert payload["error"] and payload["error_kind"] == "blocking"
    assert payload["coverage_pct"] == 0.0 and payload["results"] == []


def test_scan_deadline_is_real(market: Market, call, monkeypatch) -> None:
    monkeypatch.setattr(_stock_tools, "MIN_SCAN_DEADLINE_S", 0.05)

    def slow(t_dict, fetch_news=False, regime=None):
        time.sleep(1.0)
        return _row(t_dict["symbol"])

    monkeypatch.setattr(_stock_tools, "process_ticker", slow)
    started = time.monotonic()
    payload = call("scan_market", {"tickers": "AAA,BBB", "deadline_s": 0.2})
    assert time.monotonic() - started < 0.9
    assert payload["deadline_hit"] is True and payload["degraded"] is True
    assert {item["reason"] for item in payload["failed_tickers"]} == {"deadline exceeded"}


def test_scan_input_limits(market: Market, call, monkeypatch) -> None:
    too_many = ",".join(f"T{i}" for i in range(201))
    payload = call("scan_market", {"tickers": too_many})
    assert payload["error"] and "limit is 200" in payload["error"]
    monkeypatch.setattr(_stock_tools, "process_ticker", lambda t, fetch_news=False, regime=None: _row(t["symbol"]))
    ok = call("scan_market", {"tickers": "AAA", "top_n": 500, "min_score": 0})
    assert any("top_n=500 clamped to 50" in w for w in ok["warnings"])
    assert ok["degraded"] is False and ok["coverage_pct"] == 100.0


def test_scan_fetch_news_defaults_to_false(market: Market, call, monkeypatch) -> None:
    seen: list[bool] = []

    def spy(t_dict, fetch_news=True, regime=None):
        seen.append(fetch_news)
        return _row(t_dict["symbol"])

    monkeypatch.setattr(_stock_tools, "process_ticker", spy)
    call("scan_market", {"tickers": "AAA"})
    assert seen == [False]


def test_analyze_stock_short_history_has_no_price(market: Market, call) -> None:
    market.frames["NEW"] = _daily("NEW", 20, 10.0, 0.1)
    market.prices["NEW"] = 12.0
    market.infos["NEW"] = {"quoteType": "EQUITY", "shortName": "New"}
    payload = call("analyze_stock", {"ticker": "NEW", "fetch_news": False})
    assert payload["status"] == "insufficient_data" and payload["price"] is None
    assert payload["degraded"] is True
    assert payload["signal_alignment"]["pct"] is None


def test_bakshi_and_tsmom_errors_have_no_numbers(market: Market, call) -> None:
    for name in ("bakshi_signals", "tsmom_signals", "bali_signals"):
        payload = call(name, {"ticker": "ZZZZ"})
        assert payload["error"], name
        assert payload["degraded"] is True
        assert invented_numbers(payload) == [], (name, invented_numbers(payload))


def test_quote_fallback_after_expiry_is_flagged(market: Market) -> None:
    market.frames["AAPL"] = _daily("AAPL", 10, 100.0, 0.0)
    market.prices["AAPL"] = 100.0
    provider = prov.data_provider
    assert provider.get_quote("AAPL").price == 100.0
    entry = provider._ensure_ticker_cache("AAPL").quote
    entry.fetched_at -= timedelta(minutes=5).total_seconds()
    market.down.add("AAPL")
    quote = provider.get_quote("AAPL")
    assert quote.price == 100.0 and quote.cached and quote.warnings
