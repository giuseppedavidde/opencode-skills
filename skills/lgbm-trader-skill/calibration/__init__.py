"""Score-to-probability calibration via isotonic regression.

P1 August 2026: converts LGBM scores (0-100) into calibrated probabilities
using isotonic regression (preferred over Platt for non-monotonic signals).
Strictly requires:
- Temporal split: train/calibration and OOS test sets with non-overlapping
  date ranges.
- Minimum sample sizes for calibration and OOS.
- Evaluates OOS only — never reports metrics on calibration data.
- Saves/loads artifact as reproducible JSON.

The score 0-100 is NOT automatically interpreted as probability:
LGBMResult.calibrated_probability is None until a calibration artifact
is loaded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class CalibrationStatus(str, Enum):
    """Calibration pipeline status."""

    NOT_CALIBRATED = "not_calibrated"
    CALIBRATED = "calibrated"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class CalibrationMetrics(BaseModel):
    """OOS calibration evaluation metrics.

    All metrics are computed on the TEST set only, never on
    calibration data. The bias-variance decomposition ensures
    the reliability check uses OOS data exclusively.
    """

    n_fit: int = 0
    n_calibration: int = 0
    n_oos: int = 0
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    ece: Optional[float] = None
    reliability_bins: list[dict] = Field(default_factory=list)
    score_range: tuple[float, float] = (0.0, 100.0)
    calibration_error: Optional[float] = None
    model_version: str = ""


class CalibrationArtifact(BaseModel):
    """Serializable calibration artifact.

    Stores the isotonic regression state (X thresholds, Y values)
    and metadata for reproducibility.

    Attributes:
        ticker: Stock ticker (or "cross_sectional" for pooled).
        status: Pipeline status.
        isotonic_X: Thresholds for isotonic regressor (score values).
        isotonic_Y: Calibrated probabilities for each threshold.
        metrics: OOS evaluation metrics.
        calibration_start: First date in calibration set.
        calibration_end: Last date in calibration set.
        oos_start: First date in OOS test set.
        oos_end: Last date in OOS test set.
        created_at: ISO timestamp of artifact creation.
        notes: Human-readable limitations/warnings.
    """

    ticker: str
    status: CalibrationStatus = CalibrationStatus.NOT_CALIBRATED
    isotonic_X: list[float] = Field(default_factory=list)
    isotonic_Y: list[float] = Field(default_factory=list)
    metrics: CalibrationMetrics = Field(default_factory=CalibrationMetrics)
    calibration_start: Optional[str] = None
    calibration_end: Optional[str] = None
    oos_start: Optional[str] = None
    oos_end: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_isotonic_arrays(self) -> "CalibrationArtifact":
        if len(self.isotonic_X) != len(self.isotonic_Y):
            raise ValueError(
                f"isotonic_X ({len(self.isotonic_X)}) and isotonic_Y "
                f"({len(self.isotonic_Y)}) must have equal length"
            )
        if self.isotonic_X and self.isotonic_X != sorted(self.isotonic_X):
            raise ValueError("isotonic_X must be monotonically non-decreasing")
        return self

    def calibrate(self, score: float) -> Optional[float]:
        """Map a raw score to calibrated probability.

        Uses linear interpolation between isotonic_X thresholds.
        Clamps to [isotonic_Y[0], isotonic_Y[-1]].
        Returns None if not calibrated.
        """
        if self.status != CalibrationStatus.CALIBRATED:
            return None
        if not self.isotonic_X:
            return None
        if score <= self.isotonic_X[0]:
            return self.isotonic_Y[0]
        if score >= self.isotonic_X[-1]:
            return self.isotonic_Y[-1]
        idx = np.searchsorted(self.isotonic_X, score) - 1
        idx = max(0, min(idx, len(self.isotonic_X) - 2))
        x0, x1 = self.isotonic_X[idx], self.isotonic_X[idx + 1]
        y0, y1 = self.isotonic_Y[idx], self.isotonic_Y[idx + 1]
        if x1 == x0:
            return y0
        t = (score - x0) / (x1 - x0)
        return round(float(y0 + t * (y1 - y0)), 6)

    def save(self, path: str | Path) -> Path:
        """Save artifact as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, default=str)
        logger.info("Calibration artifact saved to %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationArtifact":
        """Load artifact from JSON."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Calibration artifact not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)


# ── Minimum sample size constants ──────────────────────────────────────

_MIN_CALIBRATION_SAMPLES: int = 100
_MIN_OOS_SAMPLES: int = 50


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Brier score: mean squared error between probability and outcome."""
    return float(np.mean((y_prob - y_true) ** 2))


def compute_log_loss(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Binary cross-entropy / log loss."""
    eps = 1e-15
    y_prob = np.clip(y_prob, eps, 1.0 - eps)
    return float(-np.mean(y_true * np.log(y_prob) + (1 - y_true) * np.log(1 - y_prob)))


def compute_ece(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> tuple[float, list[dict]]:
    """Expected Calibration Error and reliability bins.

    Args:
        y_true: Binary outcomes (0/1).
        y_prob: Predicted probabilities.
        n_bins: Number of equal-width bins.

    Returns:
        (ece, reliability_bins) where ece is the weighted average
        of |accuracy - confidence| across bins.
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_results: list[dict] = []
    ece_sum = 0.0

    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if i == n_bins - 1:
            mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        n_bin = int(np.sum(mask))
        if n_bin == 0:
            bin_results.append({
                "bin_start": round(float(bins[i]), 3),
                "bin_end": round(float(bins[i + 1]), 3),
                "count": 0,
                "accuracy": None,
                "avg_confidence": None,
                "gap": None,
            })
            continue
        accuracy = float(np.mean(y_true[mask]))
        avg_conf = float(np.mean(y_prob[mask]))
        gap = abs(accuracy - avg_conf)
        ece_sum += (n_bin / len(y_true)) * gap
        bin_results.append({
            "bin_start": round(float(bins[i]), 3),
            "bin_end": round(float(bins[i + 1]), 3),
            "count": n_bin,
            "accuracy": round(accuracy, 4),
            "avg_confidence": round(avg_conf, 4),
            "gap": round(gap, 4),
        })

    return round(ece_sum, 6), bin_results


def calibrate_isotonic(
    scores: np.ndarray,
    labels: np.ndarray,
    dates: list[str],
    calibration_end_date: str,
    min_calibration: int = _MIN_CALIBRATION_SAMPLES,
    min_oos: int = _MIN_OOS_SAMPLES,
    ticker: str = "UNKNOWN",
    model_version: str = "",
) -> CalibrationArtifact:
    """Calibrate scores → probabilities using isotonic regression.

    Uses strict temporal split:
    - Calibration set: dates <= calibration_end_date
    - OOS test set: dates > calibration_end_date

    The isotonic regressor is fit ONLY on the calibration set.
    All evaluation metrics refer to the OOS test set.

    Args:
        scores: Array of raw scores (0-100).
        labels: Binary outcomes (0/1, e.g. forward return > 0).
        dates: ISO date strings aligned with scores/labels.
        calibration_end_date: Last date included in calibration (YYYY-MM-DD).
        min_calibration: Minimum samples in calibration set.
        min_oos: Minimum samples in OOS test set.
        ticker: Ticker label for the artifact.
        model_version: Version string of the score-producing model.

    Returns:
        CalibrationArtifact (status=CALIBRATED on success).
    """
    from sklearn.isotonic import IsotonicRegression

    n_total = len(scores)
    if n_total < min_calibration + min_oos:
        return CalibrationArtifact(
            ticker=ticker,
            status=CalibrationStatus.INSUFFICIENT_DATA,
            metrics=CalibrationMetrics(
                n_fit=0,
                n_calibration=0,
                n_oos=n_total,
                model_version=model_version,
            ),
            notes=[
                f"Total samples ({n_total}) < required "
                f"(calibration={min_calibration} + oos={min_oos})"
            ],
        )

    scores_arr = np.asarray(scores, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    dates_arr = np.array(dates, dtype=object)

    cal_mask = dates_arr <= calibration_end_date
    oos_mask = dates_arr > calibration_end_date

    cal_scores = scores_arr[cal_mask]
    cal_labels = labels_arr[cal_mask]
    oos_scores = scores_arr[oos_mask]
    oos_labels = labels_arr[oos_mask]

    if len(cal_scores) < min_calibration:
        cal_dates = sorted(dates_arr[cal_mask]) if cal_mask.any() else []
        return CalibrationArtifact(
            ticker=ticker,
            status=CalibrationStatus.INSUFFICIENT_DATA,
            metrics=CalibrationMetrics(
                n_fit=0,
                n_calibration=int(len(cal_scores)),
                n_oos=int(len(oos_scores)),
                model_version=model_version,
            ),
            calibration_start=cal_dates[0] if cal_dates else None,
            calibration_end=calibration_end_date,
            notes=[
                f"Calibration samples ({len(cal_scores)}) < required "
                f"({min_calibration})"
            ],
        )

    if len(oos_scores) < min_oos:
        cal_dates = sorted(dates_arr[cal_mask]) if cal_mask.any() else []
        return CalibrationArtifact(
            ticker=ticker,
            status=CalibrationStatus.INSUFFICIENT_DATA,
            metrics=CalibrationMetrics(
                n_fit=int(len(cal_scores)),
                n_calibration=int(len(cal_scores)),
                n_oos=int(len(oos_scores)),
                model_version=model_version,
            ),
            calibration_start=cal_dates[0] if cal_dates else None,
            calibration_end=calibration_end_date,
            notes=[
                f"OOS test samples ({len(oos_scores)}) < required "
                f"({min_oos})"
            ],
        )

    # Fit isotonic regression on calibration set
    iso = IsotonicRegression(
        y_min=0.0,
        y_max=1.0,
        increasing=True,
        out_of_bounds="clip",
    )
    iso.fit(cal_scores, cal_labels)

    # Predict on OOS only
    oos_probs = iso.predict(oos_scores)

    # Metrics on OOS
    brier = compute_brier_score(oos_labels, oos_probs)
    logloss = compute_log_loss(oos_labels, oos_probs)
    ece, reliability_bins = compute_ece(oos_labels, oos_probs)
    cal_error = float(np.mean(oos_probs) - np.mean(oos_labels))

    # Extract isotonic thresholds
    iso_X = (
        iso.X_thresholds_.tolist()
        if hasattr(iso, "X_thresholds_")
        else sorted(set(cal_scores))  # type: ignore[union-attr]
    )
    iso_Y = (
        iso.Y_thresholds_.tolist()
        if hasattr(iso, "Y_thresholds_")
        else iso.predict(iso_X)  # type: ignore[union-attr]
    )

    cal_dates_subset = sorted(dates_arr[cal_mask]) if cal_mask.any() else []
    oos_dates_subset = sorted(dates_arr[oos_mask]) if oos_mask.any() else []

    return CalibrationArtifact(
        ticker=ticker,
        status=CalibrationStatus.CALIBRATED,
        isotonic_X=(
            list(iso_X) if isinstance(iso_X, np.ndarray)
            else iso_X  # type: ignore[arg-type]
        ),
        isotonic_Y=(
            list(iso_Y) if isinstance(iso_Y, np.ndarray)
            else iso_Y  # type: ignore[arg-type]
        ),
        metrics=CalibrationMetrics(
            n_fit=int(len(cal_scores)),
            n_calibration=int(len(cal_scores)),
            n_oos=int(len(oos_scores)),
            brier_score=round(brier, 6),
            log_loss=round(logloss, 6),
            ece=ece,
            reliability_bins=reliability_bins,
            score_range=(float(scores_arr.min()), float(scores_arr.max())),
            calibration_error=round(cal_error, 6),
            model_version=model_version,
        ),
        calibration_start=cal_dates_subset[0] if cal_dates_subset else None,
        calibration_end=calibration_end_date,
        oos_start=oos_dates_subset[0] if oos_dates_subset else None,
        oos_end=oos_dates_subset[-1] if oos_dates_subset else None,
        notes=[
            "Isotonic regression on temporal calibration split",
            "OOS evaluation only — no metrics on calibration data",
            "Non-ticker-specific: VRP slope is S&P 500 empirical; "
            "ticker-specific requires delta-hedged P&L history",
        ],
    )
