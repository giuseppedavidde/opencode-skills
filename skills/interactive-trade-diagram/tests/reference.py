"""Independent Python reference for the trade-diagram engine (golden values).

The script reads tests/fixtures/golden_cases.json, values every case with
Black-Scholes-Merton per leg (scipy), solves the break-evens with brentq on a
dense grid over [0, inf), and finds the extremes with a bounded search.

Run (check mode, compares with the stored values):
    uv run --no-project --with numpy --with scipy python skills/interactive-trade-diagram/tests/reference.py
Write new expected values:
    uv run --no-project --with numpy --with scipy python skills/interactive-trade-diagram/tests/reference.py --write
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import ndtr

FIXTURE = Path(__file__).parent / "fixtures" / "golden_cases.json"
NY = ZoneInfo("America/New_York")
YEAR_S = 365 * 86400.0


def parse_day(text: str) -> date:
    """Parse gg.mm.aaaa or aaaa-mm-gg."""
    if "." in text:
        d, m, y = text.split(".")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(text)


def ny_ts(day: date, hhmm: str = "16:00") -> float:
    """POSIX time of a New York wall-clock time (zoneinfo handles DST)."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=NY).timestamp()


@dataclass
class Leg:
    """One normalized leg."""

    kind: str
    sgn: int
    qty: float
    entry: float
    mult: float
    strike: float | None
    iv: float | None
    exp_day: date | None
    exp_ts: float | None
    american: bool
    mark: float | None
    bid: float | None
    ask: float | None

    @property
    def opt(self) -> bool:
        return self.kind != "stock"


