"""Point-in-time leakage guards for fundamental and short-interest features."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))


class TestPublicationLag:
    """A period end becomes usable only after the filing lag."""

    def test_effective_date_applies_lag_without_filing_date(self) -> None:
        from data.fundamentals_fetcher import PUBLICATION_LAG_DAYS, _effective_date

        eff = _effective_date("2024-03-31")
        assert eff == pd.Timestamp("2024-03-31") + pd.Timedelta(days=PUBLICATION_LAG_DAYS)

    def test_filing_date_wins_over_lag(self) -> None:
        from data.fundamentals_fetcher import _effective_date

        eff = _effective_date("2024-03-31", filing_date="2024-05-02")
        assert eff == pd.Timestamp("2024-05-02")


class TestTtmAggregation:
    """Income items must be annualised before feeding a multiple."""

    def test_ttm_sums_last_four_quarters(self) -> None:
        from data.fundamentals_fetcher import _ttm

        series = pd.Series(
            [10.0, 11.0, 12.0, 13.0, 14.0],
            index=[
                pd.Timestamp("2023-06-30"),
                pd.Timestamp("2023-09-30"),
                pd.Timestamp("2023-12-31"),
                pd.Timestamp("2024-03-31"),
                pd.Timestamp("2024-06-30"),
            ],
        )
        assert _ttm(series, pd.Timestamp("2024-03-31")) == pytest.approx(46.0)
        assert _ttm(series, pd.Timestamp("2024-06-30")) == pytest.approx(50.0)

    def test_ttm_requires_four_periods(self) -> None:
        from data.fundamentals_fetcher import _ttm

        series = pd.Series(
            [10.0, 12.0],
            index=[pd.Timestamp("2024-03-31"), pd.Timestamp("2024-06-30")],
        )
        assert _ttm(series, pd.Timestamp("2024-06-30")) is None


class TestShortInterestNoLeak:
    """A current snapshot must not be written across the whole history."""

    def test_snapshot_only_on_last_bar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from features import short_interest

        monkeypatch.setattr(
            short_interest,
            "fetch_short_interest",
            lambda ticker: {"si_short_pct_float": 0.12, "si_days_to_cover": 3.4},
        )
        ohlcv = pd.DataFrame(
            {
                "close": np.linspace(100, 120, 30),
                "volume": np.full(30, 1_000_000.0),
            },
            index=pd.date_range("2024-01-01", periods=30, freq="B"),
        )
        df = short_interest.build_point_in_time_short_interest("TEST", ohlcv)
        assert "si_short_pct_float" in df.columns
        col = df["si_short_pct_float"]
        assert col.iloc[:-1].isna().all(), "history must not carry the snapshot"
        assert col.iloc[-1] == pytest.approx(0.12)
