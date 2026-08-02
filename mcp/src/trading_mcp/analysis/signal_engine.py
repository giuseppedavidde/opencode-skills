"""Signal engine: raccomandazione operativa basata su evidenza OOS.

Il segnale primario è volume_profile (unico modulo con IC reale OOS).
EVOLUZIONE (Agosto 2026): il volume profile è un indicatore di ESTENSIONE/SCONTO
rispetto alla value area, NON un segnale di momentum. L'evidenza empirica su
19.488 snapshot (200 ticker, 5 anni, 2021-2026) mostra che:

  IC VP vs fwd 180gg: −0.068 (p<0.0001)
  → VP alto (≥60) = prezzo ESTESO sopra VAH → ritorno alla media
  → VP basso (≤40) = prezzo SCONTATO sotto VAL → mean reversion verso Value Area
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_mcp.analysis.volume_profile import get_profile_levels


def compute_action(
    hist: pd.DataFrame | None = None,
    context: dict | None = None,
    levels: dict | None = None,
) -> dict[str, Any]:
    """Produce la raccomandazione operativa basata su evidenza empirica.

    Il volume profile score (VP) misura la posizione del prezzo rispetto
    alla value area del profilo. L'evidenza su 19.488 snapshot mostra che è
    un indicatore di mean-reversion (non momentum):

        - VP ≤ 40: prezzo sotto VAL = sconto → mean reversion verso VA
          (IC −0.068 a 180gg, p<0.0001, Q5–Q1 spread −6.90%)
        - VP ≥ 60: prezzo sopra VAH = esteso → expected mean reversion down
          (evidenza statisticamente significativa a 6-12 mesi)

    Args:
        hist: DataFrame OHLCV (Open, High, Low, Close, Volume). Opzionale se
              vengono passati ``levels``.
        context: dict opzionale con altre dimensioni per l'evidence.
        levels: dict pre-calcolato da ``get_profile_levels()``.
                Evita il rifetch/recalcolo dei dati.

    Returns:
        {
            "action": "LONG_TERM_BUY" | "HOLD" | "AVOID",
            "horizon_days": 180,
            "hit_rate_estimate": 0.57,  # stima conservativa da dati 180gg
            "volume_profile_score": 65,
            "target_price": 123.4 or None (None when action == "AVOID"),
            "target_type": "vah_convergence" | "modest_projection" | "none",
            "poc_reference": 118.0,
            "stop_price": 110.2,
            "entry_zone": "below VAL",
            "evidence": [...],
            "context": {...},
        }
    """
    if levels is None:
        if hist is None:
            raise ValueError("Either hist or levels must be provided")
        levels = get_profile_levels(hist)

    vp_score = levels["score"]
    val = float(levels["val"])
    vah = float(levels["vah"])
    poc_price = float(levels["poc_price"])
    price = float(levels.get("price", 0.0))
    position = str(levels["price_position"])

    # ── Azione basata su mean-reversion verso la value area ──
    # Evidenza: IC −0.068 a 180gg, p<0.0001, 19.488 snapshot, 200 ticker, 2021-2026.
    # Hit rate conservativi (inferiori all'osservato) per evitare overfitting.
    action: str
    hit_rate: float
    if vp_score <= 40:
        # Prezzo SCONTATO sotto VAL → mean reversion verso la value area
        action = "LONG_TERM_BUY"
        hit_rate = 0.57  # conservativa: osservato 0.64 in-sample, usato 0.57
    elif vp_score >= 60:
        # Prezzo ESTESO sopra VAH → ritorno alla media atteso
        action = "AVOID"
        hit_rate = 0.44  # conservativa per VP alto
    else:
        # Dentro la value area → nessun vantaggio direzionale
        action = "HOLD"
        hit_rate = 0.50

    # ── Target / Stop per orizzonte 180gg ──
    if action == "AVOID":
        target_price = None
        target_type = "none"
    elif position == "below_val":
        # Prezzo sotto VAL: target naturale = VAH (ritorno completo nella value area)
        target_price = round(vah, 2)
        target_type = "vah_convergence"
    elif 0.7 * price < poc_price < 1.3 * price:
        target_price = poc_price
        target_type = "poc_convergence"
    else:
        target_price = round(price * 1.08, 2)
        target_type = "modest_projection"

    poc_reference = poc_price

    # Stop per orizzonte 180gg — più largo (10% sotto)
    if position == "below_val":
        support = val
    elif position == "inside_va":
        support = val
    else:
        support = vah

    if action == "LONG_TERM_BUY":
        stop_price = round(price * 0.90, 2)  # 10% stop per orizzonte 180gg
    else:
        stop_price = round(min(support, price) * 0.94, 2)
        if stop_price >= price:
            stop_price = round(price * 0.92, 2)
        stop_price = min(stop_price, round(price * 0.95, 2))

    entry_zone_map = {
        "below_val": "below VAL",
        "inside_va": "inside VA",
        "above_vah": "above VAH",
    }
    entry_zone = entry_zone_map.get(position, "unknown")

    # ── Evidence strings ──
    evidence: list[str] = []
    if vp_score <= 40:
        # VP basso: statisticamente associato a forward returns superiori
        # (IC −0.068 a 180gg, p<0.0001, 19.488 snapshot OOS, 200 ticker, 5 anni)
        pos_label = {
            "below_val": "sconto sotto VAL",
            "inside_va": "fair value basso",
            "above_vah": "estensione contenuta sopra VAH",
        }.get(position, "sconto relativo")
        evidence.append(
            f"Volume profile {vp_score} (≤40): {pos_label} — "
            f"storicamente outperform a 6-12 mesi "
            f"(IC −0.068 a 180gg, p<0.0001, 19.488 snapshot OOS)"
        )
    elif vp_score >= 60:
        # VP alto: statisticamente associato a forward returns inferiori
        pos_label = {
            "below_val": "sconto con volume alto ma esteso statisticamente",
            "inside_va": "fair value alto con cluster di volumi",
            "above_vah": "estensione marcata sopra VAH",
        }.get(position, "estensione marcata")
        evidence.append(
            f"Volume profile {vp_score} (≥60): {pos_label} — "
            f"storicamente underperform a 6-12 mesi "
            f"(IC −0.068 a 180gg, p<0.0001)"
        )
    else:
        evidence.append(
            f"Volume profile {vp_score} (40-60): inside VA, nessun vantaggio direzionale statistico, HOLD"
        )

    if position == "below_val":
        evidence.append(
            f"Price ${price:.2f} below VAL ${val:.2f} — sconto sulla value area"
        )
    elif position == "inside_va":
        evidence.append(
            f"Price ${price:.2f} inside VA (${val:.2f}-${vah:.2f}) — fair value"
        )
    else:
        evidence.append(
            f"Price ${price:.2f} above VAH ${vah:.2f} — premio sulla value area"
        )

    if action == "AVOID":
        evidence.append("Target non applicabile: raccomandazione AVOID")
    elif target_type == "modest_projection":
        evidence.append(
            f"POC ${poc_price:.2f} lontano dal prezzo ({(poc_price/price-1)*100:+.0f}%) "
            f"— target di convergenza non applicabile, uso proiezione +8%"
        )
        evidence.append(
            f"Target: ${target_price:.2f} | POC reference: ${poc_price:.2f} "
            f"| Stop: ${stop_price:.2f} (180gg horizon)"
        )
    elif target_type == "vah_convergence":
        evidence.append(
            f"Target: VAH ${target_price:.2f} (mean reversion verso value area) "
            f"| POC: ${poc_price:.2f} | Stop: ${stop_price:.2f} (180gg horizon)"
        )
    else:
        evidence.append(
            f"Target: POC ${target_price:.2f} | Stop: ${stop_price:.2f} (180gg horizon)"
        )

    context_out: dict[str, Any] = {}
    if context is not None:
        context_out = {
            "composite_score": context.get("final_score"),
            "confidence": context.get("confidence"),
            "sector": context.get("sector"),
            "pattern": context.get("pattern"),
        }
        context_out = {k: v for k, v in context_out.items() if v is not None}

    return {
        "action": action,
        "horizon_days": 180,
        "hit_rate_estimate": hit_rate,
        "volume_profile_score": vp_score,
        "target_price": round(target_price, 2) if target_price is not None else None,
        "target_type": target_type,
        "poc_reference": round(poc_reference, 2),
        "stop_price": stop_price,
        "entry_zone": entry_zone,
        "evidence": evidence,
        "context": context_out,
    }
