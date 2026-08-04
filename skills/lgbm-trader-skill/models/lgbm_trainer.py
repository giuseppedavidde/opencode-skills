"""LightGBM trainer with walk-forward purged cross-validation.

Implements the methodology described in Marcos Lopez de Prado's
``Advances in Financial Machine Learning`` (ch. 7-8): walk-forward splits
with purging of overlapping labels and an embargo period after each
validation set to neutralise serial correlation leakage.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd

from data.preprocessor import add_target
from utils.logger import get_logger

logger = get_logger(__name__)


def _sigmoid_np(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid (used to map raw preds → 0-100 score)."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


@dataclass
class FoldResult:
    """Container for a single walk-forward fold."""

    fold_id: int
    model: lgb.LGBMRegressor
    train_idx: pd.Index
    val_idx: pd.Index
    best_iteration: int
    val_rmse: float
    feature_importance: dict[str, float] = field(default_factory=dict)


class LGBMTrainer:
    """LightGBM trainer with walk-forward purged CV (Lopez de Prado)."""

    def __init__(self, config: dict) -> None:
        self.params: dict = dict(config["model"]["params"])
        self.wf_config: dict = dict(config["model"]["walk_forward"])
        self.target_config: dict = dict(config["target"])
        self.models: list[FoldResult] = []
        self.feature_names: list[str] = []

    # ------------------------------------------------------------------ #
    # Target
    # ------------------------------------------------------------------ #
    def create_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """Triple-barrier labelling (Lopez de Prado).

        - Upper / lower barriers set at ``pt_sl * ATR * atr_multiplier``
          above / below the entry close.
        - If upper barrier is touched first -> ``+1`` (long).
        - If lower barrier is touched first -> ``-1`` (short).
        - Vertical barrier reached (neither touched) -> ``0`` (flat).

        The continuous version is also stored as ``target_cont`` for the
        regression objective; the column ``target`` always carries the
        discrete ``{-1, 0, +1}`` label.
        """
        out = add_target(
            df,
            horizon=self.target_config["horizon"],
            atr_multiplier=self.target_config["atr_multiplier"],
            pt_sl=tuple(self.target_config["pt_sl"]),
        )
        # Discretise the existing continuous tanh target into {-1, 0, +1}
        cont = out["target"]
        disc = np.where(cont > 0.2, 1, np.where(cont < -0.2, -1, 0))
        out["target_cont"] = cont
        out["target"] = disc.astype(float)
        n_valid = out["target"].notna().sum()
        logger.info(
            "Triple-barrier target built: %d valid labels (pos=%d, neg=%d, flat=%d)",
            n_valid,
            int((out["target"] == 1).sum()),
            int((out["target"] == -1).sum()),
            int((out["target"] == 0).sum()),
        )
        return out

    # ------------------------------------------------------------------ #
    # Walk-forward splits
    # ------------------------------------------------------------------ #
    def walk_forward_split(
        self,
        df: pd.DataFrame,
        n_splits: Optional[int] = None,
        train_months: Optional[int] = None,
        val_months: Optional[int] = None,
        embargo_days: Optional[int] = None,
    ) -> list[dict]:
        """Build walk-forward folds with purging + embargo.

        Each fold's training window spans ``train_months`` and the
        validation window ``val_months``; the train window slides forward
        by ``val_months`` each iteration. Embargo removes
        ``embargo_days`` from training immediately *after* the validation
        period.
        """
        n_splits = n_splits or self.wf_config["n_splits"]
        tm = train_months or self.wf_config["train_months"]
        vm = val_months or self.wf_config["val_months"]
        embargo = embargo_days if embargo_days is not None else self.wf_config["embargo_days"]

        if df.empty:
            return []

        idx = pd.to_datetime(df.index)
        start, end = idx.min(), idx.max()

        step = vm
        splits: list[dict] = []
        for k in range(n_splits):
            train_start = start
            train_end = train_start + pd.DateOffset(months=tm) - pd.Timedelta(days=1)
            val_start = train_end + pd.Timedelta(days=1)
            val_end = val_start + pd.DateOffset(months=vm) - pd.Timedelta(days=1)
            if val_end > end:
                break

            train_mask = (idx >= train_start) & (idx <= train_end)
            val_mask = (idx >= val_start) & (idx <= val_end)
            train_idx = idx[train_mask]
            val_idx = idx[val_mask]

            if len(train_idx) == 0 or len(val_idx) == 0:
                start = start + pd.DateOffset(months=step)
                continue

            splits.append(
                {"fold_id": k, "train_idx": train_idx, "val_idx": val_idx}
            )
            start = start + pd.DateOffset(months=step)

        # ── Purging (label horizon) + embargo (gap aggiuntivo) ──
        # Per Lopez de Prado AFML ch.7:
        #   PURGE:  rimuovi training bar a posizione t se la label
        #           a t "vede" dentro la validation (t+horizon >= val_start).
        #           Il numero di barre da rimuovere è l'horizon della label.
        #   EMBARGO: gap aggiuntivo in barre di trading dopo la validation,
        #            per decorrelare serialmente training e test.
        #
        # Usiamo le posizioni intere nell'indice temporale (barre di trading),
        # NON giorni di calendario. Questo garantisce che nessuna label
        # training "sbordi" nella validation window.
        purge_bars: int = int(self.target_config.get("horizon", 5))
        embargo_bars: int = max(embargo, 0)
        total_purge: int = purge_bars + embargo_bars

        if total_purge > 0:
            date_to_pos: dict = {d: i for i, d in enumerate(idx)}
            purged_folds: list[dict] = []
            for sp in splits:
                val_start = sp["val_idx"].min()
                val_start_pos = date_to_pos.get(val_start, 0)
                cutoff_pos = val_start_pos - total_purge
                purged_train = [
                    d for d in sp["train_idx"]
                    if date_to_pos.get(d, 0) < cutoff_pos
                ]
                if len(purged_train) < 21:
                    logger.warning(
                        "Fold %d: purging+embargo (%d+%d bars) leaves "
                        "only %d training bars (<21), skipping fold",
                        sp["fold_id"],
                        purge_bars,
                        embargo_bars,
                        len(purged_train),
                    )
                    continue
                sp["train_idx"] = pd.DatetimeIndex(purged_train)
                sp["purge_bars"] = purge_bars
                sp["embargo_bars"] = embargo_bars
                purged_folds.append(sp)
            splits = purged_folds

        logger.info(
            "Walk-forward produced %d folds "
            "(purge=%d bars, embargo=%d bars)",
            len(splits),
            purge_bars if total_purge > 0 else 0,
            embargo_bars if total_purge > 0 else 0,
        )
        return splits

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def train(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series) -> None:
        """Run the full walk-forward training loop.

        For every fold:
          1. split train/val (already purged by construction),
          2. train LightGBM with early stopping on the validation set,
          3. store the model, best_iteration, val rmse and feature importance.
        """
        if X.empty or y.empty:
            logger.warning("Empty training data, nothing to do")
            return

        X = X.copy()
        y = y.copy()
        X.index = pd.to_datetime(dates.values if hasattr(dates, "values") else dates)
        y.index = X.index
        work = pd.concat([X, y.rename("target")], axis=1).dropna(subset=["target"])

        splits = self.walk_forward_split(work)
        if not splits:
            logger.warning("No valid folds, aborting training")
            return

        self.feature_names = list(X.columns)
        for sp in splits:
            tr_idx = sp["train_idx"]
            val_idx = sp["val_idx"]
            X_train = work.loc[tr_idx, X.columns]
            y_train = work.loc[tr_idx, "target"]
            X_val = work.loc[val_idx, X.columns]
            y_val = work.loc[val_idx, "target"]
            if len(X_train) == 0 or len(X_val) == 0:
                continue
            res = self.train_fold(
                X_train, y_train, X_val, y_val, train_idx=tr_idx, val_idx=val_idx
            )
            res.fold_id = sp["fold_id"]
            self.models.append(res)
            logger.info(
                "Fold %d trained | best_iter=%d val_rmse=%.5f",
                res.fold_id,
                res.best_iteration,
                res.val_rmse,
            )

    def train_fold(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        train_idx: Optional[pd.Index] = None,
        val_idx: Optional[pd.Index] = None,
    ) -> FoldResult:
        """Train a single LightGBM model with early stopping on ``X_val``.

        Parameters
        ----------
        X_train, y_train, X_val, y_val:
            Train/validation frames for this fold.
        train_idx, val_idx:
            Optional index labels for the train/val windows. When provided
            they are stored on the returned :class:`FoldResult` so callers
            (e.g. the stacking ensemble) can reconstruct out-of-fold
            predictions mapped back to the original frame.
        """
        params = dict(self.params)
        n_estimators = int(params.pop("n_estimators", 500))
        early_stopping = int(params.pop("early_stopping_rounds", 50))
        verbose = int(params.pop("verbose", -1))

        model = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            early_stopping_rounds=early_stopping,
            verbosity=verbose,
            **params,
        )
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.log_evaluation(0)],
        )
        preds = model.predict(X_val)
        rmse = float(np.sqrt(np.mean((preds - y_val.to_numpy()) ** 2)))
        importance = dict(zip(X_train.columns, model.feature_importances_.tolist()))
        return FoldResult(
            fold_id=-1,
            model=model,
            train_idx=pd.Index(train_idx) if train_idx is not None else pd.Index([]),
            val_idx=pd.Index(val_idx) if val_idx is not None else pd.Index([]),
            best_iteration=int(model.best_iteration_ or n_estimators),
            val_rmse=rmse,
            feature_importance=importance,
        )

    # ------------------------------------------------------------------ #
    # Param management
    # ------------------------------------------------------------------ #
    def set_params(self, params: dict) -> None:
        """Update model params (e.g. after Optuna tuning).

        Parameters
        ----------
        params:
            Dictionary of LightGBM hyperparameters to merge into the
            current ``self.params``. Existing keys are overwritten.
        """
        self.params.update(params)

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #
    def predict(self, X: pd.DataFrame, fold_idx: int = -1) -> np.ndarray:
        """Predict with a single model (``fold_idx``) or average across all."""
        if X is None or X.empty:
            return np.array([])
        if not self.models:
            raise RuntimeError("No trained models available")
        if fold_idx >= 0:
            return self.models[fold_idx].model.predict(X)
        preds = np.column_stack([m.model.predict(X) for m in self.models])
        return preds.mean(axis=1)

    def predict_oof(self, X: pd.DataFrame) -> pd.Series:
        """Generate out-of-fold predictions for the whole frame.

        For every fold, the model trained on that fold predicts ONLY on the
        validation window it was never trained on. Each bar therefore
        receives *at most* one prediction — the one made by the model whose
        validation window contained that bar. Bars never assigned to any
        validation set stay ``NaN`` (typically the first ``train_months``
        of history).

        Parameters
        ----------
        X:
            Full feature frame indexed by trading date (same index used
            for :meth:`train`).

        Returns
        -------
        pandas.Series
            Indexed by ``X.index``; OOF raw predictions where available,
            ``NaN`` everywhere else.
        """
        if X is None or X.empty:
            return pd.Series(dtype=float)
        oof = pd.Series(np.nan, index=X.index, dtype=float, name="oof_pred")
        for fr in self.models:
            val_idx = fr.val_idx
            if val_idx is None or len(val_idx) == 0:
                continue
            mask = X.index.isin(val_idx)
            if not mask.any():
                continue
            X_val = X.loc[mask]
            if X_val.empty:
                continue
            preds = fr.model.predict(X_val.fillna(0.0))
            oof.loc[mask] = preds
        n_oof = int(oof.notna().sum())
        logger.info(
            "OOF predictions: %d/%d bars covered (%.1f%%)",
            n_oof,
            len(oof),
            100.0 * n_oof / max(1, len(oof)),
        )
        return oof

    def predict_oof_with_atr(
        self, X: pd.DataFrame, df_full: pd.DataFrame
    ) -> pd.DataFrame:
        """Return OOF predictions enriched with ATR for vol-target sizing.

        Like :meth:`predict_oof` but returns a DataFrame that also carries
        the percentage ATR and its annualised version so the backtest
        engine can scale positions by current volatility (Moskowitz-style
        vol-targeting).

        Parameters
        ----------
        X:
            Full feature frame (same as :meth:`predict_oof`).
        df_full:
            Original DataFrame containing at least a ``close`` column
            and (optionally) an ``atr`` column. When ``atr`` is missing
            we fall back to a 14-day Wilder ATR computed on the fly.

        Returns
        -------
        pandas.DataFrame
            Columns: ``score`` (0-100, NaN where no OOF pred available),
            ``atr_pct`` (atr / close), ``vol_annualized``.
        """
        oof = self.predict_oof(X)
        out = pd.DataFrame(index=X.index)
        out["score"] = _sigmoid_np(oof.fillna(0.0).to_numpy()) * 100.0
        # Restore NaN where OOF was unavailable so downstream code can mask
        out.loc[oof.isna(), "score"] = np.nan

        if "close" not in df_full.columns:
            logger.warning("predict_oof_with_atr: 'close' not in df_full, skipping ATR")
            return out

        close = df_full["close"].reindex(X.index)
        if "atr" in df_full.columns:
            atr = df_full["atr"].reindex(X.index)
        else:
            logger.info("predict_oof_with_atr: 'atr' column missing, computing Wilder ATR(14)")
            atr = self._compute_atr(df_full, window=14).reindex(X.index)
        atr = atr.replace(0.0, np.nan)
        out["atr_pct"] = atr / close
        out["vol_annualized"] = out["atr_pct"] * np.sqrt(252)
        return out

    @staticmethod
    def _compute_atr(
        df_full: pd.DataFrame, window: int = 14
    ) -> pd.Series:
        """Wilder-style ATR helper (re-uses data.preprocessor.compute_atr)."""
        from data.preprocessor import compute_atr  # local import to avoid cycle

        if "high" not in df_full.columns or "low" not in df_full.columns:
            return pd.Series(np.nan, index=df_full.index)
        return compute_atr(
            df_full["high"], df_full["low"], df_full["close"], window=window
        )

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path) -> None:
        """Pickle the trainer state (models + feature names)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(
                {
                    "feature_names": self.feature_names,
                    "models": self.models,
                    "params": self.params,
                    "wf_config": self.wf_config,
                    "target_config": self.target_config,
                },
                fh,
            )
        logger.info("Trainer saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "LGBMTrainer":
        """Reconstruct a trainer previously saved via :meth:`save`."""
        path = Path(path)
        with path.open("rb") as fh:
            state = pickle.load(fh)
        inst = cls.__new__(cls)
        inst.params = state["params"]
        inst.wf_config = state["wf_config"]
        inst.target_config = state["target_config"]
        inst.models = state["models"]
        inst.feature_names = state["feature_names"]
        return inst

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def feature_importance_df(self) -> pd.DataFrame:
        """Aggregate per-fold feature importance into a single DataFrame."""
        if not self.models:
            return pd.DataFrame()
        rows = []
        for m in self.models:
            rows.append(pd.Series(m.feature_importance, name=f"fold_{m.fold_id}"))
        df = pd.DataFrame(rows).fillna(0.0)
        df.loc["mean"] = df.mean(axis=0)
        return df.sort_values(axis=1, by="mean", ascending=False)
