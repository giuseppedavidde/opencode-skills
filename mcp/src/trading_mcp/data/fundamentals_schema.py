"""One typed, normalized fundamentals model for every vendor (DATA-12).

Each field carries its value, unit, period and source, so values from
yfinance, FMP and Alpha Vantage never mix units:

- ratios are plain ratios (P/E 25.0; debt-to-equity 0.84 means 84%);
- margins, returns, growth, yields and payout are FRACTIONS (0.25 = 25%);
- money is in the instrument currency; ``short_ratio`` is in days.

Vendor units handled here: yfinance ``debtToEquity`` is a PERCENT,
``dividendYield`` is a PERCENT in yfinance 1.5.1 (never read here; the
fraction ``trailingAnnualDividendYield`` is used), FMP ``ratios`` are
fiscal-year values, Alpha Vantage ``PercentInstitutions`` is a PERCENT.

:func:`merge` keeps the first source of each field and only fills gaps
(no overwrite). :meth:`Fundamentals.to_legacy_info` renders the normalized
values back into yfinance keys AND yfinance units, for callers that still
read the ``info`` dict.
"""

from __future__ import annotations

import copy
import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Unit(str, Enum):
    """Unit of a fundamental value."""

    RATIO = "ratio"
    FRACTION = "fraction"
    CURRENCY = "currency"
    SHARES = "shares"
    DAYS = "days"


class Period(str, Enum):
    """Measurement period of a fundamental value."""

    TTM = "ttm"
    MRQ = "mrq"
    ANNUAL = "annual"
    QUARTERLY_YOY = "quarterly_yoy"
    FORWARD = "forward"
    SNAPSHOT = "snapshot"


# Field name -> (unit, description). The unit of a field never changes.
FIELD_UNITS: dict[str, tuple[Unit, str]] = {
    "pe_ttm": (Unit.RATIO, "price / trailing 12-month EPS"),
    "pe_forward": (Unit.RATIO, "price / forward EPS"),
    "pe_annual": (Unit.RATIO, "price / last fiscal-year EPS"),
    "peg": (Unit.RATIO, "P/E divided by EPS growth"),
    "price_to_book": (Unit.RATIO, "price / book value per share"),
    "price_to_sales": (Unit.RATIO, "market cap / revenue"),
    "ev_to_ebitda": (Unit.RATIO, "enterprise value / EBITDA"),
    "ev_to_revenue": (Unit.RATIO, "enterprise value / revenue"),
    "debt_to_equity": (Unit.RATIO, "total debt / shareholder equity (0.84 = 84%)"),
    "current_ratio": (Unit.RATIO, "current assets / current liabilities"),
    "gross_margin": (Unit.FRACTION, "gross profit / revenue"),
    "operating_margin": (Unit.FRACTION, "operating income / revenue"),
    "profit_margin": (Unit.FRACTION, "net income / revenue"),
    "roe": (Unit.FRACTION, "net income / equity"),
    "roa": (Unit.FRACTION, "net income / assets"),
    "revenue_growth": (Unit.FRACTION, "revenue growth year over year"),
    "earnings_growth": (Unit.FRACTION, "earnings growth year over year"),
    "dividend_yield": (Unit.FRACTION, "annual dividends / price"),
    "payout_ratio": (Unit.FRACTION, "dividends / earnings"),
    "fcf_yield": (Unit.FRACTION, "free cash flow / market cap"),
    "earnings_yield": (Unit.FRACTION, "EPS / price"),
    "free_cash_flow": (Unit.CURRENCY, "free cash flow"),
    "operating_cash_flow": (Unit.CURRENCY, "operating cash flow"),
    "revenue": (Unit.CURRENCY, "revenue"),
    "market_cap": (Unit.CURRENCY, "market capitalization"),
    "eps": (Unit.CURRENCY, "earnings per share"),
    "target_mean_price": (Unit.CURRENCY, "mean analyst price target"),
    "shares_outstanding": (Unit.SHARES, "shares outstanding"),
    "beta": (Unit.RATIO, "beta to the market"),
    "short_percent_of_float": (Unit.FRACTION, "shares short / float"),
    "short_ratio": (Unit.DAYS, "days to cover"),
    "held_pct_institutions": (Unit.FRACTION, "shares held by institutions"),
}

