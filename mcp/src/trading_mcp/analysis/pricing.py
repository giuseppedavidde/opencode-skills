"""Option pricing core shared by every options tool (one engine).

Conventions
-----------
- ``T`` is in years, ACT/365 with fractional days
  (:func:`trading_mcp.data.market_calendar.time_to_expiry`). ``T <= 0`` is an
  expired option: its value is the intrinsic value.
- ``r`` and ``q`` are continuously compounded decimals; ``sigma`` is a decimal.
- Discrete cash dividends use the escrowed-dividend model: the formula and the
  tree run on ``S* = S - PV(dividends with ex-time in (0, T))``. ``div_times``
  are years from the valuation time, ``div_amounts`` are cash per share.
  ``sigma`` is the volatility of ``S*``. Do not combine a discrete schedule
  with a continuous ``q`` for the same dividends.
- Greeks are per share (multiply by the contract multiplier and the signed
  quantity): delta per $1, gamma per $1 per $1, theta per calendar day (value
  change when one day passes, spot fixed), vega per 1 vol point (0.01), rho per
  1 rate point (0.01), vanna = delta change per 1 vol point, charm = delta
  change per calendar day, vomma = vega change per 1 vol point.
- American prices use a Cox-Ross-Rubinstein tree with the Black-Scholes value
  one step before expiry and Richardson extrapolation (BBSR, Broadie and
  Detemple 1996). American Greeks use central finite differences on the same
  pricer. European prices and Greeks are closed form (Merton 1973).
- Every function is vectorised: scalar or array inputs broadcast together.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.special import ndtr

IV_MIN = 0.01
IV_MAX = 5.0
STYLE_AMERICAN = "american"
STYLE_EUROPEAN = "european"
DEFAULT_STEPS = 200
IV_TREE_STEPS = 100
_SOLVE_LO = 0.005
_SOLVE_HI = 5.0
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)
_DAY = 1.0 / 365.0

GREEK_UNITS: dict[str, str] = {
    "delta": "per share, $ per $1 of the underlying",
    "gamma": "per share, delta per $1 of the underlying",
    "theta": "per share, $ per calendar day (spot fixed)",
    "vega": "per share, $ per 1 vol point (0.01)",
    "rho": "per share, $ per 1 rate point (0.01)",
    "vanna": "per share, delta per 1 vol point",
    "charm": "per share, delta per calendar day",
    "vomma": "per share, vega per 1 vol point",
}


def _pdf(x: np.ndarray) -> np.ndarray:
    return _INV_SQRT_2PI * np.exp(-0.5 * x * x)


def _call_flags(is_call: Any) -> np.ndarray:
    flags = np.asarray(is_call)
    if flags.dtype.kind in ("U", "S", "O"):
        flags = np.vectorize(lambda v: str(v).lower().startswith("c"), otypes=[bool])(flags)
    return flags.astype(bool)


def _flat(*values: Any) -> list[np.ndarray]:
    """Broadcast numeric inputs to one 1-D float shape."""
    arrays = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in values])
    return [np.array(a, dtype=float).reshape(-1) for a in arrays]


def _prep(*values: Any) -> list[np.ndarray]:
    """Broadcast numeric inputs plus a trailing call flag to one 1-D shape."""
    *numbers, is_call = values
    arrays = np.broadcast_arrays(*[np.asarray(v, dtype=float) for v in numbers], _call_flags(is_call))
    out = [np.array(a, dtype=float).reshape(-1) for a in arrays[:-1]]
    out.append(np.array(arrays[-1], dtype=bool).reshape(-1))
    return out


def _div_matrix(div_times: Any, div_amounts: Any, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Dividend times and amounts as ``(n, m)`` arrays (``m = 0`` without dividends)."""
    if div_times is None or div_amounts is None:
        return np.zeros((n, 0)), np.zeros((n, 0))
    times = np.asarray(div_times, dtype=float)
    amounts = np.asarray(div_amounts, dtype=float)
    if times.size == 0:
        return np.zeros((n, 0)), np.zeros((n, 0))
    if times.ndim == 1:
        times = np.broadcast_to(times, (n, times.shape[0]))
    if amounts.ndim == 1:
        amounts = np.broadcast_to(amounts, times.shape)
    return np.array(times, dtype=float), np.array(amounts, dtype=float)


