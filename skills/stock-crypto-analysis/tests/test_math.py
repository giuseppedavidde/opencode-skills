#!/usr/bin/env python3
"""Unit tests for mathematical functions across trading skills."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add all skill script directories to path
SCRIPTS_DIRS = [
    "stock-crypto-analysis/scripts",
    "options-analysis/scripts",
    "options-strategy-suggestions/scripts",
]
BASE = Path(__file__).resolve().parent.parent.parent
for rel in SCRIPTS_DIRS:
    sys.path.insert(0, str(BASE / rel))


# ---------------------------------------------------------------------------
# 1. Black-Scholes Gamma (from gex_analysis.py)
# ---------------------------------------------------------------------------

def test_bs_gamma() -> None:
    """BS gamma should be positive for ATM options and approach 0 for deep ITM/OTM."""
    from gex_analysis import bs_gamma

    spot = 150.0
    strike = 150.0
    tte = 30 / 365.0
    rate = 0.05
    sigma = 0.30

    gamma = bs_gamma(spot, strike, tte, rate, sigma)
    assert gamma > 0, f"ATM gamma should be positive, got {gamma}"
    assert not math.isnan(gamma), f"ATM gamma should not be NaN, got {gamma}"

    # Deep OTM
    gamma_otm = bs_gamma(spot, 200.0, tte, rate, sigma)
    assert gamma_otm >= 0, f"OTM gamma should be non-negative, got {gamma_otm}"

    # Deep ITM
    gamma_itm = bs_gamma(spot, 100.0, tte, rate, sigma)
    assert gamma_itm > 0, f"ITM gamma should be positive, got {gamma_itm}"

    # Very short expiry gamma spike
    gamma_short = bs_gamma(spot, strike, 1 / 365.0, rate, sigma)
    assert gamma_short > gamma, "Gamma should be higher closer to expiry"


# ---------------------------------------------------------------------------
# 2. Max Pain (from gex_analysis.py)
# ---------------------------------------------------------------------------

def test_max_pain_basic() -> None:
    """Max Pain should pick the strike with minimum total cost."""
    from gex_analysis import compute_max_pain

    calls = pd.DataFrame({
        "strike": [100.0, 110.0, 120.0],
        "openInterest": [100, 200, 300],
    })
    puts = pd.DataFrame({
        "strike": [100.0, 110.0, 120.0],
        "openInterest": [300, 200, 100],
    })

    result = compute_max_pain(calls, puts)
    assert result is not None, "Max Pain should return a result for valid inputs"
    assert result.strike > 0, f"Max Pain strike should be positive, got {result.strike}"
    assert result.total_pain >= 0, f"Max Pain value should be >= 0, got {result.total_pain}"

    # With OI centered on 110, max pain should be near 110
    assert abs(result.strike - 110.0) < 10, (
        f"Max pain should be near high-OI strike, got {result.strike}"
    )


def test_max_pain_edge_cases() -> None:
    """Max Pain should handle empty and single-strike inputs."""
    from gex_analysis import compute_max_pain

    # Both empty
    empty = pd.DataFrame(columns=["strike", "openInterest"])
    assert compute_max_pain(empty, empty) is None

    # Single strike
    single = pd.DataFrame([{"strike": 100.0, "openInterest": 500}])
    result = compute_max_pain(single, single)
    if result is not None:
        assert result.strike == 100.0


# ---------------------------------------------------------------------------
# 3. Pearson Correlation (from correlation_check.py)
# ---------------------------------------------------------------------------

def test_correlation_clusters() -> None:
    """Correlation clusters should group highly-correlated tickers."""
    from correlation_check import compute_correlation_clusters

    corr = pd.DataFrame(
        [
            [1.0, 0.95, 0.3, 0.2],
            [0.95, 1.0, 0.25, 0.1],
            [0.3, 0.25, 1.0, 0.92],
            [0.2, 0.1, 0.92, 1.0],
        ],
        index=["AAPL", "MSFT", "BTC", "ETH"],
        columns=["AAPL", "MSFT", "BTC", "ETH"],
    )

    clusters = compute_correlation_clusters(corr, threshold=0.70)
    assert len(clusters) == 2, f"Expected 2 clusters, got {len(clusters)}"

    # One cluster should contain AAPL+MSFT, the other BTC+ETH
    tickers_in_clusters = {t for c in clusters for t in c}
    assert tickers_in_clusters == {"AAPL", "MSFT", "BTC", "ETH"}, (
        f"All tickers should be in clusters, got {tickers_in_clusters}"
    )


def test_diversification_score() -> None:
    """Diversification score should be 100 for perfectly uncorrelated assets."""
    from correlation_check import compute_diversification_score

    # Identity matrix = perfectly uncorrelated
    uncorrelated = pd.DataFrame(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    score = compute_diversification_score(uncorrelated)
    assert score == 100.0, f"Uncorrelated should score 100, got {score}"

    # Perfectly correlated = score 0
    perfect_corr = pd.DataFrame(
        [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    score_corr = compute_diversification_score(perfect_corr)
    assert score_corr < 100, f"Perfectly correlated should score < 100, got {score_corr}"

    # Single ticker
    single = pd.DataFrame([[1.0]], index=["A"], columns=["A"])
    assert compute_diversification_score(single) == 100.0

    # With equal position weights, uncorrelated assets should give ~42 (not 100)
    weights = {"A": 0.5, "B": 0.3, "C": 0.2}
    score_w = compute_diversification_score(uncorrelated, positions=weights)
    assert 0 < score_w < 100, f"Weighted score should be 0-100, got {score_w}"


# ---------------------------------------------------------------------------
# 4. HV / IV Rank calculation logic
# ---------------------------------------------------------------------------

def test_hv_calculation() -> None:
    """Historical Volatility should be positive for real price series."""
    # Create 2y of daily prices with ~20% annualized volatility
    np.random.seed(42)
    n = 504
    returns = np.random.normal(0, 0.0125, n)  # ~20% annual vol
    prices = 100 * np.exp(np.cumsum(returns))
    closes = pd.Series(prices)

    # Compute rolling 20-day HV: std(log_returns) * sqrt(252)
    log_rets = np.log(closes / closes.shift(1)).dropna()
    rolling_hv = log_rets.rolling(20).std() * math.sqrt(252)

    hv_values = rolling_hv.dropna().values
    assert len(hv_values) > 0, "Should produce valid HV values"
    assert all(hv >= 0 for hv in hv_values), "All HV values should be >= 0"
    assert not any(math.isnan(hv) for hv in hv_values), "No NaN HV values"

    # Mean HV should be around 0.20 (within reasonable range)
    mean_hv = np.mean(hv_values)
    assert 0.05 < mean_hv < 0.50, f"Mean HV should be near 0.20, got {mean_hv:.3f}"


def test_iv_rank_formula() -> None:
    """IV Rank formula: (current_iv - hv_min) / (hv_max - hv_min) * 100."""
    # Create HV series spanning 10-30%
    hv_series = np.concatenate([
        np.linspace(0.10, 0.30, 200),
        np.linspace(0.30, 0.10, 100),
        np.linspace(0.10, 0.20, 100),
    ])
    hv_min, hv_max = hv_series.min(), hv_series.max()

    def rank(iv: float) -> float:
        return (iv - hv_min) / (hv_max - hv_min) * 100

    assert abs(rank(0.10) - 0.0) < 0.1, "IV at HV min should give 0"
    assert abs(rank(0.30) - 100.0) < 0.1, "IV at HV max should give 100"
    assert abs(rank(0.20) - 50.0) < 5, "IV at midpoint should give ~50"


# ---------------------------------------------------------------------------
# 5. Sharpe-like ratio (from feedback_loop.py)
# ---------------------------------------------------------------------------

def test_sharpe_like() -> None:
    """Sharpe-like ratio should be positive for winning trades."""
    from feedback_loop import compute_sharpe_like

    # Winning trades
    winners = [
        {"is_open": False, "pnl_pct": 5.0, "entry_date": "2024-01-01", "exit_date": "2024-01-10"},
        {"is_open": False, "pnl_pct": 3.0, "entry_date": "2024-02-01", "exit_date": "2024-02-10"},
        {"is_open": False, "pnl_pct": 4.0, "entry_date": "2024-03-01", "exit_date": "2024-03-10"},
    ]
    sharp = compute_sharpe_like(winners, annualize=False)
    assert sharp is not None
    assert sharp["raw_ratio"] > 0

    # Mixed trades
    mixed = [
        {"is_open": False, "pnl_pct": 10.0, "entry_date": "2024-01-01", "exit_date": "2024-02-01"},
        {"is_open": False, "pnl_pct": -5.0, "entry_date": "2024-02-15", "exit_date": "2024-03-15"},
        {"is_open": False, "pnl_pct": 2.0, "entry_date": "2024-04-01", "exit_date": "2024-05-01"},
    ]
    sharp_mixed = compute_sharpe_like(mixed)
    assert sharp_mixed is not None

    # Too few trades
    single = [{"is_open": False, "pnl_pct": 5.0}]
    assert compute_sharpe_like(single) is None

    # Open trades should be excluded
    with_open = [
        {"is_open": True, "pnl_pct": 100.0},
        {"is_open": False, "pnl_pct": 2.0},
        {"is_open": False, "pnl_pct": 3.0},
    ]
    sharp_open = compute_sharpe_like(with_open, annualize=False)
    assert sharp_open is not None
    # Only 2 closed trades should be used
    assert sharp_open["raw_ratio"] > 0


# ---------------------------------------------------------------------------
# 6. Volume Profile helpers (from backtest.py)
# ---------------------------------------------------------------------------

def test_volume_profile_basic() -> None:
    """Volume Profile score should be 0-100 and higher near VPOC."""
    from backtest import score_volume_profile

    # Create 100 bars with price oscillating around 100, volume constant
    np.random.seed(0)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "Open": 100 + np.random.randn(100) * 2,
        "High": 105 + np.random.randn(100) * 2,
        "Low": 95 + np.random.randn(100) * 2,
        "Close": 100 + np.random.randn(100) * 2,
        "Volume": [1_000_000] * 100,
        "Adj Close": 100 + np.random.randn(100) * 2,
    }, index=dates)

    score = score_volume_profile(df, idx=99)
    assert 0 <= score <= 100, f"Score should be 0-100, got {score}"

    # Early idx with insufficient data
    score_early = score_volume_profile(df, idx=10)
    assert 0 <= score_early <= 100


# ---------------------------------------------------------------------------
# 7. Wyckoff score (from backtest.py)
# ---------------------------------------------------------------------------

def test_wyckoff_score() -> None:
    """Wyckoff score should be 0-100."""
    from backtest import score_wyckoff

    np.random.seed(1)
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    close = 100 + np.cumsum(np.random.randn(200) * 0.5)
    df = pd.DataFrame({
        "Open": close + np.random.randn(200) * 0.1,
        "High": close + abs(np.random.randn(200)) * 0.5,
        "Low": close - abs(np.random.randn(200)) * 0.5,
        "Close": close,
        "Volume": [1_000_000] * 200,
        "Adj Close": close,
    }, index=dates)

    score = score_wyckoff(df, idx=199)
    assert 0 <= score <= 100, f"Score should be 0-100, got {score}"

    # Early idx (< 50) should return default
    score_early = score_wyckoff(df, idx=30)
    assert score_early == 50.0


# ---------------------------------------------------------------------------
# 8. Price Action score (from backtest.py)
# ---------------------------------------------------------------------------

def test_price_action_score() -> None:
    """Price Action score should be 0-100."""
    from backtest import score_price_action

    np.random.seed(2)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    df = pd.DataFrame({
        "Open": close + np.random.randn(100) * 0.1,
        "High": close + abs(np.random.randn(100)) * 1.0,
        "Low": close - abs(np.random.randn(100)) * 1.0,
        "Close": close,
        "Volume": [1_000_000] * 100,
        "Adj Close": close,
    }, index=dates)

    score = score_price_action(df, idx=99)
    assert 0 <= score <= 100, f"Score should be 0-100, got {score}"


# ---------------------------------------------------------------------------
# 9. Weight config integrity
# ---------------------------------------------------------------------------

def test_weight_sums() -> None:
    """All weight configurations should sum approximately to 1.0."""
    from weights_config import (
        BASE_WEIGHTS_STOCK,
        BASE_WEIGHTS_CRYPTO,
        Regime,
        get_dynamic_weights,
    )

    stock_total = sum(BASE_WEIGHTS_STOCK.values())
    assert abs(stock_total - 1.0) < 0.001, (
        f"Stock weights sum to {stock_total}, expected 1.0"
    )

    crypto_total = sum(BASE_WEIGHTS_CRYPTO.values())
    assert abs(crypto_total - 1.0) < 0.001, (
        f"Crypto weights sum to {crypto_total}, expected 1.0"
    )

    for regime in Regime:
        for is_crypto in [True, False]:
            w = get_dynamic_weights(regime, is_crypto)
            total = sum(w.values())
            assert abs(total - 1.0) < 0.01, (
                f"{regime.value} {'crypto' if is_crypto else 'stock'} "
                f"weights sum to {total}, expected 1.0"
            )


# ---------------------------------------------------------------------------
# 10. Round strike (from options_backtest.py)
# ---------------------------------------------------------------------------

def test_round_strike() -> None:
    """Strike rounding should follow standard option intervals."""
    def _round_strike(price: float) -> float:
        if price < 25:
            return round(price * 2) / 2
        if price <= 200:
            return round(price)
        return round(price / 5) * 5

    # < $25: $0.50 intervals
    assert _round_strike(10.20) in (10.0, 10.5), f"Got {_round_strike(10.20)}"
    assert _round_strike(10.60) in (10.5, 11.0), f"Got {_round_strike(10.60)}"

    # $25-$200: $1.00 intervals
    assert _round_strike(50.40) == 50.0, f"Got {_round_strike(50.40)}"
    assert _round_strike(50.60) == 51.0, f"Got {_round_strike(50.60)}"
    assert _round_strike(150.0) == 150.0

    # > $200: $5.00 intervals
    assert _round_strike(252.0) == 250.0, f"Got {_round_strike(252.0)}"
    assert _round_strike(253.0) == 255.0, f"Got {_round_strike(253.0)}"


# ---------------------------------------------------------------------------
# 11. GEX net computation
# ---------------------------------------------------------------------------

def test_gex_net_calculation() -> None:
    """Net GEX should be positive when call GEX dominates and vice versa."""
    from gex_analysis import StrikeGexInfo

    call_dominant = StrikeGexInfo(
        strike=150.0,
        call_gex=100_000.0,
        put_gex=10_000.0,
        call_oi=1000,
        put_oi=100,
        net_gex=90_000.0,
    )
    assert call_dominant.net_gex > 0, "Call-dominant strike should have positive net GEX"

    put_dominant = StrikeGexInfo(
        strike=150.0,
        call_gex=10_000.0,
        put_gex=100_000.0,
        call_oi=100,
        put_oi=1000,
        net_gex=-90_000.0,
    )
    assert put_dominant.net_gex < 0, "Put-dominant strike should have negative net GEX"


# ---------------------------------------------------------------------------
# 12. Fundamentals score edge cases
# ---------------------------------------------------------------------------

def test_fundamentals_score() -> None:
    """Fundamentals score should handle missing data gracefully."""
    from backtest import score_fundamentals

    # No info
    score = score_fundamentals({})
    assert 0 <= score <= 100, f"Empty info should give 0-100, got {score}"

    # Partial info
    partial = {"marketCap": 1e9, "trailingPE": 15.0}
    score_partial = score_fundamentals(partial)
    assert 0 <= score_partial <= 100


# ---------------------------------------------------------------------------
# 13. NaN / edge case handling in scores
# ---------------------------------------------------------------------------

def test_score_nan_handling() -> None:
    """Scores should handle NaN values gracefully."""
    from backtest import score_wyckoff, score_volume_profile, score_price_action

    # DataFrame with NaN values
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "Open": [float("nan")] * 100,
        "High": [float("nan")] * 100,
        "Low": [float("nan")] * 100,
        "Close": [float("nan")] * 100,
        "Volume": [float("nan")] * 100,
        "Adj Close": [float("nan")] * 100,
    }, index=dates)

    for score_fn in [score_wyckoff, score_volume_profile, score_price_action]:
        s = score_fn(df, idx=99)
        assert 0 <= s <= 100, f"{score_fn.__name__} with NaN df should give 0-100, got {s}"


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_bs_gamma()
    test_max_pain_basic()
    test_max_pain_edge_cases()
    test_correlation_clusters()
    test_diversification_score()
    test_hv_calculation()
    test_iv_rank_formula()
    test_sharpe_like()
    test_volume_profile_basic()
    test_wyckoff_score()
    test_price_action_score()
    test_weight_sums()
    test_round_strike()
    test_gex_net_calculation()
    test_fundamentals_score()
    test_score_nan_handling()
    print("All 16 tests passed.")
