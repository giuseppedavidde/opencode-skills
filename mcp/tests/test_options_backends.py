"""Tests for the pluggable options-data backends and the fallback chain."""

# pylint: disable=protected-access,import-outside-toplevel

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from trading_mcp import config
from trading_mcp.data.backends.base import (
    BackendCapabilities,
    ChainData,
    OptionsChain,
    OptionQuote,
    OptionRight,
)
from trading_mcp.data.backends.marketdata_backend import MarketDataBackend, _zipped_rows
from trading_mcp.data.backends.polygon_backend import PolygonBackend
from trading_mcp.data.backends.registry import build_backends, default_priority
from trading_mcp.data.backends.rest import TokenBucket
from trading_mcp.data.backends.thetadata_backend import (
    ThetaDataBackend,
    _rows_from_response,
)
from trading_mcp.data.backends.yfinance_backend import YFinanceBackend, _row_to_quote
from trading_mcp.data.provider import DataProvider

_EXPIRY = "2026-01-16"
_EXPIRY_DATE = date(2026, 1, 16)


# ── Fakes ─────────────────────────────────────────────────────────────
class FakeBackend:
    """In-memory backend for fallback/ordering tests."""

    def __init__(self, name, expirations=None, chain=None, raise_on=None):
        self.name = name
        self.capabilities = BackendCapabilities()
        self._expirations = expirations if expirations is not None else []
        self._chain = chain
        self._raise_on = raise_on

    def is_available(self) -> bool:
        """Fake backend is always available."""
        return True

    def get_expirations(self, _ticker: str) -> list[str]:
        """Return the canned expirations (or raise, for the failure test)."""
        if self._raise_on == "exp":
            raise RuntimeError("boom")
        return self._expirations

    def get_chain(self, _ticker: str, _expiry: str) -> OptionsChain | None:
        """Return the canned chain (or raise, for the failure test)."""
        if self._raise_on == "chain":
            raise RuntimeError("boom")
        return self._chain


def _quote(strike: float, right: OptionRight, gamma: float = 0.02) -> OptionQuote:
    return OptionQuote(
        strike=strike,
        right=right,
        expiry=_EXPIRY_DATE,
        bid=1.0,
        ask=1.2,
        volume=5,
        open_interest=100,
        implied_volatility=0.25,
        delta=0.5,
        gamma=gamma,
        theta=-0.05,
        vega=0.1,
    )


def _chain(source: str = "fake", native: bool = True) -> OptionsChain:
    return OptionsChain(
        ticker="X",
        spot=100.0,
        expiry=_EXPIRY_DATE,
        quotes=[_quote(105.0, OptionRight.CALL), _quote(95.0, OptionRight.PUT)],
        as_of=datetime(2026, 1, 1),
        source=source,
        greeks_are_native=native,
    )


# ── Config / registry ────────────────────────────────────────────────
def test_default_backend_priority_constant() -> None:
    """The shipped default priority is ThetaData -> ... -> yfinance."""
    assert config.DEFAULT_OPTIONS_BACKENDS == [
        "thetadata",
        "polygon",
        "marketdata",
        "yfinance",
    ]


def test_default_priority_reads_config() -> None:
    """default_priority mirrors the configured backend list."""
    assert default_priority() == list(config.OPTIONS_BACKENDS)


def test_registry_keeps_yfinance_last_and_filters(monkeypatch) -> None:
    """Only available backends survive; yfinance is always last."""
    monkeypatch.setattr(config, "POLYGON_API_KEY", "key")
    monkeypatch.setattr(config, "MARKETDATA_API_KEY", None)
    monkeypatch.setattr(config, "THETADATA_API_KEY", None)
    names = [b.name for b in build_backends(["thetadata", "polygon", "marketdata", "yfinance"])]
    assert names == ["polygon", "yfinance"]


def test_registry_zero_config_falls_back_to_yfinance(monkeypatch) -> None:
    """With no keys/daemon, only yfinance remains (default behaviour)."""
    monkeypatch.setattr(config, "POLYGON_API_KEY", None)
    monkeypatch.setattr(config, "MARKETDATA_API_KEY", None)
    monkeypatch.setattr(config, "THETADATA_API_KEY", None)
    names = [b.name for b in build_backends()]
    assert names == ["yfinance"]


def test_theta_unavailable_without_key(monkeypatch) -> None:
    """ThetaData is unavailable with no API key (no daemon probe attempted)."""
    monkeypatch.setattr(config, "THETADATA_API_KEY", None)
    assert ThetaDataBackend().is_available() is False


def test_polygon_and_marketdata_availability(monkeypatch) -> None:
    """REST backends gate purely on the presence of their API key."""
    monkeypatch.setattr(config, "POLYGON_API_KEY", "k")
    monkeypatch.setattr(config, "MARKETDATA_API_KEY", None)
    assert PolygonBackend().is_available() is True
    assert MarketDataBackend().is_available() is False


