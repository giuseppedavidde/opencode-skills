"""Typed wire contract for every MCP tool.

Each tool annotates its return type with a model from this module. FastMCP
turns that annotation into the tool's ``outputSchema``, so a client knows the
shape before the first call and a malformed payload fails at the boundary
instead of confusing the consumer.

Two rules keep the contract safe and cheap:

- ``extra="allow"``: models document and validate known fields without
  dropping vendor-specific or newly added ones. ``model_dump()`` therefore
  preserves every key (see ``tests/test_responses_contract.py``).
- Nested payloads that are large or vendor-shaped (option legs, per-dimension
  detail, payoff curves) stay ``dict`` / ``list[dict]``. Typing every leaf
  would inflate the schema that is sent on every session without adding
  meaning to the model that reads it.

Envelope conventions (every tool, see :class:`ToolResponse`):

- ``as_of``: data time of the main numbers, ISO 8601 with offset. Never a
  fetch time. Each nested price, quote or bar block carries its own
  ``as_of`` and ``source``.
- ``computed_at``: when the server built the answer (ISO 8601, UTC). A cache
  hit keeps the original value and adds ``cached=True`` and ``cache_age_s``.
- ``sources``: data sources used (for example ``yfinance:chart``).
- ``degraded``: True when any input is missing, stale or failed. A missing
  number is ``null``, never ``0.0`` or a default; ``warnings`` says why.
- ``error`` / ``error_kind`` (``blocking`` or ``degraded``) /
  ``error_retryable``: the uniform error envelope (:func:`error_payload`).

This module is the *live* contract. :mod:`trading_mcp.schemas` keeps the
shared analysis vocabulary (enums, unified verdict) used across skills.
"""

from __future__ import annotations

import functools
import importlib
from datetime import datetime
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trading_mcp.timeutil import iso, utc_iso

# Bump when a payload shape changes. The contract snapshot in
# ``docs/contract/tools.json`` records it, and CI fails on drift without a bump.
CONTRACT_VERSION = "4.0.0"


class PayloadModel(BaseModel):
    """Nested payload fragment: keeps unknown fields, carries no envelope."""

    model_config = ConfigDict(extra="allow")


def _as_of_text(value: Any) -> Any:
    """Accept aware datetimes for ``as_of`` fields and render them as ISO 8601."""
    if isinstance(value, datetime) or hasattr(value, "to_pydatetime"):
        return iso(value)
    return value


class QuoteStamp(PayloadModel):
    """Last price with its data time and freshness (see :mod:`trading_mcp.data.quotes`).

    ``freshness`` is ``realtime`` (regular session, age <= 60 s), ``delayed``
    (inside the declared vendor delay), ``last_close`` (market closed; the
    price is the last session close), ``stale`` or ``unknown``.
    """

    symbol: str | None = None
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    currency: str | None = None
    previous_close: float | None = None
    as_of: str | None = Field(default=None, description="Data time of price (ISO 8601 with offset)")
    source: str | None = None
    session_state: str | None = Field(default=None, description="pre | regular | post | closed")
    market_state: str | None = None
    age_s: float | None = Field(default=None, description="Seconds between as_of and the answer time")
    freshness: str | None = None
    stale: bool | None = None
    delayed_by_min: float | None = None
    fetched_at: str | None = None
    error: str | None = None
    error_kind: str | None = None


class DataStamp(PayloadModel):
    """Data time and source of one nested block."""

    as_of: str | None = None
    source: str | None = None
    fetched_at: str | None = None
    stale: bool | None = None


