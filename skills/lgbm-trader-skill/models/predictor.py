"""Inference wrapper for previously trained LightGBM models.

Loads the pickled ``LGBMTrainer`` (or just its models) and produces an
ensemble score between 0 and 100 for every row of incoming features.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from models.lgbm_trainer import LGBMTrainer
from utils.logger import get_logger

logger = get_logger(__name__)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


class Predictor:
    """Inference on new data using trained models."""

    def __init__(self, model_dir: str | Path) -> None:
        self.model_dir = Path(model_dir)
        self.trainer: Optional[LGBMTrainer] = None
        self._load()

    def _load(self) -> None:
        """Load the most recent ``.pkl`` model in ``model_dir``."""
        if not self.model_dir.exists():
            logger.warning("Model dir %s does not exist", self.model_dir)
            return
        pkls = sorted(self.model_dir.glob("*.pkl"), key=lambda p: p.stat().st_mtime)
        if not pkls:
            logger.warning("No .pkl models found in %s", self.model_dir)
            return
        self.trainer = LGBMTrainer.load(pkls[-1])
        logger.info("Loaded model %s (%d folds)", pkls[-1].name, len(self.trainer.models))

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Generate a 0-100 score per row (ensemble mean over folds).

        The LightGBM regresses a continuous target centred on zero, so the
        raw prediction is squashed by a sigmoid and scaled to 0-100.
        """
        if self.trainer is None or features is None or features.empty:
            return pd.DataFrame(columns=["score", "raw_pred"])

        feature_cols = [
            c
            for c in self.trainer.feature_names
            if c in features.columns
        ] or list(features.columns)
        X = features[feature_cols].copy()
        X = X.fillna(0.0)
        raw = self.trainer.predict(X)
        scores = _sigmoid(raw) * 100.0
        return pd.DataFrame(
            {"score": scores, "raw_pred": raw},
            index=features.index,
        )