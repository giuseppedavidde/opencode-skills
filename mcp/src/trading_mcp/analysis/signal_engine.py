"""Signal engine: raccomandazione operativa basata su evidenza OOS.

Il segnale primario è volume_profile (unico modulo con IC reale OOS).
EVOLUZIONE (Agosto 2026): il volume profile è un indicatore mean-reversion,
NON momentum. L'evidenza empirica su 19.488 snapshot (200 ticker, 5 anni,
2021-2026) mostra IC rank −0.068 (p<0.0001): VP score alto → forward return
basso, VP score basso → forward return alto.

SEMANTICA (mean-reversion, unica, documentata):
  VP ≤ 40 → BUY    (ritorno alla media verso l'alto atteso, IC negativo)
  VP ≥ 60 → AVOID  (ritorno alla media verso il basso atteso)
  40 < VP < 60 → HOLD (nessun vantaggio direzionale statistico)

P2: se esiste un artifact di calibrazione in
``~/.config/opencode/calibrations/vp_calibration.json`` con
``status=calibrated``, ``compute_action`` restituisce
``hit_rate_calibrated`` (da isotonic) insieme a ``calibration_status``
e ``calibration_file``. Altrimenti usa i valori conservativi fissi
con ``calibration_status='not_calibrated'``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from trading_mcp.analysis.volume_profile import get_profile_levels

logger = logging.getLogger(__name__)

# ── Calibration artifact default path ────────────────────────────────────

_VP_CALIBRATION_PATH = Path.home() / ".config" / "opencode" / "calibrations" / "vp_calibration.json"


def _load_calibration_artifact(
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load VP calibration artifact if it exists and is calibrated/weak_calibrated."""
    target = Path(path) if path else _VP_CALIBRATION_PATH
    if not target.exists():
        logger.debug("No calibration artifact at %s", target)
        return None
    try:
        with open(target, "r", encoding="utf-8") as f:
            artifact = json.load(f)
        status = artifact.get("status")
        if status in ("calibrated", "weak_calibrated"):
            return artifact
        logger.debug("Calibration artifact at %s has status=%s (not used)",
                     target, status)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load calibration artifact: %s", exc)
        return None


def _calibrated_hit_rate(
    vp_score: float,
    artifact: dict[str, Any],
) -> tuple[float | None, str, list[str]]:
    """Map VP score to hit probability based on artifact status.

    Returns:
        (hit_rate, hit_rate_source, warnings)
        - calibrated: isotonic curve on inverted score
        - weak_calibrated: empirical buckets with shrinkage
        - None if lookup fails
    """
    status = artifact.get("status", "not_calibrated")

    if status == "calibrated":
        iso_x = artifact.get("isotonic_X")
        iso_y = artifact.get("isotonic_Y")
        if not iso_x or not iso_y or len(iso_x) != len(iso_y):
            return None, "calibrated_isotonic", []
        inverted = 100.0 - vp_score
        if inverted <= iso_x[0]:
            return iso_y[0], "calibrated_isotonic", []
        if inverted >= iso_x[-1]:
            return iso_y[-1], "calibrated_isotonic", []
        import numpy as np
        idx = np.searchsorted(iso_x, inverted) - 1
        idx = max(0, min(idx, len(iso_x) - 2))
        x0, x1 = iso_x[idx], iso_x[idx + 1]
        y0, y1 = iso_y[idx], iso_y[idx + 1]
        if x1 == x0:
            return y0, "calibrated_isotonic", []
        t = (inverted - x0) / (x1 - x0)
        return round(float(y0 + t * (y1 - y0)), 4), "calibrated_isotonic", []

    if status == "weak_calibrated":
        buckets = artifact.get("bucket_hit_rates", [])
        base_rate = artifact.get("base_rate_oos", 0.5)
        shrinkage = artifact.get("shrinkage", 0.40)
        inverted = 100.0 - vp_score

        bucket_raw = None
        for b in buckets:
            low = b["score_low"]
            high = b["score_high"]
            if low <= inverted <= high:
                bucket_raw = b["hit_rate_raw"]
                break

        if bucket_raw is None:
            # Fallback: nearest bucket
            return None, "bucket_empirical_shrunk", [
                f"No bucket found for inverted score {inverted:.1f}"
            ]

        shrunk = base_rate + shrinkage * (bucket_raw - base_rate)
        shrunk = max(0.0, min(1.0, shrunk))
        return round(shrunk, 4), "bucket_empirical_shrunk", []

    return None, "none", []


