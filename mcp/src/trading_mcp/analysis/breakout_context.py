"""Breakout context + momentum bias guard.

This module implements a *honest* breakout overlay for momentum names. It was
born from a concrete failure: applying mean-reversion logic (fade the call wall,
sell the extension) to a stock that is actually in a confirmed uptrend.

Two things are deliberately kept separate:

1.  ``compute_bias_guard`` raises a loud flag when a name has strong momentum
    but the surrounding analysis tends to interpret it in mean-reversion terms
    (RSI "overbought", distance above SMA200, a GEX call wall). The guard does
    NOT promise an edge; it only prevents the known *bias*.

2.  ``compute_breakout_trigger`` exposes a conditional breakout trigger
    (close above the 252d high WITH a 2x volume expansion AND above SMA200).
    Phase 1 calibration proved that **no raw breakout configuration beat the
    baseline in-sample**, so this trigger is explicitly labelled as NOT
    statistically certified. The value is the honest labelling, not an edge.

Thresholds are consumed from
``research/breakout_calibration/output/thresholds.json`` when present, with
sensible baked-in defaults and a warning otherwise.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Threshold defaults (mirror the Phase 1 thresholds.json) ──────────────
_BREAKOUT_LOOKBACK_DAYS = 252
_BREAKOUT_VOLUME_MULT = 2.0
_BREAKOUT_REQUIRES_VOLUME = True
_ATR_WINDOW = 14
_STOP_ATR_MULT = 2.0
_HOLDING_DAYS_PREFERRED = 120
_MIN_MOMENTUM_12M = 0.0
_VOLUME_AVG_WINDOW = 20
_MOMENTUM_LOOKBACK_DAYS = 252

# Relative path from this file to the calibration output.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_THRESHOLDS_PATH = (
    _REPO_ROOT
    / "research"
    / "breakout_calibration"
    / "output"
    / "thresholds.json"
)

# Caveats fallback if the calibrated file is missing.
_DEFAULT_CAVEATS = [
    "Breakout edge NOT certified: no raw configuration beat the baseline "
    "in-sample (Phase 1 calibration).",
    "Survivorship bias present in the calibration universe.",
    "Overlapping forward windows inflate the effective sample.",
]


class MomentumBlock(BaseModel):
    """Momentum / trend / extension measurements for the analysed name."""

    ret_12m: float | None = None
    tsmom_signal: int | None = None
    tsmom_direction: str = "unavailable"
    dist_sma200_pct: float | None = None
    dist_sma50_pct: float | None = None
    rsi14: float | None = None
    atr14: float | None = None
    is_extended: bool = False
    extension_atr_above_sma50: float | None = None


class BiasGuard(BaseModel):
    """Explicit guard against applying mean-reversion to a momentum name."""

    flag: bool = False
    reason: str = ""
    momentum_strength: str = "unknown"


class BreakoutConfirmations(BaseModel):
    """Per-condition confirmation booleans for the breakout trigger."""

    close_above_level: bool = False
    volume_ok: bool = False
    above_sma200: bool = False


class BreakoutTrigger(BaseModel):
    """Conditional, NOT-certified breakout trigger state."""

    lookback_days: int = _BREAKOUT_LOOKBACK_DAYS
    level: float | None = None
    volume_avg20: float | None = None
    volume_mult: float = _BREAKOUT_VOLUME_MULT
    volume_today: float | None = None
    fired: bool = False
    confirmations: BreakoutConfirmations = Field(
        default_factory=BreakoutConfirmations
    )
    status: str = "unavailable"


class GexOverlay(BaseModel):
    """Best-effort GEX overlay, regime-aware."""

    regime: str = "unavailable"
    call_wall: float | None = None
    put_wall: float | None = None
    gamma_flip: float | None = None
    wall_interpretation: str = ""
    available: bool = False
    error: str | None = None


class RiskBlock(BaseModel):
    """Suggested risk levels derived from the calibrated ATR stop."""

    suggested_stop: float | None = None
    atr: float | None = None
    atr_mult: float = _STOP_ATR_MULT
    holding_days_preferred: int = _HOLDING_DAYS_PREFERRED


class EvidenceBlock(BaseModel):
    """Provenance and honesty disclaimer."""

    source: str = "research/breakout_calibration"
    edge_certified: bool = False
    expected_win_rate: float | None = None
    expected_excess_return: float | None = None
    caveats: list[str] = Field(default_factory=list)


class BreakoutContext(BaseModel):
    """Full breakout-context payload."""

    ticker: str
    price: float | None = None
    momentum: MomentumBlock = Field(default_factory=MomentumBlock)
    bias_guard: BiasGuard = Field(default_factory=BiasGuard)
    breakout_triggers: BreakoutTrigger = Field(default_factory=BreakoutTrigger)
    gex: GexOverlay = Field(default_factory=GexOverlay)
    risk: RiskBlock = Field(default_factory=RiskBlock)
    evidence: EvidenceBlock = Field(default_factory=EvidenceBlock)
    error: str | None = None


def _default_thresholds() -> dict[str, Any]:
    """Baked-in thresholds used when the calibration file is unavailable."""
    return {
        "breakout_lookback_days": _BREAKOUT_LOOKBACK_DAYS,
        "breakout_volume_mult": _BREAKOUT_VOLUME_MULT,
        "breakout_requires_volume": _BREAKOUT_REQUIRES_VOLUME,
        "atr_window": _ATR_WINDOW,
        "stop_atr_mult": _STOP_ATR_MULT,
        "holding_days_preferred": _HOLDING_DAYS_PREFERRED,
        "min_momentum_12m": _MIN_MOMENTUM_12M,
        "expected_win_rate": None,
        "expected_excess_return": None,
        "caveats": list(_DEFAULT_CAVEATS),
    }


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    """Load calibrated thresholds, falling back to sane defaults.

    Args:
        path: Optional explicit path to ``thresholds.json``.

    Returns:
        Threshold dictionary. If the file is missing or malformed, defaults are
        returned and a warning is logged.
    """
    target = path or _THRESHOLDS_PATH
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("thresholds.json is not a JSON object")
        merged = _default_thresholds()
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "breakout_context: could not load thresholds from %s (%s); "
            "using defaults",
            target,
            exc,
        )
        return _default_thresholds()


def _safe_float(value: Any) -> float | None:
    """Coerce ``value`` to float, returning None on failure."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def compute_atr(hist: pd.DataFrame, window: int) -> float | None:
    """Compute the latest ATR over ``window`` bars."""
    if hist.empty or len(hist) < window:
        return None
    high = hist["High"]
    low = hist["Low"]
    close_prev = hist["Close"].shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window).mean().iloc[-1]
    return _safe_float(round(float(atr), 4))


