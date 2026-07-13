# Skill: lgbm-trader-skill

LightGBM Trading System — feature engineering, stacking ensemble, signal generation.

## Architettura

98 feature in 5 gruppi decorrelati → 5 LightGBM specializzati → meta-modello → score 0-100.

## Utilizzo

### Predizione live

```bash
source /tmp/opencode/.venv/bin/activate
cd /home/giuseppe/Progetti/Github/opencode-skills/skills/lgbm-trader-skill

# Output human-readable
python scripts/predict_live.py --ticker GME

# Output JSON (per trade agent)
python scripts/predict_live.py --ticker AAPL --json
```

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

Il trade agent chiama `predict_live.py --ticker X --json` e combina lo score con analyze_stock, Bali, TS-MOM:

```python
final = 0.40 * analyze_stock + 0.20 * bali + 0.20 * tsmom + 0.20 * lgbm_ensemble
```

## Dipendenze

Python 3.10+, lightgbm, pandas, numpy, yfinance, scikit-learn, optuna, scipy, pyyaml.

Install: `pip install -e .` nella cartella della skill.

## Base directory

/home/giuseppe/Progetti/Github/opencode-skills/skills/lgbm-trader-skill
