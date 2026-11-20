"""Trade plan from the volume-profile rule, with hard invariants (SIG-01, SIG-02, SIG-12, SIG-19).

The rule is a HYPOTHESIS (mean reversion toward the one-year value area), not
a validated edge. The repository evidence for it (IC -0.068) used daily rows
with overlapping 180-day labels and a naive p-value, on a 365-bar profile,
and raw (not excess) returns. No walk-forward test exists, so every action
carries ``validation_status="unvalidated"`` and no hit rate is published
unless a verified, walk-forward, better-than-naive artifact exists.

Zones of the extension score (see :mod:`trading_mcp.analysis.volume_profile`):

- ``<= 40`` (discount): long candidate; a plan is built and checked;
- ``>= 60`` (extended): ``AVOID`` new longs (it is NOT a short signal);
- otherwise ``HOLD`` (no signal).

Long plan (documented rule):

- entry: the current price (quote when fresh, else the last complete close);
- target: the first level at least 0.25 ATR ABOVE the entry among VAL, POC,
  VAH and the HVNs; with no level above, entry + 3 ATR (``atr_projection``);
- stop: 0.5 ATR below the first support (VAL, POC, VAH, HVN) at least
  0.25 ATR below the entry and at most 4 ATR away; else entry - 2 ATR (the
  research stop). The stop is always at least 1 ATR below the entry;
- reward/risk = (target - entry) / (entry - stop). When an earnings report can
  fall inside the horizon, the gate uses the gap-adjusted value: the stop can
  gap through by the earnings-gap estimate (median of the four largest
  overnight gaps of the last year), so the risk becomes
  ``entry - stop x (1 - gap)``.

A ``LONG_TERM_BUY`` needs ALL of: stop < entry < target, reward/risk >= 1.5,
no earnings in the blackout window (the next 10 calendar days), and the same
zone at 0.5x, 1x and 2x the profile bin width. Otherwise the action is
``HOLD`` and ``plan_status`` says why (the rejected plan is kept in
``rejected_plan``). Without a profile there is no stop and no target.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from trading_mcp.analysis.ta_core import event_gap_estimate
from trading_mcp.analysis.volume_profile import get_profile_levels, zone_of
from trading_mcp.calibration import accept_probability_artifact, load_artifact
from trading_mcp.weights_config import config_home

logger = logging.getLogger(__name__)

HORIZON_DAYS = 120
HORIZON_UNIT = "trading_days"
HORIZON_CALENDAR_DAYS = int(round(HORIZON_DAYS * 365.0 / 252.0))
MIN_REWARD_RISK = 1.5
TARGET_MIN_DISTANCE_ATR = 0.25
STOP_BUFFER_ATR = 0.5
STOP_MIN_ATR = 1.0
STOP_DEFAULT_ATR = 2.0
STRUCTURE_STOP_MAX_ATR = 4.0
TARGET_PROJECTION_ATR = 3.0
EARNINGS_BLACKOUT_DAYS = 10
VALIDATION_STATUS = "unvalidated"
VALIDATION_NOTE = (
    "No walk-forward test of this rule exists. The old IC -0.068 claim used overlapping "
    "180-day labels and a naive p-value; it is not evidence. Compare with base_rate."
)

ACTION_BUY = "LONG_TERM_BUY"
ACTION_HOLD = "HOLD"
ACTION_AVOID = "AVOID"
ACTION_ORDER = {ACTION_BUY: 0, ACTION_HOLD: 1, ACTION_AVOID: 2}

SIGNAL_LIMITS = [
    "The volume-profile rule is an unvalidated hypothesis (mean reversion to the 1-year value area).",
    "Reward/risk uses profile levels and ATR; fills, costs and slippage are not modelled.",
    "AVOID means: do not open a new long. It is not a short signal.",
]

_NOT_EARNINGS_TYPES = ("ETF", "INDEX", "CRYPTOCURRENCY", "CURRENCY", "FUTURE", "MUTUALFUND")


# ── Calibration artifact (SIG-19) ────────────────────────────────────────

def vp_calibration_path() -> Path:
    """``$TRADING_VP_CALIBRATION_FILE`` or ``<config>/opencode/calibrations/vp_calibration.json``."""
    env = os.environ.get("TRADING_VP_CALIBRATION_FILE", "").strip()
    if env:
        return Path(env)
    return config_home() / "opencode" / "calibrations" / "vp_calibration.json"


def _calibrated_hit_rate(extension_score: float, payload: dict[str, Any]) -> float | None:
    """Isotonic map of the favorability (100 - extension) to a hit rate, or ``None``."""
    iso_x, iso_y = payload.get("isotonic_X"), payload.get("isotonic_Y")
    if not iso_x or not iso_y or len(iso_x) != len(iso_y):
        return None
    value = float(np.interp(100.0 - float(extension_score), iso_x, iso_y))
    return round(min(1.0, max(0.0, value)), 4)


def calibration_status(extension_score: float | None, path: str | Path | None = None) -> dict[str, Any]:
    """Calibrated hit rate only from an accepted artifact; else ``None`` and the reason."""
    target = Path(path) if path else vp_calibration_path()
    artifact = load_artifact(target, name="vp_calibration", source="vp_calibration")
    out: dict[str, Any] = {"hit_rate_calibrated": None, "calibration_status": "not_calibrated",
                           "calibration_file": None, "calibration_note": "no calibration artifact"}
    if artifact is None:
        return out
    out["calibration_file"] = str(target)
    accepted, reason = accept_probability_artifact(artifact)
    if not accepted:
        out.update(calibration_status="rejected", calibration_note=reason)
        return out
    rate = _calibrated_hit_rate(extension_score, artifact.payload) if extension_score is not None else None
    out.update(calibration_status="calibrated" if rate is not None else "rejected",
               calibration_note=reason if rate is not None else "artifact has no isotonic curve",
               hit_rate_calibrated=rate)
    return out


# ── Earnings (SIG-12) ────────────────────────────────────────────────────

def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def earnings_context(events: Any, *, horizon_days: int = HORIZON_DAYS) -> dict[str, Any]:
    """Next earnings window, blackout flag and horizon overlap from :class:`CorporateEvents`."""
    horizon_cal = int(round(horizon_days * 365.0 / 252.0))
    out: dict[str, Any] = {
        "status": "unknown", "next_start": None, "next_end": None, "days_until": None,
        "timing": None, "is_estimate": None, "last_earnings": None,
        "blackout": False, "blackout_days": EARNINGS_BLACKOUT_DAYS,
        "within_horizon": None, "source": _get(events, "source"), "as_of": _get(events, "as_of"),
        "warnings": list(_get(events, "warnings") or []),
    }
    if events is None:
        out["warnings"].append("corporate events unavailable")
        return out
    quote_type = _get(events, "quote_type")
    out["last_earnings"] = _get(events, "last_earnings")
    if quote_type in _NOT_EARNINGS_TYPES:
        out.update(status="not_applicable", within_horizon=False)
        return out
    window = _get(events, "next_earnings")
    days = _get(window, "days_until")
    if window is None or days is None:
        return out
    days = float(days)
    out.update(
        status="scheduled", next_start=_get(window, "start"), next_end=_get(window, "end"),
        days_until=round(days, 2), timing=_get(window, "timing"), is_estimate=_get(window, "is_estimate"),
        blackout=days <= EARNINGS_BLACKOUT_DAYS, within_horizon=days <= horizon_cal,
    )
    return out


def earnings_flags(earnings: dict[str, Any]) -> list[str]:
    """``earnings_in_<n>d`` within 14 days and ``earnings_blackout``."""
    flags: list[str] = []
    days = earnings.get("days_until")
    if days is not None and days <= 14:
        flags.append(f"earnings_in_{max(0, int(np.floor(days)))}d")
    if earnings.get("blackout"):
        flags.append("earnings_blackout")
    return flags


# ── Plan helpers ─────────────────────────────────────────────────────────

def _levels(levels: dict[str, Any]) -> list[tuple[float, str]]:
    found: list[tuple[float, str]] = []
    for key, name in (("val", "VAL"), ("poc_price", "POC"), ("vah", "VAH")):
        value = levels.get(key)
        if value is not None:
            found.append((float(value), name))
    for value in levels.get("hvn") or []:
        found.append((float(value), "HVN"))
    return found


def build_long_plan(entry: float, atr: float, levels: dict[str, Any]) -> dict[str, Any]:
    """Target, stop and reward/risk of a long at ``entry`` (see the module docstring)."""
    found = _levels(levels)
    above = sorted((p, n) for p, n in found if p >= entry + TARGET_MIN_DISTANCE_ATR * atr)
    if above:
        target, target_type = above[0][0], above[0][1].lower()
    else:
        target, target_type = entry + TARGET_PROJECTION_ATR * atr, "atr_projection"
    below = sorted(((p, n) for p, n in found if p <= entry - TARGET_MIN_DISTANCE_ATR * atr), reverse=True)
    if below and entry - below[0][0] <= STRUCTURE_STOP_MAX_ATR * atr:
        stop, stop_type = below[0][0] - STOP_BUFFER_ATR * atr, f"{below[0][1].lower()}_minus_0.5atr"
    else:
        stop, stop_type = entry - STOP_DEFAULT_ATR * atr, "2atr"
    if entry - stop < STOP_MIN_ATR * atr:
        stop, stop_type = entry - STOP_MIN_ATR * atr, "1atr_minimum"
    risk = entry - stop
    reward = target - entry
    valid = stop > 0 and stop < entry < target
    return {
        "entry_price": round(entry, 4),
        "target_price": round(target, 4),
        "target_type": target_type,
        "stop_price": round(stop, 4) if stop > 0 else None,
        "stop_type": stop_type,
        "risk_pct": round(risk / entry, 4) if valid else None,
        "reward_pct": round(reward / entry, 4) if valid else None,
        "reward_risk": round(reward / risk, 3) if valid and risk > 0 else None,
        "valid": valid,
    }


def _gap_adjust(plan: dict[str, Any], gap: float | None) -> float | None:
    if gap is None or not plan.get("valid"):
        return None
    entry, stop, target = plan["entry_price"], plan["stop_price"], plan["target_price"]
    risk = entry - stop * (1.0 - gap)
    return round((target - entry) / risk, 3) if risk > 0 else None


def _entry_zone(position: str | None) -> str:
    return {"below_val": "below VAL", "inside_va": "inside VA", "above_vah": "above VAH"}.get(position or "", "unknown")


# ── Action ───────────────────────────────────────────────────────────────

def compute_action(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    hist: pd.DataFrame | None = None,
    context: dict | None = None,
    levels: dict | None = None,
    calibration_path: str | Path | None = None,
    *,
    price: float | None = None,
    price_as_of: str | None = None,
    price_source: str | None = None,
    events: Any = None,
    gap_estimate: float | None = None,
    size_multiplier: float = 1.0,
    regime_window: str | None = None,
    base_rate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational recommendation with an invariant-checked trade plan.

    Args:
        hist: Complete daily bars (used when ``levels`` or ``gap_estimate`` are missing).
        context: Scanner row (composite score, sector, pattern) for the ``context`` block.
        levels: Output of :func:`get_profile_levels`.
        calibration_path: VP calibration artifact (default :func:`vp_calibration_path`).
        price: Entry price (quote); the profile close is used when ``None``.
        price_as_of: Data time of ``price``.
        price_source: Source label of ``price``.
        events: :class:`~trading_mcp.data.events.CorporateEvents` (or a dict).
        gap_estimate: Earnings-gap fraction; estimated from ``hist`` when ``None``.
        size_multiplier: Regime risk-budget multiplier (1.0, 0.5 or 0.25).
        regime_window: Macro window that set ``size_multiplier``.
        base_rate: Base-rate block to embed (see :mod:`trading_mcp.analysis.base_rates`).
    """
    if levels is None:
        if hist is None:
            raise ValueError("Either hist or levels must be provided")
        levels = get_profile_levels(hist)
    if gap_estimate is None and hist is not None:
        gap_estimate = event_gap_estimate(hist)

    ext = levels.get("score")
    atr = levels.get("atr")
    available = bool(levels.get("available")) and ext is not None and atr is not None
    entry = float(price) if price is not None else levels.get("price")
    zone = zone_of(ext) if available else None
    earnings = earnings_context(events)
    sens = levels.get("sensitivity") or {}

    out: dict[str, Any] = {
        "action": ACTION_HOLD,
        "signal": {"discount": "vp_discount", "extended": "vp_extended", "inside": "vp_inside"}.get(zone or "", "none"),
        "plan_status": "no_signal",
        "horizon_days": HORIZON_DAYS,
        "horizon_unit": HORIZON_UNIT,
        "validation_status": VALIDATION_STATUS,
        "validation_note": VALIDATION_NOTE,
        "volume_profile_score": ext,
        "vp_zone": zone,
        "vp_zone_stable": sens.get("zone_stable"),
        "entry_price": None,
        "price": round(float(entry), 4) if entry is not None else None,
        "entry_as_of": price_as_of,
        "entry_source": price_source,
        "target_price": None,
        "target_type": None,
        "stop_price": None,
        "stop_type": None,
        "reward_risk": None,
        "reward_risk_gap_adjusted": None,
        "risk_pct": None,
        "reward_pct": None,
        "gap_risk_pct": round(gap_estimate, 4) if gap_estimate is not None else None,
        "min_reward_risk": MIN_REWARD_RISK,
        "atr": round(float(atr), 4) if atr is not None else None,
        "position_size_multiplier": size_multiplier,
        "regime_window": regime_window,
        "entry_zone": _entry_zone(levels.get("price_position")),
        "poc_reference": levels.get("poc_price"),
        "levels": {"poc": levels.get("poc_price"), "val": levels.get("val"), "vah": levels.get("vah"),
                   "hvn": list(levels.get("hvn") or []), "lvn": list(levels.get("lvn") or [])},
        "earnings": earnings,
        "rejected_plan": None,
        "base_rate": base_rate,
        "evidence": [],
        "signal_limits": list(SIGNAL_LIMITS),
    }
    out.update(calibration_status(ext if available else None, calibration_path))
    evidence: list[str] = out["evidence"]

    if not available:
        out["plan_status"] = "no_profile"
        evidence.append(f"No volume profile ({levels.get('detail', 'insufficient data')}): no signal, no stop, no target.")
        return _finish(out, context)

    evidence.append(f"Volume-profile extension {ext}/100 ({zone}); {levels.get('detail', '')}")
    if zone == "extended":
        out.update(action=ACTION_AVOID, plan_status="no_long_plan")
        evidence.append("Extended above the value area: no new long. AVOID is not a short signal.")
        return _finish(out, context)
    if zone == "inside":
        out["plan_status"] = "no_signal"
        evidence.append("Inside the value area: the rule gives no direction.")
        return _finish(out, context)
    if entry is None:
        out["plan_status"] = "no_price"
        evidence.append("No entry price: no plan.")
        return _finish(out, context)

    plan = build_long_plan(float(entry), float(atr), levels)
    rr = plan["reward_risk"]
    rr_gap = _gap_adjust(plan, gap_estimate)
    gap_applies = earnings["within_horizon"] is not False
    gate = rr_gap if gap_applies and rr_gap is not None else rr
    candidate = {k: plan[k] for k in ("entry_price", "target_price", "target_type", "stop_price", "stop_type",
                                      "reward_risk", "risk_pct", "reward_pct")}
    candidate["reward_risk_gap_adjusted"] = rr_gap
    if gap_applies and gap_estimate is None:
        evidence.append("Earnings gap risk unknown (too few bars): reward/risk is not gap-adjusted.")

    if not plan["valid"]:
        status = "invalid_plan"
    elif earnings["blackout"]:
        status = "blocked_earnings"
    elif sens and sens.get("zone_stable") is False:
        status = "zone_unstable"
    elif gate is None or gate < MIN_REWARD_RISK:
        status = "rejected_reward_risk"
    else:
        status = "active"

    if status == "active":
        out.update(action=ACTION_BUY, plan_status=status, **candidate)
        evidence.append(
            f"Plan: entry {plan['entry_price']:.2f}, stop {plan['stop_price']:.2f} ({plan['stop_type']}), "
            f"target {plan['target_price']:.2f} ({plan['target_type']}), reward/risk {rr:.2f}"
            + (f" ({rr_gap:.2f} with a {gap_estimate:.1%} earnings gap)" if rr_gap is not None else "")
        )
    else:
        out.update(plan_status=status, rejected_plan=candidate)
        reason = {
            "invalid_plan": "the levels give no valid long plan (target or stop on the wrong side)",
            "blocked_earnings": f"earnings in {earnings['days_until']:.1f} days (blackout {EARNINGS_BLACKOUT_DAYS} d)"
            if earnings.get("days_until") is not None else "earnings blackout",
            "zone_unstable": "the zone changes with the profile bin width",
            "rejected_reward_risk": f"reward/risk {gate if gate is not None else float('nan'):.2f} < {MIN_REWARD_RISK}",
        }[status]
        evidence.append(f"Discount zone, but HOLD: {reason}.")
    return _finish(out, context)