# ── Provider fallback chain ──────────────────────────────────────────
def test_provider_chain_uses_first_success() -> None:
    """The provider returns the first backend that resolves a chain."""
    empty = FakeBackend("empty", chain=None)
    good = FakeBackend("good", chain=_chain("good"))
    provider = DataProvider(backends=[empty, good])
    got = provider.get_options_chain("X", _EXPIRY)
    assert got is not None
    assert got.source == "good"
    assert not got.calls.empty and not got.puts.empty


def test_provider_chain_survives_backend_exception() -> None:
    """A backend that raises is skipped, not propagated."""
    boom = FakeBackend("boom", raise_on="chain")
    good = FakeBackend("good", chain=_chain("good"))
    provider = DataProvider(backends=[boom, good])
    assert provider.get_options_chain("X", _EXPIRY).source == "good"


def test_provider_chain_returns_none_when_all_fail() -> None:
    """No backend resolving yields ``None`` (not an exception)."""
    provider = DataProvider(backends=[FakeBackend("a"), FakeBackend("b")])
    assert provider.get_options_chain("X", _EXPIRY) is None


def test_provider_expirations_fallback() -> None:
    """Expirations use the first non-empty backend."""
    empty = FakeBackend("empty", expirations=[])
    good = FakeBackend("good", expirations=[_EXPIRY])
    provider = DataProvider(backends=[empty, good])
    assert provider.get_options_expirations("X") == [_EXPIRY]


def test_provider_expirations_survive_exception() -> None:
    """A raising backend is skipped for expirations too."""
    boom = FakeBackend("boom", raise_on="exp")
    good = FakeBackend("good", expirations=[_EXPIRY])
    provider = DataProvider(backends=[boom, good])
    assert provider.get_options_expirations("X") == [_EXPIRY]


def test_chain_data_bridge_columns() -> None:
    """The OptionsChain -> ChainData bridge keeps the pipeline columns."""
    data = ChainData(calls=pd.DataFrame(), puts=pd.DataFrame(), source="x")
    assert data.source == "x"
    chain = _chain("thetadata")
    from trading_mcp.data.backends.base import chain_to_chaindata  # local import

    bridged = chain_to_chaindata(chain)
    assert list(bridged.calls.columns) == [
        "strike",
        "bid",
        "ask",
        "volume",
        "openInterest",
        "impliedVolatility",
        "delta",
        "gamma",
        "theta",
        "vega",
    ]
    assert bridged.greeks_are_native is True


# ── data_source propagation ──────────────────────────────────────────
def test_data_source_propagates_to_gex(monkeypatch) -> None:
    """The winning backend id reaches GexResult.data_source."""
    from trading_mcp.analysis import gex as gex_mod  # local import

    expiry = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    payload = {
        "ticker": "X",
        "underlying_price": 100.0,
        "expirations": [expiry],
        "selected_expiry": expiry,
        "dte": 30,
        "calls": [
            {"strike": 105.0, "gamma": 0.02, "openInterest": 1000,
             "iv_used": 0.25, "iv_source": "vendor"}
        ],
        "puts": [
            {"strike": 95.0, "gamma": 0.03, "openInterest": 1500,
             "iv_used": 0.30, "iv_source": "vendor"}
        ],
        "risk_free_rate": {"value": 0.04},
        "_source": "thetadata",
        "data_source": "thetadata",
        "data_quality": "native-greeks",
    }
    monkeypatch.setattr(gex_mod, "fetch_options_chain", lambda *a, **k: payload)
    result = gex_mod.analyze_gex("X", max_expiries=1, top_n=5)
    assert result["source"] == "thetadata"
    assert result["data_source"] == "thetadata"
    assert result["data_quality"] == "native-greeks"
    assert result["n_strikes"] == 2


def test_gex_overlay_carries_data_source(monkeypatch) -> None:
    """GexOverlay exposes the inherited data_source."""
    from trading_mcp.analysis import gex as gex_mod  # local import
    from trading_mcp.analysis.breakout_context import MomentumBlock, build_gex_overlay

    monkeypatch.setattr(
        gex_mod,
        "analyze_gex",
        lambda *a, **k: {"regime": "long_gamma", "call_wall": 105.0, "put_wall": 95.0,
                         "gamma_flip": 100.0, "data_source": "polygon"},
    )
    overlay = build_gex_overlay("X", MomentumBlock())
    assert overlay.available is True
    assert overlay.data_source == "polygon"


