"""Earnings surprise and proximity analysis."""

from __future__ import annotations

import yfinance as yf


def compute_earnings_surprise(ticker: yf.Ticker) -> tuple[int | None, str]:
    """Compute earnings surprise trend (beat/miss streak).

    Analyzes last 4-8 quarters of earnings surprises.
    Returns None score if data unavailable.
    """
    score = 50
    details = []

    try:
        earnings = ticker.earnings_history
        if earnings is None or (hasattr(earnings, "empty") and earnings.empty):
            return None, "No earnings history"

        if "surprisePercent" in earnings.columns:
            surprises = earnings["surprisePercent"].dropna().values
            if len(surprises) == 0:
                return None, "No surprise data"

            recent = surprises[: min(8, len(surprises))]
            beats = sum(1 for s in recent if float(s) > 0)
            misses = sum(1 for s in recent if float(s) < 0)

            streak = 0
            for s in recent:
                val = float(s)
                if val > 0:
                    streak = abs(streak) + 1
                elif val < 0:
                    streak = -(abs(streak) + 1)
                else:
                    break

            if streak >= 4:
                score += 25
                details.append(f"Earnings beat streak: {streak}Q (+25)")
            elif streak >= 2:
                score += 15
                details.append(f"Earnings beat streak: {streak}Q (+15)")
            elif streak <= -4:
                score -= 25
                details.append(f"Earnings miss streak: {abs(streak)}Q (-25)")
            elif streak <= -2:
                score -= 15
                details.append(f"Earnings miss streak: {abs(streak)}Q (-15)")

            avg_surprise = sum(float(s) for s in recent) / len(recent)
            if avg_surprise > 5:
                score += 10
                details.append(f"Avg surprise +{avg_surprise:.1f}% (+10)")
            elif avg_surprise < -5:
                score -= 10
                details.append(f"Avg surprise {avg_surprise:.1f}% (-10)")

            details.append(f"Beats: {beats}/{len(recent)}, Misses: {misses}/{len(recent)}")
        else:
            return None, "No surprisePercent column"

    except Exception as e:
        return None, f"Earnings history error: {e}"

    return min(100, max(0, score)), " | ".join(details)


def earnings_proximity_adjustment(
    _symbol: str, days_to_earnings: int | None, _iv_rank: float | None
) -> float | None:
    """Compute earnings proximity adjustment factor.

    Args:
        _symbol: Ticker (unused).
        days_to_earnings: Days to next earnings.
        _iv_rank: Current IV rank (unused).
    """
    if days_to_earnings is None:
        return None
    if days_to_earnings <= 3:
        return 0.15
    if days_to_earnings <= 7:
        return 0.10
    if days_to_earnings <= 14:
        return 0.05
    return 0.0
