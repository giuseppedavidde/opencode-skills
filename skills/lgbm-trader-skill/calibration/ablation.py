"""Feature ablation utility — compare feature groups vs baseline on OOS.

P1 August 2026: ablation does NOT change model weights automatically.
It provides a diagnostic report comparing retrained-without-group
predictions to a baseline (full-feature model) on a strict temporal
OOS split.

Methodology:
1. Caller provides baseline_scores AND ablated_scores (dict
   group_name -> pd.Series of OOS predictions from a model retrained
   without that group).
2. All series are aligned on a common date index. Only dates
   > oos_cutoff are evaluated.
3. For each group, IC rank / hit rate are compared to baseline.
4. If ablated_scores is None or empty, the report returns
   INSUFFICIENT_EVIDENCE — NO zero-signal comparison, NO ranking.

Groups are defined by the 5 decorrelated groups in the LGBM stacking:
  momentum_vol, volume_profile, price_pattern, fundamentals,
  macro_options.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# Feature groups as defined in features/pipeline.py
_FEATURE_GROUPS = {
    "momentum_vol": [
        "ret_1d", "ret_5d", "ret_21d", "ret_63d", "ret_126d", "ret_252d",
        "vol_21d", "vol_63d", "vol_126d", "vol_252d",
        "rsi_14", "rsi_28",
        "bb_width", "bb_position",
        "sma_50_dist", "sma_200_dist",
    ],
    "volume_profile": [
        "volume_ratio_5d", "volume_ratio_21d",
        "vwap_deviation", "poc_price", "poc_shift",
        "value_area_high", "value_area_low",
        "volume_trend", "obv",
    ],
    "price_pattern": [
        "doji_ratio", "marubozu_ratio", "hammer_ratio",
        "engulfing_bull", "engulfing_bear",
        "wick_ratio", "body_ratio",
        "high_low_range", "close_position",
    ],
    "fundamentals": [
        "pe_ratio", "pb_ratio", "ps_ratio",
        "debt_to_equity", "roe", "roa",
        "profit_margin", "revenue_growth",
        "earnings_yield", "fcf_yield",
        "dividend_yield", "payout_ratio",
        "beta", "market_cap_log",
    ],
    "macro_options": [
        "vix_level", "dxy_level", "fed_rate",
        "fear_greed", "put_call_ratio", "iv_rank",
        "skew", "term_structure_slope",
        "sector_momentum", "sector_correlation",
    ],
}

_INSUFFICIENT_EVIDENCE_WARNING = (
    "true ablation requires OOS predictions from models retrained "
    "without each feature group; zeroing or random baseline is NOT "
    "valid evidence of group importance — provide ablated_scores "
    "(dict group_name -> pd.Series) from retrained models"
)


class AblationStatus(str, Enum):
    """Status of an ablation run."""

    OK = "ok"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ERROR = "error"


class GroupAblation(BaseModel):
    """Ablation result for a single feature group.

    All IC/hit-rate fields are None unless ablated_scores is
    provided for this group and OOS alignment succeeds.
    """

    group_name: str
    n_features: int = 0
    baseline_ic_rank: Optional[float] = None
    ablated_ic_rank: Optional[float] = None
    ic_rank_delta: Optional[float] = None
    baseline_hit_rate: Optional[float] = None
    ablated_hit_rate: Optional[float] = None
    hit_rate_delta: Optional[float] = None
    n_oos: int = 0
    status: str = "ok"
    note: str = ""


class AblationReport(BaseModel):
    """Complete ablation diagnostic report.

    This is a DIAGNOSTIC tool — it does not modify model weights.
    Use the results to understand feature contributions, then
    retrain models if feature selection changes are warranted.

    When ablated_scores is not provided, status is always
    INSUFFICIENT_EVIDENCE and ranked_by_importance is empty.
    """

    ticker: str
    status: AblationStatus = AblationStatus.INSUFFICIENT_EVIDENCE
    baseline_ic_rank: Optional[float] = None
    baseline_hit_rate: Optional[float] = None
    n_oos: int = 0
    min_oos_required: int = 30
    groups: list[GroupAblation] = Field(default_factory=list)
    ranked_by_importance: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_version: str = ""
    notes: list[str] = Field(
        default_factory=lambda: [
            "Ablation is diagnostic only — weights are NOT modified.",
            "True ablation requires OOS predictions from models "
            "retrained without each feature group.",
            "Retrain models with modified feature groups to apply findings.",
        ]
    )


def run_ablation(
    baseline_scores: pd.Series,
    forward_returns: pd.Series,
    dates: pd.DatetimeIndex,
    oos_cutoff: str,
    ablated_scores: dict[str, pd.Series] | None = None,
    feature_groups: dict[str, list[str]] | None = None,
    ticker: str = "UNKNOWN",
    model_version: str = "",
    min_oos: int = 30,
) -> AblationReport:
    """Run feature ablation on OOS data using retrained ablated predictions.

    Compares baseline (full-feature model) scores against scores from
    models retrained without each feature group. Evaluated ONLY on the
    temporal OOS period (dates > oos_cutoff).

    If ablated_scores is None or empty, returns INSUFFICIENT_EVIDENCE
    with a clear warning — NO zero-signal comparison is performed.

    Args:
        baseline_scores: Full-model scores aligned to dates index.
        forward_returns: Forward returns (same index as scores).
        dates: Date index aligned to scores and returns.
        oos_cutoff: ISO date string (YYYY-MM-DD) marking the
            temporal split. Only dates > cutoff are evaluated.
        ablated_scores: Optional dict group_name -> pd.Series of
            OOS predictions from a model retrained without that group.
            If None/empty, the report returns INSUFFICIENT_EVIDENCE.
        feature_groups: Dict of group_name -> list of feature column
            names (used only for n_features metadata). Defaults to
            _FEATURE_GROUPS.
        ticker: Ticker label.
        model_version: Version of the model producing baseline_scores.
        min_oos: Minimum aligned OOS observations required per group.

    Returns:
        AblationReport. status=OK only when ablated_scores is provided
        and OOS alignment succeeds.
    """
    if feature_groups is None:
        feature_groups = _FEATURE_GROUPS

    # ── Guard: no ablated scores → INSUFFICIENT_EVIDENCE ──────────
    if not ablated_scores:
        return AblationReport(
            ticker=ticker,
            status=AblationStatus.INSUFFICIENT_EVIDENCE,
            n_oos=0,
            min_oos_required=min_oos,
            warnings=[_INSUFFICIENT_EVIDENCE_WARNING],
            model_version=model_version,
        )

    # ── Build OOS mask ────────────────────────────────────────────
    oos_mask = dates > pd.Timestamp(oos_cutoff)
    oos_idx = dates[oos_mask]

    if len(oos_idx) < min_oos:
        return AblationReport(
            ticker=ticker,
            status=AblationStatus.INSUFFICIENT_EVIDENCE,
            n_oos=len(oos_idx),
            min_oos_required=min_oos,
            model_version=model_version,
            warnings=[
                f"Only {len(oos_idx)} OOS observations (need {min_oos})"
            ],
        )

    # ── Align baseline on OOS dates ───────────────────────────────
    oos_baseline = baseline_scores.reindex(dates).loc[oos_idx].dropna()
    oos_returns = forward_returns.reindex(dates).loc[oos_idx].dropna()

    common_idx = oos_baseline.index.intersection(oos_returns.index)
    if len(common_idx) < min_oos:
        return AblationReport(
            ticker=ticker,
            status=AblationStatus.INSUFFICIENT_EVIDENCE,
            n_oos=len(common_idx),
            min_oos_required=min_oos,
            model_version=model_version,
            warnings=[
                f"Only {len(common_idx)} aligned baseline+returns "
                f"OOS obs (need {min_oos})"
            ],
        )

    base_scores_arr = oos_baseline.loc[common_idx].to_numpy(dtype=float)
    base_returns_arr = oos_returns.loc[common_idx].to_numpy(dtype=float)

    base_ic, _ = spearmanr(base_scores_arr, base_returns_arr)
    base_ic = float(base_ic) if np.isfinite(base_ic) else None
    base_hr = float(np.mean(base_returns_arr > 0))

    # ── Ablation per group ────────────────────────────────────────
    groups_out: list[GroupAblation] = []

    for group_name, features in feature_groups.items():
        n_feat = len(features)

        ablated_series = ablated_scores.get(group_name)
        if ablated_series is None or ablated_series.empty:
            groups_out.append(GroupAblation(
                group_name=group_name,
                n_features=n_feat,
                n_oos=0,
                status="insufficient_evidence",
                note=(
                    f"No ablated_scores provided for '{group_name}'. "
                    "Retrain the model without this group and supply "
                    "OOS predictions."
                ),
            ))
            continue

        # Align ablated scores on common_idx
        aligned_ablated = ablated_series.reindex(common_idx).dropna()
        group_common = aligned_ablated.index.intersection(common_idx)

        if len(group_common) < min_oos:
            groups_out.append(GroupAblation(
                group_name=group_name,
                n_features=n_feat,
                n_oos=len(group_common),
                status="insufficient_evidence",
                note=(
                    f"Only {len(group_common)} aligned OOS obs for "
                    f"'{group_name}' (need {min_oos})"
                ),
            ))
            continue

        # Truncate baseline/returns to the intersection with ablated
        group_base = oos_baseline.loc[group_common].to_numpy(dtype=float)
        group_ret = oos_returns.loc[group_common].to_numpy(dtype=float)
        group_abl = aligned_ablated.loc[group_common].to_numpy(dtype=float)

        ablated_ic, _ = spearmanr(group_abl, group_ret)
        ablated_ic_val = float(ablated_ic) if np.isfinite(ablated_ic) else None
        ablated_hr_val = float(np.mean(group_ret > 0))

        # Baseline IC/hit rate on the same subset
        group_base_ic, _ = spearmanr(group_base, group_ret)
        group_base_ic_val = (
            float(group_base_ic) if np.isfinite(group_base_ic) else None
        )
        group_base_hr_val = float(np.mean(group_ret > 0))

        ic_delta = (
            None
            if group_base_ic_val is None or ablated_ic_val is None
            else round(group_base_ic_val - ablated_ic_val, 6)
        )
        hr_delta = round(group_base_hr_val - ablated_hr_val, 4)

        groups_out.append(GroupAblation(
            group_name=group_name,
            n_features=n_feat,
            baseline_ic_rank=(
                round(group_base_ic_val, 6)
                if group_base_ic_val is not None else None
            ),
            ablated_ic_rank=(
                round(ablated_ic_val, 6)
                if ablated_ic_val is not None else None
            ),
            ic_rank_delta=ic_delta,
            baseline_hit_rate=round(group_base_hr_val, 4),
            ablated_hit_rate=round(ablated_hr_val, 4),
            hit_rate_delta=hr_delta,
            n_oos=len(group_common),
            status="ok",
            note=(
                "IC delta = baseline IC − ablated IC. "
                "Positive delta → group contributes predictive power. "
                "Negative delta → group may be noise on this split."
            ),
        ))

    # Rank groups with valid IC delta (higher = more important)
    ranked = sorted(
        groups_out,
        key=lambda g: (
            g.ic_rank_delta if g.ic_rank_delta is not None else -999.0
        ),
        reverse=True,
    )
    ranked_names = [g.group_name for g in ranked]

    warnings: list[str] = []
    any_insufficient = any(
        g.status == "insufficient_evidence" for g in groups_out
    )
    if any_insufficient:
        warnings.append(
            "Some groups lack ablated predictions — only groups "
            "with sufficient OOS data are compared."
        )

    return AblationReport(
        ticker=ticker,
        status=AblationStatus.OK,
        baseline_ic_rank=(
            round(base_ic, 6) if base_ic is not None else None
        ),
        baseline_hit_rate=round(base_hr, 4),
        n_oos=len(common_idx),
        min_oos_required=min_oos,
        groups=ranked,
        ranked_by_importance=ranked_names,
        warnings=warnings,
        model_version=model_version,
        notes=[
            "DIAGNOSTIC ONLY: no weights modified.",
            "IC delta = baseline IC − ablated IC (positive = group "
            "contributes predictive power).",
            "Ablated predictions MUST come from models retrained "
            "without the group on the same temporal split.",
        ],
    )
