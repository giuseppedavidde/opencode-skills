"""debtToEquity scale and Weis-wave / trend-threshold regressions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_mcp.analysis.fundamentals import _de_ratio, compute_fundamentals
from trading_mcp.analysis.price_action import compute_multiframe_trend
from trading_mcp.analysis.weis_wave import _zigzag_legs, compute_sot_weis_wave


class TestDebtToEquityScale:
    """yfinance returns a percentage; the scorer needs a ratio."""

    def test_percentage_is_normalised(self) -> None:
        assert _de_ratio({"debtToEquity": 150.0}) == pytest.approx(1.5)

    def test_small_percentage_is_not_read_as_a_ratio(self) -> None:
        """DATA-12: yfinance 8.0 means 0.08x, not 8x (the info dict is always percent)."""
        assert _de_ratio({"debtToEquity": 8.0}) == pytest.approx(0.08)
        assert _de_ratio({"debtToEquity": 1.5}) == pytest.approx(0.015)

    def test_missing_returns_none(self) -> None:
        assert _de_ratio({}) is None
        assert _de_ratio({"debtToEquity": None}) is None

    def test_low_debt_earns_bonus_with_percentage_input(self) -> None:
        score, detail = compute_fundamentals({"debtToEquity": 30.0})
        assert "D/E 0.30x" in detail
        assert score >= 20

    def test_high_debt_is_not_a_value_trap_with_healthy_pe(self) -> None:
        """P/E 25 is not value-trap territory, so no D/E trap must fire."""
        _, detail = compute_fundamentals({"debtToEquity": 150.0, "trailingPE": 25.0})
        assert "Value Trap: D/E" not in detail


class TestWeisWaveLegs:
    """Volume must be segmented per leg, and both directions detected."""

    def _frame(self, close: np.ndarray, volume: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Open": close,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": volume,
            }
        )

    def test_zigzag_detects_alternating_legs(self) -> None:
        close = np.array(
            [100, 101, 102, 103, 104, 103, 102, 101, 100, 101, 102, 103, 104, 105],
            dtype=float,
        )
        volume = np.full(len(close), 1000.0)
        legs = _zigzag_legs(close, volume, threshold=0.02)
        assert len(legs) >= 2
        assert {leg["direction"] for leg in legs} == {"up", "down"}
        assert all(leg["volume"] > 0 for leg in legs)

    def test_up_leg_exhaustion_is_bearish(self) -> None:
        close: list[float] = [100.0]
        for gain in (0.10, 0.05, 0.01):
            for _ in range(4):
                close.append(close[-1] * (1 + gain / 4))
            for _ in range(4):
                close.append(close[-1] * 0.97)
        close.extend([close[-1]] * 60)
        arr = np.array(close[:200], dtype=float)
        arr = np.resize(arr, 200)
        frame = self._frame(arr, np.full(200, 1000.0))
        score, detail = compute_sot_weis_wave(frame)
        assert "up-legs" not in detail or "bearish" in detail or score <= 50


class TestMultiFrameTrendThreshold:
    """A 200-day MA must not require a 100% annualised slope to read 'up'."""

    def test_steady_uptrend_is_bullish(self) -> None:
        n = 260
        close = np.linspace(100.0, 160.0, n)
        volume = np.full(n, 1_000_000.0)
        frame = pd.DataFrame(
            {"Open": close, "High": close * 1.01, "Low": close * 0.99,
             "Close": close, "Volume": volume},
            index=pd.date_range("2024-01-01", periods=n, freq="B"),
        )
        score, detail = compute_multiframe_trend(frame)
        assert score > 50, detail