class Position:
    """Position model with the documented rules of the template."""

    def __init__(self, cfg: dict):
        self.s0 = float(cfg["spot"])
        self.r = float(cfg["r"])
        self.q = float(cfg.get("q", 0.0))
        self.carry = float(cfg.get("realized", 0.0))
        self.asof_day = parse_day(cfg["asOf"])
        self.asof = ny_ts(self.asof_day, cfg.get("asOfTime", "16:00"))
        self.front_day = date.fromisoformat(cfg["expiryISO"])
        self.front = ny_ts(self.front_day)
        vol_model = cfg.get("volModel", {})
        self.rule = vol_model.get("rule", "sticky-strike")
        self.slope = float(vol_model.get("slope", 0.0))
        self.stress = float(cfg.get("daily", {}).get("ivStress", 10))
        style = cfg.get("style", "european")
        self.legs: list[Leg] = []
        for raw in cfg["legs"]:
            opt = raw["kind"] in ("call", "put")
            exp_day = date.fromisoformat(raw.get("expiry", cfg["expiryISO"])) if opt else None
            self.legs.append(Leg(
                kind=raw["kind"], sgn=-1 if raw["side"] == "short" else 1, qty=float(raw["qty"]),
                entry=float(raw["entry"]), mult=float(raw.get("mult", 100 if opt else 1)),
                strike=float(raw["strike"]) if opt else None,
                iv=float(raw.get("iv", cfg.get("ivToday", float("nan")))) if opt else None,
                exp_day=exp_day, exp_ts=ny_ts(exp_day) if opt else None,
                american=raw.get("style", style) == "american",
                mark=raw.get("mark"), bid=raw.get("bid"), ask=raw.get("ask")))
        groups: dict[date, dict[float, list[float]]] = {}
        for leg in self.legs:
            if leg.opt:
                groups.setdefault(leg.exp_day, {}).setdefault(leg.strike, []).append(leg.iv)
        self.smile = {d: (np.array(sorted(g)), np.array([np.mean(g[k]) for k in sorted(g)])) for d, g in groups.items()}
        self.kinks = sorted({leg.strike for leg in self.legs if leg.opt})
        self.scale = sum(l.qty * l.mult * (l.strike if l.opt else self.s0) for l in self.legs) + abs(self.carry) + 1
        self.ztol = 1e-9 * self.scale
        self.slope_tol = 1e-9 * sum(l.qty * l.mult for l in self.legs)

    def years(self, leg: Leg, t: float) -> float:
        return max(0.0, (leg.exp_ts - t) / YEAR_S)

    def sigma(self, leg: Leg, s: np.ndarray, shift: float) -> np.ndarray:
        sig = np.full_like(s, leg.iv)
        pos = s > 0
        safe = np.where(pos, s, 1.0)
        ks, ivs = self.smile[leg.exp_day]
        if self.rule == "sticky-delta" and len(ks) > 1:
            moved = leg.strike * self.s0 / safe
            sig = np.where(pos, leg.iv + np.interp(moved, ks, ivs) - np.interp(leg.strike, ks, ivs), sig)
        if self.slope != 0:
            sig = np.where(pos, sig + self.slope * np.log(safe / self.s0), sig)
        return np.clip(sig + shift, 0.001, 10.0)

    def _bs(self, kind: str, s: np.ndarray, k: float, t_y: float, sig: np.ndarray) -> np.ndarray:
        zero = s <= 0
        sp = np.where(zero, 1.0, s)
        st = sig * math.sqrt(t_y)
        d1 = (np.log(sp / k) + (self.r - self.q + 0.5 * sig ** 2) * t_y) / st
        d2 = d1 - st
        dq, dr = math.exp(-self.q * t_y), math.exp(-self.r * t_y)
        if kind == "call":
            return np.where(zero, 0.0, sp * dq * ndtr(d1) - k * dr * ndtr(d2))
        return np.where(zero, k * dr, k * dr * ndtr(-d2) - sp * dq * ndtr(-d1))

    def intrinsic(self, leg: Leg, s: np.ndarray) -> np.ndarray:
        if not leg.opt:
            return s
        return np.maximum(0.0, leg.strike - s) if leg.kind == "put" else np.maximum(0.0, s - leg.strike)

    def value(self, leg: Leg, s, t: float, shift: float = 0.0) -> np.ndarray:
        s = np.asarray(s, dtype=float)
        if not leg.opt:
            return s.copy()
        t_y = self.years(leg, t)
        intr = self.intrinsic(leg, s)
        if t_y <= 0:
            return intr
        v = self._bs(leg.kind, s, leg.strike, t_y, self.sigma(leg, s, shift))
        return np.maximum(v, intr) if leg.american else v

    def pnl(self, s, t: float, shift: float = 0.0) -> np.ndarray:
        s = np.asarray(s, dtype=float)
        total = np.full_like(s, self.carry)
        for leg in self.legs:
            total = total + leg.sgn * (self.value(leg, s, t, shift) - leg.entry) * leg.qty * leg.mult
        return total

    def f(self, t: float, shift: float = 0.0):
        return lambda x: float(self.pnl(np.array([x]), t, shift)[0])

    def delta(self, s: float, t: float) -> float:
        out = 0.0
        for leg in self.legs:
            w = leg.sgn * leg.qty * leg.mult
            if not leg.opt:
                out += w
                continue
            t_y = self.years(leg, t)
            itm = (-1.0 if s < leg.strike else 0.0) if leg.kind == "put" else (1.0 if s > leg.strike else 0.0)
            if t_y <= 0:
                out += w * itm
                continue
            sig = float(self.sigma(leg, np.array([s]), 0.0)[0])
            if leg.american:
                v = float(self._bs(leg.kind, np.array([s]), leg.strike, t_y, np.array([sig]))[0])
                if v <= float(self.intrinsic(leg, np.array([s]))[0]):
                    out += w * itm
                    continue
            d1 = (math.log(s / leg.strike) + (self.r - self.q + 0.5 * sig * sig) * t_y) / (sig * math.sqrt(t_y))
            dq = math.exp(-self.q * t_y)
            out += w * (-dq * float(ndtr(-d1)) if leg.kind == "put" else dq * float(ndtr(d1)))
        return out

    def slope_inf(self, t: float) -> float:
        b = 0.0
        for leg in self.legs:
            w = leg.sgn * leg.qty * leg.mult
            if not leg.opt:
                b += w
            elif leg.kind == "call":
                t_y = self.years(leg, t)
                e = math.exp(-self.q * t_y)
                b += w if t_y <= 0 else w * (max(1.0, e) if leg.american else e)
        return b

    def analyze(self, t: float) -> dict:
        """Break-evens, sign zones and extremes of P&L(S) on [0, inf)."""
        f = self.f(t)
        lo, hi = min([self.s0, *self.kinks]), max([self.s0, *self.kinks])
        grid = np.unique(np.concatenate([[0.0, self.s0], self.kinks, np.geomspace(1e-4 * lo, 1e4 * hi, 400001)]))
        vals = self.pnl(grid, t)
        zero = np.abs(vals) <= self.ztol
        roots: list[float] = list(grid[zero])
        for i in np.nonzero((vals[:-1] * vals[1:] < 0) & ~zero[:-1] & ~zero[1:])[0]:
            roots.append(brentq(f, grid[i], grid[i + 1], xtol=1e-13, rtol=1e-15, maxiter=500))
        b_inf = self.slope_inf(t)
        up_unb, dn_unb = b_inf > self.slope_tol, b_inf < -self.slope_tol
        last_x, last_v = grid[-1], vals[-1]
        if not zero[-1] and (up_unb or dn_unb) and last_v * b_inf < 0:
            far = last_x * 2
            while f(far) * last_v > 0:
                far *= 2
            roots.append(brentq(f, last_x, far, xtol=1e-12, rtol=1e-15, maxiter=500))
        roots.sort()
        uniq: list[float] = []
        for x in roots:
            if not uniq or x - uniq[-1] > 1e-9 * max(1.0, x):
                uniq.append(x)
        edges = [0.0, *[x for x in uniq if x > 0], math.inf]
        zones: list[dict] = []
        for a, b in zip(edges[:-1], edges[1:]):
            mid = (a * 2 if a > 0 else max(self.s0, last_x)) if b == math.inf else 0.5 * (a + b)
            v = f(mid)
            sign = 1 if v > self.ztol else (-1 if v < -self.ztol else 0)
            if zones and zones[-1]["sign"] == sign:
                zones[-1]["to"] = b
            else:
                zones.append({"from": a, "to": b, "sign": sign})
        for z in zones:
            d = 1 if z["sign"] >= 0 else -1
            inside = np.nonzero((grid >= z["from"]) & (grid <= min(z["to"], grid[-1])))[0]
            i = inside[np.argmax(d * vals[inside])]
            best = float(vals[i])
            if 0 < i < len(grid) - 1:
                a, b = max(z["from"], grid[i - 1]), min(z["to"], grid[i + 1])
                res = minimize_scalar(lambda x: -d * f(x), bounds=(a, b), method="bounded", options={"xatol": 1e-10})
                if d * -res.fun > d * best:
                    best = -d * res.fun
            z["unbounded"] = z["to"] == math.inf and ((d > 0 and up_unb) or (d < 0 and dn_unb))
            z["best"] = None if z["unbounded"] else best
        prof = [z for z in zones if z["sign"] > 0]
        loss = [z for z in zones if z["sign"] < 0]
        max_p = None if up_unb else (max(z["best"] for z in prof) if prof else float(vals.max()))
        max_l = None if dn_unb else (min(z["best"] for z in loss) if loss else float(vals.min()))
        return {"bes": [z["from"] for z in zones[1:]], "zones": zones, "max": max_p, "min": max_l,
                "max_unb": up_unb, "min_unb": dn_unb}

    def prob_below(self, x: float, sig: float, t_front: float) -> float:
        if x <= 0:
            return 0.0
        if x == math.inf:
            return 1.0
        if t_front <= 0:
            return 1.0 if self.s0 < x else 0.0
        d2 = (math.log(self.s0 / x) + (self.r - self.q - 0.5 * sig * sig) * t_front) / (sig * math.sqrt(t_front))
        return float(ndtr(-d2))

    def p_itm(self, leg: Leg) -> float | None:
        if not leg.opt:
            return None
        t_y = self.years(leg, self.asof)
        if t_y <= 0:
            return 1.0 if float(self.intrinsic(leg, np.array([self.s0]))[0]) > 0 else 0.0
        d2 = (math.log(self.s0 / leg.strike) + (self.r - self.q - 0.5 * leg.iv ** 2) * t_y) / (leg.iv * math.sqrt(t_y))
        return float(ndtr(d2)) if leg.kind == "call" else float(ndtr(-d2))


