"""Options position analysis: Greeks, payoff scenarios, recommendations."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

from trading_mcp.config import RISK_FREE_RATE


class OptionLeg:
    """A single options leg in a multi-leg position."""

    def __init__(self, opt_type: str, strike: float, qty: int, entry: float):
        if opt_type.lower() not in ("call", "put"):
            raise ValueError(f"type must be 'call' or 'put', got '{opt_type}'")
        self.opt_type = opt_type.lower()
        self.strike = strike
        self.qty = qty
        self.entry = entry

    def side_label(self) -> str:
        side = "Long" if self.qty > 0 else "Short"
        return f"{side} {abs(self.qty)}x {self.opt_type.title()} {self.strike}"


def analyze_options_position(
    ticker: str,
    legs: list[dict[str, Any]],
    expiry: str | None = None,
) -> dict[str, Any]:
    """Analyze a multi-leg options position.

    Args:
        ticker: Stock ticker symbol.
        legs: List of leg dicts with keys: type, strike, qty, entry_premium.
        expiry: Optional target expiry (YYYY-MM-DD).
    """
    t = yf.Ticker(ticker)
    info = t.info or {}
    spot = info.get("currentPrice", 0.0)
    if spot == 0.0:
        hist = t.history(period="5d")
        if not hist.empty:
            spot = float(hist["Close"].iloc[-1])

    try:
        expirations = list(t.options)
    except Exception:
        return {"ticker": ticker, "error": "No options available"}

    if not expirations:
        return {"ticker": ticker, "error": "No options available"}

    selected_expiry = _select_expiry_opt(expirations, expiry)
    tte = _time_to_expiry_opt(selected_expiry)

    parsed_legs: list[OptionLeg] = []
    for leg_data in legs:
        parsed_legs.append(OptionLeg(
            str(leg_data["type"]),
            float(leg_data["strike"]),
            int(leg_data["qty"]),
            float(leg_data["entry_premium"]),
        ))

    try:
        chain = t.option_chain(selected_expiry)
    except Exception:
        return {"ticker": ticker, "error": f"Cannot fetch chain for {selected_expiry}"}

    leg_results = []
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    cost_basis = 0.0
    current_value = 0.0

    r = RISK_FREE_RATE

    for leg in parsed_legs:
        df = chain.calls if leg.opt_type == "call" else chain.puts
        row = df[df["strike"] == leg.strike]
        if row.empty:
            continue

        row_data = row.iloc[0]
        bid = float(row_data.get("bid", 0) or 0)
        ask = float(row_data.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if (bid + ask) > 0 else float(row_data.get("lastPrice", 0) or 0)
        iv = row_data.get("impliedVolatility", 0.3) or 0.3
        iv = float(iv)

        greeks_result = _bs_greeks(spot, leg.strike, tte, r, iv, leg.opt_type)

        pnl_per = (mid - leg.entry) * abs(leg.qty) * 100
        cost_leg = leg.entry * abs(leg.qty) * 100
        current_leg = mid * abs(leg.qty) * 100

        cost_basis += cost_leg
        current_value += current_leg

        leg_results.append({
            "side": "Long" if leg.qty > 0 else "Short",
            "type": leg.opt_type,
            "strike": leg.strike,
            "qty": leg.qty,
            "entry_premium": leg.entry,
            "current_premium": round(mid, 4),
            "pnl_per_unit": round(mid - leg.entry, 2),
            "pnl": round(pnl_per, 2),
            "delta": round(greeks_result["delta"] * leg.qty, 4),
            "gamma": round(greeks_result["gamma"] * leg.qty, 4),
            "theta": round(greeks_result["theta"] * leg.qty, 4),
            "vega": round(greeks_result["vega"] * leg.qty, 4),
        })

        total_delta += greeks_result["delta"] * leg.qty
        total_gamma += greeks_result["gamma"] * leg.qty
        total_theta += greeks_result["theta"] * leg.qty
        total_vega += greeks_result["vega"] * leg.qty

    total_pnl = current_value - cost_basis

    payoff, breakevens = _compute_payoff(parsed_legs, spot, tte, r)
    probabilities = _compute_probabilities(parsed_legs, spot, tte, r)

    strategy_name = _classify_strategy(parsed_legs)

    recommendations = _generate_recommendations(
        parsed_legs, total_pnl, spot, payoff, strategy_name
    )

    return {
        "ticker": ticker,
        "underlying_price": round(spot, 2),
        "expiry": selected_expiry,
        "dte": int(tte * 365),
        "strategy_classification": strategy_name,
        "legs": leg_results,
        "position_greeks": {
            "total_delta": round(total_delta, 4),
            "total_gamma": round(total_gamma, 4),
            "total_theta": round(total_theta, 4),
            "total_vega": round(total_vega, 4),
        },
        "pnl": {
            "cost_basis": round(cost_basis, 2),
            "current_value": round(current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / cost_basis * 100, 1) if cost_basis > 0 else 0.0,
        },
        "payoff_scenarios": payoff,
        "breakevens": breakevens,
        "probabilities": probabilities,
        "recommendations": recommendations,
    }


def _bs_greeks(
    spot: float, strike: float, tte: float, r: float, sigma: float, opt_type: str
) -> dict[str, float]:
    sqrt_t = math.sqrt(max(tte, 0.001))
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * tte) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t

    if opt_type == "call":
        delta = norm.cdf(d1)
        theta = (
            -spot * norm.pdf(d1) * sigma / (2 * sqrt_t)
            - r * strike * math.exp(-r * tte) * norm.cdf(d2)
        ) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (
            -spot * norm.pdf(d1) * sigma / (2 * sqrt_t)
            + r * strike * math.exp(-r * tte) * norm.cdf(-d2)
        ) / 365

    gamma = norm.pdf(d1) / (spot * sigma * sqrt_t)
    vega = spot * norm.pdf(d1) * sqrt_t / 100

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def _compute_payoff(
    legs: list[OptionLeg], spot: float, tte: float, r: float
) -> tuple[list[dict], list[float]]:
    points = np.linspace(spot * 0.5, spot * 1.5, 100)
    breakevens: list[float] = []

    payoffs = []
    prev_pnl: float | None = None

    for price in points:
        pnl = 0.0
        for leg in legs:
            intrinsic = max(0.0, (price - leg.strike) if leg.opt_type == "call" else (leg.strike - price))
            pnl += (intrinsic - leg.entry) * leg.qty * 100

        payoff_type = "normal"
        if abs(pnl) < 0.01 * spot * 100:
            payoff_type = "breakeven"
            breakevens.append(round(float(price), 2))

        payoffs.append({
            "price": round(float(price), 2),
            "pnl": round(float(pnl), 2),
            "type": payoff_type,
        })

        prev_pnl = pnl

    return payoffs, sorted(set(breakevens))[:10]


def _compute_probabilities(
    legs: list[OptionLeg], spot: float, tte: float, r: float
) -> dict[str, float]:
    sigma = 0.30
    dr = (r - 0.5 * sigma ** 2) * tte
    vol = sigma * math.sqrt(tte)

    profit_count = 0
    max_profit_count = 0
    total = 5000
    max_pnl = -1e9

    for _ in range(total):
        z = float(np.random.normal(0, 1))
        price = spot * math.exp(dr + vol * z)
        pnl = 0.0
        for leg in legs:
            intrinsic = max(0.0, (price - leg.strike) if leg.opt_type == "call" else (leg.strike - price))
            pnl += (intrinsic - leg.entry) * leg.qty * 100

        if pnl > 0:
            profit_count += 1
        if pnl > max_pnl:
            max_pnl = pnl
            max_profit_count = 1
        elif abs(pnl - max_pnl) < 0.01:
            max_profit_count += 1

    return {
        "itm_prob": 0.0,
        "otm_prob": 0.0,
        "profit_prob": round(profit_count / total, 3),
        "max_profit_prob": round(max_profit_count / total, 3),
    }


def _classify_strategy(legs: list[OptionLeg]) -> str:
    calls_long = sum(1 for l in legs if l.opt_type == "call" and l.qty > 0)
    calls_short = sum(1 for l in legs if l.opt_type == "call" and l.qty < 0)
    puts_long = sum(1 for l in legs if l.opt_type == "put" and l.qty > 0)
    puts_short = sum(1 for l in legs if l.opt_type == "put" and l.qty < 0)

    if calls_long == 1 and puts_short == 2 and calls_short == 0 and puts_long == 0:
        return "Synthetic Long 2:1"
    if calls_long == 1 and calls_short == 0 and puts_long == 0 and puts_short == 0:
        return "Long Call"
    if puts_long == 1 and calls_long == 0 and calls_short == 0 and puts_short == 0:
        return "Long Put"
    if calls_short == 1 and calls_long == 0 and puts_long == 0 and puts_short == 0:
        return "Short Call"
    if puts_short > 0 and puts_long == 0 and calls_long == 0 and calls_short == 0:
        return "Short Put(s)"
    if calls_short >= 1 and puts_short >= 1:
        if calls_long == 0 and puts_long == 0:
            return "Short Strangle" if calls_short == 1 and puts_short == 1 else "Multi-Leg Short"
    if calls_long == 1 and calls_short == 1:
        return "Bull Call Spread" if calls_long > 0 else "Bear Call Spread"
    if puts_long == 1 and puts_short == 1:
        return "Bull Put Spread" if puts_short > 0 else "Bear Put Spread"
    return "Custom Multi-Leg"


def _generate_recommendations(
    legs: list[OptionLeg],
    total_pnl: float,
    spot: float,
    payoff: list[dict],
    strategy_name: str,
) -> list[dict[str, str]]:
    recs = []
    breakevens_list = [s["price"] for s in payoff if s["type"] == "breakeven"]

    if total_pnl > 0:
        recs.append({"type": "Consider", "reason": "Position is profitable. Consider taking partial profits."})
    elif total_pnl < 0:
        recs.append({"type": "Monitor", "reason": "Position underwater. Check invalidation conditions."})

    if breakevens_list:
        recs.append({"type": "Target", "reason": f"Nearest breakeven: ${min(breakevens_list):.2f}"})

    recs.append({"type": "Strategy", "reason": f"Classified as: {strategy_name}"})

    return recs


def _select_expiry_opt(expirations: list[str], target: str | None) -> str:
    today = date.today()
    parsed = [datetime.strptime(e, "%Y-%m-%d").date() for e in expirations]

    if target:
        target_date = datetime.strptime(target, "%Y-%m-%d").date()
        if target_date in parsed:
            return target
        closest = min(parsed, key=lambda d: abs((d - target_date).days))
        return closest.strftime("%Y-%m-%d")

    future = [d for d in parsed if d > today]
    if not future:
        return max(parsed).strftime("%Y-%m-%d")
    far_enough = [d for d in future if (d - today).days > 30]
    if far_enough:
        return min(far_enough).strftime("%Y-%m-%d")
    return min(future).strftime("%Y-%m-%d")


def _time_to_expiry_opt(expiry_str: str) -> float:
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = date.today()
    days = (expiry_date - today).days
    return max(days, 1) / 365.0
