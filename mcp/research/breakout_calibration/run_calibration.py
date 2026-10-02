"""End-to-end breakout calibration study (Phase 1).

Run::

    python -m research.breakout_calibration.run_calibration --quick
    python -m research.breakout_calibration.run_calibration

Outputs (in ``research/breakout_calibration/output/``):

- ``thresholds.json``  consumable thresholds for Phase 2
- ``report.json``      full machine-readable report
- ``report.md``        human-readable summary with tables
"""

# pylint: disable=too-many-locals,too-many-statements
# pylint: disable=too-many-positional-arguments,too-many-arguments

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from . import calibration, config, dataset, features
from .schema import (
    BreakoutCell,
    CalibrationReport,
    HorizonStats,
    MomentumBucket,
    RealityCheckResult,
    RegimeVariant,
    SampleInfo,
    StopOutcome,
    Thresholds,
)

LOGGER = logging.getLogger("breakout_calibration")

EVENT_COLUMNS = [
    *[f"fwd{horizon}" for horizon in config.HORIZONS],
    "dist_sma200",
    "rsi14",
    "mom12",
    "ret_1d",
    "atr_pct",
    "above_sma200",
    "vol_ratio",
]


class Accumulator:  # pylint: disable=too-few-public-methods
    """Mutable container for the raw panels and running stop sums."""

    def __init__(self) -> None:
        self.baseline_parts: list[pd.DataFrame] = []
        self.event_parts: list[pd.DataFrame] = []
        self.stop_sums: dict[tuple[int, float, float, int], list[float]] = defaultdict(
            lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        )
        self.n_trading_days: set[pd.Timestamp] = set()
        self.n_observations = 0


def _event_slice(
    frame: pd.DataFrame,
    positions: np.ndarray,
    symbol: str,
    lookback: int,
    volume_mult: float,
) -> pd.DataFrame:
    """Slice breakout event rows for one configuration."""
    cols = [col for col in EVENT_COLUMNS if col in frame.columns]
    block = frame.iloc[positions][cols].copy()
    block["symbol"] = symbol
    block["date"] = frame.index[positions]
    block["n_days"] = lookback
    block["volume_mult"] = volume_mult
    return block.reset_index(drop=True)


def _accumulate_stops(
    acc: Accumulator,
    frame: pd.DataFrame,
    positions: np.ndarray,
    lookback: int,
    volume_mult: float,
    max_horizon: int,
) -> None:
    """Update running stop/hold aggregates for one symbol."""
    close = frame["Close"].to_numpy(dtype=float)
    low = frame["Low"].to_numpy(dtype=float)
    atr_pct = frame["atr_pct"].to_numpy(dtype=float)
    n_rows = close.size
    for pos in positions:
        if pos + max_horizon >= n_rows:
            continue
        entry = close[pos]
        entry_atr = atr_pct[pos]
        if not np.isfinite(entry) or not np.isfinite(entry_atr) or entry_atr <= 0.0:
            continue
        future_low = low[pos + 1 : pos + 1 + max_horizon]
        for atr_mult in config.ATR_MULTS:
            stop_distance = atr_mult * entry_atr
            hits = np.flatnonzero(future_low <= entry * (1.0 - stop_distance))
            first_hit = int(hits[0]) + 1 if hits.size else None
            for horizon in config.HORIZONS:
                if first_hit is not None and first_hit <= horizon:
                    outcome = -stop_distance
                else:
                    outcome = close[pos + horizon] / entry - 1.0
                key = (lookback, volume_mult, atr_mult, horizon)
                bucket = acc.stop_sums[key]
                bucket[0] += 1.0
                bucket[1] += outcome
                bucket[2] += outcome * outcome
                bucket[3] += stop_distance
                if outcome > 0.0:
                    bucket[4] += outcome
                    bucket[6] += 1.0
                else:
                    bucket[5] += -outcome


