"""Implied earnings move and event flags shared by the options tools."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from trading_mcp.analysis import iv_surface
from trading_mcp.analysis.options_market import ChainView, MarketContext, load_chains
from trading_mcp.data import market_calendar as mcal
from trading_mcp.timeutil import to_datetime


def implied_event_move(ctx: MarketContext, expirations: list[str], event_start: datetime,
                       views: dict[str, ChainView] | None = None) -> dict[str, Any]:
    """Market-implied move of an event (earnings) from the term structure of the chain.

    With an expiry before the event and one after it (and a diffusive volatility
    equal to the pre-event IV), the event variance is ``T2 * (iv2^2 - iv1^2)``.
    Without a pre-event expiry, the ATM straddle of the first post-event expiry
    is used (it also holds the normal diffusion, so it overstates the event).
    """
    out: dict[str, Any] = {"event_start": event_start.isoformat(), "method": None, "move_1sd_pct": None,
                           "expected_abs_move_pct": None, "expiries_used": [], "note": None}
    future = [e for e in expirations if ctx.tte(e) > 0]
    moments = {e: ctx.expiry_moment(e) for e in future}
    before = [e for e in future if moments[e] < event_start]
    after = [e for e in future if moments[e] >= event_start]
    if not after:
        out["note"] = "no listed expiry after the event"
        return out
    wanted = [after[0]] + ([before[-1]] if before else [])
    cache = dict(views or {})
    missing = [e for e in wanted if e not in cache]
    if missing:
        loaded, _ = load_chains(ctx.ticker, missing, now=ctx.now, source=ctx.source)
        cache.update(loaded)
    smiles = {e: iv_surface.build_smile(cache[e], ctx) for e in wanted if e in cache}
    post = smiles.get(after[0])
    if post is None or post.atm_iv is None:
        out["note"] = "no ATM IV for the first expiry after the event"
        return out
    if before and before[-1] in smiles and smiles[before[-1]].atm_iv is not None:
        pre = smiles[before[-1]]
        excess = post.atm_iv ** 2 - pre.atm_iv ** 2
        out["expiries_used"] = [pre.expiry, post.expiry]
        if excess <= 0:
            out["method"] = "term_structure"
            out["note"] = "post-event ATM IV is not above the pre-event IV: no event premium is priced"
            out["move_1sd_pct"] = 0.0
            out["expected_abs_move_pct"] = 0.0
            return out
        sigma_event = math.sqrt(post.T * excess)
        out["method"] = "term_structure"
        out["move_1sd_pct"] = round(sigma_event * 100.0, 3)
        out["expected_abs_move_pct"] = round(sigma_event * math.sqrt(2.0 / math.pi) * 100.0, 3)
        return out
    out["expiries_used"] = [post.expiry]
    if post.straddle_move is not None and ctx.price > 0:
        out["method"] = "atm_straddle_first_post_event_expiry"
        out["expected_abs_move_pct"] = round(post.straddle_move / ctx.price * 100.0, 3)
        out["note"] = "no expiry before the event: the straddle also prices the normal diffusion"
    return out


def earnings_block(ctx: MarketContext, until: datetime, expirations: list[str],
                   views: dict[str, ChainView] | None = None, *, with_move: bool = True) -> dict[str, Any]:
    """Earnings inside ``(now, until]`` with the implied move, or the reason it is unknown."""
    events = ctx.events
    window = getattr(events, "next_earnings", None) if events is not None else None
    quote_type = getattr(events, "quote_type", None) if events is not None else None
    block: dict[str, Any] = {"before_horizon": None, "next_earnings": None, "implied_move": None}
    if window is None or window.start is None:
        if quote_type == "EQUITY" or events is None:
            block["note"] = "next earnings date unknown: earnings risk not checked"
        else:
            block["before_horizon"] = False
            block["note"] = f"no earnings for quote type {quote_type}"
        return block
    start = to_datetime(window.start)
    block["next_earnings"] = window.model_dump()
    block["before_horizon"] = bool(start is not None and start <= until)
    if block["before_horizon"] and with_move and start is not None:
        block["implied_move"] = implied_event_move(ctx, expirations, start, views)
    return block


def ex_dividends_before(ctx: MarketContext, until: date) -> list[dict[str, Any]]:
    """Dividends with an ex-date from tomorrow up to ``until``."""
    today = mcal.exchange_today(ctx.ticker, ctx.now)
    return [
        event.model_dump() for event in ctx.dividends.events
        if today < date.fromisoformat(event.ex_date) <= until
    ]
