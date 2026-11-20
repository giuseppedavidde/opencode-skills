"""Tests of the thin scanner wrapper: no scoring of its own, report columns for the consumers.

Run: uv run --no-project --with pytest --with pandas python -m pytest skills/market-accumulation-scanner/tests
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compare_reports  # noqa: E402  pylint: disable=wrong-import-position
import scanner  # noqa: E402  pylint: disable=wrong-import-position
import watchlist_update  # noqa: E402  pylint: disable=wrong-import-position


def _mcp_result(symbol: str, score: float, sector: str = "Industrials") -> dict:
    return {
        "symbol": symbol, "name": symbol + " Inc", "market": "US", "sector": sector, "price": 42.5,
        "final_score": score, "pattern": "Spring", "flags": ["squeeze_candidate"], "competitive_score": 61.0,
        "dimensions": [
            {"name": "Wyckoff Phase", "weight": 0.2, "score": 70.0},
            {"name": "Volume Profile", "weight": 0.2, "score": 65.0},
            {"name": "Price Action", "weight": 0.15, "score": 55.0},
            {"name": "Sentiment", "weight": 0.2, "score": 50.0},
            {"name": "Fundamentals", "weight": 0.25, "score": 60.0},
        ],
        "sentiment_breakdown": {"short_interest": 40.0, "institutional": 60.0, "momentum": 80.0},
        "indicators": {"candlestick": 55, "fibonacci": 60},
    }


def _fake_mcp(results: dict[str, dict]) -> types.SimpleNamespace:
    """Stand-in for trading_mcp.analysis.scanner: the wrapper must only call these functions."""
    return types.SimpleNamespace(
        parse_custom_tickers=lambda text: [{"symbol": s, "name": s, "market": "CUSTOM"} for s in text.split(",")],
        load_universe=lambda name, folder: [],
        process_ticker=lambda t, fetch_news=True: results.get(t["symbol"]),
        process_crypto_ticker=lambda t, fetch_news=True: results.get(t["symbol"]),
        apply_macro_regime=lambda rows, regime: rows,
    )


def test_wrapper_keeps_no_scoring_logic() -> None:
    source = (SCRIPTS / "scanner.py").read_text(encoding="utf-8").lower()
    assert len(source.splitlines()) < 300
    for forbidden in ("def compute_", "def score_", "weight ="):
        assert forbidden not in source


def test_flatten_maps_mcp_dimensions_to_report_columns() -> None:
    row = scanner.flatten(_mcp_result("ABC", 71.2))
    assert row["wyckoff"] == 70.0 and row["volprof"] == 65.0 and row["pa"] == 55.0
    assert row["sentiment"] == 50.0 and row["fundamentals"] == 60.0 and row["competitive"] == 61.0
    assert row["sent_si"] == 40.0 and row["sent_momentum"] == 80.0 and row["sent_options"] is None
    assert row["candlestick"] == 55 and row["final_score"] == 71.2


def test_json_output_uses_the_mcp_functions(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    fake = _fake_mcp({"ABC": _mcp_result("ABC", 71.2), "LOW": _mcp_result("LOW", 30.0)})
    monkeypatch.setattr(scanner, "load_mcp", lambda: fake)
    assert scanner.main(["--tickers", "ABC,LOW,MISSING", "--json-output", "--min-score", "50"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["symbol"] for r in rows] == ["ABC"]
    assert rows[0]["final_score"] == 71.2 and rows[0]["wyckoff"] == 70.0


def test_unknown_and_empty_universes_are_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        scanner.main(["--universe", "nowhere", "--list-tickers"])
    monkeypatch.setattr(scanner, "load_mcp", lambda: _fake_mcp({}))
    with pytest.raises(SystemExit, match="empty or unknown"):
        scanner.main(["--universe", "italy", "--list-tickers"])


def test_csv_report_is_readable_by_the_consumers(tmp_path: Path) -> None:
    old = scanner.write_csv([scanner.flatten(_mcp_result("ABC", 60.0))], tmp_path, "2026-11-01_1000")
    new = scanner.write_csv([scanner.flatten(_mcp_result("ABC", 72.0))], tmp_path, "2026-11-08_1000")
    result = compare_reports.compare_reports(str(old), str(new))
    assert result is not None
    snap = watchlist_update.compute_snapshot(watchlist_update.load_report(new)[0])
    assert snap["score"] == 72.0
    html = scanner.write_html([scanner.flatten(_mcp_result("<b>X</b>", 72.0))], tmp_path, "s", "us_large", 1)
    assert "<b>X</b>" not in html.read_text(encoding="utf-8")
