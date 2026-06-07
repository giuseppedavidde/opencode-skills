#!/usr/bin/env python3
"""
IV Term Structure Analyzer

Fetches and analyzes Implied Volatility term structure for a ticker.
Computes IV Rank, IV Percentile, IV Regime, and Term Structure Shape.

Usage:
    python3 iv_term_structure.py --ticker AAPL
    python3 iv_term_structure.py --ticker AAPL --json
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime
from typing import Optional

# pylint: disable=import-error
# yfinance is imported lazily below
# pylint: enable=import-error

from pydantic import BaseModel, Field

RISK_FREE_RATE = 0.05


class ExpiryIVData(BaseModel):
    """IV data for a single expiration."""

    expiry: str
    dte: int
    atm_call_iv: float
    atm_put_iv: float
    atm_iv: float
    otm_call_iv_plus10: Optional[float] = None
    otm_put_iv_minus10: Optional[float] = None


class IVTermStructureResult(BaseModel):
    """Full IV term structure analysis result."""

    ticker: str
    current_price: float
    fetch_date: str
    expirations: list[ExpiryIVData] = Field(default_factory=list)
    current_atm_iv: float
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    iv_regime: str = "NORMAL"
    term_structure_shape: str = "FLAT"
    iv_history_summary: Optional[str] = None
    skew_analysis: Optional[str] = None
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


def _find_atm_strike(chain, current_price: float):
    """Find the strike closest to current price in the chain DataFrame."""
    if chain.empty:
        return None
    idx = (chain["strike"] - current_price).abs().idxmin()
    return chain.loc[idx]


def _extract_iv_from_row(row) -> float:
    """Extract implied volatility from a chain row."""
    iv = _safe_float(row.get("impliedVolatility"))
    if iv <= 0:
        iv = _safe_float(row.get("lastPrice"))
        if iv > 0:
            iv = iv / _safe_float(row.get("strike", 1)) * 2.0
        else:
            iv = 0.3
    return iv


def _estimate_iv_from_price_range(hist) -> float:
    """Approximate IV from daily high-low range as a percentage proxy."""
    if hist.empty:
        return 0.3
    data = hist.copy()
    data = data.dropna(subset=["High", "Low", "Close"])
    if data.empty or len(data) < 5:
        return 0.3
    data["range_pct"] = (data["High"] - data["Low"]) / data["Close"]
    daily_vol = data["range_pct"].std()
    annual_vol = daily_vol * math.sqrt(252)
    return min(max(annual_vol, 0.05), 2.0)


def fetch_iv_term_structure(ticker_symbol: str) -> IVTermStructureResult:
    """
    Fetch and analyze IV term structure for a ticker.

    Args:
        ticker_symbol: Stock ticker symbol.

    Returns:
        IVTermStructureResult with full analysis.
    """
    result = IVTermStructureResult(
        ticker=ticker_symbol,
        current_price=0.0,
        fetch_date=date.today().isoformat(),
        current_atm_iv=0.0,
    )

    yf = _get_yfinance()
    yf_ticker = yf.Ticker(ticker_symbol)

    try:
        info = yf_ticker.info
    except Exception as exc:
        result.error = f"Failed to fetch ticker info: {exc}"
        return result

    price = _safe_float(info.get("regularMarketPrice"))
    if price == 0:
        price = _safe_float(info.get("currentPrice"))
    if price == 0:
        try:
            hist_quick = yf_ticker.history(period="5d")
            if not hist_quick.empty:
                price = float(hist_quick["Close"].iloc[-1])
        except Exception:
            pass
    if price == 0:
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
            parsed_expiries.append(
                (exp_str, (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days)
            )
        except ValueError:
            continue

    future_expiries = [(e, d) for e, d in parsed_expiries if d > 0]
    future_expiries.sort(key=lambda x: x[1])
    next_six = future_expiries[:6]

    if not next_six:
        result.error = "No future expirations available"
        return result

    all_atm_ivs = []

    for exp_str, dte in next_six:
        try:
            chain = yf_ticker.option_chain(exp_str)
        except Exception:
            continue

        calls = chain.calls
        puts = chain.puts

        atm_call_iv = 0.0
        atm_put_iv = 0.0
        otm_call_iv_plus10 = None
        otm_put_iv_minus10 = None

        if not calls.empty:
            atm_call = _find_atm_strike(calls, price)
            if atm_call is not None:
                atm_call_iv = _extract_iv_from_row(atm_call)

            otm_strike_call = price * 1.10
            idx_call = (calls["strike"] - otm_strike_call).abs().idxmin()
            otm_call_iv_plus10 = _extract_iv_from_row(calls.loc[idx_call])

        if not puts.empty:
            atm_put = _find_atm_strike(puts, price)
            if atm_put is not None:
                atm_put_iv = _extract_iv_from_row(atm_put)

            otm_strike_put = price * 0.90
            idx_put = (puts["strike"] - otm_strike_put).abs().idxmin()
            otm_put_iv_minus10 = _extract_iv_from_row(puts.loc[idx_put])

        atm_iv = 0.0
        if atm_call_iv > 0 and atm_put_iv > 0:
            atm_iv = (atm_call_iv + atm_put_iv) / 2
        elif atm_call_iv > 0:
            atm_iv = atm_call_iv
        elif atm_put_iv > 0:
            atm_iv = atm_put_iv

        if atm_iv > 0:
            all_atm_ivs.append(atm_iv)

        expiry_data = ExpiryIVData(
            expiry=exp_str,
            dte=dte,
            atm_call_iv=round(atm_call_iv * 100, 1),
            atm_put_iv=round(atm_put_iv * 100, 1),
            atm_iv=round(atm_iv * 100, 1),
            otm_call_iv_plus10=round(otm_call_iv_plus10 * 100, 1) if otm_call_iv_plus10 else None,
            otm_put_iv_minus10=round(otm_put_iv_minus10 * 100, 1) if otm_put_iv_minus10 else None,
        )
        result.expirations.append(expiry_data)

    if all_atm_ivs:
        result.current_atm_iv = round(all_atm_ivs[0] * 100, 1)
    else:
        result.current_atm_iv = 0.0

    # ---- Term Structure Shape ----
    if len(result.expirations) >= 2:
        ivs = [d.atm_iv for d in result.expirations]
        diffs = [ivs[i + 1] - ivs[i] for i in range(len(ivs) - 1)]
        pos_count = sum(1 for d in diffs if d > 0.5)
        neg_count = sum(1 for d in diffs if d < -0.5)
        if pos_count >= len(diffs) * 0.5:
            result.term_structure_shape = "CONTANGO"
        elif neg_count >= len(diffs) * 0.5:
            result.term_structure_shape = "BACKWARDATION"
        else:
            result.term_structure_shape = "FLAT"

    # ---- Historical IV Estimation ----
    try:
        hist = yf_ticker.history(period="1y")
    except Exception:
        hist = None

    if hist is not None and not hist.empty and len(hist) >= 20:
        iv_history = []
        for win_start in range(0, len(hist) - 20, 5):
            win = hist.iloc[win_start : win_start + 20]
            iv_est = _estimate_iv_from_price_range(win)
            iv_history.append(iv_est)

        if iv_history:
            iv_min = min(iv_history)
            iv_max = max(iv_history)
            current_iv_raw = all_atm_ivs[0] if all_atm_ivs else 0.3

            if iv_max - iv_min > 0.001:
                result.iv_rank = round(
                    (current_iv_raw - iv_min) / (iv_max - iv_min) * 100, 1
                )
            else:
                result.iv_rank = 50.0

            below_count = sum(1 for v in iv_history if v < current_iv_raw)
            result.iv_percentile = round(
                below_count / len(iv_history) * 100, 1
            )

            if result.iv_percentile is not None:
                if result.iv_percentile < 20:
                    result.iv_regime = "LOW"
                elif result.iv_percentile > 80:
                    result.iv_regime = "HIGH"
                else:
                    result.iv_regime = "NORMAL"

            result.iv_history_summary = (
                f"Min IV: {iv_min*100:.1f}% | "
                f"Max IV: {iv_max*100:.1f}% | "
                f"Samples: {len(iv_history)}"
            )
        else:
            result.iv_history_summary = "Insufficient history"
    else:
        result.iv_history_summary = "Insufficient history (<20 days)"

    # ---- Skew Analysis ----
    if result.expirations:
        first = result.expirations[0]
        if first.otm_call_iv_plus10 is not None and first.otm_put_iv_minus10 is not None:
            call_iv = first.otm_call_iv_plus10
            put_iv = first.otm_put_iv_minus10
            atm_iv = first.atm_iv
            if atm_iv > 0:
                call_skew = call_iv - atm_iv
                put_skew = put_iv - atm_iv
                if put_skew > call_skew + 2:
                    result.skew_analysis = (
                        f"Put skew elevated (+{put_skew:.1f}% vs ATM) → "
                        f"market pricing downside risk premium. "
                        f"Call IV spread: +{call_skew:.1f}%."
                    )
                elif call_skew > put_skew + 2:
                    result.skew_analysis = (
                        f"Call skew elevated (+{call_skew:.1f}% vs ATM) → "
                        f"speculative upside demand. "
                        f"Put IV spread: +{put_skew:.1f}%."
                    )
                else:
                    result.skew_analysis = (
                        f"Skew balanced: Call +{call_skew:.1f}% | "
                        f"Put +{put_skew:.1f}% vs ATM — no extreme."
                    )

    return result


def format_output_text(result: IVTermStructureResult) -> str:
    """Format IVTermStructureResult as readable text output."""
    lines = []

    header = (
        f"  {result.ticker}  |  ${result.current_price:.2f}  |  "
        f"ATM IV: {result.current_atm_iv:.1f}%  |  "
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

    # ---- IV Regime ----
    lines.append(f"  IV Regime:      {result.iv_regime}")
    rank_str = f"  IV Rank:        {result.iv_rank:.1f}%"
    lines.append(rank_str if result.iv_rank else "  IV Rank:        N/A")
    pct_str = f"  IV Percentile:  {result.iv_percentile:.1f}%"
    lines.append(pct_str if result.iv_percentile else "  IV Percentile:  N/A")
    lines.append(f"  Term Structure: {result.term_structure_shape}")
    lines.append("")

    # ---- Regime Interpretation ----
    if result.iv_regime == "HIGH":
        lines.append(
            "  Interpretation: IV is HIGH → options are expensive. "
            "Favor selling premium."
        )
    elif result.iv_regime == "LOW":
        lines.append(
            "  Interpretation: IV is LOW → options are cheap. "
            "Favor buying premium."
        )
    else:
        lines.append(
            "  Interpretation: IV is NORMAL → options are fairly priced. "
            "Both buy/sell viable."
        )

    if result.term_structure_shape == "CONTANGO":
        lines.append(
            "  Term Structure: CONTANGO → Far-dated options more expensive. "
            "Calendar spreads may benefit."
        )
    elif result.term_structure_shape == "BACKWARDATION":
        lines.append(
            "  Term Structure: BACKWARDATION → Near-dated options more "
            "expensive. Event-driven premium compression expected."
        )
    else:
        lines.append(
            "  Term Structure: FLAT → Little difference across expirations. "
            "No edge from calendar."
        )

    lines.append("")

    # ---- Skew ----
    if result.skew_analysis:
        lines.append(f"  Skew: {result.skew_analysis}")
        lines.append("")

    # ---- History Summary ----
    if result.iv_history_summary:
        lines.append(f"  History: {result.iv_history_summary}")
        lines.append("")

    # ---- Term Structure Table ----
    lines.append(f"  {'── IV Term Structure ──':^70s}")
    lines.append("")
    header_row = (
        f"  {'Expiry':>12s}  {'DTE':>5s}  "
        f"{'ATM Call':>10s}  {'ATM Put':>9s}  "
        f"{'ATM Avg':>9s}  {'+10% Call':>10s}  "
        f"{'-10% Put':>9s}"
    )
    lines.append(header_row)
    lines.append("  " + "-" * 78)

    for exp_data in result.expirations:
        call_str = f"{exp_data.atm_call_iv:.1f}%" if exp_data.atm_call_iv > 0 else "  N/A"
        put_str = f"{exp_data.atm_put_iv:.1f}%" if exp_data.atm_put_iv > 0 else "  N/A"
        atm_str = f"{exp_data.atm_iv:.1f}%" if exp_data.atm_iv > 0 else "  N/A"
        otm_c = f"{exp_data.otm_call_iv_plus10:.1f}%" if exp_data.otm_call_iv_plus10 else "  N/A"
        otm_p = f"{exp_data.otm_put_iv_minus10:.1f}%" if exp_data.otm_put_iv_minus10 else "  N/A"

        lines.append(
            f"  {exp_data.expiry:>12s}  {exp_data.dte:>5d}d  "
            f"{call_str:>10s}  {put_str:>9s}  "
            f"{atm_str:>9s}  {otm_c:>10s}  {otm_p:>9s}"
        )

    lines.append("")
    lines.append("  " + "─" * 60)
    lines.append("  Data: Yahoo Finance  |  Engine: Python (yfinance)")
    lines.append("  IV History: Estimated from daily range (proxy)")
    lines.append("")

    return "\n".join(lines)


def format_output_json(result: IVTermStructureResult) -> str:
    """Format IVTermStructureResult as JSON string."""
    import json

    return json.dumps(
        result.model_dump(),
        indent=2,
        default=str,
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Implied Volatility term structure for a ticker"
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

    print(f"Fetching IV term structure for {ticker_symbol}...", file=sys.stderr)

    result = fetch_iv_term_structure(ticker_symbol)

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
