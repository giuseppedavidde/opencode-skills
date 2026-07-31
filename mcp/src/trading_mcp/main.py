"""CLI entry point for trading-mcp-server."""

from __future__ import annotations

import logging
import sys

import click


def _configure_logging() -> None:
    """Configure logging to stderr to avoid corrupting the MCP stdio transport."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="%(name)s: %(message)s",
    )


@click.command(name="run")
@click.option(
    "-t",
    "--transport",
    "transport",
    type=str,
    help="MCP transport (stdio or http).",
    default="stdio",
    envvar="MCP_TRANSPORT",
)
@click.option(
    "-p",
    "--port",
    "port",
    type=int,
    help="HTTP port (when transport=http).",
    default=8000,
    envvar="MCP_PORT",
)
@click.option(
    "--skills-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Path to skills directory containing SKILL.md files.",
    envvar="TRADING_SKILLS_DIR",
)
@click.option(
    "--tickers-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Path to ticker CSV data directory.",
    envvar="TRADING_TICKERS_DIR",
)
def run_app(
    transport: str = "stdio",
    port: int = 8000,
    skills_dir: str | None = None,
    tickers_dir: str | None = None,
) -> None:
    """Run the trading-mcp-server.

    Exposes 13 MCP tools for stock/crypto market analysis:
    fetch_stock_data, fetch_crypto_data, fetch_options_chain,
    scan_market, analyze_stock, analyze_options,
    get_macro_context, get_skill_knowledge, suggest_options_strategy,
    bali_signals, tsmom_signals, bakshi_signals, lgbm_predict.
    """
    _configure_logging()
    logger = logging.getLogger(__name__)

    from trading_mcp.mcp import initialize_mcp  # pylint: disable=import-outside-toplevel

    mcp_server = initialize_mcp(skills_dir, tickers_dir)

    transport_lower = transport.lower()
    if transport_lower == "http":
        logger.info("Starting trading-mcp-server on http://0.0.0.0:%d", port)
        mcp_server.run(transport="http", port=port)
    else:
        logger.info("Starting trading-mcp-server (stdio)")
        mcp_server.run(transport="stdio")


if __name__ == "__main__":
    run_app()
