"""Tests of the trade journal (log_trade.py) and of its statistics (feedback_loop.py).

Run: uv run --no-project --with pytest --with pydantic --with numpy --with pandas --with yfinance \
         python -m pytest skills/stock-crypto-analysis/tests/test_journal.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL))

import feedback_loop as fl  # noqa: E402  pylint: disable=wrong-import-position
import log_trade as lt  # noqa: E402  pylint: disable=wrong-import-position


def _verdict(verdict: str = "Long-Term Investment", direction: str = "Long", window: str = "NORMAL",
             score: float = 76.0) -> dict:
    return {
        "ticker": "AAPL", "composite_score": score, "analysis_score": 70.0, "macro_score": 12,
        "verdict": verdict, "direction": direction,
        "macro": {"total": 12, "window": window},
        "multi_timeframe": {"alignment": "aligned_bull"},
        "risk": {"max_position_pct": 5.0, "stop_loss_pct": 5.0, "max_leverage": 1.0},
        "entry": {},
    }


def _new(tmp: Path, verdict: dict, *extra: str) -> int:
    vf = tmp / "verdict.json"
    vf.write_text(json.dumps(verdict), encoding="utf-8")
    return lt.main(["--log-path", str(tmp / "log.jsonl"), "new", "--ticker", "AAPL", "--verdict-file", str(vf), *extra])


def _entries(tmp: Path) -> list[dict]:
    return [json.loads(x) for x in (tmp / "log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def test_new_requires_entry_price_and_size(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _new(tmp_path, _verdict())
    with pytest.raises(SystemExit):
        _new(tmp_path, _verdict(), "--entry-price", "150")
    assert _new(tmp_path, _verdict(), "--entry-price", "150", "--size-pct", "0") == 1
    assert _new(tmp_path, _verdict(), "--entry-price", "-1", "--size-pct", "2") == 1
    assert _new(tmp_path, _verdict(), "--entry-price", "150", "--size-pct", "2") == 0
    row = _entries(tmp_path)[0]
    assert row["entry_price"] == 150 and row["position_size_pct"] == 2 and row["position"] == "long"


def test_exit_computes_pnl_for_long_short_and_flat(tmp_path: Path) -> None:
    assert _new(tmp_path, _verdict(), "--entry-price", "100", "--size-pct", "4", "--fees-pct", "0.2",
                "--entry-date", "2026-01-05") == 0
    assert _new(tmp_path, _verdict("Short-Term Speculation (Bullish)", "Short"), "--entry-price", "100",
                "--size-pct", "2", "--entry-date", "2026-01-05") == 0
    assert _new(tmp_path, _verdict("Avoid / Wait", "Neutral"), "--entry-price", "100", "--size-pct", "0",
                "--entry-date", "2026-01-05") == 0
    ids = [e["trade_id"] for e in _entries(tmp_path)]
    for trade_id in ids:
        assert lt.main(["--log-path", str(tmp_path / "log.jsonl"), "exit", "--trade-id", trade_id[:8],
                        "--exit-price", "110", "--reason", "manual", "--exit-date", "2026-02-05"]) == 0
    long_, short, flat = _entries(tmp_path)
    assert long_["pnl_pct"] == pytest.approx(9.8) and long_["pnl_equity_pct"] == pytest.approx(0.392)
    assert short["pnl_pct"] == pytest.approx(-10.0) and short["pnl_equity_pct"] == pytest.approx(-0.2)
    assert flat["position"] == "flat" and flat["pnl_pct"] == 0 and flat["underlying_move_pct"] == pytest.approx(10.0)


def test_exit_rejects_bad_dates_and_unknown_ids(tmp_path: Path) -> None:
    assert _new(tmp_path, _verdict(), "--entry-price", "100", "--size-pct", "4", "--entry-date", "2026-03-01") == 0
    log = str(tmp_path / "log.jsonl")
    trade_id = _entries(tmp_path)[0]["trade_id"]
    assert lt.main(["--log-path", log, "exit", "--trade-id", "zzzz", "--exit-price", "1", "--reason", "manual"]) == 1
    assert lt.main(["--log-path", log, "exit", "--trade-id", trade_id, "--exit-price", "101", "--reason", "manual",
                    "--exit-date", "2026-02-01"]) == 1
    assert _entries(tmp_path)[0]["is_open"] is True


def test_avoid_is_flat_and_checked_against_the_market() -> None:
    # Audit case: an Avoid verdict and the price +5% must not count as a correct verdict.
    avoid = {"is_open": False, "verdict_snapshot": _verdict("Avoid / Wait", "Neutral", "DEFENSIVE"),
             "entry_price": 100.0, "exit_price": 105.0, "pnl_pct": 5.0,
             "entry_date": "2026-01-01", "exit_date": "2026-01-20"}
    hr = fl.compute_hit_rate([avoid] * 5)
    assert hr["total_closed"] == 0
    assert hr["avoid_signals"]["long_would_lose_pct"] == 0.0
    assert hr["avoid_signals"]["avg_underlying_move"] == pytest.approx(5.0)
    assert any("a long would have lost in 0%" in p for p in fl.find_patterns([avoid] * 5))
    assert fl.equity_pnl(avoid) == 0.0


def _daily_trades(pnls: list[float], start: date = date(2026, 1, 1), gap: int = 2) -> list[dict]:
    rows = []
    for i, p in enumerate(pnls):
        day = start + timedelta(days=gap * i)
        rows.append({"is_open": False, "position": "long", "position_size_pct": 10.0, "pnl_pct": p * 10,
                     "pnl_equity_pct": p, "entry_date": (day - timedelta(days=1)).isoformat(),
                     "exit_date": day.isoformat(), "verdict_snapshot": _verdict()})
    return rows


def test_sharpe_uses_daily_equity_returns() -> None:
    # Audit case: 5 trades in 7 days gave a "Sharpe-like" 15.11. Now the sample is too short.
    short = _daily_trades([1.0, 0.5, 0.8, -0.2, 0.6], gap=1)
    assert fl.compute_sharpe(short)["insufficient_data"] is True

    pnls = [0.6, -0.4, 0.3, 0.5, -0.7, 0.2, 0.4, -0.1, 0.9, -0.3, 0.2, 0.1, -0.5, 0.4, 0.3, 0.2, -0.2, 0.6, 0.1, -0.4]
    trades = _daily_trades(pnls, gap=3)
    res = fl.compute_sharpe(trades)
    curve = fl.equity_curve(trades)
    rets = curve["returns"]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    assert res["insufficient_data"] is False
    assert res["days"] == len(rets) == 3 * (len(pnls) - 1) + 2
    assert res["sharpe"] == pytest.approx(mean / sd * math.sqrt(365), abs=1e-3)
    with_rf = fl.compute_sharpe(trades, rf_annual=0.05)
    assert with_rf["sharpe"] < res["sharpe"]


def test_drawdown_comes_from_the_compounded_equity_curve() -> None:
    trades = _daily_trades([-10.0, -10.0], gap=5)
    dd = fl.compute_drawdown(trades)
    assert dd["max_drawdown_pct"] == pytest.approx(19.0)
    assert dd["total_return_pct"] == pytest.approx(-19.0)
    big_position = [{**t, "position_size_pct": 50.0, "pnl_pct": -20.0, "pnl_equity_pct": -10.0} for t in trades]
    assert fl.compute_drawdown(big_position)["max_drawdown_pct"] == pytest.approx(19.0)


def test_legacy_rows_without_position_are_recomputed() -> None:
    legacy_avoid = {"is_open": False, "verdict_snapshot": _verdict("Avoid / Wait", "Neutral"),
                    "entry_price": 50.0, "exit_price": 45.0, "pnl_pct": -10.0, "exit_date": "2026-01-10"}
    legacy_long = {"is_open": False, "verdict_snapshot": _verdict(), "entry_price": 50.0, "exit_price": 55.0,
                   "pnl_pct": None, "position_size_pct": 5.0, "exit_date": "2026-01-10"}
    assert fl.position_pnl(legacy_avoid) == 0.0
    assert fl.position_pnl(legacy_long) == pytest.approx(10.0)
    assert fl.equity_pnl(legacy_long) == pytest.approx(0.5)


def test_data_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCODE_SKILLS_DATA_DIR", str(tmp_path / "data"))
    assert lt._default_data_file("trade_log.jsonl") == tmp_path / "data" / "trade_log.jsonl"  # pylint: disable=protected-access
    assert fl._default_data_file("trade_log.jsonl") == tmp_path / "data" / "trade_log.jsonl"  # pylint: disable=protected-access


def test_weights_come_from_the_mcp() -> None:
    import weights_config  # pylint: disable=import-outside-toplevel
    from trading_mcp.analysis import macro  # pylint: disable=import-outside-toplevel
    from trading_mcp.weights_config import get_weights  # pylint: disable=import-outside-toplevel

    assert weights_config.BASE_WEIGHTS_STOCK == get_weights().stocks.to_dict()
    assert weights_config.BASE_WEIGHTS_CRYPTO == get_weights().crypto.to_dict()
    assert weights_config.get_dynamic_weights is macro.get_dynamic_weights
    assert weights_config.detect_regime is macro.detect_regime
