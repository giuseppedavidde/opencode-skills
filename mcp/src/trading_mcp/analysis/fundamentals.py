"""Fundamentals dimension on one 0-100 scale with coverage (SIG-09).

Input is the typed :class:`~trading_mcp.data.fundamentals_schema.Fundamentals`
(units per field: ratios are ratios, margins/growth/yields are FRACTIONS,
debt-to-equity is a plain ratio). A legacy yfinance ``info`` dict is
converted with :func:`from_yfinance`, so the D/E unit always comes from the
schema (yfinance reports a percent).

Rules (documented priors, unvalidated):

- Every metric maps to a sub-score with 50 = neutral (bands below). A
  MISSING metric is unknown: it is left out, never scored 0 or 50.
- Groups and weights: value 0.30 (P/E, EV/EBITDA, FCF yield), quality 0.25
  (ROE, operating margin), growth 0.20 (revenue, earnings), balance sheet
  0.15 (D/E; skipped for financials, where D/E has another meaning),
  analyst 0.10 (mean target vs the QUOTE price, never ``currentPrice``).
  The dimension is the weighted mean of the groups with data; ``coverage``
  is the share of group weight with data. No group: the score is ``None``.
- The earnings-surprise score (when given) joins the growth group.
- Sector context: with a sector median P/E (cross-section of a scan with at
  least 5 names of the sector), the P/E band uses P/E relative to the median
  instead of absolute bands. Without it, ``sector_context`` is ``None``.
- Value trap: P/E < 12 with falling earnings AND falling revenue caps the
  value group at 45.
- There is no size bonus and no additive point total, so scores do not
  saturate at 100.
"""

from __future__ import annotations

import logging
from typing import Any

from trading_mcp.data.fundamentals_schema import Fundamentals, debt_to_equity_ratio, from_yfinance

logger = logging.getLogger(__name__)

GROUP_WEIGHTS = {"value": 0.30, "quality": 0.25, "growth": 0.20, "balance": 0.15, "analyst": 0.10}
FINANCIAL_SECTORS = {"Financial Services", "Financials", "Banks", "Insurance"}


def _de_ratio(info: dict[str, Any]) -> float | None:
    """Debt-to-equity as a plain ratio from a yfinance-shaped dict (``debtToEquity`` is a PERCENT)."""
    return debt_to_equity_ratio(info)


def _band(value: float, bands: list[tuple[float, float]], top: float) -> float:
    """Score of ``value`` from ascending ``(upper_bound, score)`` bands; ``top`` above the last bound."""
    for upper, score in bands:
        if value < upper:
            return score
    return top


def _pe_score(pe: float | None, eps: float | None, median: float | None) -> tuple[float | None, str | None]:
    if pe is None:
        if eps is not None and eps < 0:
            return 35.0, "negative EPS (35)"
        return None, None
    if pe <= 0:
        return 35.0, f"P/E {pe:.1f} (loss, 35)"
    if median is not None and median > 0:
        rel = pe / median
        score = _band(rel, [(0.6, 70.0), (0.85, 60.0), (1.15, 50.0), (1.5, 40.0)], 30.0)
        return score, f"P/E {pe:.1f} = {rel:.2f}x sector median {median:.1f} ({score:.0f})"
    score = _band(pe, [(10, 70.0), (15, 62.0), (22, 52.0), (30, 45.0), (45, 38.0)], 30.0)
    return score, f"P/E {pe:.1f} ({score:.0f})"


