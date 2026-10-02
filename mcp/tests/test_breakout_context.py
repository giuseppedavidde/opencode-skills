"""Tests for the breakout-context module and MCP tool.

Covers: bias-guard firing on strong momentum, breakout-trigger confirmation
logic (fired / not fired with and without volume), GEX overlay failure
handling, and a live HPE + control-ticker comparison.
"""

# pylint: disable=no-member  # pylint mis-infers pydantic Field() as FieldInfo
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_mcp.analysis.breakout_context import (
    BreakoutContext,
    GexOverlay,
    MomentumBlock,
    build_breakout_context,
    build_gex_overlay,
    compute_bias_guard,
    compute_breakout_trigger,
    compute_momentum_block,
    interpret_wall,
    load_thresholds,
    momentum_bias_warning,
)
from trading_mcp.data.stocks import fetch_stock


def _momentum_hist(n: int = 300, breakout_volume: float = 3e6) -> pd.DataFrame:
    """Synthetic strong-uptrend series making a fresh high on big volume."""
    close = pd.Series(np.linspace(10.0, 40.0, n))
    close.iloc[-1] = close.iloc[-2] * 1.05
    volume = pd.Series([1e6] * n)
    volume.iloc[-1] = breakout_volume
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.001,
            "Low": close * 0.999,
            "Close": close,
            "Volume": volume,
        }
    )


def _range_hist(n: int = 300) -> pd.DataFrame:
    """Synthetic neutral/range-bound series."""
    rng = np.random.default_rng(0)
    close = pd.Series(50.0 + np.cumsum(rng.normal(0.0, 0.2, n)))
    close.iloc[-1] = float(close.mean())
    volume = pd.Series([1e6] * n)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.002,
            "Low": close * 0.998,
            "Close": close,
            "Volume": volume,
        }
    )


# ── thresholds ───────────────────────────────────────────────────────────


def test_load_thresholds_reads_calibration_file() -> None:
    """The calibrated thresholds.json is consumed when present."""
    cfg = load_thresholds()
    assert cfg["breakout_lookback_days"] == 252
    assert cfg["breakout_volume_mult"] == pytest.approx(2.0)
    assert cfg["atr_window"] == 14
    assert cfg["stop_atr_mult"] == pytest.approx(2.0)
    assert cfg["holding_days_preferred"] == 120
    assert cfg["caveats"]


def test_load_thresholds_falls_back_on_missing_file(tmp_path) -> None:
    """A missing file yields sensible defaults without raising."""
    cfg = load_thresholds(tmp_path / "nope.json")
    assert cfg["breakout_lookback_days"] == 252
    assert cfg["breakout_volume_mult"] == pytest.approx(2.0)
    assert cfg["caveats"]


# ── bias guard ───────────────────────────────────────────────────────────


def test_bias_guard_fires_on_strong_momentum() -> None:
    """Strong 12m momentum above SMA200 raises the guard flag."""
    cfg = load_thresholds()
    momentum = compute_momentum_block(_momentum_hist(), cfg)
    guard = compute_bias_guard(momentum, cfg)
    assert guard.flag is True
    assert guard.momentum_strength == "strong"
    assert "MOMENTUM BIAS GUARD" in guard.reason
    assert "mean-reversion" in guard.reason.lower()


def test_bias_guard_silent_on_range_bound_name() -> None:
    """A neutral/range name does not raise the guard."""
    cfg = load_thresholds()
    momentum = compute_momentum_block(_range_hist(), cfg)
    guard = compute_bias_guard(momentum, cfg)
    assert guard.flag is False
    assert guard.momentum_strength == "neutral"


def test_momentum_bias_warning_returns_none_for_range() -> None:
    """The compact warning is None when no bias is detected."""
    assert momentum_bias_warning(_range_hist()) is None


def test_momentum_bias_warning_present_for_momentum() -> None:
    """The compact warning surfaces flag+reason for a momentum name."""
    warning = momentum_bias_warning(_momentum_hist())
    assert warning is not None
    assert warning["flag"] is True
    assert warning["reason"]


# ── breakout trigger ─────────────────────────────────────────────────────


def test_breakout_trigger_fires_with_volume_confirmation() -> None:
    """Fresh high + 3x volume + above SMA200 fires the trigger."""
    cfg = load_thresholds()
    hist = _momentum_hist(breakout_volume=3e6)
    momentum = compute_momentum_block(hist, cfg)
    trigger = compute_breakout_trigger(hist, momentum, cfg)
    assert trigger.fired is True
    assert trigger.confirmations.close_above_level is True
    assert trigger.confirmations.volume_ok is True
    assert trigger.confirmations.above_sma200 is True
    assert "NOT certified" in trigger.status
    assert trigger.level is not None


def test_breakout_trigger_not_fired_without_volume() -> None:
    """Fresh high but weak volume fails the volume confirmation."""
    cfg = load_thresholds()
    hist = _momentum_hist(breakout_volume=1.1e6)
    momentum = compute_momentum_block(hist, cfg)
    trigger = compute_breakout_trigger(hist, momentum, cfg)
    assert trigger.fired is False
    assert trigger.confirmations.close_above_level is True
    assert trigger.confirmations.volume_ok is False
    assert "volume_ok" in trigger.status