def compute_rsi(hist: pd.DataFrame, window: int = 14) -> float | None:
    """Compute the latest Wilder RSI over ``window`` bars."""
    if hist.empty or len(hist) < window + 1:
        return None
    delta = hist["Close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=window - 1).mean()
    ma_down = down.ewm(com=window - 1).mean()
    rs_series = ma_up / ma_down.replace(0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs_series))
    return _safe_float(round(float(rsi.iloc[-1]), 2))


def compute_momentum_block(
    hist: pd.DataFrame, thresholds: dict[str, Any]
) -> MomentumBlock:
    """Build the momentum/trend/extension block from OHLCV history."""
    block = MomentumBlock()
    if hist.empty:
        return block

    close = hist["Close"]
    price = _safe_float(close.iloc[-1])
    atr_window = int(thresholds.get("atr_window", _ATR_WINDOW))
    atr = compute_atr(hist, atr_window)
    rsi = compute_rsi(hist, atr_window)
    block.atr14 = atr
    block.rsi14 = rsi

    lookback = int(thresholds.get("breakout_lookback_days", _BREAKOUT_LOOKBACK_DAYS))
    if price is not None and len(close) > lookback:
        past = _safe_float(close.iloc[-(lookback + 1)])
        if past and past > 0:
            block.ret_12m = round(price / past - 1.0, 4)
    elif price is not None and len(close) >= lookback:
        # Exactly lookback bars: approximate 12m from the earliest available bar.
        past = _safe_float(close.iloc[0])
        if past and past > 0:
            block.ret_12m = round(price / past - 1.0, 4)

    sma50 = _safe_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = (
        _safe_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    )
    if price is not None and sma50 and sma50 > 0:
        block.dist_sma50_pct = round((price / sma50 - 1.0) * 100.0, 2)
    if price is not None and sma200 and sma200 > 0:
        block.dist_sma200_pct = round((price / sma200 - 1.0) * 100.0, 2)

    if price is not None and sma50 and atr and atr > 0:
        ext_atr = (price - sma50) / atr
        block.extension_atr_above_sma50 = round(float(ext_atr), 2)
        block.is_extended = ext_atr >= 2.0
    return block


