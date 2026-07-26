"""Fundamental analysis: P/E, earnings quality, value trap, competitive positioning."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def compute_fundamentals(info: dict[str, Any]) -> tuple[int, str]:
    """Compute fundamentals score (0-100).

    Evaluates P/E with earnings quality modifier, value trap check,
    revenue growth, margins, debt, ROE/ROA, market cap, and price vs consensus.
    """
    score = 10
    details = []

    pe = info.get("trailingPE")
    earnings_growth = info.get("earningsGrowth")
    rev_growth = info.get("revenueGrowth")

    pe_base = 0
    if pe is not None and float(pe) > 0:
        pe_val = float(pe)
        if pe_val < 12:
            pe_base = 30
        elif pe_val < 20:
            pe_base = 20
        elif pe_val < 30:
            pe_base = 10
        else:
            pe_base = 0

    eq_mod = 0
    if earnings_growth is not None:
        eg_val = float(earnings_growth)
        if eg_val > 0.15:
            eq_mod = 20
        elif eg_val > 0.05:
            eq_mod = 10
        elif eg_val > 0:
            eq_mod = 5
        elif eg_val < -0.10:
            eq_mod = -20
        elif eg_val < 0:
            eq_mod = -10

    score += pe_base + eq_mod
    if pe is not None and float(pe) > 0:
        details.append(f"P/E {float(pe):.1f} base={pe_base} EQ mod={eq_mod:+d}")

    pe_low = pe is not None and 0 < float(pe) < 15
    vt_count = 0
    if pe_low:
        if earnings_growth is not None and float(earnings_growth) <= 0:
            score -= 20
            vt_count += 1
            details.append("WARN: Value Trap: P/E low + EPS falling (-20)")
        if rev_growth is not None and float(rev_growth) < 0.02:
            score -= 15
            vt_count += 1
            details.append("WARN: Value Trap: P/E low + revenue < 2% (-15)")
        de = info.get("debtToEquity")
        if de is not None and float(de) > 2.0:
            score -= 15
            vt_count += 1
            details.append(f"WARN: Value Trap: D/E {float(de):.2f} > 2.0 (-15)")
    if vt_count >= 2:
        score = min(score, 40)
        details.append(f"WARN: VALUE TRAP ALERT ({vt_count} signals) -- score capped at 40")

    if rev_growth is not None and float(rev_growth) > 0:
        score += 15
        details.append(f"Rev growth {float(rev_growth)*100:.1f}% (+15)")

    margins = info.get("profitMargins")
    if margins is not None and float(margins) > 0:
        score += 15
        details.append(f"Margins {float(margins)*100:.1f}% (+15)")

    de = info.get("debtToEquity")
    if de is not None:
        de_val = float(de)
        if de_val < 0.5:
            score += 20
            details.append(f"D/E {de_val:.2f} < 0.5 (+20)")
        elif de_val < 1.0:
            score += 10
            details.append(f"D/E {de_val:.2f} < 1.0 (+10)")

    roe = info.get("returnOnEquity")
    if roe is not None:
        roe_val = float(roe)
        if roe_val > 0.20:
            score += 15
            details.append(f"ROE {roe_val*100:.1f}% > 20% (moat +15)")
        elif roe_val > 0.15:
            score += 10
            details.append(f"ROE {roe_val*100:.1f}% > 15% (+10)")

    roa = info.get("returnOnAssets")
    if roa is not None:
        roa_val = float(roa)
        if roa_val > 0.10:
            score += 10
            details.append(f"ROA {roa_val*100:.1f}% > 10% (+10)")
        elif roa_val > 0.05:
            score += 5
            details.append(f"ROA {roa_val*100:.1f}% > 5% (+5)")

    op_margins = info.get("operatingMargins")
    if op_margins is not None:
        om_val = float(op_margins)
        if om_val > 0.20:
            score += 10
            details.append(f"Op margins {om_val*100:.1f}% (efficient +10)")

    mcap = info.get("marketCap")
    if mcap is not None:
        mcap_b = float(mcap) / 1e9
        if mcap_b > 10:
            score += 10
            details.append(f"MCap ${mcap_b:.1f}B > $10B (+10)")

    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    current = info.get("currentPrice")
    if target_mean and current and float(target_mean) > 0 and float(current) > 0:
        ratio = float(current) / float(target_mean)
        if ratio > 1.10:
            score -= 25
            details.append(f"Price ${float(current):.2f} > 110% of mean target ${float(target_mean):.2f} (-25)")
        elif ratio > 0.80 and target_high:
            ratio_high = float(current) / float(target_high)
            if ratio_high > 0.90:
                score -= 10
                details.append("Price near high target (priced for perfection -10)")
        elif ratio < 0.80:
            score += 15
            details.append(f"Price ${float(current):.2f} < 80% of mean target (+15)")
        elif ratio < 1.0:
            score += 5
            details.append(f"Price ${float(current):.2f} < mean target (+5)")

    return min(max(score, 0), 100), " | ".join(details)


def compute_fundamentals_enriched(info: dict[str, Any]) -> dict[str, Any]:
    """Enrich yfinance info dict with external data sources.

    Ordine di tentativo:
    1. Alpha Vantage (free tier, 25/giorno — il più ricco, dati point-in-time)
    2. FMP (se disponibile)
    3. yfinance (sempre disponibile, fallback finale)

    Returns the enriched info dict (mutates in place).
    """
    symbol = info.get("symbol", "")
    if not symbol:
        info["_fundamentals_source"] = "yfinance"
        return info

    # 1. Alpha Vantage (prioritario)
    try:
        from trading_mcp.data.alpha_vantage_fetcher import fetch_av_fundamentals
        av_data = fetch_av_fundamentals(symbol)
        if av_data:
            info.update(av_data)
            info["_fundamentals_source"] = "alpha_vantage"
            logger.info("AV enriched %s", symbol)
            return info
    except Exception:
        logger.debug("AV enrichment skipped", exc_info=True)

    # 2. FMP (fallback)
    try:
        from trading_mcp.data.fmp_fetcher import fetch_fmp_fundamentals
        fmp_data = fetch_fmp_fundamentals(symbol)
        if fmp_data:
            info.update(fmp_data)
            info["_fundamentals_source"] = "fmp"
            logger.info("FMP enriched %s", symbol)
            return info
    except Exception:
        logger.debug("FMP enrichment skipped", exc_info=True)

    # 3. yfinance (fallback finale)
    info["_fundamentals_source"] = "yfinance"
    return info


def compute_competitive_positioning(info: dict[str, Any]) -> tuple[int, str]:
    """Compute competitive positioning score (0-100).

    Proxy metrics from yfinance: ROE, margins, ROA, market cap, operating margins.
    """
    score = 30
    details = []

    roe = info.get("returnOnEquity")
    if roe is not None:
        roe_val = float(roe)
        if roe_val > 0.20:
            score += 20
            details.append(f"ROE {roe_val*100:.1f}% > 20% (moat proxy +20)")
        elif roe_val > 0.15:
            score += 10
            details.append(f"ROE {roe_val*100:.1f}% > 15% (+10)")
        else:
            details.append(f"ROE {roe_val*100:.1f}% (+0)")

    margins = info.get("profitMargins")
    if margins is not None:
        m_val = float(margins)
        if m_val > 0.20:
            score += 20
            details.append(f"Margins {m_val*100:.1f}% > 20% (pricing power +20)")
        elif m_val > 0.10:
            score += 10
            details.append(f"Margins {m_val*100:.1f}% > 10% (+10)")

    roa = info.get("returnOnAssets")
    if roa is not None:
        roa_val = float(roa)
        if roa_val > 0.10:
            score += 15
            details.append(f"ROA {roa_val*100:.1f}% > 10% (+15)")
        elif roa_val > 0.05:
            score += 10
            details.append(f"ROA {roa_val*100:.1f}% > 5% (+10)")

    mcap = info.get("marketCap")
    if mcap is not None:
        mcap_b = float(mcap) / 1e9
        if mcap_b > 200:
            score += 15
            details.append(f"MCap ${mcap_b:.0f}B > $200B (scale moat +15)")
        elif mcap_b > 50:
            score += 10
            details.append(f"MCap ${mcap_b:.0f}B $50-200B (+10)")
        elif mcap_b > 10:
            score += 5
            details.append(f"MCap ${mcap_b:.0f}B > $10B (+5)")

    op_margins = info.get("operatingMargins")
    if op_margins is not None:
        om_val = float(op_margins)
        if om_val > 0.20:
            score += 10
            details.append(f"Op margins {om_val*100:.1f}% (efficient +10)")

    return min(score, 100), " | ".join(details)
