"""Options position analysis: Greeks, payoff scenarios, recommendations."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from trading_mcp.data.provider import data_provider
from trading_mcp.data.risk_free import get_risk_free_rate

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

    rate_snapshot = get_risk_free_rate()
    r = rate_snapshot.value
    # Continuous dividend yield (Merton extension). yfinance reports a
    # fractional yield (0.0155 == 1.55%); other backends may omit it.
    _div = info.get("dividendYield") if info else None
    q = float(_div) if isinstance(_div, (int, float)) and 0.0 <= float(_div) < 1.0 else 0.0

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

        # Realistic exit mark: long legs exit at the bid, short legs are
        # closed by paying the ask. Fall back to the mid when a quote is missing.
        if leg.qty > 0 and bid > 0:
            mark_exec = bid
        elif leg.qty < 0 and ask > 0:
            mark_exec = ask
        else:
            mark_exec = mid

        # Greeks use THIS leg's own DTE (today -> leg effective expiry).
        leg_tte = _time_to_expiry_opt(eff)
        greeks_result = _bs_greeks(spot, leg.strike, leg_tte, r, iv, leg.opt_type, q)

        # Signed by position direction: a short leg loses when the mark rises.
        pnl_per_unit = (mark_exec - leg.entry) * (1.0 if leg.qty > 0 else -1.0)
        pnl_per = pnl_per_unit * abs(leg.qty) * 100.0
        cost_leg = leg.entry * leg.qty * 100.0
        current_leg = mark_exec * leg.qty * 100.0

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
            "bid": round(bid, 4),
            "ask": round(ask, 4),
            "current_premium": round(mid, 4),
            "exit_mark": round(mark_exec, 4),
            "pnl_per_unit": round(pnl_per_unit, 2),
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

    # ── P2: estimated trading costs ────────────────────────────────
    n_legs = len(parsed_legs)
    commission_per_contract = 0.65
    slippage_premium_bps = 5.0
    estimated_commissions = n_legs * commission_per_contract * sum(
        abs(l.qty) for l in parsed_legs
    )
    estimated_slippage = abs(cost_basis) * (slippage_premium_bps / 10000.0)
    estimated_total_costs = estimated_commissions + estimated_slippage
    pnl_net_estimate = total_pnl - estimated_total_costs

    estimated_costs_dict = {
        "commission_per_contract": commission_per_contract,
        "commissions_total": round(estimated_commissions, 2),
        "slippage_bps": slippage_premium_bps,
        "slippage_total": round(estimated_slippage, 2),
        "total_estimated_costs": round(estimated_total_costs, 2),
        "pnl_net_estimate": round(pnl_net_estimate, 2),
        "note": (
            "Costs are estimates based on typical retail rates. Actual "
            "costs depend on execution quality, market conditions, and "
            "broker-specific fees. pnl_net_estimate is informative, not "
            "exact — gross P&L is always preserved in pnl.total_pnl."
        ),
    }

    payoff, breakevens = _compute_payoff(
        parsed_legs, spot, r, payoff_expiry, eff_expiries, leg_iv, q=q
    )
    probabilities = _compute_probabilities(
        parsed_legs, spot, r, payoff_expiry, eff_expiries, leg_iv,
        payoff=payoff, q=q,
    )

    strategy_name = _classify_strategy(parsed_legs)

    recommendations = _generate_recommendations(
        parsed_legs, total_pnl, spot, strategy_name, breakevens
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
            "total_pnl_pct": round(total_pnl / abs(cost_basis) * 100, 1) if cost_basis != 0 else 0.0,
        },
        "estimated_costs": estimated_costs_dict,
        "payoff_scenarios": payoff,
        "breakevens": breakevens,
        "probabilities": probabilities,
        "recommendations": recommendations,
        "risk_free_rate": {
            "value": round(r, 6),
            "source": rate_snapshot.source_ticker,
            "as_of": rate_snapshot.as_of,
            "is_live": rate_snapshot.is_live,
            "fallback_reason": rate_snapshot.fallback_reason,
        },
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


def _bs_greeks(  # pylint: disable=too-many-positional-arguments
    spot: float,
    strike: float,
    tte: float,
    r: float,
    sigma: float,
    opt_type: str,
    q: float = 0.0,
) -> dict[str, float]:
    """Merton (dividend-adjusted) Black-Scholes Greeks."""
    sqrt_t = math.sqrt(max(tte, 0.001))
    d1 = (
        math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * tte
    ) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_q = math.exp(-q * tte)
    disc_r = math.exp(-r * tte)

    if opt_type == "call":
        delta = disc_q * norm.cdf(d1)
        theta = (
            -spot * disc_q * norm.pdf(d1) * sigma / (2 * sqrt_t)
            - r * strike * disc_r * norm.cdf(d2)
            + q * spot * disc_q * norm.cdf(d1)
        ) / 365
    else:
        delta = -disc_q * norm.cdf(-d1)
        theta = (
            -spot * disc_q * norm.pdf(d1) * sigma / (2 * sqrt_t)
            + r * strike * disc_r * norm.cdf(-d2)
            - q * spot * disc_q * norm.cdf(-d1)
        ) / 365

    gamma = disc_q * norm.pdf(d1) / (spot * sigma * sqrt_t)
    vega = spot * disc_q * norm.pdf(d1) * sqrt_t / 100

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def _bs_price(  # pylint: disable=too-many-positional-arguments
    spot: float,
    strike: float,
    tte: float,
    r: float,
    sigma: float,
    opt_type: str,
    q: float = 0.0,
) -> float:
    """Merton (dividend-adjusted) Black-Scholes theoretical option price."""
    if tte <= 0 or sigma <= 0:
        return max(0.0, (spot - strike) if opt_type == "call" else (strike - spot))
    sqrt_t = math.sqrt(tte)
    d1 = (
        math.log(spot / strike) + (r - q + 0.5 * sigma ** 2) * tte
    ) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc_q = math.exp(-q * tte)
    disc_r = math.exp(-r * tte)
    if opt_type == "call":
        return spot * disc_q * norm.cdf(d1) - strike * disc_r * norm.cdf(d2)
    return strike * disc_r * norm.cdf(-d2) - spot * disc_q * norm.cdf(-d1)


def _leg_value_at(  # pylint: disable=too-many-positional-arguments
    price: float,
    leg: OptionLeg,
    leg_eff_expiry: str,
    payoff_date: date,
    iv: float,
    r: float,
    q: float = 0.0,
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
    return _bs_price(price, leg.strike, remaining_tte, r, iv, leg.opt_type, q)


def _position_pnl_at(  # pylint: disable=too-many-positional-arguments
    price: float,
    legs: list[OptionLeg],
    eff_expiries: list[str],
    leg_iv: dict[int, float],
    payoff_date: date,
    r: float,
    q: float = 0.0,
) -> float:
    """Signed position P&L at one terminal ``price`` on the payoff date."""
    pnl = 0.0
    for i, leg in enumerate(legs):
        iv = leg_iv.get(i, 0.3)
        value = _leg_value_at(price, leg, eff_expiries[i], payoff_date, iv, r, q)
        pnl += (value - leg.entry) * leg.qty * 100
    return pnl


def _compute_payoff(  # pylint: disable=too-many-positional-arguments
    legs: list[OptionLeg],
    spot: float,
    r: float,
    payoff_expiry: str,
    eff_expiries: list[str],
    leg_iv: dict[int, float],
    q: float = 0.0,
) -> tuple[list[dict], list[float]]:
    points = np.linspace(spot * 0.5, spot * 1.5, 100)
    payoff_date = datetime.strptime(payoff_expiry, "%Y-%m-%d").date()

    raw: list[tuple[float, float]] = []
    payoffs = []
    for price in points:
        pnl = _position_pnl_at(
            float(price), legs, eff_expiries, leg_iv, payoff_date, r, q
        )
        raw.append((float(price), pnl))
        payoffs.append({
            "price": round(float(price), 2),
            "pnl": round(float(pnl), 2),
            "type": "normal",
        })

    # Break-evens come from zero crossings of the payoff curve, interpolated
    # linearly between adjacent grid points. No absolute tolerance: a fixed
    # dollar band mislabels every point of a small-max-profit spread as BE.
    breakevens: list[float] = []
    for (x0, y0), (x1, y1) in zip(raw, raw[1:]):
        if y0 == 0.0:
            breakevens.append(x0)
        elif (y0 < 0.0) != (y1 < 0.0) and y1 != y0:
            breakevens.append(x0 - y0 * (x1 - x0) / (y1 - y0))
    if raw and raw[-1][1] == 0.0:
        breakevens.append(raw[-1][0])

    return payoffs, sorted({round(be, 2) for be in breakevens})[:10]


def _compute_probabilities(  # pylint: disable=too-many-positional-arguments
    legs: list[OptionLeg],
    spot: float,
    r: float,
    payoff_expiry: str,
    eff_expiries: list[str],
    leg_iv: dict[int, float],
    payoff: list[dict] | None = None,
    q: float = 0.0,
) -> dict[str, float | bool]:
    """Terminal-distribution probabilities driven by the position's own IV.

    The diffusion uses the quantity-weighted average leg IV (not a hardcoded
    30%), so the simulated dispersion matches the market. ``max_profit_prob``
    is the share of terminal prices landing on the achievable-profit plateau;
    unlimited-profit/loss profiles are flagged instead of reporting 0%.
    """
    tte = _time_to_expiry_opt(payoff_expiry)

    weights = [(abs(leg.qty), float(leg_iv.get(i, 0.30))) for i, leg in enumerate(legs)]
    tot_w = sum(w for w, _ in weights)
    sigma = (sum(w * s for w, s in weights) / tot_w) if tot_w > 0 else 0.30
    sigma = max(sigma, 0.01)

    dr = (r - q - 0.5 * sigma ** 2) * tte
    vol = sigma * math.sqrt(tte)
    payoff_date = datetime.strptime(payoff_expiry, "%Y-%m-%d").date()

    # Achievable-profit plateau from the payoff grid.
    max_pnl: float | None = None
    if payoff:
        max_pnl = max(point["pnl"] for point in payoff)
    # "Unbounded" means the curve is still rising at the grid edge, not merely
    # flat there: a capped-profit plateau (short put) is bounded.
    unbounded_up = bool(
        payoff and len(payoff) >= 2
        and max_pnl is not None
        and payoff[-1]["pnl"] >= max_pnl - 1.0
        and (payoff[-1]["pnl"] - payoff[-2]["pnl"]) > 1.0
    )
    unbounded_down = bool(
        payoff and len(payoff) >= 2
        and max_pnl is not None
        and payoff[0]["pnl"] >= max_pnl - 1.0
        and (payoff[0]["pnl"] - payoff[1]["pnl"]) > 1.0
    )

    rng = np.random.default_rng(7)
    profit_count = 0
    max_profit_count = 0
    total = 5000
    plateau_tol = 1.0

    for _ in range(total):
        z = float(rng.normal(0.0, 1.0))
        price = spot * math.exp(dr + vol * z)
        pnl = 0.0
        for i, leg in enumerate(legs):
            iv = leg_iv.get(i, 0.3)
            value = _leg_value_at(price, leg, eff_expiries[i], payoff_date, iv, r, q)
            pnl += (value - leg.entry) * leg.qty * 100

        if pnl > 0:
            profit_count += 1
        if max_pnl is not None and pnl >= max_pnl - plateau_tol:
            max_profit_count += 1

    profit_prob = profit_count / total
    if max_pnl is None or unbounded_up or unbounded_down:
        # No finite maximum (long call, short put): the meaningful analog of
        # "keeps the max profit" is simply "finishes in profit".
        max_profit_prob = profit_prob
    else:
        max_profit_prob = max_profit_count / total

    # Unbounded *loss* profiles (naked short call / short put).
    loss_unbounded = False
    if payoff and len(payoff) >= 3:
        right_falling = payoff[-1]["pnl"] < payoff[-2]["pnl"]
        left_falling = payoff[0]["pnl"] < payoff[1]["pnl"]
        loss_unbounded = (right_falling and payoff[-1]["pnl"] < payoff[0]["pnl"]) or (
            left_falling and payoff[0]["pnl"] < payoff[-1]["pnl"]
        )

    # Analytic ITM probability of the dominant leg (largest |qty|).
    itm_prob = 0.0
    if legs:
        main_idx = max(range(len(legs)), key=lambda i: abs(legs[i].qty))
        main = legs[main_idx]
        s_main = max(float(leg_iv.get(main_idx, sigma)), 0.01)
        sq = s_main * math.sqrt(tte)
        if sq > 0 and main.strike > 0 and spot > 0:
            d1 = (
                math.log(spot / main.strike) + (r - q + 0.5 * s_main ** 2) * tte
            ) / sq
            d2 = d1 - sq
            itm_prob = float(
                norm.cdf(d2) if main.opt_type == "call" else norm.cdf(-d2)
            )
    itm_prob = min(max(itm_prob, 0.0), 1.0)

    return {
        "itm_prob": round(itm_prob, 3),
        "otm_prob": round(1.0 - itm_prob, 3),
        "profit_prob": round(profit_prob, 3),
        "max_profit_prob": round(max_profit_prob, 3),
        "max_profit_unbounded": unbounded_up or unbounded_down,
        "max_loss_unbounded": loss_unbounded,
    }


def _classify_strategy(legs: list[OptionLeg]) -> str:
    calls_long = [leg for leg in legs if leg.opt_type == "call" and leg.qty > 0]
    calls_short = [leg for leg in legs if leg.opt_type == "call" and leg.qty < 0]
    puts_long = [leg for leg in legs if leg.opt_type == "put" and leg.qty > 0]
    puts_short = [leg for leg in legs if leg.opt_type == "put" and leg.qty < 0]

    n_cl, n_cs = len(calls_long), len(calls_short)
    n_pl, n_ps = len(puts_long), len(puts_short)

    if n_cl == 1 and n_ps == 2 and n_cs == 0 and n_pl == 0:
        return "Synthetic Long 2:1"
    if n_cl == 1 and n_cs == 0 and n_pl == 0 and n_ps == 0:
        return "Long Call"
    if n_pl == 1 and n_cl == 0 and n_cs == 0 and n_ps == 0:
        return "Long Put"
    if n_cs == 1 and n_cl == 0 and n_pl == 0 and n_ps == 0:
        return "Short Call"
    if n_ps > 0 and n_pl == 0 and n_cl == 0 and n_cs == 0:
        return "Short Put(s)"

    # Vertical spreads: the strike order decides bull vs bear.
    if n_cl == 1 and n_cs == 1 and n_pl == 0 and n_ps == 0:
        return (
            "Bull Call Spread"
            if calls_long[0].strike < calls_short[0].strike
            else "Bear Call Spread"
        )
    if n_pl == 1 and n_ps == 1 and n_cl == 0 and n_cs == 0:
        return (
            "Bull Put Spread"
            if puts_short[0].strike > puts_long[0].strike
            else "Bear Put Spread"
        )

    # Volatility structures.
    if n_cl == 1 and n_pl == 1 and n_cs == 0 and n_ps == 0:
        return (
            "Long Straddle"
            if calls_long[0].strike == puts_long[0].strike
            else "Long Strangle"
        )
    if n_cl == 2 and n_pl == 1 and n_cs == 0 and n_ps == 0:
        return "Call Butterfly"
    if n_pl == 2 and n_cl == 1 and n_cs == 0 and n_ps == 0:
        return "Put Butterfly"
    if n_cl == 1 and n_pl == 1 and n_ps == 1 and n_cs == 1:
        return "Iron Condor" if _has_four_distinct_strikes(legs) else "Iron Butterfly"

    if n_cs >= 1 and n_ps >= 1:
        if n_cl == 0 and n_pl == 0:
            return (
                "Short Strangle"
                if n_cs == 1 and n_ps == 1
                else "Multi-Leg Short"
            )

    return "Custom Multi-Leg"


def _has_four_distinct_strikes(legs: list[OptionLeg]) -> bool:
    return len({leg.strike for leg in legs}) >= 4


def _generate_recommendations(  # pylint: disable=too-many-positional-arguments
    legs: list[OptionLeg],
    total_pnl: float,
    spot: float,
    strategy_name: str,
    breakevens: list[float],
) -> list[dict[str, str]]:
    recs = []

    if total_pnl > 0:
        recs.append({"type": "Consider", "reason": "Position is profitable. Consider taking partial profits."})
    elif total_pnl < 0:
        recs.append({"type": "Monitor", "reason": "Position underwater. Check invalidation conditions."})

    if breakevens:
        nearest = min(breakevens, key=lambda level: abs(level - spot))
        recs.append({"type": "Target", "reason": f"Nearest breakeven: ${nearest:.2f}"})

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
