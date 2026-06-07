"""
Shared dimension weight tables for the stock-crypto-analysis scoring engine.

Single source of truth for all weight-related configuration.
Used by backtest.py, dynamic_weights.py, and any other scoring scripts.
"""

from __future__ import annotations

from enum import Enum


class Regime(str, Enum):
    """Market regime classification."""

    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    HIGH_VOLATILITY = "high_volatility"  # VIX > 25
    RANGE_BOUND = "range_bound"          # Sideways, low vol
    CRISIS = "crisis"                    # VIX > 35, macro stress
    UNKNOWN = "unknown"


# Base weights (stock)
BASE_WEIGHTS_STOCK: dict[str, float] = {
    "wyckoff": 0.15,
    "volume_profile": 0.20,
    "price_action": 0.20,
    "sentiment": 0.15,
    "fundamentals": 0.20,
    "competitive": 0.10,
}

# Base weights (crypto) — uses crypto_layer instead of shifting fundamentals
BASE_WEIGHTS_CRYPTO: dict[str, float] = {
    "wyckoff": 0.10,
    "volume_profile": 0.15,
    "price_action": 0.15,
    "sentiment": 0.10,
    "fundamentals": 0.10,
    "competitive": 0.05,
    "crypto_layer": 0.35,
}

# Regime adjustments (delta applied to base, then normalized)
REGIME_ADJUSTMENTS: dict[Regime, dict[str, float]] = {
    Regime.TRENDING_BULL: {
        "wyckoff": 0.05,
        "price_action": 0.05,
        "sentiment": -0.05,
        "fundamentals": -0.05,
    },
    Regime.TRENDING_BEAR: {
        "wyckoff": 0.05,
        "sentiment": 0.05,
        "price_action": 0.00,
        "volume_profile": -0.05,
        "fundamentals": -0.05,
    },
    Regime.HIGH_VOLATILITY: {
        "sentiment": 0.10,
        "volume_profile": -0.05,
        "price_action": -0.05,
    },
    Regime.RANGE_BOUND: {
        "volume_profile": 0.10,
        "price_action": -0.05,
        "sentiment": -0.05,
    },
    Regime.CRISIS: {
        "wyckoff": 0.05,
        "sentiment": 0.10,
        "fundamentals": -0.10,
        "competitive": -0.05,
    },
    Regime.UNKNOWN: {},
}


def get_dynamic_weights(regime: Regime, is_crypto: bool = False) -> dict[str, float]:
    """Compute regime-adjusted dimensional weights.

    Returns dict dimension_name → weight (sum = 1.0).
    """
    base = BASE_WEIGHTS_CRYPTO if is_crypto else BASE_WEIGHTS_STOCK
    adjustments = REGIME_ADJUSTMENTS.get(regime, {})

    adjusted = dict(base)
    for dim, delta in adjustments.items():
        if dim in adjusted:
            adjusted[dim] = max(0.01, adjusted[dim] + delta)

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    return adjusted
