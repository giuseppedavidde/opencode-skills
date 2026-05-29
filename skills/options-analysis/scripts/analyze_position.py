#!/usr/bin/env python3
"""
Options Position Analyzer

Analyzes multi-leg options positions: Greeks, payoff scenarios, probabilities,
strategy classification (Options Playbook), Volume Profile (1yr), and
sentiment (Trading Against the Crowd).

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


# ───── Strategy Classification (Options Playbook) ─────


def classify_strategy(legs: list[OptionLeg], total_pos_delta: float) -> dict:
    n_calls = sum(1 for l in legs if l.opt_type == "call")
    n_puts = sum(1 for l in legs if l.opt_type == "put")
    long_calls = [l for l in legs if l.opt_type == "call" and l.qty > 0]
    short_calls = [l for l in legs if l.opt_type == "call" and l.qty < 0]
    long_puts = [l for l in legs if l.opt_type == "put" and l.qty > 0]
    short_puts = [l for l in legs if l.opt_type == "put" and l.qty < 0]

    structure = "Unknown"
    outlook = "Neutral"
    risk_profile = "Defined"

    if n_calls == 1 and n_puts == 0:
        if long_calls:
            structure = "Long Call"
            outlook = "Bullish"
            risk_profile = "Limited (premium paid)"
        elif short_calls:
            structure = "Short Call"
            outlook = "Bearish"
            risk_profile = "Unlimited"

    elif n_puts == 1 and n_calls == 0:
        if long_puts:
            structure = "Long Put"
            outlook = "Bearish"
            risk_profile = "Limited (premium paid)"
        elif short_puts:
            structure = "Short Put"
            outlook = "Bullish"
            risk_profile = "Substantial (strike - premium)"

    elif long_calls and short_calls:
        if len(long_calls) == 1 and len(short_calls) == 1:
            structure = "Bull Call Spread" if long_calls[0].strike < short_calls[0].strike else "Bear Call Spread"
            outlook = "Bullish" if long_calls[0].strike < short_calls[0].strike else "Bearish"
            risk_profile = "Limited (net debit)"
        else:
            structure = "Call Ratio Spread" if len(short_calls) > len(long_calls) else "Call Back Spread"
            outlook = "Bullish" if total_pos_delta > 0 else "Bearish"
            risk_profile = "Limited"

    elif long_puts and short_puts:
        if len(long_puts) == 1 and len(short_puts) == 1:
            structure = "Bear Put Spread" if long_puts[0].strike < short_puts[0].strike else "Bull Put Spread"
            outlook = "Bearish" if long_puts[0].strike < short_puts[0].strike else "Bullish"
            risk_profile = "Limited (net debit)"
        else:
            structure = "Put Ratio Spread" if len(short_puts) > len(long_puts) else "Put Back Spread"
            outlook = "Bearish" if total_pos_delta < 0 else "Bullish"
            risk_profile = "Limited"

    elif long_calls and short_puts:
        total_long_call_qty = sum(l.qty for l in long_calls)
        total_short_put_qty = sum(abs(l.qty) for l in short_puts)
        if total_long_call_qty == 1 and total_short_put_qty == 1:
            structure = "Long Combination (Synthetic Long)"
            outlook = "Bullish"
            risk_profile = "Limited upside, substantial downside"
        elif total_short_put_qty > total_long_call_qty:
            structure = f"Bullish Long Combination (1:{total_short_put_qty} Ratio)"
            outlook = "Bullish"
            risk_profile = f"Substantial downside ({total_short_put_qty}x naked put{'s' if total_short_put_qty > 1 else ''})"
        else:
            structure = "Bullish Back Spread"
            outlook = "Bullish"
            risk_profile = "Limited"

    elif long_puts and short_calls:
        structure = "Short Combination (Synthetic Short)"
        outlook = "Bearish"
        risk_profile = "Unlimited upside risk"

    elif long_calls and long_puts:
        if len(long_calls) == 1 and len(long_puts) == 1 and abs(long_calls[0].strike - long_puts[0].strike) < 0.5:
            structure = "Long Straddle"
            outlook = "Volatile"
            risk_profile = "Limited (premium paid)"
        elif len(long_calls) == 1 and len(long_puts) == 1:
            structure = "Long Strangle"
            outlook = "Volatile"
            risk_profile = "Limited (premium paid)"

    elif short_calls and short_puts:
        if len(short_calls) == 1 and len(short_puts) == 1 and abs(short_calls[0].strike - short_puts[0].strike) < 0.5:
            structure = "Short Straddle"
            outlook = "Neutral"
            risk_profile = "Unlimited"
        elif len(short_calls) == 1 and len(short_puts) == 1:
            structure = "Short Strangle"
            outlook = "Neutral"
            risk_profile = "Unlimited"

    elif short_calls and short_puts and long_calls and long_puts:
        structure = "Iron Condor / Iron Butterfly"
        outlook = "Neutral"
        risk_profile = "Limited (width - credit)"

    return {
        "structure": structure,
        "outlook": outlook,
        "risk_profile": risk_profile,
    }


# ───── Volume Profile (1 anno) ─────


def compute_volume_profile(hist, n_bins: int = 60) -> Optional[dict]:
    if hist.empty or len(hist) < 20:
        return None
    hist = hist.dropna(subset=["Close", "Volume"])
    if hist.empty:
        return None

    prices = hist["Close"].values
    volumes = hist["Volume"].values
    lo, hi = np.min(prices), np.max(prices)
    if hi - lo < 0.01:
        return None

    bins = np.linspace(lo, hi, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_idx = np.digitize(prices, bins) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)

    vol_per_bin = np.zeros(n_bins)
    for i, idx in enumerate(bin_idx):
        vol_per_bin[idx] += volumes[i]

    total_vol = vol_per_bin.sum()
    if total_vol == 0:
        return None

    # VPOC = bin with max volume
    vpoc_idx = int(np.argmax(vol_per_bin))
    vpoc = float(bin_centers[vpoc_idx])

    # Value Area: sorted bins descending, include until 70% of volume
    sorted_idx = np.argsort(vol_per_bin)[::-1]
    cum_vol = 0.0
    va_bins = []
    for idx in sorted_idx:
        va_bins.append(idx)
        cum_vol += vol_per_bin[idx]
        if cum_vol >= total_vol * 0.70:
            break

    vah = float(bin_centers[max(va_bins)])
    val = float(bin_centers[min(va_bins)])

    # High Volume Nodes: bins with vol > 2x average
    avg_vol_per_bin = total_vol / n_bins
    hvn_indices = [i for i in range(n_bins) if vol_per_bin[i] > avg_vol_per_bin * 2]
    hvn_zones = []
    if hvn_indices:
        hvn_indices.sort()
        start = hvn_indices[0]
        for i in range(1, len(hvn_indices)):
            if hvn_indices[i] - hvn_indices[i - 1] > 2:
                hvn_zones.append((float(bin_centers[start]), float(bin_centers[hvn_indices[i - 1]])))
                start = hvn_indices[i]
        hvn_zones.append((float(bin_centers[start]), float(bin_centers[hvn_indices[-1]])))

    # Low Volume Nodes: bins with vol < 0.3x average
    lvn_indices = [i for i in range(n_bins) if vol_per_bin[i] < avg_vol_per_bin * 0.3]
    lvn_zones = []
    if lvn_indices:
        lvn_indices.sort()
        start = lvn_indices[0]
        for i in range(1, len(lvn_indices)):
            if lvn_indices[i] - lvn_indices[i - 1] > 2:
                lvn_zones.append((float(bin_centers[start]), float(bin_centers[lvn_indices[i - 1]])))
                start = lvn_indices[i]
        lvn_zones.append((float(bin_centers[start]), float(bin_centers[lvn_indices[-1]])))

    return {
        "vpoc": round(vpoc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "hvn_zones": [(round(a, 2), round(b, 2)) for a, b in hvn_zones],
        "lvn_zones": [(round(a, 2), round(b, 2)) for a, b in lvn_zones],
    }


# ───── Sentiment (Trading Against the Crowd) ─────


def compute_sentiment(all_calls, all_puts, iv_rank: Optional[float]) -> dict:
    call_oi = int(all_calls["openInterest"].sum())
    put_oi = int(all_puts["openInterest"].sum())
    call_vol = int(all_calls["volume"].sum())
    put_vol = int(all_puts["volume"].sum())

    pc_oi = put_oi / call_oi if call_oi > 0 else None
    pc_vol = put_vol / call_vol if call_vol > 0 else None

    # Interpretation
    oi_signal = "neutral"
    if pc_oi is not None:
        if pc_oi < 0.5:
            oi_signal = "bullish (many calls open)"
        elif pc_oi > 1.2:
            oi_signal = "bearish (many puts open)"
        else:
            oi_signal = "neutral"

    vol_signal = "neutral"
    if pc_vol is not None:
        if pc_vol < 0.6:
            vol_signal = "bullish (more calls trading)"
        elif pc_vol > 1.3:
            vol_signal = "bearish (more puts trading)"
        else:
            vol_signal = "neutral"

    iv_signal = "neutral"
    if iv_rank is not None:
        if iv_rank > 80:
            iv_signal = f"IV high ({iv_rank:.0f}% rank) → options expensive, good to sell premium"
        elif iv_rank < 20:
            iv_signal = f"IV low ({iv_rank:.0f}% rank) → options cheap, good to buy premium"
        else:
            iv_signal = f"IV moderate ({iv_rank:.0f}% rank) → no extreme"

    contrarian_signal = None
    if pc_oi is not None and pc_vol is not None:
        if oi_signal.startswith("bullish") and vol_signal.startswith("bearish"):
            contrarian_signal = "Possible short-term reversal: OI bullish but volume bearish"
        elif oi_signal.startswith("bearish") and vol_signal.startswith("bullish"):
            contrarian_signal = "Possible short-term reversal: OI bearish but volume bullish"

    return {
        "pc_oi_ratio": round(pc_oi, 2) if pc_oi is not None else None,
        "pc_vol_ratio": round(pc_vol, 2) if pc_vol is not None else None,
        "oi_signal": oi_signal,
        "vol_signal": vol_signal,
        "iv_signal": iv_signal,
        "contrarian_signal": contrarian_signal,
    }


# ───── Run Analysis ─────


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

    # ---- Historical data for Volume Profile ----
    hist_1y = yf_ticker.history(period="1y")

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
    avg_iv = float(np.mean([r["iv"] for r in leg_results]))

    # ---- Strategy Classification ----
    strategy = classify_strategy(legs, total_pos_delta)

    # ---- Volume Profile ----
    volprof = compute_volume_profile(hist_1y)

    # ---- Sentiment ----
    sent = compute_sentiment(all_calls, all_puts, iv_rank)

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
        avg_iv_for_prob = avg_iv
        pnl_above = payoff_at_expiry(be * 1.01, legs)
        if pnl_above > 0:
            g = black_scholes_greeks(S, be, T, RISK_FREE_RATE, avg_iv_for_prob, "call")
            prob_positive = norm.cdf(g["d2"])
        else:
            g = black_scholes_greeks(S, be, T, RISK_FREE_RATE, avg_iv_for_prob, "put")
            prob_positive = norm.cdf(-g["d2"])
    elif len(breakevens) == 2:
        be_low = min(breakevens)
        be_high = max(breakevens)
        avg_iv_for_prob = avg_iv
        pnl_mid = payoff_at_expiry((be_low + be_high) / 2, legs)
        if pnl_mid > 0:
            g_hi = black_scholes_greeks(S, be_high, T, RISK_FREE_RATE, avg_iv_for_prob, "call")
            g_lo = black_scholes_greeks(S, be_low, T, RISK_FREE_RATE, avg_iv_for_prob, "put")
            prob_positive = norm.cdf(g_hi["d2"]) - norm.cdf(-g_lo["d2"])
        else:
            pnl_above = payoff_at_expiry(be_high * 1.1, legs)
            if pnl_above > 0:
                g = black_scholes_greeks(S, be_high, T, RISK_FREE_RATE, avg_iv_for_prob, "call")
                prob_positive = norm.cdf(g["d2"])
            else:
                g = black_scholes_greeks(S, be_low, T, RISK_FREE_RATE, avg_iv_for_prob, "put")
                prob_positive = norm.cdf(-g["d2"])
        if prob_positive is not None:
            prob_positive = max(0.0, min(1.0, prob_positive))

    # ──── Build Output ────
    header = (
        f"  {ticker}  |  ${S:.2f}  |  "
        f"IV ~{avg_iv*100:.0f}%  |  "
        f"Exp {expiry}  ({dte}d)"
    )

    lines = []
    lines.append("")
    lines.append("=" * len(header))
    lines.append(header)
    lines.append("=" * len(header))
    lines.append("")

    # ── Strategy Classification ──
    lines.append(f"  {'── Options Playbook ──':^50s}")
    lines.append(f"  Structure:   {strategy['structure']}")
    lines.append(f"  Outlook:     {strategy['outlook']} (net Δ {total_pos_delta:+.2f})")
    lines.append(f"  Risk:        {strategy['risk_profile']}")
    if strategy["structure"] == "Unknown":
        lines.append("  (non-standard leg configuration — interpret Greeks directly)")
    lines.append("")

    # ── Greeks & P&L ──
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

    # ── Volume Profile ──
    lines.append(f"  {'── Volume Profile (1yr) ──':^50s}")
    if volprof:
        lines.append(f"  VPOC: ${volprof['vpoc']:<7.2f}  VAH: ${volprof['vah']:<7.2f}  VAL: ${volprof['val']:<7.2f}")
        if S > volprof["vah"]:
            ext = "+" if S > volprof["vah"] * 1.05 else ""
            lines.append(f"  Price vs VP:  ${S:.2f} is ${S - volprof['vah']:+.2f} above VAH{ext} (extended bullish)")
        elif S < volprof["val"]:
            lines.append(f"  Price vs VP:  ${S:.2f} is ${S - volprof['val']:+.2f} below VAL (extended bearish)")
        else:
            lines.append("  Price vs VP:  inside value area (fair price zone)")

        if volprof["hvn_zones"]:
            hvns = ",  ".join(f"${a}-${b}" for a, b in volprof["hvn_zones"][:4])
            lines.append(f"  HVN zones:    {hvns}")
        if volprof["lvn_zones"]:
            lvns = ",  ".join(f"${a}-${b}" for a, b in volprof["lvn_zones"][:4])
            lines.append(f"  LVN gaps:     {lvns}")

        # Check strikes vs volume profile
        for leg in legs:
            if leg.qty < 0 and leg.opt_type == "put":
                if volprof["val"] and leg.strike < volprof["val"]:
                    lines.append(f"  → Short put ${leg.strike} is below VAL — structurally safer zone")
                elif volprof["vpoc"] and leg.strike < volprof["vpoc"]:
                    lines.append(f"  → Short put ${leg.strike} is below VPOC — moderate safety")
            if leg.qty > 0 and leg.opt_type == "call":
                in_lvn = False
                for a, b in volprof.get("lvn_zones", []):
                    if a <= leg.strike <= b:
                        in_lvn = True
                        break
                if in_lvn:
                    lines.append(f"  → Call ${leg.strike} sits in an LVN gap — thin support below")
    else:
        lines.append("  Not enough historical data (need >20 days)")
    lines.append("")

    # ── Sentiment ──
    lines.append(f"  {'── Sentiment (Trading Against the Crowd) ──':^60s}")
    if sent["pc_oi_ratio"] is not None:
        lines.append(f"  Put/Call OI Ratio:  {sent['pc_oi_ratio']:.2f}  ({sent['oi_signal']})")
    if sent["pc_vol_ratio"] is not None:
        lines.append(f"  Put/Call Vol Ratio: {sent['pc_vol_ratio']:.2f}  ({sent['vol_signal']})")
    lines.append(f"  IV:  {sent['iv_signal']}")
    if sent["contrarian_signal"]:
        lines.append(f"  ⚠ Contrarian: {sent['contrarian_signal']}")
    else:
        lines.append("  Contrarian: No extreme signal — sentiment confirms price action")
    lines.append("")

    # ── Expiry Payoff Scenarios ──
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

    # ── Probabilities ──
    lines.append(f"  {'── Probabilities (lognormal) ──':^50s}")
    for label in sorted(probs):
        lines.append(f"  {label:<18s} ITM: {probs[label]*100:>5.1f}%")
    if prob_positive is not None:
        lines.append(f"  {'P&L > $0':<18s}      {prob_positive*100:>5.1f}%")
    lines.append("")

    # ── Recommendations ──
    lines.append(f"  {'── Recommendations ──':^40s}")
    lines.append("")

    short_puts = [l for l in legs if l.opt_type == "put" and l.qty < 0]
    short_calls = [l for l in legs if l.opt_type == "call" and l.qty < 0]

    # HOLD
    hold_why = []
    if total_pos_theta > 0.001:
        hold_why.append("positive theta (time decay works for you)")
    if total_pos_delta > 0.3 and total_pos_delta < 3.0:
        hold_why.append("moderate bullish delta")
    if total_pos_delta < -0.3 and total_pos_delta > -3.0:
        hold_why.append("moderate bearish delta")
    if abs(total_pnl) < 0.5:
        hold_why.append("P&L too small to justify closing costs")

    hold_extra = []
    if volprof and S > volprof["vah"]:
        hold_extra.append("price extended above VAH — trend is up")
    if sent["contrarian_signal"] is None and sent["oi_signal"] != "bearish":
        hold_extra.append("no sentiment extremes")

    if hold_why or hold_extra:
        all_hold = hold_why + hold_extra
        lines.append(f"  ▶ HOLD — {'. '.join(all_hold)}.")
    else:
        lines.append("  ▶ HOLD — Maintain current position.")

    # ADJUST
    adjust_lines = []

    # Short put risk
    if short_puts and total_pos_delta > 0.8:
        total_put_risk = sum(abs(l.qty) * l.strike for l in short_puts)
        adj = (
            f"  ▶ ADJUST — Short put{'s' if len(short_puts) > 1 else ''} expose you to "
            f"${total_put_risk:.0f}/sh max downside. "
        )
        if volprof:
            adj += f"VAL at ${volprof['val']:.0f} is your key level — if price breaks below, put assignment risk rises. "
        adj += "Consider: (a) buy back 1 short put, (b) buy a protective put at lower strike, or (c) roll puts down."
        adjust_lines.append(adj)

    # Negative theta
    if total_pos_theta < -0.01:
        adjust_lines.append(
            f"  ▶ ADJUST — Negative theta (${abs(total_pos_theta*100):.1f}/day decay). "
            f"Time is working against you. Consider selling premium or closing before "
            f"theta accelerates in the final 60 days."
        )

    # Short calls
    if short_calls:
        adjust_lines.append(
            "  ▶ ADJUST — Naked short call risk. Consider buying a higher-strike call "
            "to create a bear call spread and cap max loss."
        )

    # Significant P&L
    if abs(total_pnl) > 3.0:
        adjust_lines.append(
            f"  ▶ ADJUST — Significant P&L (${abs(total_pnl):.2f}/sh). "
            f"Consider taking partial profits or rolling strikes to lock in gains."
        )

    # High gamma
    if total_pos_gamma > 0.05:
        adjust_lines.append(
            f"  ▶ ADJUST — High gamma ({total_pos_gamma:.4f}). Position delta will change "
            f"rapidly with price moves. Monitor actively."
        )

    # Strategy-specific
    if strategy["structure"] in ("Bullish Long Combination (1:N Ratio)",):
        adjust_lines.append(
            "  ▶ ADJUST — This is a leveraged bullish structure. Playbook suggests: if the "
            "underlying rallies further, the short puts become safer; if it drops, consider "
            "closing the puts first to reduce max loss."
        )

    for adj_line in adjust_lines:
        lines.append(adj_line)

    # CLOSE
    close_why = []
    if total_pnl >= 3.0:
        close_why.append(f"you are up ${total_pnl:.2f}/sh (${total_pnl * 100:.0f} per set)")
    if dte < 45:
        close_why.append("theta decay accelerates in the final weeks")
    if total_pos_gamma > 0.08:
        close_why.append("gamma risk requires constant monitoring")

    if volprof and S > volprof["vah"] and S > volprof["vah"] * 1.1:
        close_why.append("price is 10%+ above VAH — extended move may revert")

    if close_why:
        lines.append(f"  ▶ CLOSE — Consider closing because {', '.join(close_why)}.")
    else:
        lines.append(f"  ▶ CLOSE — Lock in current P&L of ${total_pnl:+.2f}/sh.")

    lines.append("")
    lines.append("  " + "─" * 60)
    lines.append(f"  Data: Yahoo Finance  |  Model: Black-Scholes  |  Greeks: BS with r={RISK_FREE_RATE*100:.1f}%")
    lines.append("  Frameworks: Options Playbook / Volume Profile / Trading Against the Crowd")
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
                "avg_iv": avg_iv,
                "iv_rank": iv_rank,
            },
            "strategy": strategy,
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
            "volume_profile": volprof,
            "sentiment": sent,
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
