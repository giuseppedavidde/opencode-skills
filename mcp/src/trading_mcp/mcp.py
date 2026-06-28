"""FastMCP server initialization and tool registration."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from trading_mcp.config import SKILLS_DIR, TICKERS_DIR


def initialize_mcp(
    skills_dir: str | None = None,
    tickers_dir: str | None = None,
) -> FastMCP:
    """Initialize the FastMCP server with trading tools.

    Args:
        skills_dir: Optional override for skills directory path.
        tickers_dir: Optional override for tickers CSV directory path.
    """
    resolved_skills = Path(skills_dir) if skills_dir else SKILLS_DIR
    resolved_tickers = Path(tickers_dir) if tickers_dir else TICKERS_DIR

    mcp_server = FastMCP(
        name="trading-mcp",
        instructions=(
            "Trading analysis MCP server. Exposes market scanning, stock/crypto "
            "analysis, options analysis, macro context, and skill knowledge tools. "
            "Use get_macro_context first to understand the current market regime, "
            "then scan_market to find opportunities, analyze_stock for deep analysis, "
            "and analyze_options or suggest_options_strategy for options trades."
        ),
        on_duplicate="error",
    )

    from trading_mcp.tools._data_tools import register_data_tools
    from trading_mcp.tools._analysis_tools import register_analysis_tools
    from trading_mcp.tools._knowledge_tools import register_knowledge_tools

    register_data_tools(mcp_server)
    register_analysis_tools(mcp_server, str(resolved_skills), str(resolved_tickers))
    register_knowledge_tools(mcp_server, str(resolved_skills))

    return mcp_server
