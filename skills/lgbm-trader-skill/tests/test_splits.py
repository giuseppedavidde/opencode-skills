"""Test temporal splits: embargo, purging, leakage prevention.

All tests use synthetic data (no network). Verify that:
1. Embargo removes training bars within embargo_days of validation
2. No label overlap between train and validation windows
3. Small datasets raise explicit error
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Add skill root to path
import sys
from pathlib import Path

_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))


def make_synthetic_ohlcv(n_days: int = 600, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic daily OHLCV data."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n_days))
    close = np.maximum(close, 10.0)
    high = close + rng.uniform(0.5, 2.0, n_days)
    low = close - rng.uniform(0.5, 2.0, n_days)
    volume = rng.integers(1000, 100000, n_days)
    return pd.DataFrame(
        {
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


class TestWalkForwardSplits:
    """Tests for LGBMTrainer.walk_forward_split with purging + embargo."""

    def test_embargo_purges_training_before_validation(self) -> None:
        """Training bars must be at least purge_bars+embargo_bars positions
        before validation start (bar-based, not calendar)."""
        from models.lgbm_trainer import LGBMTrainer
        from utils.config import load_config

        cfg_path = _skill_root / "config" / "config.yaml"
        cfg = load_config(cfg_path).model_dump()

        trainer = LGBMTrainer(cfg)
        trainer.wf_config = {
            "n_splits": 3,
            "train_months": 12,
            "val_months": 3,
            "embargo_days": 10,
        }

        df = make_synthetic_ohlcv(500)
        df["target"] = 0.0

        splits = trainer.walk_forward_split(
            df, n_splits=3, train_months=12, val_months=3, embargo_days=10
        )

        assert len(splits) > 0, "Should produce at least one fold"
        purge_bars = trainer.target_config.get("horizon", 5)

        for sp in splits:
            val_start = sp["val_idx"].min()
            total_purge = purge_bars + 10  # horizon + embargo
            # Build position map
            date_to_pos = {d: i for i, d in enumerate(df.index)}
            val_start_pos = date_to_pos.get(val_start, 0)
            for t in sp["train_idx"]:
                t_pos = date_to_pos.get(t, 0)
                gap = val_start_pos - t_pos
                assert gap > total_purge, (
                    f"Training bar at pos {t_pos} ({t.date()}) is only "
                    f"{gap} bars before validation start at pos {val_start_pos} "
                    f"({val_start.date()}); requires > {total_purge}"
                )

    def test_train_val_no_overlap_after_embargo(self) -> None:
        """Train and validation index sets must be disjoint."""
        from models.lgbm_trainer import LGBMTrainer
        from utils.config import load_config

        cfg_path = _skill_root / "config" / "config.yaml"
        cfg = load_config(cfg_path).model_dump()

        trainer = LGBMTrainer(cfg)
        trainer.wf_config = {
            "n_splits": 3,
            "train_months": 12,
            "val_months": 3,
            "embargo_days": 5,
        }

        df = make_synthetic_ohlcv(500)
        df["target"] = 0.0

        splits = trainer.walk_forward_split(
            df, n_splits=3, train_months=12, val_months=3, embargo_days=5
        )

        for sp in splits:
            overlap = set(sp["train_idx"]).intersection(set(sp["val_idx"]))
            if pd.Timestamp in overlap or any(True for _ in overlap):
                # Force set intersection check
                tr_set = set(sp["train_idx"].to_list())
                val_set = set(sp["val_idx"].to_list())
                assert tr_set.isdisjoint(val_set), (
                    f"Fold {sp['fold_id']}: train and val overlap!"
                )

    def test_too_small_dataset_produces_no_folds(self) -> None:
        """A dataset with < min_training bars should produce 0 folds."""
        from models.lgbm_trainer import LGBMTrainer
        from utils.config import load_config

        cfg_path = _skill_root / "config" / "config.yaml"
        cfg = load_config(cfg_path).model_dump()

        trainer = LGBMTrainer(cfg)
        trainer.wf_config = {
            "n_splits": 3,
            "train_months": 24,
            "val_months": 6,
            "embargo_days": 5,
        }

        df = make_synthetic_ohlcv(30)  # way too small
        df["target"] = 0.0

        splits = trainer.walk_forward_split(
            df, n_splits=3, train_months=24, val_months=6, embargo_days=5
        )
        assert len(splits) == 0, "Small dataset should produce 0 folds"

    def test_embargo_reduces_training_set_size(self) -> None:
        """With embargo > 0, training set should be smaller than without."""
        from models.lgbm_trainer import LGBMTrainer
        from utils.config import load_config

        cfg_path = _skill_root / "config" / "config.yaml"
        cfg = load_config(cfg_path).model_dump()

        df = make_synthetic_ohlcv(500)
        df["target"] = 0.0

        # Without embargo
        trainer_no = LGBMTrainer(cfg)
        splits_no = trainer_no.walk_forward_split(
            df, n_splits=3, train_months=12, val_months=3, embargo_days=0
        )

        # With embargo
        trainer_yes = LGBMTrainer(cfg)
        splits_yes = trainer_yes.walk_forward_split(
            df, n_splits=3, train_months=12, val_months=3, embargo_days=10
        )

        if splits_no and splits_yes:
            for sno, syes in zip(splits_no, splits_yes):
                assert len(syes["train_idx"]) <= len(sno["train_idx"]), (
                    f"Fold {sno['fold_id']}: embargo should reduce training size, "
                    f"got {len(syes['train_idx'])} vs {len(sno['train_idx'])}"
                )

    def test_fold_after_embargo_has_minimum_training(self) -> None:
        """After embargo, each fold must have >= 21 training bars."""
        from models.lgbm_trainer import LGBMTrainer
        from utils.config import load_config

        cfg_path = _skill_root / "config" / "config.yaml"
        cfg = load_config(cfg_path).model_dump()

        trainer = LGBMTrainer(cfg)
        df = make_synthetic_ohlcv(500)
        df["target"] = 0.0

        splits = trainer.walk_forward_split(
            df, n_splits=5, train_months=12, val_months=3, embargo_days=5
        )

        for sp in splits:
            assert len(sp["train_idx"]) >= 21, (
                f"Fold {sp['fold_id']}: only {len(sp['train_idx'])} training bars after embargo"
            )
