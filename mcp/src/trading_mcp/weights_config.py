"""Scoring weights of the trading engine: PRIORS, NOT FITTED.

No weight in this module was estimated from data. Every value is a
hand-set prior that states how much a dimension counts in the composite
score. No out-of-sample test supports them (see SIG-08 in the audit);
``analysis/composite.py`` labels every payload ``weights_kind="priors,
not fitted"``.

Structure of the composite (all scores on one 0-100 scale, 50 = neutral):

- :class:`StockWeights` / :class:`CryptoWeights`: weight of each dimension
  in the composite. A dimension without data is left out and the other
  weights are renormalized; the payload reports the covered weight.
- :class:`ComponentWeights`: weight of each component inside its
  dimension (Wyckoff: structure, 6-clue, Weis/SOT, VSA; Price Action: core,
  multi-timeframe, market structure, technical indicators).
- :class:`IndicatorWeights`: weight of each technical indicator inside the
  "technical indicators" component of Price Action.

The user file is ``$TRADING_WEIGHTS_FILE``, else
``$XDG_CONFIG_HOME/opencode/weights.json``, else
``<home>/.config/opencode/weights.json`` where ``<home>`` is ``$HOME`` or,
when ``$HOME`` is unset or empty, the home directory of the user account.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

WEIGHTS_KIND = "priors, not fitted"


def _account_home() -> Path | None:
    """Home directory of the user account, read without ``$HOME``."""
    try:
        import pwd  # pylint: disable=import-outside-toplevel

        home = pwd.getpwuid(os.getuid()).pw_dir
    except (ImportError, KeyError, AttributeError, OSError):
        return None
    return Path(home) if home and os.path.isabs(home) else None


def config_home() -> Path:
    """Base config directory (``$XDG_CONFIG_HOME``, else ``<home>/.config``); never relative."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and os.path.isabs(xdg):
        return Path(xdg)
    home_env = os.environ.get("HOME", "").strip()
    if home_env and os.path.isabs(home_env):
        return Path(home_env) / ".config"
    account = _account_home()
    if account is not None:
        return account / ".config"
    return Path("/") / ".config"


