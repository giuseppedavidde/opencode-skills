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
from pydantic import BaseModel, Field
from scipy.stats import norm

from trading_mcp.data.provider import data_provider
from trading_mcp.data.risk_free import get_risk_free_rate

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.environ.get("TRADING_CACHE_DIR", "/tmp/opencode/options_cache"))
_MEM_CACHE: dict[str, dict[str, Any]] = {}
_MEM_CACHE_TIMES: dict[str, float] = {}
_MEM_CACHE_TTL: float = 300.0  # 5 minutes for intraday freshness

# ── Robust IV-surface parameters ──────────────────────────────────────
_IV_MIN: float = 0.01          # 1%  — below this an IV is not credible
_IV_MAX: float = 5.0           # 500% — above this an IV is an outlier
_IV_OUTLIER_Z: float = 3.5     # robust z threshold for MAD rejection
_IV_REL_TOL: float = 0.75      # max |quote-smile|/smile to keep a real quote
_IRLS_ITERS: int = 4           # robust reweighting iterations
_SMILE_MIN_POINTS: int = 4     # minimum valid quotes to fit a smile
_SMILE_DEGREE: int = 2         # quadratic smile in log-moneyness
_IV_SRC_QUOTE = "quote"        # IV taken straight from a valid live quote
_IV_SRC_SMILE = "smile"        # IV interpolated from the fitted smile
_IV_SRC_FALLBACK = "fallback"  # no fit possible → flat fallback sigma


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
    # Fall back to disk cache (7-day TTL for weekend/holiday use).
    # Defensive read: a corrupted/partial file (concurrent writer) is ignored
    # and treated as a miss instead of crashing the tool.
    cache_file = _CACHE_DIR / f"{ticker}_{expiry or 'auto'}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("options cache payload non e' un dizionario")
            cached_date = data.get("_cached_at", "")
            if cached_date:
                days_old = (date.today() - date.fromisoformat(cached_date[:10])).days
                if days_old <= 7:
                    _MEM_CACHE[cache_key] = data
                    _MEM_CACHE_TIMES[cache_key] = time.time()
                    logger.debug("Options cache hit (disk) for %s (%d days old)", ticker, days_old)
                    return data
        except (json.JSONDecodeError, ValueError, KeyError, TypeError, OSError) as e:
            logger.warning("Ignoring corrupt options disk cache for %s: %s", ticker, e)
    return None


def _save_cached_chain(ticker: str, expiry: str | None, data: dict[str, Any]) -> None:
    cache_key = f"{ticker}_{expiry or 'auto'}"
    data["_cached_at"] = date.today().isoformat()
    _MEM_CACHE[cache_key] = data
    _MEM_CACHE_TIMES[cache_key] = time.time()
    # Atomic write (temp file in the same dir + os.replace) so parallel MCP
    # processes never observe a partially-written cache file.
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / f"{cache_key}.json"
        tmp_file = _CACHE_DIR / f".{cache_key}.{os.getpid()}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, cache_file)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Failed to save options cache for %s: %s", ticker, e)


