---
name: smart-dispatcher
description: >
  Auto-dispatcher that translates natural language requests into parallel
  orchestration via subatomic-orchestrator. You write "scan Europe" or "what
  to do with AAPL and MSFT" — it classifies intent, extracts parameters, and
  runs the optimal parallel pipeline. Zero CLI arguments needed.
allowed-tools:
  - read
  - grep
  - bash
  - task
  - glob
  - write
  - websearch
triggers:
  - scan*, screening, scansion*, mercat*, market scan, cerca ticker
  - analizz*, deep dive, cosa far*, cosa fare, verdict, unified analysis
  - opzioni su, options on, strategia opzioni su, suggerisci opzioni
  - wsb, wallstreetbets, pump, pompano, meme stock
  - fetch, prendi, dati di, quotazione, price, prezzo di
  - "cosa fare con", "cosa fare di", "cosa fare su"
---

# Smart Dispatcher

Traduce linguaggio naturale in orchestrazione parallela.
L'utente non sa che esiste un orchestrator — scrive e ottiene risultati 3-5x più veloci.

## Pipeline

```
Richiesta utente ("scan di italy, germany e francia top 5")
        │
        ▼
┌─────────────────┐
│  1. CLASSIFY    │  scripts/classify.py
│  intent + param │  → market_scan, tickers=[], top=5
└────────┬────────┘
         ▼
┌─────────────────┐
│  2. BUILD       │  Costruisce comando orchestrator
│  orchestration  │  → --skills market-accumulation-scanner
└────────┬────────┘    --items italy,germany,france
         ▼             --split-by market --top 5
┌─────────────────┐
│  3. DISPATCH    │  subatomic-orchestrator
│  parallel agents│  → 3 agent in parallelo
└────────┬────────┘
         ▼
┌─────────────────┐
│  4. AGGREGATE   │  merge rank → top 5 globale
│  + RENDER       │  output pulito all'utente
└─────────────────┘
```

## Intent Classification

`scripts/classify.py` analizza la richiesta e restituisce:

```json
{
  "intent": "market_scan",
  "params": {
    "markets": ["italy", "germany", "france"],
    "top": 5
  },
  "orchestrator_cmd": "--skills market-accumulation-scanner --items italy,germany,france --split-by market --top 5"
}
```

### 6 Intent Supportati

| # | Intent | Trigger keywords | Skill orchestrata |
|---|--------|-----------------|-------------------|
| 1 | `market_scan` | scan, screening, scansiona, mercato, screening | market-accumulation-scanner |
| 2 | `deep_dive` | analizza, deep dive, cosa fare, verdict, cosa farne | stock-crypto-analysis |
| 3 | `options_suggest` | opzioni su, options on, strategia opzioni | options-strategy-suggestions |
| 4 | `wsb_detect` | wsb, wallstreetbets, pump, pompano, meme | wallstreetbets-pump-detect |
| 5 | `data_fetch` | fetch, prendi dati, quotazione, prezzo di | market-data-fetch |
| 6 | `full_pipeline` | WSB + analisi, "cosa comprare", "cosa fare" | wallstreetbets → analysis → options |

## Parameter Extraction

classify.py estrae dalla frase:

| Parametro | Pattern | Esempi |
|-----------|---------|--------|
| `markets` | Nomi mercato o paesi | "italy", "germania", "dax", "nasdaq", "europa" |
| `tickers` | Simboli borsistici | "AAPL", "DBK.DE", "ENI.MI", "SGRO.L" |
| `top` | Numeri dopo "top/best/primi/migliori" | "top 10", "best 5", "i primi 3" |
| `custom_tickers` | Lista ticker separati da virgola/e | "MSFT, AAPL, ENI.MI" |

## Market Aliases (classify.py)