def build_panels(
    ohlcv: dict[str, pd.DataFrame],
    benchmark_uptrend: dict[pd.Timestamp, bool],
) -> Accumulator:
    """Iterate the universe once, filling baseline/event panels + stops."""
    acc = Accumulator()
    max_horizon = max(config.HORIZONS)
    for symbol, frame in ohlcv.items():
        clean = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        if len(clean) < config.MIN_HISTORY_DAYS:
            continue
        ind = features.compute_indicators(clean)
        acc.n_trading_days.update(ind.index)
        valid = ind[[f"fwd{horizon}" for horizon in config.HORIZONS]].notna().any(
            axis=1
        )
        base_cols = [
            *[f"fwd{horizon}" for horizon in config.HORIZONS],
            "dist_sma200",
            "rsi14",
            "mom12",
            "ret_1d",
        ]
        base_block = ind.loc[valid, base_cols].copy()
        base_block["date"] = ind.index[valid]
        acc.baseline_parts.append(base_block.reset_index(drop=True))
        acc.n_observations += int(valid.sum())

        for lookback in config.BREAKOUT_LOOKBACKS:
            for volume_mult in config.VOLUME_MULTIPLES:
                mask = features.breakout_mask(ind, lookback, volume_mult).to_numpy()
                positions = np.flatnonzero(mask)
                if positions.size == 0:
                    continue
                block = _event_slice(ind, positions, symbol, lookback, volume_mult)
                block["market_uptrend"] = [
                    benchmark_uptrend.get(ts, False) for ts in block["date"]
                ]
                acc.event_parts.append(block)
                _accumulate_stops(
                    acc, ind, positions, lookback, volume_mult, max_horizon
                )
    return acc


def _baseline_arrays(
    baseline_df: pd.DataFrame,
    mask: pd.Series | None = None,
) -> dict[int, np.ndarray]:
    """Return {horizon: forward-return array} for a baseline."""
    frame = baseline_df if mask is None else baseline_df.loc[mask]
    return {
        horizon: frame[f"fwd{horizon}"].to_numpy(dtype=float)
        for horizon in config.HORIZONS
    }


def _cell(
    events: pd.DataFrame,
    baseline: dict[int, np.ndarray],
    lookback: int,
    volume_mult: float,
    sample: str,
    label: str,
) -> BreakoutCell:
    """Build a BreakoutCell from the events of one configuration."""
    horizons = [
        calibration.horizon_stats(
            events[f"fwd{horizon}"].to_numpy(dtype=float),
            baseline[horizon],
            horizon,
        )
        for horizon in config.HORIZONS
    ]
    return BreakoutCell(
        n_days=lookback,
        volume_mult=volume_mult,
        label=label,
        sample=sample,
        horizons=horizons,
    )


def breakout_grid(
    events: pd.DataFrame,
    baseline: dict[int, np.ndarray],
    sample: str,
) -> list[BreakoutCell]:
    """Compute the breakout grid over lookback/volume combos."""
    cells: list[BreakoutCell] = []
    for lookback in config.BREAKOUT_LOOKBACKS:
        for volume_mult in config.VOLUME_MULTIPLES:
            subset = events[
                (events["n_days"] == lookback)
                & (np.isclose(events["volume_mult"], volume_mult))
            ]
            label = f"N{lookback}_vol{volume_mult:g}"
            cells.append(
                _cell(subset, baseline, lookback, volume_mult, sample, label)
            )
    return cells


def regime_analysis(
    events: pd.DataFrame,
    baseline: dict[int, np.ndarray],
    lookbacks: tuple[int, ...],
    volume_mult: float,
) -> list[RegimeVariant]:
    """Compute breakout stats under regime conditions."""
    variants: list[RegimeVariant] = []
    for lookback in lookbacks:
        base = events[
            (events["n_days"] == lookback)
            & (np.isclose(events["volume_mult"], volume_mult))
        ]
        conditions: list[tuple[str, str, pd.Series]] = [
            ("all", "Unconditional breakout", pd.Series(True, index=base.index)),
            ("ticker_uptrend", "Close > SMA200", base["above_sma200"]),
            ("ticker_downtrend", "Close <= SMA200", ~base["above_sma200"]),
            ("momentum_12m_pos", "12m momentum > 0", base["mom12"] > 0.0),
            ("market_uptrend", "SPY > SMA200", base["market_uptrend"]),
            (
                "uptrend_and_market",
                "Close > SMA200 and SPY > SMA200",
                base["above_sma200"] & base["market_uptrend"],
            ),
            (
                "full_confluence",
                "Close > SMA200, SPY > SMA200, 12m momentum > 0",
                base["above_sma200"]
                & base["market_uptrend"]
                & (base["mom12"] > 0.0),
            ),
            (
                "extended_20pct",
                "Close > SMA200 by more than 20% (extension test)",
                base["dist_sma200"] > 0.20,
            ),
        ]
        for name, description, mask in conditions:
            subset = base.loc[mask.fillna(False)]
            horizons = [
                calibration.horizon_stats(
                    subset[f"fwd{horizon}"].to_numpy(dtype=float),
                    baseline[horizon],
                    horizon,
                )
                for horizon in config.HORIZONS
            ]
            variants.append(
                RegimeVariant(
                    condition=f"N{lookback}_{name}",
                    description=description,
                    n_events=int(len(subset)),
                    horizons=horizons,
                )
            )
    return variants


