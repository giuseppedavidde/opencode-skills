"""MCP tool registration: single-stock and scanner tools.

``scan_market``, ``analyze_stock``, ``breakout_context`` and the
Moskowitz, Ooi & Pedersen (2012) ``tsmom_signals``.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

import numpy as np
from fastmcp import FastMCP

from trading_mcp.analysis.scanner import (
    apply_macro_regime,
    compute_dynamic_thresholds,
    load_universe_with_meta,
    parse_custom_tickers,
    process_crypto_ticker,
    process_ticker,
    recompute_patterns,
)
from trading_mcp.analysis.breakout_context import (
    build_breakout_context,
    momentum_bias_warning,
)
from trading_mcp.analysis.signal_engine import compute_action
from trading_mcp.data.prices import adjusted_close, returns as total_returns
from trading_mcp.data.provider import data_provider
from trading_mcp.data.result_cache import result_cache
from trading_mcp.data.stocks import fetch_stock
from trading_mcp.responses import (
    typed,
    AnalyzeStockResponse,
    BreakoutContextResponse,
    ScanMarketResponse,
    TSMomResult,
    error_payload,
)
from trading_mcp.timeutil import to_datetime, utc_iso

logger = logging.getLogger(__name__)

MAX_CUSTOM_TICKERS = 200
MAX_UNIVERSE_TICKERS = 1200
MAX_SCAN_TOP_N = 50
MAX_SCAN_WORKERS = 16
MIN_SCAN_DEADLINE_S = 10.0
MAX_SCAN_DEADLINE_S = 600.0
DEFAULT_SCAN_DEADLINE_S = 240.0
MAX_FAILED_LISTED = 50


def register_stock_tools(
    mcp_server: FastMCP, skills_dir: str, tickers_dir: str
) -> None:
    """Register the stock and scanner tools with the MCP server."""

    @mcp_server.tool()
    @typed(ScanMarketResponse)
    def scan_market(
        universe: str = "us_large",
        tickers: str | None = None,
        min_score: float = 50.0,
        top_n: int = 15,
        regime: str = "NORMAL",
        max_workers: int = 8,
        fetch_news: bool = False,
        verbose: bool = False,
        deadline_s: float = DEFAULT_SCAN_DEADLINE_S,
    ) -> ScanMarketResponse:
        """Scan a market universe for accumulation patterns and rank by score (complete daily bars).

        Check coverage_pct and degraded first: when tickers fail or the
        deadline cuts the scan, failed_tickers lists them, degraded is true,
        results are NOT a complete ranking, and the scan is not cached. Row
        prices come from the quote layer (price_as_of, price_source).
        Limits: at most 200 custom tickers, top_n 1-50, max_workers 1-16,
        deadline_s 10-600 (default 240).

        Args:
            universe: Market universe (us_large, us_tech, italy, germany, ...).
            tickers: Custom comma-separated list (overrides universe, max 200).
            min_score: Min score threshold (0-100).
            top_n: Max results (1-50).
            regime: Macro window (FULL, NORMAL, SELECTIVE, DEFENSIVE).
            max_workers: Parallel workers (1-16, default 8).
            fetch_news: If True, scrape Finviz/WSB for web sentiment (slow; default False).
            verbose: If True, include full detail strings and sub-scores. Default False.
            deadline_s: Wall-clock budget in seconds; unfinished tickers count as failed.
        """
        warnings: list[str] = []
        top_n_c = _clamp(top_n, 1, MAX_SCAN_TOP_N, "top_n", warnings)
        workers_c = _clamp(max_workers, 1, MAX_SCAN_WORKERS, "max_workers", warnings)
        min_score_c = _clamp(min_score, 0.0, 100.0, "min_score", warnings)
        deadline = _clamp(deadline_s, MIN_SCAN_DEADLINE_S, MAX_SCAN_DEADLINE_S, "deadline_s", warnings)
        limits = {"max_custom_tickers": MAX_CUSTOM_TICKERS, "max_universe_tickers": MAX_UNIVERSE_TICKERS,
                  "max_top_n": MAX_SCAN_TOP_N, "max_workers": MAX_SCAN_WORKERS,
                  "deadline_s": [MIN_SCAN_DEADLINE_S, MAX_SCAN_DEADLINE_S]}
        cache_params: dict[str, Any] = {
            "universe": universe,
            "tickers": tickers,
            "min_score": min_score_c,
            "top_n": top_n_c,
            "regime": regime,
            "max_workers": workers_c,
            "fetch_news": fetch_news,
        }
        cached = result_cache.get("scan_market", "BATCH", cache_params)
        if cached is not None:
            return _apply_scan_verbose_filter(cached, verbose)

        if tickers:
            universe_list = parse_custom_tickers(tickers)
            if len(universe_list) > MAX_CUSTOM_TICKERS:
                return error_payload(
                    f"{len(universe_list)} custom tickers; the limit is {MAX_CUSTOM_TICKERS}",
                    data_source="yfinance", universe="custom", limits=limits,
                )
            universe_name = "custom"
            universe_meta = {
                "name": "custom", "source": "user-provided tickers",
                "as_of": None, "universe_type": "current",
                "survivorship_warning": False,
                "historical_universe_available": False,
                "notes": ["Custom ticker list"],
            }
        else:
            universe_list, universe_meta = load_universe_with_meta(universe, tickers_dir)
            universe_name = universe
        total = len(universe_list)
        if total == 0:
            return error_payload(f"universe '{universe_name}' has no tickers", data_source="yfinance",
                                 universe=universe_name, universe_metadata=universe_meta, limits=limits)
        if total > MAX_UNIVERSE_TICKERS:
            return error_payload(f"universe '{universe_name}' has {total} tickers; the limit is "
                                 f"{MAX_UNIVERSE_TICKERS}", data_source="yfinance", universe=universe_name,
                                 limits=limits)

        workers = min(workers_c, total)
        results: list[dict] = []
        failed: list[dict[str, Any]] = []
        t0 = time.time()
        executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan")
        future_map = {}
        for t_dict in universe_list:
            fn = process_crypto_ticker if t_dict.get("market") == "CRYPTO" else process_ticker
            future = executor.submit(_safe_process, fn, t_dict, t_dict["symbol"], fetch_news, regime)
            future_map[future] = t_dict["symbol"]
        done, pending = wait(future_map, timeout=deadline)
        deadline_hit = bool(pending)
        for future in pending:
            future.cancel()
            failed.append({"ticker": future_map[future], "reason": "deadline exceeded"})
        executor.shutdown(wait=False, cancel_futures=True)
        for future in done:
            symbol = future_map[future]
            result, reason = future.result()
            if result:
                results.append(result)
            else:
                failed.append({"ticker": symbol, "reason": reason or _failure_reason(symbol)})
        if deadline_hit:
            warnings.append(f"deadline of {deadline:.0f} s reached: {len(pending)} tickers not scanned")

        # ── separate insufficient_data from valid results ─────────
        insufficient_data: list[dict] = []
        valid_results: list[dict] = []
        for r in results:
            if r.get("status") == "insufficient_data" or r.get("final_score") is None:
                insufficient_data.append(r)
            else:
                valid_results.append(r)

        results = valid_results

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

        filtered = [r for r in results if (r.get("final_score") or 0) >= min_score_c]
        elapsed = time.time() - t0

        output_results = []
        bar_times: list[str] = []
        for r in filtered[:top_n_c]:
            bars_meta = data_provider.last_hist_meta(r["symbol"], "1y")
            if bars_meta is not None and bars_meta.as_of:
                bar_times.append(bars_meta.as_of)
            output_results.append({
                "ticker": r["symbol"],
                "final_score": r["final_score"],
                "dimensions": r.get("dimensions", []),
                "modifiers": r.get("modifiers", {}),
                "indicators": r.get("indicators", {}),
                "flags": r.get("flags", []),
                "sector": r.get("sector", ""),
                "price": r.get("price"),
                "price_as_of": r.get("price_as_of"),
                "price_source": r.get("price_source"),
                "bars_as_of": bars_meta.as_of if bars_meta is not None else None,
                "pattern": r.get("pattern", ""),
                "sentiment_breakdown": r.get("sentiment_breakdown"),
            })

        processed = len(results) + len(insufficient_data)
        coverage = round(100.0 * processed / total, 1)
        degraded = bool(failed) or deadline_hit
        if failed:
            warnings.append(f"{len(failed)} of {total} tickers failed: the ranking is partial")
        scan_result: dict[str, Any] = {
            "universe": universe_name,
            "universe_metadata": universe_meta,
            "timestamp": utc_iso(),
            "as_of": min(bar_times, key=lambda v: to_datetime(v)) if bar_times else None,
            "tickers_scanned": total,
            "tickers_processed": processed,
            "tickers_passed": len(filtered),
            "coverage_pct": coverage,
            "min_score_threshold": min_score_c,
            "elapsed_seconds": round(elapsed, 1),
            "workers": workers,
            "failures": len(failed),
            "failed_tickers": failed[:MAX_FAILED_LISTED],
            "deadline_s": deadline,
            "deadline_hit": deadline_hit,
            "limits": limits,
            "degraded": degraded,
            "warnings": warnings,
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
        if processed == 0:
            scan_result.update(error=f"all {total} tickers failed; no ranking available",
                               error_kind="blocking", error_retryable=True)
        result_cache.set("scan_market", "BATCH", cache_params, scan_result)
        return _apply_scan_verbose_filter(scan_result, verbose)

    @mcp_server.tool()
    @typed(AnalyzeStockResponse)
    def analyze_stock(
        ticker: str,
        include_options_context: bool = False,
        fetch_news: bool = True,
        verbose: bool = False,
    ) -> AnalyzeStockResponse:
        """Deep single-stock analysis through all dimensions.

        Returns a comprehensive analysis including ``action_recommendation``
        with an operational recommendation (BUY/HOLD/AVOID) based on
        evidence-based volume profile signals (180d horizon, OOS-validated).

        Args:
            ticker: Stock ticker symbol (e.g. 'ENI.MI', 'AAPL').
            include_options_context: If True, fetch options chain data too.
            fetch_news: If True, scrape yfinance/Finviz news for web sentiment.
            verbose: If True, include full detail strings and sub-scores.
                     Default False.

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
            return _apply_stock_verbose_filter(cached, verbose)

        t_dict = {"symbol": ticker, "name": ticker, "market": "US"}
        result = process_ticker(t_dict, fetch_news=fetch_news)
        if result is None:
            return error_payload(
                f"Could not analyze ticker '{ticker}'. Check symbol or try later.",
                retryable=True,
                data_source="yfinance",
                ticker=ticker,
            )

        # ── P0 short-history guard ──────────────────────────────────
        if result.get("status") == "insufficient_data":
            return error_payload(
                result.get("reason", "Dati insufficienti per l'analisi"),
                kind="degraded",
                data_source="yfinance",
                ticker=result["symbol"],
                timestamp=utc_iso(),
                composite_score=None,
                verdict="insufficient_data",
                confidence="N/A",
                signal_alignment={"bullish": 0, "total": 0, "pct": None},
                dimensions=[],
                modifiers={},
                flags=[],
                pattern="N/A",
                sector="",
                price=None,
                action_recommendation={
                    "action": "N/A",
                    "reason": result.get("reason", "Dati insufficienti per l'analisi"),
                    "confidence": "N/A",
                },
                status="insufficient_data",
                history_bars=result.get("history_bars", 0),
                required_bars=result.get("required_bars", 50),
                reason=result.get("reason", ""),
            )

        options_context = None
        if include_options_context:
            try:
                from trading_mcp.data.options_chain import fetch_options_chain
                options_context = fetch_options_chain(ticker)
            except Exception as e:
                options_context = {"error": f"Could not fetch options chain: {e}", "_source": "error"}

        composite_score = result["final_score"]
        dimensions = result.get("dimensions", [])
        modifiers = result.get("modifiers", {})
        sbd = result.get("sentiment_breakdown")

        verdict_obj = _compute_verdict(composite_score, result.get("dimensions", []), result)

        profile_levels = result.get("profile_levels")
        action_obj = compute_action(levels=profile_levels, context=result)

        output: dict[str, Any] = {
            "ticker": result["symbol"],
            "timestamp": utc_iso(),
            "composite_score": composite_score,
            "verdict": verdict_obj["verdict"],
            "confidence": verdict_obj["confidence"],
            "signal_alignment": verdict_obj["signal_alignment"],
            "dimensions": dimensions,
            "modifiers": modifiers,
            "flags": result.get("flags", []),
            "pattern": result.get("pattern", ""),
            "sector": result.get("sector", ""),
            "price": result.get("price"),
            "price_as_of": result.get("price_as_of"),
            "price_source": result.get("price_source"),
            "action_recommendation": action_obj,
        }

        # ── Data freshness from the data time of the bars ───────────
        freshness_info = data_provider.get_data_freshness(ticker)
        output["data_freshness"] = freshness_info.get("freshness")
        output["last_data_date"] = freshness_info.get("last_data_date")
        output["bars_as_of"] = freshness_info.get("as_of")
        output["as_of"] = freshness_info.get("as_of")
        output["sources"] = sorted({s for s in ("yfinance:history", result.get("price_source")) if s})
        if freshness_info.get("freshness") != "current":
            output["degraded"] = True
            output.setdefault("warnings", []).append(
                f"bars are {freshness_info.get('freshness')} (last bar {freshness_info.get('last_data_date')})"
            )
        if result.get("price") is None:
            output["degraded"] = True
            output.setdefault("warnings", []).append("no quote: price is null")
        output["indicators"] = result.get("indicators", {})
        output["sentiment_breakdown"] = sbd

        # ── Momentum bias guard (retrocompatible, informational) ────────
        try:
            warning = momentum_bias_warning(fetch_stock(ticker, period="2y"))
            if warning is not None:
                output["momentum_bias_warning"] = warning
        except Exception:  # pylint: disable=broad-except
            pass

        if include_options_context:
            output["options_context"] = options_context

        result_cache.set("analyze_stock", ticker, cache_params, output)
        return _apply_stock_verbose_filter(output, verbose)


    @mcp_server.tool()
    @typed(BreakoutContextResponse)
    def breakout_context(ticker: str, include_gex: bool = True) -> BreakoutContextResponse:
        """Momentum bias-guard + conditional breakout trigger for a ticker.

        Returns a structured payload with: momentum/extension metrics, an
        explicit ``bias_guard`` that fires when a trending/momentum name would
        otherwise be mis-read with mean-reversion logic, a *conditional and NOT
        statistically certified* breakout trigger, a best-effort regime-aware
        GEX overlay, ATR-based risk levels, and the honesty disclaimer.

        The breakout trigger fires when the latest close is above the 252d high
        with volume > 2x the 20d average AND price above SMA200. Phase 1
        calibration proved that NO raw breakout configuration beat the baseline
        in-sample, so ``evidence.edge_certified`` is always False.

        Args:
            ticker: Stock ticker symbol (e.g. 'HPE', 'AAPL').
            include_gex: If True, include the best-effort GEX overlay.

        Returns:
            BreakoutContext payload (see :mod:`trading_mcp.analysis.
            breakout_context`).
        """
        cache_params: dict[str, Any] = {"include_gex": include_gex}
        cached = result_cache.get("breakout_context", ticker, cache_params)
        if cached is not None:
            return cached

        hist, meta = data_provider.get_hist_with_meta(ticker, period="2y")
        if hist.empty:
            return error_payload(
                f"Could not fetch data for '{ticker}': {meta.error or 'no bars'}",
                retryable=meta.error_kind != "not_found",
                data_source="yfinance",
                ticker=ticker.upper(),
            )

        payload = build_breakout_context(
            ticker, hist, include_gex=include_gex
        ).model_dump()
        payload["as_of"] = meta.as_of
        payload["price_as_of"] = meta.as_of
        payload["price_source"] = "last complete daily close"
        payload["sources"] = [meta.source]
        if meta.stale or meta.up_to_date is False:
            payload["degraded"] = True
            payload["warnings"] = [f"bars end at {meta.last_bar_date}; latest session {meta.last_complete_session}"]
        result_cache.set("breakout_context", ticker, cache_params, payload)
        return payload

    # ── 2. Moskowitz, Ooi & Pedersen (2012) TS-MOM ───────────────

    @mcp_server.tool()
    @typed(TSMomResult)
    def tsmom_signals(
        ticker: str,
        lookback_months: int = 12,
        skip_last_days: int = 21,
    ) -> TSMomResult:
        """Moskowitz, Ooi & Pedersen (2012) time series momentum.

        Calcola il TS-MOM signal:
          sign(return_{t-12:t-1}) con volatility scaling a target 40% annuo.

        USA IL DATAPROVIDER per i dati OHLCV.

        Args:
            ticker: Simbolo del titolo (es. 'AAPL', 'SPY').
            lookback_months: Mesi di lookback (default: 12).
            skip_last_days: Giorni da saltare (default: 21 ≈ 1 mese).

        Returns:
            dict con score TS-MOM 0-100, direzione, Sharpe stimato.
        """
        cache_params: dict[str, Any] = {
            "lookback_months": lookback_months,
            "skip_last_days": skip_last_days,
        }
        cached = result_cache.get("tsmom_signals", ticker, cache_params)
        if cached is not None:
            return cached

        # Fetch dati via DataProvider (cache hit se analyze_stock chiamato prima)
        _MIN_TSMOM_BARS = 60
        period_needed = f"{lookback_months + 3}mo"
        hist, hist_meta = data_provider.get_hist_with_meta(ticker, period=period_needed)
        avail_tsmom = len(hist) if not hist.empty else 0

        if hist.empty or avail_tsmom < _MIN_TSMOM_BARS:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Dati insufficienti per TS-MOM: {avail_tsmom} barre "
                    f"disponibili, richieste almeno {_MIN_TSMOM_BARS}."
                ),
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        close = hist["Close"]
        # Total returns from Adj Close (dividends included); levels use raw Close.
        returns = total_returns(hist)

        # Lookback period: escludi ultimi skip_last_days giorni
        total_days = len(returns)
        start_idx = max(0, total_days - lookback_months * 21 - skip_last_days)
        end_idx = max(0, total_days - skip_last_days)

        if start_idx >= end_idx:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Dati insufficienti dopo skip: start={start_idx}, end={end_idx}",
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        lookback_returns = returns.iloc[start_idx:end_idx]
        recent_returns = returns.iloc[-min(126, len(returns)):]

        if len(lookback_returns) < 20:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Lookback troppo corto: {len(lookback_returns)} giorni",
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        # TS-MOM signal (MOP 2012)
        cum_return = float((1 + lookback_returns).prod() - 1)
        signal = 1 if cum_return > 0 else -1

        # Volatility scaling (MOP 2012: target 40% annuo, EWMA vol)
        span = 60
        ewma_vol = float(recent_returns.ewm(span=span).std().iloc[-1] * np.sqrt(252))
        target_vol = 0.40
        vol_scaling = target_vol / max(ewma_vol, 0.05)
        position_size = signal * vol_scaling

        # Score 0-100
        raw_strength = float(np.clip(cum_return, -0.50, 0.50))
        mom_score = round((raw_strength + 0.50) / 1.0 * 100, 1)

        if mom_score >= 65:
            direction = "bullish"
        elif mom_score <= 35:
            direction = "bearish"
        else:
            direction = "neutral"

        # Sharpe ratio del TS-MOM nel lookback
        sharpe_lookback = float(
            lookback_returns.mean() / max(lookback_returns.std(), 1e-6) * np.sqrt(252)
        )

        # Percentuale mesi positivi
        monthly_rets = adjusted_close(hist).resample("ME").last().pct_change().dropna()
        monthly_lookback = monthly_rets.iloc[-lookback_months:]
        pct_positive = (
            float((monthly_lookback > 0).mean() * 100)
            if len(monthly_lookback) > 0
            else 50.0
        )

        tsmom_result = TSMomResult(
            ticker=ticker,
            available=True,
            price=round(float(close.iloc[-1]), 2),
            price_as_of=hist_meta.as_of,
            as_of=hist_meta.as_of,
            available_bars=avail_tsmom,
            required_bars=_MIN_TSMOM_BARS,
            lookback_months=lookback_months,
            cum_return_lookback=round(float(cum_return), 4),
            signal=signal,
            ewma_vol=round(ewma_vol, 4),
            vol_scaling=round(float(vol_scaling), 4),
            position_size=round(float(position_size), 4),
            mom_score=mom_score,
            direction=direction,
            pct_positive_months=round(pct_positive, 1),
            sharpe_lookback=round(sharpe_lookback, 4),
            target_vol=target_vol,
            paper_reference={
                "title": "Time series momentum",
                "authors": ["Tobias J. Moskowitz", "Yao Hua Ooi", "Lasse Heje Pedersen"],
                "year": 2012,
                "journal": "Journal of Financial Economics",
                "signal_formula": "sign(return_{t-12:t-1}) con volatility scaling a target 40%",
                "key_finding": (
                    "Sharpe ratio > 1.0 su portafoglio diversificato cross-asset, "
                    "universale in 58 futures su 4 asset class"
                ),
            },
        ).model_dump()

        result_cache.set("tsmom_signals", ticker, cache_params, tsmom_result)
        return tsmom_result



