"""Universe metadata: source, as_of, historical vs current, survivorship.

P1 August 2026: explicit metadata on ticker universes so that
backtests know when they're using a current-snapshot CSV vs a
historical point-in-time constituents file.
"""

from __future__ import annotations

from datetime import datetime  # noqa: F401  # keep for future use
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UniverseType(str, Enum):
    """Whether this is a current or historical universe."""

    CURRENT = "current"
    HISTORICAL = "historical"


class UniverseMetadata(BaseModel):
    """Metadata for a ticker universe.

    Attributes:
        name: Universe name (us_large, us_tech, italy, ...).
        source: File or URL the tickers were sourced from.
        as_of: Date the ticker list was compiled.
        universe_type: current or historical.
        survivorship_warning: True if the universe does NOT
            account for delisted/dead tickers.
        historical_universe_available: True if a point-in-time
            historical constituents file exists (for backtests).
        notes: Any additional notes.
    """

    name: str
    source: str = ""
    as_of: Optional[str] = None
    universe_type: UniverseType = UniverseType.CURRENT
    survivorship_warning: bool = True
    historical_universe_available: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def is_suitable_for_backtest(self) -> bool:
        """True if the universe can be used for unbiased backtests.

        A universe is suitable if:
        - It is historical (point-in-time), OR
        - It explicitly flags survivorship_warning=False.
        """
        if self.universe_type == UniverseType.HISTORICAL:
            return True
        return not self.survivorship_warning


# ── Registry of known universes with metadata ──────────────────────────

_UNIVERSE_REGISTRY: dict[str, UniverseMetadata] = {
    "us_large": UniverseMetadata(
        name="us_large",
        source="market-accumulation-scanner/data/us_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[
            "Current snapshot: includes only surviving tickers.",
            "BACKTESTS SHOULD NOT USE THIS without point-in-time constituents.",
            "Survivorship bias: delisted stocks from earlier periods are absent.",
        ],
    ),
    "us_tech": UniverseMetadata(
        name="us_tech",
        source="market-accumulation-scanner/data/us_tech_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[
            "Subset of us_large filtered to tech sector.",
            "Same survivorship caveats as parent universe.",
        ],
    ),
    "italy": UniverseMetadata(
        name="italy",
        source="market-accumulation-scanner/data/italy_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[
            "Milan-listed stocks. Subject to delisting bias.",
        ],
    ),
    "germany": UniverseMetadata(
        name="germany",
        source="market-accumulation-scanner/data/germany_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[],
    ),
    "france": UniverseMetadata(
        name="france",
        source="market-accumulation-scanner/data/france_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[],
    ),
    "uk": UniverseMetadata(
        name="uk",
        source="market-accumulation-scanner/data/uk_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[],
    ),
    "spain": UniverseMetadata(
        name="spain",
        source="market-accumulation-scanner/data/spain_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[],
    ),
    "all": UniverseMetadata(
        name="all",
        source="market-accumulation-scanner/data/{us,italy,etc.}_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[
            "Aggregate of current CSV snapshots.",
            "No historical point-in-time constituents available.",
        ],
    ),
    "crypto": UniverseMetadata(
        name="crypto",
        source="market-accumulation-scanner/data/crypto_tickers.csv",
        as_of="2026-06-28",
        universe_type=UniverseType.CURRENT,
        survivorship_warning=True,
        historical_universe_available=False,
        notes=[
            "Crypto tickers from CoinGecko.",
        ],
    ),
}


def get_universe_metadata(name: str) -> Optional[UniverseMetadata]:
    """Return metadata for a known universe, or None."""
    return _UNIVERSE_REGISTRY.get(name)


def register_universe_metadata(meta: UniverseMetadata) -> None:
    """Register or overwrite universe metadata."""
    _UNIVERSE_REGISTRY[meta.name] = meta


def check_backtest_universe(name: str) -> tuple[bool, str]:
    """Check whether a universe is suitable for unbiased backtests.

    Args:
        name: Universe name.

    Returns:
        (is_suitable, reason) — is_suitable is True only if
        historical constituents exist or survivorship_warning is False.
        reason explains the verdict.
    """
    meta = get_universe_metadata(name)
    if meta is None:
        return False, (
            f"Universe '{name}' not found in registry. "
            "Cannot verify survivorship bias status."
        )

    if meta.universe_type == UniverseType.HISTORICAL:
        return True, (
            f"Universe '{name}' has historical point-in-time "
            "constituents — suitable for backtests."
        )

    if meta.survivorship_warning and not meta.historical_universe_available:
        return False, (
            f"Universe '{name}' is a current snapshot with survivorship bias. "
            "For unbiased backtests, provide historical_universe_file (point-in-time "
            "constituents CSV). Without it, results are flagged as biased."
        )

    return True, f"Universe '{name}' is suitable for backtests."


def historical_universe_unavailable_message(universe: str) -> str:
    """Build the blocking warning message for missing historical universe."""
    meta = get_universe_metadata(universe)
    meta_note = ""
    if meta and meta.notes:
        meta_note = " Notes: " + "; ".join(meta.notes)
    return (
        f"historical_universe_unavailable: '{universe}' is a current-snapshot "
        f"universe ({meta.as_of if meta else 'unknown date'}). "
        f"Survivorship bias: delisted/delisted stocks from earlier periods are "
        f"not in the CSV. To avoid bias, provide a point-in-time constituents file "
        f"with --historical-universe-file <path>.{meta_note}"
    )
