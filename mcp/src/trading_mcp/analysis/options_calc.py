"""Options position analysis: Greeks, payoff scenarios, recommendations."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from trading_mcp.config import RISK_FREE_RATE
from trading_mcp.data.provider import data_provider

def _fetch_chains_parallel(ticker: str, expiries: list[str]) -> dict[str, Any]:
    """Fetch multiple option chains via DataProvider (parallel, cached)."""
    chains: dict[str, Any] = {}

    # Fetch from DataProvider in parallel
    with ThreadPoolExecutor(max_workers=min(4, len(expiries))) as pool:
        future_map = {
            pool.submit(data_provider.get_options_chain, ticker, exp): exp
            for exp in expiries
        }
        for future in as_completed(future_map):
            exp = future_map[future]
            try:
                chain = future.result(timeout=30)
                if chain is not None:
                    chains[exp] = chain
            except Exception:
                raise

    return chains


class OptionLeg:
    """A single options leg in a multi-leg position."""

    def __init__(
        self,
        opt_type: str,
        strike: float,
        qty: int,
        entry: float,
        expiry: str | None = None,
    ):
        if opt_type.lower() not in ("call", "put"):
            raise ValueError(f"type must be 'call' or 'put', got '{opt_type}'")
        self.opt_type = opt_type.lower()
        self.strike = strike
        self.qty = qty
        self.entry = entry
        # Per-leg expiry (YYYY-MM-DD). None = fall back to the global expiry
        # passed to analyze_options_position. Enables multi-expiry positions
        # such as calendar spreads and diagonal spreads.
        self.expiry = expiry

    def side_label(self) -> str:
        side = "Long" if self.qty > 0 else "Short"
        return f"{side} {abs(self.qty)}x {self.opt_type.title()} {self.strike}"


def analyze_options_position(
    ticker: str,
    legs: list[dict[str, Any]],
    expiry: str | None = None,
) -> dict[str, Any]:
    """Analyze a multi-leg options position.

    Supports multi-expiry positions (calendar spreads, diagonals): each leg
    may carry its own optional ``expiry`` (YYYY-MM-DD). Per-leg expiry takes
    precedence over the global ``expiry`` parameter.

    Args:
        ticker: Stock ticker symbol.
        legs: List of leg dicts with keys: type, strike, qty, entry_premium.
              Each leg can optionally include "expiry" (YYYY-MM-DD) for
              multi-expiry positions (calendar spreads, diagonals). Falls
              back to the global expiry when omitted.
        expiry: Optional global target expiry (YYYY-MM-DD). Used for legs
                without per-leg expiry and as the payoff reference date.
    """
    info = data_provider.get_info(ticker)
    expirations = data_provider.get_options_expirations(ticker)
    spot = info.get("currentPrice", 0.0) if info else 0.0
    if spot == 0.0:
        try:
            hist = data_provider.get_hist(ticker, period="5d")
            if not hist.empty:
                spot = float(hist["Close"].iloc[-1])
        except Exception:
            pass

    if not expirations:
        return {"ticker": ticker, "error": "No options available"}

    if not expirations:
        return {"ticker": ticker, "error": "No options available"}

    # Parse legs, reading the optional per-leg "expiry" key.
    parsed_legs: list[OptionLeg] = []
    for leg_data in legs:
        leg_expiry = leg_data.get("expiry")
        if isinstance(leg_expiry, str) and leg_expiry.lower() in ("", "null", "none"):
            leg_expiry = None
        if leg_expiry is not None:
            leg_expiry = str(leg_expiry).strip()
        # Normalize compound type names: "long_call"/"short_put"/"Long Put" → "call"/"put"
        raw_type = str(leg_data["type"]).lower().replace(" ", "_")
        type_clean = raw_type.replace("long_", "").replace("short_", "")
        if type_clean in ("call", "put"):
            leg_type = type_clean
            leg_qty = int(leg_data["qty"])
            if raw_type.startswith("short_"):
                leg_qty = -abs(leg_qty)
            elif raw_type.startswith("long_"):
                leg_qty = abs(leg_qty)
        else:
            leg_type, leg_qty = raw_type, int(leg_data["qty"])
        parsed_legs.append(OptionLeg(
            leg_type,
            float(leg_data["strike"]),
            leg_qty,
            float(leg_data["entry_premium"]),
            expiry=leg_expiry,
        ))

    # Track whether global expiry was user-provided or auto-selected.
    was_provided = expiry is not None and str(expiry).lower() not in ("null", "none", "")

    # If any leg lacks both per-leg and global expiry, resolve an auto-selected
    # global fallback (nearest expiry >30 DTE) to feed those legs.
    global_resolved = expiry
    if global_resolved is None and any(l.expiry is None for l in parsed_legs):
        global_resolved = _select_expiry_opt(expirations, None)

    # Effective expiry per leg, snapped to an available chain expiration.
    eff_expiries: list[str] = []
    for leg in parsed_legs:
        eff = leg.expiry if leg.expiry else global_resolved
        eff_expiries.append(_select_expiry_opt(expirations, eff))

    # Group legs by effective expiry and fetch chains (parallel + cached).
    unique_expiries = sorted(set(eff_expiries))
    try:
        chains = _fetch_chains_parallel(ticker, unique_expiries)
    except Exception:
        return {"ticker": ticker, "error": f"Cannot fetch chain(s) for {ticker} expiry(s) {unique_expiries}"}

    # Payoff reference date: the global expiry if provided (it is the horizon
    # the caller cares about), otherwise the farthest leg expiry.
    if expiry is not None:
        payoff_expiry = _select_expiry_opt(expirations, expiry)
    else:
        payoff_expiry = unique_expiries[-1]
    payoff_tte = _time_to_expiry_opt(payoff_expiry)

    leg_results = []
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    cost_basis = 0.0
    current_value = 0.0
    # Per-leg IV, indexed by leg position, reused by the multi-expiry payoff.
    leg_iv: dict[int, float] = {}

    r = RISK_FREE_RATE

    for i, leg in enumerate(parsed_legs):
        eff = eff_expiries[i]
        chain = chains[eff]
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
        leg_iv[i] = iv

        # Greeks use THIS leg's own DTE (today -> leg effective expiry).
        leg_tte = _time_to_expiry_opt(eff)
        greeks_result = _bs_greeks(spot, leg.strike, leg_tte, r, iv, leg.opt_type)

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
            "expiry": eff,
            "dte": int(leg_tte * 365),
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

    payoff, breakevens = _compute_payoff(
        parsed_legs, spot, r, payoff_expiry, eff_expiries, leg_iv
    )
    probabilities = _compute_probabilities(
        parsed_legs, spot, r, payoff_expiry, eff_expiries, leg_iv
    )

    strategy_name = _classify_strategy(parsed_legs)

    recommendations = _generate_recommendations(
        parsed_legs, total_pnl, spot, payoff, strategy_name
    )

    result: dict[str, Any] = {
        "ticker": ticker,
        "underlying_price": round(spot, 2),
        "expiry": payoff_expiry,
        "dte": int(payoff_tte * 365),
        "leg_expiries": unique_expiries,
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

    # Warning: global expiry auto-selected and actually used by at least one leg
    used_auto = not was_provided and any(l.expiry is None for l in parsed_legs)
    if used_auto:
        result["warning"] = (
            f"Global expiry auto-selected: {payoff_expiry} ({payoff_tte*365:.0f} DTE). "
            "Pass expiry='YYYY-MM-DD' for accurate Greeks. "
            "Legs without per-leg expiry use this global value."
        )
    elif len(unique_expiries) > 1:
        result["warning"] = (
            f"Multi-expiry position: {len(unique_expiries)} distinct expiries "
            f"({', '.join(unique_expiries)}). Greeks are computed per-leg using "
            "each leg's own DTE. Payoff is evaluated at the global/farthest "
            f"expiry ({payoff_expiry}): expired legs use intrinsic value, "
            "live legs use the Black-Scholes theoretical price."
        )

    return result


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


def _bs_price(
    spot: float, strike: float, tte: float, r: float, sigma: float, opt_type: str
) -> float:
    """Black-Scholes theoretical option price."""
    if tte <= 0 or sigma <= 0:
        return max(0.0, (spot - strike) if opt_type == "call" else (strike - spot))
    sqrt_t = math.sqrt(tte)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * tte) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if opt_type == "call":
        return spot * norm.cdf(d1) - strike * math.exp(-r * tte) * norm.cdf(d2)
    return strike * math.exp(-r * tte) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def _leg_value_at(
    price: float,
    leg: OptionLeg,
    leg_eff_expiry: str,
    payoff_date: date,
    iv: float,
    r: float,
) -> float:
    """Value of a single leg at ``price`` on the payoff date.

    Legs that have already expired by the payoff date settle to intrinsic
    value. Legs that are still alive are valued with the Black-Scholes
    theoretical price using the remaining time to the leg's own expiry.
    """
    leg_exp_date = datetime.strptime(leg_eff_expiry, "%Y-%m-%d").date()
    if leg_exp_date <= payoff_date:
        return max(0.0, (price - leg.strike)
                   if leg.opt_type == "call" else (leg.strike - price))
    remaining_days = max((leg_exp_date - payoff_date).days, 1)
    remaining_tte = remaining_days / 365.0
    return _bs_price(price, leg.strike, remaining_tte, r, iv, leg.opt_type)


def _compute_payoff(
    legs: list[OptionLeg],
    spot: float,
    r: float,
    payoff_expiry: str,
    eff_expiries: list[str],
    leg_iv: dict[int, float],
) -> tuple[list[dict], list[float]]:
    points = np.linspace(spot * 0.5, spot * 1.5, 100)
    breakevens: list[float] = []
    payoff_date = datetime.strptime(payoff_expiry, "%Y-%m-%d").date()

    payoffs = []

    for price in points:
        pnl = 0.0
        for i, leg in enumerate(legs):
            iv = leg_iv.get(i, 0.3)
            value = _leg_value_at(float(price), leg, eff_expiries[i], payoff_date, iv, r)
            pnl += (value - leg.entry) * leg.qty * 100

        payoff_type = "normal"
        if abs(pnl) < 0.01 * spot * 100:
            payoff_type = "breakeven"
            breakevens.append(round(float(price), 2))

        payoffs.append({
            "price": round(float(price), 2),
            "pnl": round(float(pnl), 2),
            "type": payoff_type,
        })

    return payoffs, sorted(set(breakevens))[:10]


def _compute_probabilities(
    legs: list[OptionLeg],
    spot: float,
    r: float,
    payoff_expiry: str,
    eff_expiries: list[str],
    leg_iv: dict[int, float],
) -> dict[str, float]:
    sigma = 0.30
    tte = _time_to_expiry_opt(payoff_expiry)
    dr = (r - 0.5 * sigma ** 2) * tte
    vol = sigma * math.sqrt(tte)
    payoff_date = datetime.strptime(payoff_expiry, "%Y-%m-%d").date()

    profit_count = 0
    max_profit_count = 0
    total = 5000
    max_pnl = -1e9

    for _ in range(total):
        z = float(np.random.normal(0, 1))
        price = spot * math.exp(dr + vol * z)
        pnl = 0.0
        for i, leg in enumerate(legs):
            iv = leg_iv.get(i, 0.3)
            value = _leg_value_at(price, leg, eff_expiries[i], payoff_date, iv, r)
            pnl += (value - leg.entry) * leg.qty * 100

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
