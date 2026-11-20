"""Regime object (hysteresis, equity-only inputs), risk-free fallback, prices, cache dirs, quotes."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from trading_mcp.analysis.macro import Regime, current_regime, regime_to_macro_window
from trading_mcp.data import cache_paths, prices, risk_free
from trading_mcp.data.macro_inputs import MacroInput, MacroInputs
from trading_mcp.data.quotes import Quote, evaluate

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)


def _inputs(vix: float | None, trend: str | None = "up", dxy_trend: str | None = "neutral",
            fear_greed: float | None = 50.0) -> MacroInputs:
    def item(name: str, value: float | None) -> MacroInput:
        return MacroInput(name=name, value=value, as_of="2026-11-20T14:59:00-05:00", source="test")

    return MacroInputs(
        vix=item("vix", vix), vix3m=item("vix3m", None), spx=item("spx", 6000.0 if trend else None),
        dxy=item("dxy", 100.0), rate=item("rate", 4.2), btc=item("btc", 90000.0),
        btc_dominance=item("btc_dominance", 55.0), fear_greed=item("fear_greed", fear_greed),
        equity_trend=trend, dxy_trend=dxy_trend,
    )


class TestRegimeObject:
    def test_hysteresis_enters_at_25_and_leaves_below_23(self, tmp_path: Path) -> None:
        state = tmp_path / "regime_state.json"
        assert current_regime(_inputs(24.0), state_path=state, now=NOW).regime is Regime.TRENDING_BULL
        high = current_regime(_inputs(25.5), state_path=state, now=NOW)
        assert high.regime is Regime.HIGH_VOLATILITY and high.changed
        held = current_regime(_inputs(24.0), state_path=state, now=NOW + timedelta(minutes=5))
        assert held.regime is Regime.HIGH_VOLATILITY and held.hysteresis_applied
        assert held.since == high.since
        left = current_regime(_inputs(22.9), state_path=state, now=NOW + timedelta(minutes=10))
        assert left.regime is Regime.TRENDING_BULL and left.previous_regime is Regime.HIGH_VOLATILITY

    def test_crisis_band(self, tmp_path: Path) -> None:
        state = tmp_path / "s.json"
        assert current_regime(_inputs(36.0), state_path=state, now=NOW).regime is Regime.CRISIS
        assert current_regime(_inputs(33.0), state_path=state, now=NOW).regime is Regime.CRISIS
        assert current_regime(_inputs(31.0), state_path=state, now=NOW).regime is Regime.HIGH_VOLATILITY

    def test_old_state_is_ignored(self, tmp_path: Path) -> None:
        state = tmp_path / "s.json"
        current_regime(_inputs(26.0), state_path=state, now=NOW)
        later = current_regime(_inputs(24.0), state_path=state, now=NOW + timedelta(days=6))
        assert later.regime is Regime.TRENDING_BULL and not later.hysteresis_applied

    def test_missing_vix_is_unknown_and_defensive(self, tmp_path: Path) -> None:
        state = current_regime(_inputs(None), state_path=tmp_path / "s.json", now=NOW)
        assert state.regime is Regime.UNKNOWN
        assert state.macro_window == "DEFENSIVE" == regime_to_macro_window(Regime.UNKNOWN)
        assert state.degraded and "vix" in state.missing_inputs
        assert not (tmp_path / "s.json").exists()

    def test_stale_vix_is_not_used(self, tmp_path: Path) -> None:
        inputs = _inputs(15.0)
        inputs.vix.stale = True
        assert current_regime(inputs, state_path=tmp_path / "s.json", now=NOW).regime is Regime.UNKNOWN

    def test_crypto_fear_greed_never_moves_the_equity_regime(self, tmp_path: Path) -> None:
        calm = current_regime(_inputs(15.0, fear_greed=99.0), persist=False, now=NOW)
        assert calm.regime is Regime.TRENDING_BULL

    def test_dollar_is_a_note(self, tmp_path: Path) -> None:
        state = current_regime(_inputs(15.0, dxy_trend="rising"), persist=False, now=NOW)
        assert state.regime is Regime.TRENDING_BULL and "dollar_headwind" in state.notes


class TestRiskFree:
    def test_fallback_is_flagged_and_not_cached_as_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = {"t": 1_000.0}
        calls = {"n": 0}
        outcome: dict = {"quote": None}

        def fake_quote():
            calls["n"] += 1
            if outcome["quote"] is None:
                raise ValueError("offline")
            return outcome["quote"]

        monkeypatch.setattr(risk_free, "_fetch_quote", fake_quote)
        provider = risk_free.RiskFreeProvider(clock=lambda: clock["t"])
        first = provider.get_rate()
        assert not first.is_live and first.stale and first.as_of is None
        assert "configured" in first.fallback_reason
        provider.get_rate()
        assert calls["n"] == 1  # fallback kept for 30 s only
        clock["t"] += 31
        outcome["quote"] = Quote(symbol="^IRX", price=4.2, as_of="2026-11-20T14:59:00-05:00", source="yfinance:chart")
        live = provider.get_rate()
        assert live.is_live and live.value == pytest.approx(0.042) and live.as_of.startswith("2026-11-20")
        clock["t"] += 7 * 3600
        outcome["quote"] = None
        after = provider.get_rate()
        assert not after.is_live and after.stale
        assert after.value == pytest.approx(0.042) and "last live value" in after.fallback_reason


class TestPrices:
    def test_returns_use_adj_close_and_levels_keep_raw_close(self) -> None:
        index = pd.date_range("2026-01-01", periods=3, freq="D", tz="America/New_York")
        frame = pd.DataFrame({"Close": [100.0, 99.0, 100.0], "Adj Close": [98.0, 99.0, 100.0]}, index=index)
        assert prices.has_adjusted_close(frame)
        assert prices.returns(frame).iloc[0] == pytest.approx(99.0 / 98.0 - 1)
        assert prices.total_return(frame, 2) == pytest.approx(100.0 / 98.0 - 1)
        assert prices.total_return(frame, 5) is None

    def test_fallback_to_close_without_adj_close(self) -> None:
        frame = pd.DataFrame({"Close": [10.0, 11.0]})
        assert not prices.has_adjusted_close(frame)
        assert prices.returns(frame).iloc[0] == pytest.approx(0.1)


class TestCacheDirs:
    def test_xdg_root_and_private_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        monkeypatch.delenv("TRADING_X_DIR", raising=False)
        path = cache_paths.cache_dir("data", "TRADING_X_DIR")
        assert path == tmp_path / "trading_mcp" / "data"
        assert path.stat().st_mode & 0o777 == 0o700
        assert path.parent.stat().st_mode & 0o777 == 0o700

    def test_loose_permissions_are_tightened(self, tmp_path: Path) -> None:
        target = tmp_path / "loose"
        target.mkdir(mode=0o777)
        os.chmod(target, 0o777)
        assert cache_paths.secure_dir(target) == target
        assert target.stat().st_mode & 0o777 == 0o700

    def test_foreign_owner_disables_the_disk_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cache_paths, "_current_uid", lambda: os.getuid() + 1)
        assert cache_paths.secure_dir(tmp_path / "x") is None

    def test_relative_xdg_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "relative/dir")
        root = cache_paths.cache_root()
        assert root is not None and root.is_absolute()


class TestQuoteFreshness:
    def test_european_quote_inside_the_vendor_delay_is_delayed_not_stale(self) -> None:
        now = datetime(2026, 11, 20, 14, 42, tzinfo=UTC)
        quote = evaluate({"symbol": "ENI.MI", "price": 24.42, "as_of": "2026-11-20T15:26:41+01:00",
                          "source": "yfinance:chart"}, now=now, fetched_at=now, cached=False)
        assert quote.freshness == "delayed" and not quote.stale
        assert quote.delayed_by_min == 15.0

    def test_quote_without_time_is_unknown(self) -> None:
        quote = evaluate({"symbol": "AAPL", "price": 1.0, "as_of": None}, now=NOW, fetched_at=NOW, cached=False)
        assert quote.freshness == "unknown" and quote.stale and quote.warnings
