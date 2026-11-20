"""Liquidity score of one option strike: spread, open interest, volume.

``score`` (0-100) = 50% spread + 30% open interest + 20% volume:

- spread: 100 at a spread of 2% of the mid or less, 0 at 30% or more (linear);
- open interest: log scale, 100 at 2,000 contracts or more;
- volume: log scale, 100 at 1,000 contracts or more (volume is low early in
  the session, so it has the smallest weight).

A strike is ``tradable`` only with a bid above 0, an ask, a spread of at most
:data:`MAX_SPREAD_PCT` of the mid (or at most :data:`MAX_SPREAD_ABS` dollars for
cheap options) and at least :data:`MIN_OPEN_INTEREST` contracts. ``grade`` is
``good`` (score 70 or more), ``fair`` (40 or more), ``poor`` or ``untradable``.
"""

from __future__ import annotations

import math
from typing import Any

MAX_SPREAD_PCT = 0.20
MAX_SPREAD_ABS = 0.05
MIN_OPEN_INTEREST = 100


def _clip(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def liquidity(bid: float | None, ask: float | None, open_interest: float | None,
              volume: float | None) -> dict[str, Any]:
    """Liquidity block of one strike (see the module docstring)."""
    oi = float(open_interest or 0.0)
    vol = float(volume or 0.0)
    has_quote = (
        bid is not None and ask is not None and math.isfinite(bid) and math.isfinite(ask)
        and ask > 0 and ask >= bid
    )
    mid = 0.5 * (bid + ask) if has_quote else None
    spread = (ask - bid) if has_quote else None
    spread_pct = spread / mid if has_quote and mid and mid > 0 else None
    s_spread = _clip(1.0 - ((spread_pct if spread_pct is not None else 1.0) - 0.02) / 0.28)
    s_oi = _clip(math.log10(1.0 + oi) / math.log10(2001.0))
    s_vol = _clip(math.log10(1.0 + vol) / math.log10(1001.0))
    score = round(100.0 * (0.5 * s_spread + 0.3 * s_oi + 0.2 * s_vol), 1) if has_quote else 0.0
    reasons: list[str] = []
    if not has_quote:
        reasons.append("no two-sided quote")
    elif bid <= 0:
        reasons.append("bid is 0")
    if has_quote and spread_pct is not None and spread_pct > MAX_SPREAD_PCT and spread > MAX_SPREAD_ABS:
        reasons.append(f"spread {spread_pct * 100:.0f}% of mid")
    if oi < MIN_OPEN_INTEREST:
        reasons.append(f"open interest {int(oi)} < {MIN_OPEN_INTEREST}")
    tradable = not reasons
    grade = "untradable" if not tradable else "good" if score >= 70 else "fair" if score >= 40 else "poor"
    return {
        "score": score,
        "grade": grade,
        "tradable": tradable,
        "spread": round(spread, 4) if spread is not None else None,
        "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
        "open_interest": int(oi),
        "volume": int(vol),
        "reasons": reasons,
    }
