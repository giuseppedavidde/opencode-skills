"""Multi-leg options position analysis: marks, model Greeks, payoff, probabilities, scenarios.

Rules (inputs come from :mod:`trading_mcp.analysis.options_market`):

1. Every leg needs a listed expiry and a listed strike. A missing strike, an
   unlisted expiry or an expired leg fails the analysis with the list of the
   bad legs; no leg is dropped and no expiry is snapped.
2. The horizon is the earliest leg expiry. Legs that expire then settle at
   their intrinsic value; later legs are valued with the model (their own IV,
   tenor rate and dividends). A global ``expiry`` that no leg uses must not be
   later than the earliest leg expiry; an earlier one moves the horizon there.
3. The spot comes from the quote layer and must pass the 60-second rule of
   the regular session. A long leg closes at the bid (a zero bid is worth 0),
   a short leg at the ask. Without a two-sided quote the mark is ``None`` and
   the P&L of the leg, and of the position, is blocked (``pnl_blocked``).
4. Leg IV is solved from the mid with the contract model (American BBSR tree
   or European closed form, own rate and dividends). When the quote gives no
   IV, the smile IV of the strike is used and tagged. Only finite IVs in
   ``(0.01, 5)`` are used; vendor IV is a cross-check only.
5. Probabilities are risk-neutral (``measure = "risk_neutral"``), from the
   smile of the horizon expiry (Breeden-Litzenberger), else lognormal at the
   ATM IV. They do not depend on the leg order.
6. Greeks are model Greeks per share for each leg; position Greeks are in
   shares and dollars (see ``units``).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
from scipy.special import ndtr

from trading_mcp.analysis import event_risk, iv_surface, liquidity, options_market, pricing
from trading_mcp.analysis.options_market import MarketContext, build_context, check_spot, load_chains
from trading_mcp.data import market_calendar as mcal
from trading_mcp.timeutil import iso, utc_now

COMMISSION_PER_CONTRACT = 0.65
SHORT_DELTA_ALERT = 0.30
MANAGEMENT_DTE = 21.0
PIN_DAYS = 3.0
_GRID_POINTS = 801
_OUTPUT_POINTS = 41

POSITION_UNITS: dict[str, str] = {
    "delta_shares": "share-equivalent delta of the position (sum of delta x qty x multiplier)",
    "delta_dollars": "delta_shares x spot: $ exposure equivalent to stock",
    "gamma_shares_per_dollar": "change of delta_shares for a $1 move",
    "gamma_dollars_per_1pct": "change of delta_dollars for a 1% move (gamma x qty x mult x S^2 x 0.01)",
    "theta_dollars_per_day": "$ value change of the position when one calendar day passes",
    "vega_dollars_per_vol_point": "$ value change for +1 vol point (0.01) on every leg",
    "rho_dollars_per_rate_point": "$ value change for +1 rate point (0.01)",
    "vanna_shares_per_vol_point": "change of delta_shares for +1 vol point",
    "charm_shares_per_day": "change of delta_shares when one calendar day passes",
    "vomma_dollars_per_vol_point": "change of vega_dollars_per_vol_point for +1 vol point",
    "pnl": "$ per position (premium x qty x multiplier)",
    "premium": "$ per share",
    "iv": "decimal (0.25 = 25%)",
    "probabilities": "risk-neutral, 0-1",
}


class LegInput:
    """A validated input leg."""

    def __init__(self, index: int, opt_type: str, strike: float, qty: int, entry: float,
                 expiry: str | None) -> None:
        self.index = index
        self.opt_type = opt_type
        self.strike = strike
        self.qty = qty
        self.entry = entry
        self.expiry = expiry
        self.eff_expiry: str = expiry or ""

    @property
    def is_call(self) -> bool:
        """True for a call."""
        return self.opt_type == "call"

    def label(self) -> str:
        """Readable leg name."""
        side = "Long" if self.qty > 0 else "Short"
        return f"{side} {abs(self.qty)}x {self.opt_type.title()} {self.strike:g} {self.eff_expiry}".strip()


def _fail(ticker: str, message: str, *, retryable: bool = False, **extra: Any) -> dict[str, Any]:
    payload = {"ticker": ticker, "error": message, "error_kind": "blocking", "error_retryable": retryable,
               "degraded": True, "data_source": "options"}
    payload.update(extra)
    return payload


def _clean_expiry(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in ("", "null", "none"):
        return None
    return text[:10]


def parse_legs(raw_legs: list[dict[str, Any]] | None) -> tuple[list[LegInput], list[dict[str, Any]]]:
    """Validate the input legs. Returns ``(legs, errors)``; nothing is dropped silently."""
    legs: list[LegInput] = []
    errors: list[dict[str, Any]] = []
    if not raw_legs:
        return legs, [{"leg": None, "reason": "no legs given"}]
    for index, raw in enumerate(raw_legs):
        if not isinstance(raw, dict):
            errors.append({"leg": index, "reason": "leg is not an object"})
            continue
        kind = str(raw.get("type", "")).strip().lower().replace(" ", "_").replace("-", "_")
        sign = 0
        if kind.startswith("long_"):
            kind, sign = kind[5:], 1
        elif kind.startswith("short_"):
            kind, sign = kind[6:], -1
        kind = {"c": "call", "calls": "call", "p": "put", "puts": "put"}.get(kind, kind)
        if kind not in ("call", "put"):
            errors.append({"leg": index, "reason": f"type must be call or put, got {raw.get('type')!r}"})
            continue
        try:
            strike = float(raw.get("strike"))
            qty_value = float(raw.get("qty"))
            entry = float(raw.get("entry_premium"))
        except (TypeError, ValueError):
            errors.append({"leg": index, "reason": "strike, qty and entry_premium must be numbers"})
            continue
        if not (math.isfinite(strike) and strike > 0):
            errors.append({"leg": index, "reason": f"strike must be > 0, got {raw.get('strike')!r}"})
            continue
        if not math.isfinite(qty_value) or qty_value == 0 or qty_value != int(qty_value):
            errors.append({"leg": index, "reason": f"qty must be a non-zero integer, got {raw.get('qty')!r}"})
            continue
        if not (math.isfinite(entry) and entry >= 0):
            errors.append({"leg": index, "reason": "entry_premium must be >= 0 (per share)"})
            continue
        qty = int(qty_value)
        if sign:
            qty = sign * abs(qty)
        legs.append(LegInput(index, kind, strike, qty, entry, _clean_expiry(raw.get("expiry"))))
    return legs, errors


def _nearest(values: list[str], target: str, count: int = 2) -> list[str]:
    try:
        day = date.fromisoformat(target)
    except ValueError:
        return values[:count]
    return sorted(values, key=lambda v: abs((date.fromisoformat(v) - day).days))[:count]


def classify(legs: list[LegInput]) -> str:
    """Strategy name from the expiry set, the quantity ratios and the strike order."""
    expiries = sorted({leg.eff_expiry for leg in legs})
    calls = sorted((leg for leg in legs if leg.is_call), key=lambda leg: leg.strike)
    puts = sorted((leg for leg in legs if not leg.is_call), key=lambda leg: leg.strike)
    if len(expiries) > 1:
        return _classify_multi_expiry(legs, calls, puts)
    if len(legs) == 1:
        leg = legs[0]
        return f"{'Long' if leg.qty > 0 else 'Short'} {leg.opt_type.title()}"
    if len(legs) == 2:
        return _classify_two(legs[0], legs[1])
    if len(legs) == 3 and (len(calls) == 3 or len(puts) == 3):
        return _classify_butterfly(calls or puts)
    if len(legs) == 4 and len(calls) == 2 and len(puts) == 2:
        return _classify_iron(calls, puts)
    if len(legs) == 4 and (len(calls) == 4 or len(puts) == 4):
        same = calls or puts
        signs = [int(np.sign(leg.qty)) for leg in same]
        if len({abs(leg.qty) for leg in same}) == 1 and signs in ([1, -1, -1, 1], [-1, 1, 1, -1]):
            return f"{'Long' if signs[0] > 0 else 'Short'} {'Call' if calls else 'Put'} Condor"
    return "Custom Multi-Leg"


def _classify_two(a: LegInput, b: LegInput) -> str:
    if a.opt_type == b.opt_type:
        low, high = sorted((a, b), key=lambda leg: leg.strike)
        if low.strike == high.strike:
            return "Custom Multi-Leg"
        kind = a.opt_type.title()
        if np.sign(low.qty) == np.sign(high.qty):
            return f"{'Long' if low.qty > 0 else 'Short'} {kind} Pair"
        if abs(low.qty) != abs(high.qty):
            long_leg = low if low.qty > 0 else high
            short_leg = high if long_leg is low else low
            name = "Backspread" if abs(long_leg.qty) > abs(short_leg.qty) else "Ratio Spread"
            return f"{kind} {name} {max(abs(a.qty), abs(b.qty))}:{min(abs(a.qty), abs(b.qty))}"
        if a.is_call:
            return "Bull Call Spread" if low.qty > 0 else "Bear Call Spread"
        return "Bull Put Spread" if high.qty < 0 else "Bear Put Spread"
    call, put = (a, b) if a.is_call else (b, a)
    if np.sign(call.qty) == np.sign(put.qty):
        side = "Long" if call.qty > 0 else "Short"
        if abs(call.qty) != abs(put.qty):
            return f"{side} {'Strap' if abs(call.qty) > abs(put.qty) else 'Strip'}"
        if call.strike == put.strike:
            return f"{side} Straddle"
        return f"{side} {'Strangle' if call.strike > put.strike else 'Guts'}"
    ratio = abs(put.qty) / abs(call.qty)
    if call.qty > 0:
        if ratio == 2:
            return "Synthetic Long 2:1"
        if ratio == 1:
            return "Synthetic Long" if call.strike == put.strike else "Risk Reversal (bullish)"
        return f"Risk Reversal (bullish) {abs(put.qty)}:{abs(call.qty)}"
    if ratio == 1:
        return "Synthetic Short" if call.strike == put.strike else "Risk Reversal (bearish)"
    return f"Risk Reversal (bearish) {abs(put.qty)}:{abs(call.qty)}"


def _classify_butterfly(same: list[LegInput]) -> str:
    low, mid, high = same
    kind = low.opt_type.title()
    if low.strike < mid.strike < high.strike and np.sign(low.qty) == np.sign(high.qty) != np.sign(mid.qty):
        if abs(mid.qty) == abs(low.qty) + abs(high.qty):
            side = "Long" if low.qty > 0 else "Short"
            equal = abs((mid.strike - low.strike) - (high.strike - mid.strike)) < 1e-9
            if equal and abs(low.qty) == abs(high.qty):
                return f"{side} {kind} Butterfly"
            return f"{side} Broken-Wing {kind} Butterfly"
        return f"{kind} Ladder"
    return "Custom Multi-Leg"


def _classify_iron(calls: list[LegInput], puts: list[LegInput]) -> str:
    put_low, put_high = puts
    call_low, call_high = calls
    if len({abs(leg.qty) for leg in calls + puts}) != 1:
        return "Custom Multi-Leg"
    short_inner = put_high.qty < 0 < put_low.qty and call_low.qty < 0 < call_high.qty
    long_inner = put_high.qty > 0 > put_low.qty and call_low.qty > 0 > call_high.qty
    if not (short_inner or long_inner) or put_high.strike > call_low.strike:
        return "Custom Multi-Leg"
    body = "Iron Butterfly" if put_high.strike == call_low.strike else "Iron Condor"
    return body if short_inner else f"Reverse {body}"


def _classify_multi_expiry(legs: list[LegInput], calls: list[LegInput], puts: list[LegInput]) -> str:
    if len(legs) == 2 and legs[0].opt_type == legs[1].opt_type and np.sign(legs[0].qty) != np.sign(legs[1].qty):
        near, far = sorted(legs, key=lambda leg: leg.eff_expiry)
        side = "Long" if far.qty > 0 else "Short"
        ratio = "" if abs(near.qty) == abs(far.qty) else f" {abs(far.qty)}:{abs(near.qty)}"
        shape = "Calendar" if near.strike == far.strike else "Diagonal"
        return f"{side} {near.opt_type.title()} {shape}{ratio}"
    if len(legs) == 4 and len(calls) == 2 and len(puts) == 2:
        parts = [_classify_multi_expiry(list(pair), [], []) for pair in (calls, puts)]
        if all(part.startswith("Long") for part in parts):
            return "Double Calendar" if all("Calendar" in part for part in parts) else "Double Diagonal"
    return "Custom Multi-Expiry"


def _structure(legs: list[LegInput], multiplier: int) -> dict[str, Any]:
    net = sum(leg.entry * leg.qty for leg in legs) * multiplier
    return {
        "expiries": sorted({leg.eff_expiry for leg in legs}),
        "n_legs": len(legs),
        "contracts": sum(abs(leg.qty) for leg in legs),
        "net_call_qty": sum(leg.qty for leg in legs if leg.is_call),
        "net_put_qty": sum(leg.qty for leg in legs if not leg.is_call),
        "entry": "debit" if net > 0 else "credit" if net < 0 else "even",
        "entry_net_premium": round(net, 2),
    }


class Valuer:
    """Position value at a future time and spot, with the model of each leg."""

    def __init__(self, ctx: MarketContext, legs: list[LegInput], ivs: list[float | None],
                 multiplier: int) -> None:
        self.ctx = ctx
        self.legs = legs
        self.ivs = ivs
        self.mult = multiplier
        self.T = [ctx.tte(leg.eff_expiry) for leg in legs]
        self.r = [ctx.rate(T).value for T in self.T]
        self.times, self.amounts = ctx.schedule()

    @property
    def complete(self) -> bool:
        """True when every leg has an IV."""
        return all(iv is not None for iv in self.ivs)

    def leg_values(self, index: int, spots: np.ndarray, t: float, iv_shift: float = 0.0) -> np.ndarray:
        """Value per share of one leg at ``t`` years from now for each spot."""
        leg = self.legs[index]
        remaining = self.T[index] - t
        spots = np.asarray(spots, dtype=float)
        phi = 1.0 if leg.is_call else -1.0
        if remaining <= 1e-12:
            return np.maximum(phi * (spots - leg.strike), 0.0)
        iv = self.ivs[index]
        if iv is None:
            return np.full(spots.shape, np.nan)
        sigma = max(iv + iv_shift, pricing.IV_MIN)
        times = [x - t for x in self.times]
        return pricing.option_price(spots, leg.strike, remaining, self.r[index], self.ctx.dividends.q,
                                    sigma, leg.is_call, self.ctx.style, times, self.amounts)

    def pnl(self, spots: Any, t: float, iv_shift: float = 0.0) -> np.ndarray:
        """Position P&L ($) at ``t`` years from now (model value, before spreads and fees)."""
        spots = np.atleast_1d(np.asarray(spots, dtype=float))
        total = np.zeros(spots.shape)
        for index, leg in enumerate(self.legs):
            total += (self.leg_values(index, spots, t, iv_shift) - leg.entry) * leg.qty * self.mult
        return total


def _round(value: Any, places: int = 4) -> float | None:
    if value is None:
        return None
    number = float(value)
    return round(number, places) if math.isfinite(number) else None


def payoff_analysis(valuer: Valuer, spot: float, t_h: float, sigma_ref: float,
                    strikes: list[float]) -> dict[str, Any]:
    """Break-evens, max profit and loss, and the compact payoff curve at the horizon.

    The search grid spans +/- 6 standard deviations (at least +/- 25% in log
    terms) plus every strike; the extremes also check a spot near 0 and the
    slope at 50x and 100x the spot (unbounded profit or loss).
    """
    from scipy.optimize import brentq  # pylint: disable=import-outside-toplevel

    scale = sigma_ref * math.sqrt(max(t_h, 1e-6))
    width = max(6.0 * scale, 0.25)
    grid = np.unique(np.concatenate([
        spot * np.exp(np.linspace(-width, width, _GRID_POINTS)), np.asarray(strikes, dtype=float), [spot],
    ]))
    grid = grid[grid > 0]
    pnl = valuer.pnl(grid, t_h)
    breakevens: list[float] = []
    for i in range(grid.shape[0] - 1):
        y0, y1 = pnl[i], pnl[i + 1]
        if not (math.isfinite(y0) and math.isfinite(y1)):
            continue
        if y0 == 0.0:
            breakevens.append(float(grid[i]))
        elif (y0 < 0) != (y1 < 0):
            try:
                root = brentq(lambda s: float(valuer.pnl([s], t_h)[0]), grid[i], grid[i + 1], xtol=1e-6)
            except ValueError:
                root = grid[i] - y0 * (grid[i + 1] - grid[i]) / (y1 - y0)
            breakevens.append(float(root))
    contracts = sum(abs(leg.qty) for leg in valuer.legs) * valuer.mult
    far = valuer.pnl([spot * 50.0, spot * 100.0], t_h)
    slope = (far[1] - far[0]) / (spot * 50.0)
    tol = 1e-3 * contracts
    unbounded_profit = bool(slope > tol)
    unbounded_loss = bool(slope < -tol)
    candidates = np.concatenate([pnl, valuer.pnl([spot * 1e-6], t_h), far])
    finite = candidates[np.isfinite(candidates)]
    max_profit = None if unbounded_profit or not finite.size else float(finite.max())
    max_loss = None if unbounded_loss or not finite.size else float(finite.min())
    span = min(width, 3.0 * scale + 0.05)
    lo_out, hi_out = spot * math.exp(-span), spot * math.exp(span)
    out_grid = np.unique(np.concatenate([
        np.exp(np.linspace(math.log(lo_out), math.log(hi_out), _OUTPUT_POINTS)),
        [s for s in strikes if lo_out <= s <= hi_out], [b for b in breakevens if lo_out <= b <= hi_out], [spot],
    ]))
    out_pnl = valuer.pnl(out_grid, t_h)
    return {
        "grid": grid, "pnl": pnl, "breakevens": sorted({round(b, 4) for b in breakevens}),
        "max_profit": max_profit, "max_loss": max_loss,
        "max_profit_unbounded": unbounded_profit, "max_loss_unbounded": unbounded_loss,
        "curve": [{"price": round(float(p), 4), "pnl": _round(v, 2)} for p, v in zip(out_grid, out_pnl)],
        "price_range": [round(float(grid[0]), 4), round(float(grid[-1]), 4)],
    }


def probabilities(valuer: Valuer, payoff: dict[str, Any], smile: iv_surface.SmileFit | None,
                  ctx: MarketContext, t_h: float, sigma_ref: float, short_strikes: list[float]) -> dict[str, Any]:
    """Risk-neutral probabilities at the horizon and touch probabilities of the key levels."""
    forward = smile.forward if smile is not None else ctx.price
    dist = iv_surface.terminal_distribution(smile, spot=ctx.price, T=t_h, forward=forward, atm_iv=sigma_ref)
    out: dict[str, Any] = {"measure": "risk_neutral", "distribution": None, "horizon_years": round(t_h, 6)}
    if dist is None:
        out["note"] = "no implied volatility for the horizon: probabilities unavailable"
        return out
    pnl = valuer.pnl(dist.prices, t_h)
    good = np.isfinite(pnl)
    probs, pnl = dist.probs[good], pnl[good]
    out["distribution"] = dist.method
    out["profit_prob"] = round(float(probs[pnl > 0].sum()), 4)
    out["loss_prob"] = round(float(probs[pnl < 0].sum()), 4)
    span = 0.0
    if payoff["max_profit"] is not None and payoff["max_loss"] is not None:
        span = payoff["max_profit"] - payoff["max_loss"]
    tol = max(1.0, 0.005 * span)
    out["max_profit_prob"] = (round(float(probs[pnl >= payoff["max_profit"] - tol].sum()), 4)
                              if payoff["max_profit"] is not None else None)
    out["max_loss_prob"] = (round(float(probs[pnl <= payoff["max_loss"] + tol].sum()), 4)
                            if payoff["max_loss"] is not None else None)
    out["expected_pnl_risk_neutral"] = round(float(np.sum(probs * pnl)), 2)
    out["expected_pnl_note"] = "risk-neutral mean of the horizon value minus the entry cost; not a forecast"
    if dist.negative_mass > 1e-3:
        out["density_warning"] = f"smile density had {dist.negative_mass:.3f} negative mass (clipped)"
    rate = ctx.rate(t_h).value
    touches = []
    for level in sorted({*payoff["breakevens"], *short_strikes}):
        sigma = float(smile.iv([level])[0]) if smile is not None and smile.fitted else sigma_ref
        touches.append({
            "level": round(float(level), 4),
            "kind": "short_strike" if level in short_strikes else "breakeven",
            "touch_prob": round(float(pricing.touch_probability(
                ctx.price, level, t_h, rate, ctx.dividends.q, sigma)[0]), 4),
        })
    out["touch"] = touches
    return out


def scenario_grid(valuer: Valuer, spot: float, t_h: float,
                  short_strikes: list[float]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Spot x days-forward grid, spot x IV grid and the standard stress tests."""
    days_h = t_h * 365.0
    days = sorted({0.0, round(min(7.0, days_h), 4), round(days_h / 2.0, 4), round(days_h, 4)})
    shifts = [-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20]
    spots = np.array([spot * (1 + s) for s in shifts])
    grid = [{"days_forward": day, "pnl": [_round(v, 2) for v in valuer.pnl(spots, day / 365.0)]} for day in days]
    vol_rows = [{"iv_shift_points": int(round(shift * 100)),
                 "pnl": [_round(v, 2) for v in valuer.pnl(spots, 0.0, shift)]} for shift in (-0.10, 0.0, 0.10)]
    scenarios = {
        "spot_shifts_pct": [int(round(s * 100)) for s in shifts],
        "spot_levels": [round(float(s), 4) for s in spots],
        "by_days_forward": grid,
        "by_iv_shift_today": vol_rows,
        "basis": "model value (mid-equivalent), before spreads and fees; IV shift in absolute vol points",
    }
    stress = [
        {"name": "spot -20%", "spot": round(spot * 0.8, 4), "iv_shift_points": 0, "days_forward": 0.0,
         "pnl": _round(valuer.pnl([spot * 0.8], 0.0)[0], 2)},
        {"name": "IV +20 points", "spot": round(spot, 4), "iv_shift_points": 20, "days_forward": 0.0,
         "pnl": _round(valuer.pnl([spot], 0.0, 0.20)[0], 2)},
        {"name": "spot -20% and IV +20 points", "spot": round(spot * 0.8, 4), "iv_shift_points": 20,
         "days_forward": 0.0, "pnl": _round(valuer.pnl([spot * 0.8], 0.0, 0.20)[0], 2)},
    ]
    for strike in short_strikes:
        legs = [leg for leg in valuer.legs if leg.qty < 0 and leg.strike == strike]
        for leg in legs[:1]:
            beyond = strike * (1.02 if leg.is_call else 0.98)
            for label, t in (("now", 0.0), ("at the horizon", t_h)):
                stress.append({
                    "name": f"gap through short {leg.opt_type} {strike:g} ({label})", "spot": round(beyond, 4),
                    "iv_shift_points": 0, "days_forward": round(t * 365.0, 4),
                    "pnl": _round(valuer.pnl([beyond], t)[0], 2),
                })
    return scenarios, stress


