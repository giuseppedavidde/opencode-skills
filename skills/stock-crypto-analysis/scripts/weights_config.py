"""
Dimension weights of the stock-crypto-analysis scripts: a view of the trading MCP.

The trading MCP (``mcp/src/trading_mcp``) is the only source of the weights:

- base weights: ``trading_mcp.weights_config.get_weights()`` (defaults, or the user file
  ``~/.config/opencode/weights.json`` / ``$TRADING_WEIGHTS_FILE``);
- regime detection and regime adjustment: ``trading_mcp.analysis.macro``.

This module keeps no number of its own. The old local copy had other weights and other
regime rules, so the local scripts gave a second ``final_score``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_MCP_SRC = Path(__file__).resolve().parents[3] / "mcp" / "src"
if (_MCP_SRC / "trading_mcp").is_dir() and str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

try:
    # pylint: disable=wrong-import-position
    from trading_mcp.analysis.macro import Regime, detect_regime, get_dynamic_weights  # noqa: E402
    from trading_mcp.weights_config import get_weights  # noqa: E402
except ImportError as exc:  # pragma: no cover - environment problem
    raise ImportError(
        "weights_config: the trading MCP package is not importable. Run the script with the "
        "trading MCP venv (~/.local/share/opencode/trading-mcp-venv/bin/python) or from this "
        f"repository. Cause: {exc}"
    ) from exc

BASE_WEIGHTS_STOCK: dict[str, float] = get_weights().stocks.to_dict()
BASE_WEIGHTS_CRYPTO: dict[str, float] = get_weights().crypto.to_dict()

__all__ = ["BASE_WEIGHTS_CRYPTO", "BASE_WEIGHTS_STOCK", "Regime", "detect_regime", "get_dynamic_weights"]
