"""Macro regime classification and dynamic weight rebalancing (SIG-07).

One regime object for every caller: :func:`current_regime` (stateful, with
hysteresis) and :func:`classify_regime` (pure). The scanner and
``analyze_stock`` must read the regime from here.

Equity regime rules (equity inputs only; crypto Fear & Greed and BTC never
enter it):

1. Volatility state from the VIX level, with hysteresis:

   - ``crisis``: enter at VIX >= 35, leave when VIX < 32;
   - ``high``: enter at VIX >= 25, leave when VIX < 23;
   - ``normal`` otherwise.

2. ``crisis`` gives CRISIS and ``high`` gives HIGH_VOLATILITY.
3. In the ``normal`` state the S&P 500 trend decides: ``up`` gives
   TRENDING_BULL, ``down`` TRENDING_BEAR, ``range`` RANGE_BOUND.
4. A missing VIX, or a missing equity trend in the ``normal`` state, gives
   UNKNOWN (``degraded``). UNKNOWN maps to the DEFENSIVE window.
5. The dollar never flips the direction. A rising DXY in a bull trend adds
   the note ``dollar_headwind``; a falling DXY in a bear trend adds
   ``dollar_tailwind``.

Window mapping: CRISIS and TRENDING_BEAR give DEFENSIVE, HIGH_VOLATILITY
gives SELECTIVE, RANGE_BOUND gives NORMAL, TRENDING_BULL gives FULL,
UNKNOWN gives DEFENSIVE.

The hysteresis state (volatility state, regime, start time) is saved in the
private cache (``<cache>/regime/regime_state.json``). A state older than five
days is ignored, so a restart after a long pause starts without memory.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data.cache_paths import atomic_write_json, cache_dir, read_json
from trading_mcp.timeutil import iso, to_datetime, utc_now
from trading_mcp.weights_config import get_weights

logger = logging.getLogger(__name__)


class Regime(str, Enum):
    """Market regime classification."""

    UNKNOWN = "unknown"
    CRISIS = "crisis"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"


VIX_HIGH_ENTER = 25.0
VIX_HIGH_EXIT = 23.0
VIX_CRISIS_ENTER = 35.0
VIX_CRISIS_EXIT = 32.0
STATE_MAX_AGE = timedelta(days=5)

VOL_NORMAL = "normal"
VOL_HIGH = "high"
VOL_CRISIS = "crisis"

_REGIME_TO_MACRO_WINDOW: dict[Regime, str] = {
    Regime.CRISIS: "DEFENSIVE",
    Regime.HIGH_VOLATILITY: "SELECTIVE",
    Regime.RANGE_BOUND: "NORMAL",
    Regime.TRENDING_BULL: "FULL",
    Regime.TRENDING_BEAR: "DEFENSIVE",
    Regime.UNKNOWN: "DEFENSIVE",
}


def regime_to_macro_window(regime: Regime) -> str:
    """Map a :class:`Regime` to its Adaptive Macro Matrix window (UNKNOWN is DEFENSIVE)."""
    return _REGIME_TO_MACRO_WINDOW.get(regime, "DEFENSIVE")


class RegimeState(BaseModel):
    """Result of one regime classification (the single regime object)."""

    regime: Regime
    macro_window: str
    vol_state: str | None = None
    previous_regime: Regime | None = None
    previous_vol_state: str | None = None
    hysteresis_applied: bool = False
    changed: bool = False
    since: str | None = Field(default=None, description="Start of the current regime (ISO 8601)")
    computed_at: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    degraded: bool = False
    reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=lambda: {
        "vix_high_enter": VIX_HIGH_ENTER, "vix_high_exit": VIX_HIGH_EXIT,
        "vix_crisis_enter": VIX_CRISIS_ENTER, "vix_crisis_exit": VIX_CRISIS_EXIT,
    })


def _vol_state(vix: float | None, previous: str | None) -> tuple[str | None, bool]:
    """Volatility state with hysteresis; returns ``(state, hysteresis_applied)``."""
    if vix is None:
        return None, False
    stateless = VOL_CRISIS if vix >= VIX_CRISIS_ENTER else VOL_HIGH if vix >= VIX_HIGH_ENTER else VOL_NORMAL
    if previous == VOL_CRISIS:
        state = VOL_CRISIS if vix >= VIX_CRISIS_EXIT else VOL_HIGH if vix >= VIX_HIGH_EXIT else VOL_NORMAL
    elif previous == VOL_HIGH:
        state = VOL_CRISIS if vix >= VIX_CRISIS_ENTER else VOL_HIGH if vix >= VIX_HIGH_EXIT else VOL_NORMAL
    else:
        state = stateless
    return state, state != stateless


def classify_regime(
    vix: float | None,
    equity_trend: str | None,
    dxy_trend: str | None = None,
    *,
    previous_vol_state: str | None = None,
) -> tuple[Regime, str | None, bool, list[str], list[str], list[str]]:
    """Pure classification (see the module rules).

    Returns:
        ``(regime, vol_state, hysteresis_applied, reasons, notes, missing_inputs)``.
    """
    reasons: list[str] = []
    notes: list[str] = []
    missing: list[str] = []
    vol, hysteresis = _vol_state(vix, previous_vol_state)
    if vix is None:
        missing.append("vix")
    if equity_trend not in ("up", "down", "range"):
        missing.append("equity_trend")
        equity_trend = None

    if vol == VOL_CRISIS:
        reasons.append(f"VIX {vix:.2f} in the crisis band (enter {VIX_CRISIS_ENTER}, leave below {VIX_CRISIS_EXIT})")
        regime = Regime.CRISIS
    elif vol == VOL_HIGH:
        reasons.append(f"VIX {vix:.2f} in the high band (enter {VIX_HIGH_ENTER}, leave below {VIX_HIGH_EXIT})")
        regime = Regime.HIGH_VOLATILITY
    elif vol is None:
        reasons.append("VIX unavailable: the volatility state is unknown")
        regime = Regime.UNKNOWN
    elif equity_trend is None:
        reasons.append("S&P 500 trend unavailable")
        regime = Regime.UNKNOWN
    else:
        reasons.append(f"VIX {vix:.2f} below the high band; S&P 500 trend {equity_trend}")
        regime = {"up": Regime.TRENDING_BULL, "down": Regime.TRENDING_BEAR}.get(equity_trend, Regime.RANGE_BOUND)
    if hysteresis:
        reasons.append(f"hysteresis kept the {vol} volatility state")
    if dxy_trend == "rising" and equity_trend == "up":
        notes.append("dollar_headwind")
    elif dxy_trend == "falling" and equity_trend == "down":
        notes.append("dollar_tailwind")
    if dxy_trend is None:
        notes.append("dxy_trend_unavailable")
    return regime, vol, hysteresis, reasons, notes, missing


def detect_regime(
    vix: float | None = None,
    dxy_trend: str | None = "neutral",
    macro_window: str = "normal",
    fear_greed: int | None = None,
    equity_trend: str | None = None,
) -> Regime:
    """Stateless legacy wrapper around :func:`classify_regime`.

    ``fear_greed`` is accepted for compatibility and ignored: the crypto
    Fear & Greed index is not an equity input. ``macro_window`` DEFENSIVE
    forces CRISIS and SELECTIVE forces at least HIGH_VOLATILITY.
    """
    del fear_greed
    window = (macro_window or "").upper()
    if window == "DEFENSIVE":
        return Regime.CRISIS
    regime = classify_regime(vix, equity_trend, dxy_trend)[0]
    if window == "SELECTIVE" and regime not in (Regime.CRISIS, Regime.HIGH_VOLATILITY):
        return Regime.HIGH_VOLATILITY
    return regime


# ── Persisted hysteresis state ───────────────────────────────────────

_state_lock = threading.Lock()
_STATE_FILE = "regime_state.json"


def _state_path() -> Path | None:
    directory = cache_dir("regime")
    return directory / _STATE_FILE if directory is not None else None


def load_regime_state(path: Path | None = None, now: datetime | None = None) -> dict[str, Any] | None:
    """Return the saved state, or ``None`` when absent, unreadable or older than 5 days."""
    target = path or _state_path()
    if target is None:
        return None
    state = read_json(target)
    if not isinstance(state, dict):
        return None
    updated = to_datetime(state.get("updated_at"))
    reference = now or utc_now()
    if updated is None or reference - updated > STATE_MAX_AGE:
        return None
    return state


def save_regime_state(state: dict[str, Any], path: Path | None = None) -> bool:
    """Persist the hysteresis state atomically in the private cache."""
    target = path or _state_path()
    return target is not None and atomic_write_json(target, state)


def current_regime(
    inputs: Any | None = None,
    *,
    persist: bool = True,
    state_path: Path | None = None,
    now: datetime | None = None,
) -> RegimeState:
    """Classify the current equity regime with hysteresis (the single regime object).

    Args:
        inputs: :class:`~trading_mcp.data.macro_inputs.MacroInputs`; fetched
            through the DataProvider when ``None``.
        persist: Load and save the hysteresis state in the cache.
        state_path: Explicit state file (tests).
        now: Classification time (tests).
    """
    if inputs is None:
        from trading_mcp.data.macro_inputs import collect_macro_inputs  # pylint: disable=import-outside-toplevel

        inputs = collect_macro_inputs()
    moment = now or utc_now()
    vix = inputs.vix.value if inputs.vix.usable else None
    equity_trend = inputs.equity_trend
    with _state_lock:
        saved = load_regime_state(state_path, moment) if persist else None
        previous_vol = saved.get("vol_state") if saved else None
        previous_regime = None
        if saved and saved.get("regime") in {r.value for r in Regime}:
            previous_regime = Regime(saved["regime"])
        regime, vol, hysteresis, reasons, notes, missing = classify_regime(
            vix, equity_trend, inputs.dxy_trend, previous_vol_state=previous_vol
        )
        changed = previous_regime is not None and previous_regime != regime
        since = iso(moment)
        if saved and not changed and saved.get("since"):
            since = saved["since"]
        if inputs.spx.stale:
            notes.append("spx_history_stale")
        state = RegimeState(
            regime=regime,
            macro_window=regime_to_macro_window(regime),
            vol_state=vol,
            previous_regime=previous_regime,
            previous_vol_state=previous_vol,
            hysteresis_applied=hysteresis,
            changed=changed,
            since=since,
            computed_at=iso(moment),
            inputs={
                "vix": vix, "vix_as_of": inputs.vix.as_of,
                "equity_trend": equity_trend, "equity_as_of": inputs.spx.as_of,
                "dxy_trend": inputs.dxy_trend,
            },
            missing_inputs=missing,
            degraded=bool(missing) or regime is Regime.UNKNOWN,
            reasons=reasons,
            notes=notes,
        )
        if persist and vol is not None:
            save_regime_state({
                "vol_state": vol, "regime": regime.value, "since": since, "updated_at": iso(moment),
            }, state_path)
    return state


# ── Dynamic weights ──────────────────────────────────────────────────

def _get_base_weights_stock() -> dict[str, float]:
    """Get base stock weights from config."""
    return get_weights().stocks.to_dict()


def _get_base_weights_crypto() -> dict[str, float]:
    """Get base crypto weights from config."""
    return get_weights().crypto.to_dict()


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
