"""Configurable scoring weights for the trading engine."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# Default weights file path
DEFAULT_WEIGHTS_PATH = Path(
    os.environ.get(
        "TRADING_WEIGHTS_FILE",
        os.path.join(
            os.environ.get("HOME", str(Path.home())),
            ".config", "opencode", "weights.json",
        ),
    )
)


class StockWeights(BaseModel):
    """Weights for stock analysis dimensions. Must sum to 1.0."""
    wyckoff: float = Field(default=0.20, ge=0.0, le=1.0)
    volume_profile: float = Field(default=0.20, ge=0.0, le=1.0)
    price_action: float = Field(default=0.15, ge=0.0, le=1.0)
    sentiment: float = Field(default=0.20, ge=0.0, le=1.0)
    fundamentals: float = Field(default=0.25, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "StockWeights":
        total = self.wyckoff + self.volume_profile + self.price_action + self.sentiment + self.fundamentals
        if abs(total - 1.0) > 0.01:
            logger.warning("Stock weights sum to %.4f (expected 1.0), normalizing", total)
            if total > 0:
                self.wyckoff /= total
                self.volume_profile /= total
                self.price_action /= total
                self.sentiment /= total
                self.fundamentals /= total
        return self

    def to_dict(self) -> dict[str, float]:
        return {
            "wyckoff": self.wyckoff,
            "volume_profile": self.volume_profile,
            "price_action": self.price_action,
            "sentiment": self.sentiment,
            "fundamentals": self.fundamentals,
        }


class CryptoWeights(BaseModel):
    """Weights for crypto analysis dimensions. Must sum to 1.0."""
    wyckoff: float = Field(default=0.25, ge=0.0, le=1.0)
    volume_profile: float = Field(default=0.25, ge=0.0, le=1.0)
    price_action: float = Field(default=0.20, ge=0.0, le=1.0)
    crypto_apc: float = Field(default=0.30, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "CryptoWeights":
        total = self.wyckoff + self.volume_profile + self.price_action + self.crypto_apc
        if abs(total - 1.0) > 0.01:
            logger.warning("Crypto weights sum to %.4f (expected 1.0), normalizing", total)
            if total > 0:
                self.wyckoff /= total
                self.volume_profile /= total
                self.price_action /= total
                self.crypto_apc /= total
        return self

    def to_dict(self) -> dict[str, float]:
        return {
            "wyckoff": self.wyckoff,
            "volume_profile": self.volume_profile,
            "price_action": self.price_action,
            "sentiment": self.crypto_apc,
        }


class IndicatorWeights(BaseModel):
    """Weights for 11 technical indicators. Each applied as (score-50)×weight."""
    candlestick: float = Field(default=0.10, ge=0.0, le=0.5)
    fibonacci: float = Field(default=0.10, ge=0.0, le=0.5)
    bollinger: float = Field(default=0.10, ge=0.0, le=0.5)
    obv: float = Field(default=0.10, ge=0.0, le=0.5)
    support_resistance: float = Field(default=0.10, ge=0.0, le=0.5)
    psychology: float = Field(default=0.10, ge=0.0, le=0.5)
    ichimoku: float = Field(default=0.06, ge=0.0, le=0.5)
    candlestick_advanced: float = Field(default=0.06, ge=0.0, le=0.5)
    risk_reward: float = Field(default=0.06, ge=0.0, le=0.5)
    psychology_advanced: float = Field(default=0.06, ge=0.0, le=0.5)
    point_figure: float = Field(default=0.06, ge=0.0, le=0.5)


class ModifierScale(BaseModel):
    """Scale factors for modifier adjustments (mtf, sot, squeeze, earnings, clue6)."""
    multi_timeframe: float = Field(default=0.2, ge=0.0, le=1.0)
    sot_weis_wave: float = Field(default=0.2, ge=0.0, le=1.0)
    squeeze_play: float = Field(default=0.2, ge=0.0, le=1.0)
    earnings_surprise: float = Field(default=0.2, ge=0.0, le=1.0)
    clue6_test: float = Field(default=0.2, ge=0.0, le=1.0)


class WeightsConfig(BaseModel):
    """Complete scoring weights configuration."""
    stocks: StockWeights = Field(default_factory=StockWeights)
    crypto: CryptoWeights = Field(default_factory=CryptoWeights)
    indicators: IndicatorWeights = Field(default_factory=IndicatorWeights)
    modifier_scale: ModifierScale = Field(default_factory=ModifierScale)


def load_weights(path: Optional[Path] = None) -> WeightsConfig:
    """Load scoring weights from JSON file, falling back to defaults.

    Args:
        path: Optional path to weights.json. Uses DEFAULT_WEIGHTS_PATH if None.

    Returns:
        WeightsConfig loaded from file, or defaults if file not found/invalid.
    """
    filepath = path or DEFAULT_WEIGHTS_PATH
    if not filepath.exists():
        logger.info("Weights file not found at %s, using defaults", filepath)
        return WeightsConfig()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = WeightsConfig(**data)
        logger.info("Loaded custom weights from %s", filepath)
        return config
    except Exception as e:
        logger.warning("Failed to load weights from %s: %s, using defaults", filepath, e)
        return WeightsConfig()


# Module-level singleton (lazy-loaded on first use)
_weights_singleton: Optional[WeightsConfig] = None


def get_weights() -> WeightsConfig:
    """Get the singleton WeightsConfig, loading on first call."""
    global _weights_singleton
    if _weights_singleton is None:
        _weights_singleton = load_weights()
    return _weights_singleton
