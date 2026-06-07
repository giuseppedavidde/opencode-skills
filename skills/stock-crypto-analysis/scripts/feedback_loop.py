#!/usr/bin/env python3
"""
Feedback loop analyzer for the stock-crypto-analysis engine.

Reads trade_log.jsonl and produces performance analytics:
- Hit rate by verdict type and macro window
- Average PnL by score bucket
- Performance vs benchmark
- Pattern identification (e.g., "DEFENSIVE → AVOID had 87% accuracy")

Usage:
    python3 feedback_loop.py                  # Full report to stdout
    python3 feedback_loop.py --json           # JSON output
    python3 feedback_loop.py --report report.md  # Markdown report to file
    python3 feedback_loop.py --since 2026-01-01  # Filter by date
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add parent dir so we can import schemas
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SKILL_DIR))




DEFAULT_LOG_PATH = Path.home() / "Progetti" / "Github" / "Data_for_Analysis" / "trade_log.jsonl"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_trades(log_path: Path, since: Optional[datetime] = None) -> list[dict]:
    """Load all trades, optionally filtered by date."""
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
                ts = entry.get("entry_date") or entry.get("timestamp", "")
                if ts and datetime.fromisoformat(ts.replace("Z", "+00:00")) < since:
                    continue

            trades.append(entry)

    return trades


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


def compute_hit_rate(trades: list[dict]) -> dict[str, Any]:
    """Overall and per-category hit rates."""
    closed = [t for t in trades if not t.get("is_open", True) and t.get("pnl_pct") is not None]

    if not closed:
        return {"error": "No closed trades with PnL data"}

    by_verdict: dict[str, list[float]] = defaultdict(list)
    by_window: dict[str, list[float]] = defaultdict(list)
    by_direction: dict[str, list[float]] = defaultdict(list)
    by_score_bucket: dict[str, list[float]] = defaultdict(list)

    for t in closed:
        pnl = t["pnl_pct"]
        vs = t.get("verdict_snapshot", {})

        by_verdict[vs.get("verdict", "Unknown")].append(pnl)
        by_window[vs.get("macro", {}).get("window", "Unknown")].append(pnl)
        by_direction[vs.get("direction", "Unknown")].append(pnl)
        by_score_bucket[_bucket_score(vs.get("composite_score", 0))].append(pnl)

    def _stats(values: list[float]) -> dict:
        wins = [v for v in values if v > 0]
        return {
            "count": len(values),
            "wins": len(wins),
            "losses": len(values) - len(wins),
            "hit_rate": round(len(wins) / len(values) * 100, 1) if values else 0,
            "avg_pnl": round(sum(values) / len(values), 2) if values else 0,
            "best": round(max(values), 2),
            "worst": round(min(values), 2),
        }

    return {
        "total_closed": len(closed),
        "overall": _stats([t["pnl_pct"] for t in closed]),
        "by_verdict": {k: _stats(v) for k, v in sorted(by_verdict.items())},
        "by_macro_window": {k: _stats(v) for k, v in sorted(by_window.items())},
        "by_direction": {k: _stats(v) for k, v in sorted(by_direction.items())},
        "by_score_bucket": {k: _stats(v) for k, v in sorted(by_score_bucket.items())},
    }


def compute_sharpe_like(trades: list[dict]) -> Optional[float]:
    """Compute a Sharpe-like ratio from trade PnLs (no risk-free rate)."""
    closed = [t for t in trades if not t.get("is_open", True) and t.get("pnl_pct") is not None]
    pnls = [t["pnl_pct"] for t in closed]

    if len(pnls) < 2:
        return None

    mean_ = sum(pnls) / len(pnls)
    variance = sum((x - mean_) ** 2 for x in pnls) / (len(pnls) - 1) if len(pnls) > 1 else 0

    if variance <= 0:
        return None

    return round(mean_ / (variance ** 0.5), 3)


def compute_drawdown(trades: list[dict]) -> dict:
    """Compute max drawdown from cumulative PnL."""
    closed = sorted(
        [t for t in trades if not t.get("is_open", True) and t.get("pnl_pct") is not None],
        key=lambda t: t.get("exit_date", ""),
    )

    if not closed:
        return {"max_drawdown_pct": 0, "peak_pnl": 0, "trough_pnl": 0}

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    peak_val = 0.0
    trough_val = 0.0

    for t in closed:
        cumulative += t["pnl_pct"]
        peak = max(peak, cumulative)
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
            peak_val = peak
            trough_val = cumulative

    return {
        "max_drawdown_pct": round(max_dd, 2),
        "peak_cumulative_pnl": round(peak_val, 2),
        "trough_cumulative_pnl": round(trough_val, 2),
    }


def _pattern_defensive_avoid(closed: list[dict]) -> Optional[str]:
    """Check pattern: DEFENSIVE + AVOID accuracy."""
    def_avoid = [
        t for t in closed
        if t.get("verdict_snapshot", {}).get("macro", {}).get("window") == "DEFENSIVE"
        and t.get("verdict_snapshot", {}).get("verdict") == "Avoid / Wait"
    ]
    if len(def_avoid) < 3:
        return None
    wins = [t for t in def_avoid if t["pnl_pct"] >= 0]
    acc = len(wins) / len(def_avoid) * 100
    return (
        f"In DEFENSIVE window, AVOID verdicts were correct {acc:.0f}% of the time "
        f"({len(wins)}/{len(def_avoid)} trades profitable or break-even)"
    )


def _pattern_lt_vs_st(closed: list[dict]) -> Optional[str]:
    """Check pattern: Long-Term vs Short-Term hit rate."""
    lt = [t["pnl_pct"] for t in closed
          if t.get("verdict_snapshot", {}).get("verdict") == "Long-Term Investment"]
    st = [t["pnl_pct"] for t in closed
          if "Short-Term" in t.get("verdict_snapshot", {}).get("verdict", "")]
    if not lt or not st:
        return None
    lt_hr = len([x for x in lt if x > 0]) / len(lt) * 100
    st_hr = len([x for x in st if x > 0]) / len(st) * 100
    better = "LONG_TERM" if lt_hr > st_hr else "SHORT_TERM"
    return f"Long-Term hit rate {lt_hr:.0f}% vs Short-Term {st_hr:.0f}% — {better} outperforms"


def _pattern_score_buckets(closed: list[dict]) -> list[str]:
    """Check pattern: score bucket reliability."""
    results = []
    for bucket in ("70-100", "50-69"):
        low_str, high_str = bucket.split("-", maxsplit=1)
        low, high = int(low_str), int(high_str)
        def _in_bucket(t: dict, lo: int = low, hi: int = high) -> bool:
            score = t.get("verdict_snapshot", {}).get("composite_score", 0)
            return lo <= score <= hi
        bucket_trades = [t for t in closed if _in_bucket(t)]
        if len(bucket_trades) >= 3:
            wins = [t for t in bucket_trades if t["pnl_pct"] > 0]
            hr = len(wins) / len(bucket_trades) * 100
            results.append(
                f"Score bucket {bucket}: hit rate {hr:.0f}% "
                f"({len(wins)}/{len(bucket_trades)})"
            )
    return results


def _pattern_direction_asymmetry(closed: list[dict]) -> Optional[str]:
    """Check pattern: Long vs Short PnL asymmetry."""
    longs = [t["pnl_pct"] for t in closed
             if t.get("verdict_snapshot", {}).get("direction") == "Long"]
    shorts = [t["pnl_pct"] for t in closed
              if t.get("verdict_snapshot", {}).get("direction") == "Short"]
    if not longs or not shorts:
        return None
    long_avg = sum(longs) / len(longs)
    short_avg = sum(shorts) / len(shorts)
    return f"Long avg PnL {long_avg:+.2f}% vs Short avg PnL {short_avg:+.2f}%"


def find_patterns(trades: list[dict]) -> list[str]:
    """Identify recurring patterns in trade outcomes."""
    patterns: list[str] = []
    closed = [t for t in trades if not t.get("is_open", True) and t.get("pnl_pct") is not None]

    result = _pattern_defensive_avoid(closed)
    if result:
        patterns.append(result)

    result = _pattern_lt_vs_st(closed)
    if result:
        patterns.append(result)

    patterns.extend(_pattern_score_buckets(closed))

    result = _pattern_direction_asymmetry(closed)
    if result:
        patterns.append(result)

    return patterns


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(trades: list[dict]) -> dict:
    """Generate the full feedback report as a dict."""
    hit_rate = compute_hit_rate(trades)
    sharpe = compute_sharpe_like(trades)
    dd = compute_drawdown(trades)
    patterns = find_patterns(trades)

    open_count = len([t for t in trades if t.get("is_open", True)])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_trades": len(trades),
        "open_trades": open_count,
        "closed_trades": hit_rate.get("total_closed", 0),
        "hit_rate": hit_rate,
        "sharpe_like_ratio": sharpe,
        "drawdown": dd,
        "patterns": patterns,
    }


def format_report(report: dict) -> str:
    """Format the report as markdown."""
    lines = [
        "# Feedback Loop Report",
        f"Generated: {report['generated_at']}\n",
        f"**Total trades**: {report['total_trades']} "
        f"({report['open_trades']} open, {report['closed_trades']} closed)",
    ]

    hr = report.get("hit_rate", {})
    if "error" not in hr:
        overall = hr["overall"]
        lines.append("\n## Overall Performance")
        lines.append(f"- Hit rate: {overall['hit_rate']}% "
                     f"({overall['wins']}W / {overall['losses']}L)")
        lines.append(f"- Avg PnL: {overall['avg_pnl']:+.2f}%")
        lines.append(f"- Best: {overall['best']:+.2f}% | Worst: {overall['worst']:+.2f}%")

        if report.get("sharpe_like_ratio") is not None:
            lines.append(f"- Sharpe-like ratio: {report['sharpe_like_ratio']}")

        dd = report.get("drawdown", {})
        if dd.get("max_drawdown_pct", 0) > 0:
            lines.append(f"- Max drawdown: {dd['max_drawdown_pct']:.2f}% "
                         f"(peak {dd['peak_cumulative_pnl']:+.2f}% → "
                         f"trough {dd['trough_cumulative_pnl']:+.2f}%)")

        # By verdict
        by_verdict = hr.get("by_verdict", {})
        if by_verdict:
            lines.append("\n## By Verdict")
            for v, stats in by_verdict.items():
                lines.append(
                    f"- **{v}**: {stats['count']} trades, "
                    f"hit rate {stats['hit_rate']}%, avg PnL {stats['avg_pnl']:+.2f}%"
                )

        # By macro window
        by_window = hr.get("by_macro_window", {})
        if by_window:
            lines.append("\n## By Macro Window")
            for w, stats in by_window.items():
                lines.append(
                    f"- **{w}**: {stats['count']} trades, "
                    f"hit rate {stats['hit_rate']}%, avg PnL {stats['avg_pnl']:+.2f}%"
                )

        # By score bucket
        by_bucket = hr.get("by_score_bucket", {})
        if by_bucket:
            lines.append("\n## By Score Bucket")
            for b, stats in by_bucket.items():
                lines.append(
                    f"- **{b}**: {stats['count']} trades, "
                    f"hit rate {stats['hit_rate']}%, avg PnL {stats['avg_pnl']:+.2f}%"
                )

    # Patterns
    patterns = report.get("patterns", [])
    if patterns:
        lines.append("\n## Detected Patterns")
        for pat in patterns:
            lines.append(f"- {pat}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Feedback loop analyzer")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--report", type=str, help="Write markdown report to file")
    parser.add_argument("--since", type=str, help="Filter trades since date (YYYY-MM-DD)")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    trades = load_trades(log_path, since)

    if not trades:
        print("No trades found in log.")
        return

    report = generate_report(trades)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif args.report:
        md = format_report(report)
        Path(args.report).write_text(md, encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
