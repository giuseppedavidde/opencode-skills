"""Corporate events from recorded yfinance 1.5.1 payloads (2026-11-20)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading_mcp.data.events import MAX_DIVIDEND_YIELD, get_corporate_events, parse_corporate_events
from trading_mcp.data.quotes import Quote

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 20, 14, 42, tzinfo=timezone.utc)


def _info(name: str) -> dict:
    return json.loads((FIXTURES / f"yf_info_{name}.json").read_text(encoding="utf-8"))


def test_aapl_dividend_yield_is_a_fraction_not_the_vendor_percent() -> None:
    info = _info("AAPL")
    assert info["dividendYield"] == 0.31  # yfinance 1.5.1: percent
    events = parse_corporate_events("AAPL", info, now=NOW)
    assert events.dividend_yield == pytest.approx(0.0030354, rel=1e-4)
    assert events.dividend_yield_source == "trailingAnnualDividendYield"
    assert events.dividend_yield_conflict is False
    assert events.forward_dividend_yield == pytest.approx(1.08 / 350.89, rel=1e-4)


def test_aapl_next_earnings_window_is_timezone_aware() -> None:
    events = parse_corporate_events("AAPL", _info("AAPL"), now=NOW)
    window = events.next_earnings
    assert window is not None
    assert window.start == "2027-01-28T16:00:00-05:00"
    assert window.timing == "after_close"
    assert window.is_estimate is True
    assert window.days_until == pytest.approx(69.263, abs=0.001)
    assert events.last_earnings == "2026-11-02T16:00:00-05:00"
    assert events.ex_dividend_date == "2026-11-12"
    assert events.ex_dividend_in_future is False
    assert events.as_of is not None and events.as_of.endswith("-05:00")
    assert events.degraded is False


def test_eni_wrong_trailing_yield_is_detected() -> None:
    """Yahoo's trailing yield for ENI.MI counts one payment only (1.09% vs 4.4%)."""
    events = parse_corporate_events("ENI.MI", _info("ENI_MI"), now=NOW)
    assert events.dividend_yield_conflict is True
    assert events.dividend_yield_source == "dividendRate/spot"
    assert events.dividend_yield == pytest.approx(1.08 / 24.42, rel=1e-4)
    assert any("disagree" in w for w in events.warnings)


def test_eni_past_earnings_window_is_not_the_next_one() -> None:
    events = parse_corporate_events("ENI.MI", _info("ENI_MI"), now=NOW)
    assert events.next_earnings is None
    assert events.last_earnings == "2026-10-23T17:30:00+02:00"
    assert events.degraded is True
    assert events.ex_dividend_date == "2026-11-23"
    assert events.ex_dividend_in_future is True


def test_non_payer_has_a_real_zero_yield() -> None:
    events = parse_corporate_events("TSLA", _info("TSLA"), now=NOW)
    assert events.dividend_yield == 0.0
    assert events.dividend_rate is None
    assert events.ex_dividend_date is None


def test_unit_error_above_20_percent_is_rejected() -> None:
    info = _info("AAPL") | {"trailingAnnualDividendYield": 0.31, "dividendRate": None}
    events = parse_corporate_events("AAPL", info, now=NOW)
    assert events.dividend_yield is None
    assert events.degraded is True
    assert any(f"> {MAX_DIVIDEND_YIELD:.2f}" in w for w in events.warnings)


def test_quote_spot_is_used_for_the_forward_yield() -> None:
    class FakeProvider:
        def get_info_with_meta(self, ticker):
            from trading_mcp.data.provider import InfoMeta

            return _info("ENI_MI"), InfoMeta(symbol=ticker, fetched_at="2026-11-20T14:40:00+00:00")

        def get_quote(self, ticker):
            return Quote(symbol=ticker, price=27.0, as_of="2026-11-20T15:25:00+01:00", source="yfinance:chart")

    events = get_corporate_events("ENI.MI", provider=FakeProvider(), now=NOW)
    assert events.spot_used == 27.0 and events.spot_source == "yfinance:chart"
    assert events.forward_dividend_yield == pytest.approx(1.08 / 27.0, rel=1e-4)
    assert events.fetched_at == "2026-11-20T14:40:00+00:00"


def test_missing_info_is_an_error() -> None:
    events = parse_corporate_events("ZZZZ", {}, now=NOW)
    assert events.error and events.degraded
    assert events.dividend_yield is None
