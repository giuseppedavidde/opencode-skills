"""Per-expiry implied-volatility smile, term structure and risk-neutral distribution.

Smile of one expiry (:func:`build_smile`):

- Points are out-of-the-money quotes only: puts with a strike under the
  forward, calls at or above it. A point needs a two-sided quote, a mid inside
  the no-arbitrage bounds and a spread of at most 50% of the mid. Its IV is
  solved from the mid with our own rate, dividends and exercise style (vendor
  IV is a cross-check only).
- Fit: raw SVI on total variance ``w(k) = a + b(rho(k-m) + sqrt((k-m)^2+s^2))``
  with ``k = ln(K/F)``, weighted by the inverse spread. The fit is rejected
  when Durrleman's ``g(k)`` is negative (butterfly arbitrage) or the error is
  large; a robust quadratic in ``k`` (Cauchy IRLS) is then used and flagged.
  Beyond the quoted range the quadratic is held flat.
- Static checks on the quotes: monotone call and put prices with bid/ask, and
  convex mids.
- Summary: forward-ATM IV, 25-delta risk reversal and butterfly, 1-SD move,
  ATM straddle move, put-call-parity forward (a cross-check of the dividend
  and borrow inputs).

Term structure (:func:`term_structure`) checks that ATM total variance does
not fall with maturity. :func:`constant_maturity_iv` interpolates total
variance to a fixed number of days. :func:`terminal_distribution` gives the
risk-neutral law of ``S_T`` from the smile (Breeden-Litzenberger:
``CDF(K) = 1 + dC/dK`` on undiscounted Black prices), or a lognormal law at the
ATM IV when no smile exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.special import ndtr

from trading_mcp.analysis import pricing
from trading_mcp.analysis.options_market import ChainView, MarketContext

MAX_SPREAD_PCT = 0.5
SVI_MIN_POINTS = 5
POLY_MIN_POINTS = 3
_MAX_RMSE_VOL = 0.05
_IRLS_ITERS = 4
_OUTLIER_Z = 3.5
METHOD_SVI = "svi"
METHOD_POLY = "poly2"
METHOD_NONE = "none"


@dataclass
class SmileFit:
    """Fitted smile of one expiry (see the module docstring)."""

    expiry: str
    T: float
    spot: float
    forward: float
    rate: float
    q: float
    style: str
    iv_model: str
    method: str = METHOD_NONE
    params: dict[str, float] = field(default_factory=dict)
    k_min: float | None = None
    k_max: float | None = None
    n_points: int = 0
    n_candidates: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    rmse_vol: float | None = None
    atm_iv: float | None = None
    atm_iv_source: str | None = None
    rr25: float | None = None
    bf25: float | None = None
    expected_move: float | None = None
    straddle_move: float | None = None
    forward_parity: float | None = None
    butterfly_arbitrage: bool | None = None
    min_durrleman_g: float | None = None
    monotonicity_violations: int = 0
    convexity_violations: int = 0
    warnings: list[str] = field(default_factory=list)
    point_k: list[float] = field(default_factory=list)
    point_iv: list[float] = field(default_factory=list)

    @property
    def fitted(self) -> bool:
        """True when a smile function exists."""
        return self.method in (METHOD_SVI, METHOD_POLY)

    def iv_k(self, k: Any) -> np.ndarray:
        """Smile IV at log-moneyness ``k`` (NaN without a fit)."""
        k_arr = np.asarray(k, dtype=float)
        if self.method == METHOD_SVI:
            w = _svi_w(self.params, k_arr)
            with np.errstate(invalid="ignore"):
                return np.clip(np.sqrt(np.maximum(w, 1e-12) / self.T), pricing.IV_MIN, pricing.IV_MAX)
        if self.method == METHOD_POLY:
            lo = self.k_min if self.k_min is not None else -np.inf
            hi = self.k_max if self.k_max is not None else np.inf
            coeffs = [self.params[f"c{i}"] for i in range(3)]
            return np.clip(np.polyval(coeffs, np.clip(k_arr, lo, hi)), pricing.IV_MIN, pricing.IV_MAX)
        return np.full(k_arr.shape, np.nan)

    def iv(self, strikes: Any) -> np.ndarray:
        """Smile IV at listed strikes."""
        return self.iv_k(np.log(np.asarray(strikes, dtype=float) / self.forward))

    def summary(self) -> dict[str, Any]:
        """Wire block (decimals; IV and moves unrounded to 6 places)."""
        def rnd(value: float | None, places: int = 6) -> float | None:
            return round(float(value), places) if value is not None and math.isfinite(value) else None

        return {
            "expiry": self.expiry,
            "dte": rnd(self.T * 365.0, 3),
            "forward": rnd(self.forward, 4),
            "forward_parity": rnd(self.forward_parity, 4),
            "method": self.method,
            "iv_model": self.iv_model,
            "n_points": self.n_points,
            "n_candidates": self.n_candidates,
            "rejected": dict(self.rejected),
            "rmse_vol": rnd(self.rmse_vol),
            "atm_iv": rnd(self.atm_iv),
            "atm_iv_source": self.atm_iv_source,
            "rr25": rnd(self.rr25),
            "bf25": rnd(self.bf25),
            "expected_move_1sd": rnd(self.expected_move, 4),
            "expected_move_1sd_pct": rnd(self.expected_move / self.spot * 100.0, 3)
            if self.expected_move is not None and self.spot > 0 else None,
            "straddle_move": rnd(self.straddle_move, 4),
            "straddle_move_pct": rnd(self.straddle_move / self.spot * 100.0, 3)
            if self.straddle_move is not None and self.spot > 0 else None,
            "butterfly_arbitrage": self.butterfly_arbitrage,
            "min_durrleman_g": rnd(self.min_durrleman_g),
            "quote_monotonicity_violations": self.monotonicity_violations,
            "quote_convexity_violations": self.convexity_violations,
            "warnings": list(self.warnings),
        }


def _svi_w(params: dict[str, float], k: np.ndarray) -> np.ndarray:
    a, b, rho, m, s = (params[name] for name in ("a", "b", "rho", "m", "sigma"))
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + s * s))


def durrleman_g(params: dict[str, float], k: np.ndarray) -> np.ndarray:
    """Durrleman's butterfly condition for raw SVI (``g >= 0`` means no arbitrage)."""
    a, b, rho, m, s = (params[name] for name in ("a", "b", "rho", "m", "sigma"))
    root = np.sqrt((k - m) ** 2 + s * s)
    w = a + b * (rho * (k - m) + root)
    w1 = b * (rho + (k - m) / root)
    w2 = b * s * s / root ** 3
    with np.errstate(divide="ignore", invalid="ignore"):
        return (1.0 - k * w1 / (2.0 * w)) ** 2 - 0.25 * w1 * w1 * (1.0 / w + 0.25) + 0.5 * w2


