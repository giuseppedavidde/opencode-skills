"""Regime-aware dimensional weights and macro regime detection."""

from __future__ import annotations

import pytest

from trading_mcp.analysis.macro import Regime, detect_regime, get_dynamic_weights
from trading_mcp.analysis.scanner import _regime_weights


class TestRegimeWeights:
    def test_static_weights_sum_to_one(self) -> None:
        assert sum(_regime_weights(None).values()) == pytest.approx(1.0, abs=1e-3)

    @pytest.mark.parametrize(
        "regime",
        ["NORMAL", "HIGH_VOLATILITY", "CRISIS", "TRENDING_BULL", "TRENDING_BEAR"],
    )
    def test_stock_weights_are_normalised(self, regime: str) -> None:
        assert sum(_regime_weights(regime).values()) == pytest.approx(1.0, abs=1e-3)

    def test_regime_shifts_the_mix(self) -> None:
        normal = _regime_weights("NORMAL")
        crisis = _regime_weights("CRISIS")
        assert crisis["sentiment"] > normal["sentiment"]
        assert crisis["wyckoff"] < normal["wyckoff"]

    def test_unknown_regime_falls_back_to_static(self) -> None:
        assert _regime_weights("NOT_A_REGIME") == _regime_weights(None)

    @pytest.mark.parametrize("regime", ["CRISIS", "TRENDING_BULL", "TRENDING_BEAR"])
    def test_crypto_weights_never_carry_unused_sentiment(self, regime: str) -> None:
        weights = _regime_weights(regime, is_crypto=True)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)
        assert "sentiment" not in weights


class TestRegimeDetection:
    def test_low_vix_with_rising_equity_is_bull(self) -> None:
        assert detect_regime(vix=14.0, dxy_trend="neutral", equity_trend="up") is Regime.TRENDING_BULL

    def test_low_vix_flat_equity_is_range(self) -> None:
        assert detect_regime(vix=14.0, dxy_trend="neutral", equity_trend="range") is Regime.RANGE_BOUND

    def test_high_vix_wins_over_equity_trend(self) -> None:
        assert detect_regime(vix=30.0, equity_trend="up") is Regime.HIGH_VOLATILITY

    def test_rising_dollar_blocks_bull(self) -> None:
        assert detect_regime(vix=14.0, dxy_trend="rising", equity_trend="up") is Regime.TRENDING_BEAR