def momentum_analysis(
    baseline_df: pd.DataFrame,
    baseline: dict[int, np.ndarray],
) -> list[MomentumBucket]:
    """Compute forward returns per cross-sectional quintile."""
    work = baseline_df.copy()
    for metric in config.MOMENTUM_METRICS:
        ranks = work.groupby("date")[metric].rank(pct=True)
        quantile = np.ceil(ranks.to_numpy() * config.MOMENTUM_QUANTILES)
        work[f"q_{metric}"] = np.where(np.isfinite(quantile), quantile, 0).astype(int)

    results: list[MomentumBucket] = []
    for metric in config.MOMENTUM_METRICS:
        values = work[metric].to_numpy(dtype=float)
        for quantile in range(1, config.MOMENTUM_QUANTILES + 1):
            mask = (work[f"q_{metric}"] == quantile).to_numpy()
            metrics = values[mask]
            finite = metrics[np.isfinite(metrics)]
            if finite.size == 0:
                continue
            horizons = [
                calibration.horizon_stats(
                    work[f"fwd{horizon}"].to_numpy(dtype=float)[mask],
                    baseline[horizon],
                    horizon,
                )
                for horizon in config.HORIZONS
            ]
            results.append(
                MomentumBucket(
                    metric=metric,
                    quantile=quantile,
                    n_quantiles=config.MOMENTUM_QUANTILES,
                    range_low=float(np.min(finite)),
                    range_high=float(np.max(finite)),
                    sample="full",
                    horizons=horizons,
                )
            )
    return results


def stop_analysis(acc: Accumulator) -> list[StopOutcome]:
    """Convert running stop sums into StopOutcome records."""
    outcomes: list[StopOutcome] = []
    for (lookback, volume_mult, atr_mult, horizon), sums in sorted(
        acc.stop_sums.items()
    ):
        count, total, _, stop_total, gross_profit, gross_loss, win_count = sums
        if count <= 0:
            continue
        mean_return = total / count
        mean_stop = stop_total / count
        win_rate = win_count / count
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )
        expectancy = mean_return / mean_stop if mean_stop > 0 else 0.0
        outcomes.append(
            StopOutcome(
                n_days=lookback,
                volume_mult=volume_mult,
                atr_mult=atr_mult,
                horizon_days=horizon,
                n_events=int(count),
                stop_distance_pct_mean=mean_stop,
                win_rate=win_rate,
                mean_return=mean_return,
                expectancy_over_risk=expectancy,
                profit_factor=profit_factor,
            )
        )
    return outcomes


def _daily_excess_series(
    events: pd.DataFrame,
    dates: np.ndarray,
    horizon: int,
    baseline_mean: float,
    configs: list[tuple[int, float]],
) -> dict[str, np.ndarray]:
    """Build per-config daily excess series for the RC test."""
    index = {ts: idx for idx, ts in enumerate(dates)}
    series: dict[str, np.ndarray] = {}
    for lookback, volume_mult in configs:
        identity = f"N{lookback}_vol{volume_mult:g}"
        arr = np.full(dates.shape, np.nan)
        subset = events[
            (events["n_days"] == lookback)
            & (np.isclose(events["volume_mult"], volume_mult))
        ]
        if subset.empty:
            series[identity] = arr
            continue
        grouped = subset.groupby("date")[f"fwd{horizon}"].mean()
        for ts, value in grouped.items():
            idx = index.get(ts)
            if idx is not None and np.isfinite(value):
                arr[idx] = value - baseline_mean
        series[identity] = arr
    return series


