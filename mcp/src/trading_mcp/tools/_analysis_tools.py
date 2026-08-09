"""MCP tool registration: Analysis tools (scanner, stock, options)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from trading_mcp.analysis.scanner import (
    apply_macro_regime,
    compute_dynamic_thresholds,
    load_universe,
    load_universe_with_meta,
    parse_custom_tickers,
    process_crypto_ticker,
    process_ticker,
    recompute_patterns,
)
from trading_mcp.analysis.options_calc import analyze_options_position
from trading_mcp.analysis.signal_engine import compute_action
from trading_mcp.data.result_cache import result_cache

logger = logging.getLogger(__name__)


def register_analysis_tools(
    mcp_server: FastMCP, skills_dir: str, tickers_dir: str
) -> None:
    """Register analysis tools with the MCP server."""

    @mcp_server.tool()
    def scan_market(
        universe: str = "us_large",
        tickers: str | None = None,
        min_score: float = 50.0,
        top_n: int = 15,
        regime: str = "NORMAL",
        max_workers: int = 8,
        fetch_news: bool = True,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Scan a market universe for accumulation patterns and rank by score.

        Parallel scanning via ThreadPoolExecutor. 500 tickers in ~45s.

        Args:
            universe: Market universe (us_large, us_tech, italy, germany, ...).
            tickers: Custom comma-separated list (overrides universe).
            min_score: Min score threshold (0-100).
            top_n: Max results.
            regime: Macro window (FULL, NORMAL, SELECTIVE, DEFENSIVE).
            max_workers: Parallel workers (default 20).
            fetch_news: If True, scrape Finviz/WSB for web sentiment.
            verbose: If True, include full detail strings and sub-scores. Compress output with headroom to save tokens.
        """
        cache_params: dict[str, Any] = {
            "universe": universe,
            "tickers": tickers,
            "min_score": min_score,
            "top_n": top_n,
            "regime": regime,
            "max_workers": max_workers,
            "fetch_news": fetch_news,
        }
        cached = result_cache.get("scan_market", "BATCH", cache_params)
        if cached is not None:
            return cached

        if tickers:
            universe_list = parse_custom_tickers(tickers)
            universe_name = "custom"
            universe_meta = {
                "name": "custom", "source": "user-provided tickers",
                "as_of": None, "universe_type": "current",
                "survivorship_warning": False,
                "historical_universe_available": False,
                "notes": ["Custom ticker list via CLI"],
            }
        else:
            universe_list, universe_meta = load_universe_with_meta(universe, tickers_dir)
            universe_name = universe

        workers = min(max_workers, 50, len(universe_list))
        total = len(universe_list)
        results: list[dict] = []
        failures = 0
        t0 = time.time()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {}
            for t_dict in universe_list:
                symbol = t_dict["symbol"]
                if t_dict.get("market") == "CRYPTO":
                    future = executor.submit(_safe_process, process_crypto_ticker, t_dict, symbol, fetch_news)
                else:
                    future = executor.submit(_safe_process, process_ticker, t_dict, symbol, fetch_news)
                future_map[future] = symbol

            completed = 0
            for future in as_completed(future_map):
                completed += 1
                symbol = future_map[future]
                try:
                    result = future.result(timeout=30)
                except Exception as e:
                    logger.warning("Future timeout/error for %s: %s: %s",
                                   symbol, type(e).__name__, e)
                    result = None

                if result:
                    results.append(result)
                else:
                    failures += 1

        # ── P0: separate insufficient_data from valid results ─────────
        insufficient_data: list[dict] = []
        valid_results: list[dict] = []
        for r in results:
            if r.get("status") == "insufficient_data" or r.get("final_score") is None:
                insufficient_data.append(r)
            else:
                valid_results.append(r)

        results = valid_results

        # Only sort if results are non-empty and have final_score
        if results:
            results.sort(key=lambda r: r.get("final_score", 0) or 0, reverse=True)
        results = apply_macro_regime(results, regime)
        if results:
            results.sort(key=lambda r: r.get("final_score", 0) or 0, reverse=True)

        # ── Recompute pattern labels with dynamic thresholds ──
        if results:
            dyn_thresholds = compute_dynamic_thresholds(results)
            logger.info("Dynamic thresholds for %s: %s", universe_name,
                         {k: v for k, v in sorted(dyn_thresholds.items())})
            recompute_patterns(results, dyn_thresholds)

        filtered = [r for r in results if (r.get("final_score") or 0) >= min_score]

        elapsed = time.time() - t0

        output_results = []
        for r in filtered[:top_n]:
            dims = r.get("dimensions", [])
            if not verbose:
                dims = [{"name": d["name"], "score": d["score"]} for d in dims]

            mods = r.get("modifiers", {})
            if not verbose:
                mods = {k: v.get("score") if isinstance(v, dict) else v for k, v in mods.items()}

            sbd = r.get("sentiment_breakdown")
            if not verbose and sbd:
                sbd = {k: v for k, v in sbd.items() if v is not None}

            entry = {
                "ticker": r["symbol"],
                "final_score": r["final_score"],
                "dimensions": dims,
                "modifiers": mods,
                "indicators": r.get("indicators", {}) if verbose else {},
                "flags": r.get("flags", []),
                "sector": r.get("sector", ""),
                "price": r.get("price", 0.0),
                "pattern": r.get("pattern", ""),
            }
            if verbose:
                entry["sentiment_breakdown"] = sbd
            output_results.append(entry)

        scan_result = {
            "universe": universe_name,
            "universe_metadata": universe_meta,
            "timestamp": datetime.utcnow().isoformat(),
            "tickers_scanned": total,
            "tickers_passed": len(filtered),
            "min_score_threshold": min_score,
            "elapsed_seconds": round(elapsed, 1),
            "workers": workers,
            "failures": failures,
            "insufficient_data_count": len(insufficient_data),
            "insufficient_data_detail": [
                {
                    "ticker": d["symbol"],
                    "history_bars": d.get("history_bars", 0),
                    "required_bars": d.get("required_bars", 50),
                }
                for d in insufficient_data[:10]
            ] if insufficient_data else [],
            "results": output_results,
        }
        result_cache.set("scan_market", "BATCH", cache_params, scan_result)
        return scan_result

    @mcp_server.tool()
    def analyze_stock(
        ticker: str,
        include_options_context: bool = False,
        fetch_news: bool = True,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Deep single-stock analysis through all dimensions.

        Returns a comprehensive analysis including ``action_recommendation``
        with an operational recommendation (BUY/HOLD/AVOID) based on
        evidence-based volume profile signals (180d horizon, OOS-validated).

        Args:
            ticker: Stock ticker symbol (e.g. 'ENI.MI', 'AAPL').
            include_options_context: If True, fetch options chain data too.
            fetch_news: If True, scrape yfinance/Finviz news for web sentiment.
            verbose: If True, include full detail strings and sub-scores.
                     Compress output with headroom to save tokens.

        Returns:
            Dictionary with composite_score, verdict, confidence, dimensions,
            action_recommendation, and optional options_context.
        """
        cache_params: dict[str, Any] = {
            "include_options_context": include_options_context,
            "fetch_news": fetch_news,
        }
        cached = result_cache.get("analyze_stock", ticker, cache_params)
        if cached is not None:
            return cached

        t_dict = {"symbol": ticker, "name": ticker, "market": "US"}
        result = process_ticker(t_dict, fetch_news=fetch_news)
        if result is None:
            return {"error": f"Could not analyze ticker '{ticker}'. Check symbol or try later."}

        # ── P0 short-history guard ──────────────────────────────────
        if result.get("status") == "insufficient_data":
            return {
                "ticker": result["symbol"],
                "timestamp": datetime.utcnow().isoformat(),
                "composite_score": None,
                "verdict": "insufficient_data",
                "confidence": "N/A",
                "signal_alignment": {"bullish": 0, "total": 0, "pct": 0.0},
                "dimensions": [],
                "modifiers": {},
                "flags": [],
                "pattern": "N/A",
                "sector": "",
                "price": 0.0,
                "action_recommendation": {
                    "action": "N/A",
                    "reason": result.get("reason", "Dati insufficienti per l'analisi"),
                    "confidence": "N/A",
                },
                "status": "insufficient_data",
                "history_bars": result.get("history_bars", 0),
                "required_bars": result.get("required_bars", 50),
                "reason": result.get("reason", ""),
            }

        options_context = None
        if include_options_context:
            try:
                from trading_mcp.data.options_chain import fetch_options_chain
                options_context = fetch_options_chain(ticker)
            except Exception as e:
                options_context = {"error": f"Could not fetch options chain: {e}", "_source": "error"}

        composite_score = result["final_score"]
        dimensions = result.get("dimensions", [])
        if not verbose:
            dimensions = [{"name": d["name"], "score": d["score"]} for d in dimensions]

        modifiers = result.get("modifiers", {})
        if not verbose:
            modifiers = {k: v.get("score") if isinstance(v, dict) else v for k, v in modifiers.items()}

        sbd = result.get("sentiment_breakdown")
        if not verbose and sbd:
            sbd = {k: v for k, v in sbd.items() if v is not None}

        verdict_obj = _compute_verdict(composite_score, result.get("dimensions", []), result)

        profile_levels = result.get("profile_levels")
        action_obj = compute_action(levels=profile_levels, context=result)

        output: dict[str, Any] = {
            "ticker": result["symbol"],
            "timestamp": datetime.utcnow().isoformat(),
            "composite_score": composite_score,
            "verdict": verdict_obj["verdict"],
            "confidence": verdict_obj["confidence"],
            "signal_alignment": verdict_obj["signal_alignment"],
            "dimensions": dimensions,
            "modifiers": modifiers,
            "flags": result.get("flags", []),
            "pattern": result.get("pattern", ""),
            "sector": result.get("sector", ""),
            "price": result.get("price", 0.0),
            "action_recommendation": action_obj,
        }

        # ── P2: data freshness ─────────────────────────────────────
        try:
            from trading_mcp.data.provider import data_provider as dp
            freshness_info = dp.get_data_freshness(ticker, data_type="stock")
            output["data_freshness"] = freshness_info.get("freshness")
            output["last_data_date"] = freshness_info.get("last_data_date")
        except Exception:
            pass
        if verbose:
            output["indicators"] = result.get("indicators", {})
            output["sentiment_breakdown"] = result.get("sentiment_breakdown")
        if include_options_context:
            output["options_context"] = options_context

        result_cache.set("analyze_stock", ticker, cache_params, output)
        return output

    @mcp_server.tool()
    def analyze_options(
        ticker: str,
        legs: list[dict[str, Any]],
        expiry: str,
    ) -> dict[str, Any]:
        """Analyze a multi-leg options position.

        Computes Greeks per leg and total, payoff scenarios at 100 price levels,
        break-even points, probabilities (ITM/OTM, profit), and strategy classification
        using the Options Playbook framework.

        Supports multi-expiry positions (calendar spreads, diagonal spreads): each
        leg dict may carry an optional ``expiry`` key (YYYY-MM-DD). Per-leg expiry
        takes precedence over the global ``expiry`` parameter.

        Args:
            ticker: Stock ticker symbol.
            legs: List of leg dicts with type, strike, qty, entry_premium.
                  Each leg can optionally include "expiry" (YYYY-MM-DD) for
                  multi-expiry positions (calendar spreads, diagonals).
            expiry: Global target expiry (YYYY-MM-DD). Used for legs without
                    per-leg expiry. REQUIRED — the tool rejects calls without it.
        """
        if not expiry or str(expiry).lower() in ("null", "none", ""):
            return {"ticker": ticker, "error": "expiry is REQUIRED. Pass expiry='YYYY-MM-DD'."}

        cache_params: dict[str, Any] = {"legs": legs, "expiry": str(expiry)}
        cached = result_cache.get("analyze_options", ticker, cache_params)
        if cached is not None:
            return cached

        result = analyze_options_position(ticker, legs, expiry)
        result_cache.set("analyze_options", ticker, cache_params, result)
        return result


def _safe_process(fn, t_dict, symbol, fetch_news=True):
    try:
        return fn(t_dict, fetch_news=fetch_news)
    except Exception as e:
        logger.error("_safe_process failed for %s via %s: %s: %s",
                     symbol, fn.__name__, type(e).__name__, e)
        return None


def _compute_verdict(
    composite_score: float,
    dimensions: list[dict],
    result: dict,
) -> dict[str, Any]:
    """Compute verdict driven by volume profile (OOS-validated signal).

    SEMANTICA MEAN-REVERSION (documentata, unica per tutto il sistema):
    VP score è un composito mean-reversion con IC rank −0.068 OOS:
      - VP ≤ 40 → BUY (forward return alto atteso)
      - VP ≥ 60 → AVOID (forward return basso atteso)
      - altrimenti HOLD

    Il composite_score fornisce contesto ma non inverte il segnale VP.
    """
    bull_signals = 0
    total_signals = 0

    for dim in dimensions:
        score = dim.get("score", 50)
        name = dim.get("name", "")
        total_signals += 1
        if score >= 60:
            bull_signals += 1

    modifiers = result.get("modifiers", {})
    for mod_name in ("squeeze_play", "earnings_surprise", "clue6_test", "multi_timeframe"):
        mod = modifiers.get(mod_name, {})
        if isinstance(mod, dict):
            mod_score = mod.get("score")
        else:
            mod_score = 50
        if mod_score is None:
            mod_score = 50
        total_signals += 1
        if mod_score >= 60:
            bull_signals += 1

    sit_score = result.get("indicators", {}).get("risk_reward", 50)
    total_signals += 1
    if sit_score >= 60:
        bull_signals += 1

    alignment_pct = round(bull_signals / total_signals * 100, 1) if total_signals > 0 else 50.0

    if alignment_pct >= 80:
        confidence = "HIGH"
    elif alignment_pct >= 60:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    vp_score = result.get("profile_levels", {}).get("score", 50)

    # Mean-reversion semantics (allineata a signal_engine.py):
    # VP alto → AVOID, VP basso → BUY, VP medio → HOLD
    if vp_score <= 40:
        if composite_score >= 45:
            verdict = "Long-Term Investment"
        else:
            verdict = "Buy (60d horizon) — context mixed"
    elif vp_score >= 60:
        if composite_score <= 55:
            verdict = "Avoid / Wait"
        else:
            verdict = "Avoid (60d horizon)"
    elif composite_score >= 70:
        verdict = "Long-Term Investment"
    else:
        verdict = "Hold / Monitor"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "signal_alignment": {
            "bullish": bull_signals,
            "total": total_signals,
            "pct": alignment_pct,
        },
    }