| Alias utente | Universo orchestrator |
|-------------|----------------------|
| nasdaq, qqq, tecnologici americani | us_tech |
| nyse, america, usa, stati uniti, s&p 500 | us_large |
| italia, milano, italy, mib, ftse mib | italy |
| germania, germany, dax, francoforte | germany |
| francia, france, parigi, cac | france |
| uk, inghilterra, londra, ftse | uk |
| spagna, spain, madrid, ibex | spain |
| europa, europe, mercati europei | all_eu (tutti e 5) |
| tutto, mondo, world, global, all | all (US + EU) |

## Esempi di Traduzione

| Utente dice | Intent | Parametri | Comando orchestrator |
|---|---|---|---|
| "scan del NASDAQ" | market_scan | markets=[us_tech], top=15 | `--skills market-accumulation-scanner --items us_tech --split-by market --top 15` |
| "Scansiona italy, germany e francia top 5" | market_scan | markets=[italy,germany,france], top=5 | `--skills market-accumulation-scanner --items italy,germany,france --split-by market --top 5` |
| "Cosa fare di DBK.DE e SGRO.L" | deep_dive | tickers=[DBK.DE,SGRO.L] | `--skills stock-crypto-analysis --items DBK.DE,SGRO.L --split-by ticker --top 2` |
| "Opzioni su AAPL" | options_suggest | tickers=[AAPL] | `--skills options-strategy-suggestions --items AAPL --split-by ticker` |
| "Cosa pompano su WSB oggi?" | wsb_detect | — | `--skills wallstreetbets-pump-detect` |
| "Scan completo Europa top 10" | market_scan | markets=[all_eu], top=10 | `--skills market-accumulation-scanner --items italy,germany,france,uk,spain --split-by market --top 10` |
| "Prendi i dati di DBK.DE e SGRO.L" | data_fetch | tickers=[DBK.DE,SGRO.L] | `--skills market-data-fetch --items DBK.DE,SGRO.L --split-by ticker` |
| "Cosa comprare oggi secondo WSB?" | full_pipeline | — | Fase 1: wsb → Fase 2: analysis → Fase 3: options |

## Output all'Utente

L'output è pulito — l'utente non vede chunk, merge log, o agent mention:

```
📊 Smart Scan — Italia, Germania, Francia
Orchestrato da: subatomic-orchestrator (3 agent in parallelo)
Tempo: 84s → 32s (2.6x speedup)

Top 5 Globale:
#1  DBK.DE (Deutsche Bank)       — Score: 66.0 — Accumulation Spring
#2  SGRO.L (Segro plc)           — Score: 65.0 — Accumulation Spring
#3  PST.MI (Poste Italiane)      — Score: 63.8 — Accumulation Spring
#4  BATS.L (British American)    — Score: 64.0 — Accumulation Spring
#5  SAB.MC (Banco de Sabadell)   — Score: 62.0 — Accumulation Spring

Reports: scan_report_2026-05-31_1216.csv | scan_report_2026-05-31_1216.html
```

Se l'utente chiede deep dive, si carica stock-crypto-analysis per i top N.

## Come Usarlo

L'utente scrive in chat in italiano o inglese. La skill si auto-attiva via trigger.

```
"Scan completo Europa top 10"
  → classifica market_scan
  → dispaccia 5 agent (italy, germany, france, uk, spain)
  → merge rank → top 10 globale
  → stampa risultato

"Cosa fare di DBK.DE e SGRO.L"
  → classifica deep_dive
  → dispaccia 2 agent (stock-crypto-analysis su ciascuno)
  → merge rank → verdict + raccomandazione
  → stampa
```

## Scripts

```
scripts/classify.py    → Prende richiesta in input, stampa intent + params + orchestrator_cmd
```

## Anti-Patterns

- **Non** chiedere conferma all'utente — se l'intent è chiaro (>80% confidence), esegui direttamente
- **Non** mostrare dettagli di orchestrazione — l'utente vede solo il risultato
- **Non** mischiare intent — se rilevi `market_scan` + `deep_dive`, dai priorità a `full_pipeline`
