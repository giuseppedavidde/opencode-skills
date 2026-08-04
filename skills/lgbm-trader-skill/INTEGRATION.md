# Integrazione con Trade Agent

Il trade agent può chiamare il sistema LightGBM stacking per ottenere
uno score 0-100 decorrelato dall'analisi fondamentale.

## ⚠️ Status (P0 — Agosto 2026)

L'infrastruttura è in fase P0 di verifica. I segnali e gli score
prodotti sono **diagnostici, non predittivi**. Solo dopo un run OOS su
dati reali (non usati nel training/calibrazione) le metriche diventano
interpretabili come stime di performance attesa.

### Cosa è stato verificato nella P0

| Componente | Stato |
|---|---|
| Split temporali con purging/embargo | ✅ Implementato |
| Coerenza semantica VP (mean-reversion) | ✅ Allineata signal_engine ↔ _compute_verdict |
| LGBM unavailable = no score neutro | ✅ `available=False` esplicito |
| Stacking meta-model holdout dedicato | ✅ Metriche ensemble solo su holdout OOS |
| Backtest CLI OHLCV point-in-time | ✅ `scripts/run_backtest.py` |
| Test unitari senza rete | ✅ `tests/` con fixture sintetiche |
| **Gestione storia corta** (P0 Aug 2026) | ✅ `BacktestBuildResult` stato esplicito |
| **Per-horizon capability** (P0 Aug 2026) | ✅ `supported`/`insufficient_data` per orizzonte |
| **Modalità diagnostica** (P0 Aug 2026) | ✅ `diagnostic_only` flag, VP window adattiva |
| **LGBM short-history block** (P0 Aug 2026) | ✅ `available=False` con barre disponibili/richieste |
| **process_ticker short guard** (P0 Aug 2026) | ✅ <50 barre → `status='insufficient_data'`, `final_score=None` |
| **analyze_stock propagation** (P0 Aug 2026) | ✅ `composite_score=None`, no verdict |
| **scan_market exclusion** (P0 Aug 2026) | ✅ `insufficient_data_count`, esclusi dal ranking |
| **bakshi_signals guard** (P0 Aug 2026) | ✅ <63 barre → errore con `available_bars`/`required_bars` |
| **Portabilità MCP_SRC** (P0 Aug 2026) | ✅ `TRADING_MCP_SRC` env var, walk-up discovery |

### Novità P0 Agosto 2026: gestione esplicita storia corta

Prima di questa release, `build_predictions_from_ohlcv` restituiva una
lista vuota senza spiegazione quando i dati erano insufficienti. Ora:

1. **`BacktestBuildResult`** — il costruttore restituisce uno stato
   esplicito (`ok` / `insufficient_data`) con `available_bars`,
   `required_bars`, `reason` e per-horizon `HorizonCapability`.

2. **Modalità strict vs diagnostica** — default `strict_mode=True`:
   nessun risultato OOS se non ci sono abbastanza barre per la finestra
   VP canonica (252) e almeno 30 osservazioni per orizzonte. La modalità
   `--diagnostic` usa finestra VP adattiva >=20 barre ed etichetta
   sempre il risultato come **diagnostico, non comparabile** alla
   calibrazione 365d.

3. **Orizzonti indipendenti** — se sono supportati 20 e 60 giorni ma non
   180, vengono generate predizioni solo per gli orizzonti supportati.
   Ogni orizzonte riporta `supported` / `insufficient_data`.

4. **VP CLI** — la finestra VP effettiva e la copertura sono visibili
   nell'output; `--diagnostic` attiva finestra adattiva.

5. **LGBM history guard** — se la storia è <120 barre (minimo assoluto)
   o <252 barre (lookback feature), `lgbm_predict` restituisce
   `available=False`, `score=None`, `error_is_blocking=True` con
   `available_bars` e `required_bars`. Non si addestra né predice con
   fill o modello non calibrato.

6. **process_ticker guard (<50 barre)** — `scanner.py` ora restituisce
   un dict strutturato con `status='insufficient_data'`,
   `final_score=None`, `history_bars`, `required_bars=50` e `reason`.
   Non esegue il composite su dati insufficienti.

