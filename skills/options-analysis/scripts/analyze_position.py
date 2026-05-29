#!/usr/bin/env python3
"""
Options Position Analyzer

Analyzes multi-leg options positions: Greeks, payoff scenarios, probabilities.

Usage:
  python analyze_position.py TICKER \\
    --leg "type strike qty entry" \\
    [--leg ...] \\
    [--expiry "YYYY-MM-DD"] \\
    [--output json]

Example:
  python analyze_position.py DRAM \\
    --leg "call 59 1 14.71" \\
    --leg "put 45 -2 7.90" \\
    --expiry "2026-12-18"
"""

import argparse
import math
import sys
from datetime import date, datetime
from typing import Optional

import numpy as np
import yfinance as yf
from scipy.stats import norm

RISK_FREE_RATE = 0.045


class OptionLeg:
    def __init__(self, opt_type: str, strike: float, qty: int, entry: float):
        if opt_type.lower() not in ("call", "put"):
            raise ValueError(f"type must be 'call' or 'put', got '{opt_type}'")
        self.opt_type = opt_type.lower()
        self.strike = strike
        self.qty = qty
        self.entry = entry

    def __repr__(self) -> str:
        side = "Long" if self.qty > 0 else "Short"
        return f"{side} {abs(self.qty)}x {self.opt_type.title()} {self.strike} @ {self.entry}"

    def side_label(self) -> str:
        side = "Long" if self.qty > 0 else "Short"
        return f"{side} {abs(self.qty)}x {self.opt_type.title()} {self.strike}"


def find_closest_expiry(expirations: list[str], target: Optional[str] = None) -> str:
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


def black_scholes_greeks(
    S: float, K: float, T: float, r: float, sigma: float, opt_type: str
) -> dict:
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    if opt_type == "call":
        delta = norm.cdf(d1)
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * sqrt_T)
            - r * K * math.exp(-r * T) * norm.cdf(d2)
        ) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * sqrt_T)
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
        ) / 365

    gamma = norm.pdf(d1) / (S * sigma * sqrt_T)
    vega = S * norm.pdf(d1) * sqrt_T / 100

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega, "d1": d1, "d2": d2}


def payoff_at_expiry(S: float, legs: list[OptionLeg]) -> float:
    total = 0.0
    for leg in legs:
        if leg.opt_type == "call":
            option_value = max(0.0, S - leg.strike)
        else:
            option_value = max(0.0, leg.strike - S)
        total += (option_value - leg.entry) * leg.qty
    return total


def find_breakevens(legs: list[OptionLeg], S0: float) -> list[float]:
    hi = max(S0 * 5, 1000.0)
    prices = np.linspace(0.01, hi, 5000)
    pnls = np.array([payoff_at_expiry(p, legs) for p in prices])
    be = []
    for i in range(1, len(prices)):
        if pnls[i] == 0.0:
            be.append(prices[i])
        elif pnls[i - 1] * pnls[i] < 0:
            frac = -pnls[i - 1] / (pnls[i] - pnls[i - 1])
            be.append(prices[i - 1] + frac * (prices[i] - prices[i - 1]))
    if len(be) > 1:
        cleaned = [be[0]]
        for b in be[1:]:
            if abs(b - cleaned[-1]) > 0.02:
                cleaned.append(b)
        return cleaned
    return be


def safe_float(val) -> float:
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except (TypeError, ValueError):
        return 0.0


def compute_iv_rank(chain_calls, chain_puts) -> Optional[float]:
    ivs = []
    for _, row in chain_calls.iterrows():
        iv = safe_float(row.get("impliedVolatility"))
        if iv > 0:
            ivs.append(iv)
    for _, row in chain_puts.iterrows():
        iv = safe_float(row.get("impliedVolatility"))
        if iv > 0:
            ivs.append(iv)
    if len(ivs) < 5:
        return None
    current_iv = np.mean(ivs)
    iv_low = np.min(ivs)
    iv_high = np.max(ivs)
    if iv_high - iv_low < 0.001:
        return 50.0
    return (current_iv - iv_low) / (iv_high - iv_low) * 100


