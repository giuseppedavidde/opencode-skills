"""Sentiment dimension (0-100, 50 = neutral; ``None`` when no input is known) — SIG-09.

Sub-scores and their signs follow the published evidence (documented priors,
unvalidated here):

- ``short_interest``: HIGH short interest is BEARISH. Heavily shorted stocks
  underperform on average (Desai, Ramesh, Thiagarajan & Balachandran 2002,
  Journal of Finance 57(5); Asquith, Pathak & Ritter 2005, Journal of
  Financial Economics 78(2)), and lightly shorted stocks earn positive
  abnormal returns (Boehmer, Huszar & Jordan 2010, Journal of Financial
  Economics 96(1)). Short % of float: > 20% 25, 10-20% 35, 5-10% 45,
  2-5% 50, < 2% 55; days to cover > 10 subtracts 5.
- ``options_sentiment``: a HIGH put/call volume ratio is BEARISH. Option
  volume carries information about future stock prices, and stocks with
  high put/call ratios underperform (Pan & Poteshman 2006, Review of
  Financial Studies 19(3)). The ratio here is total volume over the first
  four expiries (not open-buy volume, so it is noisier): > 1.5 35,
  1.0-1.5 42, 0.7-1.0 50, 0.5-0.7 55, < 0.5 58.
- ``institutional``: held by institutions > 70% 55, 40-70% 52, 10-40% 48,
  < 10% 45 (weak evidence; small effect).
- ``web_news``: negation-aware headline score
  (:func:`trading_mcp.analysis.sentiment_web.headline_polarity`).
- ``social_media``: retail attention on WSB, contrarian (high attention 40).

Weights: short_interest 0.30, options_sentiment 0.25, institutional 0.15,
web_news 0.20, social_media 0.10, renormalized over the known sub-scores.
Earnings quality (a fundamentals input) and price momentum (a price input)
are NOT part of sentiment, so they are not counted twice. Insider and retail
inputs were never filled, so they were removed.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

WEIGHTS = {
    "short_interest": 0.30,
    "options_sentiment": 0.25,
    "institutional": 0.15,
    "web_news": 0.20,
    "social_media": 0.10,
}


def short_interest_score(si: float | None, dtc: float | None) -> float | None:
    """Score of the short % of float (FRACTION) and days to cover (see the module docstring)."""
    if si is None:
        return None
    si = float(si)
    if si > 0.20:
        score = 25.0
    elif si > 0.10:
        score = 35.0
    elif si > 0.05:
        score = 45.0
    elif si > 0.02:
        score = 50.0
    else:
        score = 55.0
    if dtc is not None and float(dtc) > 10:
        score -= 5.0
    return score


def put_call_score(ratio: float | None) -> float | None:
    """Score of a put/call volume ratio (see the module docstring)."""
    if ratio is None:
        return None
    if ratio > 1.5:
        return 35.0
    if ratio > 1.0:
        return 42.0
    if ratio > 0.7:
        return 50.0
    if ratio > 0.5:
        return 55.0
    return 58.0


def institutional_score(held: float | None) -> float | None:
    """Score of the share held by institutions (FRACTION)."""
    if held is None:
        return None
    held = float(held)
    if held > 0.70:
        return 55.0
    if held > 0.40:
        return 52.0
    if held > 0.10:
        return 48.0
    return 45.0


def _put_call_ratio(symbol: str) -> float | None:
    from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

    exps = data_provider.get_options_expirations(symbol)
    if not exps or len(exps) < 2:
        return None
    ratios: list[float] = []
    for exp in exps[:4]:
        chain = data_provider.get_options_chain(symbol, exp)
        if chain is None or chain.calls.empty or chain.puts.empty:
            continue
        c_vol = float(pd.to_numeric(chain.calls.get("volume"), errors="coerce").fillna(0).sum())
        p_vol = float(pd.to_numeric(chain.puts.get("volume"), errors="coerce").fillna(0).sum())
        if c_vol > 0:
            ratios.append(p_vol / c_vol)
    return sum(ratios) / len(ratios) if ratios else None


def compute_sentiment_6d(
    ticker: Any,
    info: dict[str, Any],
    hist: pd.DataFrame | None = None,
    spx_hist: pd.DataFrame | None = None,
    wsb_hotlist: dict | None = None,
    fetch_news: bool = False,
    *,
    options: bool = True,
) -> tuple[float | None, str, dict[str, float | None]]:
    """Sentiment score, detail and sub-scores (see the module docstring).

    Args:
        ticker: Symbol (or a ``yf.Ticker``; only its symbol is used).
        info: yfinance ``info`` (short interest, institutional ownership).
        hist: Unused (kept for the call signature).
        spx_hist: Unused (momentum is no longer a sentiment input).
        wsb_hotlist: Pre-fetched WSB hotlist.
        fetch_news: Fetch headlines (yfinance, then Finviz) and the WSB hotlist.
        options: Read the put/call ratio from the option chains.
    """
    del hist, spx_hist
    symbol = ticker if isinstance(ticker, str) else str(getattr(ticker, "ticker", "") or info.get("symbol") or "")
    subs: dict[str, float | None] = {name: None for name in WEIGHTS}
    detail_parts: list[str] = []

    si, dtc = info.get("shortPercentOfFloat"), info.get("shortRatio")
    subs["short_interest"] = short_interest_score(si, dtc)
    if si is not None:
        detail_parts.append(f"SI {float(si):.1%}" + (f" DTC {float(dtc):.1f}" if dtc is not None else ""))

    inst = info.get("heldPercentInstitutions")
    subs["institutional"] = institutional_score(inst)
    if inst is not None:
        detail_parts.append(f"Inst {float(inst):.0%}")

    if options and symbol:
        try:
            ratio = _put_call_ratio(symbol)
        except Exception:  # pylint: disable=broad-exception-caught
            ratio = None
        subs["options_sentiment"] = put_call_score(ratio)
        if ratio is not None:
            detail_parts.append(f"P/C {ratio:.2f}")

    if fetch_news and symbol:
        from trading_mcp.analysis.sentiment_web import (  # pylint: disable=import-outside-toplevel
            compute_social_sentiment,
            fetch_finviz_news,
            fetch_wsb_hotlist,
            fetch_yfinance_news,
        )

        news_score, news_detail = fetch_yfinance_news(symbol, timeout=5)
        if news_score is None:
            news_score, news_detail = fetch_finviz_news(symbol, timeout=5)
        if news_score is not None:
            subs["web_news"] = news_score
            detail_parts.append(f"News: {news_detail}")
        if wsb_hotlist is None:
            wsb_hotlist = fetch_wsb_hotlist(timeout=5)
    if wsb_hotlist and symbol:
        from trading_mcp.analysis.sentiment_web import compute_social_sentiment  # pylint: disable=import-outside-toplevel

        social_score, social_detail = compute_social_sentiment(symbol, wsb_hotlist)
        if social_score is not None:
            subs["social_media"] = social_score
            detail_parts.append(f"Social: {social_detail}")

    known = {k: v for k, v in subs.items() if v is not None}
    mass = sum(WEIGHTS[k] for k in known)
    final = round(sum(WEIGHTS[k] * v for k, v in known.items()) / mass, 1) if mass > 0 else None
    coverage = mass / sum(WEIGHTS.values())
    detail = " | ".join(detail_parts) if detail_parts else "No sentiment inputs"
    detail += f" | coverage {coverage:.0%}"
    return final, detail, subs


def earnings_proximity_adjustment(
    _symbol: str, days_to_earnings: int | None, _iv_rank: float | None
) -> float | None:
    """Legacy alias of :func:`trading_mcp.analysis.earnings.earnings_proximity_adjustment`."""
    from trading_mcp.analysis.earnings import (  # pylint: disable=import-outside-toplevel
        earnings_proximity_adjustment as _impl,
    )

    return _impl(_symbol, days_to_earnings, _iv_rank)
