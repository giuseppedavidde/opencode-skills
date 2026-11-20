"""Wire models of the market-wide and knowledge tools.

``get_macro_context``, ``clear_macro_cache`` and ``get_skill_knowledge``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from trading_mcp.responses import ToolResponse


class MacroContextResponse(ToolResponse):
    """Output of ``get_macro_context``.

    ``macro_window`` is derived from ``detected_regime`` so the two can never
    contradict each other (UNKNOWN gives DEFENSIVE). ``inputs`` holds value,
    ``as_of`` and source of every input; ``regime`` is the full
    :class:`~trading_mcp.analysis.macro.RegimeState` (hysteresis, reasons).
    BTC fields are crypto context only.
    """
    data_source: str = "yfinance"
    data_quality: str = "eod"

    timestamp: str | None = None
    vix: float | None = None
    vix3m: float | None = None
    vix_term_ratio: float | None = None
    dxy: float | None = None
    dxy_trend: str | None = None
    equity_trend: str | None = None
    fed_rate: float | None = Field(default=None, description="^IRX 13-week T-bill yield, percent")
    fed_rate_source: str | None = None
    fed_rate_as_of: str | None = None
    fallback_reason: str | None = None
    btc_dominance: float | None = None
    btc_price: float | None = None
    fear_greed_index: float | None = None
    detected_regime: str | None = None
    macro_window: str | None = None
    regime: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    dynamic_weights_stock: dict[str, float] = Field(default_factory=dict)
    dynamic_weights_crypto: dict[str, float] = Field(default_factory=dict)


class ClearMacroCacheResponse(ToolResponse):
    """Output of ``clear_macro_cache``."""
    data_source: str = "core"
    data_quality: str = "derived"

    status: str
    message: str = ""
    cleared_symbols: list[str] = Field(default_factory=list)
    cleared_entries: dict[str, int] = Field(default_factory=dict)


class SkillKnowledgeResponse(ToolResponse):
    """Output of ``get_skill_knowledge``.

    ``content`` is capped (see ``truncated``) and ``sections`` lists the
    available headings so the caller can re-query one section.
    """
    data_source: str = "skill"
    data_quality: str = "derived"

    skill_name: str | None = None
    section: str | None = None
    sections: list[str] | None = None
    content: str | None = None
    files: list[str] = Field(default_factory=list)
    truncated: bool = False
    error: str | None = None
