"""Signal evaluator: IC rank/Pearson, hit rate, quintile spread, turnover.

All computations are point-in-time: each prediction's ``as_of`` is
guaranteed by the caller (``contract.py``) to use only data available at
that timestamp. The evaluator simply aggregates and ranks.

P0 August 2026: per-horizon ``supported`` / ``insufficient_data`` flags,
``required_observations`` threshold, diagnostic-only labelling.

P2 August 2026: net metrics (after trading costs) when
``BacktestConfig.apply_costs=True``. Costs are modelled as a fraction of
position turnover per the ``CostModel``. Net metrics are ESTIMATES,
never presented as exact measures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from backtest.contract import (
    BacktestBuildResult,
    BacktestBuildStatus,
    BacktestConfig,
    BacktestPrediction,
    BacktestResult,
    HorizonResult,
)


def evaluate(
    predictions: list[BacktestPrediction] | BacktestBuildResult,
    config: BacktestConfig | None = None,
    ticker: str = "UNKNOWN",
    signal_description: str = "",
) -> BacktestResult:
    """Evaluate point-in-time predictions across all horizons.

    For each horizon:
    - IC rank (Spearman) and IC Pearson between signal_score and
      forward_return
    - Hit rate (% of predictions with forward_return > 0)
    - Mean return %
    - Quintile spread (Q5 mean return - Q1 mean return)
    - Permutation control (randomised scores baseline)

    Horizons with < ``min_horizon_observations`` observations get
    ``supported=False`` and ``status="insufficient_data"`` — no metrics
    are computed.

    Parameters
    ----------
    predictions:
        Either a list of BacktestPrediction (legacy) or a
        BacktestBuildResult. When a BacktestBuildResult is passed,
        per-horizon capability flags are honoured.
    config:
        BacktestConfig (horizons, strict_mode, etc.).
    ticker:
        Ticker label.
    signal_description:
        Human-readable description of the signal source.

    Returns
    -------
    BacktestResult
    """
    if config is None:
        config = BacktestConfig()

    build_result: BacktestBuildResult | None = None
    preds_list: list[BacktestPrediction]

    if isinstance(predictions, BacktestBuildResult):
        build_result = predictions
        preds_list = build_result.predictions
    else:
        preds_list = predictions

    if not preds_list:
        return BacktestResult(
            ticker=ticker,
            signal_description=signal_description,
            diagnostic_only=(
                build_result.diagnostic_only if build_result else False
            ),
            build_status=(
                build_result.status.value if build_result else ""
            ),
            limits=[
                build_result.reason if build_result
                else "No predictions to evaluate",
            ],
        )

    df = pd.DataFrame([p.model_dump() for p in preds_list])

    if df.empty:
        return BacktestResult(
            ticker=ticker,
            signal_description=signal_description,
            diagnostic_only=(
                build_result.diagnostic_only if build_result else False
            ),
            build_status=(
                build_result.status.value if build_result else ""
            ),
            limits=["Empty prediction frame"],
        )

    as_of_min = df["as_of"].min()
    as_of_max = df["as_of"].max()

    min_obs = config.min_horizon_observations

    horizon_results: list[HorizonResult] = []
    for h in sorted(config.horizons_days):
        h_df = df[df["horizon_days"] == h].dropna(
            subset=["signal_score", "forward_return"]
        )
        n = len(h_df)

        # Check if this horizon is supported at all (check build caps)
        horizon_supported = True
        if build_result:
            for hc in build_result.horizons:
                if hc.horizon_days == h:
                    horizon_supported = hc.supported
                    break

        if not horizon_supported:
            horizon_results.append(
                HorizonResult(
                    horizon_days=h,
                    supported=False,
                    n_observations=n,
                    required_observations=min_obs,
                    status="insufficient_data",
                )
            )
            continue

        if n < min_obs:
            horizon_results.append(
                HorizonResult(
                    horizon_days=h,
                    supported=False,
                    n_observations=n,
                    required_observations=min_obs,
                    status="insufficient_data",
                )
            )
            continue

        signals = h_df["signal_score"].to_numpy(dtype=float)
        returns = h_df["forward_return"].to_numpy(dtype=float)

        ic_rank, _ = spearmanr(signals, returns)
        ic_rank = float(ic_rank) if np.isfinite(ic_rank) else None

        ic_pearson, _ = pearsonr(signals, returns)
        ic_pearson = float(ic_pearson) if np.isfinite(ic_pearson) else None

        hit_rate = float(np.mean(returns > 0))
        mean_ret = float(np.mean(returns)) * 100.0

        q_edges = np.percentile(signals, [0, 20, 40, 60, 80, 100])
        q_labels = ["Q1", "Q2", "Q3", "Q4", "Q5"]
        quintile_returns: dict[str, float] = {}

        for qi in range(5):
            mask = (signals >= q_edges[qi]) & (signals < q_edges[qi + 1])
            if qi == 4:
                mask = (signals >= q_edges[qi]) & (signals <= q_edges[qi + 1])
            q_ret = returns[mask]
            quintile_returns[q_labels[qi]] = (
                float(np.mean(q_ret)) * 100.0 if len(q_ret) > 0 else 0.0
            )

        qt_spread = None
        if all(k in quintile_returns for k in ("Q5", "Q1")):
            qt_spread = round(quintile_returns["Q5"] - quintile_returns["Q1"], 4)

        perm_ic_rank = None
        perm_ic_pearson = None
        if config.permutation_control and n >= min_obs:
            rng = np.random.default_rng(42)
            shuffled = rng.permutation(signals.copy())
            base_ic, _ = spearmanr(shuffled, returns)
            perm_ic_rank = float(base_ic) if np.isfinite(base_ic) else None
            base_p, _ = pearsonr(shuffled, returns)
            perm_ic_pearson = float(base_p) if np.isfinite(base_p) else None

        # ── P2: net metrics (cost estimation) ──────────────────────
        hit_rate_net = None
        mean_return_pct_net = None
        quintile_spread_net = None
        quintile_returns_net = None
        costs_applied = False
        cost_assumptions = None

        if config.apply_costs:
            costs_applied = True
            cost_assumptions = config.cost_model.assumptions_dict()
            cost_bps = config.cost_model.total_bps() / 10000.0

            if n >= 2:
                # Sort by date to simulate sequential position changes
                h_sorted = h_df.sort_values("as_of")
                scores_sorted = h_sorted["signal_score"].to_numpy(dtype=float)
                rets_sorted = h_sorted["forward_return"].to_numpy(dtype=float)

                # Cost is proportional to |score_t - score_t-1| / 50
                # (normalised position change) * cost_bps
                score_norm = (scores_sorted - 50.0) / 50.0
                position_changes = np.diff(score_norm, prepend=score_norm[0])
                cost_per_obs = np.abs(position_changes) * cost_bps
                net_returns = rets_sorted - cost_per_obs

                hit_rate_net = float(np.mean(net_returns > 0))
                mean_return_pct_net = float(np.mean(net_returns)) * 100.0

                q_edges = np.percentile(scores_sorted, [0, 20, 40, 60, 80, 100])
                q_labels_net = ["Q1", "Q2", "Q3", "Q4", "Q5"]
                quintile_returns_net = {}
                for qi in range(5):
                    mask = (scores_sorted >= q_edges[qi]) & (scores_sorted < q_edges[qi + 1])
                    if qi == 4:
                        mask = (scores_sorted >= q_edges[qi]) & (scores_sorted <= q_edges[qi + 1])
                    q_ret = net_returns[mask]
                    quintile_returns_net[q_labels_net[qi]] = (
                        float(np.mean(q_ret)) * 100.0 if len(q_ret) > 0 else 0.0
                    )

                if all(k in quintile_returns_net for k in ("Q5", "Q1")):
                    quintile_spread_net = round(
                        quintile_returns_net["Q5"] - quintile_returns_net["Q1"], 4
                    )

        horizon_results.append(
            HorizonResult(
                horizon_days=h,
                supported=True,
                n_observations=n,
                required_observations=min_obs,
                status="ok",
                ic_rank=ic_rank,
                ic_pearson=ic_pearson,
                hit_rate=round(hit_rate, 4),
                mean_return_pct=round(mean_ret, 4),
                quintile_spread=qt_spread,
                quintile_returns=quintile_returns,
                permutation_ic_rank=perm_ic_rank,
                permutation_ic_pearson=perm_ic_pearson,
                # P2 net metrics
                hit_rate_net=round(hit_rate_net, 4) if hit_rate_net is not None else None,
                mean_return_pct_net=(
                    round(mean_return_pct_net, 4)
                    if mean_return_pct_net is not None else None
                ),
                quintile_spread_net=quintile_spread_net,
                quintile_returns_net=quintile_returns_net,
                costs_applied=costs_applied,
                cost_assumptions=cost_assumptions,
            )
        )

    limits: list[str] = [
        "OHLCV-only: no fundamental/macro/options data used in signal generation",
        "Point-in-time: signals use only data available at as_of (no future leakage)",
        "Signal is the CANONICAL VP composite score from volume_profile.py",
        "Permutation control IC is a sanity check, NOT an investable baseline",
        "Results are diagnostic, not predictive. OOS on real data needed for validation.",
    ]

    if config.apply_costs:
        cost_item = (
            f"Trading costs ESTIMATED: {config.cost_model.total_bps():.0f}bps "
            f"round-trip (slippage={config.cost_model.slippage_bps:.0f}bps, "
            f"spread={config.cost_model.spread_bps:.0f}bps per side). "
            f"Net metrics are estimates, not exact measures."
        )
        limits.insert(2, cost_item)
    else:
        limits.insert(2, "Trading costs/slippage not modeled (gross returns only)")

    if config.diagnostic_only or (build_result and build_result.diagnostic_only):
        limits.insert(0, (
            "DIAGNOSTIC MODE: VP window < canonical 365d. "
            "Results NOT comparable to canonical calibration."
        ))

    if build_result and build_result.status == BacktestBuildStatus.INSUFFICIENT_DATA:
        limits.insert(0, f"INSUFFICIENT DATA: {build_result.reason}")

    return BacktestResult(
        ticker=ticker,
        horizons=horizon_results,
        as_of_range=(as_of_min, as_of_max),
        signal_description=signal_description,
        limits=limits,
        diagnostic_only=(
            config.diagnostic_only
            or (build_result.diagnostic_only if build_result else False)
        ),
        build_status=(
            build_result.status.value if build_result
            else BacktestBuildStatus.OK.value
        ),
        costs_applied=config.apply_costs,
        last_data_date=as_of_max if as_of_max else None,
    )