def pv_dividends(T: Any, r: Any, div_times: Any = None, div_amounts: Any = None) -> np.ndarray:
    """Present value of the dividends with ex-time strictly inside ``(0, T)``."""
    T_arr, r_arr = _flat(T, r)
    times, amounts = _div_matrix(div_times, div_amounts, T_arr.shape[0])
    if times.shape[1] == 0:
        return np.zeros_like(T_arr)
    live = np.isfinite(times) & np.isfinite(amounts) & (times > 0.0) & (times < T_arr[:, None])
    disc = np.exp(-r_arr[:, None] * np.where(live, times, 0.0))
    return np.sum(np.where(live, amounts * disc, 0.0), axis=1)


def _black_parts(F: np.ndarray, K: np.ndarray, T: np.ndarray, sigma: np.ndarray):
    vol = sigma * np.sqrt(np.maximum(T, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(F / K) + 0.5 * vol * vol) / vol
    d2 = d1 - vol
    return d1, d2, vol


def bs_price(S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any) -> np.ndarray:
    """Merton (continuous yield) Black-Scholes price; intrinsic value when ``T <= 0``."""
    S_, K_, T_, r_, q_, s_, calls = _prep(S, K, T, r, q, sigma, is_call)
    phi = np.where(calls, 1.0, -1.0)
    out = np.maximum(phi * (S_ - K_), 0.0)
    live = T_ > 0.0
    if not np.any(live):
        return out
    Tl, rl, ql = T_[live], r_[live], q_[live]
    F = S_[live] * np.exp((rl - ql) * Tl)
    df = np.exp(-rl * Tl)
    sig = np.maximum(s_[live], 0.0)
    ph = phi[live]
    Kl = K_[live]
    tiny = sig * np.sqrt(Tl) < 1e-10
    d1, d2, _ = _black_parts(F, Kl, Tl, np.where(tiny, 1.0, sig))
    value = df * ph * (F * ndtr(ph * d1) - Kl * ndtr(ph * d2))
    value = np.where(tiny, df * np.maximum(ph * (F - Kl), 0.0), value)
    out[live] = np.maximum(value, 0.0)
    return out


def bs_greeks(S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any) -> dict[str, np.ndarray]:
    """Closed-form Merton Greeks per share (units in :data:`GREEK_UNITS`).

    An expired option (``T <= 0``) has delta 1/-1 when in the money and every
    other Greek 0.
    """
    S_, K_, T_, r_, q_, s_, calls = _prep(S, K, T, r, q, sigma, is_call)
    n = S_.shape[0]
    phi = np.where(calls, 1.0, -1.0)
    keys = ("delta", "gamma", "theta", "vega", "rho", "vanna", "charm", "vomma", "prob_itm")
    out = {key: np.zeros(n) for key in keys}
    itm = phi * (S_ - K_) > 0.0
    out["delta"] = np.where(itm, phi, 0.0)
    out["prob_itm"] = np.where(itm, 1.0, 0.0)
    live = (T_ > 0.0) & (s_ > 0.0)
    if not np.any(live):
        return out
    S, K, T, r, q, sig, ph = S_[live], K_[live], T_[live], r_[live], q_[live], s_[live], phi[live]
    sqrt_t = np.sqrt(T)
    vol = sig * sqrt_t
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(S / K) + (r - q + 0.5 * sig * sig) * T) / vol
    d2 = d1 - vol
    dq = np.exp(-q * T)
    dr = np.exp(-r * T)
    nd1 = _pdf(d1)
    delta = ph * dq * ndtr(ph * d1)
    gamma = dq * nd1 / (S * vol)
    vega = S * dq * nd1 * sqrt_t
    theta_year = (
        -S * dq * nd1 * sig / (2.0 * sqrt_t)
        - ph * r * K * dr * ndtr(ph * d2)
        + ph * q * S * dq * ndtr(ph * d1)
    )
    rho = ph * K * T * dr * ndtr(ph * d2)
    vanna = -dq * nd1 * d2 / sig
    # dDelta/dT (time to expiry); time passing is the negative of it.
    ddelta_dT = -ph * q * dq * ndtr(ph * d1) + dq * nd1 * (
        (r - q) / vol - d2 / (2.0 * T)
    )
    vomma = vega * d1 * d2 / sig
    out["delta"][live] = delta
    out["gamma"][live] = gamma
    out["theta"][live] = theta_year * _DAY
    out["vega"][live] = vega * 0.01
    out["rho"][live] = rho * 0.01
    out["vanna"][live] = vanna * 0.01
    out["charm"][live] = -ddelta_dT * _DAY
    out["vomma"][live] = vomma * 1e-4
    out["prob_itm"][live] = ndtr(ph * d2)
    return out