def fetch_options_chain(  # pylint: disable=too-many-locals,too-many-return-statements
    ticker: str,
    expiry: str | None = None,
    use_cache: bool = True,
    strike_window: int | None = 10,
    full_chain: bool = False,
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
        full_chain: When True, force the full chain regardless of
            ``strike_window`` (used by GEX so wing strikes are not lost).
    """
    # Sanitize: MCP may send the string "null" instead of JSON null
    if expiry is not None and isinstance(expiry, str) and expiry.strip().lower() in ("null", "none", ""):
        expiry = None

    strike_window = None if full_chain else strike_window

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

    tte = _time_to_expiry(selected_expiry)
    sigma = live_iv or 0.3
    rate_snapshot = get_risk_free_rate()
    r = rate_snapshot.value

    # Robust IV surface fitted on the FULL chain (wings included), so
    # strikes with stale/missing quotes get an interpolated smile IV
    # instead of a flat fallback sigma.
    surface = _robust_iv_surface(calls_df, puts_df, spot, sigma)
    calls_list, calls_res = _resolve_legs(
        spot, calls_df, tte, r, sigma, "call", surface, strike_window
    )
    puts_list, puts_res = _resolve_legs(
        spot, puts_df, tte, r, sigma, "put", surface, strike_window
    )
    iv_metrics.update(_iv_quality_metrics(surface, calls_res, puts_res))

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
            "iv_coverage_pct": 0.0,
            "num_quote_iv": 0,
            "num_synthetic_iv": 0,
            "num_fallback_iv": 0,
            "smile_fitted": False,
        },
        "_source": "fallback",
        "_fallback_note": f"{error_msg}. {'Weekend: try Monday-Friday.' if _is_weekend() else 'Retry later.'}",
    }


def _window_bounds(
    df: pd.DataFrame, spot: float, window: int | None
) -> tuple[int, int]:
    """Return the half-open positional ``(lo, hi)`` slice around ATM.

    Args:
        df: Chain DataFrame with a ``strike`` column (sorted ascending).
        spot: Underlying price used to locate the ATM strike.
        window: Strikes to keep on each side of ATM. None → full chain.

    Returns:
        ``(0, len(df))`` for a full chain, else the ATM-centred bounds.
    """
    if window is None or window < 0 or df.empty or "strike" not in df.columns:
        return 0, len(df)
    strikes = df["strike"].to_numpy(dtype=float)
    atm_idx = int(np.argmin(np.abs(strikes - spot)))
    lo = max(0, atm_idx - window)
    hi = min(len(df), atm_idx + window + 1)
    return lo, hi


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
    lo, hi = _window_bounds(df, spot, window)
    if not lo and hi == len(df):
        return df
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


class IvSurface(BaseModel):
    """Robust per-expiry IV smile fitted on log-moneyness ``ln(K/S)``."""

    spot: float
    coeffs: list[float] = Field(default_factory=list)
    fallback_sigma: float = 0.3
    fitted: bool = False
    n_quote: int = 0
    n_outliers: int = 0
    residual_mad: float = 0.0

    def predict(self, strikes: np.ndarray) -> np.ndarray:
        """Evaluate the fitted smile at ``strikes`` (clipped to a sane range)."""
        strikes = np.asarray(strikes, dtype=float)
        if not self.fitted or not self.coeffs or self.spot <= 0:
            return np.full(strikes.shape[0], self.fallback_sigma, dtype=float)
        log_m = np.log(strikes / self.spot)
        predicted = np.polyval(np.asarray(self.coeffs, dtype=float), log_m)
        return np.clip(predicted, _IV_MIN, _IV_MAX)


class IvResolution(BaseModel):
    """IV actually used per strike, with provenance and quality counts."""

    iv_used: list[float] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    n_quote: int = 0
    n_smile: int = 0
    n_fallback: int = 0

    @property
    def coverage_pct(self) -> float:
        """Share of strikes backed by a real quote (percent)."""
        total = self.n_quote + self.n_smile + self.n_fallback
        return round(100.0 * self.n_quote / total, 1) if total else 0.0


def _collect_surface_points(
    calls_df: pd.DataFrame, puts_df: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Collect valid quotes ``(strikes, ivs, oi_weights)`` for the smile fit.

    A quote is usable when it has a finite IV inside ``(_IV_MIN, _IV_MAX)``
    and at least some market presence (a bid, ask, volume or open interest).
    """
    strikes: list[float] = []
    ivs: list[float] = []
    weights: list[float] = []
    for frame in (calls_df, puts_df):
        if frame is None or frame.empty:
            continue
        if "strike" not in frame.columns or "impliedVolatility" not in frame.columns:
            continue
        strike = frame["strike"].to_numpy(dtype=float)
        iv = frame["impliedVolatility"].to_numpy(dtype=float)
        rows = frame.shape[0]
        bid = frame["bid"].to_numpy(dtype=float) if "bid" in frame.columns else np.zeros(rows)
        ask = frame["ask"].to_numpy(dtype=float) if "ask" in frame.columns else np.zeros(rows)
        oi = (
            frame["openInterest"].to_numpy(dtype=float)
            if "openInterest" in frame.columns
            else np.zeros(rows)
        )
        vol = frame["volume"].to_numpy(dtype=float) if "volume" in frame.columns else np.zeros(rows)
        bid = np.nan_to_num(bid)
        ask = np.nan_to_num(ask)
        oi = np.nan_to_num(oi)
        vol = np.nan_to_num(vol)
        mask = np.isfinite(iv) & (iv > _IV_MIN) & (iv < _IV_MAX) & (strike > 0)
        mask &= (bid > 0) | (ask > 0) | (oi > 0) | (vol > 0)
        for pos in np.nonzero(mask)[0]:
            strikes.append(float(strike[pos]))
            ivs.append(float(iv[pos]))
            weights.append(max(float(oi[pos]), 1.0))
    return (
        np.asarray(strikes, dtype=float),
        np.asarray(ivs, dtype=float),
        np.asarray(weights, dtype=float),
    )


def _fit_robust_smile(
    log_moneyness: np.ndarray,
    ivs: np.ndarray,
    weights: np.ndarray,
    degree: int,
) -> tuple[np.ndarray, np.ndarray]:
    """IRLS (Cauchy) polynomial fit of IV on log-moneyness.

    Re-weights observations down as their robust residual grows, so a few
    bad quotes cannot bend the smile. Returns the coefficients and the
    boolean inlier mask (``|robust z| <= _IV_OUTLIER_Z``).
    """
    coeffs = np.polyfit(log_moneyness, ivs, degree, w=np.sqrt(weights))
    inliers = np.ones(ivs.shape[0], dtype=bool)
    for _ in range(_IRLS_ITERS):
        residual = ivs - np.polyval(coeffs, log_moneyness)
        scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
        if scale <= 0.0 or not np.isfinite(scale):
            break
        robust_z = np.abs(residual) / scale
        inliers = robust_z <= _IV_OUTLIER_Z
        if int(inliers.sum()) < max(_SMILE_MIN_POINTS, degree + 1):
            break
        cauchy = 1.0 / (1.0 + robust_z ** 2)
        fit_w = np.sqrt(weights * cauchy)
        coeffs = np.polyfit(log_moneyness, ivs, degree, w=fit_w)
    return coeffs, inliers


def _robust_iv_surface(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    spot: float,
    sigma_fallback: float,
) -> IvSurface:
    """Fit a robust IV smile on log-moneyness from all valid chain quotes.

    Quotes are filtered by range, dropped when they lack any market
    presence, and outliers are rejected with a MAD robust z-score before
    a weighted (by open interest) polynomial fit of degree
    ``_SMILE_DEGREE``. When too few points survive, ``fitted`` stays
    ``False`` and consumers fall back to a flat ``sigma_fallback``.

    Args:
        calls_df: Call chain DataFrame.
        puts_df: Put chain DataFrame.
        spot: Underlying spot price (log-moneyness pivot).
        sigma_fallback: Flat sigma used when no fit is possible.

    Returns:
        The fitted :class:`IvSurface` (``fitted=False`` if too few points).
    """
    surface = IvSurface(spot=spot, fallback_sigma=sigma_fallback)
    strikes, ivs, weights = _collect_surface_points(calls_df, puts_df)
    surface.n_quote = int(strikes.size)
    if strikes.size < _SMILE_MIN_POINTS or spot <= 0:
        return surface

    log_m = np.log(strikes / spot)
    degree = min(_SMILE_DEGREE, strikes.size - 1)
    coeffs, inliers = _fit_robust_smile(log_m, ivs, weights, degree)
    surface.n_outliers = int((~inliers).sum())

    if _SMILE_MIN_POINTS <= int(inliers.sum()) < strikes.size:
        log_m = log_m[inliers]
        degree = min(_SMILE_DEGREE, int(inliers.sum()) - 1)
        coeffs = np.polyfit(log_m, ivs[inliers], degree, w=np.sqrt(weights[inliers]))
        residual = ivs[inliers] - np.polyval(coeffs, log_m)
    else:
        residual = ivs - np.polyval(coeffs, log_m)

    surface.coeffs = [float(coeff) for coeff in coeffs]
    surface.fitted = True
    mad = float(np.median(np.abs(residual))) if residual.size else 0.0
    surface.residual_mad = mad if np.isfinite(mad) else 0.0
    logger.debug(
        "IV surface: %d quotes, %d outliers, degree=%d",
        surface.n_quote,
        surface.n_outliers,
        len(surface.coeffs) - 1,
    )
    return surface


def _apply_iv_surface(
    df: pd.DataFrame, surface: IvSurface, sigma_override: float
) -> IvResolution:
    """Resolve the IV to use per strike, tagging each with a provenance.

    A strike keeps its raw quote when it is finite, inside the sane range,
    and consistent with the fitted smile; otherwise it is replaced by the
    smile interpolation, or by ``sigma_override`` when no fit exists.

    Args:
        df: Chain DataFrame (call or put side).
        surface: Fitted IV surface from :func:`_robust_iv_surface`.
        sigma_override: Flat sigma used as the last-resort fallback.

    Returns:
        An :class:`IvResolution` with per-strike ``iv_used`` + ``sources``.
    """
    if df is None or df.empty:
        return IvResolution()
    size = df.shape[0]
    if "impliedVolatility" in df.columns:
        raw = df["impliedVolatility"].to_numpy(dtype=float)
    else:
        raw = np.full(size, np.nan, dtype=float)
    if "strike" in df.columns:
        strikes = df["strike"].to_numpy(dtype=float)
    else:
        strikes = np.full(size, np.nan, dtype=float)
    predicted = surface.predict(strikes)
    tolerance = np.maximum(_IV_OUTLIER_Z * surface.residual_mad, _IV_REL_TOL * predicted)

    iv_used: list[float] = []
    sources: list[str] = []
    for pos in range(size):
        value = float(raw[pos])
        is_quote = bool(
            np.isfinite(value)
            and _IV_MIN < value < _IV_MAX
            and (not surface.fitted or abs(value - predicted[pos]) <= tolerance[pos])
        )
        if is_quote:
            iv_used.append(value)
            sources.append(_IV_SRC_QUOTE)
        elif surface.fitted:
            iv_used.append(float(predicted[pos]))
            sources.append(_IV_SRC_SMILE)
        else:
            iv_used.append(float(sigma_override))
            sources.append(_IV_SRC_FALLBACK)

    return IvResolution(
        iv_used=iv_used,
        sources=sources,
        n_quote=sources.count(_IV_SRC_QUOTE),
        n_smile=sources.count(_IV_SRC_SMILE),
        n_fallback=sources.count(_IV_SRC_FALLBACK),
    )


def _iv_quality_metrics(
    surface: IvSurface, calls_res: IvResolution, puts_res: IvResolution
) -> dict[str, Any]:
    """Summarize IV provenance across both sides of the chain."""
    n_quote = calls_res.n_quote + puts_res.n_quote
    n_smile = calls_res.n_smile + puts_res.n_smile
    n_fallback = calls_res.n_fallback + puts_res.n_fallback
    total = n_quote + n_smile + n_fallback
    return {
        "iv_coverage_pct": round(100.0 * n_quote / total, 1) if total else 0.0,
        "num_quote_iv": n_quote,
        "num_synthetic_iv": n_smile,
        "num_fallback_iv": n_fallback,
        "smile_fitted": surface.fitted,
        "smile_outliers_removed": surface.n_outliers,
    }


def _resolve_legs(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    spot: float,
    df: pd.DataFrame,
    tte: float,
    r: float,
    sigma: float,
    opt_type: str,
    surface: IvSurface,
    window: int | None,
) -> tuple[list[dict[str, Any]], IvResolution]:
    """Resolve IV, compute Greeks and serialize one side of the chain.

    Applies the robust IV surface, trims the DataFrame to the ATM window
    (keeping the resolved IV aligned), then computes Greeks and builds the
    leg dictionaries, returning the resolution for quality accounting.
    """
    resolution = _apply_iv_surface(df, surface, sigma)
    lo, hi = _window_bounds(df, spot, window)
    iv_used = resolution.iv_used[lo:hi]
    sources = resolution.sources[lo:hi]
    trimmed = df.iloc[lo:hi]
    greeks = _compute_chain_greeks(
        spot, trimmed, tte, r, sigma, opt_type, iv_used=iv_used
    )
    legs = _chain_to_list(trimmed, greeks, iv_used, sources)
    return legs, resolution


def _compute_chain_greeks(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    spot: float,
    df: pd.DataFrame,
    tte: float,
    r: float,
    sigma_override: float,
    opt_type: str,
    iv_used: np.ndarray | list[float] | None = None,
) -> pd.DataFrame:
    """Compute Greeks for a whole chain via vectorized numpy (fix M3).

    Numerically identical to the previous per-row loop, but 10-100x faster
    on chains with 200+ strikes.

    Args:
        spot: Underlying spot price.
        df: Chain DataFrame (needs a ``strike`` column).
        tte: Time to expiry in years.
        r: Risk-free rate.
        sigma_override: Flat sigma used where the resolved IV is unusable.
        opt_type: ``"call"`` or ``"put"``.
        iv_used: Optional pre-resolved per-strike IV (e.g. from the robust
            IV surface). When omitted, the raw ``impliedVolatility`` column
            is used with a flat fallback (legacy behaviour).
    """
    sqrt_t = np.sqrt(max(tte, 0.001))

    strikes = df["strike"].to_numpy(dtype=float)
    resolved: np.ndarray | None = None
    if iv_used is not None:
        candidate = np.asarray(iv_used, dtype=float)
        if candidate.shape[0] == strikes.shape[0]:
            resolved = candidate
    if resolved is None:
        if "impliedVolatility" in df.columns:
            resolved = df["impliedVolatility"].to_numpy(dtype=float)
        else:
            resolved = np.full(len(df), np.nan, dtype=float)
    iv = np.where(np.isfinite(resolved) & (resolved > 0), resolved, sigma_override)

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


def _chain_to_list(  # pylint: disable=too-many-locals
    df: pd.DataFrame,
    greeks: pd.DataFrame,
    iv_used: np.ndarray | list[float] | None = None,
    iv_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Serialize a chain DataFrame (with Greeks) into a list of leg dicts.

    Args:
        df: Chain DataFrame.
        greeks: Greeks aligned with ``df`` (by index).
        iv_used: Optional per-strike IV actually used for the Greeks.
        iv_sources: Optional per-strike IV provenance labels.

    Returns:
        List of leg dictionaries including ``iv_used`` and ``iv_source``.
    """
    resolved = np.asarray(iv_used, dtype=float) if iv_used is not None else None
    sources = list(iv_sources) if iv_sources is not None else None
    result = []
    for pos, (idx, row) in enumerate(df.iterrows()):
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

        if resolved is not None and pos < resolved.shape[0]:
            leg_iv = float(resolved[pos])
        else:
            leg_iv = float(iv)
        leg_source = _IV_SRC_QUOTE if leg_iv > 0 else _IV_SRC_FALLBACK
        if sources is not None and pos < len(sources):
            leg_source = sources[pos]

        entry: dict[str, Any] = {
            "strike": float(row["strike"]),
            "bid": round(float(bid), 4),
            "ask": round(float(ask), 4),
            "volume": int(vol),
            "openInterest": int(oi),
            "impliedVolatility": round(float(iv), 4),
            "iv_used": round(leg_iv, 4),
            "iv_source": leg_source,
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
