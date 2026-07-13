"""Structured logging utilities for the LightGBM Trading System."""

from __future__ import annotations

import logging
import sys
from typing import Optional

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED: bool = False


def _configure_root(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with structured formatting.

    Parameters
    ----------
    name:
        Logger name (usually ``__name__`` of the calling module).
    level:
        Logging level for this specific logger.
    """
    _configure_root()
    logger = logging.getLogger(name if name else "lgbm_trader")
    logger.setLevel(level)
    return logger