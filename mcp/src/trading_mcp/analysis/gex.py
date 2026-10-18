"""Gamma Exposure (GEX) analysis from an aggregated options chain.

Sign convention (dealer-positioning heuristic)
----------------------------------------------
Dealers are assumed to be LONG call gamma and SHORT put gamma, the
standard working assumption used by spot-gamma ("GEX") dashboards:

- Call GEX = ``+ gamma * OI * 100 * S^2 * 0.01``  (positive)
- Put  GEX = ``- gamma * OI * 100 * S^2 * 0.01``  (negative)
- Net GEX per strike = call GEX + put GEX
- Total Net GEX      = sum over all strikes

Units: dollars of dealer gamma exposure per **1% move** in the underlying.
A positive Net GEX means the dealer book is long gamma and mechanically
dampens moves (mean reversion / pinning). A negative Net GEX means the
book is short gamma and amplifies moves (higher realized volatility).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, NamedTuple

import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import norm

from trading_mcp.data.options_chain import fetch_options_chain

logger = logging.getLogger(__name__)

_CONTRACT_MULTIPLIER = 100.0
_PCT_MOVE = 0.01
_MAX_EXPIRIES_DEFAULT = 12
_MAX_DTE_DEFAULT = 120
_TOP_N_DEFAULT = 15
_MIN_DTE_DAYS = 1
_FLIP_GRID_POINTS = 81
_FLIP_GRID_WIDTH = 0.10

_CONVENTION = (
    "Call GEX positive, put GEX negative (dealers long call gamma / short "
    "put gamma). GEX = gamma * OI * 100 * S^2 * 0.01, in $ per 1% move. "
    "Gamma flip = spot where the repriced net GEX crosses zero."
)


class StrikeGex(BaseModel):
    """Per-strike gamma exposure breakdown."""

    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_oi: int = 0
    put_oi: int = 0
    call_gamma: float = 0.0
    put_gamma: float = 0.0
    iv: float = 0.0
    iv_source: str = "unknown"


class GexResult(BaseModel):
    """Structured Gamma Exposure analysis result."""

    ticker: str
    underlying_price: float
    expiries_used: list[str]
    n_strikes: int
    net_gex: float
    total_call_gex: float
    total_put_gex: float
    gamma_flip: float | None = None
    distance_to_flip_pct: float | None = None
    spot_position: str = "unknown"
    call_wall: float | None = None
    put_wall: float | None = None
    largest_positive_gamma_strike: float | None = None
    largest_negative_gamma_strike: float | None = None
    regime: str = "neutral"
    regime_description: str = ""
    profile: list[StrikeGex] = Field(default_factory=list)
    source: str = "live"
    data_source: str = "unknown"
    data_quality: str = "unknown"
    iv_coverage_pct: float | None = None
    num_quote_iv: int = 0
    num_synthetic_iv: int = 0
    num_fallback_iv: int = 0
    warnings: list[str] = Field(default_factory=list)
    convention: str = _CONVENTION


class _GexCore(BaseModel):
    """Computed GEX metrics, before ticker/source metadata is attached."""

    net_gex: float
    total_call_gex: float
    total_put_gex: float
    gamma_flip: float | None = None
    distance_to_flip_pct: float | None = None
    spot_position: str = "unknown"
    call_wall: float | None = None
    put_wall: float | None = None
    largest_positive_gamma_strike: float | None = None
    largest_negative_gamma_strike: float | None = None
    regime: str = "neutral"
    regime_description: str = ""
    profile: list[StrikeGex] = Field(default_factory=list)
    extra_warnings: list[str] = Field(default_factory=list)


class GexLeg(BaseModel):
    """One option leg needed to reprice dealer gamma across a spot grid."""

    strike: float
    tte: float
    rate: float
    sigma: float
    is_call: bool
    open_interest: float


def _strike_gex(gamma: float, open_interest: float, spot: float) -> float:
    """Return the raw unsigned gamma exposure for one option leg."""
    return gamma * open_interest * _CONTRACT_MULTIPLIER * (spot ** 2) * _PCT_MOVE


def aggregate_strikes(
    chains: list[dict[str, Any]], spot: float
) -> dict[float, dict[str, float]]:
    """Aggregate call/put gamma exposure per strike across multiple chains.

    Args:
        chains: List of ``fetch_options_chain`` payloads.
        spot: Underlying spot price used for the $S^2$ scaling.

    Returns:
        Mapping ``strike -> {call_gex, put_gex, call_oi, put_oi,
        call_gamma, put_gamma, iv_num, iv_den, src_quote, src_smile,
        src_fallback}`` with signed GEX values. The ``iv_*``/``src_*`` keys
        carry an OI-weighted IV and its dominant provenance per strike.
    """
    agg: dict[float, dict[str, float]] = {}
    for chain in chains:
        for key, sign in (("calls", 1.0), ("puts", -1.0)):
            for leg in chain.get(key) or []:
                strike = float(leg.get("strike", 0.0) or 0.0)
                gamma = float(leg.get("gamma", 0.0) or 0.0)
                open_interest = float(leg.get("openInterest", 0.0) or 0.0)
                gex = sign * _strike_gex(gamma, open_interest, spot)
                entry = agg.setdefault(
                    strike,
                    {
                        "call_gex": 0.0,
                        "put_gex": 0.0,
                        "call_oi": 0.0,
                        "put_oi": 0.0,
                        "call_gamma": 0.0,
                        "put_gamma": 0.0,
                        "iv_num": 0.0,
                        "iv_den": 0.0,
                        "src_quote": 0.0,
                        "src_smile": 0.0,
                        "src_fallback": 0.0,
                    },
                )
                if sign > 0:
                    entry["call_gex"] += gex
                    entry["call_oi"] += open_interest
                    entry["call_gamma"] += gamma
                else:
                    entry["put_gex"] += gex
                    entry["put_oi"] += open_interest
                    entry["put_gamma"] += gamma
                _accumulate_iv(entry, leg, open_interest)
    return agg


def _accumulate_iv(
    entry: dict[str, float], leg: dict[str, Any], open_interest: float
) -> None:
    """Add one leg's IV and provenance to a strike accumulator (OI-weighted)."""
    iv = float(leg.get("iv_used", 0.0) or 0.0)
    weight = open_interest if open_interest > 0 else 1.0
    entry["iv_num"] += iv * weight
    entry["iv_den"] += weight
    source = str(leg.get("iv_source") or "unknown")
    if source in ("quote", "vendor"):
        entry["src_quote"] += weight
    elif source == "smile":
        entry["src_smile"] += weight
    elif source == "fallback":
        entry["src_fallback"] += weight