def compute_bias_guard(
    momentum: MomentumBlock, thresholds: dict[str, Any]
) -> BiasGuard:
    """Raise a mean-reversion bias flag when momentum is strong/extended.

    The guard fires when the name shows a confirmed uptrend (positive 12m
    return, price above a rising reference) yet is likely to be read as
    "overbought". It never asserts an edge; it only blocks the known bias.
    """
    min_mom = float(thresholds.get("min_momentum_12m", _MIN_MOMENTUM_12M))
    ret12 = momentum.ret_12m
    above_sma200 = momentum.dist_sma200_pct is not None and momentum.dist_sma200_pct > 0
    strong_ret = ret12 is not None and ret12 > max(min_mom, 0.20)
    moderate_ret = ret12 is not None and ret12 > min_mom
    overbought = momentum.rsi14 is not None and momentum.rsi14 >= 70.0

    if strong_ret and above_sma200:
        strength = "strong"
    elif moderate_ret and above_sma200 and (overbought or momentum.is_extended):
        strength = "moderate"
    elif above_sma200 and (overbought or momentum.is_extended):
        strength = "moderate"
    else:
        strength = "neutral"

    if strength == "neutral":
        return BiasGuard(
            flag=False,
            momentum_strength="neutral",
            reason=(
                "No confirmed momentum/uptrend detected: mean-reversion logic "
                "(fading extension or a GEX wall) is not contradicted here."
            ),
        )

    parts: list[str] = []
    if ret12 is not None:
        parts.append(f"12m return {ret12:+.1%}")
    if momentum.dist_sma200_pct is not None:
        parts.append(f"{momentum.dist_sma200_pct:+.1f}% above SMA200")
    if momentum.dist_sma50_pct is not None:
        parts.append(f"{momentum.dist_sma50_pct:+.1f}% above SMA50")
    if momentum.rsi14 is not None:
        parts.append(f"RSI14 {momentum.rsi14:.0f}")
    if momentum.extension_atr_above_sma50 is not None:
        parts.append(
            f"{momentum.extension_atr_above_sma50:+.1f} ATR above SMA50"
        )
    context = ", ".join(parts) if parts else "confirmed uptrend"

    reason = (
        f"MOMENTUM BIAS GUARD ({strength}): {context}. This is a trending / "
        "momentum name, NOT a mean-reversion candidate. Do NOT treat the "
        "extension as a fade signal, and do NOT treat a GEX call wall as a "
        "hard ceiling: in a long-gamma regime a call wall acts as a price "
        "ATTRACTOR/pin rather than resistance, and in a short-gamma regime "
        "hedging flow amplifies the trend. Avoid setting a bearish bias based "
        "solely on 'overbought' readings for this profile."
    )
    return BiasGuard(flag=True, momentum_strength=strength, reason=reason)


def _breakout_level(close: pd.Series, lookback: int) -> float | None:
    """Return the max close over the lookback window, excluding today's bar."""
    if len(close) > lookback:
        window = close.iloc[-(lookback + 1) : -1]
    else:
        window = close.iloc[:-1]
    if window.empty:
        return None
    return _safe_float(window.max())