def expected_for(cfg: dict) -> dict:
    """Compute every golden value of one case."""
    pos = Position(cfg)
    exp, now = pos.analyze(pos.front), pos.analyze(pos.asof)
    t_front = max(0.0, (pos.front - pos.asof) / YEAR_S)
    sig_atm = None
    if pos.front_day in pos.smile:
        ks, ivs = pos.smile[pos.front_day]
        sig_atm = float(np.interp(pos.s0, ks, ivs))
    for z in exp["zones"]:
        z["prob"] = None if sig_atm is None else pos.prob_below(z["to"], sig_atm, t_front) - pos.prob_below(z["from"], sig_atm, t_front)
    rank = {"bid/ask": 0, "mid/mark": 1, "modello": 2}
    basis, pnl_mark, pnl_close, legs = "bid/ask", pos.carry, pos.carry, []
    for leg in pos.legs:
        model0 = float(pos.value(leg, np.array([pos.s0]), pos.asof)[0])
        mark = leg.mark if leg.mark is not None else (model0 if leg.opt else pos.s0)
        mark_src = "mark" if leg.mark is not None else ("modello" if leg.opt else "spot")
        if leg.sgn > 0 and leg.bid is not None:
            exit_v, src = leg.bid, "bid/ask"
        elif leg.sgn < 0 and leg.ask is not None:
            exit_v, src = leg.ask, "bid/ask"
        else:
            exit_v, src = mark, ("modello" if mark_src == "modello" else "mid/mark")
        if rank[src] > rank[basis]:
            basis = src
        pnl_mark += leg.sgn * (mark - leg.entry) * leg.qty * leg.mult
        pnl_close += leg.sgn * (exit_v - leg.entry) * leg.qty * leg.mult
        legs.append({"T0": pos.years(leg, pos.asof) if leg.opt else 0.0, "model0": model0, "pItm": pos.p_itm(leg)})
    day1 = ny_ts(pos.asof_day + timedelta(days=1))
    spot = np.array([pos.s0])
    scen = []
    for p in cfg.get("scenarios", []):
        x = np.array([float(p)])
        scen.append({"price": float(p), "exp": float(pos.pnl(x, pos.front)[0]), "now": float(pos.pnl(x, pos.asof)[0]),
                     "ivDn": float(pos.pnl(x, pos.asof, -pos.stress / 100)[0]),
                     "ivUp": float(pos.pnl(x, pos.asof, pos.stress / 100)[0])})
    return {
        "T0front": t_front,
        "bes": exp["bes"], "besToday": now["bes"],
        "maxProfit": exp["max"], "maxProfitUnbounded": exp["max_unb"],
        "maxLoss": exp["min"], "maxLossUnbounded": exp["min_unb"],
        "zones": [{"from": z["from"], "to": None if z["to"] == math.inf else z["to"], "sign": z["sign"],
                   "best": z["best"], "unbounded": z["unbounded"], "prob": z["prob"]} for z in exp["zones"]],
        "pnlExpSpot": float(pos.pnl(spot, pos.front)[0]), "pnlNowSpot": float(pos.pnl(spot, pos.asof)[0]),
        "deltaNow": pos.delta(pos.s0, pos.asof),
        "thetaDay": float(pos.pnl(spot, day1)[0] - pos.pnl(spot, pos.asof)[0]),
        "vegaPt": float((pos.pnl(spot, pos.asof, 0.01)[0] - pos.pnl(spot, pos.asof, -0.01)[0]) / 2),
        "pnlMark": pnl_mark, "pnlClose": pnl_close, "closeBasis": basis,
        "sigmaAtm": sig_atm, "legs": legs, "scenarios": scen,
    }