7. **analyze_stock propagation** — se `process_ticker` restituisce
   `insufficient_data`, `analyze_stock` propaga `composite_score=None`,
   `verdict='insufficient_data'` e nessun `action_recommendation`.

8. **scan_market exclusion** — i risultati con `final_score=None` o
   `status='insufficient_data'` sono esclusi dal ranking. Il campo
   `insufficient_data_count` e `insufficient_data_detail` nel
   risultato aggregate riportano il conteggio.

9. **bakshi_signals guard (<63 barre)** — con meno di 63 barre valide,
   `BakshiResult` restituisce `available_bars`/`required_bars` e un
   errore esplicito. Il VRP non viene calcolato.

10. **Portabilità CLI** — `run_backtest.py` ora risolve `trading_mcp`
    via `TRADING_MCP_SRC` env var o walk-up automatico fino a 6 livelli
    dalla skill root; nessun path `/home/giuseppe` hardcoded.

### Cosa NON è ancora verificato

- Performance LGBM su holdout reale (richiede dati storici completi)
- Consensus tra segnali quantitativi (LGBM, Bali, TS-MOM, VP)
- Robustezza cross-sectional su universo ampio
- Calibrazione score → probabilità reale di successo

## Uso base

```bash
source /tmp/opencode/.venv/bin/activate
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/predict_live.py --ticker GME
```

## Backtest point-in-time (AGGIORNATO P0 Ago 2026)

```bash
# Backtest canonico (strict mode, VP window 365d, richiede >=432 barre)
source /tmp/opencode/.venv/bin/activate
python scripts/run_backtest.py --ticker SPY --horizons 20,60,180 --output backtest_results/

# Modalita' diagnostica per ticker con storia corta (VP window adattiva >=20d)
python scripts/run_backtest.py --ticker NEWIPO --diagnostic --no-strict --horizons 20,60

# Output: CSV + JSON con esplicito supported/insufficient_data per orizzonte
```

Il backtest ora produce uno stato esplicito:
- `BacktestBuildResult.status` = `ok` o `insufficient_data`
- Ogni orizzonte ha flag `supported` e `status` (`ok`/`insufficient_data`)
- In modalità diagnostica, `diagnostic_only=True` e i limiti lo segnalano

### Esempio: storia corta (ticker con 50 barre)

```bash
$ python scripts/run_backtest.py --ticker NEW --diagnostic --no-strict \
    --horizons 20,60 --min-bars 40 --period 1mo

Fetching OHLCV for NEW (1mo)...
  Downloaded: 21 bars

  Mode: DIAGNOSTIC
  VP window requested: 365d
  VP window effective: 20d
  Strict mode: False
  Min bars: 40

Building point-in-time predictions...
  Build status: insufficient_data
  Available bars: 21
  Required bars: 100
  Reason: Strict mode: ...

INSUFFICIENT DATA — no predictions generated
Per-horizon capability:
     Horizon  Supported     Need     Have
    -------------------------------------
          20         NO       60       21
          60         NO      100       21

To run with short history, use --diagnostic and --no-strict:
  python scripts/run_backtest.py --ticker NEW --diagnostic --no-strict --period 1mo
```

## Output JSON (per uso programmatico)

```bash
python /home/giuseppe/Progetti/Github/lgbm-trader/scripts/predict_live.py --ticker AAPL --json
```

Quando il modello LGBM NON è disponibile, l'output ora restituisce
`available: false` e `error_is_blocking: true` invece di uno score
neutro (50). Il campo `score` sarà `null`.

## Segnali

Score / signal mapping:

| Score       | Signal         |
| ----------- | -------------- |
| ≥ 70        | `strong_long`  |
| 55 – 69     | `long`         |
| 46 – 54     | `neutral`      |
| 31 – 45     | `short`        |
| ≤ 30        | `strong_short` |

⚠️ Se il modello non è disponibile, il signal è `"unavailable"` e lo
score è `null`. Non usare mai uno score neutro (50) come segnale quando
il modello manca.