def escrowed_spot(S: Any, T: Any, r: Any, div_times: Any = None, div_amounts: Any = None) -> np.ndarray:
    """Spot minus the present value of the dividends before expiry."""
    S_, T_, r_ = _flat(S, T, r)
    return S_ - pv_dividends(T_, r_, div_times, div_amounts)


def european_price(
    S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any,
    div_times: Any = None, div_amounts: Any = None,
) -> np.ndarray:
    """European price with continuous ``q`` and escrowed discrete dividends."""
    S_, K_, T_, r_, q_, s_, calls = _prep(S, K, T, r, q, sigma, is_call)
    star = S_ - pv_dividends(T_, r_, *_div_matrix(div_times, div_amounts, S_.shape[0]))
    out = bs_price(np.maximum(star, 1e-12), K_, T_, r_, q_, s_, calls)
    return np.where(star > 0.0, out, np.nan)


def _remaining_pv(times: np.ndarray, amounts: np.ndarray, t_now: np.ndarray, T: np.ndarray,
                  r: np.ndarray) -> np.ndarray:
    if times.shape[1] == 0:
        return np.zeros_like(t_now)
    live = np.isfinite(times) & (times > t_now[:, None]) & (times < T[:, None])
    gap = np.where(live, times - t_now[:, None], 0.0)
    return np.sum(np.where(live, amounts * np.exp(-r[:, None] * gap), 0.0), axis=1)


def _tree(S_star: np.ndarray, K: np.ndarray, T: np.ndarray, r: np.ndarray, q: np.ndarray,
          sigma: np.ndarray, calls: np.ndarray, times: np.ndarray, amounts: np.ndarray,
          steps: int) -> np.ndarray:
    """CRR tree on the escrowed spot, BBS last step, early exercise at every node."""
    N = max(int(steps), 2)
    dt = T / N
    sq = sigma * np.sqrt(dt)
    up = np.exp(sq)
    down = 1.0 / up
    growth = np.exp((r - q) * dt)
    prob = np.clip((growth - down) / (up - down), 0.0, 1.0)
    disc = np.exp(-r * dt)
    phi = np.where(calls, 1.0, -1.0)[:, None]
    strike = K[:, None]
    j = N - 1
    nodes = S_star[:, None] * np.exp((2.0 * np.arange(j + 1) - j)[None, :] * sq[:, None])
    shape = nodes.shape
    cont = bs_price(
        nodes, np.broadcast_to(strike, shape), np.broadcast_to(dt[:, None], shape),
        np.broadcast_to(r[:, None], shape), np.broadcast_to(q[:, None], shape),
        np.broadcast_to(sigma[:, None], shape), np.broadcast_to(calls[:, None], shape),
    ).reshape(shape)
    actual = nodes + _remaining_pv(times, amounts, j * dt, T, r)[:, None]
    values = np.maximum(cont, np.maximum(phi * (actual - strike), 0.0))
    p_up = prob[:, None]
    p_dn = 1.0 - p_up
    dsc = disc[:, None]
    dn = down[:, None]
    for j in range(N - 2, -1, -1):
        values = dsc * (p_up * values[:, 1:] + p_dn * values[:, :-1])
        nodes = nodes[:, 1:] * dn
        actual = nodes + _remaining_pv(times, amounts, j * dt, T, r)[:, None]
        values = np.maximum(values, phi * (actual - strike))
    return values[:, 0]