def test_breakout_trigger_not_fired_in_range() -> None:
    """A range-bound name never triggers."""
    cfg = load_thresholds()
    hist = _range_hist()
    momentum = compute_momentum_block(hist, cfg)
    trigger = compute_breakout_trigger(hist, momentum, cfg)
    assert trigger.fired is False


def test_breakout_trigger_insufficient_data() -> None:
    """Empty history returns an insufficient_data status."""
    cfg = load_thresholds()
    trigger = compute_breakout_trigger(
        pd.DataFrame(), MomentumBlock(), cfg
    )
    assert trigger.status == "insufficient_data"


def test_ret_12m_available_with_exactly_lookback_bars() -> None:
    """A 1y fetch (exactly 252 bars) still yields a 12m return estimate."""
    cfg = load_thresholds()
    hist = _momentum_hist(n=252)
    momentum = compute_momentum_block(hist, cfg)
    assert momentum.ret_12m is not None
    assert momentum.ret_12m > 0


# ── GEX overlay ──────────────────────────────────────────────────────────


def test_gex_overlay_handles_failure_gracefully(monkeypatch) -> None:
    """A failing analyze_gex yields an unavailable overlay, not an exception."""
    import trading_mcp.analysis.gex as gex_mod  # pylint: disable=import-outside-toplevel

    def _boom(*_args, **_kwargs):
        raise RuntimeError("no option data")

    monkeypatch.setattr(gex_mod, "analyze_gex", _boom)
    overlay = build_gex_overlay("HPE", MomentumBlock(ret_12m=0.5))
    assert overlay.available is False
    assert overlay.regime == "unavailable"
    assert overlay.error is not None
    assert "unavailable" in overlay.wall_interpretation.lower()


def test_interpret_wall_regime_awareness() -> None:
    """Call wall is an attractor in long-gamma/trend, resistance in neutral."""
    trending = MomentumBlock(ret_12m=0.5)
    long_gamma = interpret_wall("long_gamma", trending)
    short_gamma = interpret_wall("short_gamma", trending)
    neutral = interpret_wall("neutral", trending)
    assert "ATTRACTOR" in long_gamma
    assert "checkpoint" in short_gamma
    assert "resistance" in neutral
    assert "NOT justified" in long_gamma


def test_interpret_wall_unavailable() -> None:
    """An unavailable regime applies no wall interpretation."""
    assert "unavailable" in interpret_wall("unavailable", MomentumBlock()).lower()


# ── full payload ─────────────────────────────────────────────────────────


def test_build_breakout_context_never_certifies_edge() -> None:
    """The payload is always honest about the uncertified edge."""
    cfg = load_thresholds()
    payload = build_breakout_context(
        "TEST", _momentum_hist(), cfg, include_gex=False
    )
    assert isinstance(payload, BreakoutContext)
    assert payload.evidence.edge_certified is False
    assert payload.evidence.source == "research/breakout_calibration"
    assert payload.evidence.caveats
    assert payload.ticker == "TEST"
    assert payload.risk.holding_days_preferred == 120
    assert payload.risk.suggested_stop is not None


def test_build_breakout_context_gex_disabled() -> None:
    """include_gex=False returns an unavailable overlay without calling GEX."""
    cfg = load_thresholds()
    payload = build_breakout_context(
        "TEST", _range_hist(), cfg, include_gex=False
    )
    assert payload.gex.available is False
    assert isinstance(payload.gex, GexOverlay)


# ── live network tests ───────────────────────────────────────────────────


@pytest.mark.network
def test_live_hpe_reflects_post_breakout_momentum() -> None:
    """Live HPE: strong momentum -> bias guard raised, honest payload."""
    hist = fetch_stock("HPE", period="2y")
    assert not hist.empty
    cfg = load_thresholds()
    payload = build_breakout_context("HPE", hist, cfg, include_gex=False)
    assert payload.evidence.edge_certified is False
    assert payload.momentum.ret_12m is not None
    assert payload.momentum.dist_sma200_pct is not None
    # HPE is a documented post-breakout momentum name: guard must fire.
    assert payload.bias_guard.flag is True
    assert payload.bias_guard.momentum_strength in {"strong", "moderate"}
    print("\nHPE live payload:")
    print(payload.model_dump_json(indent=2))


@pytest.mark.network
def test_live_control_ticker_is_neutral() -> None:
    """Live control (KO): a low-momentum name for contrast."""
    hist = fetch_stock("KO", period="2y")
    if hist.empty or len(hist) < 252:
        pytest.skip("insufficient KO history")
    cfg = load_thresholds()
    payload = build_breakout_context("KO", hist, cfg, include_gex=False)
    print("\nKO control payload (bias flag):", payload.bias_guard.flag)
    print("KO ret_12m:", payload.momentum.ret_12m)
    # No assertion on the flag itself (market-dependent); we assert the
    # payload is well-formed and honest.
    assert payload.evidence.edge_certified is False
