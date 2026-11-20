#!/usr/bin/env python3
"""
Feedback loop analyzer for the stock-crypto-analysis engine.

Reads trade_log.jsonl and produces performance analytics:
- hit rate and average P&L of the positions, by verdict, macro window, direction and score bucket;
- Avoid verdicts count as flat (no position, P&L 0). The report shows the move of the
  underlying after each Avoid, so the verdict is checked against the market;
- a time-based equity curve on calendar days, the daily Sharpe ratio and the max drawdown
  of that curve;
- bootstrap confidence intervals of the per-trade statistics.

The equity curve books the realized P&L (in % of equity) on the exit date. Open trades
have no mark-to-market, so the daily volatility is a lower bound.

Usage:
    python3 feedback_loop.py                     # Full report to stdout
    python3 feedback_loop.py --json              # JSON output
    python3 feedback_loop.py --report report.md  # Markdown report to file
    python3 feedback_loop.py --since 2026-01-01  # Filter by entry date
    python3 feedback_loop.py --rf 0.04           # Annual risk-free rate for the Sharpe ratio
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# Add parent dir so we can import schemas
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SKILL_DIR))
sys.path.insert(0, str(_SCRIPT_DIR))

# pylint: disable=import-error,wrong-import-position
from log_trade import position_side  # noqa: E402

MIN_CURVE_DAYS = 30
MIN_RETURN_DAYS = 5
SMALL_SAMPLE = 30


def _default_data_file(name: str) -> Path:
    """Return the data file: $OPENCODE_SKILLS_DATA_DIR, the legacy data repo, then the XDG data folder."""
    override = os.environ.get("OPENCODE_SKILLS_DATA_DIR")
    if override:
        return Path(override).expanduser() / name
    legacy = Path.home() / "Progetti" / "Github" / "Data_for_Analysis"
    if legacy.is_dir():
        return legacy / name
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "opencode-skills" / name


DEFAULT_LOG_PATH = _default_data_file("trade_log.jsonl")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _dt(value: Any) -> Optional[datetime]:
    """Parse an ISO datetime; naive values are UTC. Returns None when the value is empty or invalid."""
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def load_trades(log_path: Path, since: Optional[datetime] = None) -> list[dict]:
    """Load all trades, optionally filtered by entry date."""
    if not log_path.exists():
        return []
    trades = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since:
                when = _dt(entry.get("entry_date") or entry.get("timestamp"))
                if when and when < since:
                    continue
            trades.append(entry)
    return trades


# ---------------------------------------------------------------------------
# Trade views
# ---------------------------------------------------------------------------


def underlying_move(t: dict) -> Optional[float]:
    """Move of the underlying in %, from the record or from the prices."""
    if t.get("underlying_move_pct") is not None:
        return float(t["underlying_move_pct"])
    entry, exit_ = t.get("entry_price"), t.get("exit_price")
    if entry and exit_ and entry > 0:
        return (exit_ / entry - 1.0) * 100.0
    return None


def position_pnl(t: dict) -> Optional[float]:
    """Position P&L in % of the position. A flat entry has 0; an old record is recomputed from its prices."""
    side = position_side(t)
    if side == "flat":
        return 0.0
    move = underlying_move(t)
    if t.get("pnl_pct") is not None and t.get("position") is not None:
        return float(t["pnl_pct"])
    if move is None:
        return float(t["pnl_pct"]) if t.get("pnl_pct") is not None else None
    fees = float(t.get("fees_pct") or 0.0)
    return (-move if side == "short" else move) - fees


def equity_pnl(t: dict) -> Optional[float]:
    """Position P&L in % of equity, or None when the size is unknown."""
    if position_side(t) == "flat":
        return 0.0
    if t.get("pnl_equity_pct") is not None and t.get("position") is not None:
        return float(t["pnl_equity_pct"])
    pnl, size = position_pnl(t), t.get("position_size_pct")
    if pnl is None or not size:
        return None
    return pnl * float(size) / 100.0


def closed_positions(trades: list[dict]) -> list[dict]:
    """Closed long or short trades with a P&L."""
    return [t for t in trades if not t.get("is_open", True) and position_side(t) != "flat"
            and position_pnl(t) is not None]


def flat_signals(trades: list[dict]) -> list[dict]:
    """Closed flat entries (Avoid and Neutral verdicts) with a known move of the underlying."""
    return [t for t in trades if not t.get("is_open", True) and position_side(t) == "flat"
            and underlying_move(t) is not None]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _bucket_score(score: float) -> str:
    """Map composite score to a bucket label."""
    if score >= 70:
        return "70-100"
    if score >= 50:
        return "50-69"
    if score >= 30:
        return "30-49"
    return "0-29"


def _stats(values: list[float]) -> dict:
    wins = [v for v in values if v > 0]
    return {
        "count": len(values),
        "wins": len(wins),
        "losses": len(values) - len(wins),
        "hit_rate": round(len(wins) / len(values) * 100, 1) if values else 0,
        "avg_pnl": round(sum(values) / len(values), 2) if values else 0,
        "best": round(max(values), 2) if values else 0,
        "worst": round(min(values), 2) if values else 0,
        "small_sample": len(values) < SMALL_SAMPLE,
    }


def _avoid_stats(signals: list[dict]) -> dict:
    """An Avoid is right when a long position would have lost money."""
    moves = [underlying_move(t) for t in signals]
    moves = [m for m in moves if m is not None]
    if not moves:
        return {"count": 0}
    return {
        "count": len(moves),
        "avg_underlying_move": round(sum(moves) / len(moves), 2),
        "long_would_lose_pct": round(len([m for m in moves if m < 0]) / len(moves) * 100, 1),
        "small_sample": len(moves) < SMALL_SAMPLE,
    }


def compute_hit_rate(trades: list[dict]) -> dict[str, Any]:
    """Hit rates of the positions (flat entries excluded) and the check of the flat signals."""
    closed = closed_positions(trades)
    signals = flat_signals(trades)
    if not closed and not signals:
        return {"error": "No closed trades with price data"}

    by_verdict: dict[str, list[float]] = defaultdict(list)
    by_window: dict[str, list[float]] = defaultdict(list)
    by_direction: dict[str, list[float]] = defaultdict(list)
    by_score_bucket: dict[str, list[float]] = defaultdict(list)
    for t in closed:
        pnl = position_pnl(t)
        vs = t.get("verdict_snapshot", {})
        by_verdict[vs.get("verdict", "Unknown")].append(pnl)
        by_window[vs.get("macro", {}).get("window", "Unknown")].append(pnl)
        by_direction[position_side(t)].append(pnl)
        by_score_bucket[_bucket_score(vs.get("composite_score", 0))].append(pnl)

    avoid_by_window: dict[str, list[dict]] = defaultdict(list)
    for t in signals:
        avoid_by_window[t.get("verdict_snapshot", {}).get("macro", {}).get("window", "Unknown")].append(t)

    return {
        "total_closed": len(closed),
        "flat_signals": len(signals),
        "overall": _stats([position_pnl(t) for t in closed]),
        "by_verdict": {k: _stats(v) for k, v in sorted(by_verdict.items())},
        "by_macro_window": {k: _stats(v) for k, v in sorted(by_window.items())},
        "by_direction": {k: _stats(v) for k, v in sorted(by_direction.items())},
        "by_score_bucket": {k: _stats(v) for k, v in sorted(by_score_bucket.items())},
        "avoid_signals": _avoid_stats(signals),
        "avoid_by_macro_window": {k: _avoid_stats(v) for k, v in sorted(avoid_by_window.items())},
    }


def equity_curve(trades: list[dict]) -> dict:
    """Daily equity curve (calendar days, start = 1.0) from the realized P&L in % of equity."""
    booked: dict[date, float] = defaultdict(float)
    starts: list[date] = []
    skipped = 0
    used = 0
    for t in closed_positions(trades):
        exit_dt, entry_dt, pnl = _dt(t.get("exit_date")), _dt(t.get("entry_date")), equity_pnl(t)
        if exit_dt is None or pnl is None:
            skipped += 1
            continue
        booked[exit_dt.date()] += pnl / 100.0
        starts.append((entry_dt or exit_dt).date())
        used += 1
    if not booked:
        return {"dates": [], "equity": [], "returns": [], "trades_used": 0, "trades_skipped": skipped}
    first, last = min(starts + list(booked)), max(booked)
    dates, equity, returns = [], [], []
    level = 1.0
    day = first
    while day <= last:
        r = booked.get(day, 0.0)
        level *= 1.0 + r
        dates.append(day.isoformat())
        equity.append(level)
        returns.append(r)
        day += timedelta(days=1)
    return {"dates": dates, "equity": equity, "returns": returns, "trades_used": used, "trades_skipped": skipped}


def compute_sharpe(trades: list[dict], rf_annual: float = 0.0) -> dict:
    """Annualized Sharpe ratio from the daily returns of the equity curve (calendar days, √365)."""
    curve = equity_curve(trades)
    rets = curve["returns"]
    nonzero = len([r for r in rets if r != 0])
    base = {"days": len(rets), "return_days": nonzero, "rf_annual": rf_annual,
            "trades_used": curve["trades_used"], "trades_skipped": curve["trades_skipped"]}
    if len(rets) < MIN_CURVE_DAYS or nonzero < MIN_RETURN_DAYS:
        return {**base, "insufficient_data": True,
                "reason": f"need >= {MIN_CURVE_DAYS} days and >= {MIN_RETURN_DAYS} days with a realized P&L"}
    excess = [r - rf_annual / 365.0 for r in rets]
    mean_ = sum(excess) / len(excess)
    var_ = sum((x - mean_) ** 2 for x in excess) / (len(excess) - 1)
    if var_ <= 0:
        return {**base, "insufficient_data": True, "reason": "zero variance"}
    sd = math.sqrt(var_)
    return {**base, "insufficient_data": False, "sharpe": round(mean_ / sd * math.sqrt(365.0), 3),
            "mean_daily_pct": round(mean_ * 100, 5), "std_daily_pct": round(sd * 100, 5)}


def compute_drawdown(trades: list[dict]) -> dict:
    """Max drawdown of the equity curve, in % of the peak equity."""
    curve = equity_curve(trades)
    if not curve["equity"]:
        return {"max_drawdown_pct": 0.0, "total_return_pct": 0.0, "peak_date": None, "trough_date": None}
    peak, peak_date = curve["equity"][0], curve["dates"][0]
    max_dd, at_peak, at_trough = 0.0, None, None
    for d, level in zip(curve["dates"], curve["equity"]):
        if level > peak:
            peak, peak_date = level, d
        dd = (1.0 - level / peak) * 100.0
        if dd > max_dd:
            max_dd, at_peak, at_trough = dd, peak_date, d
    return {
        "max_drawdown_pct": round(max_dd, 4),
        "total_return_pct": round((curve["equity"][-1] - 1.0) * 100.0, 4),
        "peak_date": at_peak,
        "trough_date": at_trough,
    }


def _pattern_avoid(signals: list[dict]) -> list[str]:
    """Check the Avoid verdicts against the move of the underlying, per macro window."""
    out = []
    by_window: dict[str, list[dict]] = defaultdict(list)
    for t in signals:
        by_window[t.get("verdict_snapshot", {}).get("macro", {}).get("window", "Unknown")].append(t)
    for window, rows in sorted(by_window.items()):
        if len(rows) < 5:
            continue
        s = _avoid_stats(rows)
        out.append(
            f"In {window} window, after AVOID the underlying moved {s['avg_underlying_move']:+.2f}% on average; "
            f"a long would have lost in {s['long_would_lose_pct']:.0f}% of {s['count']} cases"
            + (" (small sample)" if s["small_sample"] else "")
        )
    return out


def _pattern_lt_vs_st(closed: list[dict]) -> Optional[str]:
    """Check pattern: Long-Term vs Short-Term hit rate."""
    lt = [position_pnl(t) for t in closed if t.get("verdict_snapshot", {}).get("verdict") == "Long-Term Investment"]
    st = [position_pnl(t) for t in closed if "Short-Term" in t.get("verdict_snapshot", {}).get("verdict", "")]
    if len(lt) < 5 or len(st) < 5:
        return None
    lt_hr = len([x for x in lt if x > 0]) / len(lt) * 100
    st_hr = len([x for x in st if x > 0]) / len(st) * 100
    better = "LONG_TERM" if lt_hr > st_hr else "SHORT_TERM"
    small = " (small sample)" if min(len(lt), len(st)) < SMALL_SAMPLE else ""
    return f"Long-Term hit rate {lt_hr:.0f}% vs Short-Term {st_hr:.0f}% — {better} has the higher hit rate{small}"


def _pattern_score_buckets(closed: list[dict]) -> list[str]:
    """Check pattern: score bucket reliability."""
    results = []
    for bucket in ("70-100", "50-69"):
        rows = [t for t in closed if _bucket_score(t.get("verdict_snapshot", {}).get("composite_score", 0)) == bucket]
        if len(rows) >= 5:
            wins = [t for t in rows if position_pnl(t) > 0]
            small = " (small sample)" if len(rows) < SMALL_SAMPLE else ""
            results.append(f"Score bucket {bucket}: hit rate {len(wins) / len(rows) * 100:.0f}% ({len(wins)}/{len(rows)}){small}")
    return results


def _pattern_direction_asymmetry(closed: list[dict]) -> Optional[str]:
    """Check pattern: Long vs Short P&L asymmetry."""
    longs = [position_pnl(t) for t in closed if position_side(t) == "long"]
    shorts = [position_pnl(t) for t in closed if position_side(t) == "short"]
    if len(longs) < 5 or len(shorts) < 5:
        return None
    return f"Long avg P&L {sum(longs) / len(longs):+.2f}% vs Short avg P&L {sum(shorts) / len(shorts):+.2f}%"


def find_patterns(trades: list[dict]) -> list[str]:
    """Identify recurring patterns in trade outcomes (minimum 5 cases each)."""
    closed = closed_positions(trades)
    patterns: list[str] = _pattern_avoid(flat_signals(trades))
    for result in (_pattern_lt_vs_st(closed), *_pattern_score_buckets(closed), _pattern_direction_asymmetry(closed)):
        if result:
            patterns.append(result)
    return patterns


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_metrics(trades: list[dict], n_iterations: int = 10_000, seed: int = 42) -> dict:
    """Bootstrap the closed positions: hit rate, average P&L of the position and of the equity.

    Time-dependent statistics (Sharpe, drawdown) are not bootstrapped: resampling trades breaks the time order.
    Returns an empty dict with fewer than 5 closed positions.
    """
    closed = closed_positions(trades)
    if len(closed) < 5:
        return {}
    pnls = [position_pnl(t) for t in closed]
    eq = [equity_pnl(t) for t in closed]
    eq_known = [v for v in eq if v is not None]
    n = len(pnls)
    rng = random.Random(seed)
    hit, avg, avg_eq = [], [], []
    for _ in range(n_iterations):
        idx = [rng.randrange(n) for _ in range(n)]
        sample = [pnls[i] for i in idx]
        hit.append(sum(1 for p in sample if p > 0) / n * 100)
        avg.append(sum(sample) / n)
        if eq_known:
            picks = [eq_known[rng.randrange(len(eq_known))] for _ in range(len(eq_known))]
            avg_eq.append(sum(picks) / len(picks))

    def _ci(values: list[float]) -> dict:
        s = sorted(values)
        m = sum(values) / len(values)
        return {
            "mean": round(m, 4),
            "ci_low": round(s[int(len(s) * 0.05)], 4),
            "ci_high": round(s[min(len(s) - 1, int(len(s) * 0.95))], 4),
            "median": round(s[len(s) // 2], 4),
        }

    out = {"n_iterations": n_iterations, "resample_size": n, "small_sample": n < SMALL_SAMPLE,
           "hit_rate": _ci(hit), "avg_pnl": _ci(avg)}
    if avg_eq:
        out["avg_pnl_equity"] = _ci(avg_eq)
    return out


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(trades: list[dict], bootstrap: bool = True, bootstrap_iterations: int = 10_000,
                    bootstrap_seed: int = 42, rf_annual: float = 0.0) -> dict:
    """Generate the full feedback report as a dict."""
    hit_rate = compute_hit_rate(trades)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_trades": len(trades),
        "open_trades": len([t for t in trades if t.get("is_open", True)]),
        "closed_trades": hit_rate.get("total_closed", 0),
        "flat_signals": hit_rate.get("flat_signals", 0),
        "hit_rate": hit_rate,
        "sharpe": compute_sharpe(trades, rf_annual),
        "drawdown": compute_drawdown(trades),
        "patterns": find_patterns(trades),
    }
    if bootstrap:
        report["bootstrap"] = bootstrap_metrics(trades, bootstrap_iterations, bootstrap_seed)
    return report


def _fmt_group(title: str, groups: dict) -> list[str]:
    lines = [f"\n## {title}"] if groups else []
    for k, s in groups.items():
        small = " · small sample" if s.get("small_sample") else ""
        lines.append(f"- **{k}**: {s['count']} trades, hit rate {s['hit_rate']}%, avg P&L {s['avg_pnl']:+.2f}%{small}")
    return lines


def format_report(report: dict) -> str:
    """Format the report as markdown."""
    lines = [
        "# Feedback Loop Report",
        f"Generated: {report['generated_at']}\n",
        f"**Total entries**: {report['total_trades']} ({report['open_trades']} open, "
        f"{report['closed_trades']} closed positions, {report['flat_signals']} flat signals)",
    ]
    hr = report.get("hit_rate", {})
    if "error" not in hr:
        overall = hr["overall"]
        lines.append("\n## Positions (Avoid and Neutral verdicts are flat and excluded)")
        lines.append(f"- Hit rate: {overall['hit_rate']}% ({overall['wins']}W / {overall['losses']}L)")
        lines.append(f"- Avg P&L: {overall['avg_pnl']:+.2f}% of the position")
        lines.append(f"- Best: {overall['best']:+.2f}% | Worst: {overall['worst']:+.2f}%")
        sharpe = report.get("sharpe", {})
        if sharpe.get("insufficient_data"):
            lines.append(f"- Sharpe (daily equity curve): insufficient data ({sharpe.get('reason')})")
        else:
            lines.append(f"- Sharpe (daily equity curve, rf {sharpe['rf_annual'] * 100:.2f}%, √365): "
                         f"{sharpe['sharpe']:.3f} over {sharpe['days']} days")
        dd = report.get("drawdown", {})
        lines.append(f"- Equity curve: total return {dd.get('total_return_pct', 0):+.3f}%, "
                     f"max drawdown {dd.get('max_drawdown_pct', 0):.3f}%"
                     + (f" ({dd['peak_date']} → {dd['trough_date']})" if dd.get("peak_date") else ""))
        lines.append("- The curve books the realized P&L on the exit date; open trades have no mark-to-market.")
        lines += _fmt_group("By Verdict", hr.get("by_verdict", {}))
        lines += _fmt_group("By Macro Window", hr.get("by_macro_window", {}))
        lines += _fmt_group("By Score Bucket", hr.get("by_score_bucket", {}))
        av = hr.get("avoid_signals", {})
        if av.get("count"):
            lines.append("\n## Avoid Signals (no position)")
            lines.append(f"- {av['count']} signals: underlying move {av['avg_underlying_move']:+.2f}% on average; "
                         f"a long would have lost in {av['long_would_lose_pct']:.0f}% of the cases"
                         + (" · small sample" if av.get("small_sample") else ""))
    bs = report.get("bootstrap")
    if bs:
        lines.append("\n## Bootstrap Confidence Intervals (90% CI, per trade)")
        lines.append(f"- Resamples: {bs['n_iterations']:,} | Sample size: {bs['resample_size']}"
                     + (" · small sample" if bs.get("small_sample") else ""))
        for label, key in [("Hit rate", "hit_rate"), ("Avg P&L (% of position)", "avg_pnl"),
                           ("Avg P&L (% of equity)", "avg_pnl_equity")]:
            s = bs.get(key)
            if s:
                lines.append(f"- **{label}**: mean {s['mean']:.3f} [{s['ci_low']:.3f} – {s['ci_high']:.3f}] (median {s['median']:.3f})")
    if report.get("patterns"):
        lines.append("\n## Detected Patterns")
        lines += [f"- {p}" for p in report["patterns"]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Feedback loop analyzer")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--report", type=str, help="Write markdown report to file")
    parser.add_argument("--since", type=str, help="Filter trades since date (YYYY-MM-DD)")
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for the Sharpe ratio (0.04 = 4%%)")
    parser.add_argument("--no-bootstrap", action="store_true", help="Skip bootstrap resampling")
    parser.add_argument("--bootstrap-iterations", type=int, default=10_000, help="Bootstrap resample count")
    parser.add_argument("--bootstrap-seed", type=int, default=42, help="Random seed for bootstrap reproducibility")
    args = parser.parse_args(argv)

    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
    trades = load_trades(Path(args.log_path), since)
    if not trades:
        print("No trades found in log.")
        return
    report = generate_report(trades, bootstrap=not args.no_bootstrap, bootstrap_iterations=args.bootstrap_iterations,
                             bootstrap_seed=args.bootstrap_seed, rf_annual=args.rf)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif args.report:
        Path(args.report).write_text(format_report(report), encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
