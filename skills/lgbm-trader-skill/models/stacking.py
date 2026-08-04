"""Ensemble stacking per decorrelare e combinare segnali di trading.

Train 5 LightGBM specializzati su feature set diversi (tecnico, macro,
opzioni, decorrelato, completo) e un meta-modello che apprende come pesarli.

Architettura::

    Level-1 (walk-forward purged CV, OOF predictions raccolte per ogni fold)
        tech_model    -> pred_tech    (OHLCV features)
        macro_model   -> pred_macro   (VIX/DXY/yields features)
        options_model -> pred_options (VRP, PCR, IV proxy features)
        decorr_model  -> pred_decorr  (short interest, relative strength, valutation)
        full_model    -> pred_full    (all features)

    Level-2 (LightGBM)
        meta_model.fit([pred_tech, pred_macro, pred_options, pred_decorr,
                        pred_full] -> target)

L'idea e' che ogni modello base catturi una "view" parziale del mercato
(tecnica, macro, opzioni, decorrelata, combinata). Il meta-modello impara a
pesare dinamicamente le view invece di fare una media fissa, riducendo
l'overfitting ai singoli feature set. Il modello opzioni e' decorrelato dal
tecnico perche' usa feature diverse (IV, VRP, put/call, skew); il modello
``decorr`` e' ulteriormente decorrelato perche' usa feature NON derivabili da
OHLCV (short interest, relative strength vs benchmark e fondamentale).
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.special import expit as sigmoid
from scipy.stats import spearmanr

from models.lgbm_trainer import FoldResult, LGBMTrainer
from utils.logger import get_logger

logger = get_logger("models.stacking")


@dataclass
class StackingResult:
    """Risultato del training stacking."""

    tech_model: Optional[LGBMTrainer]
    macro_model: Optional[LGBMTrainer]
    full_model: Optional[LGBMTrainer]
    options_model: Optional[LGBMTrainer]
    decorr_model: Optional[LGBMTrainer]
    meta_model: Optional[lgb.LGBMRegressor]
    feature_names: list[str]
    train_date: str
    metrics: dict


class StackingEnsemble:
    """Ensemble stacking a 2 livelli.

    Livello 1: 5 LightGBM specializzati (tecnico, macro, opzioni, decorrelato,
    completo).
    Livello 2: LightGBM che combina le OOF predictions dei modelli base.

    Il training usa walk-forward purged CV a livello 1, poi le OOF
    (out-of-fold) predictions vengono usate per trainare il meta-modello.
    """

    # Prefissi delle famiglie di feature
    TECH_PREFIXES: list[str] = [
        "mom_",
        "trend_",
        "vol_",
        "prc_",
        "ms_",
        "fd_",
    ]
    MACRO_PREFIXES: list[str] = ["macro_"]
    OPTIONS_PREFIXES: list[str] = ["opt_"]
    DECORR_PREFIXES: list[str] = ["si_", "rs_", "val_"]

    def __init__(self, config: dict) -> None:
        self.config: dict = config
        self.models: dict[str, LGBMTrainer] = {}
        self.meta_model: Optional[lgb.LGBMRegressor] = None
        self.feature_groups: dict[str, list[str]] = {
            "tech": [],
            "macro": [],
            "full": [],
            "options": [],
            "decorr": [],
        }
        self.oof_preds: Optional[dict[str, np.ndarray]] = None
        self.oof_index: Optional[pd.Index] = None
        self.result: Optional[StackingResult] = None

    # ------------------------------------------------------------------ #
    # Feature grouping
    # ------------------------------------------------------------------ #
    @staticmethod
    def split_feature_groups(df: pd.DataFrame) -> dict[str, list[str]]:
        """Divide le colonne feature in gruppi in base al prefisso.

        Returns
        -------
        dict
            Chiavi ``tech``, ``macro``, ``options``, ``full`` mappate alle
            rispettive liste di colonne. ``full`` contiene TUTTE le feature
            valide (esclude target, OHLCV e colonne derivate dal modello).
        """
        exclude = {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "target",
            "target_cont",
            "atr",
            "raw_pred",
            "score",
        }
        all_cols = [c for c in df.columns if c not in exclude]

        tech = [
            c
            for c in all_cols
            if any(c.startswith(p) for p in StackingEnsemble.TECH_PREFIXES)
        ]
        macro = [
            c
            for c in all_cols
            if any(c.startswith(p) for p in StackingEnsemble.MACRO_PREFIXES)
        ]
        options = [
            c
            for c in all_cols
            if any(c.startswith(p) for p in StackingEnsemble.OPTIONS_PREFIXES)
        ]
        decorr = [
            c
            for c in all_cols
            if any(c.startswith(p) for p in StackingEnsemble.DECORR_PREFIXES)
        ]
        full = list(all_cols)

        logger.info(
            "Feature groups: tech=%d, macro=%d, options=%d, decorr=%d, full=%d",
            len(tech),
            len(macro),
            len(options),
            len(decorr),
            len(full),
        )
        return {"tech": tech, "macro": macro, "options": options, "decorr": decorr, "full": full}

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def oof_mask(self, df: pd.DataFrame) -> pd.Series:
        """Boolean Series marking bars covered by out-of-fold predictions.

        A bar is ``True`` when every base model has an OOF prediction for it
        — equivalently, when the meta-model's training matrix (`meta_X`)
        contained that row. Bars that were inside the training window of all
        base models (and thus never in any validation window) are ``False``.

        Parameters
        ----------
        df:
            Reference frame (only its index is used to align the output).

        Returns
        -------
        pandas.Series
            Boolean series aligned to ``df.index``.
        """
        if self.oof_index is None:
            logger.warning("oof_mask: no stored OOF index — returning all-True mask (legacy behaviour)")
            return pd.Series(True, index=df.index)
        mask = pd.Series(False, index=df.index)
        mask.loc[mask.index.isin(self.oof_index)] = True
        return mask
    def train(
        self,
        df: pd.DataFrame,
        feature_cols: list[str],
        dates: pd.Index,
        config: dict,
    ) -> StackingResult:
        """Esegue il training completo dello stacking ensemble.

        Steps:
            1. Divide le feature in gruppi (tech, macro, options, full).
            2. Per ogni gruppo allena :class:`LGBMTrainer` con walk-forward.
            3. Raccoglie le OOF predictions di ogni modello base.
            4. Allena il meta-modello (LightGBM) sulle OOF predictions.
            5. Calcola le metriche di ensemble.

        Parameters
        ----------
        df:
            DataFrame con feature + target.
        feature_cols:
            Tutte le feature columns disponibili (usato solo per sanity check;
            i gruppi vengono derivati dai prefissi delle colonne).
        dates:
            Indice temporale della frame.
        config:
            Configurazione completa (model, target, walk_forward, ...).

        Returns
        -------
        StackingResult
            Modelli base, meta-modello e metriche aggregate.
        """
        del feature_cols  # i grupppi dipendono dai prefissi, non da questa lista
        self.feature_groups = self.split_feature_groups(df)
        self.oof_preds = {}
        oof_matrix = pd.DataFrame(index=df.index)

        # --- Livello 1: 4 modelli specializzati ------------------------ #
        for name, feats in [
            ("tech", self.feature_groups["tech"]),
            ("macro", self.feature_groups["macro"]),
            ("options", self.feature_groups["options"]),
            ("decorr", self.feature_groups.get("decorr", [])),
            ("full", self.feature_groups["full"]),
        ]:
            if not feats:
                logger.warning("No features for group '%s', skipping", name)
                continue

            X = df[feats]
            y = df["target"]

            trainer = LGBMTrainer(config)
            trainer.train(X, y, dates)
            if not trainer.models:
                logger.warning("Group '%s' produced no models, skipping", name)
                continue
            self.models[name] = trainer

            oof = self._collect_oof_predictions(df, feats, trainer.models)
            oof_matrix[f"pred_{name}"] = oof
            self.oof_preds[name] = oof
            logger.info(
                "Stacking level-1 '%s': OOF preds collected (non-NaN=%d)",
                name,
                int(np.sum(~np.isnan(oof))),
            )

        if oof_matrix.dropna().empty:
            raise RuntimeError(
                "Stacking produced no OOF predictions — "
                "check the feature set / walk-forward configuration"
            )

        # --- Livello 2: meta-modello ----------------------------------- #
        meta_X = oof_matrix.dropna()
        meta_y = df.loc[meta_X.index, "target"]
        self.oof_index = meta_X.index
        logger.info("Meta-model training data: %d rows", len(meta_X))

        if len(meta_X) < 50:
            raise RuntimeError(
                f"Meta-model requires at least 50 OOF rows, got {len(meta_X)}. "
                "Increase data history or reduce walk-forward parameters."
            )

        self.meta_model, meta_holdout_idx = self._train_meta_model(meta_X, meta_y)

        # --- Metriche ensemble (SOLO su holdout temporale) ------------- #
        meta_holdout_X = meta_X.loc[meta_holdout_idx]
        meta_holdout_y = meta_y.loc[meta_holdout_idx]

        if len(meta_holdout_X) < 10:
            logger.warning(
                "Meta holdout has only %d rows (<10) — metrics unreliable",
                len(meta_holdout_X),
            )

        meta_importance = dict(
            zip(meta_X.columns, self.meta_model.feature_importances_.tolist())
        )

        # IC e Sharpe proxy sul SOLO holdout
        holdout_preds = self.meta_model.predict(meta_holdout_X.fillna(0.0))
        corr, _ = spearmanr(holdout_preds, meta_holdout_y.fillna(0.0))
        ic = float(corr) if np.isfinite(corr) else 0.0

        pnl_proxy = holdout_preds * meta_holdout_y.fillna(0.0).to_numpy()
        std = float(np.std(pnl_proxy))
        sharpe_proxy = float(np.mean(pnl_proxy) / std) if std > 0 else 0.0

        result = StackingResult(
            tech_model=self.models.get("tech"),
            macro_model=self.models.get("macro"),
            full_model=self.models.get("full"),
            options_model=self.models.get("options"),
            decorr_model=self.models.get("decorr"),
            meta_model=self.meta_model,
            feature_names=list(meta_X.columns),
            train_date=pd.Timestamp.now().strftime("%Y-%m-%d"),
            metrics={
                "meta_sharpe_proxy": sharpe_proxy,
                "spearman_ic": ic,
                "n_meta_samples": int(len(meta_X)),
                "n_holdout_samples": int(len(meta_holdout_X)),
                "meta_feature_importance": meta_importance,
            },
        )
        self.result = result
        logger.info(
            "Stacking complete. Holdout IC=%.4f, Sharpe=%.4f (%d rows). "
            "Meta-model weights: %s",
            ic,
            sharpe_proxy,
            len(meta_holdout_X),
            meta_importance,
        )
        return result

    @staticmethod
    def _collect_oof_predictions(
        df: pd.DataFrame,
        feats: list[str],
        fold_results: list[FoldResult],
    ) -> np.ndarray:
        """Raccoglie le out-of-fold predictions per un singolo modello base.

        Per ogni fold, predice sul validation window usando il modello di
        quel fold (mai sul train window). Ala fine ogni riga del frame
        originale riceve AL PIU' una prediction (quella del fold in cui era
        nel validation set).
        """
        oof = np.full(len(df), np.nan, dtype=float)
        for fr in fold_results:
            val_idx = fr.val_idx
            if val_idx is None or len(val_idx) == 0:
                continue
            mask = df.index.isin(val_idx)
            X_val = df.loc[mask, feats]
            if X_val.empty:
                continue
            oof[mask] = fr.model.predict(X_val.fillna(0.0))
        return oof

    @staticmethod
    def _train_meta_model(
        meta_X: pd.DataFrame,
        meta_y: pd.Series,
    ) -> tuple[lgb.LGBMRegressor, pd.Index]:
        """Allena il meta-modello LightGBM sulle OOF predictions.

        Holdout 20% finale temporale: il meta-modello NON vede mai queste
        righe durante il training. Le metriche ensemble (IC, Sharpe proxy)
        vengono calcolate SOLO su questo holdout.

        I 5 modelli base producono al massimo 5 colonne (pred_tech,
        pred_macro, pred_options, pred_decorr, pred_full). Il meta-modello
        è regolarizzato con ``num_leaves=8`` + ``lambda_l2`` per evitare
        overfitting su poche feature.

        Returns
        -------
        tuple
            (meta_model, holdout_index) — il modello addestrato e l'indice
            delle righe tenute fuori per le metriche ensemble.
        """
        meta_params = {
            "objective": "regression",
            "metric": "rmse",
            "boosting_type": "gbdt",
            "num_leaves": 8,
            "learning_rate": 0.02,
            "n_estimators": 200,
            "min_data_in_leaf": 20,
            "feature_fraction": 1.0,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "lambda_l1": 0.1,
            "lambda_l2": 0.5,
            "verbose": -1,
        }

        split_idx = int(len(meta_X) * 0.8)
        X_train = meta_X.iloc[:split_idx]
        y_train = meta_y.iloc[:split_idx]
        X_val = meta_X.iloc[split_idx:]
        y_val = meta_y.iloc[split_idx:]
        holdout_idx = meta_X.index[split_idx:]

        model = lgb.LGBMRegressor(**meta_params)
        if len(X_val) > 0:
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.log_evaluation(0), lgb.early_stopping(20, False)],
            )
        else:
            model.fit(X_train, y_train, callbacks=[lgb.log_evaluation(0)])
        return model, holdout_idx

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Genera la predizione ensemble completa.

        Per ogni riga in ``df``:
            1. Predici con il modello tech -> ``pred_tech``.
            2. Predici con il modello macro -> ``pred_macro`` (se presente).
            3. Predici con il modello options -> ``pred_options`` (se presente).
            4. Predici con il modello decorr -> ``pred_decorr`` (se presente).
            5. Predici con il modello full -> ``pred_full``.
            6. Combina con il meta-modello -> ``pred_final``.
            7. ``score`` = sigmoid(``pred_final``) * 100.

        Returns
        -------
        pandas.DataFrame
            Colonne ``[pred_tech, pred_macro, pred_options, pred_decorr,
            pred_full, pred_final, score]`` (alcune possono mancare se il
            modello base corrispondente non e' stato trainato).
        """
        result = pd.DataFrame(index=df.index)

        for name in ("tech", "macro", "options", "decorr", "full"):
            trainer = self.models.get(name)
            if trainer is None:
                continue
            feats = self.feature_groups.get(name, [])
            if not feats:
                continue
            preds = trainer.predict(df[feats].fillna(0.0))
            result[f"pred_{name}"] = preds

        if self.meta_model is not None:
            meta_input = result.dropna()
            if not meta_input.empty:
                meta_pred = self.meta_model.predict(meta_input.fillna(0.0))
                result["pred_final"] = np.nan
                result.loc[meta_input.index, "pred_final"] = meta_pred
                result["score"] = sigmoid(np.clip(meta_pred, -10, 10)) * 100.0
        return result

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path) -> None:
        """Salva l'intero ensemble (3 modelli + meta-modello + config)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "models": self.models,
            "meta_model": self.meta_model,
            "feature_groups": self.feature_groups,
            "config": self.config,
            "result": self.result,
            "date": pd.Timestamp.now().isoformat(),
        }
        with path.open("wb") as f:
            pickle.dump(data, f)
        logger.info("Stacking ensemble saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "StackingEnsemble":
        """Carica un ensemble salvato in precedenza."""
        with Path(path).open("rb") as f:
            data = pickle.load(f)
        ensemble = cls(data["config"])
        ensemble.models = data["models"]
        ensemble.meta_model = data["meta_model"]
        ensemble.feature_groups = data["feature_groups"]
        ensemble.result = data["result"]
        return ensemble

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def feature_importance_df(self) -> pd.DataFrame:
        """Restituisce un DataFrame con la feature importance aggregata.

        Una colonna per ogni modello base (mean importance across folds) e
        una colonna ``meta`` con i pesi impliciti del meta-modello.
        """
        rows: dict[str, pd.Series] = {}
        for name, trainer in self.models.items():
            imp = trainer.feature_importance_df()
            if not imp.empty and "mean" in imp.index:
                rows[name] = imp.loc["mean"]

        if (
            self.meta_model is not None
            and hasattr(self.meta_model, "feature_importances_")
            and self.result is not None
        ):
            meta_feats = self.result.feature_names
            meta_imp = dict(
                zip(meta_feats, self.meta_model.feature_importances_.tolist())
            )
            rows["meta"] = pd.Series(meta_imp)

        return pd.DataFrame(rows) if rows else pd.DataFrame()