def _dominant_source(data: dict[str, float]) -> str:
    """Return the OI-weighted dominant IV provenance for a strike."""
    weights = {
        "quote": data.get("src_quote", 0.0),
        "smile": data.get("src_smile", 0.0),
        "fallback": data.get("src_fallback", 0.0),
    }
    best = max(weights, key=lambda name: weights[name])
    return best if weights[best] > 0.0 else "unknown"


def build_profile(agg: dict[float, dict[str, float]]) -> list[StrikeGex]:
    """Convert the aggregated mapping into a strike-sorted profile."""
    profile: list[StrikeGex] = []
    for strike in sorted(agg):
        data = agg[strike]
        den = data.get("iv_den", 0.0)
        iv = data.get("iv_num", 0.0) / den if den > 0 else 0.0
        profile.append(
            StrikeGex(
                strike=strike,
                call_gex=data["call_gex"],
                put_gex=data["put_gex"],
                net_gex=data["call_gex"] + data["put_gex"],
                call_oi=int(data["call_oi"]),
                put_oi=int(data["put_oi"]),
                call_gamma=data["call_gamma"],
                put_gamma=data["put_gamma"],
                iv=round(iv, 4),
                iv_source=_dominant_source(data),
            )
        )
    return profile


def _bs_gamma(
    spot: np.ndarray | float,
    strike: np.ndarray | float,
    tte: np.ndarray | float,
    rate: np.ndarray | float,
    sigma: np.ndarray | float,
) -> np.ndarray:
    """Black-Scholes gamma per share (European, no dividend yield).

    Mirrors the gamma used by the options chain so that repricing at the
    current spot reproduces the per-leg gamma exactly.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(spot / strike) + (rate + 0.5 * sigma ** 2) * tte) / (
            sigma * np.sqrt(tte)
        )
        gamma = norm.pdf(d1) / (spot * sigma * np.sqrt(tte))
    return np.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)


class _LegArrays(NamedTuple):
    """Vectorised repricing inputs, one entry per option leg."""

    strikes: np.ndarray
    ttes: np.ndarray
    rates: np.ndarray
    sigmas: np.ndarray
    is_calls: np.ndarray
    open_interests: np.ndarray


def _leg_arrays(legs: list[GexLeg]) -> _LegArrays:
    """Pack the legs into column arrays for fast repricing."""
    return _LegArrays(
        strikes=np.array([leg.strike for leg in legs], dtype=float),
        ttes=np.array([leg.tte for leg in legs], dtype=float),
        rates=np.array([leg.rate for leg in legs], dtype=float),
        sigmas=np.array([leg.sigma for leg in legs], dtype=float),
        is_calls=np.array([leg.is_call for leg in legs], dtype=bool),
        open_interests=np.array([leg.open_interest for leg in legs], dtype=float),
    )


def _net_gex_grid(data: _LegArrays, grid: np.ndarray) -> np.ndarray:
    """Signed net GEX on candidate spot prices, in dollars per 1% move."""
    if grid.size == 0 or data.strikes.size == 0:
        return np.zeros(grid.shape, dtype=float)
    level = grid[:, None]
    gamma = _bs_gamma(
        level,
        data.strikes[None, :],
        data.ttes[None, :],
        data.rates[None, :],
        data.sigmas[None, :],
    )
    signs = np.where(data.is_calls, 1.0, -1.0)
    contrib = (signs * data.open_interests)[None, :] * gamma
    totals = contrib.sum(axis=1) * _CONTRACT_MULTIPLIER * _PCT_MOVE
    return totals * grid ** 2


def net_gex_at_spot(legs: list[GexLeg], spot: float) -> float:
    """Reprice the signed net GEX (dollars per 1% move) at a candidate spot."""
    if not legs or spot <= 0.0:
        return 0.0
    return float(_net_gex_grid(_leg_arrays(legs), np.array([spot]))[0])


def find_gamma_flip(
    legs: list[GexLeg],
    spot: float,
    n_grid: int = _FLIP_GRID_POINTS,
    width: float = _FLIP_GRID_WIDTH,
) -> float | None:
    """Locate the zero-gamma ("gamma flip") spot level.

    Reprices the signed net GEX at ``n_grid`` candidate prices spanning
    ``spot`` +/- ``width`` and linearly interpolates the nearest sign
    change, matching the reference methodology (repricing grid). This
    replaces the previous cumulative-by-strike approximation, which froze
    the per-leg gammas at the current spot and could return ``None`` even
    when a true zero-gamma level existed.

    Args:
        legs: Repricing inputs (one entry per option leg).
        spot: Current underlying price.
        n_grid: Number of candidate prices on the grid.
        width: Half-width of the grid as a fraction of spot (0.10 = +/-10%).

    Returns:
        Interpolated zero-gamma spot price, or ``None`` when the repriced
        net GEX does not change sign anywhere on the grid.
    """
    if not legs or spot <= 0.0 or n_grid < 2:
        return None
    grid = np.linspace(1.0 - width, 1.0 + width, n_grid) * spot
    totals = _net_gex_grid(_leg_arrays(legs), grid)

    sign = np.sign(totals)
    crossings = np.where(sign[:-1] * sign[1:] < 0.0)[0]
    if crossings.size == 0:
        return None
    nearest = crossings[np.argmin(np.abs(grid[crossings] - spot))]
    x0, x1 = float(grid[nearest]), float(grid[nearest + 1])
    y0, y1 = float(totals[nearest]), float(totals[nearest + 1])
    if y1 == y0:
        return x0
    return x0 + (0.0 - y0) / (y1 - y0) * (x1 - x0)


def _extreme_strike(
    profile: list[StrikeGex], attr: str, most_negative: bool
) -> float | None:
    """Return the strike with the extreme value of ``attr`` (or ``None``)."""
    if not profile:
        return None
    if most_negative:
        best = min(profile, key=lambda point: getattr(point, attr))
        return best.strike if getattr(best, attr) < 0.0 else None
    best = max(profile, key=lambda point: getattr(point, attr))
    return best.strike if getattr(best, attr) > 0.0 else None


def _regime(net_gex: float) -> tuple[str, str]:
    """Classify the dealer gamma regime from total net GEX."""
    if net_gex > 0.0:
        return (
            "long_gamma",
            "Dealers are long gamma: expect mean-reversion and price pinning "
            "toward high-gamma strikes; realized volatility is suppressed.",
        )
    if net_gex < 0.0:
        return (
            "short_gamma",
            "Dealers are short gamma: hedging flow amplifies moves; expect "
            "trend continuation and elevated realized volatility.",
        )
    return "neutral", "Net gamma exposure is flat."


def _expiries_within_dte(available: list[Any], max_dte: int) -> list[str]:
    """Parse, sort and keep expirations with 1 <= DTE <= ``max_dte`` days."""
    today = date.today()
    dated: list[tuple[int, str]] = []
    for raw in available:
        try:
            parsed = datetime.strptime(str(raw), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        dte = (parsed - today).days
        if _MIN_DTE_DAYS <= dte <= max_dte:
            dated.append((dte, str(raw)))
    dated.sort()
    return [value for _, value in dated]


def _evenly_spaced(values: list[str], cap: int) -> list[str]:
    """Pick up to ``cap`` values evenly spaced across the term structure."""
    if len(values) <= cap:
        return list(values)
    indices = np.linspace(0, len(values) - 1, cap).round().astype(int)
    picked: list[str] = []
    for idx in indices:
        value = values[int(idx)]
        if value not in picked:
            picked.append(value)
    return picked


def _select_expiries(
    first: dict[str, Any],
    expiry: str | None,
    max_expiries: int,
    max_dte: int = _MAX_DTE_DEFAULT,
) -> list[str]:
    """Choose which expirations to aggregate for the GEX computation.

    Mirrors the reference: expirations beyond ``max_dte`` days and 0DTE
    (fewer than ``_MIN_DTE_DAYS`` days) are dropped. When more than
    ``max_expiries`` survive, the kept expirations are evenly spaced across
    the surviving term structure so the GEX is not over-concentrated in the
    near-dated contracts.
    """
    selected = first.get("selected_expiry")
    if expiry is not None:
        return [selected] if selected else []
    available = first.get("expirations") or []
    if not available:
        return [selected] if selected else []
    ordered = _expiries_within_dte(available, max_dte)
    if not ordered:
        return [selected] if selected else []
    return _evenly_spaced(ordered, max(1, max_expiries))


def _fetch_chains(
    ticker: str, first: dict[str, Any], expiries: list[str], warnings: list[str]
) -> list[dict[str, Any]]:
    """Fetch one chain per expiry, tolerating individual failures."""
    chains: list[dict[str, Any]] = [first]
    for exp in expiries:
        if exp == first.get("selected_expiry"):
            continue
        try:
            chain = fetch_options_chain(ticker, expiry=exp, full_chain=True)
            if chain.get("calls") or chain.get("puts"):
                chains.append(chain)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("GEX: skipped expiry %s for %s: %s", exp, ticker, exc)
            warnings.append(f"Skipped expiry {exp}: {exc}")
    return chains


def _iv_quality(chains: list[dict[str, Any]]) -> dict[str, float | int | None]:
    """Aggregate IV provenance across all legs of all chains.

    Returns:
        ``{"coverage_pct", "num_quote", "num_synthetic", "num_fallback"}``
        where ``coverage_pct`` is the share of legs backed by a real quote,
        and ``num_synthetic`` counts smile-interpolated IVs. ``coverage_pct``
        is ``None`` when no legs are available.
    """
    n_quote = n_smile = n_fallback = n_unknown = 0
    for chain in chains:
        for key in ("calls", "puts"):
            for leg in chain.get(key) or []:
                source = str(leg.get("iv_source") or "unknown")
                if source in ("quote", "vendor"):
                    n_quote += 1
                elif source == "smile":
                    n_smile += 1
                elif source == "fallback":
                    n_fallback += 1
                else:
                    n_unknown += 1
    total = n_quote + n_smile + n_fallback + n_unknown
    coverage = round(100.0 * n_quote / total, 1) if total else None
    return {
        "coverage_pct": coverage,
        "num_quote": n_quote,
        "num_synthetic": n_smile,
        "num_fallback": n_fallback,
    }


def _tte_years(expiry: str | None) -> float:
    """Time to expiry in years (min 1 day), matching the chain greeks."""
    if not expiry:
        return 0.0
    try:
        parsed = datetime.strptime(str(expiry), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return 0.0
    return max((parsed - date.today()).days, _MIN_DTE_DAYS) / 365.0


def collect_legs(chains: list[dict[str, Any]]) -> list[GexLeg]:
    """Collect the repricing inputs (one :class:`GexLeg` per usable leg).

    Legs without open interest or a usable IV are skipped, since they
    cannot contribute to the repriced net GEX.
    """
    legs: list[GexLeg] = []
    for chain in chains:
        tte = _tte_years(chain.get("selected_expiry"))
        if tte <= 0.0:
            continue
        rate = float((chain.get("risk_free_rate") or {}).get("value") or 0.0)
        for key, is_call in (("calls", True), ("puts", False)):
            for leg in chain.get(key) or []:
                open_interest = float(leg.get("openInterest", 0.0) or 0.0)
                sigma = float(leg.get("iv_used", 0.0) or 0.0)
                if open_interest <= 0.0 or sigma <= 0.0:
                    continue
                legs.append(
                    GexLeg(
                        strike=float(leg.get("strike", 0.0) or 0.0),
                        tte=tte,
                        rate=rate,
                        sigma=sigma,
                        is_call=is_call,
                        open_interest=open_interest,
                    )
                )
    return legs


def _empty_result(
    ticker: str, spot: float, expiries: list[str], source: str, warnings: list[str]
) -> dict[str, Any]:
    """Build the zero-data GEX payload."""
    return GexResult(
        ticker=ticker.upper(),
        underlying_price=round(spot, 2),
        expiries_used=expiries,
        n_strikes=0,
        net_gex=0.0,
        total_call_gex=0.0,
        total_put_gex=0.0,
        source=source,
        data_source=source,
        data_quality="unavailable",
        warnings=warnings,
    ).model_dump()


def analyze_gex(
    ticker: str,
    expiry: str | None = None,
    max_expiries: int = _MAX_EXPIRIES_DEFAULT,
    top_n: int = _TOP_N_DEFAULT,
    max_dte: int = _MAX_DTE_DEFAULT,
) -> dict[str, Any]:
    """Compute Gamma Exposure (GEX) metrics for ``ticker``.

    Fetches the option chain via the shared :func:`fetch_options_chain`
    utility. When ``expiry`` is ``None`` the chains of up to
    ``max_expiries`` listed expirations are aggregated; otherwise only the
    requested expiration is used. Expirations beyond ``max_dte`` calendar
    days and 0DTE contracts are excluded (mirroring the reference GEX
    methodology).

    Args:
        ticker: Stock ticker symbol.
        expiry: Optional ``YYYY-MM-DD`` expiration to restrict the analysis.
        max_expiries: Cap on the number of expirations aggregated.
        top_n: Number of strikes kept in the returned profile.
        max_dte: Maximum days to expiry for aggregated expirations.

    Returns:
        JSON-serializable GEX report (see :class:`GexResult`).
    """
    first = fetch_options_chain(ticker, expiry=expiry, full_chain=True)
    spot = float(first.get("underlying_price") or 0.0)
    expiries = _select_expiries(first, expiry, max_expiries, max_dte)
    source = str(first.get("_source", "unknown"))

    if spot <= 0.0 or not expiries:
        return _empty_result(
            ticker,
            spot,
            expiries,
            source,
            ["No usable option chain / spot price for GEX analysis."],
        )

    warnings: list[str] = []
    chains = _fetch_chains(ticker, first, expiries, warnings)
    profile = build_profile(aggregate_strikes(chains, spot))
    if not profile:
        return _empty_result(
            ticker,
            spot,
            expiries,
            source,
            warnings + ["Option chain carried no gamma/open interest data."],
        )

    result = _summarize(profile, collect_legs(chains), spot, top_n)
    quality = _iv_quality(chains)
    if quality["coverage_pct"] is not None and quality["coverage_pct"] < 70.0:
        warnings.append(
            f"Low IV coverage ({quality['coverage_pct']:.1f}% real quotes); "
            f"GEX relies on {quality['num_synthetic']} smile-interpolated and "
            f"{quality['num_fallback']} fallback IVs."
        )
    payload = GexResult(
        **result.model_dump(exclude={"extra_warnings"}),
        ticker=ticker.upper(),
        underlying_price=round(spot, 2),
        expiries_used=expiries,
        n_strikes=len(profile),
        source=source,
        data_source=str(first.get("data_source", source)),
        data_quality=str(first.get("data_quality", "unknown")),
        iv_coverage_pct=quality["coverage_pct"],
        num_quote_iv=int(quality["num_quote"]),
        num_synthetic_iv=int(quality["num_synthetic"]),
        num_fallback_iv=int(quality["num_fallback"]),
        warnings=warnings + result.extra_warnings,
    )
    logger.info(
        "GEX %s: net=%.2f flip=%s regime=%s strikes=%d",
        ticker,
        payload.net_gex,
        payload.gamma_flip,
        payload.regime,
        len(profile),
    )
    return payload.model_dump()


def _summarize(
    profile: list[StrikeGex], legs: list[GexLeg], spot: float, top_n: int
) -> _GexCore:
    """Compute the GEX metrics and the top-|GEX| profile slice."""
    total_call = sum(point.call_gex for point in profile)
    total_put = sum(point.put_gex for point in profile)
    net_gex = total_call + total_put
    gamma_flip = find_gamma_flip(legs, spot)
    regime, regime_description = _regime(net_gex)

    distance: float | None = None
    position = "unknown"
    if gamma_flip is not None and spot > 0.0:
        distance = round((spot - gamma_flip) / spot * 100.0, 2)
        position = "above_flip" if spot >= gamma_flip else "below_flip"

    extra_warnings: list[str] = []
    if all(point.call_gamma == 0.0 and point.put_gamma == 0.0 for point in profile):
        extra_warnings.append("All per-strike gammas are zero; GEX may be unreliable.")

    by_abs = sorted(profile, key=lambda point: abs(point.net_gex), reverse=True)
    return _GexCore(
        net_gex=round(net_gex, 2),
        total_call_gex=round(total_call, 2),
        total_put_gex=round(total_put, 2),
        gamma_flip=round(gamma_flip, 2) if gamma_flip is not None else None,
        distance_to_flip_pct=distance,
        spot_position=position,
        call_wall=_extreme_strike(profile, "call_gex", most_negative=False),
        put_wall=_extreme_strike(profile, "put_gex", most_negative=True),
        largest_positive_gamma_strike=_extreme_strike(
            profile, "net_gex", most_negative=False
        ),
        largest_negative_gamma_strike=_extreme_strike(
            profile, "net_gex", most_negative=True
        ),
        regime=regime,
        regime_description=regime_description,
        profile=by_abs[: max(1, top_n)],
        extra_warnings=extra_warnings,
    )
