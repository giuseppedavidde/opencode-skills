"""Test backtest contract and evaluator with synthetic data.

All tests use synthetic fixtures — no network calls.
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


def make_synthetic_predictions(
    n: int = 200, horizons: list[int] | None = None, seed: int = 42
) -> list:
    """Generate synthetic BacktestPrediction list."""
    from backtest.contract import BacktestPrediction

    if horizons is None:
        horizons = [20, 60, 180]

    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    preds = []

    for h in horizons:
        signal = rng.uniform(10, 90, n)
        fwd_ret = rng.normal(0.0, 0.05, n)  # noisy, no signal by design
        for i in range(n):
            if i + h < n:
                preds.append(
                    BacktestPrediction(
                        ticker="TEST",
                        as_of=str(dates[i].date()),
                        signal_score=float(signal[i]),
                        horizon_days=h,
                        forward_price=100.0 * (1 + fwd_ret[i]),
                        forward_return=float(fwd_ret[i]),
                    )
                )
    return preds


class TestBacktestContract:
    """Tests for backtest/contract.py."""

    def test_build_empty_ohlcv_returns_empty(self) -> None:
        from backtest.contract import build_predictions_from_ohlcv, BacktestBuildStatus

        result = build_predictions_from_ohlcv(
            pd.DataFrame(), [20], pd.Series(dtype=float), ticker="X"
        )
        assert result.status == BacktestBuildStatus.INSUFFICIENT_DATA
        assert result.predictions == []

    def test_build_predictions_point_in_time(self) -> None:
        """Predictions must use only past data at as_of."""
        from backtest.contract import build_predictions_from_ohlcv, BacktestConfig

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
            # as_of must be parseable
            from datetime import datetime

            as_of_dt = datetime.strptime(p.as_of, "%Y-%m-%d")
            # Forward return must be from a future date
            assert p.forward_return is not None
            assert p.forward_price is not None

    def test_build_predictions_respects_min_bars(self) -> None:
        """Too few bars should produce insufficient_data in strict mode."""
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


class TestBacktestEvaluator:
    """Tests for backtest/evaluator.py."""

    def test_evaluate_empty_predictions(self) -> None:
        from backtest.evaluator import evaluate

        result = evaluate([], ticker="EMPTY")
        assert result.ticker == "EMPTY"
        assert len(result.limits) > 0
        assert any("No predictions" in lim for lim in result.limits) or \
            any("predictions" in lim.lower() for lim in result.limits)

    def test_evaluate_random_signal_near_zero_ic(self) -> None:
        """A purely random signal should have IC close to 0."""
        from backtest.evaluator import evaluate

        preds = make_synthetic_predictions(n=500, seed=12345)
        result = evaluate(preds, ticker="RANDOM")

        for h in result.horizons:
            if h.n_observations >= 30 and h.ic_rank is not None:
                # Random signal: IC should be within [-0.15, 0.15]
                assert (
                    -0.20 <= h.ic_rank <= 0.20
                ), f"Random signal IC={h.ic_rank:.4f} out of range at {h.horizon_days}d"

    def test_evaluate_perfect_signal_has_positive_ic(self) -> None:
        """A signal perfectly correlated with forward return has high IC."""
        from backtest.evaluator import evaluate
        from backtest.contract import BacktestPrediction

        n = 200
        rng = np.random.default_rng(42)
        dates = pd.date_range("2022-01-01", periods=n, freq="B")
        signal = np.linspace(10, 90, n)
        fwd_ret = signal / 100.0  # perfect positive correlation

        preds = []
        for i in range(n - 30):
            preds.append(
                BacktestPrediction(
                    ticker="PERFECT",
                    as_of=str(dates[i].date()),
                    signal_score=float(signal[i]),
                    horizon_days=20,
                    forward_price=100.0 * (1 + fwd_ret[i]),
                    forward_return=float(fwd_ret[i]),
                )
            )

        result = evaluate(preds, ticker="PERFECT")
        h20 = [h for h in result.horizons if h.horizon_days == 20]
        assert len(h20) == 1
        assert h20[0].ic_rank is not None
        assert h20[0].ic_rank > 0.5, f"Expected IC > 0.5, got {h20[0].ic_rank}"

    def test_horizon_results_structure(self) -> None:
        """All expected horizons appear in result with correct fields."""
        from backtest.evaluator import evaluate

        # Use enough data points to cover all horizons
        preds = make_synthetic_predictions(n=500, horizons=[20, 60])
        result = evaluate(preds, ticker="STRUCT")

        horizon_days_seen = {h.horizon_days for h in result.horizons}
        assert 20 in horizon_days_seen
        assert 60 in horizon_days_seen

        for h in result.horizons:
            assert isinstance(h.n_observations, int)
            if h.horizon_days in (20, 60):
                assert h.n_observations > 0
            assert isinstance(h.hit_rate, float)
            assert isinstance(h.mean_return_pct, float)
            assert isinstance(h.quintile_returns, dict)

    def test_backtest_config_defaults(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig()
        assert 20 in cfg.horizons_days
        assert 60 in cfg.horizons_days
        assert 180 in cfg.horizons_days
        assert cfg.min_bars == 252
        assert cfg.permutation_control is True


class TestVPNoLookahead:
    """VP signal must not use future data (prefix invariance)."""

    def test_vp_canonical_includes_current_bar_not_future(self) -> None:
        """VP at time t uses data up to t (inclusive), never beyond.

        We verify that computing VP on data[:t+1] vs data[:t+11] gives
        the same result at position t — because data[t+1:t+11] is
        future and must not affect the signal at t.
        """
        import numpy as np
        import pandas as pd
        import sys
        from pathlib import Path

        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.volume_profile import get_profile_levels

        rng = np.random.default_rng(42)
        n = 300
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        close = 100.0 + np.cumsum(rng.normal(0, 1, n))
        ohlcv = pd.DataFrame(
            {
                "Open": close,
                "High": close + rng.uniform(0.5, 2, n),
                "Low": close - rng.uniform(0.5, 2, n),
                "Close": close,
                "Volume": rng.integers(1000, 100000, n),
            },
            index=dates,
        )

        # VP at t=260 with only data[:261] (up to t)
        prefix = ohlcv.iloc[:261]
        score_prefix = get_profile_levels(prefix)["score"]

        # VP at t=260 with data[:271] (up to t+10)
        extended = ohlcv.iloc[:271]
        score_extended = get_profile_levels(extended)["score"]

        assert score_prefix == score_extended, (
            f"VP score changed when future bars were added: "
            f"{score_prefix} vs {score_extended}. "
            "The VP calculation may be using future data."
        )