# ── Native greeks preference ─────────────────────────────────────────
def test_apply_native_greeks_overrides_computed() -> None:
    """Vendor greeks/IV replace the locally computed values."""
    from trading_mcp.data.options_chain import _IV_SRC_VENDOR, _apply_native_greeks

    frame = pd.DataFrame(
        [
            {
                "strike": 100.0,
                "bid": 1.0,
                "ask": 1.2,
                "volume": 5,
                "openInterest": 10,
                "impliedVolatility": 0.42,
                "delta": 0.51,
                "gamma": 0.019,
                "theta": -0.05,
                "vega": 0.12,
            }
        ]
    )
    legs = [{"strike": 100.0, "gamma": 0.001, "iv_used": 0.2, "iv_source": "smile"}]
    out = _apply_native_greeks(legs, frame)
    assert out[0]["gamma"] == pytest.approx(0.019)
    assert out[0]["iv_used"] == pytest.approx(0.42)
    assert out[0]["iv_source"] == _IV_SRC_VENDOR


def test_apply_native_greeks_noop_without_gamma() -> None:
    """Without a native gamma column the legs are returned unchanged."""
    from trading_mcp.data.options_chain import _apply_native_greeks

    frame = pd.DataFrame([{"strike": 100.0, "impliedVolatility": 0.4}])
    legs = [{"strike": 100.0, "gamma": 0.001}]
    assert _apply_native_greeks(legs, frame)[0]["gamma"] == pytest.approx(0.001)


# ── Adapter parsers (offline) ────────────────────────────────────────
def test_yfinance_row_mapping() -> None:
    """A yfinance chain row maps to a normalised quote (no greeks)."""
    quote = _row_to_quote(
        {"strike": 100, "bid": 1.0, "ask": 1.2, "volume": 7, "openInterest": 9,
         "impliedVolatility": 0.3, "lastPrice": 1.1},
        OptionRight.CALL,
        _EXPIRY_DATE,
    )
    assert quote is not None
    assert quote.strike == 100.0
    assert quote.open_interest == 9
    assert quote.gamma is None


def test_polygon_row_mapping() -> None:
    """A Polygon snapshot row maps bid/ask/oi/greeks."""
    row = {
        "details": {"strike_price": 100.0, "contract_type": "call"},
        "last_quote": {"bid": 1.0, "ask": 1.1},
        "day": {"volume": 12, "close": 1.05},
        "open_interest": 33,
        "implied_volatility": 0.28,
        "greeks": {"delta": 0.5, "gamma": 0.02, "theta": -0.04, "vega": 0.1},
    }
    quote = PolygonBackend._row_to_quote(row, _EXPIRY_DATE)
    assert quote is not None
    assert quote.open_interest == 33
    assert quote.gamma == pytest.approx(0.02)


def test_marketdata_column_arrays_zip() -> None:
    """MarketData.app column arrays are zipped into records."""
    payload = {
        "strike": [95.0, 100.0],
        "side": ["put", "call"],
        "openInterest": [10, 20],
        "gamma": [0.01, 0.02],
    }
    rows = _zipped_rows(payload)
    assert len(rows) == 2
    assert rows[1]["side"] == "call"


def test_thetadata_response_columnar_parsing() -> None:
    """ThetaData column/header responses are decoded to records."""
    payload = {"header": {"format": ["strike", "right", "gamma"]}, "response": [[100.0, "C", 0.02]]}
    rows = _rows_from_response(payload)
    assert rows == [{"strike": 100.0, "right": "C", "gamma": 0.02}]


def test_thetadata_response_records_parsing() -> None:
    """ThetaData list-of-records responses pass through."""
    rows = _rows_from_response([{"strike": 100.0, "right": "P"}])
    assert rows == [{"strike": 100.0, "right": "P"}]


# ── Rate limiting ────────────────────────────────────────────────────
def test_token_bucket_spaces_requests() -> None:
    """A 60/min bucket enforces ~1s spacing using the injected clock."""
    slept: list[float] = []
    now = {"t": 0.0}

    def clock() -> float:
        return now["t"]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now["t"] += seconds

    bucket = TokenBucket(60, clock=clock, sleep=sleep)
    bucket.acquire()
    bucket.acquire()
    assert slept and slept[-1] == pytest.approx(1.0)


def test_token_bucket_disabled() -> None:
    """A zero limit disables throttling entirely."""
    slept: list[float] = []
    bucket = TokenBucket(0, clock=lambda: 0.0, sleep=slept.append)
    bucket.acquire()
    bucket.acquire()
    assert not slept


def test_frame_equality_smoke() -> None:
    """Bridge frames keep a deterministic empty shape for empty quotes."""
    from trading_mcp.data.backends.base import chain_to_chaindata

    empty = OptionsChain(
        ticker="X", spot=1.0, expiry=_EXPIRY_DATE, quotes=[], as_of=datetime(2026, 1, 1), source="x"
    )
    bridged = chain_to_chaindata(empty)
    assert_frame_equal(bridged.calls, pd.DataFrame(columns=bridged.calls.columns))


@pytest.mark.network
def test_yfinance_backend_live_smoke() -> None:
    """yfinance backend returns real expirations/chain (requires network)."""
    backend = YFinanceBackend()
    expirations = backend.get_expirations("SPY")
    assert expirations
    chain = backend.get_chain("SPY", expirations[0])
    assert chain is not None
    assert chain.quotes
