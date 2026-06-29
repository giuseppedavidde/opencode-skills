#!/usr/bin/env python3
"""
trading-cli — Command-line interface to the trading_mcp analysis engine.

Usage:
    trading-cli scan --universe us_large --min-score 50 --top 10
    trading-cli analyze AAPL --verbose
    trading-cli options DRAM --leg "put 45 -2 7.90" --leg "call 59 1 14.90" --expiry 2026-12-18
    trading-cli macro
    trading-cli fetch AAPL
    trading-cli knowledge wyckoff-2-0 --topic spring
    trading-cli strategy AAPL 75 "Long-Term Investment"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from trading_mcp.analysis.macro import detect_regime, get_dynamic_weights
from trading_mcp.analysis.options_calc import analyze_options_position
from trading_mcp.analysis.scanner import (
    apply_macro_regime,
    load_universe,
    parse_custom_tickers,
    process_crypto_ticker,
    process_ticker,
    set_fetch_news,
)
from trading_mcp.config import SKILLS_DIR, TICKERS_DIR
from trading_mcp.data.crypto import fetch_crypto_full
from trading_mcp.data.options_chain import fetch_options_chain
from trading_mcp.data.stocks import fetch_stock_full
from trading_mcp.knowledge.skill_bridge import SkillBridge


def cmd_scan(args: argparse.Namespace) -> dict:
    """Scan a market universe for accumulation patterns."""
    if args.tickers:
        universe_list = parse_custom_tickers(args.tickers)
        universe_name = "custom"
    else:
        universe_list = load_universe(args.universe, str(TICKERS_DIR))
        universe_name = args.universe

    set_fetch_news(args.fetch_news)
    total = len(universe_list)
    results: list[dict] = []
    failures = 0
    t0 = time.time()

    for t_dict in universe_list:
        if t_dict.get("market") == "CRYPTO":
            result = process_crypto_ticker(t_dict)
        else:
            result = process_ticker(t_dict)
        if result:
            results.append(result)
        else:
            failures += 1

    results.sort(key=lambda r: r["final_score"], reverse=True)
    results = apply_macro_regime(results, args.regime)
    results.sort(key=lambda r: r["final_score"], reverse=True)
    filtered = [r for r in results if r["final_score"] >= args.min_score]
    elapsed = time.time() - t0

    output = []
    for r in filtered[:args.top]:
        entry: dict = {
            "ticker": r["symbol"],
            "final_score": r["final_score"],
            "pattern": r.get("pattern", ""),
            "sector": r.get("sector", ""),
            "price": r.get("price", 0),
        }
        if args.verbose:
            entry["dimensions"] = r.get("dimensions", [])
            entry["modifiers"] = r.get("modifiers", {})
            entry["indicators"] = r.get("indicators", {})
            entry["sentiment_breakdown"] = r.get("sentiment_breakdown")
            entry["flags"] = r.get("flags", [])
        output.append(entry)

    return {
        "universe": universe_name,
        "tickers_scanned": total,
        "tickers_passed": len(filtered),
        "elapsed_seconds": round(elapsed, 1),
        "failures": failures,
        "results": output,
    }


def cmd_analyze(args: argparse.Namespace) -> dict:
    """Deep single-ticker analysis."""
    set_fetch_news(args.fetch_news)

    t_dict = {"symbol": args.ticker, "name": args.ticker, "market": "US"}
    result = process_ticker(t_dict)
    if result is None:
        return {"error": f"Could not analyze '{args.ticker}'"}

    composite_score = result["final_score"]

    bull_signals = 0
    total_signals = 0
    for dim in result.get("dimensions", []):
        total_signals += 1
        if dim.get("score", 50) >= 60:
            bull_signals += 1
    for mod in result.get("modifiers", {}).values():
        if isinstance(mod, dict):
            ms = mod.get("score")
            if ms is not None:
                total_signals += 1
                if ms >= 60:
                    bull_signals += 1
    sit = result.get("indicators", {}).get("risk_reward", 50)
    if sit is not None:
        total_signals += 1
        if sit >= 60:
            bull_signals += 1

    alignment_pct = round(bull_signals / total_signals * 100, 1) if total_signals > 0 else 50
    if alignment_pct >= 80:
        confidence = "HIGH"
    elif alignment_pct >= 60:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    if composite_score >= 70:
        verdict = "Long-Term Investment"
    elif composite_score >= 50:
        verdict = "Short-Term Speculation (Bullish)"
    elif composite_score >= 30:
        verdict = "Avoid / Wait"
    else:
        verdict = "Avoid / Sell"

    output: dict = {
        "ticker": result["symbol"],
        "composite_score": composite_score,
        "verdict": verdict,
        "confidence": confidence,
        "signal_alignment": {"bullish": bull_signals, "total": total_signals, "pct": alignment_pct},
        "pattern": result.get("pattern", ""),
        "sector": result.get("sector", ""),
        "price": result.get("price", 0),
        "flags": result.get("flags", []),
    }

    if args.verbose:
        output["dimensions"] = result.get("dimensions", [])
        output["modifiers"] = result.get("modifiers", {})
        output["indicators"] = result.get("indicators", {})
        output["sentiment_breakdown"] = result.get("sentiment_breakdown")

    return output


def cmd_options(args: argparse.Namespace) -> dict:
    """Analyze a multi-leg options position."""
    legs = []
    for leg_str in args.leg:
        parts = leg_str.split()
        if len(parts) == 4:
            legs.append({
                "type": parts[0],
                "strike": float(parts[1]),
                "qty": int(parts[2]),
                "entry_premium": float(parts[3]),
            })

    return analyze_options_position(args.ticker, legs, args.expiry)


def cmd_macro(_args: argparse.Namespace) -> dict:
    """Get macro context."""
    vix_val = None
    dxy_val = None
    dxy_trend = "neutral"

    try:
        import yfinance as yf
        vix_t = yf.Ticker("^VIX")
        hist = vix_t.history(period="5d")
        if not hist.empty:
            vix_val = round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass

    try:
        import yfinance as yf
        dxy_t = yf.Ticker("DX-Y.NYB")
        hist = dxy_t.history(period="1mo")
        if not hist.empty and len(hist) >= 5:
            dxy_val = round(float(hist["Close"].iloc[-1]), 2)
            dxy_prev = float(hist["Close"].iloc[-min(len(hist), 22)])
            if dxy_val > dxy_prev * 1.02:
                dxy_trend = "rising"
            elif dxy_val < dxy_prev * 0.98:
                dxy_trend = "falling"
    except Exception:
        pass

    regime = detect_regime(vix=vix_val, dxy_trend=dxy_trend)
    weights_stock = get_dynamic_weights(regime, is_crypto=False)
    weights_crypto = get_dynamic_weights(regime, is_crypto=True)

    if vix_val is not None:
        if vix_val < 15:
            macro_window = "FULL"
        elif vix_val < 25:
            macro_window = "NORMAL"
        elif vix_val < 35:
            macro_window = "SELECTIVE"
        else:
            macro_window = "DEFENSIVE"
    else:
        macro_window = "NORMAL"

    return {
        "vix": vix_val,
        "dxy": dxy_val,
        "dxy_trend": dxy_trend,
        "regime": regime.value,
        "macro_window": macro_window,
        "dynamic_weights_stock": weights_stock,
        "dynamic_weights_crypto": weights_crypto,
    }


def cmd_fetch(args: argparse.Namespace) -> dict:
    """Fetch market data."""
    if args.type == "stock":
        result = fetch_stock_full(args.symbol, args.period)
        info = result.pop("info", {})
        hist = result.pop("hist", None)
        ohlcv = []
        if hist is not None and not hist.empty:
            ohlcv = [
                {"date": str(idx), "close": round(float(r["Close"]), 2), "volume": int(r["Volume"])}
                for idx, r in hist.tail(20).iterrows()
            ]
        return {
            "ticker": result["ticker"],
            "price": result["current_price"],
            "indicators": result.get("indicators", {}),
            "recent_ohlcv": ohlcv,
        }
    elif args.type == "crypto":
        result = fetch_crypto_full(args.symbol, args.period)
        return {
            "coin_id": result["coin_id"],
            "symbol": result["symbol"],
            "price_usd": result["current_price_usd"],
            "market_cap": result.get("market_cap"),
        }
    elif args.type == "options":
        return fetch_options_chain(args.symbol, args.expiry)
    return {"error": f"Unknown type: {args.type}"}


def cmd_knowledge(args: argparse.Namespace) -> dict:
    """Get skill knowledge."""
    bridge = SkillBridge(str(SKILLS_DIR))
    try:
        content = bridge.get_skill_content(args.skill)
        files = bridge.get_skill_files(args.skill)

        if args.topic and args.topic.lower() in content.lower():
            lines = content.split("\n")
            relevant = []
            capture = False
            for line in lines:
                if args.topic.lower() in line.lower():
                    capture = True
                if capture:
                    relevant.append(line)
                    if len(relevant) > 100:
                        break
            if relevant:
                content = "\n".join(relevant)

        return {
            "skill_name": args.skill,
            "content": content[:5000] if not args.full else content,
            "files": files,
            "truncated": len(content) > 5000 and not args.full,
        }
    except ValueError as e:
        return {"error": str(e)}


def cmd_strategy(args: argparse.Namespace) -> dict:
    """Suggest options strategy."""
    verdict = args.verdict
    score = args.score
    direction = "bullish"
    if score < 60:
        direction = "neutral"

    if verdict.startswith("Avoid"):
        return {
            "ticker": args.ticker,
            "strategy_name": "No Entry",
            "description": "Verdict is Avoid/Wait.",
            "rationale": ["Score below entry threshold."],
        }

    iv_rank = 50.0
    iv_regime = "normal"

    strategy = "Bull Call Spread"
    desc = "Buy ATM Call + Sell OTM Call."

    if score >= 75 and direction == "bullish":
        strategy = "Synthetic Long 2:1"
        desc = "Sell 2x OTM Put + Buy 1x ATM Call. DTE 60-90."
    elif score >= 70 and direction == "bullish":
        strategy = "LEAPS Call"
        desc = "Buy deep ITM Call DTE 300+."
    elif direction == "neutral" and iv_regime == "high":
        strategy = "Iron Condor"
        desc = "Sell OTM Put spread + Call spread."
    elif direction == "neutral":
        strategy = "Cash-Secured Put"
        desc = "Sell ATM/OTM Put. Collect premium."

    return {
        "ticker": args.ticker,
        "strategy_name": strategy,
        "description": desc,
        "rationale": [
            f"Score {score}, verdict '{verdict}', direction: {direction}",
            f"IV rank: {iv_rank} ({iv_regime})",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="trading-cli — Market analysis CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan market for accumulation patterns")
    p_scan.add_argument("--universe", default="us_large")
    p_scan.add_argument("--tickers", help="Comma-separated ticker list")
    p_scan.add_argument("--min-score", type=float, default=50)
    p_scan.add_argument("--top", type=int, default=15)
    p_scan.add_argument("--regime", default="NORMAL")
    p_scan.add_argument("--fetch-news", action="store_true", default=True)
    p_scan.add_argument("--verbose", "-v", action="store_true")
    p_scan.add_argument("--table", action="store_true", help="Output as table (default: JSON)")

    p_analyze = sub.add_parser("analyze", help="Deep single-ticker analysis")
    p_analyze.add_argument("ticker")
    p_analyze.add_argument("--fetch-news", action="store_true", default=True)
    p_analyze.add_argument("--verbose", "-v", action="store_true")

    p_options = sub.add_parser("options", help="Analyze options position")
    p_options.add_argument("ticker")
    p_options.add_argument("--leg", action="append", required=True, help='"type strike qty entry"')
    p_options.add_argument("--expiry")

    p_macro = sub.add_parser("macro", help="Get macro context")

    p_fetch = sub.add_parser("fetch", help="Fetch market data")
    p_fetch.add_argument("type", choices=["stock", "crypto", "options"])
    p_fetch.add_argument("symbol")
    p_fetch.add_argument("--period", default="1y")
    p_fetch.add_argument("--expiry")

    p_knowledge = sub.add_parser("knowledge", help="Get skill knowledge")
    p_knowledge.add_argument("skill")
    p_knowledge.add_argument("--topic")
    p_knowledge.add_argument("--full", action="store_true")

    p_strategy = sub.add_parser("strategy", help="Suggest options strategy")
    p_strategy.add_argument("ticker")
    p_strategy.add_argument("score", type=float)
    p_strategy.add_argument("verdict")

    args = parser.parse_args()

    cmd_map = {
        "scan": cmd_scan,
        "analyze": cmd_analyze,
        "options": cmd_options,
        "macro": cmd_macro,
        "fetch": cmd_fetch,
        "knowledge": cmd_knowledge,
        "strategy": cmd_strategy,
    }

    result = cmd_map[args.command](args)

    if getattr(args, "table", False):
        if args.command == "scan" and "results" in result:
            print(f"{'Ticker':<10} {'Score':<8} {'Pattern':<25} {'Sector':<25} {'Price':<10}")
            print("-" * 78)
            for r in result["results"]:
                print(f"{r['ticker']:<10} {r['final_score']:<8} {r.get('pattern','')[:24]:<25} {r.get('sector','')[:24]:<25} {r.get('price',0):<10}")
        else:
            print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
