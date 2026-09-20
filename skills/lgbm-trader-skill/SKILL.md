---
name: lgbm-trader-skill
description: >
  LightGBM Trading System — 98 features in 5 decorrelated groups,
  stacking ensemble of 5 specialized LightGBM models + meta-model,
  producing a 0-100 score. Use for ML-based trade signal generation.
  Integrates with analyze_stock, Bali signals, and TS-MOM.
---

LightGBM Trading System — feature engineering, stacking ensemble, signal generation.

## Architettura

98 feature in 5 gruppi decorrelati → 5 LightGBM specializzati → meta-modello → score 0-100.

## Utilizzo

### Predizione live (con gate train-vs-skip)

```bash
source $HOME/.local/share/opencode/trading-mcp-venv/bin/activate
cd "$HOME/.config/opencode/skills/lgbm-trader-skill"

# Uso diretto (fallisce se nessun modello)
python scripts/predict_live.py --ticker GME

# Uso consigliato: predice, e allena SOLO se il gate lo approva
python scripts/predict_or_train.py --ticker NVDA

# Output JSON (per trade agent) con le confidenze del fallback
python scripts/predict_or_train.py --ticker AAPL --json \
  --fallback-confidence '{"bali":80,"tsmom":30,"bakshi":40,"factor_scan":50}'

# Override on-demand esplicito (solo con autorizzazione utente)
python scripts/predict_or_train.py --ticker TSLA --json --force-train
```

Se non c'è un modello per il ticker, `predict_or_train.py` NON allena
automaticamente: il gate confronta la confidenza composita stimata con-LGBM
vs baseline fallback e allena solo se l'uplift raggiunge la soglia (default 5
pts). Se il gate nega, restituisce uno skip esplicito (`train_skipped: true`,
`available: false`, `score: null`) e il chiamante prosegue col fallback.
Exit code: `0` = predizione reale, `2` = gate-skip, `1` = errore.

## Gate train-vs-skip

Quando `lgbm_predict` è indisponibile (nessun `.pkl`, ImportError,
short_history, no-data) il workflow NON addestra automaticamente. Decide se
addestrare on-demand solo se l'addestramento migliora in modo significativo la
confidenza composita (0-100).

- `conf_without = Σ w_i^without · c_i` sui segnali fallback
  {bali, tsmom, bakshi, factor_scan}
- `c_best = max(c_i)` (stima ottimistica: LGBM concorde col segnale fallback
  più forte — è un bound superiore, documentato)
- `conf_with = Σ w_i^with · c_i + w_lgbm^with · c_best`
- `uplift = conf_with − conf_without`; si allena se `uplift >= soglia`
- mappatura `c_i = 50 + |score_i − 50|` dagli score MCP 0-100

Soglia (fonte unica): `LgbmGateWeights.uplift_threshold` in
`mcp/src/trading_mcp/weights_config.py`, default **5.0 punti**, sovrascrivibile
via `weights.json → lgbm_gate`. Razionale: il rumore di confidenza
cross-segnale è ~±5 punti, quindi un uplift minore non è distinguibile dal
rumore e non giustifica i 30-60s di training (né il rischio di overfit).

Senza input di confidenza il gate nega (mai training silenzioso); deriva
esplicita solo con `--force-train` (on-demand autorizzato dall'utente).

### Training

```bash
# Stacking completo (5 modelli + meta)
python scripts/run_stacking.py --ticker AAPL --start 2020-01-01

# Modello singolo
python scripts/run_pipeline.py --ticker MSFT --start 2020-01-01

# Hyperparameter tuning
python scripts/tune_model.py --ticker AAPL --trials 50
```

### Output JSON (per trade agent)

```json
{
  "ticker": "GME",
  "score": 65.9,
  "signal": "long",
  "individual_signals": {"tech": 0.57, "macro": 0.62, "decorr": 0.55},
  "meta_weights": {"pred_tech": 28, "pred_macro": 46, "pred_decorr": 6}
}
```

## Integrazione con trade agent

Il trade agent DEVE chiamare `predict_or_train.py --ticker X --json` invece di
`predict_live.py`, passando `--fallback-confidence` con le confidenze dei
segnali fallback (0-100). Questo NON garantisce più un modello allenato: il
training è subordinato al gate.

Dopo la chiamata, il trade agent DEVE controllare `model` e `train_skipped`:
- Se `model` è presente → usare `score` nel weighted average (20%).
- Se `model` è `null`/`train_skipped` è `true` (o exit code `2`) → NON
  ritentare il training: usare il fallback bali/tsmom/bakshi + factor scan e
  ridistribuire i pesi sulla tabella `without_lgbm` di `weights_config.py`:
  ```python
  SE modello esiste:
      final = 0.40*stock + 0.20*bali + 0.20*tsmom + 0.20*lgbm
  ALTRIMENTI:
      final = 0.50*stock + 0.25*bali + 0.25*tsmom
      log("LGBM non contribuisce (gate): {reason} — verdetto da fallback")
  ```
- `--force-train` solo con autorizzazione esplicita dell'utente (on-demand).

### Esempio di parsing dal trade agent (bash + python)

```bash
result=$(source $HOME/.local/share/opencode/trading-mcp-venv/bin/activate && \
         python "$HOME/.config/opencode/skills/lgbm-trader-skill/scripts/predict_or_train.py" \
               --ticker GME --json)
has_model=$(echo "$result" | python3 -c "import sys, json; d=json.load(sys.stdin); print(str(d.get('model') is not None).lower())")
ensemble_score=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('score', 50))")
```

## Dipendenze

Python 3.10+, lightgbm, pandas, numpy, yfinance, scikit-learn, optuna, scipy, pyyaml.

Install: `pip install -e .` nella cartella della skill.

## Base directory

~/.config/opencode/skills/lgbm-trader-skill
