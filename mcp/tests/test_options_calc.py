"""Unit tests for the options position math (no network).

Covers the defects fixed in the audit: signed mark-to-market P&L for short
legs, strike-aware spread classification, break-even interpolation,
dividend-adjusted pricing, and probability semantics for bounded vs
unbounded payoff profiles.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from trading_mcp.analysis.options_calc import (
    OptionLeg,
    _bs_greeks,
    _bs_price,
    _classify_strategy,
    _compute_payoff,
    _compute_probabilities,
    _position_pnl_at,
)


def _expiry(days: int = 45) -> str:
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


class TestDividendAdjustedPricing:
    """Merton extension: q must preserve put-call parity."""

    def test_put_call_parity_with_dividend(self) -> None:
        spot, strike, tte, rate, q, sigma = 100.0, 105.0, 1.0, 0.05, 0.03, 0.2
        call = _bs_price(spot, strike, tte, rate, sigma, "call", q)
        put = _bs_price(spot, strike, tte, rate, sigma, "put", q)
        parity = spot * math.exp(-q * tte) - strike * math.exp(-rate * tte)
        assert call - put == pytest.approx(parity, abs=1e-8)

    def test_q_zero_matches_plain_black_scholes(self) -> None:
        args = (100.0, 100.0, 0.5, 0.04, 0.25)
        assert _bs_price(*args, "call", 0.0) == pytest.approx(_bs_price(*args, "call"))
        assert _bs_greeks(*args, "put", 0.0)["delta"] == pytest.approx(
            _bs_greeks(*args, "put")["delta"]
        )

    def test_call_delta_bounded_by_discount_factor(self) -> None:
        greeks = _bs_greeks(100.0, 90.0, 1.0, 0.05, 0.2, "call", 0.04)
        assert greeks["delta"] <= math.exp(-0.04) + 1e-9


class TestSignedPnl:
    """A short leg must lose money when the mark rises."""

    def _legs(self) -> list[OptionLeg]:
        return [
            OptionLeg("call", 105.0, 1, 10.0),   # long
            OptionLeg("call", 95.0, -1, 14.0),   # short
        ]

    def test_short_leg_pnl_is_negative_when_mark_rises(self) -> None:
        expiry = _expiry()
        expiry_date = date.fromisoformat(expiry)
        legs = [OptionLeg("call", 100.0, -1, 5.0)]
        # At expiry, price 120, strike 100 -> intrinsic 20, entry 5 -> loss 1500.
        pnl = _position_pnl_at(120.0, legs, [expiry], {0: 0.3}, expiry_date, 0.0)
        assert pnl == pytest.approx(-1500.0)

    def test_short_leg_pnl_is_positive_when_mark_falls(self) -> None:
        expiry = _expiry()
        expiry_date = date.fromisoformat(expiry)
        legs = [OptionLeg("call", 100.0, -1, 5.0)]
        pnl = _position_pnl_at(100.0, legs, [expiry], {0: 0.3}, expiry_date, 0.0)
        assert pnl == pytest.approx(500.0)


class TestSpreadClassification:
    """Bull vs bear must depend on the strike order, not on leg count."""

    def test_bear_call_spread(self) -> None:
        legs = [OptionLeg("call", 105.0, 1, 10.0), OptionLeg("call", 95.0, -1, 14.0)]
        assert _classify_strategy(legs) == "Bear Call Spread"

    def test_bull_call_spread(self) -> None:
        legs = [OptionLeg("call", 95.0, 1, 10.0), OptionLeg("call", 105.0, -1, 5.0)]
        assert _classify_strategy(legs) == "Bull Call Spread"

    def test_bull_put_spread(self) -> None:
        legs = [OptionLeg("put", 95.0, 1, 6.0), OptionLeg("put", 105.0, -1, 12.0)]
        assert _classify_strategy(legs) == "Bull Put Spread"

    def test_bear_put_spread(self) -> None:
        legs = [OptionLeg("put", 105.0, 1, 12.0), OptionLeg("put", 95.0, -1, 6.0)]
        assert _classify_strategy(legs) == "Bear Put Spread"

    def test_long_straddle(self) -> None:
        legs = [OptionLeg("call", 100.0, 1, 5.0), OptionLeg("put", 100.0, 1, 5.0)]
        assert _classify_strategy(legs) == "Long Straddle"


class TestBreakevens:
    """Break-evens come from zero crossings, not a dollar tolerance."""

    def test_short_put_breakeven(self) -> None:
        expiry = _expiry()
        legs = [OptionLeg("put", 95.0, -1, 3.0)]
        _, breakevens = _compute_payoff(legs, 100.0, 0.05, expiry, [expiry], {0: 0.25})
        assert breakevens == pytest.approx([92.0], abs=0.6)

    def test_bull_call_spread_breakeven(self) -> None:
        expiry = _expiry()
        legs = [OptionLeg("call", 95.0, 1, 7.0), OptionLeg("call", 105.0, -1, 3.0)]
        _, breakevens = _compute_payoff(legs, 100.0, 0.05, expiry, [expiry] * 2, {0: 0.25, 1: 0.25})
        assert breakevens == pytest.approx([99.0], abs=0.6)


class TestProbabilities:
    """Probabilities must be finite and distinguish bounded payoffs."""

    def _prob(self, legs: list[OptionLeg]) -> dict:
        expiry = _expiry()
        ivs = {i: 0.25 for i in range(len(legs))}
        pay, _ = _compute_payoff(legs, 100.0, 0.05, expiry, [expiry] * len(legs), ivs)
        return _compute_probabilities(
            legs, 100.0, 0.05, expiry, [expiry] * len(legs), ivs, payoff=pay
        )

    def test_itm_and_otm_are_complementary(self) -> None:
        probs = self._prob([OptionLeg("put", 95.0, -1, 3.0)])
        assert 0.0 <= probs["itm_prob"] <= 1.0
        assert probs["itm_prob"] + probs["otm_prob"] == pytest.approx(1.0, abs=1e-3)

    def test_bounded_spread_is_not_flagged_unbounded(self) -> None:
        probs = self._prob(
            [OptionLeg("call", 95.0, 1, 7.0), OptionLeg("call", 105.0, -1, 3.0)]
        )
        assert probs["max_profit_unbounded"] is False
        assert probs["max_loss_unbounded"] is False
        assert 0.0 <= probs["max_profit_prob"] <= 1.0

    def test_long_call_marks_profit_unbounded(self) -> None:
        probs = self._prob([OptionLeg("call", 105.0, 1, 2.0)])
        assert probs["max_profit_unbounded"] is True
        assert probs["max_profit_prob"] == pytest.approx(probs["profit_prob"])