## Semantica Volume Profile (mean-reversion, allineata P0)

Il VP score è un composito mean-reversion con IC rank −0.068 OOS:
- VP ≤ 40 → BUY (forward return alto atteso)
- VP ≥ 60 → AVOID (forward return basso atteso)
- 40 < VP < 60 → HOLD

Questa semantica è ora coerente tra `signal_engine.py` e
`_compute_verdict` in `_analysis_tools.py`.

## Fallback automatico

Lo script cerca in ordine:

1. `models/saved/{ticker}_stacking_*.pkl` → modello stacking completo.
2. `models/saved/{ticker}_lgbm_*.pkl` → modello LGBM singolo (fallback).
3. Nessun modello → `available: false` con errore esplicito (NON score=50).

## Workflow consigliato per il trade agent

Quando analizzi un ticker per opzioni:

1. Esegui `analyze_stock()` → verdict, score.
2. Esegui Bali / Bakshi signals.
3. Esegui TS-MOM signal.
4. Chiama `predict_live.py --ticker <TICKER> --json` →
   `ensemble_score` (campo `score`). Verifica `available: true`.
5. Combina i segnali (solo se disponibili):

```python
final_score = 0.40 * analyze_stock_score \
            + 0.20 * bali_score \
            + 0.20 * tsmom_score \
            + 0.20 * stacking_ensemble_score
```

I pesi sono indicativi: possono essere ri-tarati aumentando il peso
dello stacking se il backtest mostra uno Sharpe robusto e basso
drawdown (vedi log di `run_stacking.py`).

## Training di un nuovo modello

```bash
# Stacking completo (5 modelli + meta) + live prediction dopo il training
python scripts/run_stacking.py --ticker GME --start 2020-01-01 --predict

# Solo modello singolo (più veloce)
python scripts/run_pipeline.py --ticker GME --start 2020-01-01

# Tuning iperparametri
python scripts/tune_model.py --ticker GME --trials 50
```

## Esecuzione test (AGGIORNATO P0 Ago 2026)

```bash
source /tmp/opencode/.venv/bin/activate
cd ~/.config/opencode/skills/lgbm-trader-skill
python -m pytest tests/ -v

# 82 test: backtest, LGBM unavailable, short history (10-500+ barre),
# P0 guards (scanner, analyze, bakshi, bali, tsmom, portability),
# splits, VP coherence — tutti senza rete
```

### Cosa testano i nuovi test `test_short_history.py`

| Test | Copertura |
|---|---|
| `test_build_status_explicit` | Parametrizzato: 10, 30, 100, 251, 431, 500 barre |
| `test_10_bars_has_explicit_reason` | Storia minuscola → `insufficient_data` con motivo |
| `test_500_bars_ok_all_horizons_supported` | 500 barre → tutti gli orizzonti supportati |
| `test_diagnostic_mode_sets_flag` | Modalità diagnostica → `diagnostic_only=True` |
| `test_diagnostic_results_never_claim_predictive` | Valutatore preserva `diagnostic_only` nei limiti |
| `test_middle_horizon_unsupported` | 280 barre → solo 20d supportato, 60d e 180d no |
| `test_unsupported_horizons_get_no_predictions` | Nessuna predizione per orizzonti non supportati |
| `test_evaluator_respects_horizon_supported` | Valutatore rispetta flag `supported` per orizzonte |
| `test_shift_minus_h_is_strictly_future` | `.shift(-h)` non usa dati futuri |
| `test_signal_only_uses_past_data` | Segnale a `as_of` corrisponde al valore corretto |

### Nuovi test `test_p0_guards.py` (14 test)

