"""Options chain data fetching via DataProvider with weekend fallback."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from trading_mcp.data.provider import data_provider
from trading_mcp.data.risk_free import get_risk_free_rate

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.environ.get("TRADING_CACHE_DIR", "/tmp/opencode/options_cache"))
_MEM_CACHE: dict[str, dict[str, Any]] = {}
_MEM_CACHE_TIMES: dict[str, float] = {}
_MEM_CACHE_TTL: float = 300.0  # 5 minutes for intraday freshness

def _is_weekend() -> bool:
    return date.today().weekday() >= 5


def _load_cached_chain(ticker: str, expiry: str | None) -> dict[str, Any] | None:
    cache_key = f"{ticker}_{expiry or 'auto'}"
    # Check in-memory cache with TTL
    if cache_key in _MEM_CACHE:
        cached_time = _MEM_CACHE_TIMES.get(cache_key, 0.0)
        age = time.time() - cached_time
        if age <= _MEM_CACHE_TTL:
            logger.debug("Options cache hit (memory) for %s (%.1fs old)", ticker, age)
            return _MEM_CACHE[cache_key]
        # Expired — remove from memory cache
        del _MEM_CACHE[cache_key]
        _MEM_CACHE_TIMES.pop(cache_key, None)
    # Fall back to disk cache (7-day TTL for weekend/holiday use)
    cache_file = _CACHE_DIR / f"{ticker}_{expiry or 'auto'}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                cached_date = data.get("_cached_at", "")
                if cached_date:
                    days_old = (date.today() - date.fromisoformat(cached_date[:10])).days
                    if days_old <= 7:
                        _MEM_CACHE[cache_key] = data
                        _MEM_CACHE_TIMES[cache_key] = time.time()
                        logger.debug("Options cache hit (disk) for %s (%d days old)", ticker, days_old)
                        return data
        except Exception as e:
            logger.warning("Failed to load options disk cache for %s: %s", ticker, e)
    return None


def _save_cached_chain(ticker: str, expiry: str | None, data: dict[str, Any]) -> None:
    cache_key = f"{ticker}_{expiry or 'auto'}"
    data["_cached_at"] = date.today().isoformat()
    _MEM_CACHE[cache_key] = data
    _MEM_CACHE_TIMES[cache_key] = time.time()
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / f"{cache_key}.json"
        with open(cache_file, "w") as f:
            json.dump(data, f, default=str)
    except Exception as e:
        logger.warning("Failed to save options cache for %s: %s", ticker, e)


def fetch_options_chain(
    ticker: str, expiry: str | None = None, use_cache: bool = True
) -> dict[str, Any]:
    """Fetch options chain with Greeks and IV metrics.

    On weekends or when the live chain is unavailable, returns cached data
    from the last 7 days. Sets _source to 'live' or 'cache'.

    Args:
        ticker: Stock ticker symbol.
        expiry: Optional target expiry (YYYY-MM-DD). Auto-selects if None.
        use_cache: If True, fall back to cache on failure.
    """
    # Sanitize: MCP may send the string "null" instead of JSON null
    if expiry is not None and isinstance(expiry, str) and expiry.strip().lower() in ("null", "none", ""):
        expiry = None

    if use_cache:
        cached = _load_cached_chain(ticker, expiry)
    else:
        cached = None

    # Use DataProvider for info (6h TTL) and spot price
    info = data_provider.get_info(ticker)
    spot = 0.0
    if info:
        spot = info.get("currentPrice", 0.0)
    if spot == 0.0:
        hist = data_provider.get_hist(ticker, period="5d")
        if not hist.empty:
            spot = float(hist["Close"].iloc[-1])

    live_iv = info.get("impliedVolatility") if info else None

    # Use DataProvider for expirations (1h TTL)
    try:
        expirations = data_provider.get_options_expirations(ticker)
    except Exception as e:
        if cached:
            cached.setdefault("_source", "cache")
            cached.setdefault("_fallback_note", f"Rate limited/error: {e}. Showing cached data")
            return cached
        return _fallback_response(ticker, spot, live_iv, f"Options not available: {e}")

    if not expirations:
        if cached:
            cached.setdefault("_source", "cache")
            cached.setdefault("_fallback_note", "No expirations today, showing cached data")
            return cached
        return _fallback_response(ticker, spot, live_iv, "No options available")

    selected_expiry = _select_expiry(expirations, expiry)

    chain = data_provider.get_options_chain(ticker, selected_expiry)
    if chain is None:
        if cached:
            cached.setdefault("_source", "cache")
            cached.setdefault("_fallback_note", f"Chain fetch failed for {selected_expiry}, showing cached data")
            return cached
        return _fallback_response(ticker, spot, live_iv, f"Cannot fetch chain for {selected_expiry}")

    calls_df = chain.calls.copy()
    puts_df = chain.puts.copy()

    tte = _time_to_expiry(selected_expiry)
    sigma = live_iv or 0.3
    rate_snapshot = get_risk_free_rate()
    r = rate_snapshot.value

    calls_greeks = _compute_chain_greeks(spot, calls_df, tte, r, sigma, "call")
    puts_greeks = _compute_chain_greeks(spot, puts_df, tte, r, sigma, "put")

    calls_list = _chain_to_list(calls_df, calls_greeks)
    puts_list = _chain_to_list(puts_df, puts_greeks)

    iv_metrics = _compute_iv_metrics(calls_df, puts_df, info)

    result = {
        "ticker": ticker,
        "underlying_price": round(spot, 2),
        "expirations": expirations,
        "selected_expiry": selected_expiry,
        "dte": int(tte * 365),
        "calls": calls_list,
        "puts": puts_list,
        "iv_metrics": iv_metrics,
        "_source": "live",
        "_fallback_note": None,
        "risk_free_rate": {
            "value": round(r, 6),
            "source": rate_snapshot.source_ticker,
            "as_of": rate_snapshot.as_of,
            "is_live": rate_snapshot.is_live,
            "fallback_reason": rate_snapshot.fallback_reason,
        },
    }

    _save_cached_chain(ticker, expiry, result)
    return result


def _fallback_response(ticker: str, spot: float, live_iv: Any, error_msg: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "underlying_price": round(spot, 2),
        "expirations": [],
        "selected_expiry": "",
        "dte": 0,
        "calls": [],
        "puts": [],
        "iv_metrics": {
            "atm_iv": round(float(live_iv or 0), 4),
            "iv_rank": 50.0,
            "iv_percentile": 50.0,
            "put_call_ratio_vol": 0.0,
            "put_call_ratio_oi": 0.0,
            "term_structure": [],
        },
        "_source": "fallback",
        "_fallback_note": f"{error_msg}. {'Weekend: try Monday-Friday.' if _is_weekend() else 'Retry later.'}",
    }

    calls_df = chain.calls.copy()
    puts_df = chain.puts.copy()

    tte = _time_to_expiry(selected_expiry)
    sigma = info.get("impliedVolatility", 0.3)
    rate_snap2 = get_risk_free_rate()
    r = rate_snap2.value

    calls_greeks = _compute_chain_greeks(spot, calls_df, tte, r, sigma, "call")
    puts_greeks = _compute_chain_greeks(spot, puts_df, tte, r, sigma, "put")

    calls_list = _chain_to_list(calls_df, calls_greeks)
    puts_list = _chain_to_list(puts_df, puts_greeks)

    iv_metrics = _compute_iv_metrics(calls_df, puts_df, info)

    return {
        "ticker": ticker,
        "underlying_price": round(spot, 2),
        "expirations": expirations,
        "selected_expiry": selected_expiry,
        "dte": int(tte * 365),
        "calls": calls_list,
        "puts": puts_list,
        "iv_metrics": iv_metrics,
    }


def _select_expiry(expirations: list[str], target: str | None) -> str:
    today = date.today()
    parsed = [datetime.strptime(e, "%Y-%m-%d").date() for e in expirations]

    if target:
        try:
            target_date = datetime.strptime(target, "%Y-%m-%d").date()
        except ValueError:
            target = None  # invalid date string, fall through to auto-select
        else:
            if target_date in parsed:
                return target
            closest = min(parsed, key=lambda d: abs((d - target_date).days))
            return closest.strftime("%Y-%m-%d")

    future = [d for d in parsed if d > today]
    if not future:
        return max(parsed).strftime("%Y-%m-%d")
    far_enough = [d for d in future if (d - today).days > 30]
    if far_enough:
        return min(far_enough).strftime("%Y-%m-%d")
    return min(future).strftime("%Y-%m-%d")


def _time_to_expiry(expiry_str: str) -> float:
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = date.today()
    days = (expiry_date - today).days
    return max(days, 1) / 365.0


def _compute_chain_greeks(
    spot: float,
    df: pd.DataFrame,
    tte: float,
    r: float,
    sigma_override: float,
    opt_type: str,
) -> pd.DataFrame:
    sqrt_t = np.sqrt(max(tte, 0.001))
    greeks = pd.DataFrame(index=df.index)
    greeks["delta"] = 0.0
    greeks["gamma"] = 0.0
    greeks["theta"] = 0.0
    greeks["vega"] = 0.0

    for idx, row in df.iterrows():
        strike = float(row["strike"])
        iv = row.get("impliedVolatility", sigma_override)
        if iv is None or np.isnan(iv) or iv <= 0:
            iv = sigma_override

        d1_val = (np.log(spot / strike) + (r + 0.5 * iv**2) * tte) / (iv * sqrt_t)
        d2_val = d1_val - iv * sqrt_t

        if opt_type == "call":
            greeks.loc[idx, "delta"] = norm.cdf(d1_val)
            greeks.loc[idx, "theta"] = (
                -spot * norm.pdf(d1_val) * iv / (2 * sqrt_t)
                - r * strike * np.exp(-r * tte) * norm.cdf(d2_val)
            ) / 365.0
        else:
            greeks.loc[idx, "delta"] = norm.cdf(d1_val) - 1
            greeks.loc[idx, "theta"] = (
                -spot * norm.pdf(d1_val) * iv / (2 * sqrt_t)
                + r * strike * np.exp(-r * tte) * norm.cdf(-d2_val)
            ) / 365.0

        greeks.loc[idx, "gamma"] = norm.pdf(d1_val) / (spot * iv * sqrt_t)
        greeks.loc[idx, "vega"] = spot * norm.pdf(d1_val) * sqrt_t / 100.0

    return greeks


def _chain_to_list(df: pd.DataFrame, greeks: pd.DataFrame) -> list[dict[str, Any]]:
    result = []
    for idx, row in df.iterrows():
        bid = row.get("bid", 0) or 0
        ask = row.get("ask", 0) or 0
        vol = row.get("volume", 0) or 0
        oi = row.get("openInterest", 0) or 0
        iv = row.get("impliedVolatility", 0) or 0

        if isinstance(vol, float) and np.isnan(vol):
            vol = 0
        if isinstance(oi, float) and np.isnan(oi):
            oi = 0
        if isinstance(iv, float) and np.isnan(iv):
            iv = 0.0
        if isinstance(bid, float) and np.isnan(bid):
            bid = 0.0
        if isinstance(ask, float) and np.isnan(ask):
            ask = 0.0

        entry: dict[str, Any] = {
            "strike": float(row["strike"]),
            "bid": round(float(bid), 4),
            "ask": round(float(ask), 4),
            "volume": int(vol),
            "openInterest": int(oi),
            "impliedVolatility": round(float(iv), 4),
        }
        if idx in greeks.index:
            entry["delta"] = round(float(greeks.loc[idx, "delta"]), 4)
            entry["gamma"] = round(float(greeks.loc[idx, "gamma"]), 4)
            entry["theta"] = round(float(greeks.loc[idx, "theta"]), 4)
            entry["vega"] = round(float(greeks.loc[idx, "vega"]), 4)
        result.append(entry)
    return result


def _compute_iv_metrics(
    calls_df: pd.DataFrame, puts_df: pd.DataFrame, info: dict[str, Any]
) -> dict[str, Any]:
    c_vol = int(calls_df["volume"].fillna(0).sum()) if "volume" in calls_df.columns else 0
    p_vol = int(puts_df["volume"].fillna(0).sum()) if "volume" in puts_df.columns else 0
    c_oi = int(calls_df["openInterest"].fillna(0).sum()) if "openInterest" in calls_df.columns else 0
    p_oi = int(puts_df["openInterest"].fillna(0).sum()) if "openInterest" in puts_df.columns else 0

    atm_iv = info.get("impliedVolatility", 0.0) or 0.0
    iv_rank = min(100.0, max(0.0, atm_iv * 100)) if isinstance(atm_iv, float) and atm_iv < 2 else 50.0
    iv_percentile = iv_rank

    all_ivs = []
    if "impliedVolatility" in calls_df.columns:
        all_ivs.extend(calls_df["impliedVolatility"].dropna().tolist())
    if "impliedVolatility" in puts_df.columns:
        all_ivs.extend(puts_df["impliedVolatility"].dropna().tolist())
    if all_ivs:
        atm_iv = float(np.median(all_ivs))
        min_iv = float(np.min(all_ivs))
        max_iv = float(np.max(all_ivs))
        if max_iv > min_iv:
            iv_rank = (atm_iv - min_iv) / (max_iv - min_iv) * 100
        else:
            iv_rank = 50.0

    term_structure: list[dict] = []

    return {
        "atm_iv": round(atm_iv, 4),
        "iv_rank": round(iv_rank, 1),
        "iv_percentile": round(iv_percentile, 1),
        "put_call_ratio_vol": round(p_vol / c_vol, 4) if c_vol > 0 else 0.0,
        "put_call_ratio_oi": round(p_oi / c_oi, 4) if c_oi > 0 else 0.0,
        "term_structure": term_structure,
    }