def _fit_svi(k: np.ndarray, w: np.ndarray, weights: np.ndarray) -> tuple[dict[str, float], float] | None:
    from scipy.optimize import least_squares  # pylint: disable=import-outside-toplevel

    sw = np.sqrt(weights / weights.mean())
    w_max = float(w.max())
    k_lo, k_hi = float(k.min()), float(k.max())
    width = max(k_hi - k_lo, 0.05)
    lower = [-w_max, 1e-6, -0.999, k_lo - width, 1e-4]
    upper = [2.0 * w_max, 20.0, 0.999, k_hi + width, 5.0]
    k_at = float(k[np.argmin(w)])
    starts = [
        (0.8 * float(w.min()), 0.1, -0.4, k_at, 0.1),
        (0.5 * float(w.min()), 0.3, -0.7, 0.0, 0.2),
        (float(w.min()), 0.05, 0.0, k_at, 0.05),
        (0.2 * float(w.min()), 0.5, -0.2, 0.05, 0.3),
    ]

    def residual(x: np.ndarray) -> np.ndarray:
        params = dict(zip(("a", "b", "rho", "m", "sigma"), x))
        model = _svi_w(params, k)
        floor = x[0] + x[1] * x[4] * math.sqrt(max(1.0 - x[2] ** 2, 0.0))
        penalty = 1e3 * max(0.0, -floor)
        return np.append(sw * (model - w), penalty)

    best = None
    for start in starts:
        x0 = np.clip(np.asarray(start, dtype=float), lower, upper)
        try:
            fit = least_squares(residual, x0, bounds=(lower, upper), method="trf", max_nfev=400)
        except (ValueError, FloatingPointError):
            continue
        if best is None or fit.cost < best.cost:
            best = fit
    if best is None or not np.all(np.isfinite(best.x)):
        return None
    params = dict(zip(("a", "b", "rho", "m", "sigma"), (float(v) for v in best.x)))
    return params, float(best.cost)


