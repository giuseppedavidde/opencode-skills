"""Legacy sentiment score (not used by the composite; see :mod:`trading_mcp.analysis.sentiment_6d`).

Signs follow the evidence: HIGH short interest and long days-to-cover are
BEARISH (Desai et al. 2002; Asquith, Pathak & Ritter 2005; Boehmer, Huszar &
Jordan 2010). The score is 50 = neutral; a missing input adds nothing.
"""

from __future__ import annotations

from typing import Any

from trading_mcp.analysis.sentiment_6d import institutional_score, short_interest_score


def compute_sentiment(info: dict[str, Any]) -> tuple[int | None, str]:
    """Short interest and institutional ownership score (``None`` without inputs)."""
    parts: list[float] = []
    details: list[str] = []
    si_score = short_interest_score(info.get("shortPercentOfFloat"), info.get("shortRatio"))
    if si_score is not None:
        parts.append(si_score)
        details.append(f"SI {float(info['shortPercentOfFloat']) * 100:.1f}% ({si_score:.0f})")
    inst_score = institutional_score(info.get("heldPercentInstitutions"))
    if inst_score is not None:
        parts.append(inst_score)
        details.append(f"Inst {float(info['heldPercentInstitutions']) * 100:.0f}% ({inst_score:.0f})")
    if not parts:
        return None, "No sentiment inputs"
    return int(round(sum(parts) / len(parts))), " | ".join(details)