def early_exercise(ctx: MarketContext, is_call: bool, strike: float, qty: int, iv: float | None, T: float,
                   r: float, model_price: float | None) -> dict[str, Any] | None:
    """Assignment risk of a short American leg (calls before an ex-date, deep ITM puts)."""
    if ctx.style != pricing.STYLE_AMERICAN or qty > 0 or iv is None:
        return None
    S = ctx.price
    times, amounts = ctx.schedule()
    if is_call:
        for t_ex, amount in zip(times, amounts):
            if not 0.0 < t_ex < T:
                continue
            intrinsic = S - strike
            if intrinsic <= 0:
                return None
            later = [(t - t_ex, a) for t, a in zip(times, amounts) if t > t_ex]
            hold = float(pricing.european_price(
                S - amount, strike, T - t_ex, r, ctx.dividends.q, iv, True,
                [t for t, _ in later], [a for _, a in later],
            )[0])
            likely = intrinsic > hold
            return {
                "risk": "high" if likely else "low",
                "reason": (
                    f"short ITM call before an ex-dividend of {amount:.4f} (in {t_ex * 365:.1f} days): "
                    f"exercise value {intrinsic:.4f} {'>' if likely else '<='} value after the ex-date "
                    f"{hold:.4f} (spot unchanged)"
                ),
            }
        return None
    intrinsic = strike - S
    if intrinsic <= 0 or model_price is None:
        return None
    time_value = model_price - intrinsic
    likely = time_value <= max(0.01, 0.0005 * strike)
    elevated = time_value <= 0.02 * strike * iv * math.sqrt(max(T, 1e-6))
    return {
        "risk": "high" if likely else ("medium" if elevated else "low"),
        "reason": (
            f"short ITM put: model time value {time_value:.4f}; "
            f"{'early exercise is optimal for the holder now' if likely else 'early exercise not optimal yet'}"
        ),
    }


