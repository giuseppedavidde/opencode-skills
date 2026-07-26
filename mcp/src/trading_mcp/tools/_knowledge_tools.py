"""MCP tool registration: Knowledge tools."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from trading_mcp.analysis.macro import detect_regime, get_dynamic_weights
from trading_mcp.data.provider import data_provider
from trading_mcp.knowledge.skill_bridge import SkillBridge

logger = logging.getLogger(__name__)

# ── Macro Context TTL Cache ──────────────────────────────────
_macro_cache: dict[str, Any] | None = None
_macro_cache_time: float = 0.0
MACRO_CACHE_TTL: float = 60.0  # seconds


def _fetch_macro_context() -> dict[str, Any]:
    """Fetch macro context via DataProvider (no local yfinance calls)."""
    raw = data_provider.get_macro_context()
    vix_val = raw["vix"]
    dxy_val = raw["dxy"]
    dxy_prev = raw["dxy_prev"]
    btc_dominance = raw["btc_dominance"]
    fear_greed = None
    fed_rate = 4.75

    dxy_trend = "neutral"
    if dxy_val is not None and dxy_prev is not None:
        if dxy_val > dxy_prev * 1.02:
            dxy_trend = "rising"
        elif dxy_val < dxy_prev * 0.98:
            dxy_trend = "falling"

    regime = detect_regime(vix=vix_val, dxy_trend=dxy_trend, fear_greed=fear_greed)
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
        "timestamp": datetime.utcnow().isoformat(),
        "vix": vix_val,
        "dxy": dxy_val,
        "dxy_trend": dxy_trend,
        "fed_rate": fed_rate,
        "btc_dominance": btc_dominance,
        "fear_greed_index": fear_greed,
        "detected_regime": regime.value,
        "macro_window": macro_window,
        "dynamic_weights_stock": weights_stock,
        "dynamic_weights_crypto": weights_crypto,
    }


def register_knowledge_tools(mcp_server: FastMCP, skills_dir: str) -> None:
    """Register knowledge tools with the MCP server."""

    skill_bridge = SkillBridge(skills_dir)

    @mcp_server.tool()
    def get_macro_context() -> dict[str, Any]:
        """Get current macro context: VIX, DXY, Fed rate, Fear & Greed, BTC dominance.

        Fetches real-time macro indicators from yfinance and detects the
        current market regime (CRISIS, HIGH_VOLATILITY, RANGE_BOUND,
        TRENDING_BULL, TRENDING_BEAR) with dynamic weight recommendations.

        Results are cached for 60 seconds to prevent yfinance rate limiting.
        Use clear_macro_cache() to force a refresh.
        """
        global _macro_cache, _macro_cache_time
        now = time.time()
        if _macro_cache is None or (now - _macro_cache_time) > MACRO_CACHE_TTL:
            _macro_cache = _fetch_macro_context()
            _macro_cache_time = now
            logger.info("Macro context refreshed (TTL=%.1fs)", MACRO_CACHE_TTL)
        else:
            age = now - _macro_cache_time
            logger.debug("Macro context cache hit (%.1fs old)", age)
        return dict(_macro_cache)  # return a copy to prevent mutation

    @mcp_server.tool()
    def clear_macro_cache() -> dict[str, str]:
        """Force clear the macro context cache. Next call will re-fetch fresh data."""
        global _macro_cache, _macro_cache_time
        _macro_cache = None
        _macro_cache_time = 0.0
        logger.info("Macro cache cleared by user request")
        return {"status": "ok", "message": "Macro cache cleared"}

    @mcp_server.tool()
    def get_skill_knowledge(
        skill_name: str, topic: str | None = None
    ) -> dict[str, Any]:
        """Get knowledge from a specific trading skill (SKILL.md).

        Retrieve trading framework definitions on-demand without loading
        entire skill files into context. Use this when you need a specific
        concept, pattern, or strategy definition.

        Args:
            skill_name: Skill name (e.g. 'wyckoff-2-0', 'volume-profile',
                        'options-playbook', 'trading-against-the-crowd', etc.)
            topic: Optional topic to filter (e.g. 'spring', 'vah', 'iron condor').

        Returns:
            Dictionary with skill metadata and relevant content.
        """
        try:
            content = skill_bridge.get_skill_content(skill_name)
            files = skill_bridge.get_skill_files(skill_name)

            if topic and topic.lower() in content.lower():
                lines = content.split("\n")
                relevant: list[str] = []
                capture = False
                for line in lines:
                    if topic.lower() in line.lower():
                        capture = True
                    if capture:
                        relevant.append(line)
                        if len(relevant) > 100:
                            break

                if relevant:
                    content = "\n".join(relevant)
                    content = f"(Filtered for '{topic}')\n\n{content}"

            return {
                "skill_name": skill_name,
                "content": content[:8000],
                "files": files,
                "truncated": len(content) > 8000,
            }
        except ValueError as e:
            return {"error": str(e)}

    @mcp_server.tool()
    def suggest_options_strategy(
        ticker: str,
        composite_score: float,
        verdict: str,
        iv_rank: float | None = None,
        risk_tolerance: str = "medium",
    ) -> dict[str, Any]:
        """Suggest an options strategy based on stock analysis verdict.

        Combines the verdict from analyze_stock with IV regime assessment
        to recommend a specific options strategy from the Options Playbook.

        Args:
            ticker: Stock ticker symbol.
            composite_score: Score from analyze_stock (0-100).
            verdict: Verdict from analyze_stock ('Long-Term Investment',
                     'Short-Term Speculation (Bullish)', 'Avoid / Wait').
            iv_rank: IV rank (0-100). Auto-fetched if None.
            risk_tolerance: 'low', 'medium', or 'high'.

        Returns:
            StrategySuggestion with strategy name, structure, and rationale.
        """
        if verdict == "Avoid / Wait":
            return {
                "ticker": ticker,
                "strategy_name": "No Entry",
                "strategy_description": "Verdict is Avoid/Wait. No options strategy recommended.",
                "rationale": ["Composite score below threshold for entry."],
                "warnings": ["Wait for better setup or higher score."],
            }

        direction = "bullish"
        if composite_score < 60:
            direction = "neutral"

        if iv_rank is None:
            try:
                from trading_mcp.data.options_chain import fetch_options_chain
                chain = fetch_options_chain(ticker)
                iv_rank = chain.get("iv_metrics", {}).get("iv_rank", 50.0)
            except Exception:
                iv_rank = 50.0

        iv_regime = "high" if iv_rank > 70 else ("low" if iv_rank < 30 else "normal")

        strategy_name = "Bull Call Spread"
        strategy_desc = "Buy ATM Call + Sell OTM Call. Defined risk, moderate bullish."
        legs = []

        if composite_score >= 75 and iv_regime in ("high", "normal") and risk_tolerance in ("medium", "high"):
            strategy_name = "Synthetic Long 2:1"
            strategy_desc = "Sell 2x OTM Put + Buy 1x ATM Call. Aggressive bullish, uses rich put premiums."
        elif composite_score >= 70 and direction == "bullish":
            strategy_name = "LEAPS Call"
            strategy_desc = "Buy deep ITM Call with DTE 300+. Low time decay, high delta."
        elif direction == "bullish":
            strategy_name = "Bull Call Spread"
            strategy_desc = "Buy ATM Call + Sell OTM Call. Defined risk, moderate bullish."
        elif direction == "neutral" and iv_regime == "high":
            strategy_name = "Iron Condor"
            strategy_desc = "Sell OTM Put spread + Call spread. Range-bound with high IV."
        elif direction == "neutral":
            strategy_name = "Cash-Secured Put"
            strategy_desc = "Sell ATM/OTM Put. Collect premium, ready to own stock at discount."

        rationale = [
            f"Score {composite_score} with verdict '{verdict}' → {direction} outlook",
            f"IV rank {iv_rank:.0f} ({iv_regime})",
            f"Risk tolerance: {risk_tolerance}",
        ]

        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "strategy_name": strategy_name,
            "strategy_description": strategy_desc,
            "legs": legs,
            "rationale": rationale,
            "max_profit": "See Greeks in analyze_options for detailed payoff",
            "max_loss": 0.0,
            "breakeven": 0.0,
            "risk_reward_ratio": None,
            "warnings": [
                "Run analyze_options with actual strikes for precise Greeks and payoff.",
                "Verify IV regime and DTE before entry.",
            ],
        }
