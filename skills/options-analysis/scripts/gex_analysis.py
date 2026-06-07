#!/usr/bin/env python3
"""
Gamma Exposure (GEX) and Max Pain Analyzer

Estimates Gamma Exposure (GEX) and Max Pain for a ticker using
Black-Scholes gamma approximations across all option expirations.

Usage:
    python3 gex_analysis.py --ticker AAPL
    python3 gex_analysis.py --ticker AAPL --json
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime
from statistics import NormalDist
from typing import Optional

# pylint: disable=import-error
# yfinance is imported lazily below
# pylint: enable=import-error

from pydantic import BaseModel, Field

phi = NormalDist().pdf
RISK_FREE_RATE = 0.05
ONE_HUNDRED = 100


class StrikeGexInfo(BaseModel):
    """GEX contribution at a single strike."""

    strike: float
    call_oi: int = 0
    put_oi: int = 0
    call_gex: float = 0.0
    put_gex: float = 0.0
    net_gex: float = 0.0


class MaxPainResult(BaseModel):
    """Max Pain calculation result."""

    strike: float
    total_pain: float
    used_expiry: str


class GexResult(BaseModel):
    """Full GEX analysis result."""

    ticker: str
    current_price: float
    fetch_date: str
    total_gex: float = 0.0
    regime: str = "NEUTRAL"
    gamma_flip_point: Optional[float] = None
    max_pain: Optional[MaxPainResult] = None
    call_wall: Optional[StrikeGexInfo] = None
    put_wall: Optional[StrikeGexInfo] = None
    top_gex_strikes: list[StrikeGexInfo] = Field(default_factory=list)
    error: Optional[str] = None


def _get_yfinance():
    """Lazy import yfinance to avoid import errors when not available."""
    # pylint: disable=import-outside-toplevel
    import yfinance as yf
    return yf


def _safe_float(val) -> float:
    """Coerce a value to float, returning 0.0 for NaN/inf/None."""
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    """Coerce a value to int, returning 0 for NaN/inf/None."""
    try:
        v = int(float(val))
        if v < 0:
            return 0
        return v
    except (TypeError, ValueError):
        return 0


def bs_gamma(spot: float, strike: float, time_to_expiry: float,
             rate: float, sigma: float) -> float:
    """
    Black-Scholes gamma.

    Args:
        spot: Current underlying price.
        strike: Option strike price.
        time_to_expiry: Time to expiration in years.
        rate: Risk-free rate.
        sigma: Implied volatility (decimal).

    Returns:
        Gamma per share.
    """
    if time_to_expiry <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma ** 2) * time_to_expiry) / \
         (sigma * math.sqrt(time_to_expiry))
    return phi(d1) / (spot * sigma * math.sqrt(time_to_expiry))


def _estimate_sigma(hist, default_vol: float = 0.3) -> float:
    """Estimate historical volatility from price data."""
    if hist is None or hist.empty or len(hist) < 10:
        return default_vol
    data = hist.copy()
    data = data.dropna(subset=["Close"])
    if len(data) < 10:
        return default_vol
    returns = data["Close"].pct_change().dropna()
    if returns.empty:
        return default_vol
    daily_std = returns.std()
    annual_std = daily_std * math.sqrt(252)
    return min(max(annual_std, 0.05), 1.5)


def _extract_iv_from_row(row) -> float:
    """Extract implied volatility from a chain row."""
    iv = _safe_float(row.get("impliedVolatility"))
    if iv <= 0 or math.isnan(iv):
        return None
    return iv


def compute_max_pain(calls, puts) -> Optional[MaxPainResult]:
    """
    Compute Max Pain: strike where aggregate option buyer loss is minimized.

    For each candidate strike k:
      cost(k) = sum over all strikes s of OI_call(s) * max(0, k - s)
              + sum over all strikes s of OI_put(s) * max(0, s - k)

    The strike with minimum total cost is Max Pain.

    Args:
        calls: DataFrame of call options (must have 'strike', may have 'openInterest').
        puts: DataFrame of put options (must have 'strike', may have 'openInterest').

    Returns:
        MaxPainResult or None.
    """
    if calls.empty and puts.empty:
        return None

    call_strikes = set(calls["strike"].unique())
    put_strikes = set(puts["strike"].unique())
    all_strikes = sorted(call_strikes | put_strikes)

    if not all_strikes:
        return None

    min_pain = float("inf")
    min_strike = all_strikes[0]

    for target_price in all_strikes:
        total_pain = 0.0

        for _, row in calls.iterrows():
            oi = _safe_int(row.get("openInterest", 0))
            strike = float(row["strike"])
            intrinsic = max(0.0, target_price - strike)
            total_pain += intrinsic * oi

        for _, row in puts.iterrows():
            oi = _safe_int(row.get("openInterest", 0))
            strike = float(row["strike"])
            intrinsic = max(0.0, strike - target_price)
            total_pain += intrinsic * oi

        if total_pain < min_pain:
            min_pain = total_pain
            min_strike = target_price

    return MaxPainResult(
        strike=float(min_strike),
        total_pain=round(min_pain, 2),
        used_expiry="",
    )


def fetch_gex_analysis(ticker_symbol: str) -> GexResult:
    """
    Fetch and compute GEX / Max Pain analysis for a ticker.

    Args:
        ticker_symbol: Stock ticker symbol.

    Returns:
        GexResult with full analysis.
    """
    result = GexResult(
        ticker=ticker_symbol,
        current_price=0.0,
        fetch_date=date.today().isoformat(),
    )

    yf = _get_yfinance()
    yf_ticker = yf.Ticker(ticker_symbol)

    try:
        info = yf_ticker.info
    except Exception as exc:
        result.error = f"Failed to fetch ticker info: {exc}"
        return result

    price = _safe_float(info.get("regularMarketPrice"))
    if price == 0 or math.isnan(price):
        price = _safe_float(info.get("currentPrice"))
    if price == 0 or math.isnan(price):
        try:
            hist_quick = yf_ticker.history(period="5d")
            if not hist_quick.empty:
                price = float(hist_quick["Close"].iloc[-1])
        except Exception:
            pass
    if price == 0 or math.isnan(price):
        result.error = f"Could not fetch current price for {ticker_symbol}"
        return result

    result.current_price = price

    try:
        expirations = yf_ticker.options
    except Exception as exc:
        result.error = f"Failed to fetch option expirations: {exc}"
        return result

    if not expirations:
        result.error = f"No options chain available for {ticker_symbol}"
        return result

    today = date.today()
    parsed_expiries = []
    for exp_str in expirations:
        try:
            days = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
            parsed_expiries.append((exp_str, days))
        except ValueError:
            continue

    future_expiries = [(e, d) for e, d in parsed_expiries if d > 0]
    future_expiries.sort(key=lambda x: x[1])

    if not future_expiries:
        result.error = "No future expirations available"
        return result

    # Estimate historical vol for fallback sigma
    try:
        hist_1y = yf_ticker.history(period="1y")
    except Exception:
        hist_1y = None

    estimated_sigma = _estimate_sigma(hist_1y)

    # GEX aggregation
    gex_by_strike: dict[float, dict] = {}
    nearest_expiry = future_expiries[0]

    for exp_str, dte in future_expiries:
        try:
            chain = yf_ticker.option_chain(exp_str)
        except Exception:
            continue

        calls = chain.calls
        puts = chain.puts
        tte = max(dte, 1) / 365.0

        # Process calls
        for _, row in calls.iterrows():
            strike = float(row["strike"])
            oi = _safe_int(row.get("openInterest", 0))

            iv = _extract_iv_from_row(row)
            if iv is None or iv <= 0:
                sigma = estimated_sigma
            else:
                sigma = iv

            gamma_per_share = bs_gamma(price, strike, tte, RISK_FREE_RATE, sigma)
            if math.isnan(gamma_per_share):
                gamma_per_share = 0.0
            gex_contrib = gamma_per_share * oi * price * ONE_HUNDRED

            if strike not in gex_by_strike:
                gex_by_strike[strike] = {"call_oi": 0, "put_oi": 0, "call_gex": 0.0, "put_gex": 0.0}

            gex_by_strike[strike]["call_oi"] += oi
            gex_by_strike[strike]["call_gex"] += gex_contrib

        # Process puts
        for _, row in puts.iterrows():
            strike = float(row["strike"])
            oi = _safe_int(row.get("openInterest", 0))

            iv = _extract_iv_from_row(row)
            if iv is None or iv <= 0:
                sigma = estimated_sigma
            else:
                sigma = iv

            gamma_per_share = bs_gamma(price, strike, tte, RISK_FREE_RATE, sigma)
            if math.isnan(gamma_per_share):
                gamma_per_share = 0.0
            gex_contrib = gamma_per_share * oi * price * ONE_HUNDRED

            if strike not in gex_by_strike:
                gex_by_strike[strike] = {"call_oi": 0, "put_oi": 0, "call_gex": 0.0, "put_gex": 0.0}

            gex_by_strike[strike]["put_oi"] += oi
            gex_by_strike[strike]["put_gex"] += gex_contrib

        # Max Pain for nearest expiry
        if exp_str == nearest_expiry[0]:
            max_pain_result = compute_max_pain(calls, puts)
            if max_pain_result:
                max_pain_result.used_expiry = exp_str
                result.max_pain = max_pain_result

    # Build sorted strike list
    strike_infos = []
    for strike, data in sorted(gex_by_strike.items()):
        net_gex = data["call_gex"] - data["put_gex"]
        info = StrikeGexInfo(
            strike=strike,
            call_oi=data["call_oi"],
            put_oi=data["put_oi"],
            call_gex=round(data["call_gex"], 1),
            put_gex=round(data["put_gex"], 1),
            net_gex=round(net_gex, 1),
        )
        strike_infos.append(info)

    # Total GEX
    total_gex = sum(s.net_gex for s in strike_infos)
    result.total_gex = round(total_gex, 1)

    # Regime
    if total_gex > 500_000:
        result.regime = "POSITIVE (strong stabilizing)"
    elif total_gex > 50_000:
        result.regime = "POSITIVE (stabilizing)"
    elif total_gex < -500_000:
        result.regime = "NEGATIVE (strong destabilizing)"
    elif total_gex < -50_000:
        result.regime = "NEGATIVE (destabilizing)"
    else:
        result.regime = "NEUTRAL"

    # Gamma flip point: strike where cumulative GEX crosses from positive to negative
    sorted_infos = sorted(strike_infos, key=lambda x: x.strike)
    cum_gex = 0.0
    flip_point = None
    for info in sorted_infos:
        prev_cum = cum_gex
        cum_gex += info.net_gex
        if flip_point is None:
            if prev_cum > 0 and cum_gex < 0:
                flip_point = info.strike
            elif prev_cum < 0 and cum_gex > 0:
                flip_point = info.strike

    result.gamma_flip_point = flip_point

    # Call Wall: strike with highest positive GEX
    max_call_gex = -float("inf")
    max_call_strike = None
    for info in strike_infos:
        if info.call_gex > max_call_gex:
            max_call_gex = info.call_gex
            max_call_strike = info

    result.call_wall = max_call_strike

    # Put Wall: strike with highest negative GEX (most positive put_gex)
    max_put_gex = -float("inf")
    max_put_strike = None
    for info in strike_infos:
        if info.put_gex > max_put_gex:
            max_put_gex = info.put_gex
            max_put_strike = info

    result.put_wall = max_put_strike

    # Top GEX strikes by absolute net GEX
    top_strikes = sorted(strike_infos, key=lambda x: abs(x.net_gex), reverse=True)[:10]
    result.top_gex_strikes = top_strikes

    return result


def format_output_text(result: GexResult) -> str:
    """Format GexResult as readable text output."""
    lines = []

    header = (
        f"  {result.ticker}  |  ${result.current_price:.2f}  |  "
        f"{result.fetch_date}"
    )
    lines.append("")
    lines.append("=" * 80)
    lines.append(header)
    lines.append("=" * 80)
    lines.append("")

    if result.error:
        lines.append(f"  ERROR: {result.error}")
        lines.append("")
        return "\n".join(lines)

    # ---- Summary ----
    lines.append(f"  Total GEX:     ${result.total_gex:,.0f}")
    lines.append(f"  Regime:        {result.regime}")

    # ---- GEX Interpretation ----
    if "POSITIVE" in result.regime:
        lines.append(
            "  → Positive GEX: market makers are long gamma → "
            "they buy dips / sell rips → damping effect. Lower realized volatility expected."
        )
    elif "NEGATIVE" in result.regime:
        lines.append(
            "  → Negative GEX: market makers are short gamma → "
            "they sell dips / buy rips → amplifying effect. Higher realized volatility expected."
        )
    else:
        lines.append(
            "  → Neutral GEX: gamma positioning is balanced. "
            "No strong stabilizing/destabilizing force."
        )

    lines.append("")

    # ---- Walls and Flip ----
    if result.gamma_flip_point is not None:
        diff_pct = (result.gamma_flip_point - result.current_price) / result.current_price * 100
        lines.append(
            f"  Gamma Flip:    ${result.gamma_flip_point:.2f} "
            f"({result.gamma_flip_point - result.current_price:+.2f} / {diff_pct:+.1f}% from spot)"
        )

    if result.call_wall:
        cw = result.call_wall
        lines.append(
            f"  Call Wall:     ${cw.strike:.0f}  (OI: {cw.call_oi:,}, GEX: ${cw.call_gex:,.0f})"
        )

    if result.put_wall:
        pw = result.put_wall
        lines.append(
            f"  Put Wall:      ${pw.strike:.0f}  (OI: {pw.put_oi:,}, GEX: -${pw.put_gex:,.0f})"
        )

    lines.append("")

    # ---- Max Pain ----
    if result.max_pain:
        mp = result.max_pain
        diff = mp.strike - result.current_price
        diff_pct = diff / result.current_price * 100
        lines.append(
            f"  Max Pain:      ${mp.strike:.2f} "
            f"({diff:+.2f} / {diff_pct:+.1f}% from spot)  "
            f"Exp: {mp.used_expiry}  Pain: ${mp.total_pain:,.0f}"
        )
        lines.append(
            f"  → Max Pain Theory: price gravitates toward ${mp.strike:.2f} "
            f"as expiration approaches."
        )
        lines.append("")

    # ---- Top GEX Strikes ----
    lines.append(f"  {'── Top 10 Strikes by |Net GEX| ──':^53s}")
    header_row = (
        f"  {'Strike':>8s}  {'Call OI':>10s}  {'Put OI':>9s}  "
        f"{'Call GEX':>12s}  {'Put GEX':>12s}  {'Net GEX':>12s}"
    )
    lines.append(header_row)
    lines.append("  " + "-" * 76)

    for info in result.top_gex_strikes:
        is_atm = abs(info.strike - result.current_price) / result.current_price < 0.005
        marker = " *" if is_atm else ""
        lines.append(
            f"  ${info.strike:>7.0f}  {info.call_oi:>10,}  {info.put_oi:>9,}  "
            f"${info.call_gex:>11,.0f}  -${info.put_gex:>11,.0f}  ${info.net_gex:>11,.0f}{marker}"
        )

    lines.append("")
    lines.append("  * = near current price")
    lines.append("")
    lines.append("  " + "─" * 60)
    lines.append("  Data: Yahoo Finance  |  Engine: Python (yfinance)")
    lines.append("  Model: Black-Scholes Gamma with r=5%")
    lines.append("  GEX = Gamma_Aggregated * OI * Price * 100")
    lines.append("")

    return "\n".join(lines)


def format_output_json(result: GexResult) -> str:
    """Format GexResult as JSON string."""
    import json

    return json.dumps(
        result.model_dump(),
        indent=2,
        default=str,
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Estimate Gamma Exposure (GEX) and Max Pain for a ticker"
    )
    parser.add_argument("--ticker", type=str, required=True, help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results in JSON format",
    )
    args = parser.parse_args()

    ticker_symbol = args.ticker.strip().upper()
    if not ticker_symbol:
        print("Error: ticker must not be empty", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching GEX and Max Pain for {ticker_symbol}...", file=sys.stderr)

    result = fetch_gex_analysis(ticker_symbol)

    if result.error:
        print(f"\nError: {result.error}", file=sys.stderr)

    if args.json:
        print(format_output_json(result))
    else:
        print(format_output_text(result))

    if result.error:
        sys.exit(1)


if __name__ == "__main__":
    main()