def compute_action(
    hist: pd.DataFrame | None = None,
    context: dict | None = None,
    levels: dict | None = None,
    calibration_path: str | Path | None = None,
) -> dict[str, Any]:
    """Produce la raccomandazione operativa basata su evidenza empirica.

    Il VP score è un composito mean-reversion (non momentum). L'evidenza
    su 19.488 snapshot (200 ticker, 5 anni) mostra che:

        IC rank VP vs fwd 180gg = −0.068 (p<0.0001)
        → VP score ALTO → forward return BASSO (mean-reversion down)
        → VP score BASSO → forward return ALTO (mean-reversion up)

    Soglie operative (coerenti con IC negativo):
        - VP ≤ 40: BUY (forward return atteso superiore)
        - VP ≥ 60: AVOID (forward return atteso inferiore)
        - 40 < VP < 60: HOLD (nessun vantaggio direzionale statistico)

    P2: se esiste un artifact di calibrazione calibrato,
    ``hit_rate_calibrated`` viene calcolato via isotonic interpolation.
    Altrimenti viene usato il valore conservativo fisso
    (``hit_rate_estimate``) con ``calibration_status='not_calibrated'``.

    Args:
        hist: DataFrame OHLCV (Open, High, Low, Close, Volume). Opzionale se
              vengono passati ``levels``.
        context: dict opzionale con altre dimensioni per l'evidence.
        levels: dict pre-calcolato da ``get_profile_levels()``.
                Evita il rifetch/recalcolo dei dati.
        calibration_path: Path dell'artifact di calibrazione (opzionale,
            default ``~/.config/opencode/calibrations/vp_calibration.json``).

    Returns:
        {
            "action": "LONG_TERM_BUY" | "HOLD" | "AVOID",
            "horizon_days": 180,
            "hit_rate_estimate": 0.57,  # conservativa fissa
            "hit_rate_calibrated": 0.61,  # da artifact (se calibrato)
            "calibration_status": "calibrated" | "not_calibrated",
            "calibration_file": null or path,
            ...
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

    # ── Calibration artifact (P2) ──────────────────────────────────
    artifact = _load_calibration_artifact(calibration_path)
    calibration_status = "not_calibrated"
    hit_rate_calibrated = None
    hit_rate_source = None
    calibration_file = None
    calibration_warnings: list[str] = []

    if artifact is not None:
        calibration_status = artifact.get("status", "not_calibrated")
        calibration_file = str(calibration_path or _VP_CALIBRATION_PATH)
        calibrated_val, source, cal_warns = _calibrated_hit_rate(vp_score, artifact)
        hit_rate_calibrated = calibrated_val
        hit_rate_source = source
        calibration_warnings = cal_warns

        # Propagate artifact warnings
        for w in artifact.get("warnings", []):
            calibration_warnings.append(
                f"[{w.get('severity', 'info')}] {w.get('code', '')}: {w.get('message', '')}"
            )

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
        # ── P2: calibration fields ──────────────────────────────
        "hit_rate_calibrated": hit_rate_calibrated,
        "hit_rate_source": hit_rate_source,
        "calibration_status": calibration_status,
        "calibration_file": calibration_file,
        "calibration_warnings": calibration_warnings,
        # ── Signal limitations ──────────────────────────────────
        "signal_limits": [
            "VP signal is regime-dependent — flips sign between quarters "
            "and across tickers. Do NOT use standalone in strong trending "
            "markets without confirming signals.",
            "Cross-sectional pooling masks per-ticker heterogeneity. "
            "Bucket hit rates are averages across 50+ tickers; individual "
            "outcomes may differ materially.",
            "Calibration is on 180-day horizon. Shorter horizons show "
            "weaker signal discrimination.",
        ],
    }
