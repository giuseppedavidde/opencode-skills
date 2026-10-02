"""Statistical aggregation for the breakout calibration study.

Includes the data-mining-aware White Reality Check implemented as a
circular block bootstrap over the calendar-date axis, as recommended by
Aronson (Evidence-Based Technical Analysis, ch. 6 and 8).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from .schema import HorizonStats

MIN_EVENTS_FOR_CLT = 30
MAX_PROFIT_FACTOR = 999.0


def _finite(values: np.ndarray) -> np.ndarray:
    """Return only the finite values of an array as float64."""
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def horizon_stats(
    events: np.ndarray,
    baseline: np.ndarray,
    horizon: int,
) -> HorizonStats:
    """Summarise event forward returns at one horizon vs the baseline.

    The excess return is the event mean minus the unconditional baseline
    mean (the detrending step required before any hypothesis test), and
    the p-value comes from a one-sample t-test of the excess against 0.
    """
    clean = _finite(events)
    base = _finite(baseline)
    n_events = int(clean.size)
    base_mean = float(np.mean(base)) if base.size else 0.0
    base_hit = float(np.mean(base > 0.0)) if base.size else 0.0

    if n_events == 0:
        return HorizonStats(
            horizon_days=horizon,
            n_events=0,
            mean_fwd_return=0.0,
            median_fwd_return=0.0,
            std_fwd_return=0.0,
            hit_rate=0.0,
            mean_excess_return=0.0,
            t_stat=0.0,
            p_value=1.0,
            baseline_mean=base_mean,
            baseline_hit_rate=base_hit,
            sample_ok=False,
        )

    mean = float(np.mean(clean))
    std = float(np.std(clean, ddof=1)) if n_events > 1 else 0.0
    excess = clean - base_mean
    if n_events > 1 and float(np.std(excess, ddof=1)) > 0.0:
        test = stats.ttest_1samp(excess, 0.0, nan_policy="omit")
        t_stat = float(test.statistic)
        p_value = float(test.pvalue)
    else:
        t_stat = 0.0
        p_value = 1.0

    return HorizonStats(
        horizon_days=horizon,
        n_events=n_events,
        mean_fwd_return=mean,
        median_fwd_return=float(np.median(clean)),
        std_fwd_return=std,
        hit_rate=float(np.mean(clean > 0.0)),
        mean_excess_return=float(np.mean(excess)),
        t_stat=t_stat,
        p_value=p_value,
        baseline_mean=base_mean,
        baseline_hit_rate=base_hit,
        sample_ok=n_events >= MIN_EVENTS_FOR_CLT,
    )


def profit_factor(returns: np.ndarray) -> float:
    """Gross profit divided by gross loss, capped at ``MAX_PROFIT_FACTOR``."""
    clean = _finite(returns)
    gross_profit = float(clean[clean > 0.0].sum())
    gross_loss = float(-clean[clean < 0.0].sum())
    if gross_loss <= 0.0:
        return MAX_PROFIT_FACTOR if gross_profit > 0.0 else 0.0
    return min(gross_profit / gross_loss, MAX_PROFIT_FACTOR)


def circular_block_indices(
    n_dates: int,
    block_days: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return a circular block-bootstrap index vector over the date axis."""
    if n_dates <= block_days:
        return rng.integers(0, n_dates, size=n_dates)
    n_blocks = int(np.ceil(n_dates / block_days))
    starts = rng.integers(0, n_dates, size=n_blocks)
    offsets = np.arange(block_days)
    indices = (starts[:, None] + offsets[None, :]).ravel() % n_dates
    return indices[:n_dates]


def reality_check_white(  # pylint: disable=too-many-locals
    series_by_config: dict[str, np.ndarray],
    n_bootstrap: int,
    block_days: int,
    seed: int,
) -> tuple[str, dict[str, float], float]:
    """White's Reality Check over daily per-config excess-return series.

    Each series is a calendar-date-aligned array of mean forward excess
    returns (``NaN`` on dates with no signal). Series are centred by
    their own full-sample mean, block-resampled jointly, and the maximum
    across configs is compared with the observed maximum.

    Returns ``(best_label, observed_excess_by_config, p_value)``.
    """
    labels = list(series_by_config)
    if not labels:
        return "", {}, 1.0
    matrix = np.column_stack([series_by_config[label] for label in labels])
    n_dates = matrix.shape[0]
    observed = {
        label: float(np.nanmean(matrix[:, idx]))
        for idx, label in enumerate(labels)
    }
    best_label = max(observed, key=lambda key: observed[key])
    observed_max = observed[best_label]

    centred = matrix - np.nanmean(matrix, axis=0)
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_bootstrap):
        idx = circular_block_indices(n_dates, block_days, rng)
        sampled = centred[idx, :]
        boot_max = float(np.nanmax(np.nanmean(sampled, axis=0)))
        if boot_max >= observed_max:
            count += 1
    p_value = (count + 1) / (n_bootstrap + 1)
    return best_label, observed, p_value


def bonferroni_p_value(raw_p: float, n_tests: int) -> float:
    """Bonferroni-adjusted p-value for ``n_tests`` multiple comparisons."""
    return min(1.0, max(0.0, raw_p * max(1, n_tests)))
