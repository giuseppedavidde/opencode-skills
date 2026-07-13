"""Pydantic configuration models for the LightGBM Trading System.

The configuration is loaded from ``config/config.yaml`` and validated via
Pydantic models to guarantee type-safety across the whole pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import yaml
from pydantic import BaseModel, Field


class DataConfig(BaseModel):
    start_date: str = "2018-01-01"
    end_date: Optional[str] = None
    tickers: dict = Field(default_factory=dict)
    macro_tickers: List[str] = Field(default_factory=list)


class FeaturesConfig(BaseModel):
    lookback_days: int = 252
    remove_low_volume: bool = False


class ModelParams(BaseModel):
    objective: str = "regression"
    metric: str = "rmse"
    boosting_type: str = "gbdt"
    num_leaves: int = 31
    learning_rate: float = 0.05
    n_estimators: int = 500
    min_data_in_leaf: int = 50
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 5
    lambda_l1: float = 0.1
    lambda_l2: float = 0.3
    early_stopping_rounds: int = 50
    verbose: int = -1


class WalkForwardConfig(BaseModel):
    n_splits: int = 5
    train_months: int = 24
    val_months: int = 6
    embargo_days: int = 5


class OptionsModelConfig(BaseModel):
    """Configura il modello opzioni (feature VRP / IV / PCR)."""

    enabled: bool = True
    iv_lookback: int = 252
    vrp_lookback: int = 63
    iv_premium_mult: float = 1.2
    iv_premium_add: float = 0.05


class ModelConfig(BaseModel):
    type: str = "lightgbm"
    params: ModelParams = Field(default_factory=ModelParams)
    walk_forward: WalkForwardConfig = Field(default_factory=WalkForwardConfig)
    options: OptionsModelConfig = Field(default_factory=OptionsModelConfig)


class TargetConfig(BaseModel):
    horizon: int = 5
    type: str = "meta_label"
    atr_multiplier: float = 2.0
    pt_sl: List[float] = Field(default_factory=lambda: [0.05, 0.05])


class TradingConfig(BaseModel):
    slippage_bps: int = 2
    commission_bps: int = 3
    min_score_threshold: int = 55
    position_size_pct: float = 0.20
    max_position_pct: float = 0.20
    sizing_mode: str = "binary"
    target_vol_pct: float = 0.15
    neutral_zone: float = 0.05


class StackingConfig(BaseModel):
    enabled: bool = False


class AppConfig(BaseModel):
    data: DataConfig = Field(default_factory=DataConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    stacking: StackingConfig = Field(default_factory=StackingConfig)


def load_config(path: Union[str, Path]) -> AppConfig:
    """Load and validate a YAML config file into an :class:`AppConfig`."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)