def prob_itm(smile: iv_surface.SmileFit | None, strike: float, is_call: bool,
             fallback: float | None) -> float | None:
    """Risk-neutral P(ITM at the leg expiry) with the smile slope (digital = -dC/dK)."""
    if smile is None or smile.T <= 0:
        return None
    forward, T = smile.forward, smile.T

    def call(K: float, sigma: float) -> float:
        vol = sigma * math.sqrt(T)
        d1 = (math.log(forward / K) + 0.5 * vol * vol) / vol
        return forward * float(ndtr(d1)) - K * float(ndtr(d1 - vol))

    h = strike * 1e-3
    if smile.fitted:
        up, dn = float(smile.iv([strike + h])[0]), float(smile.iv([strike - h])[0])
    elif fallback is not None:
        up = dn = fallback
    else:
        return None
    above = min(max(-(call(strike + h, up) - call(strike - h, dn)) / (2 * h), 0.0), 1.0)
    return round(above if is_call else 1.0 - above, 4)


def management_flags(legs: list[LegInput], rows: list[dict[str, Any]], payoff: dict[str, Any] | None,
                     pnl_total: float | None, structure: dict[str, Any], spot: float, t_h: float,
                     sigma_ref: float | None) -> list[dict[str, Any]]:
    """21-DTE, 50%-of-max-profit, 2x-credit loss, short-delta and pin-risk flags."""
    flags: list[dict[str, Any]] = []
    shorts = [(leg, row) for leg, row in zip(legs, rows) if leg.qty < 0]
    near = [row["label"] for _, row in shorts if row["dte"] is not None and row["dte"] <= MANAGEMENT_DTE]
    if near:
        flags.append({"flag": "dte_21", "severity": "info", "legs": near,
                      "message": "short legs at or under 21 DTE: gamma risk rises; plan to close or roll"})
    tested = [row["label"] for _, row in shorts
              if row["greeks_per_share"]["delta"] is not None
              and abs(row["greeks_per_share"]["delta"]) >= SHORT_DELTA_ALERT]
    if tested:
        flags.append({"flag": "short_delta_breach", "severity": "warning", "legs": tested,
                      "message": f"short strikes with |delta| >= {SHORT_DELTA_ALERT}: the short strike is tested"})
    if payoff and payoff["max_profit"] is not None and pnl_total is not None and structure["entry"] == "credit":
        if payoff["max_profit"] > 0 and pnl_total >= 0.5 * payoff["max_profit"]:
            flags.append({"flag": "profit_50pct", "severity": "info", "legs": [],
                          "message": f"P&L {pnl_total:.2f} is at least 50% of the max profit "
                                     f"{payoff['max_profit']:.2f}: consider taking profit"})
        credit = -structure["entry_net_premium"]
        if credit > 0 and pnl_total <= -2.0 * credit:
            flags.append({"flag": "loss_2x_credit", "severity": "warning", "legs": [],
                          "message": f"loss {pnl_total:.2f} is at least 2x the credit {credit:.2f}"})
    days = t_h * 365.0
    if days <= PIN_DAYS and sigma_ref:
        band = max(spot * sigma_ref * math.sqrt(max(t_h, 1.0 / 365.0)) * 0.5, spot * 0.005)
        pinned = [row["label"] for leg, row in shorts if abs(spot - leg.strike) <= band]
        if pinned:
            flags.append({"flag": "pin_risk", "severity": "warning", "legs": pinned,
                          "message": f"{days:.1f} days to the horizon and the spot is within {band:.2f} "
                                     "of a short strike: assignment is uncertain (pin risk)"})
    return flags


