# Integrazione con Trade Agent

Il trade agent può chiamare il sistema LightGBM stacking per ottenere
uno score 0-100 decorrelato dall'analisi fondamentale.

## Uso base

```bash
source /tmp/opencode/.venv/bin/activate
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/predict_live.py --ticker GME
```

## Output JSON (per uso programmatico)

```bash
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/predict_live.py --ticker AAPL --json
```

Esempio di output:

```json
{
  "ticker": "GME",
  "date": "2026-07-11",
  "price": 24.55,
  "score": 67.3,
  "signal": "long",
  "model": "GME_stacking_20260713.pkl",
  "individual_signals": {
    "tech": 0.2143,
    "macro": -0.0512,
    "full": 0.1804
  },
  "meta_weights": {
    "pred_tech": 12,
    "pred_macro": 3,
    "pred_full": 45
  }
}
```

## Segnali

Score / signal mapping:

| Score       | Signal         |
| ----------- | -------------- |
| ≥ 70        | `strong_long`  |
| 55 – 69     | `long`         |
| 46 – 54     | `neutral`      |
| 31 – 45     | `short`        |
| ≤ 30        | `strong_short` |

Se non c'è un modello addestrato per il ticker, lo script non crasha:
restituisce `score=50`, `signal=neutral` con un messaggio nel campo
`error`.

## Fallback automatico

Lo script cerca in ordine:

1. `models/saved/{ticker}_stacking_*.pkl` → modello stacking completo.
2. `models/saved/{ticker}_lgbm_*.pkl` → modello LGBM singolo (fallback).
3. Nessun modello → score neutro (50) + errore descrittivo.

## Workflow consigliato per il trade agent

Quando analizzi un ticker per opzioni:

1. Esegui `analyze_stock()` → verdict, score.
2. Esegui Bali / Bakshi signals.
3. Esegui TS-MOM signal.
4. Chiama `predict_live.py --ticker <TICKER> --json` →
   `ensemble_score` (campo `score`).
5. Combina i segnali:

```python
final_score = 0.40 * analyze_stock_score \
            + 0.20 * bali_score \
            + 0.20 * tsmom_score \
            + 0.20 * stacking_ensemble_score  # ← NUOVO
```

I pesi sono indicativi: possono essere ri-tarati aumentando il peso
dello stacking se il backtest mostra uno Sharpe robusto e basso
drawdown (vedi log di `run_stacking.py`).

### Esempio di parsing dal trade agent (bash + python)

```bash
result=$(source /tmp/opencode/.venv/bin/activate && \
         python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/predict_live.py \
               --ticker GME --json)
ensemble_score=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('score'))")
ensemble_signal=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('signal'))")
```

## Training di un nuovo modello

```bash
# Stacking completo (5 modelli + meta) + live prediction dopo il training
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/run_stacking.py \
    --ticker GME --start 2020-01-01 --predict

# Solo modello singolo (più veloce)
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/run_pipeline.py \
    --ticker GME --start 2020-01-01

# Tuning iperparametri
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/tune_model.py \
    --ticker GME --trials 50
```

## Modelli disponibili

I modelli salvati stanno in `models/saved/{ticker}_stacking_{date}.pkl`
(stacking) e `models/saved/{ticker}_lgbm_{date}.pkl` (singolo).

Lo script `predict_live.py` seleziona sempre il più recente per il
ticker richiesto.

## Note tecniche

- Lo script non crasha mai: ogni errore (no modello, no dati, feature
  mancanti) viene catturato e riportato nel campo `error` con
  `score=50` neutro.
- Le feature mancanti nei dati live vs quelle attese dal modello
  salvato vengono riempite con `0.0` (neutrali) invece di crashare —
  vedi `_align_features` in `predict_live.py`.
- Lo score è sempre nel range `[0, 100]` perché il raw output del
  meta-modello passa per una sigmoid.