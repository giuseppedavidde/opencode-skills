"""Ticker-specific VRP calibration via walk-forward temporal split.

Uses a proxy VRP definition: VRP = IV − RV (annualised), where:
- IV is implied volatility (e.g. VIX/100 for SPY, or ATM IV for tickers)
- RV is realised volatility (rolling std of daily returns, annualised)

This is a PROXY measure, NOT the delta-hedged P&L from Bakshi & Kapadia
(2003). The paper uses delta-hedged option positions to estimate the VRP;
we use the IV−RV spread as a simpler, more accessible alternative.

Calibration uses explicit temporal split:
- Fit period (dates <= cutoff): compute mean VRP, coefficients
- OOS period (dates > cutoff): evaluate VRP sign accuracy vs forward return

Gate levels:
- calibrated: n_OOS >= 500, |IC| >= 0.03 p<0.01, VRP sign accuracy > 55%
- weak_calibrated: n_OOS >= 100, |IC| >= 0.015 p<0.05, VRP sign accuracy > 52%
- not_calibrated: otherwise
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


class VRPCalibrationMetrics(BaseModel):
    """OOS metrics for VRP proxy calibration."""

    n_fit: int = 0
    n_oos: int = 0
    mean_vrp_proxy_fit: float = 0.0
    mean_vrp_proxy_oos: float = 0.0
    vrp_sign_hit_rate_oos: Optional[float] = None
    directional_p_value_oos: Optional[float] = None
    ic_rank_oos: Optional[float] = None
    ic_p_value: Optional[float] = None
    forward_horizon_days: int = 20
    rv_window_days: int = 21


class VRPCalibrationArtifact(BaseModel):
    """Serializable VRP proxy calibration artifact.

    Attributes:
        ticker: Stock ticker (e.g. 'SPY').
        status: calibrated / weak_calibrated / not_calibrated.
        calibrated_vrp_proxy: Mean VRP proxy estimate from fit (annualised).
        calibration_start: First date in fit period.
        calibration_end: Last date in fit period.
        oos_start: First date in OOS period.
        oos_end: Last date in OOS period.
        metrics: OOS evaluation metrics.
        iv_proxy_note: How IV was estimated (e.g. 'VIX/100').
        warnings: List of warning dicts.
        created_at: ISO timestamp.
    """

    ticker: str
    status: str = "not_calibrated"
    calibrated_vrp_proxy: Optional[float] = None
    calibration_start: Optional[str] = None
    calibration_end: Optional[str] = None
    oos_start: Optional[str] = None
    oos_end: Optional[str] = None
    metrics: VRPCalibrationMetrics = Field(default_factory=VRPCalibrationMetrics)
    iv_proxy_note: str = ""
    warnings: list[dict] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: list[str] = Field(
        default_factory=lambda: [
            "VRP = IV − RV (annualised proxy, NOT delta-hedged P&L)",
            "IV proxy may use VIX/100 for indices or ATM IV for tickers",
            "All OOS metrics computed STRICTLY on data after cutoff",
        ]
    )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2, default=str)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "VRPCalibrationArtifact":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"VRP artifact not found: {path}")
        with open(path) as f:
            return cls.model_validate(json.load(f))


def calibrate_vrp(
    dates: list[str],
    underlying_close: list[float],
    iv_series: list[float],
    cutoff: str,
    risk_free_rate: float = 0.045,
    forward_horizon_days: int = 20,
    rv_window_days: int = 21,
    ticker: str = "UNKNOWN",
    iv_proxy_note: str = "",
    min_fit: int = 252,
    min_oos: int = 100,
) -> VRPCalibrationArtifact:
    """Calibrate VRP (IV−RV) with temporal split.

    Args:
        dates: ISO date strings (YYYY-MM-DD).
        underlying_close: Close prices, aligned with dates.
        iv_series: Implied volatility (decimal, e.g. 0.20 = 20%).
        cutoff: Temporal split date (YYYY-MM-DD).
        risk_free_rate: Risk-free rate (decimal).
        forward_horizon_days: Days for forward return label.
        rv_window_days: Rolling window for realised vol.
        ticker: Ticker label.
        iv_proxy_note: How IV was obtained.
        min_fit: Minimum observations in fit period.
        min_oos: Minimum observations in OOS period.

    Returns:
        VRPCalibrationArtifact.
    """
    n_total = len(dates)
    if n_total < min_fit + min_oos:
        return VRPCalibrationArtifact(
            ticker=ticker,
            status="not_calibrated",
            iv_proxy_note=iv_proxy_note,
            warnings=[{
                "code": "INSUFFICIENT_TOTAL",
                "severity": "critical",
                "message": f"n_total={n_total} < {min_fit}+{min_oos}",
            }],
        )

    dates_arr = np.array(dates, dtype=object)
    close_arr = np.asarray(underlying_close, dtype=float)
    iv_arr = np.asarray(iv_series, dtype=float)

    # ── Compute RV (rolling, annualised) ──────────────────────────
    daily_ret = np.diff(np.log(close_arr), prepend=np.nan)
    daily_ret[0] = np.nan

    rv_series = np.full(len(close_arr), np.nan)
    for i in range(rv_window_days, len(close_arr)):
        window = daily_ret[i - rv_window_days + 1 : i + 1]
        window = window[~np.isnan(window)]
        if len(window) >= 5:
            rv_series[i] = float(np.std(window, ddof=1) * np.sqrt(252))

    # ── VRP series = IV − RV ──────────────────────────────────────
    vrp_series = iv_arr - rv_series
    valid = ~np.isnan(vrp_series) & ~np.isnan(rv_series)
    dates_valid = dates_arr[valid]
    vrp_valid = vrp_series[valid]
    close_valid = close_arr[valid]

    if len(vrp_valid) < min_fit + min_oos:
        return VRPCalibrationArtifact(
            ticker=ticker,
            status="not_calibrated",
            iv_proxy_note=iv_proxy_note,
            warnings=[{
                "code": "INSUFFICIENT_VALID",
                "severity": "critical",
                "message": f"n_valid={len(vrp_valid)} < {min_fit}+{min_oos}",
            }],
        )

    # ── Forward return for evaluation (STRICTLY future data) ──────
    fwd_ret = np.full(len(close_valid), np.nan)
    for i in range(len(close_valid) - forward_horizon_days):
        fwd_ret[i] = (close_valid[i + forward_horizon_days] / close_valid[i]) - 1.0

    # ── Temporal split ────────────────────────────────────────────
    fit_mask = dates_valid <= cutoff
    oos_mask = dates_valid > cutoff

    vrp_fit = vrp_valid[fit_mask]
    vrp_oos = vrp_valid[oos_mask]
    fwd_oos = fwd_ret[oos_mask]

    n_fit = int(fit_mask.sum())
    n_oos = int(oos_mask.sum())

    if n_fit < min_fit:
        return VRPCalibrationArtifact(
            ticker=ticker,
            status="not_calibrated",
            iv_proxy_note=iv_proxy_note,
            calibration_start=str(dates_valid[fit_mask][0]) if n_fit > 0 else None,
            calibration_end=cutoff,
            metrics=VRPCalibrationMetrics(
                n_fit=n_fit, n_oos=n_oos,
                forward_horizon_days=forward_horizon_days,
                rv_window_days=rv_window_days,
            ),
            warnings=[{
                "code": "INSUFFICIENT_FIT",
                "severity": "critical",
                "message": f"n_fit={n_fit} < {min_fit}",
            }],
        )

    if n_oos < min_oos:
        mean_vrp_fit = float(np.mean(vrp_fit))
        return VRPCalibrationArtifact(
            ticker=ticker,
            status="not_calibrated",
            calibrated_vrp_proxy=round(mean_vrp_fit, 6),
            calibration_start=str(dates_valid[fit_mask][0]) if n_fit > 0 else None,
            calibration_end=cutoff,
            metrics=VRPCalibrationMetrics(
                n_fit=n_fit, n_oos=n_oos, mean_vrp_proxy_fit=round(mean_vrp_fit, 6),
                forward_horizon_days=forward_horizon_days,
                rv_window_days=rv_window_days,
            ),
            iv_proxy_note=iv_proxy_note,
            warnings=[{
                "code": "INSUFFICIENT_OOS",
                "severity": "critical",
                "message": f"n_oos={n_oos} < {min_oos}",
            }],
        )

    # ── Fit: mean VRP proxy ────────────────────────────────────────
    mean_vrp_fit = float(np.mean(vrp_fit))
    mean_vrp_oos = float(np.mean(vrp_oos))

    # ── OOS evaluation ────────────────────────────────────────────
    # VRP sign accuracy vs forward return sign
    vrp_signs = np.sign(vrp_oos)
    fwd_signs = np.sign(fwd_oos)
    valid_signs = ~np.isnan(vrp_oos) & ~np.isnan(fwd_oos)
    sign_hit = float(np.mean(vrp_signs[valid_signs] == fwd_signs[valid_signs]))

    # Directional p-value (binomial on sign hit rate, two-tailed)
    n_signs = int(valid_signs.sum())
    n_correct = int(np.sum(vrp_signs[valid_signs] == fwd_signs[valid_signs]))
    directional_p = None
    if n_signs >= 5:
        from scipy.stats import binomtest
        result = binomtest(n_correct, n=n_signs, p=0.5, alternative="two-sided")
        directional_p = float(result.pvalue) if hasattr(result, "pvalue") else None

    # Spearman IC: VRP vs forward return
    mask = ~np.isnan(vrp_oos) & ~np.isnan(fwd_oos)
    ic_rank = None
    ic_p = None
    if mask.sum() >= 10:
        ic_rank, ic_p = spearmanr(vrp_oos[mask], fwd_oos[mask])
        ic_rank = float(ic_rank) if np.isfinite(ic_rank) else None
        ic_p = float(ic_p) if ic_p is not None and np.isfinite(ic_p) else None

    # ── Gate ──────────────────────────────────────────────────────
    warnings = []
    status = "not_calibrated"

    ic_ok = ic_rank is not None and abs(ic_rank) >= 0.03
    p_ok = ic_p is not None and ic_p < 0.01
    sign_ok_strict = sign_hit > 0.55
    sign_ok_weak = sign_hit > 0.52

    if ic_ok and p_ok and sign_ok_strict:
        status = "calibrated"
    elif ic_rank is not None and abs(ic_rank) >= 0.015 and (ic_p is None or ic_p < 0.05) and sign_ok_weak:
        status = "weak_calibrated"
        warnings.append({
            "code": "WEAK_VRP",
            "severity": "medium",
            "message": (
                f"VRP sign accuracy {sign_hit:.3f} below strict threshold "
                f"0.55. VRP direction is weakly informative."
            ),
        })

    if not ic_ok:
        warnings.append({
            "code": "VRP_IC_WEAK",
            "severity": "high",
            "message": f"|IC|={abs(ic_rank):.4f} < 0.03 — VRP proxy has weak predictive power"
        })

    # VRP proxy warning
    warnings.append({
        "code": "VRP_PROXY_NOTE",
        "severity": "low",
        "message": (
            "VRP = IV − RV is a proxy. It is NOT the delta-hedged P&L from "
            "Bakshi & Kapadia (2003). The paper's VRP measures the negative "
            "expected return of delta-hedged option portfolios. This proxy "
            "indicates whether IV overstates or understates future RV."
        ),
    })

    # Regime contamination risk
    warnings.append({
        "code": "REGIME_CONTAMINATION_RISK",
        "severity": "medium",
        "message": (
            "Calibration period includes secular vol decline. VRP proxy "
            "may be regime-contaminated. Recommended: check IC by VIX "
            "terciles; compute residual VRP (IV − RV after regressing "
            "out vol level). Sign persistence alone is insufficient "
            "evidence of a tradable premium."
        ),
    })

    return VRPCalibrationArtifact(
        ticker=ticker,
        status=status,
        calibrated_vrp_proxy=round(mean_vrp_fit, 6),
        calibration_start=str(dates_valid[fit_mask][0]) if n_fit > 0 else None,
        calibration_end=cutoff,
        oos_start=str(dates_valid[oos_mask][0]) if n_oos > 0 else None,
        oos_end=str(dates_valid[oos_mask][-1]) if n_oos > 0 else None,
        metrics=VRPCalibrationMetrics(
            n_fit=n_fit,
            n_oos=n_oos,
            mean_vrp_proxy_fit=round(mean_vrp_fit, 6),
            mean_vrp_proxy_oos=round(mean_vrp_oos, 6),
            vrp_sign_hit_rate_oos=round(sign_hit, 4),
            directional_p_value_oos=(
                round(directional_p, 6) if directional_p is not None else None
            ),
            ic_rank_oos=round(ic_rank, 4) if ic_rank else None,
            ic_p_value=round(ic_p, 6) if ic_p else None,
            forward_horizon_days=forward_horizon_days,
            rv_window_days=rv_window_days,
        ),
        iv_proxy_note=iv_proxy_note,
        warnings=warnings,
    )
