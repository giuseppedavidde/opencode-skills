"""Tests for the token benchmark harness (offline, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.token_benchmark import benchmark
from trading_mcp import responses

FIXTURES = Path(__file__).resolve().parents[1] / "research" / "token_benchmark" / "fixtures"
FIXTURE_MODELS: dict[str, type] = {
    "analyze_stock__live.json": responses.AnalyzeStockResponse,
    "scan_market__live.json": responses.ScanMarketResponse,
    "bali_signals__live.json": responses.BaliResult,
    "fetch_options_chain__AAPL.json": responses.OptionsChainResponse,
}


def test_estimate_tokens_is_monotonic() -> None:
    """Estimate is deterministic and scales with input length."""
    assert benchmark.estimate_tokens("") == 0
    assert benchmark.estimate_tokens("abcd") == 1
    assert benchmark.estimate_tokens("a" * 4000) == 1000


def test_bars_payload_matches_data_tool_shape() -> None:
    """Bars are rendered exactly like the data tool payload."""
    index = pd.date_range("2026-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "High": [1.5, 2.5, 3.5, 4.5, 5.5],
            "Low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "Close": [1.2, 2.2, 3.2, 4.2, 5.2],
            "Volume": [10, 20, 30, 40, 50],
        },
        index=index,
    )
    bars = benchmark.bars_payload(frame, limit=3)
    assert len(bars) == 3
    assert bars[-1]["close"] == 5.2
    assert set(bars[0]) == {"date", "open", "high", "low", "close", "volume"}


def test_measure_scenario_compresses_raw_data() -> None:
    """The MCP payload is smaller than the raw data it summarises."""
    frame = pd.DataFrame(
        {
            "Open": [100.0] * 252,
            "High": [101.0] * 252,
            "Low": [99.0] * 252,
            "Close": [100.5] * 252,
            "Volume": [1_000_000] * 252,
        },
        index=pd.date_range("2025-01-01", periods=252, freq="B"),
    )
    scenario = benchmark.Scenario(
        name="tiny",
        tool="analyze_stock",
        args={},
        skills=(),
        raw_tickers=("AAPL",),
    )
    result = benchmark.measure_scenario(
        scenario,
        {"ticker": "AAPL", "composite_score": 70.0},
        {"AAPL": frame},
        Path("/nonexistent"),
    )
    assert result.status == "ok"
    assert result.raw_data_tokens > result.mcp_payload_tokens


def test_missing_fixture_is_skipped_not_estimated() -> None:
    """A missing fixture is reported, never silently estimated."""
    scenario = benchmark.SCENARIOS[0]
    result = benchmark.measure_scenario(scenario, None, {}, Path("/nonexistent"))
    assert result.status == "skipped"
    assert result.mcp_payload_tokens == 0


def test_report_break_even_uses_mean_savings() -> None:
    """Break-even is ceil(schema tax / mean savings)."""
    results = [
        benchmark.ScenarioResult(
            name="a", mcp_payload_tokens=100, raw_data_tokens=1000, skill_tokens=0
        ),
        benchmark.ScenarioResult(
            name="b", mcp_payload_tokens=100, raw_data_tokens=500, skill_tokens=0
        ),
    ]
    tax = {"with_output_schema_tokens": 1000, "with_input_schema_only_tokens": 500, "tool_count": 2}
    report = benchmark.build_report(results, tax, mode="test")
    # mean savings = (900 + 400) / 2 = 650 -> ceil(1000 / 650) = 2
    assert report["summary"]["schema_break_even_calls"] == 2


@pytest.mark.parametrize("fixture_name,model", list(FIXTURE_MODELS.items()))
def test_recorded_fixture_matches_contract(fixture_name: str, model: type) -> None:
    """Recorded payloads must validate against the advertised output model."""
    path = FIXTURES / fixture_name
    if not path.exists():
        pytest.skip(f"{fixture_name} not recorded")
    payload = json.loads(path.read_text(encoding="utf-8"))
    dumped = model.model_validate(payload).model_dump()
    assert set(payload) <= set(dumped)


def test_render_markdown_marks_partial_rows() -> None:
    """Partial scenarios are visibly marked in the report."""
    report = {
        "generated_at": "now",
        "mode": "test",
        "estimator": "chars/4.0",
        "schema_tax": {
            "tool_count": 1,
            "description_tokens": 1,
            "with_input_schema_only_tokens": 2,
            "with_output_schema_tokens": 3,
            "per_tool": [],
        },
        "scenarios": [
            {
                "name": "x",
                "status": "partial",
                "note": "barre mancanti: MSFT",
                "mcp_payload_tokens": 1,
                "raw_data_tokens": 2,
                "skill_tokens": 3,
                "baseline_tokens": 5,
                "savings_tokens": 4,
                "savings_vs_raw_pct": 50.0,
                "savings_vs_baseline_pct": 80.0,
            }
        ],
        "summary": {"schema_break_even_calls": 1},
        "limitations": ["x"],
    }
    markdown = benchmark.render_markdown(report)
    assert "⚠" in markdown


def _report(payload: dict[str, int], schema: int) -> dict:
    """Minimal report fixture for budget checks."""
    return {
        "scenarios": [
            {"name": name, "status": "ok", "mcp_payload_tokens": tokens}
            for name, tokens in payload.items()
        ],
        "schema_tax": {
            "tool_count": 17,
            "description_tokens": 1000,
            "with_output_schema_tokens": schema,
        },
    }


def test_budget_passes_within_limits() -> None:
    """A report inside the committed budget has no violations."""
    report = _report({"analyze_stock": 900, "scan_market": 1000}, schema=10000)
    budget = {
        "max_payload_tokens": {"analyze_stock": 1100, "scan_market": 1300},
        "max_schema_tokens": 11500,
        "max_description_tokens": 1200,
        "max_tools": 17,
    }
    assert not benchmark.check_budget(report, budget)


def test_budget_flags_payload_schema_and_tools() -> None:
    """Every dimension of the budget is enforced."""
    report = _report({"analyze_stock": 5000}, schema=99999)
    budget = {
        "max_payload_tokens": {"analyze_stock": 1100},
        "max_schema_tokens": 11500,
        "max_description_tokens": 10,
        "max_tools": 3,
    }
    violations = benchmark.check_budget(report, budget)
    joined = "\n".join(violations)
    assert "analyze_stock" in joined
    assert "schema tokens" in joined
    assert "description tokens" in joined
    assert "tool count" in joined


def test_budget_flags_missing_measurement() -> None:
    """A tool with no recorded fixture cannot silently pass the gate."""
    violations = benchmark.check_budget(
        _report({}, schema=1000), {"max_payload_tokens": {"analyze_stock": 1100}}
    )
    assert violations and "missing measurement" in violations[0]


def test_committed_budget_matches_report() -> None:
    """The committed budget file is valid JSON and covers measured scenarios."""
    budget = benchmark.load_budget()
    assert budget["max_payload_tokens"]
    assert budget["max_schema_tokens"] > 0
    report_path = (
        Path(__file__).resolve().parents[1] / "research" / "token_benchmark" / "report.json"
    )
    if not report_path.exists():
        pytest.skip("report not generated")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not benchmark.check_budget(report, budget)
