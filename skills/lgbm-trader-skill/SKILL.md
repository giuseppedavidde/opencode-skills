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

### Predizione live (con auto-training)

```bash
source /tmp/opencode/.venv/bin/activate
cd /home/giuseppe/.config/opencode/skills/lgbm-trader-skill

# Uso diretto (fallisce se nessun modello)
python scripts/predict_live.py --ticker GME

# Uso consigliato: auto-allena se necessario
python scripts/predict_or_train.py --ticker NVDA

# Output JSON (per trade agent)
python scripts/predict_or_train.py --ticker AAPL --json

# Specifica data di training (solo se nessun modello)
python scripts/predict_or_train.py --ticker TSLA --json --start 2021-01-01
```

Se non c'è un modello per il ticker, `predict_or_train.py` allena automaticamente
lo stacking ensemble prima di predire (30-60s). Non restituisce mai score=50
silenziosamente — o restituisce una predizione reale (con `model` popolato)
oppure un errore esplicito (con `score=50` e `error` descrittivo).

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
`predict_live.py`. Questo garantisce che ogni ticker abbia un modello allenato
prima di contribuire al verdict.

Dopo la chiamata, il trade agent DEVE controllare il campo `model`:
- Se `model` è presente → usare `score` nel weighted average (20%).
- Se `model` è `null`/assente → NON usare LGBM, ridistribuire i pesi:
  ```python
  SE modello esiste:
      final = 0.40*stock + 0.20*bali + 0.20*tsmom + 0.20*lgbm
  ALTRIMENTI:
      final = 0.50*stock + 0.25*bali + 0.25*tsmom
      log("⚠️ LGBM saltato per {ticker}: {error}")
  ```

### Esempio di parsing dal trade agent (bash + python)

```bash
result=$(source /tmp/opencode/.venv/bin/activate && \
         python /home/giuseppe/.config/opencode/skills/lgbm-trader-skill/scripts/predict_or_train.py \
               --ticker GME --json)
has_model=$(echo "$result" | python3 -c "import sys, json; d=json.load(sys.stdin); print(str(d.get('model') is not None).lower())")
ensemble_score=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('score', 50))")
```

## Dipendenze

Python 3.10+, lightgbm, pandas, numpy, yfinance, scikit-learn, optuna, scipy, pyyaml.

Install: `pip install -e .` nella cartella della skill.

## Base directory

/home/giuseppe/Progetti/Github/opencode-skills/skills/lgbm-trader-skill