def _volume_confirmation(
    volume: pd.Series, vol_mult: float, requires_volume: bool
) -> tuple[float | None, float | None, bool]:
    """Return ``(volume_avg20, volume_today, volume_ok)``."""
    vol_avg = _safe_float(volume.rolling(_VOLUME_AVG_WINDOW).mean().iloc[-1])
    if vol_avg is None and len(volume) >= _VOLUME_AVG_WINDOW:
        vol_avg = _safe_float(volume.iloc[-_VOLUME_AVG_WINDOW:].mean())
    volume_today = _safe_float(volume.iloc[-1])
    if not requires_volume:
        return vol_avg, volume_today, True
    volume_ok = (
        vol_avg is not None
        and vol_avg > 0
        and volume_today is not None
        and volume_today > vol_mult * vol_avg
    )
    return vol_avg, volume_today, volume_ok


def compute_breakout_trigger(  # pylint: disable=too-many-locals
    hist: pd.DataFrame, momentum: MomentumBlock, thresholds: dict[str, Any]
) -> BreakoutTrigger:
    """Compute the conditional (NOT certified) breakout trigger state.

    The trigger fires when the latest close is above the 252d high AND the
    volume exceeds ``volume_mult`` x the 20d average AND price is above SMA200.
    """
    lookback = int(thresholds.get("breakout_lookback_days", _BREAKOUT_LOOKBACK_DAYS))
    vol_mult = float(thresholds.get("breakout_volume_mult", _BREAKOUT_VOLUME_MULT))
    requires_volume = bool(
        thresholds.get("breakout_requires_volume", _BREAKOUT_REQUIRES_VOLUME)
    )
    requires_sma200 = bool(thresholds.get("require_close_above_sma200", True))

    trigger = BreakoutTrigger(lookback_days=lookback, volume_mult=vol_mult)
    if hist.empty or "Volume" not in hist.columns:
        trigger.status = "insufficient_data"
        return trigger

    close = hist["Close"]
    price = _safe_float(close.iloc[-1])
    if price is None or len(close) < 2:
        trigger.status = "insufficient_data"
        return trigger

    level = _breakout_level(close, lookback)
    if level is None:
        trigger.status = "insufficient_data"
        return trigger
    trigger.level = round(level, 2)

    vol_avg, volume_today, volume_ok = _volume_confirmation(
        hist["Volume"], vol_mult, requires_volume
    )
    trigger.volume_avg20 = round(vol_avg, 2) if vol_avg is not None else None
    trigger.volume_today = round(volume_today, 2) if volume_today is not None else None

    above_level = price > level
    above_sma200 = momentum.dist_sma200_pct is not None and momentum.dist_sma200_pct > 0
    if not requires_sma200:
        above_sma200 = True

    trigger.confirmations = BreakoutConfirmations(
        close_above_level=above_level,
        volume_ok=volume_ok,
        above_sma200=above_sma200,
    )
    trigger.fired = bool(above_level and volume_ok and above_sma200)
    if trigger.fired:
        trigger.status = (
            "fired (NOT certified): price above level with volume expansion and "
            "above SMA200 — conditional setup only, no proven statistical edge."
        )
    else:
        missing = [
            name
            for name, ok in (
                ("close_above_level", above_level),
                ("volume_ok", volume_ok),
                ("above_sma200", above_sma200),
            )
            if not ok
        ]
        trigger.status = "not fired: missing " + ", ".join(missing)
    return trigger


def interpret_wall(regime: str, momentum: MomentumBlock) -> str:
    """Regime-aware interpretation of a GEX call wall.

    Args:
        regime: One of ``long_gamma``, ``short_gamma``, ``neutral``,
            ``unavailable``.
        momentum: The momentum block for context.

    Returns:
        Human-readable interpretation string.
    """
    trending = momentum.ret_12m is not None and momentum.ret_12m > 0.0
    if regime == "long_gamma":
        base = (
            "Long-gamma regime: hedging pins price toward high-gamma strikes, "
            "so the call wall behaves as an ATTRACTOR, not a hard resistance."
        )
    elif regime == "short_gamma":
        base = (
            "Short-gamma regime: dealer hedging amplifies moves, so the call "
            "wall can be broken and overtaken; treat it as a checkpoint, not a "
            "ceiling."
        )
    elif regime == "neutral":
        base = (
            "Neutral gamma: the call wall may act as ordinary resistance in a "
            "range, but has no mechanical magnet effect."
        )
    else:
        return "GEX unavailable: no wall interpretation applied."
    if trending:
        base += (
            " Momentum is positive, so a mean-reversion fade of this wall is "
            "NOT justified."
        )
    return base