| Test | Copertura |
|---|---|
| `test_30_bars_returns_insufficient_data` | process_ticker con 30 barre → `status='insufficient_data'` |
| `test_10_bars_returns_insufficient_data` | 10 barre → `final_score=None` esplicito |
| `test_100_bars_proceeds_normally` | 100 barre → nessun blocco, composite calcolato |
| `test_short_history_yields_none_score` | analyze_stock propaga `composite_score=None` |
| `test_insufficient_not_in_ranking` | scan_market esclude insufficient_data dal ranking |
| `test_none_scores_never_in_sort_key` | `final_score=None` non crasha `sorted()` |
| `test_30_bars_returns_error_with_counts` | Bakshi <63 → errore con `available_bars`/`required_bars` |
| `test_63_bars_does_not_block` | Esattamente 63 barre → non bloccato |
| `test_bakshi_result_new_fields_default` | Campi nuovi default a 0 |
| `test_short_history_no_vrp_computed` | VRP non calcolato con storia corta |
| `test_model_defaults` | DataSufficiency default `status='ok'` |
| `test_insufficient_data_model` | DataSufficiency insufficient stato esplicito |
| `test_resolve_via_env_var` | Portabilità: `TRADING_MCP_SRC` risoluzione robusta |
| `test_fallback_path_is_safe` | Fallback a `.` quando nulla trovato |
| `test_help_runs_without_network` | `--help` exit 0, no import crash |
| `test_30_bars_returns_unavailable` (Bali) | Bali <50 → `available=False`, `composite_bali_score=None` |
| `test_success_path_has_available_true` (Bali) | Bali success → `available=True`, score valido |
| `test_bare_constructor_is_unavailable` (Bali) | Bali default → `available=False`, score=None |
| `test_score_never_defaults_to_50` (Bali) | Bali `composite_bali_score` mai 50 quando unavailable |
| `test_40_bars_returns_unavailable` (TS-MOM) | TS-MOM <60 → `available=False`, `mom_score=None` |
| `test_tsmom_success_path` (TS-MOM) | TS-MOM success → `available=True` |
| `test_tsmom_bare_constructor` (TS-MOM) | TS-MOM default → `available=False` |
| `test_mom_score_never_defaults_to_50` (TS-MOM) | TS-MOM `mom_score` mai 50 quando unavailable |
| `test_skip_days_causes_insufficient` (TS-MOM) | TS-MOM skip days → errore esplicito |

### Tool ancora privi di guardia (audit P0)

| Tool/Componente | Stato | Note |
|---|---|---|
| `lgbm_predict` | ✅ Guard attiva | <120 o <252 barre → `available=False` |
| `process_ticker` | ✅ Guard attiva | <50 barre → `insufficient_data` |
| `analyze_stock` | ✅ Guard attiva | propaga `composite_score=None` |
| `scan_market` | ✅ Guard attiva | esclude + conta |
| `bakshi_signals` | ✅ Guard attiva | <63 barre → errore |
| `build_predictions_from_ohlcv` | ✅ Guard attiva | `BacktestBuildResult` |
| `bali_signals` | ✅ Guard attiva | <50 barre → `available=False`, `composite_bali_score=None` |
| `tsmom_signals` | ✅ Guard attiva | <60 barre → `available=False`, `mom_score=None` |
| `compute_wyckoff` | ⚠️ Interno a process_ticker | Protetto dalla guard di process_ticker |
| `compute_volume_profile` | ⚠️ Interno a process_ticker | Protetto dalla guard di process_ticker |

## Modelli disponibili

I modelli salvati stanno in `models/saved/{ticker}_stacking_{date}.pkl`
(stacking) e `models/saved/{ticker}_lgbm_{date}.pkl` (singolo).

Lo script `predict_live.py` seleziona sempre il più recente per il
ticker richiesto.

## Note tecniche

- Le feature mancanti nei dati live vs quelle attese dal modello
  salvato vengono riempite con `0.0` (neutrali) invece di crashare —
  vedi `_align_features` in `predict_live.py`. Questo comportamento è
  documentato: l'utente deve sapere che feature mancanti → contributo
  nullo.
- Lo score è sempre nel range `[0, 100]` perché il raw output del
  meta-modello passa per una sigmoid.
- L'embargo nei walk-forward split ora rimuove effettivamente le barre
  di training il cui label horizon si sovrappone alla validation window
  (fix del `pass` in `lgbm_trainer.py:146-150`).
- Il meta-modello dello stacking allena su 80% temporale e calcola le
  metriche ensemble SOLO sul 20% holdout (mai visto dal meta-model).