def _default_weights_path() -> Path:
    """Resolve the weights file path without depending on ``$HOME``."""
    env_file = os.environ.get("TRADING_WEIGHTS_FILE", "").strip()
    if env_file:
        return Path(env_file)
    candidates = [config_home() / "opencode" / "weights.json"]
    account = _account_home()
    if account is not None:
        candidates.append(account / ".config" / "opencode" / "weights.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


# Default weights file path
DEFAULT_WEIGHTS_PATH = _default_weights_path()


def _normalize(model: BaseModel, names: tuple[str, ...], label: str) -> None:
    total = sum(getattr(model, name) for name in names)
    if total > 0 and abs(total - 1.0) > 0.01:
        logger.warning("%s weights sum to %.4f (expected 1.0), normalizing", label, total)
        for name in names:
            setattr(model, name, getattr(model, name) / total)


class StockWeights(BaseModel):
    """Prior weight of each stock dimension in the composite. Must sum to 1.0."""

    wyckoff: float = Field(default=0.20, ge=0.0, le=1.0)
    volume_profile: float = Field(default=0.20, ge=0.0, le=1.0)
    price_action: float = Field(default=0.15, ge=0.0, le=1.0)
    sentiment: float = Field(default=0.20, ge=0.0, le=1.0)
    fundamentals: float = Field(default=0.25, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "StockWeights":
        _normalize(self, ("wyckoff", "volume_profile", "price_action", "sentiment", "fundamentals"), "Stock")
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
    """Prior weight of each crypto dimension in the composite. Must sum to 1.0."""

    wyckoff: float = Field(default=0.25, ge=0.0, le=1.0)
    volume_profile: float = Field(default=0.25, ge=0.0, le=1.0)
    price_action: float = Field(default=0.20, ge=0.0, le=1.0)
    crypto_apc: float = Field(default=0.30, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "CryptoWeights":
        _normalize(self, ("wyckoff", "volume_profile", "price_action", "crypto_apc"), "Crypto")
        return self

    def to_dict(self) -> dict[str, float]:
        return {
            "wyckoff": self.wyckoff,
            "volume_profile": self.volume_profile,
            "price_action": self.price_action,
            "crypto_apc": self.crypto_apc,
        }


class IndicatorWeights(BaseModel):
    """Prior weight of each indicator inside the technical-indicator component.

    The weights are renormalized over the indicators with data. ``risk_reward``
    is 0: the trade plan computes reward/risk, so a score would count it twice.
    """

    candlestick: float = Field(default=0.10, ge=0.0, le=0.5)
    fibonacci: float = Field(default=0.10, ge=0.0, le=0.5)
    bollinger: float = Field(default=0.10, ge=0.0, le=0.5)
    obv: float = Field(default=0.10, ge=0.0, le=0.5)
    support_resistance: float = Field(default=0.10, ge=0.0, le=0.5)
    psychology: float = Field(default=0.10, ge=0.0, le=0.5)
    ichimoku: float = Field(default=0.06, ge=0.0, le=0.5)
    candlestick_advanced: float = Field(default=0.06, ge=0.0, le=0.5)
    risk_reward: float = Field(default=0.0, ge=0.0, le=0.5)
    psychology_advanced: float = Field(default=0.06, ge=0.0, le=0.5)
    point_figure: float = Field(default=0.06, ge=0.0, le=0.5)
    taa_patterns: float = Field(default=0.10, ge=0.0, le=0.5)

    def to_dict(self) -> dict[str, float]:
        return dict(self.model_dump())


class ComponentWeights(BaseModel):
    """Prior weight of each component inside its dimension (renormalized over known ones)."""

    wyckoff_structure: float = Field(default=0.40, ge=0.0, le=1.0)
    wyckoff_six_clue: float = Field(default=0.20, ge=0.0, le=1.0)
    wyckoff_weis_sot: float = Field(default=0.20, ge=0.0, le=1.0)
    wyckoff_vsa: float = Field(default=0.20, ge=0.0, le=1.0)
    pa_core: float = Field(default=0.25, ge=0.0, le=1.0)
    pa_multi_timeframe: float = Field(default=0.20, ge=0.0, le=1.0)
    pa_market_structure: float = Field(default=0.20, ge=0.0, le=1.0)
    pa_technical: float = Field(default=0.35, ge=0.0, le=1.0)

    def wyckoff(self) -> dict[str, float]:
        """Component priors of the Wyckoff dimension."""
        return {"structure": self.wyckoff_structure, "six_clue": self.wyckoff_six_clue,
                "weis_sot": self.wyckoff_weis_sot, "vsa": self.wyckoff_vsa}

    def price_action(self) -> dict[str, float]:
        """Component priors of the Price Action dimension."""
        return {"core": self.pa_core, "multi_timeframe": self.pa_multi_timeframe,
                "market_structure": self.pa_market_structure, "technical": self.pa_technical}


class WeightsConfig(BaseModel):
    """Complete scoring weights configuration (priors, not fitted)."""

    stocks: StockWeights = Field(default_factory=StockWeights)
    crypto: CryptoWeights = Field(default_factory=CryptoWeights)
    indicators: IndicatorWeights = Field(default_factory=IndicatorWeights)
    components: ComponentWeights = Field(default_factory=ComponentWeights)
    kind: str = WEIGHTS_KIND


def load_weights(path: Optional[Path] = None) -> WeightsConfig:
    """Load scoring weights from JSON file, falling back to defaults.

    Args:
        path: Optional path to weights.json. Uses DEFAULT_WEIGHTS_PATH if None.

    Returns:
        WeightsConfig loaded from file, or defaults if file not found/invalid.
        Unknown keys (for example the retired ``modifier_scale``) are ignored.
    """
    filepath = path or DEFAULT_WEIGHTS_PATH
    if not filepath.exists():
        logger.info("Weights file not found at %s, using defaults", filepath)
        return WeightsConfig()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("kind", None)
        config = WeightsConfig(**data)
        logger.info("Loaded custom weights from %s", filepath)
        return config
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to load weights from %s: %s, using defaults", filepath, e)
        return WeightsConfig()


# Module-level singleton (lazy-loaded on first use)
_weights_singleton: Optional[WeightsConfig] = None


def get_weights() -> WeightsConfig:
    """Get the singleton WeightsConfig, loading on first call."""
    global _weights_singleton  # pylint: disable=global-statement
    if _weights_singleton is None:
        _weights_singleton = load_weights()
    return _weights_singleton
