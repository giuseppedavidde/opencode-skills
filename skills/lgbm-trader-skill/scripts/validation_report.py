#!/usr/bin/env python3
"""Multi-ticker validation report with strict OOS-only gate and degradation.

Loads the prediction export CSV, splits into calibration (≤ cutoff) and
OOS (> cutoff), evaluates per-ticker and pooled with costs on BOTH splits,
then applies a-priori acceptance thresholds EXCLUSIVELY on OOS data.

All verdicts are based on OOS metrics. Full-period metrics are stored
as diagnostic reference with an explicit warning that they include
calibration data and inflate the signal.

Usage:
    python scripts/validation_report.py \\
        --predictions /tmp/.../predictions.csv \\
        --output /tmp/.../multiticker_report/ \\
        --cutoff 2024-06-30 --horizons 20,60,180
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

# ── Acceptance thresholds (a-priori, applied ONLY on OOS) ──────────────

ACCEPTANCE_THRESHOLDS: dict = {
    "ic_rank_abs_min": 0.03,
    "ic_pearson_min": 0.05,
    "quintile_spread_annualized_pct_min": 5.0,
    "hit_rate_bucket_delta_min": 0.05,
    "cost_impact_min_pct": 90.0,
    "n_obs_min": 5000,
    "pass_rate_min": 0.80,
    "degradation_warning_ratio": 0.50,
    "description": (
        "A-priori acceptance thresholds for VP signal validation. "
        "Verdicts are based EXCLUSIVELY on OOS data (as_of > cutoff). "
        "Full-period metrics are stored for diagnostic reference only. "
        "Thresholds require minimum IC, meaningful quintile spread, "
        "and cost resilience."
    ),
}


# ── Shared helpers ─────────────────────────────────────────────────────

def load_predictions(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Predictions file not found: {csv_path}\n"
            f"Generate: python scripts/export_predictions.py "
            f"--tickers-file <CSV> --limit 50 --period 5y --output <dir>"
        )
    df = pd.read_csv(csv_path)
    required = [
        "ticker", "as_of", "signal_score", "horizon_days",
        "forward_return", "forward_price",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df


def predictions_to_records(
    df: pd.DataFrame, ticker_filter: str | None = None, horizon: int | None = None
) -> list:
    from backtest.contract import BacktestPrediction

    sub = df
    if ticker_filter:
        sub = sub[sub["ticker"] == ticker_filter]
    if horizon is not None:
        sub = sub[sub["horizon_days"] == horizon]

    records = []
    for _, row in sub.iterrows():
        records.append(BacktestPrediction(
            ticker=str(row["ticker"]),
            as_of=str(row["as_of"]),
            signal_score=float(row["signal_score"]),
            horizon_days=int(row["horizon_days"]),
            forward_price=(
                float(row["forward_price"]) if pd.notna(row["forward_price"]) else None
            ),
            forward_return=(
                float(row["forward_return"]) if pd.notna(row["forward_return"]) else None
            ),
        ))
    return records


def evaluate_single_horizon_pooled(df: pd.DataFrame, horizon: int, config):
    from backtest.evaluator import evaluate
    preds = predictions_to_records(df, horizon=horizon)
    result = evaluate(preds, config=config, ticker="POOLED")
    for hr in result.horizons:
        if hr.horizon_days == horizon:
            return hr
    return result.horizons[0] if result.horizons else None


def _bucket_info(horizon_result):
    qr = horizon_result.quintile_returns or {}
    if len(qr) < 3:
        return {"delta_annualized_pct": None, "is_monotonic": False,
                "best_bucket_mean_return_pct": None, "status": "INSUFFICIENT_DATA"}
    vals = [v for k, v in sorted(qr.items())]
    best = max(vals)
    is_monotonic = all(
        vals[i] <= vals[i + 1] or vals[i] >= vals[i + 1]
        for i in range(len(vals) - 1)
    )
    spread = horizon_result.quintile_spread
    delta_ann = (
        abs(spread) * (252.0 / max(horizon_result.horizon_days, 1))
        if spread is not None else None
    )
    return {
        "delta_annualized_pct": round(delta_ann, 2) if delta_ann else None,
        "is_monotonic": is_monotonic,
        "best_bucket_mean_return_pct": round(best, 4),
    }


def _ic_value(hr) -> float | None:
    return abs(hr.ic_rank) if hr.ic_rank is not None else None


def _pearson_value(hr) -> float | None:
    return abs(hr.ic_pearson) if hr.ic_pearson is not None else None


# ── Threshold evaluation (STRICTLY on OOS) ─────────────────────────────

def evaluate_thresholds_oos(
    hr_gross,
    hr_net,
    n_oos: int,
    horizon: int,
    cost_model,
    degradation: dict | None = None,
) -> list[dict]:
    """Compare OOS metrics against acceptance thresholds."""
    th = ACCEPTANCE_THRESHOLDS
    results = []
    bucket = _bucket_info(hr_gross)

    # IC rank
    ic_val = _ic_value(hr_gross)
    results.append({
        "criterion": "ic_rank_abs_min", "threshold": th["ic_rank_abs_min"],
        "value": round(ic_val, 4) if ic_val is not None else None,
        "result": (
            "PASS" if (ic_val is not None and ic_val >= th["ic_rank_abs_min"])
            else "FAIL" if ic_val is not None else "INSUFFICIENT_DATA"
        ),
    })

    # IC Pearson
    ip_val = _pearson_value(hr_gross)
    results.append({
        "criterion": "ic_pearson_min", "threshold": th["ic_pearson_min"],
        "value": round(ip_val, 4) if ip_val is not None else None,
        "result": (
            "PASS" if (ip_val is not None and ip_val >= th["ic_pearson_min"])
            else "FAIL" if ip_val is not None else "INSUFFICIENT_DATA"
        ),
    })

    # Quintile spread
    spread = bucket["delta_annualized_pct"]
    results.append({
        "criterion": "quintile_spread_annualized_pct_min",
        "threshold": f">= {th['quintile_spread_annualized_pct_min']}%",
        "value": spread,
        "detail": {
            "best_bucket_mean_return_pct": bucket["best_bucket_mean_return_pct"],
            "is_monotonic": bucket["is_monotonic"],
        },
        "result": (
            "PASS" if (spread is not None and spread >= th["quintile_spread_annualized_pct_min"])
            else "FAIL" if spread is not None else "INSUFFICIENT_DATA"
        ),
    })

    # Monotonicity
    results.append({
        "criterion": "hit_rate_monotonic_or_delta",
        "threshold": "monotonic OR delta>5pp",
        "value": {"is_monotonic": bucket["is_monotonic"],
                   "delta_annualized_pct": spread},
        "result": "PASS" if bucket["is_monotonic"] else "FAIL",
    })

    # Cost impact
    cost_pct = None
    if (
        hr_net and hr_net.mean_return_pct_net is not None
        and hr_gross.mean_return_pct is not None
        and abs(hr_gross.mean_return_pct) > 0.001
    ):
        cost_pct = min(abs(hr_net.mean_return_pct_net / hr_gross.mean_return_pct) * 100.0, 100.0)
    results.append({
        "criterion": "cost_impact_min_pct",
        "threshold": f">= {th['cost_impact_min_pct']}%",
        "value": round(cost_pct, 1) if cost_pct is not None else None,
        "note": "net_return_pct / gross_return_pct",
        "result": (
            "PASS" if (cost_pct is not None and cost_pct >= th["cost_impact_min_pct"])
            else "FAIL" if cost_pct is not None else "INSUFFICIENT_DATA"
        ),
    })

    # n_obs
    results.append({
        "criterion": "n_obs_min", "threshold": th["n_obs_min"],
        "value": n_oos,
        "result": "PASS" if n_oos >= th["n_obs_min"] else "FAIL",
    })

    # Degradation warning
    if degradation:
        d = degradation
        ratio = d.get("ratio")
        if ratio is not None and ratio < th["degradation_warning_ratio"]:
            results.append({
                "criterion": "ic_degradation_warning",
                "threshold": f"|IC_oos|/|IC_full| >= {th['degradation_warning_ratio']}",
                "value": round(ratio, 4),
                "detail": {
                    "ic_full_abs": d.get("ic_full_abs"),
                    "ic_oos_abs": d.get("ic_oos_abs"),
                    "note": d.get("note", "Signal degrades on OOS — regime-dependent"),
                },
                "result": "FAIL",
            })
        else:
            results.append({
                "criterion": "ic_degradation_warning",
                "threshold": f"|IC_oos|/|IC_full| >= {th['degradation_warning_ratio']}",
                "value": round(ratio, 4) if ratio else None,
                "result": "PASS" if ratio and ratio >= th["degradation_warning_ratio"] else "INSUFFICIENT_DATA",
            })

    return results


def compute_verdict(threshold_results: list[dict]) -> tuple[str, str]:
    applicable = [r for r in threshold_results if r["result"] != "INSUFFICIENT_DATA"]
    if len(applicable) == 0:
        return "insufficient_data", "No applicable criteria on OOS"
    n_pass = sum(1 for r in applicable if r["result"] == "PASS")
    rate = n_pass / len(applicable)
    if rate >= ACCEPTANCE_THRESHOLDS["pass_rate_min"]:
        return "predictive_evidence", (
            f"{n_pass}/{len(applicable)} OOS criteria PASS ({rate:.0%})"
        )
    return "diagnostic_only", (
        f"Only {n_pass}/{len(applicable)} OOS criteria PASS ({rate:.0%}) "
        f"— threshold {ACCEPTANCE_THRESHOLDS['pass_rate_min']:.0%}"
    )


def _hr_to_dict(hr) -> dict | None:
    if hr is None:
        return None
    return {
        "n_observations": hr.n_observations,
        "ic_rank": hr.ic_rank,
        "ic_pearson": hr.ic_pearson,
        "hit_rate": hr.hit_rate,
        "mean_return_pct": hr.mean_return_pct,
        "quintile_spread": hr.quintile_spread,
        "hit_rate_net": hr.hit_rate_net,
        "mean_return_pct_net": hr.mean_return_pct_net,
        "quintile_spread_net": hr.quintile_spread_net,
        "quintile_returns": hr.quintile_returns,
        "quintile_returns_net": hr.quintile_returns_net,
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Multi-ticker validation report — OOS-only verdict"
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cutoff", default="2024-06-30",
                        help="Temporal cutoff: <=cutoff=calibration, >cutoff=OOS")
    parser.add_argument("--horizons", default="20,60,180")
    parser.add_argument("--min-obs", type=int, default=30)
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    cutoff = args.cutoff

    print(f"Loading predictions: {args.predictions}")
    t0 = time.time()
    df = load_predictions(args.predictions)
    tickers = sorted(df["ticker"].unique())

    # ── Split: calibration vs OOS ───────────────────────────────────
    df_cal = df[df["as_of"] <= cutoff]
    df_oos = df[df["as_of"] > cutoff]

    print(f"  {len(df)} total predictions, {len(tickers)} tickers")
    print(f"  Calibration (≤{cutoff}): {len(df_cal)} predictions")
    print(f"  OOS        (>{cutoff}): {len(df_oos)} predictions")
    print(f"  Horizons: {horizons}")

    from backtest.contract import BacktestConfig, CostModel
    cm = CostModel()

    # ── OOS pooled evaluation (FOR VERDICT) ──────────────────────────
    print(f"\nEvaluating OOS pooled (gross + net) — FOR VERDICT...")
    oos_results: dict[int, dict] = {}

    for h in horizons:
        cfg_gross = BacktestConfig(
            horizons_days=[h], apply_costs=False, cost_model=cm,
            min_horizon_observations=args.min_obs, strict_mode=False,
            permutation_control=False,
        )
        cfg_net = BacktestConfig(
            horizons_days=[h], apply_costs=True, cost_model=cm,
            min_horizon_observations=args.min_obs, strict_mode=False,
            permutation_control=False,
        )

        hr_gross = evaluate_single_horizon_pooled(df_oos, h, cfg_gross)
        hr_net = evaluate_single_horizon_pooled(df_oos, h, cfg_net)
        n_oos = hr_gross.n_observations if hr_gross else len(df_oos[df_oos["horizon_days"] == h])

        # Degradation: compare IC OOS vs IC full
        hr_full = evaluate_single_horizon_pooled(df, h, cfg_gross)
        ic_full_abs = _ic_value(hr_full)
        ic_oos_abs = _ic_value(hr_gross)
        degradation = None
        if ic_full_abs is not None and ic_oos_abs is not None and ic_full_abs > 1e-8:
            ratio = ic_oos_abs / ic_full_abs
            degradation = {
                "ic_full_abs": round(ic_full_abs, 4),
                "ic_oos_abs": round(ic_oos_abs, 4),
                "ratio": round(ratio, 4),
                "note": (
                    f"IC degrades from {ic_full_abs:.4f} (full) to "
                    f"{ic_oos_abs:.4f} (OOS) — signal is regime-dependent. "
                    "Full-period IC includes calibration data and inflates "
                    "the apparent signal strength."
                ),
            }

        threshold_results = evaluate_thresholds_oos(
            hr_gross, hr_net, n_oos, h, cm, degradation=degradation,
        )
        verdict, reason = compute_verdict(threshold_results)

        oos_results[h] = {
            "horizon_days": h,
            "data": "OOS (as_of > {cutoff})",
            "n_observations": n_oos,
            "gross": _hr_to_dict(hr_gross),
            "net": _hr_to_dict(hr_net),
            "threshold_results": threshold_results,
            "verdict": verdict,
            "verdict_reason": reason,
            "ic_degradation": degradation,
        }

    # ── Full-period pooled (DIAGNOSTIC REFERENCE ONLY) ────────────────
    print("Evaluating full period pooled (DIAGNOSTIC REFERENCE, NOT for verdict)...")
    full_results: dict[int, dict] = {}
    for h in horizons:
        cfg = BacktestConfig(
            horizons_days=[h], apply_costs=False, cost_model=cm,
            min_horizon_observations=args.min_obs, strict_mode=False,
            permutation_control=False,
        )
        hr_full = evaluate_single_horizon_pooled(df, h, cfg)
        full_results[h] = {
            "horizon_days": h,
            "data": "FULL PERIOD (calibration + OOS) — DIAGNOSTIC REFERENCE",
            "n_observations": hr_full.n_observations if hr_full else len(df[df["horizon_days"] == h]),
            "gross": _hr_to_dict(hr_full),
            "note": (
                "Includes calibration data. IC on full period is INFLATED "
                "relative to OOS. These metrics are NOT used for verdict."
            ),
        }

    # ── Overall verdict (OOS only) ────────────────────────────────────
    oos_pass = sum(1 for r in oos_results.values()
                   if r["verdict"] == "predictive_evidence")
    overall = (
        "predictive_evidence"
        if oos_pass >= len(horizons) * ACCEPTANCE_THRESHOLDS["pass_rate_min"]
        else "diagnostic_only"
    )

    report = {
        "report_type": "multi_ticker_validation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "signal": "Volume Profile composite (canonical 365d, no look-ahead)",
        "n_tickers": len(tickers),
        "total_predictions": len(df),
        "n_cal": int(len(df_cal)),
        "n_oos": int(len(df_oos)),
        "cutoff": cutoff,
        "horizons": horizons,
        "acceptance_thresholds": ACCEPTANCE_THRESHOLDS,
        "cost_model": cm.assumptions_dict(),
        "overall_verdict": overall,
        "overall_horizons_oos_pass": f"{oos_pass}/{len(horizons)}",
        "verdict_basis": "OOS data only (as_of > cutoff)",
        "pooled_oos": oos_results,
        "pooled_full_reference": full_results,
        "limits": [
            "OHLCV-only: no fundamental/macro data in signal",
            "Point-in-time: signals use only data available at as_of",
            "Costs are ESTIMATED (CostModel default conservative)",
            "Survivorship bias: 50 tickers from current-snapshot CSV",
            "Cross-sectional pooling masks per-ticker heterogeneity",
            "Verdicts based EXCLUSIVELY on OOS data (as_of > cutoff)",
            "Full-period metrics INCLUDE calibration — INFLATED, not for verdict",
        ],
    }

    # ── Save ──────────────────────────────────────────────────────────
    json_path = out_dir / "validation_report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nJSON report: {json_path}")

    csv_rows = []
    for h in horizons:
        pr = oos_results.get(h, {})
        tr = pr.get("threshold_results", [])
        tr_dict = {t["criterion"]: t["result"] for t in tr}
        dg = pr.get("ic_degradation", {}) or {}
        csv_rows.append({
            "horizon_days": h,
            "data": "OOS",
            "n_obs": pr.get("n_observations", 0),
            "ic_rank": (pr.get("gross") or {}).get("ic_rank"),
            "ic_pearson": (pr.get("gross") or {}).get("ic_pearson"),
            "hit_rate_gross": (pr.get("gross") or {}).get("hit_rate"),
            "mean_ret_pct_gross": (pr.get("gross") or {}).get("mean_return_pct"),
            "quintile_spread_gross": (pr.get("gross") or {}).get("quintile_spread"),
            "hit_rate_net": (pr.get("net") or {}).get("hit_rate_net"),
            "mean_ret_pct_net": (pr.get("net") or {}).get("mean_return_pct_net"),
            "ic_full_abs": dg.get("ic_full_abs"),
            "ic_oos_abs": dg.get("ic_oos_abs"),
            "ic_degradation_ratio": dg.get("ratio"),
            "ic_rank_abs_min": tr_dict.get("ic_rank_abs_min", ""),
            "ic_pearson_min": tr_dict.get("ic_pearson_min", ""),
            "quintile_spread": tr_dict.get("quintile_spread_annualized_pct_min", ""),
            "hit_rate_monotonic": tr_dict.get("hit_rate_monotonic_or_delta", ""),
            "cost_impact": tr_dict.get("cost_impact_min_pct", ""),
            "n_obs_min": tr_dict.get("n_obs_min", ""),
            "ic_degradation": tr_dict.get("ic_degradation_warning", ""),
            "verdict": pr.get("verdict", ""),
        })
    csv_path = out_dir / "validation_summary.csv"
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"CSV summary: {csv_path}")

    # ── Terminal summary ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"VALIDATION REPORT — OOS ONLY (as_of > {cutoff})")
    print(f"Verdicts based EXCLUSIVELY on OOS data")
    print(f"{'='*70}")

    for h in horizons:
        pr = oos_results.get(h)
        if not pr:
            continue
        print(f"\n── Horizon {h}d (OOS) ──")
        print(f"  n_obs:     {pr['n_observations']}")
        g = pr.get("gross") or {}
        print(f"  IC rank:   {g.get('ic_rank', 'N/A'):.4f}" if g.get("ic_rank") is not None else "  IC rank:   N/A")
        print(f"  IC Pearson:{g.get('ic_pearson', 'N/A'):.4f}" if g.get("ic_pearson") is not None else "  IC Pearson: N/A")
        print(f"  Hit rate:  {g.get('hit_rate', 0):.4f} | Mean ret%: {g.get('mean_return_pct', 0):.4f}")
        print(f"  Q5-Q1%:    {g.get('quintile_spread', 'N/A')}")
        n = pr.get("net") or {}
        if n.get("hit_rate_net") is not None:
            print(f"  Hit rate net: {n['hit_rate_net']:.4f} | Mean ret% net: {n.get('mean_return_pct_net', 0):.4f}")

        dg = pr.get("ic_degradation") or {}
        if dg.get("ratio") is not None:
            icon = "!!" if dg.get("ratio", 1.0) < ACCEPTANCE_THRESHOLDS["degradation_warning_ratio"] else ""
            print(f"  IC degradation: |IC_oos|/|IC_full| = {dg['ratio']:.4f} {icon}")
            print(f"    IC full={dg.get('ic_full_abs', 'N/A')}, IC oos={dg.get('ic_oos_abs', 'N/A')}")

        print(f"\n  Threshold results (OOS):")
        for t in pr.get("threshold_results", []):
            icon = {"PASS": "\u2713", "FAIL": "\u2717", "INSUFFICIENT_DATA": "?"}.get(t["result"], "?")
            v = t.get("value")
            if isinstance(v, dict):
                v = str(v)[:60] + ("..." if len(str(v)) > 60 else "")
            else:
                v = f"{v:.4f}" if isinstance(v, float) else str(v)
            print(f"    {icon} {t['criterion']}: {v} (threshold: {t['threshold']})")
        print(f"\n  Verdict: {pr['verdict']} — {pr['verdict_reason']}")

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Overall verdict (OOS only): {overall}")
    print(f"Horizons with predictive_evidence: {oos_pass}/{len(horizons)}")
    print(f"Warning: full-period metrics in pooled_full_reference are INFLATED")
    print(f"Elapsed: {elapsed:.1f}s")
    print(f"Reports: {out_dir}/")


if __name__ == "__main__":
    main()
