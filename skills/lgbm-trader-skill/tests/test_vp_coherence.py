"""Test VP decision coherence: mean-reversion semantics.

Verify that the same semantics (VP high → AVOID, VP low → BUY) is used
consistently across signal_engine.py and _analysis_tools.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))


class TestVPSemantics:
    """VP score thresholds: ≤40 = BUY, ≥60 = AVOID, else HOLD."""

    def test_signal_engine_low_vp_is_buy(self) -> None:
        """VP ≤ 40 must produce LONG_TERM_BUY."""
        # Add MCP src to path
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.signal_engine import compute_action

        levels = {
            "score": 35,
            "val": 100.0,
            "vah": 120.0,
            "poc_price": 110.0,
            "price": 95.0,
            "price_position": "below_val",
        }
        result = compute_action(levels=levels)
        assert result["action"] == "LONG_TERM_BUY", (
            f"VP={levels['score']} should be BUY, got {result['action']}"
        )

    def test_signal_engine_high_vp_is_avoid(self) -> None:
        """VP ≥ 60 must produce AVOID."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.signal_engine import compute_action

        levels = {
            "score": 70,
            "val": 100.0,
            "vah": 120.0,
            "poc_price": 110.0,
            "price": 130.0,
            "price_position": "above_vah",
        }
        result = compute_action(levels=levels)
        assert result["action"] == "AVOID", (
            f"VP={levels['score']} should be AVOID, got {result['action']}"
        )

    def test_signal_engine_mid_vp_is_hold(self) -> None:
        """VP in (40, 60) must produce HOLD."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.signal_engine import compute_action

        levels = {
            "score": 50,
            "val": 100.0,
            "vah": 120.0,
            "poc_price": 110.0,
            "price": 110.0,
            "price_position": "inside_va",
        }
        result = compute_action(levels=levels)
        assert result["action"] == "HOLD", (
            f"VP={levels['score']} should be HOLD, got {result['action']}"
        )

    def test_compute_verdict_low_vp_is_long_term(self) -> None:
        """_compute_verdict: VP ≤ 40 must produce Long-Term Investment."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.tools._analysis_tools import _compute_verdict

        result = {
            "profile_levels": {"score": 35},
            "dimensions": [],
            "modifiers": {},
            "indicators": {"risk_reward": 50},
        }
        verdict = _compute_verdict(60.0, [], result)
        assert "Buy" in verdict["verdict"] or "Long-Term" in verdict["verdict"], (
            f"VP=35 + composite=60 should be bullish, got {verdict['verdict']}"
        )

    def test_compute_verdict_high_vp_is_avoid(self) -> None:
        """_compute_verdict: VP ≥ 60 must produce Avoid / Wait."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.tools._analysis_tools import _compute_verdict

        result = {
            "profile_levels": {"score": 70},
            "dimensions": [],
            "modifiers": {},
            "indicators": {"risk_reward": 50},
        }
        verdict = _compute_verdict(40.0, [], result)
        assert "Avoid" in verdict["verdict"], (
            f"VP=70 + composite=40 should be Avoid, got {verdict['verdict']}"
        )

    def test_threshold_boundaries(self) -> None:
        """Regression test: verify exact threshold behavior."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.signal_engine import compute_action

        # VP = 40 → BUY (≤ boundary)
        r1 = compute_action(levels={
            "score": 40, "val": 100, "vah": 120,
            "poc_price": 110, "price": 95, "price_position": "below_val"
        })
        assert r1["action"] == "LONG_TERM_BUY", f"VP=40 boundary: {r1['action']}"

        # VP = 41 → HOLD (just above BUY)
        r2 = compute_action(levels={
            "score": 41, "val": 100, "vah": 120,
            "poc_price": 110, "price": 110, "price_position": "inside_va"
        })
        assert r2["action"] == "HOLD", f"VP=41 boundary: {r2['action']}"

        # VP = 59 → HOLD (just below AVOID)
        r3 = compute_action(levels={
            "score": 59, "val": 100, "vah": 120,
            "poc_price": 110, "price": 110, "price_position": "inside_va"
        })
        assert r3["action"] == "HOLD", f"VP=59 boundary: {r3['action']}"

        # VP = 60 → AVOID (≥ boundary)
        r4 = compute_action(levels={
            "score": 60, "val": 100, "vah": 120,
            "poc_price": 110, "price": 130, "price_position": "above_vah"
        })
        assert r4["action"] == "AVOID", f"VP=60 boundary: {r4['action']}"

    def test_no_levels_raises_error(self) -> None:
        """compute_action without hist or levels must raise ValueError."""
        mcp_src = Path(
            "/home/giuseppe/Progetti/Github/opencode-skills/mcp/src"
        )
        if str(mcp_src) not in sys.path:
            sys.path.insert(0, str(mcp_src))

        from trading_mcp.analysis.signal_engine import compute_action

        with pytest.raises(ValueError, match="Either hist or levels must be provided"):
            compute_action()
