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
    ticker: str,
    expiry: str | None = None,
    use_cache: bool = True,
    strike_window: int | None = 10,
) -> dict[str, Any]:
    """Fetch options chain with Greeks and IV metrics.

    On weekends or when the live chain is unavailable, returns cached data
    from the last 7 days. Sets _source to 'live' or 'cache'.

    Args:
        ticker: Stock ticker symbol.
        expiry: Optional target expiry (YYYY-MM-DD). Auto-selects if None.
        use_cache: If True, fall back to cache on failure.
        strike_window: Number of strikes to keep around ATM on each side.
            Default 10 (±10 strikes) reduces payload by 70-90%. Pass None
            (or -1) to return the full chain explicitly.
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

    # IV metrics on the FULL chain (ratios representative), then trim
    # the returned strike lists to the ATM window (fix A3).
    iv_metrics = _compute_iv_metrics(calls_df, puts_df, spot)

    calls_df = _filter_strike_window(calls_df, spot, strike_window)
    puts_df = _filter_strike_window(puts_df, spot, strike_window)

    tte = _time_to_expiry(selected_expiry)
    sigma = live_iv or 0.3
    rate_snapshot = get_risk_free_rate()
    r = rate_snapshot.value

    calls_greeks = _compute_chain_greeks(spot, calls_df, tte, r, sigma, "call")
    puts_greeks = _compute_chain_greeks(spot, puts_df, tte, r, sigma, "put")

    calls_list = _chain_to_list(calls_df, calls_greeks)
    puts_list = _chain_to_list(puts_df, puts_greeks)

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
            "atm_iv": round(float(live_iv), 4) if live_iv else None,
            "iv_rank": None,
            "iv_percentile": None,
            "iv_range_position": None,
            "put_call_ratio_vol": 0.0,
            "put_call_ratio_oi": 0.0,
            "term_structure": [],
        },
        "_source": "fallback",
        "_fallback_note": f"{error_msg}. {'Weekend: try Monday-Friday.' if _is_weekend() else 'Retry later.'}",
    }


def _filter_strike_window(
    df: pd.DataFrame, spot: float, window: int | None
) -> pd.DataFrame:
    """Trim a chain DataFrame to ``window`` strikes around the ATM strike.

    Args:
        df: Chain DataFrame with a ``strike`` column (sorted ascending).
        spot: Underlying price used to locate the ATM strike.
        window: Strikes to keep on each side of ATM. None → full chain.

    Returns:
        A filtered copy, or the original DataFrame when window is None.
    """
    if window is None or window < 0 or df.empty or "strike" not in df.columns:
        return df
    strikes = df["strike"].to_numpy(dtype=float)
    atm_idx = int(np.argmin(np.abs(strikes - spot)))
    lo = max(0, atm_idx - window)
    hi = min(len(df), atm_idx + window + 1)
    return df.iloc[lo:hi]


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
    """Compute Greeks for a whole chain via vectorized numpy (fix M3).

    Numerically identical to the previous per-row loop, but 10-100x faster
    on chains with 200+ strikes.
    """
    sqrt_t = np.sqrt(max(tte, 0.001))

    strikes = df["strike"].to_numpy(dtype=float)
    if "impliedVolatility" in df.columns:
        iv = df["impliedVolatility"].to_numpy(dtype=float)
        iv = np.where(np.isnan(iv) | (iv <= 0), sigma_override, iv)
    else:
        iv = np.full(len(df), sigma_override, dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(spot / strikes) + (r + 0.5 * iv ** 2) * tte) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t

    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)

    if opt_type == "call":
        delta = cdf_d1
        theta = (
            -spot * pdf_d1 * iv / (2 * sqrt_t)
            - r * strikes * np.exp(-r * tte) * norm.cdf(d2)
        ) / 365.0
    else:
        delta = cdf_d1 - 1.0
        theta = (
            -spot * pdf_d1 * iv / (2 * sqrt_t)
            + r * strikes * np.exp(-r * tte) * norm.cdf(-d2)
        ) / 365.0

    gamma = pdf_d1 / (spot * iv * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t / 100.0

    return pd.DataFrame(
        {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
        },
        index=df.index,
    )


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


def _nearest_strike_iv(df: pd.DataFrame, spot: float) -> float | None:
    """Return the IV at the strike nearest to ``spot``, or ``None``."""
    if df.empty or "strike" not in df.columns or "impliedVolatility" not in df.columns:
        return None
    idx = (df["strike"] - spot).abs().idxmin()
    try:
        iv = float(df.loc[idx, "impliedVolatility"])
    except (TypeError, ValueError):
        return None
    return iv if np.isfinite(iv) and iv > 0 else None


def _collect_ivs(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> list[float]:
    """Collect all finite positive IVs from both sides of the chain."""
    all_ivs: list[float] = []
    for df in (calls_df, puts_df):
        if "impliedVolatility" in df.columns:
            all_ivs.extend(float(v) for v in df["impliedVolatility"].dropna() if v > 0)
    return all_ivs


def _compute_iv_metrics(
    calls_df: pd.DataFrame, puts_df: pd.DataFrame, spot: float
) -> dict[str, Any]:
    """Compute IV metrics anchored on the true ATM strike.

    ``atm_iv`` is the mean of the call and put IV at the strike nearest to
    ``spot`` — the same definition used by the Bali/Bakshi tools — NOT a
    median over the whole chain, which is contaminated by the volatility
    smile/skew and by strikes outside the returned window.

    ``iv_rank`` / ``iv_percentile`` require a historical IV series; since
    none is available here they are ``None`` (never a misleading in-chain
    value). The within-chain min-max position — explicitly not a historical
    rank — is exposed separately as ``iv_range_position``.
    """
    c_vol = int(calls_df["volume"].fillna(0).sum()) if "volume" in calls_df.columns else 0
    p_vol = int(puts_df["volume"].fillna(0).sum()) if "volume" in puts_df.columns else 0
    c_oi = int(calls_df["openInterest"].fillna(0).sum()) if "openInterest" in calls_df.columns else 0
    p_oi = int(puts_df["openInterest"].fillna(0).sum()) if "openInterest" in puts_df.columns else 0

    # ── ATM IV: nearest-strike call/put, mirroring bali/bakshi ────────
    atm_iv: float | None = None
    if spot > 0 and not calls_df.empty and not puts_df.empty:
        call_iv = _nearest_strike_iv(calls_df, spot)
        put_iv = _nearest_strike_iv(puts_df, spot)
        if call_iv is not None and put_iv is not None:
            atm_iv = (call_iv + put_iv) / 2
        else:
            atm_iv = call_iv if call_iv is not None else put_iv

    # ── Within-chain IV range position (NOT a historical rank) ────────
    iv_range_position: float | None = None
    if atm_iv is not None:
        all_ivs = _collect_ivs(calls_df, puts_df)
        if all_ivs:
            min_iv = float(np.min(all_ivs))
            max_iv = float(np.max(all_ivs))
            if max_iv > min_iv:
                iv_range_position = round((atm_iv - min_iv) / (max_iv - min_iv) * 100, 1)

    term_structure: list[dict] = []

    return {
        "atm_iv": round(atm_iv, 4) if atm_iv is not None else None,
        "iv_rank": None,
        "iv_percentile": None,
        "iv_range_position": iv_range_position,
        "put_call_ratio_vol": round(p_vol / c_vol, 4) if c_vol > 0 else 0.0,
        "put_call_ratio_oi": round(p_oi / c_oi, 4) if c_oi > 0 else 0.0,
        "term_structure": term_structure,
    }