def _recommendations(flags: list[dict[str, Any]], pnl_total: float | None, payoff: dict[str, Any] | None,
                     spot: float, name: str) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    if pnl_total is None:
        recs.append({"type": "Data", "reason": "No executable close P&L: at least one leg has no two-sided quote."})
    elif pnl_total > 0:
        recs.append({"type": "Consider", "reason": "Position is profitable at bid/ask: check the take-profit plan."})
    elif pnl_total < 0:
        recs.append({"type": "Monitor", "reason": "Position is under water at bid/ask: check the stop and the thesis."})
    if payoff and payoff["breakevens"]:
        nearest = min(payoff["breakevens"], key=lambda level: abs(level - spot))
        recs.append({"type": "Target", "reason": f"Nearest breakeven at the horizon: ${nearest:.2f}"})
    for flag in flags:
        recs.append({"type": flag["flag"], "reason": flag["message"]})
    recs.append({"type": "Strategy", "reason": f"Classified as: {name}"})
    return recs


def _resolve_expiries(ticker: str, parsed: list[LegInput], expiry: Any, data: Any,
                      moment: datetime) -> tuple[dict[str, Any] | None, list[str], list[str], str]:
    """Validate leg and global expiries. Returns ``(error, expirations, leg_expiries, horizon)``."""
    global_expiry = _clean_expiry(expiry)
    if global_expiry is not None:
        try:
            date.fromisoformat(global_expiry)
        except ValueError:
            return _fail(ticker, f"expiry must be YYYY-MM-DD, got {expiry!r}"), [], [], ""
    missing = [leg.index for leg in parsed if leg.expiry is None and global_expiry is None]
    if missing:
        return _fail(ticker, f"legs {missing} have no expiry and no global expiry was given"), [], [], ""
    for leg in parsed:
        leg.eff_expiry = leg.expiry or global_expiry or ""
    expirations = sorted(str(e)[:10] for e in (data.get_options_expirations(ticker) or []))
    if not expirations:
        return _fail(ticker, f"no listed options for {ticker}", retryable=True), [], [], ""
    wanted = {leg.eff_expiry for leg in parsed} | ({global_expiry} if global_expiry else set())
    unlisted = sorted(e for e in wanted if e not in expirations)
    if unlisted:
        return _fail(
            ticker, "unlisted expiry: " + ", ".join(
                f"{e} (nearest listed: {', '.join(_nearest(expirations, e))})" for e in unlisted),
            unlisted_expiries=[{"expiry": e, "nearest_listed": _nearest(expirations, e)} for e in unlisted],
            expirations=expirations[:24],
        ), expirations, [], ""
    expired = [
        {"leg": leg.index, "expiry": leg.eff_expiry, "label": leg.label()} for leg in parsed
        if mcal.time_to_expiry(leg.eff_expiry, ticker, options_market.settlement(ticker, leg.eff_expiry),
                               moment) <= 0
    ]
    if expired:
        return _fail(ticker, "expired legs: " + ", ".join(e["label"] for e in expired),
                     expired_legs=expired), expirations, [], ""
    leg_expiries = sorted({leg.eff_expiry for leg in parsed})
    earliest = leg_expiries[0]
    horizon = earliest
    if global_expiry and global_expiry not in leg_expiries:
        if global_expiry > earliest:
            return _fail(
                ticker,
                f"global expiry {global_expiry} is later than the earliest leg expiry {earliest}: "
                "the near leg settles first, so the position is evaluated at its expiry. "
                f"Pass expiry='{earliest}' or omit it when every leg has its own expiry",
            ), expirations, leg_expiries, ""
        horizon = global_expiry
    return None, expirations, leg_expiries, horizon


