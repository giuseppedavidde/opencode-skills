"""Tests for the Gamma Exposure (GEX) analysis module and MCP tool."""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta

import pytest
from scipy.stats import norm

from trading_mcp.analysis.gex import (
    GexLeg,
    StrikeGex,
    _extreme_strike,
    _iv_quality,
    _regime,
    _select_expiries,
    aggregate_strikes,
    analyze_gex,
    build_profile,
    collect_legs,
    find_gamma_flip,
    net_gex_at_spot,
)


def _leg(strike: float, gamma: float, oi: int) -> dict[str, float]:
    return {"strike": strike, "gamma": gamma, "openInterest": oi}


def test_aggregate_strikes_sign_convention() -> None:
    """Call GEX is positive, put GEX negative, and chains sum per strike."""
    spot = 100.0
    chains = [
        {"calls": [_leg(100, 0.01, 1000)], "puts": [_leg(100, 0.01, 1000)]},
        {"calls": [_leg(100, 0.01, 1000)], "puts": [_leg(100, 0.01, 1000)]},
    ]
    agg = aggregate_strikes(chains, spot)
    # gamma*oi*100*S^2*0.01 = 0.01*1000*100*1e4*0.01 = 100_000 per leg
    assert agg[100.0]["call_gex"] == pytest.approx(200_000.0)
    assert agg[100.0]["put_gex"] == pytest.approx(-200_000.0)
    assert agg[100.0]["call_oi"] == 2000
    assert agg[100.0]["put_oi"] == 2000


def test_build_profile_net_gex() -> None:
    """Net GEX per strike equals call GEX plus (negative) put GEX."""
    agg = {
        100.0: {
            "call_gex": 300.0,
            "put_gex": -100.0,
            "call_oi": 1.0,
            "put_oi": 1.0,
            "call_gamma": 0.1,
            "put_gamma": 0.1,
        }
    }
    profile = build_profile(agg)
    assert len(profile) == 1
    assert profile[0].net_gex == pytest.approx(200.0)


def test_find_gamma_flip_repriced_zero() -> None:
    """Gamma flip is the spot where the repriced net GEX crosses zero."""
    legs = [
        GexLeg(strike=90.0, tte=1.0, rate=0.03, sigma=0.20, is_call=False, open_interest=1.0),
        GexLeg(strike=110.0, tte=1.0, rate=0.03, sigma=0.20, is_call=True, open_interest=1.0),
    ]
    flip = find_gamma_flip(legs, 100.0)
    assert flip is not None
    assert 90.0 < flip < 110.0
    below = net_gex_at_spot(legs, flip - 1.0)
    above = net_gex_at_spot(legs, flip + 1.0)
    assert below * above < 0.0


def test_find_gamma_flip_none_without_sign_change() -> None:
    """No flip when the repriced net GEX keeps one sign across the grid."""
    calls_only = [
        GexLeg(strike=100.0, tte=1.0, rate=0.03, sigma=0.20, is_call=True, open_interest=100.0)
    ]
    assert find_gamma_flip(calls_only, 100.0) is None
    assert find_gamma_flip([], 100.0) is None


def test_repricing_matches_profile_at_spot() -> None:
    """Repriced net GEX at the current spot equals the per-strike profile sum."""
    spot, rate, sigma = 100.0, 0.03, 0.20
    tte = 30.0 / 365.0
    expiry = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

    def leg_gamma(strike: float) -> float:
        d1 = (math.log(spot / strike) + (rate + 0.5 * sigma ** 2) * tte) / (sigma * math.sqrt(tte))
        return norm.pdf(d1) / (spot * sigma * math.sqrt(tte))

    chain = {
        "selected_expiry": expiry,
        "risk_free_rate": {"value": rate},
        "calls": [
            {"strike": 105.0, "gamma": leg_gamma(105.0), "openInterest": 500, "iv_used": sigma}
        ],
        "puts": [
            {"strike": 95.0, "gamma": leg_gamma(95.0), "openInterest": 300, "iv_used": sigma}
        ],
    }
    profile_net = sum(point.net_gex for point in build_profile(aggregate_strikes([chain], spot)))
    assert net_gex_at_spot(collect_legs([chain]), spot) == pytest.approx(profile_net, rel=1e-6)


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_select_expiries_excludes_0dte_and_far_dated() -> None:
    """0DTE and expirations beyond max_dte are dropped; the rest are kept."""
    first = {
        "selected_expiry": _future(30),
        "expirations": [
            _future(0),
            _future(3),
            _future(10),
            _future(30),
            _future(60),
            _future(120),
            _future(200),
        ],
    }
    picked = _select_expiries(first, None, 12, 120)
    assert _future(0) not in picked
    assert _future(200) not in picked
    assert picked == [_future(3), _future(10), _future(30), _future(60), _future(120)]


def test_select_expiries_spreads_across_term_structure() -> None:
    """When capped, expirations span the window instead of clustering near-dated."""
    dates = [_future(d) for d in range(1, 121)]
    first = {"selected_expiry": dates[0], "expirations": dates}
    picked = _select_expiries(first, None, 5, 120)
    assert len(picked) == 5
    assert dates[0] in picked
    assert dates[-1] in picked


