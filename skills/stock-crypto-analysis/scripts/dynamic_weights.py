#!/usr/bin/env python3
"""
Dynamic Weight Rebalancing for the stock-crypto-analysis scoring engine.

Adjusts dimensional weights based on detected market regime,
replacing the static weight table with regime-aware allocation.

Usage:
    python3 dynamic_weights.py --vix 18.5 --dxy-trend falling --regime-detect
    python3 dynamic_weights.py --regime trending_bull --crypto
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

from weights_config import (
    BASE_WEIGHTS_CRYPTO,
    BASE_WEIGHTS_STOCK,
    Regime,
    get_dynamic_weights,
)


def detect_regime(
    vix: Optional[float] = None,
    dxy_trend: str = "neutral",
    macro_window: str = "normal",
    fear_greed: Optional[int] = None,
) -> Regime:
    """Detect market regime from macro indicators.

    Args:
        vix: Current VIX level
        dxy_trend: 'rising', 'falling', or 'neutral'
        macro_window: Adaptive Macro Matrix window (FULL/NORMAL/SELECTIVE/DEFENSIVE)
        fear_greed: Crypto Fear & Greed index (0-100)
    """
    # Crisis detection first
    if macro_window.upper() == "DEFENSIVE":
        return Regime.CRISIS
    if vix is not None and vix > 35:
        return Regime.CRISIS

    # High volatility
    if vix is not None and vix > 25:
        return Regime.HIGH_VOLATILITY
    if macro_window.upper() == "SELECTIVE":
        return Regime.HIGH_VOLATILITY
    if fear_greed is not None and (fear_greed > 75 or fear_greed < 20):
        return Regime.HIGH_VOLATILITY

    # Range bound (low VIX + neutral DXY)
    if vix is not None and vix < 15 and dxy_trend == "neutral":
        return Regime.RANGE_BOUND

    # Trending
    if dxy_trend == "falling":
        return Regime.TRENDING_BULL
    if dxy_trend == "rising":
        return Regime.TRENDING_BEAR

    return Regime.UNKNOWN


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Dynamic Weight Rebalancing for stock-crypto-analysis"
    )
    parser.add_argument("--regime", type=str, choices=[r.value for r in Regime],
                        help="Explicit regime override")
    parser.add_argument("--vix", type=float, help="VIX level")
    parser.add_argument("--dxy-trend", type=str, default="neutral",
                        choices=["rising", "falling", "neutral"])
    parser.add_argument("--macro-window", type=str, default="normal")
    parser.add_argument("--fear-greed", type=int, help="Fear & Greed index")
    parser.add_argument("--crypto", action="store_true", help="Use crypto base weights")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--regime-detect", action="store_true",
                        help="Only detect regime, don't output weights")
    args = parser.parse_args()

    # Determine regime
    if args.regime:
        regime = Regime(args.regime)
    else:
        regime = detect_regime(
            vix=args.vix,
            dxy_trend=args.dxy_trend,
            macro_window=args.macro_window,
            fear_greed=args.fear_greed,
        )

    if args.regime_detect:
        print(f"Detected regime: {regime.value}")
        return

    weights = get_dynamic_weights(regime, args.crypto)

    if args.json:
        output = {
            "regime": regime.value,
            "is_crypto": args.crypto,
            "weights": weights,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Regime: {regime.value} ({'crypto' if args.crypto else 'stock'})")
        print("\nDynamic Weights:")
        for dim, weight in sorted(weights.items()):
            print(f"  {dim:20s}: {weight:.1%}")

        # Show diff from base
        base = BASE_WEIGHTS_CRYPTO if args.crypto else BASE_WEIGHTS_STOCK
        if regime != Regime.UNKNOWN:
            print("\n  Δ from base:")
            for dim, weight in sorted(weights.items()):
                base_w = base.get(dim, 0)
                delta = weight - base_w
                symbol = "+" if delta > 0 else ""
                print(f"    {dim:18s}: {symbol}{delta:+.1%}")


if __name__ == "__main__":
    main()
