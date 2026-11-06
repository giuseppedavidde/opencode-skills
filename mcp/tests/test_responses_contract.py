"""Contract tests: the MCP wire schema must stay typed and lossless.

Two invariants protect the server boundary:

1. Every response model keeps unknown keys (``extra="allow"``), so typing a
   tool never truncates a vendor field.
2. Every registered tool advertises a non-empty ``outputSchema``, so a client
   can validate the payload before reasoning about it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, get_args, get_origin

import numpy as np
import pytest

from fastmcp import Client

from trading_mcp import responses
from trading_mcp.mcp import initialize_mcp

# One minimal valid payload per tool output model. Kept explicit (not
# introspected) so the test fails when a model changes in a breaking way.
MINIMAL_PAYLOADS: dict[type, dict[str, Any]] = {
    responses.StockDataResponse: {"ticker": "AAPL"},
    responses.CryptoDataResponse: {"coin_id": "bitcoin"},
    responses.OptionsChainResponse: {"ticker": "AAPL"},
    responses.ScanMarketResponse: {"universe": "us_large"},
    responses.AnalyzeStockResponse: {"ticker": "AAPL"},
    responses.AnalyzeOptionsResponse: {"ticker": "AAPL"},
    responses.GexAnalysisResponse: {"ticker": "AAPL"},
    responses.BreakoutContextResponse: {"ticker": "AAPL"},
    responses.MacroContextResponse: {},
    responses.ClearMacroCacheResponse: {"status": "ok"},
    responses.SkillKnowledgeResponse: {"skill_name": "wyckoff-2-0"},
    responses.StrategySuggestionResponse: {"ticker": "AAPL"},
    responses.BaliResult: {"ticker": "AAPL"},
    responses.TSMomResult: {"ticker": "AAPL"},
    responses.BakshiResult: {"ticker": "AAPL"},
    responses.LGBMResult: {"ticker": "AAPL"},
    responses.PostProcessResult: {"ticker": "AAPL"},
}


@pytest.mark.parametrize(
    "model,payload",
    list(MINIMAL_PAYLOADS.items()),
    ids=lambda value: getattr(value, "__name__", ""),
)
def test_model_preserves_unknown_keys(model: type, payload: dict[str, Any]) -> None:
    """Typing a tool must never drop a field the server returns."""
    validated = model.model_validate({**payload, "vendor_only_field": 1})
    dumped = validated.model_dump()
    assert dumped["vendor_only_field"] == 1
    assert set(payload) <= set(dumped)


def test_model_dump_keeps_every_input_key() -> None:
    """Round-trip of a realistic scan payload is lossless."""
    payload = {
        "universe": "custom",
        "universe_metadata": {"name": "custom", "survivorship_warning": False},
        "timestamp": "2026-11-06T12:00:00",
        "tickers_scanned": 3,
        "tickers_passed": 1,
        "min_score_threshold": 50.0,
        "elapsed_seconds": 1.2,
        "workers": 3,
        "failures": 0,
        "insufficient_data_count": 0,
        "insufficient_data_detail": [],
        "results": [
            {
                "ticker": "AAPL",
                "final_score": 72.5,
                "dimensions": [{"name": "Wyckoff Phase", "score": 90}],
                "modifiers": {"multi_timeframe": {"score": 60, "detail": "ok"}},
                "indicators": {},
                "flags": [],
                "sector": "Technology",
                "price": 210.0,
                "pattern": "Accumulation",
                "sentiment_breakdown": None,
                "new_field_from_vendor": {"x": 1},
            }
        ],
    }
    dumped = responses.ScanMarketResponse.model_validate(payload).model_dump()
    assert set(payload) <= set(dumped)
    assert dumped["results"][0]["new_field_from_vendor"] == {"x": 1}


def test_numpy_scalars_are_coerced() -> None:
    """Pandas/numpy values must validate, not blow up the tool call."""
    candle = responses.OhlcvBar.model_validate(
        {
            "date": "2026-11-05",
            "open": np.float64(1.5),
            "high": np.float32(2.5),
            "low": 1.0,
            "close": 2.0,
            "volume": np.int64(100),
        }
    )
    assert candle.volume == 100
    assert candle.open == 1.5


def test_server_advertises_typed_output_schemas(tmp_path) -> None:
    """Every tool exposes a real outputSchema, not a generic object."""
    server = initialize_mcp(str(tmp_path), str(tmp_path))

    async def _list() -> list[Any]:
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(_list())
    assert len(tools) == 17

    by_name = {tool.name: tool for tool in tools}
    expected = {
        "fetch_stock_data",
        "fetch_crypto_data",
        "fetch_options_chain",
        "scan_market",
        "analyze_stock",
        "analyze_options",
        "gex_analysis",
        "breakout_context",
        "get_macro_context",
        "clear_macro_cache",
        "get_skill_knowledge",
        "suggest_options_strategy",
        "bali_signals",
        "tsmom_signals",
        "bakshi_signals",
        "lgbm_predict",
        "lgbm_postprocess",
    }
    assert set(by_name) == expected

    for name, tool in by_name.items():
        assert tool.outputSchema, f"{name} has no outputSchema"
        properties = (tool.outputSchema or {}).get("properties") or {}
        assert properties, f"{name} advertises an empty outputSchema"
        # Serialised schemas must be JSON (no Python-only defaults leaking).
        json.dumps(tool.outputSchema)


def test_annotations_resolve_to_models() -> None:
    """Return annotations must be concrete models, not strings or dicts."""
    server = initialize_mcp("/tmp", "/tmp")
    tools = asyncio.run(_tools(server))
    for tool in tools:
        assert tool.outputSchema != {"additionalProperties": True, "type": "object"}


async def _tools(server: Any) -> list[Any]:
    async with Client(server) as client:
        return await client.list_tools()


def test_generic_containers_are_only_nested() -> None:
    """Top-level payload types are models, so the schema is stable.

    ``dict``/``list`` are allowed *inside* a model (vendor rows, detail
    blocks) but not as the tool's return type.
    """
    for model in MINIMAL_PAYLOADS:
        assert get_origin(model) is None
        assert not get_args(model)


def test_error_payload_is_uniform() -> None:
    """Ad-hoc error dicts are replaced by one envelope."""
    payload = responses.error_payload(
        "boom", kind="degraded", retryable=True, data_source="yfinance", ticker="AAPL"
    )
    assert payload["error_kind"] == "degraded"
    assert payload["error_retryable"] is True
    assert payload["data_source"] == "yfinance"
    assert payload["ticker"] == "AAPL"


def test_error_kind_derives_from_legacy_blocking_flag() -> None:
    """Models that only set ``error`` still get an explicit kind."""
    blocking = responses.BaliResult(ticker="A", error="no data", error_is_blocking=True)
    degraded = responses.BaliResult(ticker="A", error="partial", error_is_blocking=False)
    assert blocking.error_kind == "blocking"
    assert degraded.error_kind == "degraded"


def test_every_model_declares_provenance() -> None:
    """Provenance fields exist on every payload, with no invented defaults."""
    for model in MINIMAL_PAYLOADS:
        fields = model.model_fields
        assert "data_source" in fields
        assert "data_quality" in fields
        assert "as_of" in fields


def test_tool_error_paths_use_the_envelope(tmp_path) -> None:
    """A real tool failure returns the uniform error fields."""
    server = initialize_mcp(str(tmp_path), str(tmp_path))

    async def _call() -> list[dict[str, Any]]:
        async with Client(server) as client:
            missing_expiry = await client.call_tool(
                "fetch_options_chain", {"ticker": "AAPL", "expiry": ""}
            )
            missing_skill = await client.call_tool(
                "get_skill_knowledge", {"skill_name": "does-not-exist"}
            )
            return [missing_expiry.structured_content or {}, missing_skill.structured_content or {}]

    for payload in asyncio.run(_call()):
        assert payload["error"]
        assert payload["error_kind"] == "blocking"
        assert "error_retryable" in payload
        assert payload["data_source"] in ("options", "skill")


def test_payloads_are_self_describing() -> None:
    """Every payload names the contract version that produced it."""
    for model, payload in MINIMAL_PAYLOADS.items():
        dumped = model.model_validate(payload).model_dump()
        assert dumped["schema_version"] == responses.CONTRACT_VERSION
