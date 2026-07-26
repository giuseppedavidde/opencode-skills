"""Sentiment 6-dimension engine with optional web sentiment."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

WEIGHTS = {
    "short_interest": 0.12,
    "options_sentiment": 0.12,
    "insider_trading": 0.12,
    "retail_sentiment": 0.08,
    "institutional": 0.12,
    "momentum": 0.08,
    "web_news": 0.08,
    "social_media": 0.08,
    "earnings_quality": 0.20,
}


def compute_sentiment_6d(
    ticker: yf.Ticker,
    info: dict[str, Any],
    hist: pd.DataFrame,
    spx_hist: pd.DataFrame | None = None,
    wsb_hotlist: dict | None = None,
    fetch_news: bool = False,
) -> tuple[int, str, dict[str, float | None]]:
    """Compute 9-dimension sentiment score.

    When fetch_news=True, also scrapes Finviz headlines and WSB hotlist
    to fill web_news and social_media sub-dimensions.
    """
    symbol = info.get("symbol", "")
    subs: dict[str, float | None] = {
        "short_interest": None,
        "options_sentiment": None,
        "insider_trading": None,
        "retail_sentiment": None,
        "institutional": None,
        "momentum": None,
        "earnings_quality": None,
        "web_news": None,
        "social_media": None,
    }
    detail_parts = []

    si = info.get("shortPercentOfFloat")
    dtc = info.get("shortRatio")
    if si is not None and dtc is not None:
        si_val = float(si)
        dtc_val = float(dtc)
        score_si = 50.0
        if si_val > 0.20 and dtc_val > 7:
            score_si = 90.0
        elif si_val > 0.15 and dtc_val > 5:
            score_si = 80.0
        elif si_val > 0.10:
            score_si = 65.0
        elif si_val > 0.05:
            score_si = 55.0
        subs["short_interest"] = score_si
        detail_parts.append(f"SI {si_val:.1%} DTC {dtc_val:.1f}")

    inst = info.get("heldPercentInstitutions")
    if inst is not None:
        inst_val = float(inst)
        if inst_val > 0.60:
            subs["institutional"] = 80.0
        elif inst_val > 0.40:
            subs["institutional"] = 60.0
        else:
            subs["institutional"] = 45.0
        detail_parts.append(f"Inst {inst_val:.0%}")

    if not hist.empty and len(hist) >= 50 and spx_hist is not None and not spx_hist.empty:
        close_hist = hist["Close"].dropna()
        close_spx = spx_hist["Close"].dropna()
        if len(close_hist) >= 50 and len(close_spx) >= 50:
            stock_ret = float(close_hist.iloc[-1]) / float(close_hist.iloc[-50]) - 1
            spx_ret = float(close_spx.iloc[-1]) / float(close_spx.iloc[-50]) - 1
            rel_momentum = stock_ret - spx_ret
        if rel_momentum > 0.10:
            subs["momentum"] = 80.0
        elif rel_momentum > 0.0:
            subs["momentum"] = 60.0
        elif rel_momentum > -0.10:
            subs["momentum"] = 40.0
        else:
            subs["momentum"] = 20.0
        detail_parts.append(f"RelMom {rel_momentum:+.1%}")

    pe = info.get("trailingPE")
    eps_growth = info.get("earningsGrowth")
    if pe is not None and eps_growth is not None:
        pe_val = float(pe)
        eps_val = float(eps_growth)
        if 0 < pe_val < 15 and eps_val > 0.10:
            subs["earnings_quality"] = 80.0
        elif eps_val > 0.10:
            subs["earnings_quality"] = 70.0
        elif eps_val > 0:
            subs["earnings_quality"] = 55.0
        else:
            subs["earnings_quality"] = 30.0
        detail_parts.append(f"P/E {pe_val:.1f} EPSg {eps_val:.1%}")

    try:
        exps = ticker.options
        if exps and len(exps) >= 2:
            pc_ratios = []
            for exp in exps[:4]:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts = chain.puts
                    if not calls.empty and not puts.empty:
                        c_vol = int(calls["volume"].sum()) if "volume" in calls.columns else 0
                        p_vol = int(puts["volume"].sum()) if "volume" in puts.columns else 0
                        if c_vol > 0:
                            pc_ratios.append(p_vol / c_vol)
                except Exception:
                    continue
            if pc_ratios:
                avg_pc = sum(pc_ratios) / len(pc_ratios)
                if avg_pc > 1.5:
                    subs["options_sentiment"] = 80.0
                elif avg_pc > 1.0:
                    subs["options_sentiment"] = 65.0
                elif avg_pc > 0.7:
                    subs["options_sentiment"] = 50.0
                else:
                    subs["options_sentiment"] = 35.0
                detail_parts.append(f"P/C avg {avg_pc:.2f}")
    except Exception:
        pass

    if fetch_news and symbol:
        try:
            from trading_mcp.analysis.sentiment_web import (
                compute_social_sentiment,
                fetch_yfinance_news,
                fetch_wsb_hotlist,
            )

            news_score, news_detail = fetch_yfinance_news(symbol, timeout=5)
            if news_score is not None:
                subs["web_news"] = news_score
                detail_parts.append(f"News: {news_detail}")
            else:
                from trading_mcp.analysis.sentiment_web import fetch_finviz_news
                news_score, news_detail = fetch_finviz_news(symbol, timeout=5)
                if news_score is not None:
                    subs["web_news"] = news_score
                    detail_parts.append(f"Finviz: {news_detail}")

            if wsb_hotlist is None:
                try:
                    wsb_hotlist = fetch_wsb_hotlist(timeout=5)
                except Exception:
                    wsb_hotlist = None

            social_score, social_detail = compute_social_sentiment(symbol, wsb_hotlist)
            if social_score is not None:
                subs["social_media"] = social_score
                detail_parts.append(f"Social: {social_detail}")

        except Exception:
            pass
    elif wsb_hotlist:
        symbol_upper = symbol.upper() if symbol else ""
        if symbol_upper and symbol_upper in wsb_hotlist:
            from trading_mcp.analysis.sentiment_web import compute_social_sentiment
            social_score, social_detail = compute_social_sentiment(symbol, wsb_hotlist)
            if social_score is not None:
                subs["social_media"] = social_score
                detail_parts.append(f"Social: {social_detail}")

    total_weight = 0.0
    weighted_sum = 0.0
    for dim, weight in WEIGHTS.items():
        sub_score = subs.get(dim)
        if sub_score is not None:
            weighted_sum += sub_score * weight
            total_weight += weight

    if total_weight > 0:
        final_score = int(round(min(100.0, max(0.0, weighted_sum / total_weight))))
    else:
        final_score = 50

    detail = " | ".join(detail_parts) if detail_parts else "Basic sentiment"

    return final_score, detail, subs


def earnings_proximity_adjustment(
    _symbol: str, days_to_earnings: int | None, _iv_rank: float | None
) -> float | None:
    """Compute earnings proximity adjustment factor."""
    if days_to_earnings is None:
        return None
    if days_to_earnings <= 3:
        return 0.15
    if days_to_earnings <= 7:
        return 0.10
    if days_to_earnings <= 14:
        return 0.05
    return 0.0
