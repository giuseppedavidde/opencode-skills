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
import json
import math
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
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


# ───── Auto-Chain: Scanner & Deep Dive Integration ─────


def _skills_dir() -> Path:
    """Resolve the skills directory from this script location."""
    # This script is in .../options-analysis/scripts/
    # Skills dir is the parent of options-analysis
    return Path(__file__).resolve().parent.parent.parent


def _find_scanner_report(ticker: str) -> dict | None:
    """Search for an existing scanner CSV report containing the ticker."""
    skills_dir = _skills_dir()
    reports_dir = skills_dir / "market-accumulation-scanner" / "reports"
    if not reports_dir.exists():
        return None
    csv_files = sorted(reports_dir.rglob("scan_report_*.csv"), reverse=True)
    for csv_path in csv_files[:10]:
        try:
            df = pd.read_csv(csv_path)
            row = df[df["symbol"].str.upper() == ticker.upper()]
            if not row.empty:
                r = row.iloc[0].to_dict()
                return {
                    "final_score": float(r.get("final_score", 0) or 0),
                    "wyckoff": float(r.get("wyckoff", 0) or 0),
                    "volprof": float(r.get("volprof", 0) or 0),
                    "pa": float(r.get("pa", 0) or 0),
                    "sentiment": float(r.get("sentiment", 0) or 0),
                    "fundamentals": float(r.get("fundamentals", 0) or 0),
                    "competitive": float(r.get("competitive", 0) or 0),
                    "pattern": str(r.get("pattern", "N/A")),
                    "source": str(csv_path),
                }
        except Exception:
            continue
    return None