def close(a, b, tol: float) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tol


def compare(old: dict, new: dict, prefix: str = "") -> list[str]:
    """Return the differences between two expected blocks."""
    diffs = []
    if isinstance(new, dict):
        for k, v in new.items():
            diffs += compare(old.get(k) if isinstance(old, dict) else None, v, prefix + "." + k)
    elif isinstance(new, list):
        if not isinstance(old, list) or len(old) != len(new):
            return [prefix + ": lunghezza diversa"]
        for i, (a, b) in enumerate(zip(old, new)):
            diffs += compare(a, b, prefix + f"[{i}]")
    elif isinstance(new, float) and isinstance(old, (int, float)):
        if not close(float(old), new, 1e-9 + 1e-9 * abs(new)):
            diffs.append(f"{prefix}: {old} -> {new}")
    elif old != new:
        diffs.append(f"{prefix}: {old} -> {new}")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write the expected values into the fixture")
    args = parser.parse_args()
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    problems = []
    for case in data["cases"]:
        new = expected_for(case["config"])
        if args.write:
            case["expected"] = new
        else:
            for d in compare(case.get("expected", {}), new):
                problems.append(case["name"] + d)
        print(f"{case['name']}: BE {[round(b, 4) for b in new['bes']]} max {new['maxProfit']} min {new['maxLoss']} "
              f"now {new['pnlNowSpot']:.4f} theta {new['thetaDay']:.4f}")
    if args.write:
        FIXTURE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("fixture scritta:", FIXTURE)
        return 0
    for p in problems:
        print("DIFF", p)
    print("OK" if not problems else f"{len(problems)} differenze")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
