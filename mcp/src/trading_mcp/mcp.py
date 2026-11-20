"""FastMCP server initialization and tool registration."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from trading_mcp.config import SKILLS_DIR, TICKERS_DIR
from trading_mcp.data.redact import install_log_redaction


def initialize_mcp(
    skills_dir: str | None = None,
    tickers_dir: str | None = None,
) -> FastMCP:
    """Initialize the FastMCP server with trading tools.

    Args:
        skills_dir: Optional override for skills directory path.
        tickers_dir: Optional override for tickers CSV directory path.
    """
    install_log_redaction()
    resolved_skills = Path(skills_dir) if skills_dir else SKILLS_DIR
    resolved_tickers = Path(tickers_dir) if tickers_dir else TICKERS_DIR

    mcp_server = FastMCP(
        name="trading-mcp",
        instructions=(
            "Trading analysis MCP server. Exposes market scanning, stock/crypto "
            "analysis, options analysis, macro context, skill knowledge, and "
            "quantitative signal tools (Bali, TS-MOM, Bakshi). "
            "Use get_macro_context first to understand the current market regime, "
            "then scan_market to find opportunities, analyze_stock for deep analysis, "
            "and analyze_options or suggest_options_strategy for options trades. "
            "Quant tools use the DataProvider cache: call analyze_stock first to "
            "warm the cache, then bali_signals/tsmom_signals/bakshi_signals "
            "will hit the cache without additional yfinance calls. "
            "Every answer carries as_of (data time, ISO 8601 with offset), "
            "computed_at, sources, degraded and warnings; a missing number is "
            "null, never 0. Check degraded and the as_of of each price before "
            "you use it; cached answers add cached and cache_age_s."
        ),
        on_duplicate="error",
    )

    # pylint: disable=import-outside-toplevel
    from trading_mcp.tools._data_tools import register_data_tools
    from trading_mcp.tools._knowledge_tools import register_knowledge_tools
    from trading_mcp.tools._market_tools import register_market_tools
    from trading_mcp.tools._options_tools import register_options_tools
    from trading_mcp.tools._stock_tools import register_stock_tools

    register_data_tools(mcp_server)
    register_stock_tools(mcp_server, str(resolved_skills), str(resolved_tickers))
    register_options_tools(mcp_server, str(resolved_skills))
    register_market_tools(mcp_server)
    register_knowledge_tools(mcp_server, str(resolved_skills))

    return mcp_server