def analyze_options_position(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    ticker: str,
    legs: list[dict[str, Any]],
    expiry: str | None = None,
    *,
    commission_per_contract: float = COMMISSION_PER_CONTRACT,
    include_scenarios: bool = True,
    now: datetime | None = None,
    source: Any = None,
) -> dict[str, Any]:
    """Analyze a multi-leg options position (see the module docstring).

    Args:
        ticker: Underlying symbol.
        legs: ``{"type", "strike", "qty", "entry_premium", "expiry"?}`` dicts;
            ``qty`` is signed (negative = short) or ``type`` has a
            ``long_``/``short_`` prefix; ``entry_premium`` is per share.
        expiry: Default expiry for legs without their own; when every leg has
            one, an optional earlier evaluation date (a listed expiry).
        commission_per_contract: Broker fee per contract and side.
        include_scenarios: Add the scenario grid and the stress tests.
        now: Valuation time (tests).
        source: DataProvider (tests).
    """
    ticker = str(ticker).strip().upper()
    moment = now or utc_now()
    data = source if source is not None else options_market.provider()
    parsed, errors = parse_legs(legs)
    if errors:
        return _fail(ticker, "invalid legs: " + "; ".join(f"leg {e['leg']}: {e['reason']}" for e in errors),
                     invalid_legs=errors)
    error, expirations, leg_expiries, horizon_expiry = _resolve_expiries(ticker, parsed, expiry, data, moment)
    if error is not None:
        return error
    earliest = leg_expiries[0]
    spot = check_spot(ticker, now=moment, source=data)
    if not spot.usable:
        return _fail(ticker, f"spot not usable: {spot.block_reason}", retryable=True, spot=spot.stamp())
    ctx = build_context(ticker, horizon=date.fromisoformat(leg_expiries[-1]), now=moment, source=data, spot=spot)
    views, chain_errors = load_chains(ticker, sorted(set(leg_expiries) | {horizon_expiry}), now=moment, source=data)
    if chain_errors:
        return _fail(ticker, "option chain unavailable: " + ", ".join(f"{e} ({m})" for e, m in chain_errors.items()),
                     retryable=True, spot=spot.stamp())
    unmatched = []
    for leg in parsed:
        side = views[leg.eff_expiry].side(leg.is_call)
        if side.index_of(leg.strike) is None:
            near = side.strike[np.argsort(np.abs(side.strike - leg.strike))[:3]] if len(side) else []
            unmatched.append({"leg": leg.index, "label": leg.label(),
                              "nearest_listed_strikes": sorted(float(k) for k in near)})
    if unmatched:
        return _fail(ticker, "strike not listed: " + "; ".join(
            f"{u['label']} (nearest: {u['nearest_listed_strikes']})" for u in unmatched),
            unmatched_legs=unmatched, spot=spot.stamp())

    warnings: list[str] = list(spot.warnings) + list(ctx.warnings) + options_market.source_warnings(views)
    degraded = bool(ctx.dividends.assumed)
    for view in views.values():
        warnings += view.warnings
        degraded |= view.stale
    multiplier = views[earliest].multiplier
    smiles = {e: iv_surface.build_smile(views[e], ctx, steps=pricing.DEFAULT_STEPS) for e in views}
    times, amounts = ctx.schedule()
    q = ctx.dividends.q
    S = ctx.price

    leg_rows: list[dict[str, Any]] = []
    ivs: list[float | None] = []
    greeks_rows: list[dict[str, np.ndarray] | None] = []
    pnl_parts: list[float | None] = []
    mid_parts: list[float | None] = []
    blocked: list[str] = []
    no_iv: list[str] = []
    flags: list[dict[str, Any]] = []
    for leg in parsed:
        view = views[leg.eff_expiry]
        side = view.side(leg.is_call)
        pos = side.index_of(leg.strike)
        bid = float(side.bid[pos]) if np.isfinite(side.bid[pos]) else None
        ask = float(side.ask[pos]) if np.isfinite(side.ask[pos]) else None
        quote_ok = bool(side.quote_ok[pos])
        mid = float(side.mid[pos]) if quote_ok else None
        T = ctx.tte(leg.eff_expiry)
        rate = ctx.rate(T)
        iv, iv_source, iv_status = None, None, None
        if quote_ok and mid is not None and mid > 0:
            solved, status = pricing.implied_vol(mid, S, leg.strike, T, rate.value, q, leg.is_call, ctx.style,
                                                 times, amounts, steps=pricing.DEFAULT_STEPS)
            iv_status = str(status[0])
            if np.isfinite(solved[0]) and pricing.IV_MIN < solved[0] < pricing.IV_MAX:
                iv, iv_source = float(solved[0]), "quote_mid"
        smile = smiles[leg.eff_expiry]
        if iv is None and smile.fitted:
            candidate = float(smile.iv([leg.strike])[0])
            if math.isfinite(candidate) and pricing.IV_MIN < candidate < pricing.IV_MAX:
                iv, iv_source = candidate, f"smile_{smile.method}"
        if iv is None:
            no_iv.append(leg.label())
        ivs.append(iv)
        g = None
        if iv is not None:
            g = pricing.greeks(S, leg.strike, T, rate.value, q, iv, leg.is_call, ctx.style, times, amounts)
        greeks_rows.append(g)
        exit_mark = (bid if leg.qty > 0 else ask) if quote_ok else None
        pnl = (exit_mark - leg.entry) * leg.qty * multiplier if exit_mark is not None else None
        if pnl is None:
            blocked.append(leg.label())
        pnl_parts.append(pnl)
        mid_parts.append((mid - leg.entry) * leg.qty * multiplier if mid is not None else None)
        vendor_iv = float(side.vendor_iv[pos]) if np.isfinite(side.vendor_iv[pos]) else None
        model_price = float(g["price"][0]) if g is not None else None
        early = early_exercise(ctx, leg.is_call, leg.strike, leg.qty, iv, T, rate.value, model_price)
        if early is not None and early["risk"] in ("high", "medium"):
            flags.append({"flag": "early_assignment", "severity": "critical" if early["risk"] == "high" else "warning",
                          "legs": [leg.label()], "message": early["reason"]})
        leg_rows.append({
            "leg": leg.index, "label": leg.label(), "side": "Long" if leg.qty > 0 else "Short",
            "type": leg.opt_type, "strike": leg.strike, "qty": leg.qty, "entry_premium": leg.entry,
            "expiry": leg.eff_expiry, "dte": _round(T * 365.0, 4),
            "expiry_time": iso(ctx.expiry_moment(leg.eff_expiry)), "settlement": ctx.settlement(leg.eff_expiry),
            "bid": bid, "ask": ask, "mid": _round(mid, 4), "quote_ok": quote_ok,
            "last": _round(side.last[pos], 4) if np.isfinite(side.last[pos]) else None,
            "last_trade_at": side.last_trade[pos], "quote_time": side.quote_time[pos],
            "quote_source": view.source, "chain_fetched_at": view.fetched_at,
            "exit_mark": exit_mark, "exit_side": "bid" if leg.qty > 0 else "ask",
            "pnl": _round(pnl, 2), "pnl_blocked": pnl is None,
            "pnl_blocked_reason": None if pnl is not None else "no two-sided quote (bid and ask)",
            "iv": _round(iv, 6), "iv_source": iv_source, "iv_solver_status": iv_status,
            "vendor_iv": _round(vendor_iv, 6),
            "iv_minus_vendor": _round(iv - vendor_iv, 6) if iv is not None and vendor_iv is not None else None,
            "model_price": _round(model_price, 4), "rate": rate.value, "rate_method": rate.method,
            "greeks_per_share": {key: _round(g[key][0], 6) if g is not None else None for key in pricing.GREEK_UNITS},
            "prob_itm_at_expiry": prob_itm(smile, leg.strike, leg.is_call, iv),
            "liquidity": liquidity.liquidity(bid, ask, side.oi[pos], side.volume[pos]),
            "early_exercise": early,
        })

    complete_greeks = all(g is not None for g in greeks_rows)
    position_greeks: dict[str, Any] = {"complete": complete_greeks, "blocked_legs": no_iv}
    if complete_greeks:
        def total(key: str) -> float:
            return float(sum(g[key][0] * leg.qty * multiplier for g, leg in zip(greeks_rows, parsed)))

        delta_shares, gamma_shares = total("delta"), total("gamma")
        position_greeks.update({
            "delta_shares": round(delta_shares, 4),
            "delta_dollars": round(delta_shares * S, 2),
            "gamma_shares_per_dollar": round(gamma_shares, 6),
            "gamma_dollars_per_1pct": round(gamma_shares * S * S * 0.01, 2),
            "theta_dollars_per_day": round(total("theta"), 2),
            "vega_dollars_per_vol_point": round(total("vega"), 2),
            "rho_dollars_per_rate_point": round(total("rho"), 2),
            "vanna_shares_per_vol_point": round(total("vanna"), 4),
            "charm_shares_per_day": round(total("charm"), 4),
            "vomma_dollars_per_vol_point": round(total("vomma"), 4),
        })
    else:
        warnings.append("no IV for " + ", ".join(no_iv) + ": position Greeks and model values blocked")
        degraded = True

    cost_basis = sum(leg.entry * leg.qty for leg in parsed) * multiplier
    contracts = sum(abs(leg.qty) for leg in parsed)
    pnl_total = None if any(p is None for p in pnl_parts) else float(sum(pnl_parts))
    pnl_mid = None if any(p is None for p in mid_parts) else float(sum(mid_parts))
    close_commissions = contracts * commission_per_contract
    if blocked:
        warnings.append("P&L blocked for " + ", ".join(blocked) + ": no two-sided quote")
        degraded = True
    pnl_block = {
        "cost_basis": round(cost_basis, 2),
        "cost_basis_note": "sum of entry_premium x qty x multiplier; positive = net debit paid",
        "close_value": round(pnl_total + cost_basis, 2) if pnl_total is not None else None,
        "total_pnl": _round(pnl_total, 2),
        "total_pnl_pct": (_round(pnl_total / abs(cost_basis) * 100.0, 2)
                          if pnl_total is not None and cost_basis else None),
        "pnl_at_mid": _round(pnl_mid, 2),
        "pnl_blocked": pnl_total is None,
        "blocked_legs": blocked,
        "basis": "close long legs at the bid and short legs at the ask",
    }
    costs = {
        "commission_per_contract": commission_per_contract,
        "contracts": contracts,
        "commissions_to_close": round(close_commissions, 2),
        "commissions_round_trip": round(2 * close_commissions, 2),
        "spread_cost_vs_mid": _round(pnl_mid - pnl_total, 2) if pnl_mid is not None and pnl_total is not None else None,
        "pnl_net_of_close_commissions": _round(pnl_total - close_commissions, 2) if pnl_total is not None else None,
        "note": "commissions = sum(|qty|) x fee per side; regulatory fees are not included",
    }

    t_h = ctx.tte(horizon_expiry)
    horizon_smile = smiles.get(horizon_expiry)
    leg_ivs = [iv for iv in ivs if iv is not None]
    sigma_ref = (horizon_smile.atm_iv if horizon_smile is not None and horizon_smile.atm_iv
                 else (float(np.median(leg_ivs)) if leg_ivs else None))
    valuer = Valuer(ctx, parsed, ivs, multiplier)
    single_expiry = len(leg_expiries) == 1 and horizon_expiry == earliest
    short_strikes = sorted({leg.strike for leg in parsed if leg.qty < 0})
    payoff = None
    probs: dict[str, Any] = {"measure": "risk_neutral", "distribution": None}
    scenarios: dict[str, Any] | None = None
    stress: list[dict[str, Any]] = []
    if valuer.complete or single_expiry:
        payoff = payoff_analysis(valuer, S, t_h, sigma_ref if sigma_ref else 0.5,
                                 sorted({leg.strike for leg in parsed}))
        if sigma_ref is not None:
            probs = probabilities(valuer, payoff, horizon_smile, ctx, t_h, sigma_ref, short_strikes)
        else:
            probs["note"] = "no implied volatility: probabilities unavailable"
        if include_scenarios and valuer.complete:
            scenarios, stress = scenario_grid(valuer, S, t_h, short_strikes)
    else:
        warnings.append("payoff blocked: a leg that is alive at the horizon has no IV")

    structure = _structure(parsed, multiplier)
    name = classify(parsed)
    events = event_risk.earnings_block(ctx, ctx.expiry_moment(leg_expiries[-1]), expirations, views)
    ex_divs = event_risk.ex_dividends_before(ctx, date.fromisoformat(leg_expiries[-1]))
    if events.get("before_horizon"):
        flags.append({"flag": "earnings_before_expiry", "severity": "warning", "legs": [],
                      "message": f"earnings {events['next_earnings']['start']} before the last expiry: "
                                 "gap and IV-crush risk"})
    if events.get("note") and "unknown" in events["note"]:
        warnings.append(events["note"])
    flags += management_flags(parsed, leg_rows, payoff, pnl_total, structure, S, t_h, sigma_ref)
    max_profit = payoff["max_profit"] if payoff else None
    max_loss = payoff["max_loss"] if payoff else None
    risk_reward = (round(max_profit / abs(max_loss), 4)
                   if max_profit is not None and max_loss is not None and max_loss < 0 else None)
    rate_h = ctx.rate(max(t_h, 1e-6))
    result: dict[str, Any] = {
        "ticker": ticker,
        "as_of": spot.as_of,
        "sources": sorted({s for s in [spot.source, *(f"{v.source}:options" for v in views.values())] if s}),
        "data_source": ",".join(sorted({v.source for v in views.values()})),
        "data_quality": f"own IV from mids; {ctx.style} model"
                        + (" (BBSR tree)" if ctx.style == pricing.STYLE_AMERICAN else " (closed form)"),
        "degraded": degraded,
        "underlying_price": S,
        "spot": spot.stamp(),
        "exercise_style": ctx.style,
        "contract_multiplier": multiplier,
        "expiry": horizon_expiry,
        "dte": _round(t_h * 365.0, 4),
        "horizon": {"expiry": horizon_expiry, "evaluation_time": iso(ctx.expiry_moment(horizon_expiry)),
                    "dte": _round(t_h * 365.0, 4), "rule": "earliest leg expiry (or the earlier global expiry)"},
        "leg_expiries": leg_expiries,
        "strategy_classification": name,
        "structure": structure,
        "legs": leg_rows,
        "position_greeks": position_greeks,
        "units": POSITION_UNITS,
        "greek_units_per_share": pricing.GREEK_UNITS,
        "pnl": pnl_block,
        "estimated_costs": costs,
        "payoff_scenarios": payoff["curve"] if payoff else [],
        "payoff_price_range": payoff["price_range"] if payoff else None,
        "breakevens": payoff["breakevens"] if payoff else [],
        "max_profit": _round(max_profit, 2),
        "max_loss": _round(max_loss, 2),
        "max_profit_unbounded": payoff["max_profit_unbounded"] if payoff else None,
        "max_loss_unbounded": payoff["max_loss_unbounded"] if payoff else None,
        "risk_reward": risk_reward,
        "probabilities": probs,
        "scenarios": scenarios,
        "stress_tests": stress,
        "management_flags": flags,
        "events": {"earnings": events, "ex_dividends_before_last_expiry": ex_divs},
        "recommendations": _recommendations(flags, pnl_total, payoff, S, name),
        "dividends": ctx.dividend_stamp(t_h),
        "rates": {e: ctx.rate(ctx.tte(e)).model_dump() for e in leg_expiries},
        "risk_free_rate": {"value": rate_h.value, "source": rate_h.source, "as_of": rate_h.as_of,
                           "is_live": rate_h.is_live, "fallback_reason": rate_h.fallback_reason,
                           "tenor_years": rate_h.tenor_years, "method": rate_h.method,
                           "compounding": rate_h.compounding},
        "smiles": {e: s.summary() for e, s in smiles.items()},
        "chains": {e: v.stamp() for e, v in views.items()},
        "warnings": list(dict.fromkeys(warnings)),
    }
    if len(leg_expiries) > 1:
        result["warning"] = (
            f"multi-expiry position: evaluated at {horizon_expiry}; legs that expire later are valued "
            "with the model at their own IV, tenor and dividends"
        )
    return result


def time_to_expiry(expiry: str, ticker: str = "US", now: datetime | None = None) -> float:
    """ACT/365 years to the expiry moment of ``ticker`` options (0.0 when expired)."""
    return mcal.time_to_expiry(expiry, ticker, options_market.settlement(ticker, expiry), now)


__all__ = [
    "LegInput",
    "POSITION_UNITS",
    "Valuer",
    "analyze_options_position",
    "classify",
    "early_exercise",
    "management_flags",
    "parse_legs",
    "payoff_analysis",
    "prob_itm",
    "probabilities",
    "scenario_grid",
    "time_to_expiry",
]