def test_select_expiries_explicit_expiry_wins() -> None:
    """An explicit expiry restricts the selection to that single chain."""
    first = {"selected_expiry": _future(30), "expirations": [_future(3), _future(30)]}
    assert _select_expiries(first, _future(3), 12, 120) == [_future(30)]


@pytest.mark.parametrize(
    ("net_gex", "expected"),
    [(100.0, "long_gamma"), (-100.0, "short_gamma"), (0.0, "neutral")],
)
def test_regime_classification(net_gex: float, expected: str) -> None:
    """Regime maps the sign of net GEX to long/short/neutral gamma."""
    regime, description = _regime(net_gex)
    assert regime == expected
    assert description


def test_extreme_strike_walls() -> None:
    """Call/put walls and extreme gamma strikes resolve to the right strike."""
    profile = [
        StrikeGex(strike=95.0, call_gex=50.0, put_gex=-10.0, net_gex=40.0),
        StrikeGex(strike=105.0, call_gex=500.0, put_gex=-900.0, net_gex=-400.0),
    ]
    assert _extreme_strike(profile, "call_gex", most_negative=False) == 105.0
    assert _extreme_strike(profile, "put_gex", most_negative=True) == 105.0
    assert _extreme_strike(profile, "net_gex", most_negative=True) == 105.0
    assert _extreme_strike(profile, "net_gex", most_negative=False) == 95.0
    assert _extreme_strike([], "net_gex", most_negative=False) is None


def test_wall_returns_none_when_no_negative_put() -> None:
    """A put wall is undefined when no strike has negative put GEX."""
    profile = [StrikeGex(strike=100.0, call_gex=0.0, put_gex=0.0, net_gex=0.0)]
    assert _extreme_strike(profile, "put_gex", most_negative=True) is None


def test_gex_tool_registered() -> None:
    """The gex_analysis tool is exposed by the initialized MCP server."""
    from trading_mcp.mcp import initialize_mcp  # pylint: disable=import-outside-toplevel

    server = initialize_mcp()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert "gex_analysis" in names


def test_analyze_gex_offline_fallback() -> None:
    """analyze_gex on an invalid ticker must return a well-formed empty result."""
    result = analyze_gex("__NOT_A_TICKER__", expiry="2000-01-01")
    assert result["ticker"] == "__NOT_A_TICKER__"
    assert result["n_strikes"] == 0
    assert "net_gex" in result
    assert result["regime"] in {"neutral", "long_gamma", "short_gamma"}


def test_build_profile_iv_weighted_and_source() -> None:
    """Per-strike IV is OI-weighted; source is the dominant provenance."""
    chains = [
        {
            "calls": [
                {
                    "strike": 100.0,
                    "gamma": 0.01,
                    "openInterest": 100,
                    "iv_used": 0.20,
                    "iv_source": "quote",
                },
                {
                    "strike": 100.0,
                    "gamma": 0.01,
                    "openInterest": 300,
                    "iv_used": 0.40,
                    "iv_source": "smile",
                },
            ],
            "puts": [],
        }
    ]
    point = build_profile(aggregate_strikes(chains, 100.0))[0]
    assert point.iv_source == "smile"
    assert point.iv == pytest.approx((0.20 * 100 + 0.40 * 300) / 400)


def test_iv_quality_coverage_metric() -> None:
    """Coverage is the real-quote share; synthetic/fallback counted apart."""
    chains = [
        {
            "calls": [
                {"iv_source": "quote"},
                {"iv_source": "quote"},
                {"iv_source": "smile"},
            ],
            "puts": [{"iv_source": "fallback"}],
        }
    ]
    quality = _iv_quality(chains)
    assert quality["coverage_pct"] == pytest.approx(50.0)
    assert (quality["num_quote"], quality["num_synthetic"], quality["num_fallback"]) == (2, 1, 1)


def test_iv_quality_none_without_legs() -> None:
    """No legs → coverage undefined (None), not a misleading zero."""
    quality = _iv_quality([])
    assert quality["coverage_pct"] is None
    assert (quality["num_quote"], quality["num_synthetic"], quality["num_fallback"]) == (0, 0, 0)


@pytest.mark.network
def test_analyze_gex_live() -> None:
    """Functional test against a real ticker (requires network)."""
    result = analyze_gex("SPY", max_expiries=1, top_n=5)
    if result["n_strikes"] == 0:
        pytest.skip("no live option chain available")
    assert result["underlying_price"] > 0
    assert result["regime"] in {"long_gamma", "short_gamma", "neutral"}
    assert len(result["profile"]) <= 5
    assert result["total_call_gex"] >= 0
    assert result["total_put_gex"] <= 0


@pytest.mark.network
@pytest.mark.parametrize("ticker", ["SPY", "SLB"])
def test_analyze_gex_live_iv_coverage(ticker: str) -> None:
    """Live GEX reports IV provenance/coverage for liquid and thinner names."""
    result = analyze_gex(ticker, max_expiries=1, top_n=10)
    if result["n_strikes"] == 0:
        pytest.skip(f"no live option chain available for {ticker}")
    coverage = result["iv_coverage_pct"]
    assert coverage is None or 0.0 <= coverage <= 100.0
    assert result["num_synthetic_iv"] >= 0
    assert result["num_fallback_iv"] >= 0
    for point in result["profile"]:
        assert point["iv_source"] in {"quote", "smile", "fallback", "unknown"}
        assert point["iv"] >= 0.0
