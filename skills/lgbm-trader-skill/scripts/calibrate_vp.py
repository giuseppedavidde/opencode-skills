#!/usr/bin/env python3
"""Calibrate VP signal scores → hit probabilities with honest 3-level gate.

Loads prediction export, applies explicit temporal split, fits isotonic
regression, then classifies the calibration via a-priori gate (Brier vs naive,
Spearman IC with p-value, ECE, n_OOS).

Gate levels:
  calibrated:      Brier < Brier_naive, n_OOS >= 5000, |IC| >= 0.03, p<0.01, ECE <= 0.05
  weak_calibrated: Brier < Brier_naive + 0.01, n_OOS >= 1000, |IC| >= 0.015, p<0.05, ECE <= 0.10
  not_calibrated:  otherwise (explicit reasons per failed criterion)

For weak_calibrated, empirical bucket hit rates + base_rate + shrinkage
are stored instead of the isotonic curve, because the curve is unreliable.

ALL metrics are computed ONLY on OOS. Never on calibration data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

# ── Gate constants (a-priori, documentate) ─────────────────────────────

_CALIBRATED = {
    "n_oos_min": 5000,
    "ic_min": 0.03,
    "ic_p_max": 0.01,
    "ece_max": 0.05,
    "brier_naive_margin": 0.0,   # Brier < naive (strict)
}

_WEAK_CALIBRATED = {
    "n_oos_min": 1000,
    "ic_min": 0.015,
    "ic_p_max": 0.05,
    "ece_max": 0.10,
    "brier_naive_margin": 0.01,  # Brier < naive + 0.01 (relaxed)
    "default_shrinkage": 0.40,
    "n_buckets": 6,
}


def load_predictions(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required_cols = [
        "ticker", "as_of", "signal_score", "horizon_days",
        "forward_return", "forward_price",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df


def compute_empirical_buckets(
    scores: np.ndarray,
    labels: np.ndarray,
    n_buckets: int = 6,
) -> list[dict]:
    """Compute raw hit rates in equal-width score buckets (OOS only)."""
    if len(scores) < n_buckets * 2:
        return []
    edges = np.linspace(scores.min(), scores.max(), n_buckets + 1)
    buckets = []
    for i in range(n_buckets):
        mask = (scores >= edges[i]) & (
            (scores < edges[i + 1]) if i < n_buckets - 1
            else (scores <= edges[i + 1])
        )
        n = int(mask.sum())
        if n == 0:
            continue
        hit_rate = float(np.mean(labels[mask]))
        buckets.append({
            "score_low": round(float(edges[i]), 1),
            "score_high": round(float(edges[i + 1]), 1),
            "n": n,
            "hit_rate_raw": round(hit_rate, 4),
        })
    return buckets


def _evaluate_gate(
    brier_cal: float,
    brier_naive: float,
    n_oos: int,
    ic_rank: float | None,
    ic_p: float | None,
    ece: float | None,
) -> tuple[str, list[dict]]:
    """Apply a-priori gate and return (status, warnings).

    Each criterion is evaluated against both strict (calibrated) and
    relaxed (weak_calibrated) thresholds. Status is the highest level
    where ALL criteria pass.
    """
    warnings: list[dict] = []
    ece_val = ece if ece is not None else 1.0
    brier_gap = brier_cal - brier_naive

    def _add_w(code: str, severity: str, msg: str) -> None:
        warnings.append({"code": code, "severity": severity, "message": msg})

    # ── Evaluate each criterion independently ─────────────────────
    strict: dict[str, bool] = {}
    weak: dict[str, bool] = {}

    # Brier vs naive
    strict["brier"] = brier_gap < _CALIBRATED["brier_naive_margin"]
    weak["brier"] = brier_gap < _WEAK_CALIBRATED["brier_naive_margin"]
    if not strict["brier"]:
        _add_w("W1_BRIER_MARGINAL" if weak["brier"] else "W1_BRIER_WORSE",
               "critical" if not weak["brier"] else "medium",
               f"Isotonic Brier ({brier_cal:.4f}) "
               f"{'worse' if not weak['brier'] else 'marginally worse'} "
               f"than naive ({brier_naive:.4f}) Δ={brier_gap:+.6f}")

    # n_OOS
    strict["n"] = n_oos >= _CALIBRATED["n_oos_min"]
    weak["n"] = n_oos >= _WEAK_CALIBRATED["n_oos_min"]
    if not weak["n"]:
        _add_w("W0_INSUFFICIENT_OOS", "critical",
               f"n_OOS={n_oos} < {_WEAK_CALIBRATED['n_oos_min']}")

    # Spearman IC
    if ic_rank is None:
        strict["ic"] = False
        weak["ic"] = False
        _add_w("W2_IC_UNDEFINED", "high",
               "Spearman IC rank undefined — degenerate data")
    else:
        strict["ic"] = abs(ic_rank) >= _CALIBRATED["ic_min"]
        weak["ic"] = abs(ic_rank) >= _WEAK_CALIBRATED["ic_min"]
        if ic_p is not None:
            if ic_p >= _CALIBRATED["ic_p_max"]:
                strict["ic"] = False
            if ic_p >= _WEAK_CALIBRATED["ic_p_max"]:
                weak["ic"] = False
                _add_w("W2_IC_NOT_SIGNIFICANT", "high",
                       f"IC p={ic_p:.4f} >= {_WEAK_CALIBRATED['ic_p_max']}")
        if not weak["ic"] and strict.get("ic") is not True:
            _add_w("W2_IC_WEAK", "high",
                   f"|IC|={abs(ic_rank):.4f} < {_WEAK_CALIBRATED['ic_min']} "
                   f"— signal may flip sign")

    # ECE
    strict["ece"] = ece_val <= _CALIBRATED["ece_max"]
    weak["ece"] = ece_val <= _WEAK_CALIBRATED["ece_max"]
    if not weak["ece"]:
        _add_w("W3_ECE_HIGH", "high",
               f"ECE {ece_val:.4f} > {_WEAK_CALIBRATED['ece_max']} "
               f"— isotonic overconfident")

    # ── Regime/heterogeneity warnings (always added) ─────────────
    _add_w("W4_REGIME_DEPENDENT", "medium",
           "VP signal is regime-dependent: flips sign between quarters "
           "and across tickers. Do not use standalone in strong trends. "
           "Calibrated hit rates are pooled cross-sectional averages, "
           "NOT per-ticker guarantees.")
    _add_w("W5_HETEROGENEITY", "medium",
           "Cross-sectional pooling masks per-ticker heterogeneity. "
           "Bucket hit rates are averages across 50 tickers; individual "
           "ticker outcomes may differ materially.")
    _add_w("W6_OVERCONFIDENCE", "medium",
           "Isotonic regression overestimates probabilities by 6-12pp "
           "in the most populated buckets. Use empirical bucket rates "
           "with shrinkage for operational decisions.")
    _add_w("W7_HORIZON", "low",
           "Calibration is on 180-day horizon only. Shorter horizons "
           "show weaker signal discrimination.")

    # ── Determine status: highest level with ALL criteria passing ─
    all_strict = all(strict.values())
    all_weak = all(weak.values())

    if all_strict:
        return "calibrated", warnings
    if all_weak:
        return "weak_calibrated", warnings

    # Build failure reason
    failed_strict = [k for k, v in strict.items() if not v]
    failed_weak = [k for k, v in weak.items() if not v]
    reason = f"Failed criteria: strict={failed_strict}, weak={failed_weak}"
    _add_w("W8_NOT_CALIBRATED", "critical", reason)
    return "not_calibrated", warnings


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate VP score → hit probability (honest 3-level gate)"
    )
    parser.add_argument("--predictions", required=True, help="Predictions CSV")
    parser.add_argument(
        "--output",
        default=str(Path.home() / ".config/opencode/calibrations/vp_calibration.json"),
        help="Output path for calibration artifact",
    )
    parser.add_argument("--cutoff", default="2024-06-30", help="YYYY-MM-DD")
    parser.add_argument("--min-calibration", type=int, default=500)
    parser.add_argument("--min-oos", type=int, default=300)
    parser.add_argument("--horizon", type=int, default=None)
    parser.add_argument("--shrinkage", type=float, default=_WEAK_CALIBRATED["default_shrinkage"])
    args = parser.parse_args()

    print(f"Loading predictions from: {args.predictions}")
    df = load_predictions(args.predictions)
    print(f"  Loaded {len(df)} predictions from {df['ticker'].nunique()} tickers")

    if args.horizon is not None:
        horizon = args.horizon
    else:
        horizon_counts = df.groupby("horizon_days").size()
        horizon = int(horizon_counts.idxmax())
    print(f"  Using horizon: {horizon}d")

    df_h = df[df["horizon_days"] == horizon].copy()
    df_h["label"] = (df_h["forward_return"] > 0).astype(int)

    n_total = len(df_h)
    print(f"\nDataset: {n_total} predictions")
    print(f"  Label: {df_h['label'].mean()*100:.1f}% positive")
    print(f"  Score range: [{df_h['signal_score'].min():.1f}, {df_h['signal_score'].max():.1f}]")

    cutoff = args.cutoff
    cal_mask = df_h["as_of"] <= cutoff
    oos_mask = df_h["as_of"] > cutoff
    cal_df = df_h[cal_mask]
    oos_df = df_h[oos_mask]

    print(f"\nTemporal split: calibration ≤ {cutoff}, OOS > {cutoff}")
    print(f"  Calibration: {len(cal_df)}")
    print(f"  OOS:         {len(oos_df)}")

    # ── Gate dictionary ──────────────────────────────────────────
    gate = {
        "calibrated_thresholds": _CALIBRATED,
        "weak_calibrated_thresholds": _WEAK_CALIBRATED,
        "description": (
            "A-priori gate applied BEFORE fit. 'calibrated' requires all: "
            "Brier < naive, n_OOS>=5000, |IC|>=0.03 p<0.01, ECE<=0.05. "
            "'weak_calibrated' requires: Brier < naive+0.01, n_OOS>=1000, "
            "|IC|>=0.015 p<0.05, ECE<=0.10. Otherwise 'not_calibrated'."
        ),
    }

    # ── Check basic sufficiency ──────────────────────────────────
    if len(cal_df) < args.min_calibration:
        artifact = {
            "ticker": "cross_sectional_vp",
            "status": "insufficient_data",
            "horizon_days": horizon,
            "n_total": n_total,
            "n_cal": int(len(cal_df)),
            "n_oos": int(len(oos_df)),
            "cutoff": cutoff,
            "reason": f"n_cal={len(cal_df)} < {args.min_calibration}",
            "gate": gate,
            "warnings": [],
        }
    elif len(oos_df) < args.min_oos:
        artifact = {
            "ticker": "cross_sectional_vp",
            "status": "insufficient_data",
            "horizon_days": horizon,
            "n_total": n_total,
            "n_cal": int(len(cal_df)),
            "n_oos": int(len(oos_df)),
            "cutoff": cutoff,
            "reason": f"n_oos={len(oos_df)} < {args.min_oos}",
            "gate": gate,
            "warnings": [],
        }
    else:
        # ── Fit isotonic ────────────────────────────────────────────
        from calibration import calibrate_isotonic, CalibrationStatus

        inverted_all = 100.0 - df_h["signal_score"].to_numpy()
        print(f"  Inverted score range: [{inverted_all.min():.1f}, {inverted_all.max():.1f}]")

        cal_artifact = calibrate_isotonic(
            scores=inverted_all,
            labels=df_h["label"].to_numpy(),
            dates=df_h["as_of"].tolist(),
            calibration_end_date=cutoff,
            min_calibration=args.min_calibration,
            min_oos=args.min_oos,
            ticker="cross_sectional_vp",
            model_version=f"vp_canonical_365d_h{horizon}d",
        )

        brier_cal = cal_artifact.metrics.brier_score or 1.0
        ece_cal = cal_artifact.metrics.ece or 1.0
        n_oos = cal_artifact.metrics.n_oos

        # ── Naive baseline (base rate on OOS) ──────────────────────
        oos_inverted = inverted_all[oos_mask.values]
        oos_labels = df_h["label"].to_numpy()[oos_mask.values]
        base_rate_oos = float(np.mean(oos_labels))
        brier_naive = float(np.mean((oos_labels - base_rate_oos) ** 2))

        # ── Spearman IC STRICTLY on OOS (not cal, not full) ────────
        # Uses inverted score (100-VP) so that IC sign is coherent
        # with the gate: positive IC means higher score → higher hit_rate.
        # The gate applies |IC|, so sign convention does not matter.
        # Never computed on cal+OOS together — that would leak
        # calibration data into the gate evaluation.
        ic_rank_oos, ic_p_oos = spearmanr(oos_inverted, oos_labels)
        ic_rank_oos = float(ic_rank_oos) if np.isfinite(ic_rank_oos) else None
        ic_p_oos = float(ic_p_oos) if ic_p_oos is not None and np.isfinite(ic_p_oos) else None

        # ── Empirical buckets on OOS (inverted score) ──────────────
        bucket_hit_rates = compute_empirical_buckets(
            oos_inverted, oos_labels, n_buckets=_WEAK_CALIBRATED["n_buckets"]
        )

        # ── Apply gate ──────────────────────────────────────────────
        status, warnings = _evaluate_gate(
            brier_cal=brier_cal,
            brier_naive=brier_naive,
            n_oos=n_oos,
            ic_rank=ic_rank_oos,
            ic_p=ic_p_oos,
            ece=ece_cal,
        )

        # ── Build artifact ──────────────────────────────────────────
        artifact = {
            "ticker": "cross_sectional_vp",
            "status": status,
            "horizon_days": horizon,
            "cutoff": cutoff,
            "model_version": f"vp_canonical_365d_h{horizon}d",
            "label_definition": "forward_return > 0",
            "inverted": True,
            "inverted_note": "Score is 100 - VP; isotonic requires increasing relationship",
            "ic_definition": (
                "Spearman rank correlation between inverted score (100−VP) and "
                "binary label (forward_return > 0) computed STRICTLY on OOS "
                f"(as_of > {cutoff}, n={n_oos}). Positive IC means higher "
                "inverted score → higher hit rate, consistent with mean-reversion "
                "(low VP → buy → higher hit rate). Gate uses |IC|."
            ),
            "n_cal": int(len(cal_df)),
            "n_oos": n_oos,
            "n_total": n_total,
            "n_tickers": int(df["ticker"].nunique()),
            "base_rate_oos": round(base_rate_oos, 4),
            "brier_naive": round(brier_naive, 6),
            "brier_cal": round(brier_cal, 6),
            "ece": round(ece_cal, 6) if ece_cal is not None else None,
            "ic_rank_oos": round(ic_rank_oos, 6) if ic_rank_oos is not None else None,
            "ic_p_value": round(ic_p_oos, 6) if ic_p_oos is not None else None,
            "gate": gate,
            "warnings": warnings,
            "notes": [
                f"VP calibration on {df['ticker'].nunique()} tickers, "
                f"horizon {horizon}d, pooled cross-sectional",
                f"All metrics computed STRICTLY on OOS (>{cutoff})",
                "Brier_naive = predicting constant base rate on OOS",
                "Spearman IC computed on OOS inverted score (100−VP) — no leakage",
            ],
        }

        # strong_calibrated → include isotonic curve
        if status == "calibrated":
            artifact["isotonic_X"] = cal_artifact.isotonic_X
            artifact["isotonic_Y"] = cal_artifact.isotonic_Y
            cal_notes = artifact.get("notes", [])
            cal_notes.append(
                "Isotonic curve passed all 4 a-priori gates — "
                "usable for hit_rate_calibrated lookup (with 100−VP inversion)"
            )

        # weak_calibrated → include empirical buckets, NOT isotonic
        elif status == "weak_calibrated":
            artifact["bucket_hit_rates"] = bucket_hit_rates
            artifact["shrinkage"] = args.shrinkage
            artifact["hit_rate_source"] = "bucket_empirical_shrunk"
            artifact["hit_rate_note"] = (
                f"hit_rate = base_rate + shrinkage * (bucket_raw - base_rate). "
                f"Shrinkage={args.shrinkage} towards base_rate_oos={base_rate_oos:.4f}. "
                f"Buckets are on INVERTED score (100 - VP). "
                f"The isotonic curve is NOT used (overconfident)."
            )
            cal_notes = artifact.get("notes", [])
            cal_notes.append(
                "Isotonic curve overestimates probabilities — "
                "empirical bucket rates with shrinkage used instead"
            )
            artifact["notes"] = cal_notes

        # not_calibrated / insufficient → reasons already in warnings
        else:
            if "reason" not in artifact:
                reasons_text = "; ".join(
                    w["message"] for w in warnings if w["severity"] == "critical"
                )
                artifact["reason"] = reasons_text or "Gate criteria not met"

        # reliability bins
        if cal_artifact.metrics.reliability_bins:
            artifact["reliability_bins"] = cal_artifact.metrics.reliability_bins

        # ── Print report ────────────────────────────────────────────
        print(f"\n{'='*70}")
        print(f"GATE EVALUATION (a-priori, all metrics on OOS)")
        print(f"{'='*70}")
        print(f"  n_cal:        {len(cal_df)}")
        print(f"  n_oos:        {n_oos}")
        print(f"  base_rate:    {base_rate_oos:.4f}")
        print(f"  Brier_naive:  {brier_naive:.6f}")
        print(f"  Brier_cal:    {brier_cal:.6f} (Δ={brier_cal-brier_naive:+.6f})")
        print(f"  IC rank (OOS inv): {ic_rank_oos:.4f}" if ic_rank_oos is not None else "  IC rank:      None")
        print(f"  IC p-value:   {ic_p_oos:.6f}" if ic_p_oos is not None else "  IC p-value:   None")
        print(f"  ECE:          {ece_cal:.6f}" if ece_cal is not None else "  ECE:          None")
        print(f"\n  Criteria for calibrated:")
        print(f"    Brier < naive:       {brier_cal < brier_naive}")
        print(f"    n_OOS >= 5000:       {n_oos >= _CALIBRATED['n_oos_min']}")
        print(f"    |IC| >= 0.03:        {abs(ic_rank_oos) >= _CALIBRATED['ic_min'] if ic_rank_oos else 'N/A'}")
        print(f"    p < 0.01:            {ic_p_oos < _CALIBRATED['ic_p_max'] if ic_p_oos else 'N/A'}")
        print(f"    ECE <= 0.05:         {ece_cal <= _CALIBRATED['ece_max'] if ece_cal else 'N/A'}")
        print(f"\n  Criteria for weak_calibrated:")
        print(f"    Brier < naive+0.01:  {brier_cal < brier_naive + _WEAK_CALIBRATED['brier_naive_margin']}")
        print(f"    n_OOS >= 1000:       {n_oos >= _WEAK_CALIBRATED['n_oos_min']}")
        print(f"    |IC| >= 0.015:       {abs(ic_rank_oos) >= _WEAK_CALIBRATED['ic_min'] if ic_rank_oos else 'N/A'}")
        print(f"    p < 0.05:            {ic_p_oos < _WEAK_CALIBRATED['ic_p_max'] if ic_p_oos else 'N/A'}")
        print(f"    ECE <= 0.10:         {ece_cal <= _WEAK_CALIBRATED['ece_max'] if ece_cal else 'N/A'}")
        print(f"\n  ==> FINAL STATUS: {status}")

        if status in ("calibrated", "weak_calibrated") and warnings:
            print(f"\n  Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"    [{w['severity']:>8}] {w['code']}: {w['message']}")

        if status == "weak_calibrated" and bucket_hit_rates:
            print(f"\n  Empirical buckets (OOS, inverted score, shrunk to base={base_rate_oos:.4f}):")
            print(f"  {'Score':>12} {'n':>6} {'Raw':>8} {'Shrunk':>8}")
            print(f"  {'-'*40}")
            for b in bucket_hit_rates:
                raw = b["hit_rate_raw"]
                shrunk = base_rate_oos + args.shrinkage * (raw - base_rate_oos)
                print(f"  [{b['score_low']:5.1f}-{b['score_high']:5.1f}] "
                      f"{b['n']:>6} {raw:>8.4f} {shrunk:>8.4f}")

    # ── Save ──────────────────────────────────────────────────────
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2, default=str)
    print(f"\nArtifact saved: {out_path}")
    print(f"Status: {artifact.get('status', 'unknown')}")


if __name__ == "__main__":
    main()