class ToolResponse(PayloadModel):
    """Top-level tool answer: never drops a field and always says where it came from.

    Provenance uses explicit ``unknown`` defaults instead of invented values:
    a number without a source is not verifiable. ``as_of=None`` means the
    upstream source did not expose a data time. ``degraded`` is True when
    any input is missing or failed; missing numbers are ``null``.
    """

    schema_version: str = CONTRACT_VERSION
    data_source: str = "unknown"
    data_quality: str = "unknown"
    as_of: str | None = Field(
        default=None, description="Data time of the main numbers (ISO 8601 with offset); never a fetch time"
    )
    computed_at: str = Field(default_factory=utc_iso, description="When the server built the answer (ISO 8601)")
    sources: list[str] = Field(default_factory=list, description="Data sources used")
    degraded: bool = Field(default=False, description="True when any input is missing, stale or failed")
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_kind: str | None = Field(default=None, description="blocking | degraded")
    error_retryable: bool | None = None
    cached: bool = Field(default=False, description="True when served from the result cache")
    cache_age_s: float | None = Field(default=None, description="Age of the cached answer in seconds")

    normalize_as_of = field_validator("as_of", mode="before")(_as_of_text)

    @model_validator(mode="after")
    def _derive_error_fields(self) -> "ToolResponse":
        """Fill the error envelope and the degraded flag; default the sources."""
        if self.error_kind is None and self.error:
            blocking = getattr(self, "error_is_blocking", True)
            object.__setattr__(self, "error_kind", "blocking" if blocking else "degraded")
        if (self.error or self.error_kind) and not self.degraded:
            object.__setattr__(self, "degraded", True)
        if not self.sources and self.data_source not in (None, "", "unknown"):
            object.__setattr__(self, "sources", [str(self.data_source)])
        return self


ResponseT = TypeVar("ResponseT", bound="ToolResponse")


def typed(model: type[ResponseT]) -> Callable[[Callable[..., Any]], Callable[..., ResponseT]]:
    """Coerce a tool answer into its declared model at the boundary.

    FastMCP only serialises fields that were *set*; a dict answer therefore
    loses model defaults such as ``schema_version`` and provenance. Wrapping
    the function makes every payload explicit and self-describing, and keeps
    the return annotation (and therefore the ``outputSchema``) intact.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., ResponseT]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ResponseT:
            result = func(*args, **kwargs)
            return result if isinstance(result, model) else model.model_validate(result)

        return wrapper

    return decorator


def error_payload(
    message: str,
    *,
    kind: str = "blocking",
    retryable: bool = False,
    data_source: str = "unknown",
    **extra: Any,
) -> dict[str, Any]:
    """Build the uniform error answer used by every tool.

    Args:
        message: Human-readable failure reason.
        kind: ``blocking`` when no answer can be produced, ``degraded`` when
            the answer is partial but usable.
        retryable: True when a later identical call may succeed.
        data_source: Where the (missing) data would have come from.
        extra: Additional payload fields for the specific tool.
    """
    return {
        "error": message,
        "error_kind": kind,
        "error_retryable": retryable,
        "data_source": data_source,
        "degraded": True,
        **extra,
    }


# ── Re-exports ───────────────────────────────────────────────────────
# Tool models live in one module per domain. They import the base classes
# from this module, so the re-export is lazy (PEP 562): ``from
# trading_mcp.responses import StockDataResponse`` keeps working and no
# import cycle can form.
_EXPORTS: dict[str, str] = {
    "OhlcvBar": "trading_mcp.responses_data",
    "StockDataResponse": "trading_mcp.responses_data",
    "CryptoDataResponse": "trading_mcp.responses_data",
    "IvMetrics": "trading_mcp.responses_options",
    "OptionsChainResponse": "trading_mcp.responses_options",
    "AnalyzeOptionsResponse": "trading_mcp.responses_options",
    "GexAnalysisResponse": "trading_mcp.responses_options",
    "StrategySuggestionResponse": "trading_mcp.responses_options",
    "BaliResult": "trading_mcp.responses_options",
    "BakshiVRP": "trading_mcp.responses_options",
    "BakshiStrikeAnalysis": "trading_mcp.responses_options",
    "BakshiResult": "trading_mcp.responses_options",
    "VRP_CALIBRATION_SOURCE": "trading_mcp.responses_options",
    "ScanResultItem": "trading_mcp.responses_stock",
    "ScanMarketResponse": "trading_mcp.responses_stock",
    "AnalyzeStockResponse": "trading_mcp.responses_stock",
    "BreakoutContextResponse": "trading_mcp.responses_stock",
    "TSMomResult": "trading_mcp.responses_stock",
    "MacroContextResponse": "trading_mcp.responses_market",
    "ClearMacroCacheResponse": "trading_mcp.responses_market",
    "SkillKnowledgeResponse": "trading_mcp.responses_market",
}

__all__ = [
    "CONTRACT_VERSION",
    "DataStamp",
    "PayloadModel",
    "QuoteStamp",
    "ToolResponse",
    "typed",
    "error_payload",
    *_EXPORTS,
]


def __getattr__(name: str) -> Any:
    """Resolve a re-exported tool model from its domain module."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
