"""Typed fundamentals: one unit per field across yfinance, FMP and Alpha Vantage (DATA-12, DATA-14)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import requests

from trading_mcp.analysis.fundamentals import _de_ratio
from trading_mcp.data import fmp_fetcher
from trading_mcp.data.fundamentals_schema import (
    Period,
    Unit,
    from_alpha_vantage,
    from_fmp,
    from_yfinance,
    merge,
)
from trading_mcp.data.redact import install_log_redaction, redact

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Synthetic FMP /stable payload with the documented field names (no recorded key).
FMP_RATIOS = [{"symbol": "XYZ", "date": "2025-12-31", "fiscalYear": "2025", "period": "FY",
               "reportedCurrency": "USD", "priceToEarningsRatio": 31.2, "priceToBookRatio": 40.1,
               "priceToSalesRatio": 8.1, "debtToEquityRatio": 1.5, "netProfitMargin": 0.24,
               "operatingProfitMargin": 0.31, "grossProfitMargin": 0.46, "enterpriseValueMultiple": 22.0,
               "dividendYield": 0.0044, "payoutRatio": 0.15, "currentRatio": 0.87}]
FMP_KEY_METRICS = [{"symbol": "XYZ", "fiscalYear": "2025", "period": "FY", "returnOnEquity": 1.5,
                    "returnOnAssets": 0.28, "freeCashFlowYield": 0.031, "earningsYield": 0.032,
                    "marketCap": 3.4e12}]
FMP_GROWTH = [{"symbol": "XYZ", "fiscalYear": "2025", "period": "FY", "revenueGrowth": 0.064, "epsgrowth": 0.1}]
FMP_PROFILE = [{"symbol": "XYZ", "sector": "Technology", "industry": "Consumer Electronics",
                "exchangeShortName": "NASDAQ", "currency": "USD"}]


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_yfinance_percent_debt_to_equity_becomes_a_ratio() -> None:
    result = from_yfinance("AAPL", _json("yf_info_AAPL.json"))
    de = result.fields["debt_to_equity"]
    assert de.value == pytest.approx(0.84286)
    assert (de.unit, de.period, de.source, de.vendor_key) == (Unit.RATIO, Period.MRQ, "yfinance", "debtToEquity")
    assert result.fields["dividend_yield"].value == pytest.approx(0.0030354226)
    assert result.fields["dividend_yield"].unit is Unit.FRACTION
    assert result.fields["fcf_yield"].vendor_key == "freeCashflow/marketCap"
    assert 0 < result.value("profit_margin") < 1


def test_alpha_vantage_recorded_overview_uses_documented_keys() -> None:
    overview = _json("av_overview_IBM.json")
    result = from_alpha_vantage("IBM", overview)
    assert result.value("pe_ttm") == pytest.approx(19.1)
    assert result.value("price_to_sales") == pytest.approx(3.029)
    assert result.fields["revenue_growth"].period is Period.QUARTERLY_YOY
    assert result.value("revenue_growth") == pytest.approx(0.047)
    assert result.value("dividend_yield") == pytest.approx(0.0295)
    assert result.value("held_pct_institutions") == pytest.approx(0.6459)
    # Not OVERVIEW fields: never invented.
    assert "debt_to_equity" not in result.fields
    assert "current_ratio" not in result.fields
    assert "free_cash_flow" not in result.fields


def test_fmp_fiscal_year_values_keep_their_period_and_unit() -> None:
    result = from_fmp("XYZ", FMP_RATIOS, FMP_KEY_METRICS, FMP_GROWTH, FMP_PROFILE)
    assert "pe_ttm" not in result.fields
    assert result.fields["pe_annual"].period is Period.ANNUAL
    assert result.fields["pe_annual"].fiscal_period == "FY2025"
    assert result.value("debt_to_equity") == pytest.approx(1.5)
    assert result.value("fcf_yield") == pytest.approx(0.031)


def test_legacy_rendering_uses_yfinance_units() -> None:
    legacy = from_fmp("XYZ", FMP_RATIOS, FMP_KEY_METRICS, FMP_GROWTH, FMP_PROFILE).to_legacy_info()
    assert legacy["debtToEquity"] == pytest.approx(150.0)      # percent, like yfinance
    assert _de_ratio(legacy) == pytest.approx(1.5)
    assert legacy["trailingAnnualDividendYield"] == pytest.approx(0.0044)
    assert legacy["dividendYield"] == pytest.approx(0.44)      # percent, like yfinance 1.5.1
    assert legacy["_fcfYield"] == pytest.approx(0.031)
    assert "freeCashflow" not in legacy
    assert "trailingPE" not in legacy and legacy["_peFiscalYear"] == pytest.approx(31.2)


def test_merge_fills_gaps_without_overwriting() -> None:
    primary = from_yfinance("IBM", {"trailingPE": 20.0, "currency": "USD"})
    merged = merge(primary, from_alpha_vantage("IBM", _json("av_overview_IBM.json")))
    assert merged.fields["pe_ttm"].source == "yfinance" and merged.value("pe_ttm") == 20.0
    assert merged.fields["pe_forward"].source == "alpha_vantage"
    assert merged.sources == ["yfinance", "alpha_vantage"]
    assert primary.value("pe_forward") is None  # inputs are not mutated


def test_dividend_unit_error_is_rejected() -> None:
    result = from_yfinance("BAD", {"trailingAnnualDividendYield": 4.3})
    assert "dividend_yield" not in result.fields
    assert result.warnings


def test_redact_masks_query_keys_and_headers() -> None:
    text = "GET /stable/ratios?symbol=AAPL&apikey=FAKE-SECRET-123 x-cg-demo-api-key: CGSECRET"
    masked = redact(text)
    assert "FAKE-SECRET-123" not in masked and "CGSECRET" not in masked
    assert "apikey=***" in masked


def test_fmp_failure_never_logs_the_key(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("TRADING_FMP_API_KEY", "FAKE-SECRET-KEY-123")

    def boom(*args, **kwargs):
        raise requests.ConnectionError(
            "HTTPSConnectionPool(host='financialmodelingprep.com'): "
            "url: /stable/ratios?symbol=AAPL&apikey=FAKE-SECRET-KEY-123"
        )

    monkeypatch.setattr(fmp_fetcher.requests, "get", boom)
    with caplog.at_level(logging.DEBUG):
        assert fmp_fetcher.fetch_fmp_fundamentals("AAPL") == {}
    assert "FAKE-SECRET-KEY-123" not in caplog.text


def test_log_records_are_redacted_everywhere(caplog: pytest.LogCaptureFixture) -> None:
    install_log_redaction()
    with caplog.at_level(logging.WARNING):
        logging.getLogger("urllib3.connectionpool").warning("Retrying %s", "/q?apikey=ABCDEF&x=1")
    assert "ABCDEF" not in caplog.text