def _metric_scores(f: Fundamentals, price: float | None, sector: str | None,
                   sector_medians: dict[str, float] | None) -> dict[str, list[tuple[float, str]]]:
    groups: dict[str, list[tuple[float, str]]] = {g: [] for g in GROUP_WEIGHTS}
    val = f.value
    medians = sector_medians or {}

    pe_score, pe_text = _pe_score(val("pe_ttm"), val("eps"), medians.get("pe_ttm"))
    if pe_score is not None:
        groups["value"].append((pe_score, pe_text or ""))
    ev = val("ev_to_ebitda")
    if ev is not None:
        score = 35.0 if ev <= 0 else _band(ev, [(8, 65.0), (12, 55.0), (18, 48.0), (25, 40.0)], 32.0)
        groups["value"].append((score, f"EV/EBITDA {ev:.1f} ({score:.0f})"))
    fcf = val("fcf_yield")
    if fcf is not None:
        score = _band(fcf, [(0.0, 38.0), (0.03, 50.0), (0.06, 57.0)], 65.0)
        groups["value"].append((score, f"FCF yield {fcf:.1%} ({score:.0f})"))

    roe = val("roe")
    if roe is not None:
        score = _band(roe, [(0.0, 32.0), (0.05, 42.0), (0.12, 50.0), (0.20, 58.0)], 65.0)
        groups["quality"].append((score, f"ROE {roe:.1%} ({score:.0f})"))
    om = val("operating_margin")
    if om is not None:
        score = _band(om, [(0.0, 35.0), (0.10, 48.0), (0.20, 55.0)], 62.0)
        groups["quality"].append((score, f"Op margin {om:.1%} ({score:.0f})"))

    rev = val("revenue_growth")
    if rev is not None:
        score = _band(rev, [(-0.05, 36.0), (0.0, 44.0), (0.05, 50.0), (0.15, 56.0)], 62.0)
        groups["growth"].append((score, f"Revenue growth {rev:+.1%} ({score:.0f})"))
    eg = val("earnings_growth")
    if eg is not None:
        score = _band(eg, [(-0.10, 36.0), (0.0, 45.0), (0.15, 54.0)], 60.0)
        groups["growth"].append((score, f"Earnings growth {eg:+.1%} ({score:.0f})"))

    de = val("debt_to_equity")
    if de is not None and (sector or "") not in FINANCIAL_SECTORS:
        score = 35.0 if de < 0 else _band(de, [(0.3, 60.0), (1.0, 54.0), (2.0, 46.0)], 36.0)
        groups["balance"].append((score, f"D/E {de:.2f}x ({score:.0f})"))

    target = val("target_mean_price")
    if target is not None and price is not None and price > 0 and target > 0:
        upside = target / price - 1.0
        score = _band(upside, [(-0.15, 38.0), (-0.05, 44.0), (0.10, 50.0), (0.25, 55.0)], 60.0)
        groups["analyst"].append((score, f"Mean target {target:.2f} vs price {price:.2f} ({upside:+.0%}, {score:.0f})"))
    return groups


def fundamentals_breakdown(
    data: Fundamentals | dict[str, Any] | None,
    *,
    price: float | None = None,
    sector: str | None = None,
    sector_medians: dict[str, float] | None = None,
    earnings_surprise: float | None = None,
    symbol: str = "",
) -> dict[str, Any]:
    """Score, coverage, group scores and detail of the fundamentals dimension."""
    if isinstance(data, Fundamentals):
        fundamentals = data
    else:
        info = dict(data or {})
        fundamentals = from_yfinance(symbol or str(info.get("symbol") or ""), info)
        sector = sector or info.get("sector")
    sector = sector or fundamentals.profile.get("sector")
    groups = _metric_scores(fundamentals, price, sector, sector_medians)
    if earnings_surprise is not None:
        groups["growth"].append((float(earnings_surprise), f"Earnings surprise score {earnings_surprise:.0f}"))

    group_scores: dict[str, float | None] = {}
    details: list[str] = []
    for name, items in groups.items():
        if items:
            group_scores[name] = sum(s for s, _ in items) / len(items)
            details.extend(text for _, text in items)
        else:
            group_scores[name] = None
    pe, eg, rev = fundamentals.value("pe_ttm"), fundamentals.value("earnings_growth"), fundamentals.value("revenue_growth")
    if pe is not None and 0 < pe < 12 and eg is not None and eg < 0 and rev is not None and rev < 0:
        if group_scores["value"] is not None and group_scores["value"] > 45:
            group_scores["value"] = 45.0
        details.append("WARN: value trap (P/E < 12, earnings and revenue falling): value group capped at 45")

    known = {g: s for g, s in group_scores.items() if s is not None}
    mass = sum(GROUP_WEIGHTS[g] for g in known)
    total = sum(GROUP_WEIGHTS.values())
    score = round(sum(GROUP_WEIGHTS[g] * s for g, s in known.items()) / mass, 1) if mass > 0 else None
    missing = [g for g, s in group_scores.items() if s is None]
    if missing:
        details.append(f"unknown groups: {', '.join(missing)}")
    return {
        "score": score,
        "coverage": round(mass / total, 3),
        "groups": {g: (round(s, 1) if s is not None else None) for g, s in group_scores.items()},
        "group_weights": dict(GROUP_WEIGHTS),
        "sector": sector,
        "sector_context": {"pe_median": sector_medians.get("pe_ttm")} if sector_medians else None,
        "sources": list(fundamentals.sources),
        "detail": " | ".join(details) if details else "No fundamentals available",
        "inputs": {k: fundamentals.value(k) for k in ("pe_ttm", "ev_to_ebitda", "fcf_yield", "roe",
                                                       "operating_margin", "revenue_growth",
                                                       "earnings_growth", "debt_to_equity",
                                                       "target_mean_price")},
    }