def _safe_process(fn, t_dict, symbol, fetch_news=False, regime=None):
    """Run one ticker; returns ``(result, failure_reason)`` and never raises."""
    try:
        return fn(t_dict, fetch_news=fetch_news, regime=regime), None
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("_safe_process failed for %s via %s: %s: %s",
                     symbol, fn.__name__, type(e).__name__, e)
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def _failure_reason(symbol: str) -> str:
    """Best explanation of a ticker that produced no result."""
    meta = data_provider.last_hist_meta(symbol, "1y")
    if meta is None:
        return "no history (fetch failed or symbol unknown)"
    if meta.error:
        return f"{meta.error_kind}: {meta.error}"
    return "no result (price below the minimum or analysis error)"


def _clamp(value, low, high, name: str, warnings: list[str]):
    """Clamp an input to its limits and record a warning when it changes."""
    clamped = type(low)(min(max(value, low), high))
    if clamped != value:
        warnings.append(f"{name}={value} clamped to {clamped} (allowed {low}..{high})")
    return clamped


def _apply_scan_verbose_filter(scan_result: dict[str, Any], verbose: bool) -> dict[str, Any]:
    """Post-lookup verbose filter (fix M1).

    The cache always stores the FULL payload; verbose filtering is applied
    on a copy at return time, so a non-verbose request never mutates the
    cached rich payload.
    """
    if verbose:
        return scan_result
    out = dict(scan_result)
    pruned: list[dict] = []
    for r in out.get("results", []):
        entry = dict(r)
        entry["dimensions"] = [{"name": d["name"], "score": d["score"]} for d in r.get("dimensions", [])]
        mods = r.get("modifiers", {})
        entry["modifiers"] = {k: v.get("score") if isinstance(v, dict) else v for k, v in mods.items()}
        sbd = r.get("sentiment_breakdown")
        if sbd:
            entry["sentiment_breakdown"] = {k: v for k, v in sbd.items() if v is not None}
        else:
            entry.pop("sentiment_breakdown", None)
        entry["indicators"] = {}
        pruned.append(entry)
    out["results"] = pruned
    return out


def _apply_stock_verbose_filter(output: dict[str, Any], verbose: bool) -> dict[str, Any]:
    """Post-lookup verbose filter for analyze_stock (fix M1)."""
    if verbose:
        return output
    out = dict(output)
    out["dimensions"] = [{"name": d["name"], "score": d["score"]} for d in output.get("dimensions", [])]
    mods = output.get("modifiers", {})
    out["modifiers"] = {k: v.get("score") if isinstance(v, dict) else v for k, v in mods.items()}
    sbd = output.get("sentiment_breakdown")
    if sbd:
        out["sentiment_breakdown"] = {k: v for k, v in sbd.items() if v is not None}
    else:
        out.pop("sentiment_breakdown", None)
    out.pop("indicators", None)
    return out


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
    # `profile_levels["score"]` is the RAW extension score (<=40 discount,
    # >=60 extended). The "Volume Profile" dimension is already inverted to
    # favorability upstream, so the >=60 bullish rule above stays valid.

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