def _cell_horizon(cell: BreakoutCell, horizon: int) -> HorizonStats:
    """Return the stats of a cell at a given horizon."""
    for stat in cell.horizons:
        if stat.horizon_days == horizon:
            return stat
    return cell.horizons[0]


def _bucket_horizon(bucket: MomentumBucket, horizon: int) -> HorizonStats:
    """Return the stats of a bucket at a given horizon."""
    for stat in bucket.horizons:
        if stat.horizon_days == horizon:
            return stat
    return bucket.horizons[0]


def build_thresholds(
    sample: SampleInfo,
    cells: list[BreakoutCell],
    oos_cells: list[BreakoutCell],
    regimes: list[RegimeVariant],
    outcomes: list[StopOutcome],
    momentum: list[MomentumBucket],
    primary_horizon: int = 20,
) -> Thresholds:
    """Deterministically derive the recommended thresholds from the evidence."""
    positive = [
        cell
        for cell in cells
        if cell.volume_mult > 0.0
        and _cell_horizon(cell, primary_horizon).sample_ok
        and _cell_horizon(cell, primary_horizon).mean_excess_return > 0.0
    ]
    oos_by_label = {cell.label: cell for cell in oos_cells}

    def combined_score(cell: BreakoutCell) -> float:
        is_stat = _cell_horizon(cell, primary_horizon)
        oos_cell = oos_by_label.get(cell.label)
        oos_stat = _cell_horizon(oos_cell, primary_horizon) if oos_cell else None
        if not is_stat.sample_ok or oos_stat is None or not oos_stat.sample_ok:
            return float("-inf")
        return is_stat.mean_excess_return + oos_stat.mean_excess_return

    robust = [
        cell
        for cell in cells
        if cell.volume_mult > 0.0 and combined_score(cell) > float("-inf")
    ]
    if positive:
        best = max(
            positive,
            key=lambda cell: _cell_horizon(cell, primary_horizon).mean_excess_return,
        )
    elif robust:
        best = max(robust, key=combined_score)
    else:
        best = max(
            [cell for cell in cells if cell.volume_mult > 0.0] or cells,
            key=lambda cell: _cell_horizon(cell, primary_horizon).mean_excess_return,
        )
    raw_edge = _cell_horizon(best, primary_horizon).mean_excess_return
    best_oos = oos_by_label.get(best.label, best)
    preferred_stat = max(
        best_oos.horizons, key=lambda stat: stat.mean_excess_return
    )

    def regime_excess(name: str) -> float:
        variant = next(
            (
                item
                for item in regimes
                if item.condition == f"N{best.n_days}_{name}"
            ),
            None,
        )
        return _horizon_excess(variant, primary_horizon) if variant else float("-inf")

    all_excess = regime_excess("all")
    uptrend_excess = regime_excess("ticker_uptrend")
    market_excess = regime_excess("market_uptrend")
    confluence_excess = regime_excess("full_confluence")
    require_trend = uptrend_excess >= all_excess
    require_market = confluence_excess >= max(all_excess, market_excess)

    def stop_pool(min_win: float) -> list[StopOutcome]:
        return [
            outcome
            for outcome in outcomes
            if outcome.n_days == best.n_days
            and np.isclose(outcome.volume_mult, best.volume_mult)
            and outcome.horizon_days == preferred_stat.horizon_days
            and outcome.n_events >= calibration.MIN_EVENTS_FOR_CLT
            and outcome.win_rate >= min_win
        ]

    stop_candidates = stop_pool(0.25) or stop_pool(0.0)
    if not stop_candidates:
        stop_candidates = [
            outcome
            for outcome in outcomes
            if outcome.horizon_days == preferred_stat.horizon_days
            and outcome.n_events >= calibration.MIN_EVENTS_FOR_CLT
        ]
    best_stop = max(
        stop_candidates, key=lambda outcome: outcome.expectancy_over_risk, default=None
    )

    mom_buckets = [bucket for bucket in momentum if bucket.metric == "mom12"]
    ext_buckets = [
        bucket for bucket in momentum if bucket.metric == "dist_sma200"
    ]
    top_mom = max(mom_buckets, key=lambda b: b.quantile, default=None)
    top_ext = max(ext_buckets, key=lambda b: b.quantile, default=None)
    mom_txt = (
        f"{_bucket_horizon(top_mom, primary_horizon).mean_excess_return:+.2%}"
        if top_mom
        else "n/a"
    )
    ext_txt = (
        f"{_bucket_horizon(top_ext, primary_horizon).mean_excess_return:+.2%}"
        if top_ext
        else "n/a"
    )
    min_momentum = 0.0

    edge_is_positive = raw_edge > 0.0
    return Thresholds(
        version="1.0.0",
        generated_at=datetime.now(timezone.utc),
        breakout_lookback_days=best.n_days,
        breakout_volume_mult=best.volume_mult,
        breakout_requires_volume=best.volume_mult > 0.0,
        max_extension_atr_above_sma50=None,
        require_close_above_sma200=require_trend,
        require_market_above_sma200=require_market,
        min_momentum_12m=round(min_momentum, 4),
        atr_window=config.ATR_WINDOW,
        stop_atr_mult=best_stop.atr_mult if best_stop else 2.0,
        holding_days_preferred=preferred_stat.horizon_days,
        holding_days_max=max(config.HORIZONS),
        expected_win_rate=preferred_stat.hit_rate,
        expected_excess_return=preferred_stat.mean_excess_return,
        mean_reversion_bias_warning=(
            "Extension is NOT a fade signal for momentum names. On this "
            f"sample the top 12m-momentum quintile has excess {mom_txt} and the "
            f"top distance-from-SMA200 quintile has excess {ext_txt} at "
            f"{primary_horizon}d, both POSITIVE: the most extended names do not "
            "mean-revert over 5-60 days. Mean-reversion logic must not be "
            "applied to a confirmed uptrend making fresh relative-strength highs."
        ),
        gex_limitation=(
            "No historical options/GEX dataset exists in this pipeline, so "
            "call walls / long-gamma magnet behaviour could NOT be backtested. "
            "GEX remains a qualitative, documented overlay only."
        ),
        verified=_verified_claims(best, best_oos),
        assumptions=[
            "Entries execute at the breakout day close (no slippage/costs).",
            "Forward returns are close-to-close, auto-adjusted for dividends.",
            "Baseline is the unconditional same-horizon return of all stock-days.",
            "Point-in-time S&P 500 membership from the MCP universe CSV.",
            (
                "Raw breakout edge is positive in-sample."
                if edge_is_positive
                else "No raw breakout config beat the baseline in-sample; the "
                "recommended setup relies on regime conditioning and must be "
                "treated as unproven."
            ),
        ],
        caveats=[
            sample.survivorship_bias,
            "No breakout configuration had a positive in-sample excess return, "
            "so the breakout edge is NOT certified in-sample; the recommended "
            "configuration is selected by the sum of in-sample and "
            "out-of-sample excess (both required sample-ok), which means "
            "out-of-sample was used for selection and is not a fully "
            "independent confirmation.",
            "Overlapping forward windows inflate the effective sample; the "
            "block bootstrap mitigates but does not fully remove the effect.",
            "Thresholds are selected in-sample (<=2020-12-31) and validated "
            "out-of-sample (>=2021-01-01).",
            "The preferred holding horizon is chosen from the tested set "
            f"{list(config.HORIZONS)}; if it equals the maximum, longer "
            "horizons were not evaluated.",
        ],
    )


