"""Optuna-based hyperparameter tuning for the LightGBM trading model.

Uses Purged Walk-Forward Cross-Validation (Lopez de Prado) as the
evaluation framework to avoid nested leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import optuna
import pandas as pd
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from utils.logger import get_logger

logger = get_logger("models.tuner")


@dataclass
class TuningConfig:
    """Configuration knobs for the Optuna tuning run."""

    n_trials: int = 100
    timeout_minutes: int = 30
    n_warmup_steps: int = 10
    direction: str = "maximize"  # maximize Sharpe or minimize val_rmse
    study_name: str = "lgbm_trading"
    storage: Optional[str] = None  # None = in-memory, or "sqlite:///optuna.db"
    random_seed: int = 42


class LGBMTuner:
    """Optuna tuner for LightGBM hyperparameters.

    Optimisation objective: maximise a Sharpe-like proxy derived from the
    average validation RMSE across the walk-forward folds (lower RMSE ->
    higher score).
    """

    def __init__(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        dates: pd.Index,
        config: dict,
        tuning_config: TuningConfig | None = None,
    ) -> None:
        """Store inputs and tuning configuration.

        Parameters
        ----------
        X:
            Feature matrix (rows aligned with ``dates``).
        y:
            Target series (same length as ``X``).
        dates:
            Datetime-like index used to build the walk-forward splits.
        config:
            Full model config dict (as produced by
            ``AppConfig.model_dump(by_alias=True)``).
        tuning_config:
            Optional :class:`TuningConfig` override. Defaults are used when
            ``None``.
        """
        self.X = X
        self.y = y
        self.dates = pd.to_datetime(dates)
        self.config = config  # full model config from config.yaml
        self.tuning = tuning_config or TuningConfig()
        self.study: optuna.Study | None = None
        self.best_params: dict | None = None

    def _suggest_params(self, trial: optuna.Trial) -> dict:
        """Suggest a set of hyperparameters for a trial.

        Spazio di ricerca ragionato per LightGBM trading:

        - ``num_leaves``: [8, 64] — pochi = underfitting, troppi = overfitting
          (per trading si preferiscono alberi piccoli: 16-31)
        - ``learning_rate``: [0.005, 0.1] — log-uniform, piu' lento = meglio
        - ``min_data_in_leaf``: [20, 200] — regolarizzazione potente
        - ``feature_fraction``: [0.5, 1.0] — subsample colonne (anti-overfitting)
        - ``bagging_fraction``: [0.5, 1.0] — subsample righe
        - ``bagging_freq``: [1, 10] — ogni N iterazioni fa bagging
        - ``lambda_l1`` / ``lambda_l2``: [0.0, 3.0] — regolarizzazione L1/L2
        - ``min_gain_to_split``: [0.0, 1.0] — split minimo
        - ``max_depth``: [3, 15] — profondita' albero
        - ``path_smooth``: [0.0, 1.0] — smoothing (nuovo param LGBM)
        """
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 8, 64),
            "learning_rate": trial.suggest_float(
                "learning_rate", 0.005, 0.1, log=True
            ),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 200),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": trial.suggest_int("bagging_freq", 1, 10),
            "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 3.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 3.0),
            "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 1.0),
            "max_depth": trial.suggest_int("max_depth", 3, 15),
            "path_smooth": trial.suggest_float("path_smooth", 0.0, 1.0),
        }
        return params

    def _objective(self, trial: optuna.Trial) -> float:
        """Objective function for Optuna.

        Steps:
          1. Suggest hyperparameters.
          2. Build LightGBM with those params.
          3. Run walk-forward purged CV.
          4. Train on each fold.
          5. Compute average validation Sharpe-proxy across folds.
          6. Return score (higher is better).

        Pruning: if after the folds the score is poor relative to the
        median of trials at the same step, the trial is pruned.
        """
        params = self._suggest_params(trial)
        params.update(
            {
                "objective": "regression",
                "metric": "rmse",
                "boosting_type": "gbdt",
                "verbose": -1,
            }
        )

        from models.lgbm_trainer import LGBMTrainer

        # Create trainer with suggested params
        trainer_config = dict(self.config)
        # ``LGBMTrainer`` expects a nested ``model.params`` dict; replace it
        # while preserving the walk-forward configuration.
        trainer_config["model"] = dict(self.config.get("model", {}))
        trainer_config["model"]["params"] = params
        trainer = LGBMTrainer(trainer_config)

        # Train with walk-forward
        trainer.train(self.X, self.y, self.dates)

        if not trainer.models:
            return float("-inf")  # no valid folds -> skip

        # Compute average Sharpe-proxy across folds from val RMSE
        val_rmses = [m.val_rmse for m in trainer.models]
        avg_rmse = float(np.mean(val_rmses))

        # Convert RMSE to a score: lower RMSE = higher score.
        # Sharpe proxy = (1 - avg_rmse) * 2 - 1
        #   maps 0.5 RMSE -> Sharpe 0, 0.1 RMSE -> Sharpe ~1
        sharpe_proxy = (1.0 - avg_rmse) * 2.0 - 1.0

        # Report intermediate value for pruning
        trial.report(sharpe_proxy, step=len(trainer.models))
        if trial.should_prune():
            raise optuna.TrialPruned()

        return float(sharpe_proxy)

    def run(self) -> dict:
        """Run the Optuna study.

        Returns
        -------
        dict
            Dictionary with keys ``best_params``, ``best_value``, ``study``
            and ``trials_df``.
        """
        sampler = TPESampler(seed=self.tuning.random_seed, n_startup_trials=10)
        pruner = MedianPruner(
            n_startup_trials=10,
            n_warmup_steps=self.tuning.n_warmup_steps,
            interval_steps=1,
        )

        study = optuna.create_study(
            study_name=self.tuning.study_name,
            direction=self.tuning.direction,
            sampler=sampler,
            pruner=pruner,
            storage=self.tuning.storage,
            load_if_exists=True,
        )

        logger.info(
            "Starting Optuna tuning: %d trials (timeout=%d min)",
            self.tuning.n_trials,
            self.tuning.timeout_minutes,
        )

        study.optimize(
            self._objective,
            n_trials=self.tuning.n_trials,
            timeout=self.tuning.timeout_minutes * 60,
            show_progress_bar=True,
        )

        self.study = study
        self.best_params = dict(study.best_params)
        self.best_params.update(
            {
                "objective": "regression",
                "metric": "rmse",
                "boosting_type": "gbdt",
                "verbose": -1,
            }
        )

        logger.info(
            "Tuning complete. Best value: %.4f | Best params: %s",
            study.best_value,
            study.best_params,
        )

        # Log top-5 trials
        df_trials = study.trials_dataframe().sort_values("value", ascending=False)
        logger.info("Top-5 trials:\n%s", df_trials.head(5).to_string())

        return {
            "best_params": self.best_params,
            "best_value": study.best_value,
            "study": study,
            "trials_df": df_trials,
        }


def suggest_params_from_study(
    study: optuna.Study, base_params: dict | None = None
) -> dict:
    """Extract the best params from a completed study and merge with base params.

    Args:
        study: Completed Optuna study.
        base_params: Base parameters to fall back on (e.g. from config.yaml).

    Returns:
        Merged parameter dict ready for :class:`LGBMTrainer`.
    """
    params = dict(base_params or {})
    params.update(study.best_params)
    # Ensure required params are present
    params.setdefault("objective", "regression")
    params.setdefault("metric", "rmse")
    params.setdefault("boosting_type", "gbdt")
    params.setdefault("verbose", -1)
    # Add early stopping / n_estimators — tuning finds best_iter, so set high
    params.setdefault("n_estimators", 1000)
    params.setdefault("early_stopping_rounds", 50)
    return params