MAX_DIVIDEND_YIELD = 0.20


class FundamentalValue(BaseModel):
    """One normalized value with its provenance."""

    value: float
    unit: Unit
    period: Period
    source: str
    vendor_key: str
    fiscal_period: str | None = None


class Fundamentals(BaseModel):
    """Normalized fundamentals of one symbol (see the module docstring)."""

    symbol: str
    currency: str | None = None
    financial_currency: str | None = None
    fetched_at: str | None = None
    sources: list[str] = Field(default_factory=list)
    fields: dict[str, FundamentalValue] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def value(self, name: str) -> float | None:
        """Value of a field, or ``None`` when absent."""
        item = self.fields.get(name)
        return item.value if item is not None else None

    def copy_deep(self) -> "Fundamentals":
        """Independent copy (callers may mutate it)."""
        return self.model_copy(deep=True)

    def to_legacy_info(self) -> dict[str, Any]:
        """yfinance-shaped dict in yfinance units (for callers of ``info``).

        Fiscal-year P/E goes to ``_peFiscalYear`` (not ``trailingPE``) and
        the FCF yield to ``_fcfYield`` (not ``freeCashflow``).
        """
        out: dict[str, Any] = {}

        def put(key: str, name: str, scale: float = 1.0, periods: tuple[Period, ...] | None = None) -> None:
            item = self.fields.get(name)
            if item is None or (periods is not None and item.period not in periods):
                return
            out[key] = item.value * scale

        put("trailingPE", "pe_ttm")
        put("_peFiscalYear", "pe_annual")
        put("forwardPE", "pe_forward")
        put("pegRatio", "peg")
        put("priceToBook", "price_to_book")
        put("priceToSalesTrailing12Months", "price_to_sales", periods=(Period.TTM,))
        put("enterpriseToEbitda", "ev_to_ebitda")
        put("enterpriseToRevenue", "ev_to_revenue")
        put("debtToEquity", "debt_to_equity", scale=100.0)  # yfinance reports a percent
        put("currentRatio", "current_ratio")
        put("grossMargins", "gross_margin")
        put("operatingMargins", "operating_margin")
        put("profitMargins", "profit_margin")
        put("returnOnEquity", "roe")
        put("returnOnAssets", "roa")
        put("revenueGrowth", "revenue_growth")
        put("earningsGrowth", "earnings_growth")
        put("trailingAnnualDividendYield", "dividend_yield")
        put("dividendYield", "dividend_yield", scale=100.0)  # yfinance 1.5.1 reports a percent
        put("payoutRatio", "payout_ratio")
        put("_fcfYield", "fcf_yield")
        put("freeCashflow", "free_cash_flow")
        put("operatingCashflow", "operating_cash_flow")
        put("totalRevenue", "revenue")
        put("marketCap", "market_cap")
        put("trailingEps", "eps", periods=(Period.TTM,))
        put("targetMeanPrice", "target_mean_price")
        put("sharesOutstanding", "shares_outstanding")
        put("beta", "beta")
        put("shortPercentOfFloat", "short_percent_of_float")
        put("shortRatio", "short_ratio")
        put("heldPercentInstitutions", "held_pct_institutions")
        for key in ("sector", "industry", "longBusinessSummary", "fullTimeEmployees", "exchange"):
            if self.profile.get(key) is not None:
                out[key] = self.profile[key]
        if self.sources:
            out["_fundamentals_source"] = self.sources[0]
        out["_fundamentals_units"] = "yfinance"
        return out


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip() in ("", "None", "-", "null"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _Builder:
    def __init__(self, symbol: str, source: str) -> None:
        self.result = Fundamentals(symbol=symbol.upper(), sources=[source])
        self.source = source

    def add(self, name: str, raw: Any, period: Period, vendor_key: str, *,
            scale: float = 1.0, fiscal_period: str | None = None) -> None:
        number = _number(raw)
        if number is None or name in self.result.fields:
            return
        unit = FIELD_UNITS[name][0]
        value = number * scale
        if name == "dividend_yield" and not 0.0 <= value <= MAX_DIVIDEND_YIELD:
            self.result.warnings.append(f"{self.source} {vendor_key}={number} rejected as a unit error")
            return
        self.result.fields[name] = FundamentalValue(
            value=value, unit=unit, period=period, source=self.source,
            vendor_key=vendor_key, fiscal_period=fiscal_period,
        )


def from_yfinance(symbol: str, info: dict[str, Any] | None) -> Fundamentals:
    """Normalize a yfinance ``info`` dict."""
    info = info or {}
    b = _Builder(symbol, "yfinance")
    b.result.currency = info.get("currency")
    b.result.financial_currency = info.get("financialCurrency")
    b.result.fetched_at = info.get("_fetched_at")
    add = b.add
    add("pe_ttm", info.get("trailingPE"), Period.TTM, "trailingPE")
    add("pe_forward", info.get("forwardPE"), Period.FORWARD, "forwardPE")
    add("peg", info.get("trailingPegRatio", info.get("pegRatio")), Period.TTM, "trailingPegRatio")
    add("price_to_book", info.get("priceToBook"), Period.MRQ, "priceToBook")
    add("price_to_sales", info.get("priceToSalesTrailing12Months"), Period.TTM, "priceToSalesTrailing12Months")
    add("ev_to_ebitda", info.get("enterpriseToEbitda"), Period.TTM, "enterpriseToEbitda")
    add("ev_to_revenue", info.get("enterpriseToRevenue"), Period.TTM, "enterpriseToRevenue")
    add("debt_to_equity", info.get("debtToEquity"), Period.MRQ, "debtToEquity", scale=0.01)
    add("current_ratio", info.get("currentRatio"), Period.MRQ, "currentRatio")
    add("gross_margin", info.get("grossMargins"), Period.TTM, "grossMargins")
    add("operating_margin", info.get("operatingMargins"), Period.TTM, "operatingMargins")
    add("profit_margin", info.get("profitMargins"), Period.TTM, "profitMargins")
    add("roe", info.get("returnOnEquity"), Period.TTM, "returnOnEquity")
    add("roa", info.get("returnOnAssets"), Period.TTM, "returnOnAssets")
    add("revenue_growth", info.get("revenueGrowth"), Period.QUARTERLY_YOY, "revenueGrowth")
    add("earnings_growth", info.get("earningsGrowth"), Period.QUARTERLY_YOY, "earningsGrowth")
    add("dividend_yield", info.get("trailingAnnualDividendYield"), Period.TTM, "trailingAnnualDividendYield")
    rate, price = _number(info.get("dividendRate")), _number(info.get("regularMarketPrice"))
    if rate is not None and price:
        add("dividend_yield", rate / price, Period.FORWARD, "dividendRate/regularMarketPrice")
    add("payout_ratio", info.get("payoutRatio"), Period.TTM, "payoutRatio")
    add("free_cash_flow", info.get("freeCashflow"), Period.TTM, "freeCashflow")
    add("operating_cash_flow", info.get("operatingCashflow"), Period.TTM, "operatingCashflow")
    add("revenue", info.get("totalRevenue"), Period.TTM, "totalRevenue")
    add("market_cap", info.get("marketCap"), Period.SNAPSHOT, "marketCap")
    fcf, mcap = _number(info.get("freeCashflow")), _number(info.get("marketCap"))
    if fcf is not None and mcap:
        add("fcf_yield", fcf / mcap, Period.TTM, "freeCashflow/marketCap")
    add("eps", info.get("trailingEps"), Period.TTM, "trailingEps")
    add("target_mean_price", info.get("targetMeanPrice"), Period.SNAPSHOT, "targetMeanPrice")
    add("shares_outstanding", info.get("sharesOutstanding"), Period.SNAPSHOT, "sharesOutstanding")
    add("beta", info.get("beta"), Period.SNAPSHOT, "beta")
    add("short_percent_of_float", info.get("shortPercentOfFloat"), Period.SNAPSHOT, "shortPercentOfFloat")
    add("short_ratio", info.get("shortRatio"), Period.SNAPSHOT, "shortRatio")
    add("held_pct_institutions", info.get("heldPercentInstitutions"), Period.SNAPSHOT, "heldPercentInstitutions")
    b.result.profile = {k: info.get(k) for k in ("sector", "industry", "longBusinessSummary",
                                                 "fullTimeEmployees", "exchange") if info.get(k) is not None}
    return b.result


def _first(records: list[dict[str, Any]] | None) -> dict[str, Any]:
    return records[0] if records and isinstance(records[0], dict) else {}


def from_fmp(
    symbol: str,
    ratios: list[dict[str, Any]] | None,
    key_metrics: list[dict[str, Any]] | None,
    growth: list[dict[str, Any]] | None,
    profile: list[dict[str, Any]] | None,
) -> Fundamentals:
    """Normalize FMP ``/stable`` ratios, key-metrics, financial-growth and profile.

    The default FMP statements are fiscal-year (``period`` FY) values.
    """
    b = _Builder(symbol, "fmp")
    r, k, g, p = _first(ratios), _first(key_metrics), _first(growth), _first(profile)

    def fiscal(record: dict[str, Any]) -> str | None:
        year, period = record.get("fiscalYear"), record.get("period")
        return f"{period or 'FY'}{year}" if year else record.get("date")

    period_r, period_k, period_g = fiscal(r), fiscal(k), fiscal(g)
    add = b.add
    add("pe_annual", r.get("priceToEarningsRatio"), Period.ANNUAL, "priceToEarningsRatio", fiscal_period=period_r)
    add("price_to_book", r.get("priceToBookRatio"), Period.ANNUAL, "priceToBookRatio", fiscal_period=period_r)
    add("price_to_sales", r.get("priceToSalesRatio"), Period.ANNUAL, "priceToSalesRatio", fiscal_period=period_r)
    add("debt_to_equity", r.get("debtToEquityRatio"), Period.ANNUAL, "debtToEquityRatio", fiscal_period=period_r)
    add("current_ratio", r.get("currentRatio"), Period.ANNUAL, "currentRatio", fiscal_period=period_r)
    add("gross_margin", r.get("grossProfitMargin"), Period.ANNUAL, "grossProfitMargin", fiscal_period=period_r)
    add("operating_margin", r.get("operatingProfitMargin"), Period.ANNUAL, "operatingProfitMargin",
        fiscal_period=period_r)
    add("profit_margin", r.get("netProfitMargin"), Period.ANNUAL, "netProfitMargin", fiscal_period=period_r)
    add("ev_to_ebitda", r.get("enterpriseValueMultiple"), Period.ANNUAL, "enterpriseValueMultiple",
        fiscal_period=period_r)
    add("dividend_yield", r.get("dividendYield"), Period.ANNUAL, "dividendYield", fiscal_period=period_r)
    add("payout_ratio", r.get("payoutRatio"), Period.ANNUAL, "payoutRatio", fiscal_period=period_r)
    add("roe", k.get("returnOnEquity"), Period.ANNUAL, "returnOnEquity", fiscal_period=period_k)
    add("roa", k.get("returnOnAssets"), Period.ANNUAL, "returnOnAssets", fiscal_period=period_k)
    add("fcf_yield", k.get("freeCashFlowYield"), Period.ANNUAL, "freeCashFlowYield", fiscal_period=period_k)
    add("earnings_yield", k.get("earningsYield"), Period.ANNUAL, "earningsYield", fiscal_period=period_k)
    add("ev_to_ebitda", k.get("evToEBITDA"), Period.ANNUAL, "evToEBITDA", fiscal_period=period_k)
    add("market_cap", k.get("marketCap"), Period.SNAPSHOT, "marketCap", fiscal_period=period_k)
    add("revenue_growth", g.get("revenueGrowth"), Period.ANNUAL, "revenueGrowth", fiscal_period=period_g)
    add("earnings_growth", g.get("epsgrowth"), Period.ANNUAL, "epsgrowth", fiscal_period=period_g)
    b.result.profile = {
        key: p.get(src) for key, src in (("sector", "sector"), ("industry", "industry"),
                                          ("fullTimeEmployees", "fullTimeEmployees"),
                                          ("longBusinessSummary", "description"),
                                          ("exchange", "exchangeShortName"))
        if p.get(src) is not None
    }
    b.result.currency = p.get("currency") or r.get("reportedCurrency")
    return b.result


def from_alpha_vantage(symbol: str, overview: dict[str, Any] | None) -> Fundamentals:
    """Normalize an Alpha Vantage ``OVERVIEW`` payload (only documented keys)."""
    o = overview or {}
    b = _Builder(symbol, "alpha_vantage")
    quarter = o.get("LatestQuarter")
    add = b.add
    add("pe_ttm", o.get("TrailingPE", o.get("PERatio")), Period.TTM, "TrailingPE", fiscal_period=quarter)
    add("pe_forward", o.get("ForwardPE"), Period.FORWARD, "ForwardPE")
    add("peg", o.get("PEGRatio"), Period.TTM, "PEGRatio")
    add("price_to_book", o.get("PriceToBookRatio"), Period.MRQ, "PriceToBookRatio", fiscal_period=quarter)
    add("price_to_sales", o.get("PriceToSalesRatioTTM"), Period.TTM, "PriceToSalesRatioTTM", fiscal_period=quarter)
    add("ev_to_ebitda", o.get("EVToEBITDA"), Period.TTM, "EVToEBITDA", fiscal_period=quarter)
    add("ev_to_revenue", o.get("EVToRevenue"), Period.TTM, "EVToRevenue", fiscal_period=quarter)
    add("profit_margin", o.get("ProfitMargin"), Period.TTM, "ProfitMargin", fiscal_period=quarter)
    add("operating_margin", o.get("OperatingMarginTTM"), Period.TTM, "OperatingMarginTTM", fiscal_period=quarter)
    add("roa", o.get("ReturnOnAssetsTTM"), Period.TTM, "ReturnOnAssetsTTM", fiscal_period=quarter)
    add("roe", o.get("ReturnOnEquityTTM"), Period.TTM, "ReturnOnEquityTTM", fiscal_period=quarter)
    add("earnings_growth", o.get("QuarterlyEarningsGrowthYOY"), Period.QUARTERLY_YOY, "QuarterlyEarningsGrowthYOY",
        fiscal_period=quarter)
    add("revenue_growth", o.get("QuarterlyRevenueGrowthYOY"), Period.QUARTERLY_YOY, "QuarterlyRevenueGrowthYOY",
        fiscal_period=quarter)
    add("dividend_yield", o.get("DividendYield"), Period.TTM, "DividendYield")
    add("revenue", o.get("RevenueTTM"), Period.TTM, "RevenueTTM", fiscal_period=quarter)
    add("eps", o.get("DilutedEPSTTM", o.get("EPS")), Period.TTM, "DilutedEPSTTM", fiscal_period=quarter)
    add("market_cap", o.get("MarketCapitalization"), Period.SNAPSHOT, "MarketCapitalization")
    add("shares_outstanding", o.get("SharesOutstanding"), Period.SNAPSHOT, "SharesOutstanding")
    add("beta", o.get("Beta"), Period.SNAPSHOT, "Beta")
    add("target_mean_price", o.get("AnalystTargetPrice"), Period.SNAPSHOT, "AnalystTargetPrice")
    add("held_pct_institutions", o.get("PercentInstitutions"), Period.SNAPSHOT, "PercentInstitutions", scale=0.01)
    b.result.currency = o.get("Currency")
    b.result.profile = {
        key: o.get(src) for key, src in (("sector", "Sector"), ("industry", "Industry"),
                                          ("exchange", "Exchange"))
        if o.get(src) is not None
    }
    return b.result


def merge(primary: Fundamentals, *fallbacks: Fundamentals | None) -> Fundamentals:
    """Fill the gaps of ``primary`` from ``fallbacks`` without overwriting (copies)."""
    result = primary.copy_deep()
    for other in fallbacks:
        if other is None:
            continue
        added = False
        for name, item in other.fields.items():
            if name not in result.fields:
                result.fields[name] = copy.deepcopy(item)
                added = True
        for key, value in other.profile.items():
            result.profile.setdefault(key, value)
        if added and other.sources and other.sources[0] not in result.sources:
            result.sources.append(other.sources[0])
        result.warnings.extend(other.warnings)
        result.currency = result.currency or other.currency
    return result


def debt_to_equity_ratio(info: dict[str, Any] | None) -> float | None:
    """Debt-to-equity as a plain ratio from a yfinance-shaped dict.

    ``debtToEquity`` in an ``info`` dict is always a PERCENT (yfinance, and
    the FMP/Alpha Vantage legacy renderings), so 84.3 gives 0.843 and 8.0
    gives 0.08.
    """
    number = _number((info or {}).get("debtToEquity"))
    return number / 100.0 if number is not None else None