def build_gex_overlay(ticker: str, momentum: MomentumBlock) -> GexOverlay:
    """Best-effort GEX overlay; never raises."""
    try:
        # Deferred import: keeps the GEX/options deps optional at module load.
        from trading_mcp.analysis.gex import (  # pylint: disable=import-outside-toplevel
            analyze_gex,
        )

        raw = analyze_gex(ticker)
        regime = str(raw.get("regime", "neutral"))
        overlay = GexOverlay(
            regime=regime,
            call_wall=_safe_float(raw.get("call_wall")),
            put_wall=_safe_float(raw.get("put_wall")),
            gamma_flip=_safe_float(raw.get("gamma_flip")),
            available=True,
        )
        if overlay.call_wall is not None:
            overlay.wall_interpretation = interpret_wall(regime, momentum)
        else:
            overlay.wall_interpretation = (
                "No call wall identified in the available option chains."
            )
        return overlay
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("breakout_context: GEX overlay failed for %s: %s", ticker, exc)
        return GexOverlay(
            regime="unavailable",
            available=False,
            error=f"{type(exc).__name__}: {exc}",
            wall_interpretation="GEX unavailable: no wall interpretation applied.",
        )


def build_breakout_context(
    ticker: str,
    hist: pd.DataFrame,
    thresholds: dict[str, Any] | None = None,
    include_gex: bool = True,
) -> BreakoutContext:
    """Assemble the full breakout-context payload from OHLCV history.

    Args:
        ticker: Stock ticker symbol.
        hist: OHLCV history DataFrame (columns Open/High/Low/Close/Volume).
        thresholds: Optional pre-loaded thresholds (loaded if omitted).
        include_gex: Whether to attempt the best-effort GEX overlay.

    Returns:
        A :class:`BreakoutContext` payload.
    """
    cfg = thresholds if thresholds is not None else load_thresholds()
    momentum = compute_momentum_block(hist, cfg)
    bias_guard = compute_bias_guard(momentum, cfg)
    trigger = compute_breakout_trigger(hist, momentum, cfg)

    price = _safe_float(hist["Close"].iloc[-1]) if not hist.empty else None
    atr = momentum.atr14
    stop_mult = float(cfg.get("stop_atr_mult", _STOP_ATR_MULT))
    suggested_stop = (
        round(price - stop_mult * atr, 2)
        if price is not None and atr is not None
        else None
    )

    gex = (
        build_gex_overlay(ticker, momentum)
        if include_gex
        else GexOverlay(available=False, error="gex disabled")
    )

    evidence = EvidenceBlock(
        edge_certified=False,
        expected_win_rate=_safe_float(cfg.get("expected_win_rate")),
        expected_excess_return=_safe_float(cfg.get("expected_excess_return")),
        caveats=list(cfg.get("caveats") or _DEFAULT_CAVEATS),
    )

    return BreakoutContext(
        ticker=ticker.upper(),
        price=round(price, 2) if price is not None else None,
        momentum=momentum,
        bias_guard=bias_guard,
        breakout_triggers=trigger,
        gex=gex,
        risk=RiskBlock(
            suggested_stop=suggested_stop,
            atr=atr,
            atr_mult=stop_mult,
            holding_days_preferred=int(
                cfg.get("holding_days_preferred", _HOLDING_DAYS_PREFERRED)
            ),
        ),
        evidence=evidence,
    )


def momentum_bias_warning(hist: pd.DataFrame) -> dict[str, Any] | None:
    """Compact bias-guard warning for embedding into ``analyze_stock``.

    Args:
        hist: OHLCV history DataFrame.

    Returns:
        ``None`` when no bias is detected, otherwise a small dict with a
        ``flag`` and ``reason`` so the warning cannot be silently ignored.
    """
    cfg = load_thresholds()
    momentum = compute_momentum_block(hist, cfg)
    guard = compute_bias_guard(momentum, cfg)
    if not guard.flag:
        return None
    return {
        "flag": True,
        "momentum_strength": guard.momentum_strength,
        "reason": guard.reason,
    }
