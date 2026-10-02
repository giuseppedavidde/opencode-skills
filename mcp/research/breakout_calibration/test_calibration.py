"""Unit tests for the breakout calibration study (synthetic data)."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.breakout_calibration import calibration, features
from research.breakout_calibration.run_calibration import (
    Accumulator,
    _accumulate_stops,
    build_thresholds,
    stop_analysis,
)
from research.breakout_calibration.schema import (
    BreakoutCell,
    HorizonStats,
    MomentumBucket,
    RegimeVariant,
    SampleInfo,
)


def _stats(horizon: int, excess: float, n: int = 500) -> HorizonStats:
    return HorizonStats(
        horizon_days=horizon,
        n_events=n,
        mean_fwd_return=excess + 0.01,
        median_fwd_return=excess,
        std_fwd_return=0.05,
        hit_rate=0.55,
        mean_excess_return=excess,
        t_stat=2.0,
        p_value=0.01,
        baseline_mean=0.01,
        baseline_hit_rate=0.54,
        sample_ok=n >= 30,
    )


def _cell(label: str, n_days: int, vol: float, excess: float) -> BreakoutCell:
    return BreakoutCell(
        n_days=n_days,
        volume_mult=vol,
        label=label,
        sample="in_sample",
        horizons=[_stats(h, excess) for h in (5, 10, 20, 60, 120)],
    )


def _synthetic_frame(n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    index = pd.bdate_range("2020-01-01", periods=n)
    close = pd.Series(100.0 + np.cumsum(rng.normal(0.0, 1.0, n)), index=index)
    high = close + 1.0
    low = close - 1.0
    volume = pd.Series(rng.integers(900, 1100, n), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume}
    )


def test_indicators_no_lookahead():
    frame = features.compute_indicators(_synthetic_frame())
    expected = frame["High"].rolling(20).max().shift(1)
    assert np.allclose(frame["high20"].iloc[25:], expected.iloc[25:], equal_nan=True)
    assert frame["vol_ma20"].notna().sum() == frame["Volume"].notna().sum() - 20
    assert frame["atr14"].notna().sum() > 0


def test_breakout_mask_respects_prior_high():
    frame = features.compute_indicators(_synthetic_frame())
    mask = features.breakout_mask(frame, 20, 0.0)
    triggers = frame.index[mask]
    assert len(triggers) > 0
    for ts in triggers:
        pos = frame.index.get_loc(ts)
        prior_high = frame["High"].iloc[max(0, pos - 20) : pos].max()
        assert frame["Close"].loc[ts] > prior_high


def test_volume_filter_is_applied():
    frame = features.compute_indicators(_synthetic_frame())
    loose = features.breakout_mask(frame, 20, 0.0).sum()
    strict = features.breakout_mask(frame, 20, 5.0).sum()
    assert strict <= loose


def test_forward_return_alignment():
    frame = _synthetic_frame(30)
    fwd = features.forward_return(frame["Close"], 5)
    assert np.isnan(fwd.iloc[-1])
    expected = frame["Close"].iloc[10] / frame["Close"].iloc[5] - 1.0
    assert fwd.iloc[5] == pytest.approx(expected)


def test_horizon_stats_basic():
    events = np.array([0.02, 0.03, -0.01, 0.04, 0.01])
    baseline = np.array([0.005, 0.0, -0.01, 0.02, 0.01])
    stat = calibration.horizon_stats(events, baseline, 5)
    assert stat.n_events == 5
    assert stat.hit_rate == pytest.approx(0.8)
    assert stat.mean_excess_return == pytest.approx(np.mean(events) - np.mean(baseline))
    assert stat.sample_ok is False


def test_horizon_stats_empty():
    stat = calibration.horizon_stats(np.array([]), np.array([0.01]), 5)
    assert stat.n_events == 0
    assert stat.p_value == 1.0
    assert stat.sample_ok is False


def test_profit_factor_capped():
    assert calibration.profit_factor(np.array([0.1, 0.2])) == calibration.MAX_PROFIT_FACTOR
    assert calibration.profit_factor(np.array([-0.1, -0.2])) == 0.0
    assert calibration.profit_factor(np.array([0.2, -0.1])) == pytest.approx(2.0)


def test_circular_block_indices_bounds():
    rng = np.random.default_rng(1)
    idx = calibration.circular_block_indices(100, 20, rng)
    assert idx.shape == (100,)
    assert idx.min() >= 0 and idx.max() < 100


def test_reality_check_detects_planted_edge():
    rng = np.random.default_rng(3)
    n_dates = 1500
    noise = rng.normal(0.0, 0.01, n_dates)
    series = {
        "noise_a": noise.copy(),
        "noise_b": rng.normal(0.0, 0.01, n_dates),
        "planted": rng.normal(0.02, 0.01, n_dates),
    }
    best, observed, p_value = calibration.reality_check_white(
        series, n_bootstrap=300, block_days=20, seed=11
    )
    assert best == "planted"
    assert p_value < 0.05
    assert observed["planted"] > 0.01


def test_reality_check_no_edge():
    rng = np.random.default_rng(4)
    n_dates = 1200
    series = {
        f"noise_{i}": rng.normal(0.0, 0.01, n_dates) for i in range(5)
    }
    _, _, p_value = calibration.reality_check_white(
        series, n_bootstrap=300, block_days=20, seed=5
    )
    assert p_value > 0.10


def test_stop_simulation_stopped_vs_held():
    frame = _synthetic_frame(60)
    frame["atr14"] = 1.0
    frame["atr_pct"] = 0.01
    acc = Accumulator()
    positions = np.array([0])
    _accumulate_stops(acc, frame, positions, 20, 2.0, max_horizon=10)
    outcomes = stop_analysis(acc)
    assert len(outcomes) == len((5, 10, 20, 60, 120)) * 5
    assert all(0.0 <= outcome.win_rate <= 1.0 for outcome in outcomes)
    assert all(outcome.n_events == 1 for outcome in outcomes)


def test_build_thresholds_prefers_positive_oos():
    sample = SampleInfo(
        universe_source="synthetic",
        universe_note="test",
        survivorship_bias="none",
        n_symbols_requested=1,
        n_symbols_loaded=1,
        period_start="2010-01-01",
        period_end="2026-09-30",
        in_sample_end="2020-12-31",
        n_trading_days=100,
        n_observations=100,
    )
    is_cells = [
        _cell("N20_vol2", 20, 2.0, -0.002),
        _cell("N252_vol2", 252, 2.0, -0.003),
    ]
    oos_cells = [
        _cell("N20_vol2", 20, 2.0, -0.001),
        _cell("N252_vol2", 252, 2.0, 0.005),
    ]
    regimes = [
        RegimeVariant(
            condition=f"N252_{name}",
            description=name,
            n_events=100,
            horizons=[_stats(h, excess) for h in (5, 10, 20, 60, 120)],
        )
        for name, excess in (("all", -0.002), ("ticker_uptrend", -0.001))
    ]
    momentum = [
        MomentumBucket(
            metric="mom12",
            quantile=5,
            n_quantiles=5,
            range_low=0.1,
            range_high=2.0,
            sample="full",
            horizons=[_stats(h, 0.001) for h in (5, 10, 20, 60, 120)],
        )
    ]
    thresholds = build_thresholds(sample, is_cells, oos_cells, regimes, [], momentum)
    assert thresholds.breakout_lookback_days == 252
    assert thresholds.expected_excess_return == pytest.approx(0.005)
    assert thresholds.require_close_above_sma200 is True
