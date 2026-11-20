"""MCP tool registration: market-wide tools (macro context)."""

from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Any

from fastmcp import FastMCP

from trading_mcp.analysis.macro import Regime, current_regime, get_dynamic_weights
from trading_mcp.data.macro_inputs import MACRO_SYMBOLS, clear_crypto_context_cache, collect_macro_inputs
from trading_mcp.data.provider import data_provider
from trading_mcp.data.risk_free import get_risk_free_provider
from trading_mcp.responses import (
    typed,
    ClearMacroCacheResponse,
    MacroContextResponse,
)
from trading_mcp.timeutil import to_datetime

logger = logging.getLogger(__name__)

# ── Macro Context TTL Cache ──────────────────────────────────
# Only complete (non-degraded) answers are kept, for 60 s at most.
_macro_cache: dict[str, Any] | None = None
_macro_cache_time: float = 0.0
_macro_lock = threading.Lock()
MACRO_CACHE_TTL: float = 60.0  # seconds

_REGIME_INPUTS = ("vix", "spx")


def _oldest_as_of(values: list[str | None]) -> str | None:
    stamps = [(to_datetime(v), v) for v in values if v]
    stamps = [(moment, raw) for moment, raw in stamps if moment is not None]
    return min(stamps)[1] if stamps else None


def _fetch_macro_context() -> dict[str, Any]:
    """Collect every input through the DataProvider and classify the regime."""
    inputs = collect_macro_inputs(data_provider)
    regime_state = current_regime(inputs)
    regime = regime_state.regime
    vix, vix3m = inputs.vix, inputs.vix3m
    term_ratio = None
    if vix.usable and vix3m.usable and vix3m.value:
        term_ratio = round(vix.value / vix3m.value, 4)  # type: ignore[operator]
    rate = inputs.rate
    warnings = list(inputs.warnings)
    if regime is Regime.UNKNOWN:
        warnings.append("regime UNKNOWN: required inputs missing; window set to DEFENSIVE")
    sources = sorted({item.source for item in (vix, vix3m, inputs.spx, inputs.dxy, rate, inputs.btc,
                                               inputs.btc_dominance, inputs.fear_greed) if item.source})
    return {
        "as_of": _oldest_as_of([getattr(inputs, name).as_of for name in _REGIME_INPUTS]),
        "timestamp": regime_state.computed_at,
        "sources": sources,
        "degraded": bool(regime_state.degraded or inputs.missing()),
        "warnings": warnings,
        "vix": vix.value if vix.usable else None,
        "vix3m": vix3m.value if vix3m.usable else None,
        "vix_term_ratio": term_ratio,
        "dxy": inputs.dxy.value,
        "dxy_trend": inputs.dxy_trend,
        "fed_rate": rate.value,
        "fed_rate_source": rate.source,
        "fed_rate_as_of": rate.as_of,
        "fallback_reason": rate.details.get("fallback_reason"),
        "btc_dominance": inputs.btc_dominance.value,
        "btc_price": inputs.btc.value,
        "fear_greed_index": inputs.fear_greed.value,
        "equity_trend": inputs.equity_trend,
        "detected_regime": regime.value,
        "macro_window": regime_state.macro_window,
        "regime": regime_state.model_dump(mode="json"),
        "inputs": {name: getattr(inputs, name).model_dump(mode="json") for name in (
            "vix", "vix3m", "spx", "dxy", "rate", "btc", "btc_dominance", "fear_greed")},
        "dynamic_weights_stock": get_dynamic_weights(regime, is_crypto=False),
        "dynamic_weights_crypto": get_dynamic_weights(regime, is_crypto=True),
    }


def register_market_tools(mcp_server: FastMCP) -> None:
    """Register the market-wide tools with the MCP server."""

    @mcp_server.tool()
    @typed(MacroContextResponse)
    def get_macro_context() -> MacroContextResponse:
        """Macro context and equity regime: VIX, VIX3M, S&P 500 trend, DXY, T-bill rate, crypto context.

        Every input has value, as_of (data time) and source in ``inputs``; a
        missing input is null and sets ``degraded``. The regime (CRISIS,
        HIGH_VOLATILITY, RANGE_BOUND, TRENDING_BULL, TRENDING_BEAR, UNKNOWN)
        uses equity inputs only, with VIX hysteresis (high band: enter 25,
        leave below 23; crisis: enter 35, leave below 32). UNKNOWN maps to the
        DEFENSIVE window. ``fed_rate`` is the ^IRX 13-week T-bill yield in
        percent; null with ``fallback_reason`` when the live value is missing.
        BTC price, BTC dominance and Fear & Greed are crypto context only.
        Complete answers are cached for 60 s (``cached``, ``cache_age_s``);
        clear_macro_cache() forces a refetch of every input.
        """
        global _macro_cache, _macro_cache_time  # pylint: disable=global-statement
        now = time.time()
        with _macro_lock:
            if _macro_cache is not None and now - _macro_cache_time <= MACRO_CACHE_TTL:
                payload = copy.deepcopy(_macro_cache)
                payload.update(cached=True, cache_age_s=round(now - _macro_cache_time, 3))
                return payload
        payload = _fetch_macro_context()
        if not payload["degraded"]:
            with _macro_lock:
                _macro_cache = copy.deepcopy(payload)
                _macro_cache_time = now
        return payload

    @mcp_server.tool()
    @typed(ClearMacroCacheResponse)
    def clear_macro_cache() -> ClearMacroCacheResponse:
        """Clear every macro cache layer: the 60 s answer, the provider quotes and bars of the macro symbols (memory and disk), the risk-free snapshot and the crypto context. The next get_macro_context call fetches every input again; the regime hysteresis state is kept."""
        global _macro_cache, _macro_cache_time  # pylint: disable=global-statement
        with _macro_lock:
            _macro_cache = None
            _macro_cache_time = 0.0
        removed = data_provider.clear_symbols(MACRO_SYMBOLS.values(), disk=True)
        get_risk_free_provider().invalidate()
        clear_crypto_context_cache()
        logger.info("Macro caches cleared by user request: %s", removed)
        return {
            "status": "ok",
            "message": "Macro caches cleared (answer, provider quotes and bars, risk-free rate, crypto context)",
            "cleared_symbols": sorted(MACRO_SYMBOLS.values()),
            "cleared_entries": removed,
        }
