"""Sentiment analysis: Short Interest, Institutional, DTC scoring."""

from __future__ import annotations

from typing import Any


def compute_sentiment(info: dict[str, Any]) -> tuple[int, str]:
    """Compute sentiment score (0-100) from short interest, institutional, and DTC.

    Args:
        info: yfinance info dictionary.
    """
    score = 25
    details = []

    si = info.get("shortPercentOfFloat")
    if si is not None:
        si_val = float(si)
        if si_val > 0.20:
            score += 35
            details.append(f"SI {si_val*100:.1f}% > 20% (+35)")
        elif si_val > 0.10:
            score += 20
            details.append(f"SI {si_val*100:.1f}% 10-20% (+20)")
        else:
            details.append(f"SI {si_val*100:.1f}% < 10% (+0)")
    else:
        details.append("SI N/A (+0)")

    inst = info.get("heldPercentInstitutions")
    if inst is not None:
        inst_val = float(inst)
        if inst_val > 0.50:
            score += 15
            details.append(f"Inst {inst_val*100:.0f}% > 50% (+15)")

    dtc = info.get("shortRatio")
    if dtc is not None:
        dtc_val = float(dtc)
        if dtc_val > 7:
            score += 25
            details.append(f"DTC {dtc_val:.1f} > 7 (+25)")
        elif dtc_val > 3:
            score += 15
            details.append(f"DTC {dtc_val:.1f} > 3 (+15)")

    return min(score, 100), " | ".join(details)