def run_analysis(
    ticker: str,
    legs: list[OptionLeg],
    target_expiry: Optional[str],
    output_json: bool,
):
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info
    S = safe_float(info.get("regularMarketPrice")) or safe_float(info.get("currentPrice"))
    if S == 0:
        hist = yf_ticker.history(period="1d")
        if not hist.empty:
            S = float(hist["Close"].iloc[-1])
    if S == 0:
        print(f"Error: could not fetch price for {ticker}")
        sys.exit(1)

    expirations = yf_ticker.options
    if not expirations:
        print(f"Error: no options chain found for {ticker}")
        sys.exit(1)

    expiry = find_closest_expiry(expirations, target_expiry)
    opt_chain = yf_ticker.option_chain(expiry)
    all_calls = opt_chain.calls
    all_puts = opt_chain.puts

    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    dte = (expiry_date - date.today()).days
    if dte <= 0:
        print(f"Error: expiry {expiry} is in the past")
        sys.exit(1)
    T = dte / 365.0

    iv_rank = compute_iv_rank(all_calls, all_puts)

    # ---- Greeks per leg ----
    leg_results = []
    for leg in legs:
        chain = all_calls if leg.opt_type == "call" else all_puts
        matches = chain[chain["strike"] == leg.strike]
        if matches.empty:
            idx = (chain["strike"] - leg.strike).abs().idxmin()
            match = chain.loc[idx]
            strike_used = float(match["strike"])
        else:
            match = matches.iloc[0]
            strike_used = leg.strike

        iv = safe_float(match.get("impliedVolatility"))
        if iv <= 0 or math.isnan(iv):
            iv = 0.8

        bid = safe_float(match.get("bid"))
        ask = safe_float(match.get("ask"))
        last = safe_float(match.get("lastPrice"))

        if bid and ask and bid > 0 and ask > 0:
            opt_mid = (bid + ask) / 2
        else:
            opt_mid = last

        g = black_scholes_greeks(S, strike_used, T, RISK_FREE_RATE, iv, leg.opt_type)
        current_pnl = (opt_mid - leg.entry) * leg.qty

        leg_results.append({
            "leg": leg,
            "strike_used": strike_used,
            "iv": iv,
            "opt_mid": opt_mid,
            "current_pnl": current_pnl,
            "opt_delta": g["delta"],
            "pos_delta": g["delta"] * leg.qty,
            "pos_gamma": g["gamma"] * abs(leg.qty),
            "pos_theta": g["theta"] * leg.qty,
            "pos_vega": g["vega"] * abs(leg.qty),
        })

    total_pos_delta = sum(r["pos_delta"] for r in leg_results)
    total_pos_gamma = sum(r["pos_gamma"] for r in leg_results)
    total_pos_theta = sum(r["pos_theta"] for r in leg_results)
    total_pos_vega = sum(r["pos_vega"] for r in leg_results)
    total_pnl = sum(r["current_pnl"] for r in leg_results)
    net_entry_cost = sum(leg.entry * leg.qty for leg in legs)

    # ---- Breakevens ----
    breakevens = find_breakevens(legs, S)
    breakevens = sorted(set(round(b, 2) for b in breakevens if b < S * 8))

    # ---- Payoff scenarios ----
    scenario_prices = sorted(set([
        0.01,
        round(S * 0.3, 2),
        round(S * 0.5, 2),
        round(S * 0.7, 2),
        round(S * 0.85, 2),
        round(S * 0.95, 2),
        round(S, 2),
        round(S * 1.05, 2),
        round(S * 1.15, 2),
        round(S * 1.3, 2),
        round(S * 1.5, 2),
        round(S * 2.0, 2),
        round(S * 3.0, 2),
        *breakevens,
    ]))

    scenarios = [{"price": p, "pnl": round(payoff_at_expiry(p, legs), 2)} for p in scenario_prices]

    # ---- Probabilities ----
    probs = {}
    for r in leg_results:
        leg = r["leg"]
        g = black_scholes_greeks(S, r["strike_used"], T, RISK_FREE_RATE, r["iv"], leg.opt_type)
        d2 = g["d2"]
        if leg.opt_type == "call":
            prob_itm = norm.cdf(d2)
        else:
            prob_itm = norm.cdf(-d2)
        probs[f"{leg.opt_type.title()} {leg.strike}"] = prob_itm

    prob_positive: Optional[float] = None
    if len(breakevens) == 1:
        be = breakevens[0]
        avg_iv = np.mean([r["iv"] for r in leg_results])
        # Determine which side of breakeven is profitable
        pnl_above = payoff_at_expiry(be * 1.01, legs)
        if pnl_above > 0:
            g = black_scholes_greeks(S, be, T, RISK_FREE_RATE, avg_iv, "call")
            prob_positive = norm.cdf(g["d2"])
        else:
            g = black_scholes_greeks(S, be, T, RISK_FREE_RATE, avg_iv, "put")
            prob_positive = norm.cdf(-g["d2"])
    elif len(breakevens) == 2:
        be_low = min(breakevens)
        be_high = max(breakevens)
        avg_iv = np.mean([r["iv"] for r in leg_results])
        # Check if profit zone is between or outside the breakevens
        pnl_mid = payoff_at_expiry((be_low + be_high) / 2, legs)
        if pnl_mid > 0:
            g_hi = black_scholes_greeks(S, be_high, T, RISK_FREE_RATE, avg_iv, "call")
            g_lo = black_scholes_greeks(S, be_low, T, RISK_FREE_RATE, avg_iv, "put")
            prob_positive = norm.cdf(g_hi["d2"]) - norm.cdf(-g_lo["d2"])
        else:
            pnl_above = payoff_at_expiry(be_high * 1.1, legs)
            if pnl_above > 0:
                g = black_scholes_greeks(S, be_high, T, RISK_FREE_RATE, avg_iv, "call")
                prob_positive = norm.cdf(g["d2"])
            else:
                g = black_scholes_greeks(S, be_low, T, RISK_FREE_RATE, avg_iv, "put")
                prob_positive = norm.cdf(-g["d2"])
        if prob_positive is not None:
            prob_positive = max(0.0, min(1.0, prob_positive))

    # ---- Build output ----
    header = (
        f"  {ticker}  |  ${S:.2f}  |  "
        f"IV ~{np.mean([r['iv'] for r in leg_results])*100:.0f}%  |  "
        f"Exp {expiry}  ({dte}d)"
    )

    lines = []
    lines.append("")
    lines.append("=" * len(header))
    lines.append(header)
    lines.append("=" * len(header))
    lines.append("")

    lines.append(
        f"  {'Leg':<27s} {'Opt Δ':>7s}  {'Pos Δ':>7s}  "
        f"{'Pos Γ':>7s}  {'Pos Θ/d':>8s}  {'Pos V/%IV':>10s}  {'PnL':>8s}"
    )
    lines.append("  " + "-" * 84)

    for r in leg_results:
        leg = r["leg"]
        label = leg.side_label()
        lines.append(
            f"  {label:<27s} {r['opt_delta']:>+7.3f}  {r['pos_delta']:>+7.3f}  "
            f"{r['pos_gamma']:>7.4f}  {r['pos_theta']:>+8.4f}  {r['pos_vega']:>10.3f}  "
            f"${r['current_pnl']:>+7.2f}"
        )

    lines.append("  " + "-" * 84)
    lines.append(
        f"  {'TOTALE':<27s} {'':>7s}  {total_pos_delta:>+7.3f}  "
        f"{total_pos_gamma:>7.4f}  {total_pos_theta:>+8.4f}  {total_pos_vega:>10.3f}  "
        f"${total_pnl:>+7.2f}"
    )

    if abs(total_pos_delta) > 0.01:
        lines.append(f"  {'  (equivalent shares)':<27s} {'':>7s}  {total_pos_delta * 100:>6.0f} sh")

    lines.append("")
    if net_entry_cost < 0:
        lines.append(f"  Net entry: ${abs(net_entry_cost):.2f}/sh CREDIT (received)")
    else:
        lines.append(f"  Net entry: ${net_entry_cost:.2f}/sh DEBIT (paid)")
    lines.append(f"  Current P&L:   ${total_pnl:+.2f}/sh  (${total_pnl * 100:+.0f} per set)")

    if breakevens:
        be_str = ",  ".join(f"${b:.2f}" for b in breakevens)
        lines.append(f"  Breakeven(s):  {be_str}")
    else:
        lines.append("  Breakeven(s):  none  (always profitable or always losing)")

    if iv_rank is not None:
        lines.append(f"  IV Rank:       {iv_rank:.0f}%")
    lines.append("")

    # Scenarios
    lines.append(f"  {'──── Expiry Payoff Scenarios ────':^60s}")
    lines.append(f"  {'Price':>10s}  {'P&L/sh':>9s}  {'P&L/set':>9s}")
    for sc in scenarios:
        p = sc["price"]
        pnl = sc["pnl"]
        marker = ""
        if p in breakevens:
            marker = "  ← BE"
        lines.append(f"  ${p:>7.2f}  ${pnl:>+8.2f}  ${pnl*100:>+8.0f}{marker}")

    lines.append("")

    # Probabilities
    lines.append(f"  {'── Probabilities (lognormal) ──':^50s}")
    for label in sorted(probs):
        lines.append(f"  {label:<18s} ITM: {probs[label]*100:>5.1f}%")
    if prob_positive is not None:
        lines.append(f"  {'P&L > $0':<18s}      {prob_positive*100:>5.1f}%")
    lines.append("")

    # ---- Recommendations ----
    lines.append(f"  {'── Recommendations ──':^40s}")
    lines.append("")

    short_puts = [l for l in legs if l.opt_type == "put" and l.qty < 0]
    short_calls = [l for l in legs if l.opt_type == "call" and l.qty < 0]

    # HOLD
    hold_why = []
    if total_pos_theta > 0.001:
        hold_why.append("positive theta (time decay works for you)")
    if total_pos_delta > 0.3 and total_pos_delta < 3.0:
        hold_why.append("moderate bullish exposure")
    if total_pos_delta < -0.3 and total_pos_delta > -3.0:
        hold_why.append("moderate bearish exposure")
    if abs(total_pnl) < 0.5:
        hold_why.append("P&L too small to justify closing costs")
    if hold_why:
        lines.append(f"  ▶ HOLD — {', '.join(hold_why)}.")

    # ADJUST
    if short_puts and total_pos_delta > 0.8:
        total_put_risk = sum(abs(l.qty) * l.strike for l in short_puts)
        lines.append(
            f"  ▶ ADJUST — Short put{'s' if len(short_puts) > 1 else ''} expose you to "
            f"${total_put_risk:.0f}/sh max downside if stock drops to zero. "
            f"Consider: (a) buy back 1 short put, (b) buy a protective put at a lower strike, "
            f"or (c) roll the puts down."
        )

    if total_pos_theta < -0.01:
        lines.append(
            f"  ▶ ADJUST — Negative theta (${abs(total_pos_theta*100):.1f}/day decay). "
            f"Time is working against you. Consider selling premium or closing before "
            f"theta accelerates in the final 60 days."
        )

    if short_calls:
        lines.append(
            "  ▶ ADJUST — Naked short call risk. Consider buying a higher-strike call "
            "to create a bear call spread and cap max loss."
        )

    if abs(total_pnl) > 3.0:
        lines.append(
            f"  ▶ ADJUST — Significant P&L (${abs(total_pnl):.2f}/sh). "
            f"Consider taking partial profits or rolling strikes to lock in gains."
        )

    if total_pos_gamma > 0.05:
        lines.append(
            f"  ▶ ADJUST — High gamma ({total_pos_gamma:.4f}). Position delta will change "
            f"rapidly with price moves. Monitor actively."
        )

    # CLOSE
    close_why = []
    if total_pnl >= 3.0:
        close_why.append(f"you are up ${total_pnl:.2f}/sh (${total_pnl * 100:.0f} per set)")
    if dte < 45:
        close_why.append("theta decay accelerates in the final weeks")
    if total_pos_gamma > 0.08:
        close_why.append("gamma risk requires constant monitoring")
    if close_why:
        lines.append(f"  ▶ CLOSE — Consider closing because {', '.join(close_why)}.")
    else:
        lines.append(f"  ▶ CLOSE — Lock in current P&L of ${total_pnl:+.2f}/sh.")

    lines.append("")
    lines.append("  " + "─" * 60)
    lines.append(f"  Data: Yahoo Finance  |  Model: Black-Scholes  |  Greeks: BS with r={RISK_FREE_RATE*100:.1f}%")
    lines.append("  Calculation engine: Python (yfinance + scipy), not LLM")
    lines.append("")

    output = "\n".join(lines)

    if output_json:
        import json
        result = {
            "meta": {
                "ticker": ticker,
                "price": S,
                "expiry": expiry,
                "dte": dte,
                "avg_iv": float(np.mean([r["iv"] for r in leg_results])),
                "iv_rank": iv_rank,
            },
            "legs": [
                {
                    "type": r["leg"].opt_type,
                    "strike": r["leg"].strike,
                    "qty": r["leg"].qty,
                    "entry": r["leg"].entry,
                    "current_mid": r["opt_mid"],
                    "iv": r["iv"],
                    "opt_delta": round(r["opt_delta"], 6),
                    "pos_delta": round(r["pos_delta"], 6),
                    "pos_gamma": round(r["pos_gamma"], 6),
                    "pos_theta": round(r["pos_theta"], 6),
                    "pos_vega": round(r["pos_vega"], 6),
                    "current_pnl": round(r["current_pnl"], 2),
                }
                for r in leg_results
            ],
            "position": {
                "delta": round(total_pos_delta, 4),
                "gamma": round(total_pos_gamma, 6),
                "theta": round(total_pos_theta, 6),
                "vega": round(total_pos_vega, 6),
                "equiv_shares": int(round(total_pos_delta * 100)),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_per_set": round(total_pnl * 100, 0),
                "net_entry_cost": round(net_entry_cost, 2),
            },
            "breakevens": breakevens,
            "prob_positive": round(prob_positive, 4) if prob_positive is not None else None,
            "scenarios": scenarios,
        }
        print(json.dumps(result, indent=2))
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze multi-leg options positions with Greeks, scenarios, and recommendations"
    )
    parser.add_argument("ticker", type=str, help="Stock/ETF ticker symbol")
    parser.add_argument(
        "--leg",
        action="append",
        required=True,
        help='Position leg: "type strike qty entry"  e.g. "call 59 1 14.71"',
    )
    parser.add_argument("--expiry", type=str, help="Target expiration date YYYY-MM-DD")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    legs: list[OptionLeg] = []
    for leg_str in args.leg:
        parts = leg_str.split()
        if len(parts) != 4:
            print("Error: each --leg must have exactly 4 parts: type strike qty entry")
            print(f"  Got: {leg_str}")
            sys.exit(1)
        try:
            legs.append(OptionLeg(parts[0], float(parts[1]), int(parts[2]), float(parts[3])))
        except ValueError as e:
            print(f"Error parsing leg '{leg_str}': {e}")
            sys.exit(1)

    run_analysis(args.ticker, legs, args.expiry, args.output == "json")


if __name__ == "__main__":
    main()