def _fit_poly(k: np.ndarray, iv: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Robust quadratic fit of IV on log-moneyness (Cauchy IRLS)."""
    degree = min(2, k.shape[0] - 1)
    coeffs = np.polyfit(k, iv, degree, w=np.sqrt(weights))
    for _ in range(_IRLS_ITERS):
        residual = iv - np.polyval(coeffs, k)
        scale = 1.4826 * float(np.median(np.abs(residual - np.median(residual))))
        if scale <= 0.0 or not np.isfinite(scale):
            break
        z = np.abs(residual) / scale
        coeffs = np.polyfit(k, iv, degree, w=np.sqrt(weights / (1.0 + z * z)))
    coeffs = np.asarray(coeffs, dtype=float)
    return np.concatenate([np.zeros(3 - coeffs.shape[0]), coeffs])


def _quote_checks(side_strikes: np.ndarray, bid: np.ndarray, ask: np.ndarray, is_call: bool) -> tuple[int, int]:
    """Count monotonicity (bid above a cheaper ask) and convexity violations."""
    ok = np.isfinite(bid) & np.isfinite(ask) & (ask >= bid)
    K, b, a = side_strikes[ok], bid[ok], ask[ok]
    mono = 0
    for i in range(K.shape[0] - 1):
        if is_call and b[i + 1] > a[i] + 1e-9:
            mono += 1
        if not is_call and b[i] > a[i + 1] + 1e-9:
            mono += 1
    convex = 0
    mid = 0.5 * (a + b)
    half = 0.5 * (a - b)
    for i in range(1, K.shape[0] - 1):
        left = (mid[i] - mid[i - 1]) / (K[i] - K[i - 1])
        right = (mid[i + 1] - mid[i]) / (K[i + 1] - K[i])
        tol = (half[i - 1] + 2 * half[i] + half[i + 1]) / min(K[i] - K[i - 1], K[i + 1] - K[i])
        if right < left - tol - 1e-9:
            convex += 1
    return mono, convex


def _solve_points(view: ChainView, ctx: MarketContext, T: float, r: float, q: float,
                  forward: float, iv_model: str, steps: int) -> dict[str, Any]:
    """OTM points with own IV from the mid, plus rejection counts."""
    times, amounts = ctx.schedule()
    style = pricing.STYLE_EUROPEAN if iv_model == pricing.STYLE_EUROPEAN else ctx.style
    rejected: dict[str, int] = {}
    strikes: list[np.ndarray] = []
    ivs: list[np.ndarray] = []
    spreads: list[np.ndarray] = []
    candidates = 0
    for is_call in (False, True):
        side = view.side(is_call)
        if not len(side):
            continue
        otm = side.strike >= forward if is_call else side.strike < forward
        candidates += int(otm.sum())
        ok = otm & side.quote_ok & (side.bid > 0)
        rejected["no_two_sided_quote"] = rejected.get("no_two_sided_quote", 0) + int((otm & ~ok).sum())
        spread = side.spread_pct
        wide = ok & ~(spread <= MAX_SPREAD_PCT)
        rejected["wide_spread"] = rejected.get("wide_spread", 0) + int(wide.sum())
        ok &= spread <= MAX_SPREAD_PCT
        if not np.any(ok):
            continue
        K = side.strike[ok]
        mid = side.mid[ok]
        lower, upper = pricing.no_arbitrage_bounds(ctx.price, K, T, r, q, is_call, style, times, amounts)
        bounded = (mid > lower) & (mid < upper)
        rejected["outside_bounds"] = rejected.get("outside_bounds", 0) + int((~bounded).sum())
        if not np.any(bounded):
            continue
        iv, status = pricing.implied_vol(mid[bounded], ctx.price, K[bounded], T, r, q, is_call, style,
                                         times, amounts, steps=steps)
        good = np.isfinite(iv) & (iv > pricing.IV_MIN) & (iv < pricing.IV_MAX)
        rejected["iv_unsolved"] = rejected.get("iv_unsolved", 0) + int((~good).sum())
        strikes.append(K[bounded][good])
        ivs.append(iv[good])
        spreads.append(spread[ok][bounded][good])
        del status
    if strikes:
        K_all = np.concatenate(strikes)
        order = np.argsort(K_all)
        return {"K": K_all[order], "iv": np.concatenate(ivs)[order],
                "spread": np.concatenate(spreads)[order], "rejected": rejected, "candidates": candidates}
    return {"K": np.zeros(0), "iv": np.zeros(0), "spread": np.zeros(0), "rejected": rejected,
            "candidates": candidates}


def _parity_forward(view: ChainView, T: float, r: float, forward: float) -> float | None:
    calls, puts = view.calls, view.puts
    if not len(calls) or not len(puts):
        return None
    common = np.intersect1d(calls.strike, puts.strike)
    if common.size == 0:
        return None
    nearest = common[np.argsort(np.abs(common - forward))[:5]]
    values = []
    for K in nearest:
        ci, pi = calls.index_of(float(K)), puts.index_of(float(K))
        if ci is None or pi is None:
            continue
        c_mid, p_mid = calls.mid[ci], puts.mid[pi]
        if np.isfinite(c_mid) and np.isfinite(p_mid):
            values.append(float(K) + math.exp(r * T) * (c_mid - p_mid))
    return float(np.median(values)) if values else None


def _delta_strike(smile: SmileFit, target: float, is_call: bool) -> float | None:
    """Log-moneyness where the smile spot delta equals ``target`` (bisection)."""
    if not smile.fitted or smile.atm_iv is None:
        return None
    sqrt_t = math.sqrt(smile.T)
    span = 8.0 * smile.atm_iv * sqrt_t
    lo, hi = (0.0, span) if is_call else (-span, 0.0)

    def delta(k: float) -> float:
        sig = float(smile.iv_k(np.array([k]))[0])
        d1 = (-k + 0.5 * sig * sig * smile.T) / (sig * sqrt_t)
        disc = math.exp(-smile.q * smile.T)
        return disc * float(ndtr(d1)) if is_call else -disc * float(ndtr(-d1))

    f_lo, f_hi = delta(lo) - target, delta(hi) - target
    if f_lo * f_hi > 0:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = delta(mid) - target
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def build_smile(view: ChainView, ctx: MarketContext, *, iv_model: str = "contract",
                steps: int = pricing.IV_TREE_STEPS) -> SmileFit:
    """Fit the smile of one expiry (see the module docstring).

    Args:
        view: Normalised chain of the expiry.
        ctx: Market inputs (spot must be usable).
        iv_model: ``contract`` (the exercise style of the contract) or
            ``european`` (European-equivalent IV; faster, used by GEX).
        steps: Tree steps for American IV.
    """
    T = ctx.tte(view.expiry)
    rate = ctx.rate(T).value if T > 0 else ctx.rate(1e-6).value
    q = ctx.dividends.q
    times, amounts = ctx.schedule()
    star = float(pricing.escrowed_spot(ctx.price, max(T, 1e-9), rate, times, amounts)[0])
    forward = star * math.exp((rate - q) * max(T, 0.0))
    model_name = pricing.STYLE_EUROPEAN if iv_model == pricing.STYLE_EUROPEAN else ctx.style
    smile = SmileFit(expiry=view.expiry, T=T, spot=ctx.price, forward=forward, rate=rate, q=q,
                     style=ctx.style, iv_model=f"{model_name}_from_mid")
    if T <= 0.0:
        smile.warnings.append("expired: no smile")
        return smile
    points = _solve_points(view, ctx, T, rate, q, forward, iv_model, steps)
    smile.rejected = {key: value for key, value in points["rejected"].items() if value}
    smile.n_candidates = int(points["candidates"])
    K, iv, spread = points["K"], points["iv"], points["spread"]
    smile.n_points = int(K.shape[0])
    smile.forward_parity = _parity_forward(view, T, rate, forward)
    for is_call in (True, False):
        side = view.side(is_call)
        mono, convex = _quote_checks(side.strike, side.bid, side.ask, is_call)
        smile.monotonicity_violations += mono
        smile.convexity_violations += convex
    if smile.n_points == 0:
        smile.warnings.append("no out-of-the-money quote passed the filters")
        return smile
    k = np.log(K / forward)
    smile.point_k, smile.point_iv = k.tolist(), iv.tolist()
    smile.k_min, smile.k_max = float(k.min()), float(k.max())
    weights = 1.0 / np.maximum(spread, 0.02)
    if smile.n_points >= SVI_MIN_POINTS:
        fit = _fit_svi(k, iv * iv * T, weights)
        if fit is not None:
            params, _ = fit
            model_iv = np.sqrt(np.maximum(_svi_w(params, k), 1e-12) / T)
            rmse = float(np.sqrt(np.average((model_iv - iv) ** 2, weights=weights)))
            grid = np.linspace(smile.k_min - 0.5, smile.k_max + 0.5, 201)
            g_min = float(np.nanmin(durrleman_g(params, grid)))
            if rmse <= _MAX_RMSE_VOL and g_min >= -1e-6:
                smile.method, smile.params, smile.rmse_vol = METHOD_SVI, params, rmse
                smile.butterfly_arbitrage, smile.min_durrleman_g = False, g_min
            else:
                smile.warnings.append(
                    f"SVI rejected (rmse {rmse:.4f}, min g {g_min:.2e}); quadratic smile used"
                )
                smile.butterfly_arbitrage = g_min < -1e-6
                smile.min_durrleman_g = g_min
    if smile.method == METHOD_NONE and smile.n_points >= POLY_MIN_POINTS:
        coeffs = _fit_poly(k, iv, weights)
        smile.method = METHOD_POLY
        smile.params = {f"c{i}": float(c) for i, c in enumerate(coeffs)}
        model_iv = smile.iv_k(k)
        smile.rmse_vol = float(np.sqrt(np.average((model_iv - iv) ** 2, weights=weights)))
        grid = np.linspace(smile.k_min, smile.k_max, 201)
        w = smile.iv_k(grid) ** 2 * T
        smile.butterfly_arbitrage = bool(_numeric_g(grid, w).min() < -1e-6)
    if smile.fitted:
        smile.atm_iv = float(smile.iv_k(np.array([0.0]))[0])
        smile.atm_iv_source = f"smile_{smile.method}"
    else:
        nearest = int(np.argmin(np.abs(k)))
        if abs(k[nearest]) <= 0.05:
            smile.atm_iv, smile.atm_iv_source = float(iv[nearest]), "nearest_otm_quote"
        smile.warnings.append(f"only {smile.n_points} usable quotes: no smile fitted")
    if smile.atm_iv is not None:
        smile.expected_move = ctx.price * smile.atm_iv * math.sqrt(T)
    if smile.fitted:
        call_k = _delta_strike(smile, 0.25, True)
        put_k = _delta_strike(smile, -0.25, False)
        if call_k is not None and put_k is not None and smile.atm_iv is not None:
            c_iv = float(smile.iv_k(np.array([call_k]))[0])
            p_iv = float(smile.iv_k(np.array([put_k]))[0])
            smile.rr25 = c_iv - p_iv
            smile.bf25 = 0.5 * (c_iv + p_iv) - smile.atm_iv
    smile.straddle_move = _straddle(view, forward)
    if smile.forward_parity is not None and ctx.style == pricing.STYLE_EUROPEAN:
        gap = smile.forward_parity / forward - 1.0
        if abs(gap) > 0.005:
            smile.warnings.append(
                f"put-call parity forward differs from the model forward by {gap * 100:.2f}%: "
                "check the dividend or borrow inputs"
            )
    return smile


def _numeric_g(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    w1 = np.gradient(w, k)
    w2 = np.gradient(w1, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (1.0 - k * w1 / (2.0 * w)) ** 2 - 0.25 * w1 * w1 * (1.0 / w + 0.25) + 0.5 * w2


def _straddle(view: ChainView, forward: float) -> float | None:
    calls, puts = view.calls, view.puts
    common = np.intersect1d(calls.strike, puts.strike) if len(calls) and len(puts) else np.zeros(0)
    if common.size == 0:
        return None
    K = float(common[np.argmin(np.abs(common - forward))])
    ci, pi = calls.index_of(K), puts.index_of(K)
    if ci is None or pi is None:
        return None
    total = calls.mid[ci] + puts.mid[pi]
    return float(total) if np.isfinite(total) else None


def term_structure(smiles: list[SmileFit]) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-expiry summary rows and calendar-arbitrage warnings (ATM total variance)."""
    rows = [smile.summary() for smile in sorted(smiles, key=lambda s: s.T)]
    warnings: list[str] = []
    prev: SmileFit | None = None
    for smile in sorted(smiles, key=lambda s: s.T):
        if smile.atm_iv is None:
            continue
        if prev is not None and prev.atm_iv is not None:
            if smile.atm_iv ** 2 * smile.T < prev.atm_iv ** 2 * prev.T - 1e-6:
                warnings.append(
                    f"calendar arbitrage: ATM total variance falls from {prev.expiry} to {smile.expiry}"
                )
        prev = smile
    return rows, warnings


def constant_maturity_iv(smiles: list[SmileFit], days: float = 30.0) -> tuple[float | None, str, list[str]]:
    """ATM IV at a fixed maturity by linear interpolation of total variance."""
    target = days / 365.0
    usable = sorted((s for s in smiles if s.atm_iv is not None and s.T > 0), key=lambda s: s.T)
    if not usable:
        return None, "no ATM IV", []
    below = [s for s in usable if s.T <= target]
    above = [s for s in usable if s.T >= target]
    if below and above:
        left, right = below[-1], above[0]
        if right.T == left.T:
            return left.atm_iv, "exact", [left.expiry]
        w_left, w_right = left.atm_iv ** 2 * left.T, right.atm_iv ** 2 * right.T
        weight = (target - left.T) / (right.T - left.T)
        w = w_left + weight * (w_right - w_left)
        if w <= 0:
            return None, "negative interpolated variance", [left.expiry, right.expiry]
        return math.sqrt(w / target), "variance_interpolation", [left.expiry, right.expiry]
    nearest = min(usable, key=lambda s: abs(s.T - target))
    if abs(nearest.T - target) * 365.0 <= 7.0:
        return nearest.atm_iv, "nearest_expiry_within_7_days", [nearest.expiry]
    return None, "no expiry within 7 days of the target", []


@dataclass
class TerminalDistribution:
    """Discrete risk-neutral law of ``S_T`` (probabilities sum to 1)."""

    prices: np.ndarray
    probs: np.ndarray
    method: str
    negative_mass: float = 0.0


def terminal_distribution(smile: SmileFit | None, *, spot: float, T: float, forward: float,
                          atm_iv: float | None, n: int = 801) -> TerminalDistribution | None:
    """Risk-neutral distribution of ``S_T`` from the smile (or lognormal at the ATM IV)."""
    use_smile = smile is not None and smile.fitted
    sigma_atm = (smile.atm_iv if use_smile and smile.atm_iv else atm_iv)
    if sigma_atm is None or not math.isfinite(sigma_atm) or T <= 0 or forward <= 0:
        return None
    width = 7.0 * sigma_atm * math.sqrt(T)
    x = np.linspace(-width, width, n)
    K = forward * np.exp(x)
    if use_smile:
        sig = smile.iv(K)
        method = f"smile_{smile.method}"
    else:
        sig = np.full_like(K, sigma_atm)
        method = "lognormal_atm_iv"
    vol = sig * math.sqrt(T)
    d1 = (np.log(forward / K) + 0.5 * vol * vol) / vol
    call = forward * ndtr(d1) - K * ndtr(d1 - vol)
    cdf = 1.0 + np.gradient(call, K)
    raw = np.diff(cdf)
    negative = float(-raw[raw < 0].sum())
    cdf = np.clip(np.maximum.accumulate(np.clip(cdf, 0.0, 1.0)), 0.0, 1.0)
    cells = np.diff(cdf)
    prices = np.concatenate([[K[0]], np.sqrt(K[:-1] * K[1:]), [K[-1]]])
    probs = np.concatenate([[cdf[0]], cells, [1.0 - cdf[-1]]])
    total = probs.sum()
    if total <= 0:
        return None
    del spot
    return TerminalDistribution(prices=prices, probs=probs / total, method=method, negative_mass=negative)
