"""Tests for the A/B outcome harness (offline, no network)."""

# pylint: disable=duplicate-code

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.ab_outcome import harness
from trading_mcp import responses

FIXTURES = Path(__file__).resolve().parents[1] / "research" / "ab_outcome" / "fixtures"
FIXTURE_MODELS = {
    "analyze_stock_aapl.json": responses.AnalyzeStockResponse,
    "scan_market_tech.json": responses.ScanMarketResponse,
    "macro_context.json": responses.MacroContextResponse,
    "bali_signals_aapl.json": responses.BaliResult,
    "tsmom_signals_aapl.json": responses.TSMomResult,
    "bakshi_signals_aapl.json": responses.BakshiResult,
    "breakout_context_aapl.json": responses.BreakoutContextResponse,
}


def test_dig_resolves_nested_paths() -> None:
    """Dotted paths resolve dicts, lists and missing keys."""
    payload = {"a": {"b": [{"c": 1}, {"c": 2}]}, "x": None}
    assert harness.dig(payload, "a.b[1].c") == 2
    assert harness.dig(payload, "a.b[5].c") is None
    assert harness.dig(payload, "missing.path") is None
    assert harness.dig(payload, "x") is None


def test_extract_and_compare() -> None:
    """Only the configured decision fields are compared."""
    paths = ["verdict", "nested.score"]
    cold = harness.extract({"verdict": "Hold", "nested": {"score": 50}}, paths)
    warm = harness.extract({"verdict": "Hold", "nested": {"score": 51}}, paths)
    assert cold == {"verdict": "Hold", "nested.score": 50}
    assert harness.compare(cold, warm) == ["nested.score"]
    assert harness.compare(cold, cold) == []


def test_report_summarises_stability() -> None:
    """Stability is computed on executed tasks only."""
    records = [
        {"name": "a", "tool": "t", "status": "ok", "stable": True, "diffs": []},
        {"name": "b", "tool": "t", "status": "ok", "stable": False, "diffs": ["x"]},
        {"name": "c", "tool": "t", "status": "error", "stable": None, "diffs": []},
    ]
    report = harness.build_report(records, mode="test")
    assert report["summary"]["tasks_executed"] == 2
    assert report["summary"]["tasks_stable"] == 1
    assert report["summary"]["stability_pct"] == 50.0
    assert "50.0%" in harness.render_markdown(report)


def test_task_definitions_are_complete() -> None:
    """Each task names a tool and at least one decision field."""
    tasks = harness.load_tasks()
    assert len(tasks) == 7
    names = [task["name"] for task in tasks]
    assert len(names) == len(set(names))
    for task in tasks:
        assert task["tool"]
        assert task["decision_fields"]


@pytest.mark.parametrize("fixture_name,model", list(FIXTURE_MODELS.items()))
def test_recorded_ab_fixture_matches_contract(fixture_name: str, model: type) -> None:
    """Decision fixtures are real payloads and must satisfy the wire contract."""
    path = FIXTURES / fixture_name
    if not path.exists():
        pytest.skip(f"{fixture_name} not recorded")
    payload = json.loads(path.read_text(encoding="utf-8"))
    dumped = model.model_validate(payload).model_dump()
    assert set(payload) <= set(dumped)
