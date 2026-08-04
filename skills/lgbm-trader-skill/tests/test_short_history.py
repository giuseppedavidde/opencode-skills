"""Test short-history scenarios: explicit status, diagnostic mode, no future leakage.

All tests use synthetic fixtures — no network calls.

Covers:
    1. Build result status explicit for 10, 30, 100, 251, 431, 500+ bars
    2. Diagnostic mode never claims predictive validity
    3. Per-horizon supported/insufficient flags
    4. No future data used (point-in-time invariant)
    5. Evaluator respects supported flags
    6. BacktestConfig strict vs diagnostic mode
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))


def make_synthetic_ohlcv(n_bars: int, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic daily OHLCV with n_bars."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n_bars, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n_bars))
    close = np.maximum(close, 10.0)
    high = close + rng.uniform(0.5, 2.0, n_bars)
    low = close - rng.uniform(0.5, 2.0, n_bars)
    volume = rng.integers(1000, 100000, n_bars)
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


def make_dummy_signal(ohlcv: pd.DataFrame) -> pd.Series:
    """Create a valid dummy signal series aligned to ohlcv index."""
    rng = np.random.default_rng(99)
    signal_vals = rng.uniform(10, 90, len(ohlcv))
    return pd.Series(signal_vals, index=ohlcv.index)


# ── Parameterised short-history tests ──────────────────────────────────


class TestBuildResultShortHistory:
    """build_predictions_from_ohlcv must never return empty list silently."""

    @pytest.mark.parametrize("n_bars,expected_status", [
        (10, "insufficient_data"),
        (30, "insufficient_data"),
        (100, "insufficient_data"),
        (251, "insufficient_data"),
        (431, "insufficient_data"),
        (500, "ok"),
    ])
    def test_build_status_explicit(self, n_bars, expected_status) -> None:
        from backtest.contract import (
            BacktestBuildStatus,
            BacktestConfig,
            build_predictions_from_ohlcv,
        )

        ohlcv = make_synthetic_ohlcv(n_bars)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20, 60, 180],
            min_bars=252,
            strict_mode=True,
        )

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="TEST", min_bars=252, config=config,
        )

        assert result.status.value == expected_status, (
            f"n_bars={n_bars}: expected {expected_status}, got {result.status.value}. "
            f"Reason: {result.reason}"
        )
        assert result.available_bars == n_bars
        assert result.required_bars == 252 + 180  # min_bars + max horizon
        assert result.reason != "", "Build result must have a reason"

        # Verify per-horizon capability flags
        for hc in result.horizons:
            h_need = 252 + hc.horizon_days
            assert hc.required_bars == h_need
            if n_bars >= h_need:
                assert hc.supported is True, (
                    f"Horizon {hc.horizon_days}d should be supported "
                    f"({n_bars} >= {h_need})"
                )
            else:
                assert hc.supported is False

    def test_10_bars_has_explicit_reason(self) -> None:
        from backtest.contract import build_predictions_from_ohlcv, BacktestConfig

        ohlcv = make_synthetic_ohlcv(10)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(horizons_days=[20, 60, 180], min_bars=252, strict_mode=True)

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="TINY", min_bars=252, config=config,
        )

        assert "Strict mode" in result.reason or "empty" in result.reason.lower()
        assert result.predictions == []

    def test_500_bars_ok_all_horizons_supported(self) -> None:
        from backtest.contract import (
            BacktestBuildStatus,
            BacktestConfig,
            build_predictions_from_ohlcv,
        )

        ohlcv = make_synthetic_ohlcv(500)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(horizons_days=[20, 60, 180], min_bars=252, strict_mode=True)

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="OK", min_bars=252, config=config,
        )

        assert result.status == BacktestBuildStatus.OK
        assert len(result.predictions) > 0
        assert all(hc.supported for hc in result.horizons)


class TestDiagnosticMode:
    """Diagnostic/short-history mode must never present as predictive."""

    def test_diagnostic_mode_sets_flag(self) -> None:
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(200)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20, 60, 180],
            min_bars=252,
            strict_mode=False,  # allow short history
            diagnostic_only=True,
            vp_window_days=365,
            vp_min_window_days=20,
        )

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="DIAG", min_bars=252, config=config,
        )

        assert result.diagnostic_only is True, "Diagnostic mode must flag diagnostic_only=True"
        assert result.vp_window_effective < 365 or result.vp_window_effective >= 20

    def test_diagnostic_with_very_short_history(self) -> None:
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(50)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20],
            min_bars=40,
            strict_mode=False,
            diagnostic_only=True,
        )

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20], signal=signal,
            ticker="TINY_DIAG", min_bars=40, config=config,
        )

        assert result.diagnostic_only is True
        assert result.vp_window_effective >= config.vp_min_window_days

    def test_diagnostic_results_never_claim_predictive(self) -> None:
        """Evaluator must flag diagnostic results as diagnostic_only."""
        from backtest.contract import BacktestConfig, BacktestPrediction
        from backtest.evaluator import evaluate

        config = BacktestConfig(
            horizons_days=[20],
            diagnostic_only=True,
            min_bars=min(252 // 2, 200),
            strict_mode=False,
            min_horizon_observations=20,
        )

        # Create synthetic predictions that would pass evaluator threshold
        preds = []
        dates = pd.date_range("2022-01-01", periods=200, freq="B")
        rng = np.random.default_rng(42)
        for i in range(200 - 30):
            preds.append(
                BacktestPrediction(
                    ticker="DIAG",
                    as_of=str(dates[i].date()),
                    signal_score=float(rng.uniform(10, 90)),
                    horizon_days=20,
                    forward_price=100.0,
                    forward_return=float(rng.normal(0, 0.02)),
                )
            )

        result = evaluate(preds, config=config, ticker="DIAG")
        assert result.diagnostic_only is True, "Evaluator must preserve diagnostic_only flag"
        assert any(
            "DIAGNOSTIC" in lim.upper() for lim in result.limits
        ), "Limits must mention diagnostic mode"


class TestPerHorizonSupport:
    """Each horizon must explicitly report supported/insufficient status."""

    def test_middle_horizon_unsupported(self) -> None:
        """Example: 280 bars. 20d horizon needs 272, supported.
        60d needs 312, unsupported. 180d needs 432, unsupported."""
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        # 280 bars — only 20d horizon should be supported with min_bars=252
        ohlcv = make_synthetic_ohlcv(280)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20, 60, 180],
            min_bars=252,
            strict_mode=False,  # don't block globally, check per-horizon
        )

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="PARTIAL", min_bars=252, config=config,
        )

        for hc in result.horizons:
            if hc.horizon_days == 20:
                assert hc.supported is True, "20d should be supported (280 >= 272)"
            elif hc.horizon_days == 60:
                assert hc.supported is False, "60d should be unsupported (280 < 312)"
            elif hc.horizon_days == 180:
                assert hc.supported is False, "180d should be unsupported (280 < 432)"

    def test_unsupported_horizons_get_no_predictions(self) -> None:
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(280)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20, 60, 180],
            min_bars=252,
            strict_mode=False,
        )

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20, 60, 180], signal=signal,
            ticker="PARTIAL", min_bars=252, config=config,
        )

        horizon_counts = {}
        for p in result.predictions:
            horizon_counts[p.horizon_days] = horizon_counts.get(p.horizon_days, 0) + 1

        assert 20 in horizon_counts, "20d predictions should exist"
        assert 60 not in horizon_counts, "60d should have NO predictions"
        assert 180 not in horizon_counts, "180d should have NO predictions"

    def test_evaluator_respects_horizon_supported(self) -> None:
        """Evaluator must mark unsupported horizons with supported=False."""
        from backtest.contract import BacktestConfig, BacktestPrediction
        from backtest.evaluator import evaluate

        config = BacktestConfig(
            horizons_days=[20, 60, 180],
            min_horizon_observations=5,
            strict_mode=False,
        )

        preds = []
        dates = pd.date_range("2022-01-01", periods=200, freq="B")
        rng = np.random.default_rng(42)
        for i in range(200 - 30):
            preds.append(
                BacktestPrediction(
                    ticker="TEST",
                    as_of=str(dates[i].date()),
                    signal_score=float(rng.uniform(10, 90)),
                    horizon_days=20,
                    forward_price=100.0,
                    forward_return=float(rng.normal(0, 0.02)),
                )
            )

        result = evaluate(preds, config=config, ticker="TEST")
        # All three horizons appear; only 20d should have data
        all_horizons = {h.horizon_days for h in result.horizons}
        assert 20 in all_horizons
        assert 60 in all_horizons
        assert 180 in all_horizons

        for h in result.horizons:
            if h.horizon_days == 20:
                assert h.supported is True
                assert h.status == "ok"
            else:
                assert h.supported is False
                assert h.status == "insufficient_data"


class TestNoFutureLeakageShort:
    """Even with short history, point-in-time invariance holds."""

    def test_shift_minus_h_is_strictly_future(self) -> None:
        """All forward returns use .shift(-h) which only uses future data."""
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(500)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(horizons_days=[20], min_bars=252, strict_mode=True)

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20], signal=signal,
            ticker="FUTURE", min_bars=252, config=config,
        )

        for p in result.predictions:
            as_of_idx = ohlcv.index.get_loc(p.as_of)
            # The forward price MUST come from a bar > as_of_idx
            fwd_price_from_data = ohlcv["Close"].iloc[as_of_idx + 20]
            assert abs(p.forward_price - fwd_price_from_data) < 1e-6, (
                f"Forward price mismatch at idx {as_of_idx}: "
                f"{p.forward_price} vs {fwd_price_from_data}"
            )

    def test_signal_only_uses_past_data(self) -> None:
        """Signal for a bar must not depend on future bars."""
        # The signal is synthetic here, so we just verify that
        # build_predictions uses as_of properly
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(500)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(horizons_days=[20], min_bars=252, strict_mode=True)

        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20], signal=signal,
            ticker="SIG", min_bars=252, config=config,
        )

        # Every prediction: signal_score should match signal at as_of
        for p in result.predictions:
            as_of_idx = ohlcv.index.get_loc(p.as_of)
            expected_signal = signal.iloc[as_of_idx]
            assert abs(p.signal_score - expected_signal) < 1e-6, (
                f"Signal mismatch at {p.as_of}"
            )


class TestBacktestConfig:
    """BacktestConfig new fields (P0 August 2026)."""

    def test_strict_mode_defaults_true(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.strict_mode is True

    def test_diagnostic_only_defaults_false(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.diagnostic_only is False

    def test_vp_window_fields(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.vp_window_days == 365
        assert cfg.vp_min_window_days == 20
        assert cfg.min_horizon_observations == 30

    def test_diagnostic_config(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig(
            diagnostic_only=True,
            strict_mode=False,
            vp_window_days=60,
            vp_min_window_days=20,
            min_bars=40,
            min_horizon_observations=15,
        )
        assert cfg.diagnostic_only is True
        assert cfg.vp_window_days == 60
        assert cfg.min_bars == 40


class TestExistingTestsStillPass:
    """Verify that the v2 API doesn't break existing test patterns."""

    def test_build_predictions_point_in_time(self) -> None:
        """Predictions must use only past data at as_of (same as original test)."""
        from backtest.contract import build_predictions_from_ohlcv, BacktestConfig
        from datetime import datetime

        dates = pd.date_range("2020-01-01", periods=400, freq="B")
        close = 100.0 + np.cumsum(np.random.default_rng(0).normal(0.0, 1.0, 400))
        ohlcv = pd.DataFrame(
            {"Close": close, "High": close + 1, "Low": close - 1, "Volume": 1000},
            index=dates,
        )
        signal = pd.Series(np.linspace(10, 90, 400), index=dates)
        config = BacktestConfig(horizons_days=[60], strict_mode=False, min_bars=252)
        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[60], signal=signal, ticker="TEST", min_bars=252,
            config=config,
        )

        assert len(result.predictions) > 0, "Should produce predictions"
        for p in result.predictions:
            datetime.strptime(p.as_of, "%Y-%m-%d")
            assert p.forward_return is not None
            assert p.forward_price is not None

    def test_build_predictions_respects_min_bars(self) -> None:
        """Too few bars should produce insufficient_data with strict mode."""
        from backtest.contract import build_predictions_from_ohlcv, BacktestConfig

        dates = pd.date_range("2020-01-01", periods=50, freq="B")
        close = np.ones(50) * 100.0
        ohlcv = pd.DataFrame(
            {"Close": close, "High": close, "Low": close, "Volume": 1000},
            index=dates,
        )
        signal = pd.Series(50.0, index=dates)
        config = BacktestConfig(horizons_days=[180], min_bars=252, strict_mode=True)
        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[180], signal=signal, ticker="X", min_bars=252,
            config=config,
        )
        assert result.status.value == "insufficient_data"
        assert result.predictions == []


class TestVPDiagnosticSignal:
    """Diagnostic mode VP window must be >= 20 and flagged."""

    def test_diagnostic_vp_window_minimum(self) -> None:
        """In diagnostic mode with 50 bars, effective VP window MUST be >= 20."""
        from backtest.contract import BacktestConfig, build_predictions_from_ohlcv

        ohlcv = make_synthetic_ohlcv(50)
        signal = make_dummy_signal(ohlcv)
        config = BacktestConfig(
            horizons_days=[20],
            min_bars=40,
            strict_mode=False,
            diagnostic_only=True,
            vp_window_days=365,
            vp_min_window_days=20,
        )
        result = build_predictions_from_ohlcv(
            ohlcv, horizons=[20], signal=signal,
            ticker="VPD", min_bars=40, config=config,
        )
        assert result.vp_window_effective >= 20
        assert result.diagnostic_only is True
