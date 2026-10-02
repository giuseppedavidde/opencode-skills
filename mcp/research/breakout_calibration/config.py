"""Static configuration for the breakout calibration study."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR: Path = Path(__file__).resolve().parent
DATA_CACHE_DIR: Path = PACKAGE_DIR / "data_cache"
OUTPUT_DIR: Path = PACKAGE_DIR / "output"

UNIVERSE_CSV: Path = (
    PACKAGE_DIR.parents[1] / "src" / "trading_mcp" / "data" / "historical_universe_sp500.csv"
)

PERIOD_START: str = "2010-01-01"
PERIOD_END: str = "2026-09-30"
IN_SAMPLE_END: str = "2020-12-31"
OUT_OF_SAMPLE_START: str = "2021-01-01"

HORIZONS: tuple[int, ...] = (5, 10, 20, 60, 120)
BREAKOUT_LOOKBACKS: tuple[int, ...] = (20, 50, 63, 126, 252)
VOLUME_MULTIPLES: tuple[float, ...] = (0.0, 1.0, 1.5, 2.0)
ATR_MULTS: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0)
ATR_WINDOW: int = 14
RSI_WINDOW: int = 14
VOLUME_WINDOW: int = 20
MOMENTUM_WINDOW: int = 252

MOMENTUM_METRICS: tuple[str, ...] = ("dist_sma200", "rsi14", "mom12", "ret_1d")
MOMENTUM_QUANTILES: int = 5

BOOTSTRAP_ITERATIONS: int = 1000
BOOTSTRAP_BLOCK_DAYS: int = 20
BOOTSTRAP_SEED: int = 20261002

MIN_HISTORY_DAYS: int = 300
BENCHMARK_SYMBOL: str = "SPY"
BENCHMARK_SMA_WINDOW: int = 200

DOWNLOAD_CHUNK: int = 100
