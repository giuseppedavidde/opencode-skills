"""Append-only prediction log with deferred outcome resolution.

Every prediction is recorded with ``as_of``, ``model_version``, ``score``,
and ``horizon``. Forward outcomes are resolved later by ``resolve_outcome``
when future data becomes available — strictly without look-ahead.

``performance_report`` returns n_pending, n_resolved, hit rate, IC rank,
and Sharpe on resolved outcomes. If no outcomes are resolved, every metric
is None and ``status`` is ``insufficient_data``.

Overlap guard (P2.5): when predictions use overlapping forward windows
(horizon > interval between observations), the Sharpe ratio is inflated
by ~√overlap_factor. The report detects this and:
- Sets ``sharpe_annualized=None``, stores raw biased value as
  ``sharpe_biased_raw`` (diagnostic only).
- Adds ``overlap_factor`` and ``n_independent_estimate``.
- Adds a warning explaining the issue.
- Computes ``directional_p_value`` (binomial test on hit rate, two-tailed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from scipy.stats import binomtest, spearmanr

logger = logging.getLogger(__name__)


class PredictionRecord(BaseModel):
    """A single prediction log entry (one JSONL line)."""

    ticker: str
    as_of: str
    model_version: str
    score: float
    calibrated_probability: Optional[float] = None
    horizon_days: int = 20
    status: str = "pending"
    forward_return: Optional[float] = None
    resolved_at: Optional[str] = None


class PredictionLogReport(BaseModel):
    """Aggregated performance report from the prediction log.

    All fields derived from resolution are None when no outcomes have
    been resolved. ``min_required`` is the minimum resolved count before
    any metric is considered meaningful.
    """

    n_total: int = 0
    n_pending: int = 0
    n_resolved: int = 0
    min_required: int = 20
    status: str = "insufficient_data"
    hit_rate: Optional[float] = None
    mean_return: Optional[float] = None
    ic_rank: Optional[float] = None
    sharpe_annualized: Optional[float] = None
    sharpe_biased_raw: Optional[float] = None
    directional_p_value: Optional[float] = None
    overlap_factor: Optional[float] = None
    n_independent_estimate: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PredictionLogger:
    """Append-only JSONL prediction log with deferred outcome resolution."""

    def __init__(self, log_path: str | Path = "prediction_log.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_prediction(
        self,
        ticker: str,
        as_of: str,
        model_version: str,
        score: float,
        calibrated_probability: float | None = None,
        horizon_days: int = 20,
    ) -> PredictionRecord:
        """Record a new prediction (``status='pending'``)."""
        record = PredictionRecord(
            ticker=ticker,
            as_of=as_of,
            model_version=model_version,
            score=score,
            calibrated_probability=calibrated_probability,
            horizon_days=horizon_days,
            status="pending",
        )
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        return record

    def resolve_outcome(
        self,
        ticker: str,
        as_of: str,
        forward_return: float,
        horizon_days: int | None = None,
    ) -> int:
        """Resolve a pending prediction with a forward return.

        Matches the most recent pending prediction for the same ticker,
        as_of date, and optional horizon. Returns the number of records
        resolved (0 or 1). Data must be strictly future relative to as_of.
        """
        if not self.log_path.exists():
            return 0

        records = self._read_all()
        resolved = 0
        updated: list[PredictionRecord] = []

        for rec in records:
            if (
                rec.ticker == ticker
                and rec.as_of == as_of
                and rec.status == "pending"
            ):
                if horizon_days is not None and rec.horizon_days != horizon_days:
                    continue
                rec.status = "resolved"
                rec.forward_return = forward_return
                rec.resolved_at = datetime.now(timezone.utc).isoformat()
                resolved += 1
            updated.append(rec)

        if resolved > 0:
            self._write_all(updated)
            logger.debug(
                "Resolved %d prediction(s) for %s @ %s", resolved, ticker, as_of
            )

        return resolved

    def performance_report(self, min_required: int = 20) -> PredictionLogReport:
        """Compute aggregated performance on resolved outcomes.

        Only resolved outcomes are evaluated. If n_resolved < min_required,
        ``status='insufficient_data'`` and all metrics are None.

        Overlap guard: if predictions have overlapping forward windows
        (horizon > average interval between observations), the Sharpe
        ratio is inflated. We compute ``overlap_factor`` and suppress
        ``sharpe_annualized`` when factor > 2.

        Args:
            min_required: Minimum resolved outcomes needed for meaningful
                metrics.

        Returns:
            PredictionLogReport. No Sharpe invented.
        """
        if not self.log_path.exists():
            return PredictionLogReport(
                status="insufficient_data", min_required=min_required,
            )

        records = self._read_all()
        n_total = len(records)
        n_pending = sum(1 for r in records if r.status == "pending")
        resolved = [r for r in records if r.status == "resolved"]
        n_resolved = len(resolved)

        if n_resolved < min_required:
            return PredictionLogReport(
                n_total=n_total, n_pending=n_pending, n_resolved=n_resolved,
                min_required=min_required, status="insufficient_data",
            )

        scores = np.array([r.score for r in resolved], dtype=float)
        returns = np.array(
            [r.forward_return for r in resolved if r.forward_return is not None],
            dtype=float,
        )

        if len(returns) < min_required:
            return PredictionLogReport(
                n_total=n_total, n_pending=n_pending, n_resolved=n_resolved,
                min_required=min_required, status="insufficient_data",
            )

        hit_rate = float(np.mean(returns > 0))
        mean_ret = float(np.mean(returns))

        # ── IC rank ───────────────────────────────────────────────
        scores_trim = scores[:len(returns)]
        ic_rank_val, _ = spearmanr(scores_trim, returns)
        ic_rank = float(ic_rank_val) if np.isfinite(ic_rank_val) else None

        # ── Directional p-value (binomial test on hit rate) ───────
        n_hits = int(np.sum(returns > 0))
        n_total_ret = len(returns)
        if n_total_ret >= 5:
            result = binomtest(n_hits, n=n_total_ret, p=0.5, alternative="two-sided")
            directional_p = float(result.pvalue) if hasattr(result, "pvalue") else None
        else:
            directional_p = None

        # ── Overlap detection ─────────────────────────────────────
        overlap_factor, n_indep, warnings = _compute_overlap(resolved)
        sharpe_annualized = None
        sharpe_biased = None

        if len(returns) > 1:
            sharpe_biased = float(
                np.mean(returns) / max(np.std(returns, ddof=1), 1e-10) * np.sqrt(252)
            )
            if overlap_factor is None or overlap_factor <= 2.0:
                sharpe_annualized = sharpe_biased

        return PredictionLogReport(
            n_total=n_total,
            n_pending=n_pending,
            n_resolved=n_resolved,
            min_required=min_required,
            status="ok",
            hit_rate=round(hit_rate, 4),
            mean_return=round(mean_ret, 6),
            ic_rank=round(ic_rank, 4) if ic_rank is not None else None,
            sharpe_annualized=(
                round(sharpe_annualized, 4) if sharpe_annualized is not None else None
            ),
            sharpe_biased_raw=(
                round(sharpe_biased, 4) if sharpe_biased is not None else None
            ),
            directional_p_value=(
                round(directional_p, 6) if directional_p is not None else None
            ),
            overlap_factor=(
                round(overlap_factor, 2) if overlap_factor is not None else None
            ),
            n_independent_estimate=(
                round(n_indep, 1) if n_indep is not None else None
            ),
            warnings=warnings,
        )

    def _read_all(self) -> list[PredictionRecord]:
        """Read all records from the log file."""
        if not self.log_path.exists():
            return []
        records: list[PredictionRecord] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(PredictionRecord.model_validate_json(line))
                except (ValueError, KeyError):
                    logger.warning("Skipping malformed log line", exc_info=True)
        return records

    def _write_all(self, records: list[PredictionRecord]) -> None:
        """Overwrite the log file with updated records."""
        with open(self.log_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(rec.model_dump_json() + "\n")


def _compute_overlap(
    resolved: list[PredictionRecord],
) -> tuple[float | None, float | None, list[str]]:
    """Compute overlap factor from prediction horizons and intervals.

    overlap_factor = mean(horizon_days) / mean(interval between as_of per ticker).
    If factor > 2, Sharpe/t-stat are inflated and invalid.

    Returns (overlap_factor, n_independent_estimate, warnings).
    """
    if not resolved:
        return None, None, []

    # Build per-ticker DataFrames of (as_of, horizon_days)
    rows = []
    for r in resolved:
        try:
            ts = pd.Timestamp(r.as_of)
            rows.append({"ticker": r.ticker, "as_of": ts, "horizon_days": r.horizon_days})
        except (ValueError, TypeError):
            continue

    if not rows:
        return None, None, []

    df = pd.DataFrame(rows)
    mean_horizon = float(df["horizon_days"].mean())

    # Per-ticker average interval
    intervals = []
    for ticker, grp in df.groupby("ticker"):
        grp_sorted = grp.sort_values("as_of")
        if len(grp_sorted) >= 2:
            diffs = grp_sorted["as_of"].diff().dropna()
            intervals.extend(diffs.dt.days.tolist())

    if not intervals:
        # Single ticker with single observation → no overlap detection possible
        return None, None, []

    mean_interval = float(np.mean(intervals))
    if mean_interval < 0.5:
        mean_interval = 1.0  # Minimum daily

    overlap = mean_horizon / mean_interval
    n_independent = len(df) / max(overlap, 1.0)

    warnings: list[str] = []
    if overlap > 2.0:
        warnings.append(
            f"OVERLAP: Sharpe/t-stat INVALID — predictions overlap ~{overlap:.1f}x "
            f"(horizon={mean_horizon:.0f}d / interval={mean_interval:.0f}d). "
            "Use non-overlapping subsample or Newey-West. "
            "Valid metrics: hit rate, mean return, IC rank, directional p-value."
        )

    return overlap, n_independent, warnings