def _find_deep_dive_report(ticker: str) -> dict | None:
    """Search for an existing deep dive JSON report."""
    skills_dir = _skills_dir()
    dd_path = (
        skills_dir
        / "market-accumulation-scanner"
        / "reports"
        / "deep_dives"
        / f"deep_dive_{ticker.lower()}.json"
    )
    if dd_path.exists():
        try:
            with open(dd_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _run_scanner(ticker: str) -> dict | None:
    """Run the market-accumulation-scanner for a single ticker and parse JSON output."""
    skills_dir = _skills_dir()
    scanner_script = skills_dir / "market-accumulation-scanner" / "scripts" / "scanner.py"
    venv_python = skills_dir / "market-accumulation-scanner" / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    try:
        result = subprocess.run(
            [
                str(venv_python),
                str(scanner_script),
                "--tickers",
                ticker,
                "--json-output",
                "--fetch-news",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  Scanner error: {result.stderr[:200]}", file=sys.stderr)
            return None
        data = json.loads(result.stdout)
        if not data:
            return None
        r = data[0]
        return {
            "final_score": float(r.get("final_score", 0) or 0),
            "wyckoff": float(r.get("wyckoff", 0) or 0),
            "volprof": float(r.get("volprof", 0) or 0),
            "pa": float(r.get("pa", 0) or 0),
            "sentiment": float(r.get("sentiment", 0) or 0),
            "fundamentals": float(r.get("fundamentals", 0) or 0),
            "competitive": float(r.get("competitive", 0) or 0),
            "pattern": str(r.get("pattern", "N/A")),
            "source": "live_scan",
        }
    except Exception as e:
        print(f"  Scanner run failed: {e}", file=sys.stderr)
        return None


def _run_deep_dive(ticker: str) -> dict | None:
    """Run deep_dive.py for a single ticker and parse JSON output."""
    skills_dir = _skills_dir()
    dd_script = skills_dir / "market-accumulation-scanner" / "scripts" / "deep_dive.py"
    venv_python = skills_dir / "market-accumulation-scanner" / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)
    try:
        result = subprocess.run(
            [str(venv_python), str(dd_script), ticker, "--save"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  Deep dive error: {result.stderr[:200]}", file=sys.stderr)
            return None
        return _find_deep_dive_report(ticker)
    except Exception as e:
        print(f"  Deep dive run failed: {e}", file=sys.stderr)
        return None


def _fetch_scanner_data(ticker: str, auto_chain: bool) -> dict | None:
    """Fetch scanner data: from existing report, or run scanner if auto_chain."""
    data = _find_scanner_report(ticker)
    if data:
        print(f"  Found scanner report: {data['source']}", file=sys.stderr)
        return data
    dd = _find_deep_dive_report(ticker)
    if dd:
        print(f"  Found deep-dive report: deep_dive_{ticker.lower()}.json", file=sys.stderr)
        return {
            "final_score": float(dd.get("final_score", 0) or 0),
            "wyckoff": float(dd.get("wyckoff", {}).get("score", 0) or 0),
            "volprof": float(dd.get("volume_profile", {}).get("score", 0) or 0),
            "pa": float(dd.get("price_action", {}).get("score", 0) or 0),
            "sentiment": float(dd.get("sentiment", {}).get("score", 0) or 0),
            "fundamentals": float(dd.get("fundamentals", {}).get("score", 0) or 0),
            "competitive": 0,
            "pattern": str(dd.get("verdict", "N/A")),
            "source": "deep_dive_json",
            "deep_dive": dd,
            # Pass through v1 and v2 fields from deep_dive
            "candlestick": dd.get("candlestick"),
            "fibonacci": dd.get("fibonacci"),
            "bollinger": dd.get("bollinger"),
            "obv": dd.get("obv"),
            "support_resistance": dd.get("support_resistance"),
            "psychology": dd.get("psychology"),
            "ichimoku": dd.get("ichimoku"),
            "candlestick_advanced": dd.get("candlestick_advanced"),
            "candlestick_advanced_detail": dd.get("candlestick_advanced_detail"),
            "risk_reward": dd.get("risk_reward"),
            "psychology_advanced": dd.get("psychology_advanced"),
            "point_figure": dd.get("point_figure"),
            "ichimoku_detail": dd.get("ichimoku_detail"),
            "risk_reward_detail": dd.get("risk_reward_detail"),
            "psychology_advanced_detail": dd.get("psychology_advanced_detail"),
            "point_figure_detail": dd.get("point_figure_detail"),
        }
    if auto_chain:
        print(
            f"  No existing scanner report for {ticker}. Running scanner...",
            file=sys.stderr,
        )
        data = _run_scanner(ticker)
        if data:
            return data
        dd = _run_deep_dive(ticker)
        if dd:
            return {
                "final_score": float(dd.get("final_score", 0) or 0),
                "wyckoff": float(dd.get("wyckoff", {}).get("score", 0) or 0),
                "volprof": float(dd.get("volume_profile", {}).get("score", 0) or 0),
                "pa": float(dd.get("price_action", {}).get("score", 0) or 0),
                "sentiment": float(dd.get("sentiment", {}).get("score", 0) or 0),
                "fundamentals": float(dd.get("fundamentals", {}).get("score", 0) or 0),
                "competitive": 0,
                "pattern": str(dd.get("verdict", "N/A")),
                "source": "deep_dive_live",
                "deep_dive": dd,
                "candlestick": dd.get("candlestick"),
                "fibonacci": dd.get("fibonacci"),
                "bollinger": dd.get("bollinger"),
                "obv": dd.get("obv"),
                "support_resistance": dd.get("support_resistance"),
                "psychology": dd.get("psychology"),
                "ichimoku": dd.get("ichimoku"),
                "candlestick_advanced": dd.get("candlestick_advanced"),
            "candlestick_advanced_detail": dd.get("candlestick_advanced_detail"),
                "risk_reward": dd.get("risk_reward"),
                "psychology_advanced": dd.get("psychology_advanced"),
                "point_figure": dd.get("point_figure"),
                "ichimoku_detail": dd.get("ichimoku_detail"),
                "risk_reward_detail": dd.get("risk_reward_detail"),
                "psychology_advanced_detail": dd.get("psychology_advanced_detail"),
                "point_figure_detail": dd.get("point_figure_detail"),
            }
    return None


def _format_scanner_context(data: dict) -> list[str]:
    """Format scanner data into report lines."""
    lines = []
    if not data:
        return lines
    source = data.get("source", "unknown")
    label = "Live Scanner" if "live" in source or "deep_dive" in source else "Cached Report"
    lines.append(f"  {'── Scanner Context (' + label + ') ──':^60s}")
    lines.append(f"  Final Score: {data.get('final_score', 0):.1f}/100")
    lines.append(f"  Pattern:     {data.get('pattern', 'N/A')}")
    lines.append(
        f"  Wyckoff:     {data.get('wyckoff', 0):.0f}/100 | "
        f"VP: {data.get('volprof', 0):.0f}/100 | "
        f"PA: {data.get('pa', 0):.0f}/100"
    )
    lines.append(
        f"  Sentiment:   {data.get('sentiment', 0):.0f}/100 | "
        f"Fund: {data.get('fundamentals', 0):.0f}/100 | "
        f"Comp: {data.get('competitive', 0):.0f}/100"
    )
    dd = data.get("deep_dive")
    if dd:
        wyckoff = dd.get("wyckoff", {})
        vp = dd.get("volume_profile", {})
        pa = dd.get("price_action", {})
        fund = dd.get("fundamentals", {})
        lines.append("")
        lines.append(f"  Wyckoff Phase: {wyckoff.get('phase', 'N/A')}")
        lines.append(
            f"  VP Shape:      {vp.get('shape', 'N/A')} | "
            f"POC: ${vp.get('poc_price', 'N/A')} | "
            f"VAL: ${vp.get('val', 'N/A')} | "
            f"VAH: ${vp.get('vah', 'N/A')}"
        )
        lines.append(
            f"  PA Verdict:    {pa.get('verdict', 'N/A')} | "
            f"EMA25: {'▲' if pa.get('ema25_slope_up') else '▼'} | "
            f"Buildup: {'Yes' if pa.get('buildup') else 'No'}"
        )
        lines.append(
            f"  Fundamentals:  P/E {fund.get('pe_ratio', 'N/A')} | "
            f"Rev Growth {fund.get('revenue_growth_pct', 'N/A')}% | "
            f"Margins {fund.get('profit_margins_pct', 'N/A')}%"
        )
    # V2 book-concept scores
    ichi = data.get("ichimoku")
    rrw = data.get("risk_reward")
    pf = data.get("point_figure")
    if ichi is not None or rrw is not None or pf is not None:
        lines.append(
            f"  Ichimoku:     {ichi or 'N/A'}/100 | "
            f"Risk/Reward: {rrw or 'N/A'}/100 | "
            f"P&F: {pf or 'N/A'}/100"
        )
        ichi_d = data.get("ichimoku_detail", "")
        rrw_d = data.get("risk_reward_detail", "")
        if ichi_d:
            lines.append(f"  → Ichimoku: {ichi_d[:80]}")
        if rrw_d:
            lines.append(f"  → Risk/Reward: {rrw_d[:80]}")
    lines.append("")
    return lines


def compute_iv_rank(ticker: yf.Ticker, current_price: float) -> Optional[float]:
    """Compute true IV Rank using 52-week historical volatility estimation.

    True IV Rank = (current IV - HV_52w_min) / (HV_52w_max - HV_52w_min) * 100
    where HV is estimated from 20-day rolling windows of daily log returns.

    Falls back to 1-year of data if 52 weeks unavailable.
    Returns None if insufficient data.
    """
    try:
        hist_1y = ticker.history(period="1y")
    except Exception:
        return None

    if hist_1y.empty or len(hist_1y) < 30:
        return None

    closes = hist_1y["Close"].dropna().values
    if len(closes) < 30:
        return None

    # Estimate current IV from ATM options on nearest expiry
    try:
        exps = ticker.options
        if not exps:
            return None
        today = datetime.now(timezone.utc).date()
        exp_str = None
        for e in exps:
            ed = datetime.strptime(e, "%Y-%m-%d").date()
            dte = (ed - today).days
            if 7 <= dte <= 60:
                exp_str = e
                break
        if exp_str is None:
            exp_str = exps[0]
        chain = ticker.option_chain(exp_str)
        calls, puts = chain.calls, chain.puts
        combined = pd.concat([calls, puts])
        ivs = combined["impliedVolatility"].dropna()
        ivs = ivs[(ivs > 0) & (ivs < 5.0)]
        if ivs.empty:
            return None
        current_iv = float(ivs.median())
    except Exception:
        return None

    # Compute rolling 20-day historical volatility
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    window = 20
    hv_values = []
    for i in range(window, len(log_returns) + 1):
        window_rets = log_returns[i - window:i]
        mean_ret = sum(window_rets) / window
        variance = sum((r - mean_ret) ** 2 for r in window_rets) / (window - 1)
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(252)
        hv_values.append(annual_vol)

    if len(hv_values) < 5:
        return None

    hv_min = min(hv_values)
    hv_max = max(hv_values)
    if hv_max - hv_min < 0.001:
        return 50.0

    return (current_iv - hv_min) / (hv_max - hv_min) * 100


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
    scanner_data: dict | None = None,
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

    iv_rank = compute_iv_rank(yf_ticker, S)

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

    # Initialize recommendation accumulators
    hold_why = []
    close_why = []
    adjust_lines = []

    # ── Scanner-based Recommendations (enriched) ──
    if scanner_data:
        dd = scanner_data.get("deep_dive", {})
        pa = dd.get("price_action", {})
        vp = dd.get("volume_profile", {})
        wk = dd.get("wyckoff", {})
        fund = dd.get("fundamentals", {})
        psych = dd.get("psychology", {})

        # Candlestick pattern override
        candle = scanner_data.get("candlestick", 50)
        if candle >= 70:
            hold_why.append("strong bullish candlestick pattern detected")
        elif candle <= 30:
            close_why.append("bearish candlestick pattern (reversal risk)")

        # Bollinger override
        bb = scanner_data.get("bollinger", 50)
        if bb >= 75:
            hold_why.append("Bollinger Squeeze — volatility expansion imminent")
        elif bb <= 30:
            close_why.append("price at Bollinger extreme (mean reversion likely)")

        # OBV override
        obv = scanner_data.get("obv", 50)
        if obv >= 70:
            hold_why.append("OBV confirms buying pressure")
        elif obv <= 30:
            close_why.append("OBV divergence — smart money exiting")

        # S/R override
        sr = scanner_data.get("support_resistance", 50)
        if sr >= 70:
            hold_why.append("price at strong support level")
        elif sr <= 30:
            close_why.append("price at resistance / role reversal bearish")

        # Fibonacci override
        fib = scanner_data.get("fibonacci", 50)
        if fib >= 70:
            hold_why.append("price at deep Fibonacci support (61.8%/78.6%)")
        elif fib <= 30:
            close_why.append("shallow Fibonacci retracement — weak support")

        # Psychology / FOMO override
        psych_score = scanner_data.get("psychology", 50)
        if psych_score >= 70:
            hold_why.append("panic selling detected (contrarian buy signal)")
        elif psych_score <= 30:
            close_why.append("FOMO / exhaustion detected — distribution risk")

        # Deep-dive specific: Wyckoff phase
        phase = wk.get("phase", "")
        if "Distribution" in phase or "SOW" in phase:
            close_why.append(f"Wyckoff phase: {phase} — bearish structure")
        elif "Accumulation" in phase or "Spring" in phase:
            hold_why.append(f"Wyckoff phase: {phase} — bullish structure")

        # Deep-dive: EMA25 slope
        if pa.get("ema25_slope_up") is False:
            adjust_lines.append("  ▶ ADJUST — EMA25 declining (momentum loss). Consider reducing delta exposure.")

        # Deep-dive: Buildup
        if pa.get("buildup") is True:
            hold_why.append("buildup detected (pre-breakout tension)")

        # Deep-dive: P/E vs value
        pe = fund.get("pe_ratio")
        if pe is not None and pe > 50:
            close_why.append(f"P/E {pe:.1f} very high — value risk")
        elif pe is not None and pe < 15:
            hold_why.append(f"P/E {pe:.1f} attractive — value support")

        # ── NEW v2: Ichimoku, Adv Candles, Risk/Reward, Psych Advanced, P&F ──

        # Ichimoku Cloud
        ichi = scanner_data.get("ichimoku", 50)
        if ichi >= 70:
            hold_why.append("Ichimoku bullish (price above cloud, Tenkan/Kijun cross up)")
        elif ichi <= 30:
            close_why.append("Ichimoku bearish (price below cloud, bearish cross)")

        # Advanced Candlestick Patterns
        candle_adv = scanner_data.get("candlestick_advanced", 50)
        if candle_adv >= 70:
            hold_why.append("advanced bullish patterns (Piercing/Abandoned Baby)")
        elif candle_adv <= 30:
            close_why.append("advanced bearish patterns (Dark Cloud Cover/Bearish Engulf)")

        # Risk/Reward
        rrw = scanner_data.get("risk_reward", 50)
        if rrw >= 70:
            hold_why.append(f"excellent risk/reward ratio — favorable position sizing")
        elif rrw <= 30:
            close_why.append(f"poor risk/reward — reduce position or exit")

        # Psychology Advanced (Cycle of Doom)
        psych_adv = scanner_data.get("psychology_advanced", 50)
        if psych_adv >= 70:
            hold_why.append("capitulation detected — contrarian buy signal")
        elif psych_adv <= 30:
            close_why.append("euphoria/anchoring bias — distribution phase")

        # Point & Figure
        pf = scanner_data.get("point_figure", 50)
        if pf >= 70:
            hold_why.append("P&F bullish projection (accumulation columns)")
        elif pf <= 30:
            close_why.append("P&F bearish projection (distribution columns)")

    # HOLD
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
    hold_why.extend(hold_extra)

    if hold_why:
        lines.append(f"  ▶ HOLD — {'. '.join(hold_why)}.")
    else:
        lines.append("  ▶ HOLD — Maintain current position.")

    # ADJUST
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
    # ── Scanner Context ──
    if scanner_data:
        lines.extend(_format_scanner_context(scanner_data))
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
            "scanner_context": scanner_data,
        }
        print(json.dumps(result, indent=2, default=str))
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
    parser.add_argument(
        "--auto-chain",
        action="store_true",
        help="Auto-run market-accumulation-scanner / deep-dive if no cached report",
    )
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

    scanner_data = None
    if getattr(args, "auto_chain", False):
        scanner_data = _fetch_scanner_data(args.ticker, auto_chain=True)

    run_analysis(args.ticker, legs, args.expiry, args.output == "json", scanner_data)


if __name__ == "__main__":
    main()