def american_price(
    S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any,
    div_times: Any = None, div_amounts: Any = None, steps: int = DEFAULT_STEPS,
) -> np.ndarray:
    """American price (BBSR tree) with continuous ``q`` and escrowed discrete dividends.

    Returns NaN when the dividends before expiry exceed the spot.
    """
    S_, K_, T_, r_, q_, s_, calls = _prep(S, K, T, r, q, sigma, is_call)
    n = S_.shape[0]
    times, amounts = _div_matrix(div_times, div_amounts, n)
    out = np.maximum(np.where(calls, 1.0, -1.0) * (S_ - K_), 0.0)
    pv = pv_dividends(T_, r_, times, amounts)
    star = S_ - pv
    live = (T_ > 0.0) & (s_ > 0.0) & (star > 0.0)
    out = np.where((T_ > 0.0) & (star <= 0.0), np.nan, out)
    if not np.any(live):
        return out
    # Calls without any carry cost from dividends are never exercised early.
    euro_call = live & calls & (q_ <= 0.0) & (pv <= 0.0)
    if np.any(euro_call):
        out[euro_call] = bs_price(S_[euro_call], K_[euro_call], T_[euro_call], r_[euro_call],
                                  q_[euro_call], s_[euro_call], True)
    tree = live & ~euro_call
    if np.any(tree):
        args = (star[tree], K_[tree], T_[tree], r_[tree], q_[tree], s_[tree], calls[tree],
                times[tree], amounts[tree])
        steps = max(int(steps) // 2 * 2, 4)
        fine = _tree(*args, steps)
        coarse = _tree(*args, steps // 2)
        intrinsic = np.maximum(np.where(calls[tree], 1.0, -1.0) * (S_[tree] - K_[tree]), 0.0)
        out[tree] = np.maximum(2.0 * fine - coarse, intrinsic)
    return out


def option_price(
    S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any, style: str = STYLE_AMERICAN,
    div_times: Any = None, div_amounts: Any = None, steps: int = DEFAULT_STEPS,
) -> np.ndarray:
    """Price with the exercise style of the contract (``american`` or ``european``)."""
    if style == STYLE_EUROPEAN:
        return european_price(S, K, T, r, q, sigma, is_call, div_times, div_amounts)
    return american_price(S, K, T, r, q, sigma, is_call, div_times, div_amounts, steps)


def no_arbitrage_bounds(
    S: Any, K: Any, T: Any, r: Any, q: Any, is_call: Any, style: str = STYLE_AMERICAN,
    div_times: Any = None, div_amounts: Any = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Model-free ``(lower, upper)`` price bounds used to reject bad quotes."""
    S_, K_, T_, r_, q_, calls = _prep(S, K, T, r, q, is_call)
    n = S_.shape[0]
    star = S_ - pv_dividends(T_, r_, *_div_matrix(div_times, div_amounts, n))
    tpos = np.maximum(T_, 0.0)
    fwd_lower = np.where(
        calls,
        np.maximum(star * np.exp(-q_ * tpos) - K_ * np.exp(-r_ * tpos), 0.0),
        np.maximum(K_ * np.exp(-r_ * tpos) - star * np.exp(-q_ * tpos), 0.0),
    )
    intrinsic = np.maximum(np.where(calls, 1.0, -1.0) * (S_ - K_), 0.0)
    lower = np.maximum(fwd_lower, intrinsic) if style == STYLE_AMERICAN else fwd_lower
    upper = np.where(calls, S_, K_ if style == STYLE_AMERICAN else K_ * np.exp(-r_ * tpos))
    return lower, upper


def implied_vol(
    price: Any, S: Any, K: Any, T: Any, r: Any, q: Any, is_call: Any, style: str = STYLE_AMERICAN,
    div_times: Any = None, div_amounts: Any = None, steps: int = IV_TREE_STEPS,
) -> tuple[np.ndarray, np.ndarray]:
    """Implied volatility by bisection on the model price.

    Returns ``(iv, status)``. ``status`` is ``ok``, ``no_price``, ``expired``,
    ``below_bound`` (the price is under the model value at the lowest
    volatility, for example a mid under the intrinsic value) or ``above_bound``.
    ``iv`` is NaN unless ``status`` is ``ok``.
    """
    P_, S_, K_, T_, r_, q_, calls = _prep(price, S, K, T, r, q, is_call)
    n = P_.shape[0]
    times, amounts = _div_matrix(div_times, div_amounts, n)
    status = np.full(n, "ok", dtype=object)
    status[~np.isfinite(P_) | (P_ <= 0.0)] = "no_price"
    status[(status == "ok") & ~(T_ > 0.0)] = "expired"

    def model(sig: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return option_price(S_[mask], K_[mask], T_[mask], r_[mask], q_[mask], sig, calls[mask],
                            style, times[mask], amounts[mask], steps)

    work = status == "ok"
    iv = np.full(n, np.nan)
    if not np.any(work):
        return iv, status
    lo = np.full(int(work.sum()), _SOLVE_LO)
    hi = np.full(int(work.sum()), _SOLVE_HI)
    target = P_[work]
    p_lo = model(lo, work)
    p_hi = model(hi, work)
    sub_status = np.full(lo.shape[0], "ok", dtype=object)
    sub_status[~(target > p_lo)] = "below_bound"
    sub_status[~(target < p_hi)] = "above_bound"
    sub_status[~np.isfinite(p_lo) | ~np.isfinite(p_hi)] = "no_price"
    inside = sub_status == "ok"
    iterations = 50 if style == STYLE_EUROPEAN else 28
    if np.any(inside):
        a, b, tgt = np.log(lo[inside]), np.log(hi[inside]), target[inside]
        mask = np.zeros(n, dtype=bool)
        mask[np.flatnonzero(work)[inside]] = True
        for _ in range(iterations):
            mid = 0.5 * (a + b)
            pm = model(np.exp(mid), mask)
            below = pm < tgt
            a = np.where(below, mid, a)
            b = np.where(below, b, mid)
        solved = np.full(lo.shape[0], np.nan)
        solved[inside] = np.exp(0.5 * (a + b))
        iv[work] = solved
    status[work] = sub_status
    iv[status != "ok"] = np.nan
    return iv, status


def _fd_greeks(S: np.ndarray, K: np.ndarray, T: np.ndarray, r: np.ndarray, q: np.ndarray,
               sig: np.ndarray, calls: np.ndarray, times: np.ndarray, amounts: np.ndarray,
               steps: int) -> dict[str, np.ndarray]:
    """American Greeks by central finite differences on the tree (one batched call)."""
    n = S.shape[0]
    h = np.clip(0.1 * sig * np.sqrt(np.maximum(T, 1e-8)), 1e-4, 0.01)
    dv = np.minimum(0.01, 0.5 * sig)
    first_div = np.where(
        (times > 0) & (times < T[:, None]) & np.isfinite(times), times, np.inf
    ).min(axis=1) if times.shape[1] else np.full(n, np.inf)
    dt = np.minimum(np.minimum(_DAY, 0.5 * T), np.where(np.isfinite(first_div), 0.5 * first_div, _DAY))
    dt = np.maximum(dt, 1e-9)
    dr = 1e-4
    up, dn = S * (1 + h), S * (1 - h)
    rows = [
        (S, sig, T, r, 0.0), (up, sig, T, r, 0.0), (dn, sig, T, r, 0.0),
        (S, sig + dv, T, r, 0.0), (S, sig - dv, T, r, 0.0),
        (up, sig + dv, T, r, 0.0), (dn, sig + dv, T, r, 0.0),
        (up, sig - dv, T, r, 0.0), (dn, sig - dv, T, r, 0.0),
        (S, sig, T - dt, r, 1.0), (up, sig, T - dt, r, 1.0), (dn, sig, T - dt, r, 1.0),
        (S, sig, T, r + dr, 0.0),
    ]
    count = len(rows)
    S_b = np.concatenate([row[0] * np.ones(n) for row in rows])
    s_b = np.concatenate([row[1] * np.ones(n) for row in rows])
    T_b = np.concatenate([row[2] * np.ones(n) for row in rows])
    r_b = np.concatenate([row[3] * np.ones(n) for row in rows])
    shift = np.concatenate([row[4] * dt for row in rows])
    times_b = np.tile(times, (count, 1)) - shift[:, None] if times.shape[1] else np.zeros((n * count, 0))
    amounts_b = np.tile(amounts, (count, 1)) if amounts.shape[1] else np.zeros((n * count, 0))
    values = american_price(
        S_b, np.tile(K, count), T_b, r_b, np.tile(q, count), s_b, np.tile(calls, count),
        times_b, amounts_b, steps,
    ).reshape(count, n)
    v0, vu, vd, vsu, vsd, vuu, vdu, vud, vdd, vt, vtu, vtd, vr = values
    hs = h * S
    delta = (vu - vd) / (2 * hs)
    delta_t = (vtu - vtd) / (2 * hs)
    days = dt / _DAY
    return {
        "delta": delta,
        "gamma": (vu - 2 * v0 + vd) / (hs * hs),
        "theta": (vt - v0) / days,
        "vega": (vsu - vsd) / (2 * dv) * 0.01,
        "rho": (vr - v0) / dr * 0.01,
        "vanna": ((vuu - vdu) - (vud - vdd)) / (2 * hs * 2 * dv) * 0.01,
        "charm": (delta_t - delta) / days,
        "vomma": (vsu - 2 * v0 + vsd) / (dv * dv) * 1e-4,
        "price": v0,
    }


def greeks(
    S: Any, K: Any, T: Any, r: Any, q: Any, sigma: Any, is_call: Any, style: str = STYLE_AMERICAN,
    div_times: Any = None, div_amounts: Any = None, steps: int = DEFAULT_STEPS,
) -> dict[str, np.ndarray]:
    """Model price and Greeks per share for the contract style.

    European: closed form on the escrowed spot (theta, charm and rho include the
    dividend carry). American: finite differences on the BBSR tree. The result
    has ``price`` plus the keys of :data:`GREEK_UNITS`.
    """
    S_, K_, T_, r_, q_, s_, calls = _prep(S, K, T, r, q, sigma, is_call)
    n = S_.shape[0]
    times, amounts = _div_matrix(div_times, div_amounts, n)
    pv = pv_dividends(T_, r_, times, amounts)
    star = S_ - pv
    result = {key: np.full(n, np.nan) for key in (*GREEK_UNITS, "price")}
    live = (T_ > 0.0) & (s_ > 0.0) & (star > 0.0)
    expired = ~(T_ > 0.0)
    if np.any(expired):
        closed = bs_greeks(S_[expired], K_[expired], 0.0, r_[expired], q_[expired], 0.2, calls[expired])
        for key in GREEK_UNITS:
            result[key][expired] = closed[key]
        result["price"][expired] = np.maximum(np.where(calls[expired], 1.0, -1.0) * (S_[expired] - K_[expired]), 0.0)
    if not np.any(live):
        return result
    euro = live & ((style == STYLE_EUROPEAN) | (calls & (q_ <= 0.0) & (pv <= 0.0)))
    if np.any(euro):
        closed = bs_greeks(star[euro], K_[euro], T_[euro], r_[euro], q_[euro], s_[euro], calls[euro])
        carry = r_[euro] * pv[euro]
        dpv_dr = np.sum(np.where(
            (times[euro] > 0) & (times[euro] < T_[euro][:, None]) & np.isfinite(times[euro]),
            times[euro] * amounts[euro] * np.exp(-r_[euro][:, None] * np.nan_to_num(times[euro])), 0.0,
        ), axis=1) if times.shape[1] else np.zeros(int(euro.sum()))
        result["price"][euro] = bs_price(star[euro], K_[euro], T_[euro], r_[euro], q_[euro], s_[euro], calls[euro])
        result["delta"][euro] = closed["delta"]
        result["gamma"][euro] = closed["gamma"]
        result["vega"][euro] = closed["vega"]
        result["vanna"][euro] = closed["vanna"]
        result["vomma"][euro] = closed["vomma"]
        # Time passing raises the PV of the remaining dividends, so S* falls by r*PV per year.
        result["theta"][euro] = closed["theta"] - closed["delta"] * carry * _DAY
        result["charm"][euro] = closed["charm"] - closed["gamma"] * carry * _DAY
        result["rho"][euro] = closed["rho"] + closed["delta"] * dpv_dr * 0.01
    tree = live & ~euro
    if np.any(tree):
        fd = _fd_greeks(S_[tree], K_[tree], T_[tree], r_[tree], q_[tree], s_[tree], calls[tree],
                        times[tree], amounts[tree], steps)
        for key, value in fd.items():
            result[key][tree] = value
    return result


def touch_probability(S: Any, H: Any, T: Any, r: Any, q: Any, sigma: Any) -> np.ndarray:
    """Risk-neutral probability that GBM touches level ``H`` before ``T`` (closed form).

    Uses the first-passage law of ``ln S`` with drift ``r - q - sigma^2/2``.
    """
    S_, H_, T_, r_, q_, s_ = _flat(S, H, T, r, q, sigma)
    out = np.where(np.isclose(S_, H_), 1.0, 0.0)
    live = (T_ > 0.0) & (s_ > 0.0) & (H_ > 0.0) & (S_ > 0.0) & ~np.isclose(S_, H_)
    if not np.any(live):
        return out
    s, T, nu = s_[live], T_[live], r_[live] - q_[live] - 0.5 * s_[live] ** 2
    a = np.log(H_[live] / S_[live])
    vol = s * np.sqrt(T)
    with np.errstate(over="ignore"):
        reflect = np.exp(np.clip(2.0 * nu * a / (s * s), -700, 700))
    upper = ndtr((nu * T - a) / vol) + reflect * ndtr((-nu * T - a) / vol)
    lower = ndtr((a - nu * T) / vol) + reflect * ndtr((a + nu * T) / vol)
    out[live] = np.clip(np.where(a > 0, upper, lower), 0.0, 1.0)
    return out
