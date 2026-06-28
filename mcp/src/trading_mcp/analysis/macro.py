"""Macro regime detection and dynamic weight rebalancing."""

from __future__ import annotations

from enum import Enum


class Regime(str, Enum):
    """Market regime classification."""

    UNKNOWN = "unknown"
    CRISIS = "crisis"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"


BASE_WEIGHTS_STOCK = {
    "wyckoff": 0.20,
    "volume_profile": 0.20,
    "price_action": 0.15,
    "sentiment": 0.20,
    "fundamentals": 0.25,
}

BASE_WEIGHTS_CRYPTO = {
    "wyckoff": 0.25,
    "volume_profile": 0.25,
    "price_action": 0.20,
    "sentiment": 0.30,
}


def detect_regime(
    vix: float | None = None,
    dxy_trend: str = "neutral",
    macro_window: str = "normal",
    fear_greed: int | None = None,
) -> Regime:
    """Detect market regime from macro indicators.

    Args:
        vix: Current VIX level.
        dxy_trend: 'rising', 'falling', or 'neutral'.
        macro_window: Adaptive Macro Matrix window.
        fear_greed: Crypto Fear & Greed index (0-100).
    """
    if macro_window.upper() == "DEFENSIVE":
        return Regime.CRISIS
    if vix is not None and vix > 35:
        return Regime.CRISIS
    if vix is not None and vix > 25:
        return Regime.HIGH_VOLATILITY
    if macro_window.upper() == "SELECTIVE":
        return Regime.HIGH_VOLATILITY
    if fear_greed is not None and (fear_greed > 75 or fear_greed < 20):
        return Regime.HIGH_VOLATILITY
    if vix is not None and vix < 15 and dxy_trend == "neutral":
        return Regime.RANGE_BOUND
    if dxy_trend == "falling":
        return Regime.TRENDING_BULL
    if dxy_trend == "rising":
        return Regime.TRENDING_BEAR
    return Regime.UNKNOWN


def get_dynamic_weights(regime: Regime, is_crypto: bool = False) -> dict[str, float]:
    """Get regime-adjusted dimensional weights.

    Args:
        regime: Current market regime.
        is_crypto: If True, use crypto base weights.
    """
    base = BASE_WEIGHTS_CRYPTO if is_crypto else BASE_WEIGHTS_STOCK
    weights = dict(base)

    if regime == Regime.CRISIS:
        for k in weights:
            weights[k] *= 0.80
        weights["sentiment"] = min(1.0, weights.get("sentiment", 0.20) * 1.4)
    elif regime == Regime.HIGH_VOLATILITY:
        weights["wyckoff"] = min(1.0, weights.get("wyckoff", 0.20) * 1.2)
        weights["price_action"] = min(1.0, weights.get("price_action", 0.15) * 0.8)
    elif regime == Regime.RANGE_BOUND:
        weights["volume_profile"] = min(1.0, weights.get("volume_profile", 0.20) * 1.3)
    elif regime == Regime.TRENDING_BULL:
        weights["wyckoff"] = min(1.0, weights.get("wyckoff", 0.20) * 1.15)
        weights["sentiment"] = min(1.0, weights.get("sentiment", 0.20) * 1.1)
    elif regime == Regime.TRENDING_BEAR:
        weights["sentiment"] = min(1.0, weights.get("sentiment", 0.20) * 1.3)
        weights["volume_profile"] = min(1.0, weights.get("volume_profile", 0.20) * 1.15)

    total = sum(weights.values())
    return {k: round(v / total, 4) for k, v in weights.items()}
