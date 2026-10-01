"""Tests for the robust per-strike IV surface (validation + smile fill)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_mcp.data.options_chain import (
    _apply_iv_surface,
    _robust_iv_surface,
)

_SPOT = 100.0
_EMPTY = pd.DataFrame()


def _smile_iv(strike: float, base: float = 0.20, curv: float = 0.8) -> float:
    """A clean convex IV smile in log-moneyness."""
    return base + curv * np.log(strike / _SPOT) ** 2


def _chain_df(strikes, ivs, *, oi: int = 500) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": list(strikes),
            "impliedVolatility": list(ivs),
            "bid": [1.0] * len(strikes),
            "ask": [1.2] * len(strikes),
            "volume": [50] * len(strikes),
            "openInterest": [oi] * len(strikes),
        }
    )


def _clean_chain(extra: dict[int, float] | None = None) -> pd.DataFrame:
    strikes = np.arange(80.0, 121.0, 5.0)
    ivs = [_smile_iv(k) for k in strikes]
    frame = _chain_df(strikes, ivs)
    for idx, value in (extra or {}).items():
        frame.loc[idx, "impliedVolatility"] = value
    return frame


def test_surface_drops_out_of_range_and_statistical_outliers() -> None:
    """NaN, <=1%, >=500% and MAD outliers are excluded from the fit."""
    frame = _clean_chain(extra={0: np.nan, 1: 0.005, 8: 5.0, 5: 1.5})
    surface = _robust_iv_surface(frame, _EMPTY, _SPOT, 0.30)

    assert surface.fitted is True
    # 9 strikes − 3 out-of-range (NaN, 0.005, 5.0) = 6 collected quotes,
    # of which the in-range 1.5 spike is rejected as a robust outlier.
    assert surface.n_quote == 6
    assert surface.n_outliers >= 1
    assert len(surface.coeffs) == 3


def test_surface_fills_holes_with_smile_not_flat() -> None:
    """A strike with a missing quote receives the smile IV, tagged 'smile'."""
    frame = _clean_chain()
    surface = _robust_iv_surface(frame, _EMPTY, _SPOT, 0.30)

    hole = frame.copy()
    hole.loc[4, "impliedVolatility"] = np.nan
    resolution = _apply_iv_surface(hole, surface, 0.30)

    strike = float(hole.loc[4, "strike"])
    assert resolution.sources[4] == "smile"
    assert resolution.n_smile == 1
    assert resolution.iv_used[4] == pytest.approx(_smile_iv(strike), abs=0.05)
    assert resolution.iv_used[4] != pytest.approx(0.30)


def test_surface_keeps_valid_quotes_as_quote() -> None:
    """A finite, in-range, smile-consistent quote stays labelled 'quote'."""
    frame = _clean_chain()
    surface = _robust_iv_surface(frame, _EMPTY, _SPOT, 0.30)
    resolution = _apply_iv_surface(frame, surface, 0.30)

    assert resolution.n_quote == frame.shape[0]
    assert set(resolution.sources) == {"quote"}
    assert resolution.coverage_pct == 100.0


def test_fallback_when_no_valid_iv() -> None:
    """With no usable quotes the surface is unfit and sigma is the fallback."""
    frame = _clean_chain(extra={idx: np.nan for idx in range(9)})
    surface = _robust_iv_surface(frame, _EMPTY, _SPOT, 0.27)
    assert surface.fitted is False

    resolution = _apply_iv_surface(frame, surface, 0.27)
    assert resolution.n_fallback == frame.shape[0]
    assert set(resolution.sources) == {"fallback"}
    assert all(iv == pytest.approx(0.27) for iv in resolution.iv_used)
    assert resolution.coverage_pct == 0.0


def test_needs_enough_points_to_fit() -> None:
    """Fewer than the minimum quotes leaves the surface unfitted."""
    strikes = [95.0, 100.0, 105.0]
    frame = _chain_df(strikes, [_smile_iv(k) for k in strikes])
    surface = _robust_iv_surface(frame, _EMPTY, _SPOT, 0.30)
    assert surface.fitted is False
