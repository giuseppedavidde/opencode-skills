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


from trading_mcp.weights_config import get_weights


def _get_base_weights_stock() -> dict[str, float]:
    """Get base stock weights from config."""
    return get_weights().stocks.to_dict()


def _get_base_weights_crypto() -> dict[str, float]:
    """Get base crypto weights from config."""
    return get_weights().crypto.to_dict()


def detect_regime(
    vix: float | None = None,
    dxy_trend: str = "neutral",
    macro_window: str = "normal",
    fear_greed: int | None = None,
    equity_trend: str | None = None,
) -> Regime:
    """Detect market regime from macro indicators.

    Args:
        vix: Current VIX level.
        dxy_trend: 'rising', 'falling', or 'neutral'.
        macro_window: Adaptive Macro Matrix window.
        fear_greed: Crypto Fear & Greed index (0-100).
        equity_trend: 'up', 'down', 'range', or None. Breadth comes from the
            index trend, because a low VIX is compatible with both a calm
            bull market and a genuine range; without it the default answer
            was always RANGE_BOUND.
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

    # Equity breadth breaks the tie before the FX-only fallbacks.
    if equity_trend == "up" and dxy_trend != "rising":
        return Regime.TRENDING_BULL
    if equity_trend == "down" and dxy_trend != "falling":
        return Regime.TRENDING_BEAR

    if vix is not None and vix < 25 and dxy_trend == "neutral":
        return Regime.RANGE_BOUND
    if dxy_trend == "falling":
        return Regime.TRENDING_BULL
    if dxy_trend == "rising":
        return Regime.TRENDING_BEAR
    return Regime.UNKNOWN


# ── Adaptive Macro Matrix window mapping ─────────────────────────────
# Single source of truth: the macro window is DERIVED from the detected
# regime so the two fields can never contradict each other.
_REGIME_TO_MACRO_WINDOW: dict[Regime, str] = {
    Regime.CRISIS: "DEFENSIVE",
    Regime.HIGH_VOLATILITY: "SELECTIVE",
    Regime.RANGE_BOUND: "NORMAL",
    Regime.TRENDING_BULL: "FULL",
    Regime.TRENDING_BEAR: "DEFENSIVE",
    Regime.UNKNOWN: "NORMAL",
}


def regime_to_macro_window(regime: Regime) -> str:
    """Map a detected :class:`Regime` to its Adaptive Macro Matrix window.

    Mapping (documented, single source of truth):
    CRISIS→DEFENSIVE, HIGH_VOLATILITY→SELECTIVE, RANGE_BOUND→NORMAL,
    TRENDING_BULL→FULL, TRENDING_BEAR→DEFENSIVE, UNKNOWN→NORMAL.
    """
    return _REGIME_TO_MACRO_WINDOW.get(regime, "NORMAL")


def get_dynamic_weights(regime: Regime, is_crypto: bool = False) -> dict[str, float]:
    """Get regime-adjusted dimensional weights.

    Args:
        regime: Current market regime.
        is_crypto: If True, use crypto base weights.
    """
    base = _get_base_weights_crypto() if is_crypto else _get_base_weights_stock()
    weights = dict(base)

    if regime == Regime.CRISIS:
        for k in weights:
            weights[k] *= 0.80
        # Crypto has no sentiment dimension: injecting one would leave part of
        # the normalised weight mass unapplied in the composite score.
        if "sentiment" in weights:
            weights["sentiment"] = min(1.0, weights["sentiment"] * 1.4)
    elif regime == Regime.HIGH_VOLATILITY:
        weights["wyckoff"] = min(1.0, weights.get("wyckoff", 0.20) * 1.2)
        weights["price_action"] = min(1.0, weights.get("price_action", 0.15) * 0.8)
    elif regime == Regime.RANGE_BOUND:
        weights["volume_profile"] = min(1.0, weights.get("volume_profile", 0.20) * 1.3)
    elif regime == Regime.TRENDING_BULL:
        weights["wyckoff"] = min(1.0, weights.get("wyckoff", 0.20) * 1.15)
        if "sentiment" in weights:
            weights["sentiment"] = min(1.0, weights["sentiment"] * 1.1)
    elif regime == Regime.TRENDING_BEAR:
        if "sentiment" in weights:
            weights["sentiment"] = min(1.0, weights["sentiment"] * 1.3)
        weights["volume_profile"] = min(1.0, weights.get("volume_profile", 0.20) * 1.15)

    total = sum(weights.values())
    return {k: round(v / total, 4) for k, v in weights.items()}