def plan_invariants_ok(action: dict[str, Any]) -> bool:
    """True unless a LONG_TERM_BUY breaks stop < entry < target or the reward/risk floor."""
    if action.get("action") != ACTION_BUY:
        return action.get("stop_price") is None and action.get("target_price") is None
    stop, entry, target = action.get("stop_price"), action.get("entry_price"), action.get("target_price")
    rr = action.get("reward_risk")
    if None in (stop, entry, target, rr):
        return False
    gate = action.get("reward_risk_gap_adjusted")
    gate = gate if gate is not None and action.get("earnings", {}).get("within_horizon") is not False else rr
    return 0 < stop < entry < target and gate >= MIN_REWARD_RISK - 1e-9


def _finish(out: dict[str, Any], context: dict | None) -> dict[str, Any]:
    if out["action"] == ACTION_BUY and not plan_invariants_ok(out):
        # Defensive: never publish a long plan that breaks the invariants.
        out["rejected_plan"] = {k: out.get(k) for k in ("entry_price", "target_price", "stop_price", "reward_risk")}
        out.update(action=ACTION_HOLD, plan_status="invalid_plan", entry_price=None, target_price=None,
                   target_type=None, stop_price=None, stop_type=None, reward_risk=None,
                   reward_risk_gap_adjusted=None, risk_pct=None, reward_pct=None)
    out["invariants_ok"] = plan_invariants_ok(out)
    context_out: dict[str, Any] = {}
    if context is not None:
        context_out = {k: v for k, v in {
            "composite_score": context.get("final_score"),
            "sector": context.get("sector"),
            "pattern": context.get("pattern"),
        }.items() if v is not None}
    out["context"] = context_out
    return out