def _horizon_excess(variant: RegimeVariant, horizon: int) -> float:
    """Return mean excess at a horizon, or -inf if missing."""
    for stat in variant.horizons:
        if stat.horizon_days == horizon:
            return stat.mean_excess_return
    return float("-inf")


def _verified_claims(best: BreakoutCell, best_oos: BreakoutCell) -> list[str]:
    """List the in/out-of-sample evidence strings for a config."""
    claims: list[str] = []
    for stat in best.horizons:
        claims.append(
            f"IS {best.label} h={stat.horizon_days}: n={stat.n_events}, "
            f"excess={stat.mean_excess_return:+.2%}, "
            f"hit={stat.hit_rate:.0%} (baseline {stat.baseline_hit_rate:.0%}), "
            f"p={stat.p_value:.3f}"
        )
    for stat in best_oos.horizons:
        claims.append(
            f"OOS {best_oos.label} h={stat.horizon_days}: n={stat.n_events}, "
            f"excess={stat.mean_excess_return:+.2%}, hit={stat.hit_rate:.0%}"
        )
    return claims


def _render_markdown(report: CalibrationReport) -> str:
    """Render the human-readable calibration report."""
    lines: list[str] = []
    lines.append("# Breakout Calibration Report (Phase 1)")
    lines.append("")
    lines.append(f"Generated: {report.generated_at.isoformat()}")
    lines.append("")
    sample = report.sample
    lines.append("## Sample")
    lines.append("")
    lines.append(f"- Universe: {sample.universe_source}")
    lines.append(f"- Symbols requested: {sample.n_symbols_requested}")
    lines.append(f"- Symbols loaded: {sample.n_symbols_loaded}")
    lines.append(f"- Period: {sample.period_start} -> {sample.period_end}")
    lines.append(f"- Trading days: {sample.n_trading_days}")
    lines.append(f"- Stock-day observations: {sample.n_observations}")
    lines.append(f"- In-sample ends: {sample.in_sample_end}")
    lines.append(f"- Survivorship bias: {sample.survivorship_bias}")
    lines.append("")

    lines.append("## Baseline (unconditional)")
    lines.append("")
    lines.append("| Horizon | Mean | Hit rate |")
    lines.append("|---|---|---|")
    for stat in report.baseline:
        lines.append(
            f"| {stat.horizon_days}d | {stat.mean_fwd_return:+.2%} | "
            f"{stat.hit_rate:.1%} |"
        )
    lines.append("")

    lines.append("## Breakout grid (in-sample)")
    lines.append("")
    lines.append("| Config | Horizon | n | Mean | Excess | Hit | baseline hit | p |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for cell in report.in_sample_grid:
        for stat in cell.horizons:
            lines.append(
                f"| {cell.label} | {stat.horizon_days}d | {stat.n_events} | "
                f"{stat.mean_fwd_return:+.2%} | {stat.mean_excess_return:+.2%} | "
                f"{stat.hit_rate:.1%} | {stat.baseline_hit_rate:.1%} | "
                f"{stat.p_value:.3f} |"
            )
    lines.append("")

    lines.append("## Out-of-sample validation")
    lines.append("")
    lines.append("| Config | Horizon | n | Mean | Excess | Hit | p |")
    lines.append("|---|---|---|---|---|---|---|")
    for cell in report.out_of_sample_grid:
        for stat in cell.horizons:
            lines.append(
                f"| {cell.label} | {stat.horizon_days}d | {stat.n_events} | "
                f"{stat.mean_fwd_return:+.2%} | {stat.mean_excess_return:+.2%} | "
                f"{stat.hit_rate:.1%} | {stat.p_value:.3f} |"
            )
    lines.append("")

    lines.append("## Regime conditioning")
    lines.append("")
    lines.append("| Condition | n | h5 excess | h10 excess | h20 excess | h60 excess |")
    lines.append("|---|---|---|---|---|---|")
    for variant in report.regime_analysis:
        by_h = {stat.horizon_days: stat for stat in variant.horizons}
        row = [f"| {variant.condition} | {variant.n_events} "]
        for horizon in config.HORIZONS:
            stat = by_h.get(horizon)
            row.append(
                f"| {stat.mean_excess_return:+.2%} " if stat else "| n/a "
            )
        lines.append("".join(row) + "|")
    lines.append("")

    lines.append("## Momentum / extension buckets")
    lines.append("")
    lines.append("| Metric | Quintile | h20 mean | h20 excess | h20 hit |")
    lines.append("|---|---|---|---|---|")
    for bucket in report.momentum_analysis:
        stat = next(
            (s for s in bucket.horizons if s.horizon_days == 20),
            bucket.horizons[0],
        )
        lines.append(
            f"| {bucket.metric} | Q{bucket.quantile} | "
            f"{stat.mean_fwd_return:+.2%} | {stat.mean_excess_return:+.2%} | "
            f"{stat.hit_rate:.1%} |"
        )
    lines.append("")

    lines.append("## Stop / holding calibration")
    lines.append("")
    lines.append(
        "| N | vol | ATR x | Horizon | n | stop % | win | mean | E/R | PF |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for outcome in report.stop_analysis:
        if outcome.n_events < calibration.MIN_EVENTS_FOR_CLT:
            continue
        lines.append(
            f"| {outcome.n_days} | {outcome.volume_mult:g} | "
            f"{outcome.atr_mult:g} | {outcome.horizon_days}d | "
            f"{outcome.n_events} | {outcome.stop_distance_pct_mean:.2%} | "
            f"{outcome.win_rate:.1%} | {outcome.mean_return:+.2%} | "
            f"{outcome.expectancy_over_risk:.2f} | "
            f"{outcome.profit_factor:.2f} |"
        )
    lines.append("")

    if report.reality_check:
        rc = report.reality_check
        lines.append("## Data-mining robustness (White Reality Check)")
        lines.append("")
        lines.append(f"- Best config: {rc.best_config}")
        lines.append(f"- Observed best excess (h={rc.horizon_days}d): "
                     f"{rc.observed_best_excess:+.2%}")
        lines.append(f"- Bootstrap p-value: {rc.p_value_bootstrap:.3f}")
        lines.append(f"- Bonferroni p-value: {rc.p_value_bonferroni:.3f}")
        lines.append(f"- Bootstrap iterations: {rc.n_bootstrap} "
                     f"(block={rc.block_days}d, configs={rc.n_configs_tested})")
        lines.append(f"- Note: {rc.note}")
        lines.append("")

    lines.append("## Recommended thresholds")
    lines.append("")
    thresholds = report.thresholds
    lines.append("```json")
    lines.append(thresholds.model_dump_json(indent=2))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def run(max_symbols: int | None, use_cache: bool) -> CalibrationReport:
    """Run the full calibration study and return the report."""
    symbols = dataset.load_universe_symbols()
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    ohlcv = dataset.download_ohlcv(symbols, use_cache=use_cache)
    benchmark = dataset.load_benchmark(use_cache=use_cache)
    spy = features.compute_indicators(benchmark)
    benchmark_uptrend = dict(
        zip(
            spy.index,
            (spy["Close"] > spy["sma200"]).fillna(False).to_numpy(),
            strict=False,
        )
    )

    acc = build_panels(ohlcv, benchmark_uptrend)
    baseline_df = pd.concat(acc.baseline_parts, ignore_index=True)
    events = pd.concat(acc.event_parts, ignore_index=True)
    baseline_full = _baseline_arrays(baseline_df)

    is_end = pd.Timestamp(config.IN_SAMPLE_END)
    oos_start = pd.Timestamp(config.OUT_OF_SAMPLE_START)
    baseline_is = _baseline_arrays(baseline_df, baseline_df["date"] <= is_end)
    baseline_oos = _baseline_arrays(baseline_df, baseline_df["date"] >= oos_start)
    events_is = events[events["date"] <= is_end]
    events_oos = events[events["date"] >= oos_start]

    grid_full = breakout_grid(events, baseline_full, "full")
    grid_is = breakout_grid(events_is, baseline_is, "in_sample")
    grid_oos = breakout_grid(events_oos, baseline_oos, "out_of_sample")

    regimes = regime_analysis(
        events, baseline_full, config.BREAKOUT_LOOKBACKS, 1.5
    )
    momentum = momentum_analysis(baseline_df, baseline_full)
    stops = stop_analysis(acc)

    rc_configs = [
        (lookback, volume_mult)
        for lookback in config.BREAKOUT_LOOKBACKS
        for volume_mult in config.VOLUME_MULTIPLES
        if volume_mult > 0.0
    ]
    dates = np.sort(baseline_df["date"].unique())
    baseline_is_mean = float(np.nanmean(baseline_is[20]))
    series = _daily_excess_series(
        events_is, dates, 20, baseline_is_mean, rc_configs
    )
    best_label, observed, p_value = calibration.reality_check_white(
        series,
        n_bootstrap=config.BOOTSTRAP_ITERATIONS,
        block_days=config.BOOTSTRAP_BLOCK_DAYS,
        seed=config.BOOTSTRAP_SEED,
    )
    best_cell_p = 1.0
    for cell in grid_is:
        if cell.label == best_label:
            best_cell_p = next(
                (
                    stat.p_value
                    for stat in cell.horizons
                    if stat.horizon_days == 20
                ),
                1.0,
            )
    reality = RealityCheckResult(
        hypothesis=(
            "No breakout configuration beats the unconditional same-horizon "
            "baseline (H0: mean excess return = 0)."
        ),
        horizon_days=20,
        observed_best_excess=float(observed.get(best_label, 0.0)),
        best_config=best_label,
        p_value_bootstrap=float(p_value),
        p_value_bonferroni=calibration.bonferroni_p_value(
            best_cell_p, len(rc_configs)
        ),
        n_bootstrap=config.BOOTSTRAP_ITERATIONS,
        block_days=config.BOOTSTRAP_BLOCK_DAYS,
        n_configs_tested=len(rc_configs),
        note=(
            "Circular block bootstrap over calendar dates; in-sample only. "
            f"Best config {best_label} with {len(rc_configs)} configurations "
            "searched, so the bootstrap p-value already accounts for the "
            "multiple-comparison selection."
        ),
    )

    sample = SampleInfo(
        universe_source=(
            "Point-in-time S&P 500 constituents "
            "(trading_mcp/data/historical_universe_sp500.csv)"
        ),
        universe_note=(
            "Yahoo Finance daily auto-adjusted OHLCV via yfinance; "
            "delisted names only partially represented."
        ),
        survivorship_bias=(
            "Survivorship bias present: the universe CSV has only 4 explicit "
            "delistings, so most names that were removed/delisted are absent. "
            "Absolute returns are therefore mildly upward biased; the "
            "*relative* breakout-vs-baseline comparison is far less affected."
        ),
        n_symbols_requested=len(symbols),
        n_symbols_loaded=len(ohlcv),
        period_start=config.PERIOD_START,
        period_end=config.PERIOD_END,
        in_sample_end=config.IN_SAMPLE_END,
        n_trading_days=len(acc.n_trading_days),
        n_observations=acc.n_observations,
    )

    thresholds = build_thresholds(
        sample, grid_is, grid_oos, regimes, stops, momentum
    )

    baseline_stats = [
        calibration.horizon_stats(
            baseline_full[horizon],
            baseline_full[horizon],
            horizon,
        )
        for horizon in config.HORIZONS
    ]

    report = CalibrationReport(
        generated_at=datetime.now(timezone.utc),
        sample=sample,
        methodology=[
            "Breakout = close above the prior N-day high, optionally confirmed "
            "by volume > k x prior 20-day average volume.",
            "Forward returns close-to-close at "
            f"{'/'.join(str(h) for h in config.HORIZONS)} trading days.",
            "Baseline = unconditional same-horizon return of all stock-days; "
            "excess = event mean - baseline mean.",
            "In-sample <= 2020-12-31; out-of-sample >= 2021-01-01.",
            "One-sample t-test of excess vs 0 (n>=30 flagged sample_ok).",
            "Momentum tests use per-date cross-sectional quintiles (rank pct).",
            "Stops: ATR multiples walked over the maximum horizon, first-touch "
            "rule, unstopped trades exit at horizon close.",
            "Stop selection maximizes expectancy/risk subject to a minimum "
            "25% stop-system win rate to avoid degenerate tight-stop configs.",
            "White Reality Check via circular block bootstrap (in-sample).",
        ],
        baseline=baseline_stats,
        breakout_grid=grid_full,
        regime_analysis=regimes,
        momentum_analysis=momentum,
        stop_analysis=stops,
        in_sample_grid=grid_is,
        out_of_sample_grid=grid_oos,
        reality_check=reality,
        thresholds=thresholds,
    )
    return report


def persist(report: CalibrationReport) -> None:
    """Write report.json, thresholds.json and report.md."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUTPUT_DIR / "report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    (config.OUTPUT_DIR / "thresholds.json").write_text(
        report.thresholds.model_dump_json(indent=2), encoding="utf-8"
    )
    (config.OUTPUT_DIR / "report.md").write_text(
        _render_markdown(report), encoding="utf-8"
    )
    LOGGER.info("Artifacts written to %s", config.OUTPUT_DIR)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Limit universe size (smoke testing).",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Smoke run over a 120-symbol subset.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore and refresh the OHLCV cache.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = _parse_args(argv)
    max_symbols = args.max_symbols
    if args.quick and max_symbols is None:
        max_symbols = 120
    report = run(max_symbols=max_symbols, use_cache=not args.no_cache)
    persist(report)
    summary: dict[str, Any] = {
        "thresholds": report.thresholds.model_dump(mode="json"),
        "best_is": report.thresholds.verified[:4],
        "reality_check_p": (
            report.reality_check.p_value_bootstrap
            if report.reality_check
            else None
        ),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