def compute_fundamentals(
    data: Fundamentals | dict[str, Any] | None,
    price: float | None = None,
    **kwargs: Any,
) -> tuple[float | None, str]:
    """Fundamentals score (``None`` when no metric is known) and detail string."""
    out = fundamentals_breakdown(data, price=price, **kwargs)
    detail = out["detail"] + f" | coverage {out['coverage']:.0%}"
    return out["score"], detail


def load_fundamentals(symbol: str, info: dict[str, Any] | None = None, *, enrich: bool = False) -> Fundamentals:
    """Typed fundamentals: the provider with gap filling (``enrich``), else the given ``info``."""
    if enrich:
        from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

        return data_provider.get_fundamentals(symbol, enrich=True)
    return from_yfinance(symbol, info or {})


def compute_fundamentals_enriched(info: dict[str, Any], symbol: str | None = None) -> dict[str, Any]:
    """Legacy ``info`` dict with fundamentals from ``get_fundamentals(enrich=True)``.

    Merge order: yfinance values stay first; Alpha Vantage, then FMP, only
    fill the gaps (no overwrite, units normalized by the schema). Returns a
    NEW dict; ``info`` is not changed.
    """
    out = dict(info or {})
    symbol = symbol or str(out.get("symbol") or "")
    if not symbol:
        out["_fundamentals_source"] = "yfinance"
        return out
    try:
        legacy = load_fundamentals(symbol, out, enrich=True).to_legacy_info()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("fundamentals enrichment skipped for %s", symbol, exc_info=True)
        out["_fundamentals_source"] = "yfinance"
        return out
    out.update(legacy)
    return out


def compute_competitive_positioning(info: dict[str, Any]) -> tuple[int | None, str]:
    """Moat proxy from ROE, margins and ROA (0-100, 50 = neutral; informational, not in the composite).

    No size bonus. ``None`` when no input is known.
    """
    parts: list[tuple[float, str]] = []
    roe = info.get("returnOnEquity")
    if roe is not None:
        score = _band(float(roe), [(0.0, 35.0), (0.10, 45.0), (0.15, 52.0), (0.20, 60.0)], 68.0)
        parts.append((score, f"ROE {float(roe) * 100:.1f}% ({score:.0f})"))
    margins = info.get("profitMargins")
    if margins is not None:
        score = _band(float(margins), [(0.0, 35.0), (0.10, 48.0), (0.20, 58.0)], 66.0)
        parts.append((score, f"Margins {float(margins) * 100:.1f}% ({score:.0f})"))
    roa = info.get("returnOnAssets")
    if roa is not None:
        score = _band(float(roa), [(0.0, 38.0), (0.05, 48.0), (0.10, 56.0)], 64.0)
        parts.append((score, f"ROA {float(roa) * 100:.1f}% ({score:.0f})"))
    if not parts:
        return None, "No inputs"
    return int(round(sum(s for s, _ in parts) / len(parts))), " | ".join(t for _, t in parts)
