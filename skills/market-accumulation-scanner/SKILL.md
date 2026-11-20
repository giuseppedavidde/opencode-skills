---
name: market-accumulation-scanner
description: >
  Scans stock/crypto markets for accumulation patterns via trading MCP.
  Use when the user asks "scan", "scanner", "market scan", "find stocks".
metadata:
  argument-hint: "[universe or ticker list]"
---

# Market Scanner

The scoring lives only in the trading MCP (`mcp/src/trading_mcp/analysis/scanner.py`).
The scripts of this skill do not score: they call the MCP code or maintain the universe files.

## MCP tools

| Tool | What it returns | What it does not return |
|---|---|---|
| `scan_market` | A ranking of the universe: `final_score` (0-100), dimensions, modifiers, indicators, sentiment breakdown, flags, pattern | A verdict, a stop or a target. A high score is not a buy signal |
| `analyze_stock` | The verdict of one ticker, with confidence, entry and exit levels | — |

The agent prompt decides when a scan row needs `analyze_stock`. This skill does not ask for an automatic deep dive.

## Execution

### Step 1 — Scan via MCP (server already running)
```
Call: scan_market(universe="<NAME>", min_score=50, top_n=15, fetch_news=True)
```

For custom tickers:
```
Call: scan_market(tickers="AAPL,MSFT,NVDA", min_score=40, top_n=10, fetch_news=True)
```

The MCP server uses a thread pool: about 45 s for 500 tickers.
It returns ranked JSON with dimensions, modifiers, indicators and sentiment breakdown.
Check the count of failures and the data time of the result. A partial scan is not a full ranking.

### Step 2 — Salva i risultati dello scan su file
Il server MCP `scan_market` restituisce JSON nel contesto. NON scrive file.
Salva l'output del tool in un file, così `uoa_flow.py` lo può incrociare:

```
python3 -c "import json,pathlib; p=pathlib.Path('/tmp/opencode/scan_results.json'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(<ARRAY_RISULTATI>))"
```

Il file contiene un array JSON di oggetti con il campo `ticker` (o `symbol`). Formato atteso da `--scan-json`:

```json
[
  {"ticker": "AAPL", "final_score": 85.2},
  {"ticker": "MSFT", "final_score": 78.1}
]
```

`uoa_flow.py` (`load_scan_map`) accetta un array di dict con chiave `ticker` **o** `symbol`, oppure un dict con la lista `results`/`tickers`.
Il punteggio dell'incrocio viene da `final_score`, `score` o `finalScore`. È opzionale: per il flag `in_scan` basta il simbolo.

### Step 3 — UOA Flow (DEFAULT, sempre)
Incrocia le Unusual Options Activity (UOA) di Barchart con i risultati dello scan.
Il bridge `opencli barchart flow` dà il feed. È screening e contesto: verifica con i tool nativi prima di decidere.

```
# dalla dir della skill (scripts/ è qui)
"$HOME/.local/share/opencode/trading-mcp-venv/bin/python" scripts/uoa_flow.py --limit 100 --scan-json /tmp/opencode/scan_results.json
```

(`python3` va bene se ha `yfinance` e `pydantic`.)

Le bande OTM seguono `gen_report.py`: put ideale 12-22% OTM (limite 4-45%), call ideale 0-15% OTM (limite 0-35%).
I segnali nella banda ideale vanno nella tabella primaria. I segnali solo dentro il limite vanno nella sezione "wide". Il resto (anche ITM) è scartato.
Filtri del rumore: notional (`--min-notional`), volume (`--min-volume`), penny (`--min-price`), finestra DTE (`--dte-min`/`--dte-max`).
Ordine: banda ideale prima, poi `in_scan`, poi Vol/OI decrescente.

Il campo `iv` del feed Barchart è anomalo (0.4%-11%). NON usarlo per decisioni. Output strutturato opzionale con `--json-out`.

**Se fallisce** (bridge giù, opencli assente, login Barchart mancante): NON bloccare lo screening. Scrivi all'utente che l'UOA non è disponibile e prosegui con lo scan.

### Step 4 — Vista unica all'utente
Presenta in un'unica vista:
1. Tabella scan: `# | Ticker | Score | Pattern | Sector | Price | Flags`. Scrivi che lo score è una classifica, non un verdetto.
2. Tabella UOA (banda ideale + wide) con il flag `InScan` (`✓` = ticker presente nello scan). Le UOA sono contesto.

### Step 5 — Opzioni (se richieste)
Una strategia in opzioni parte dal verdetto di `analyze_stock`, non dallo score dello scan.
Usa solo strutture a rischio definito. Con un verdetto Avoid non aprire posizioni.

## Universes
`us_large` | `us_tech` | `all` | `italy` | `germany` | `france` | `uk` | `spain` | `crypto`

I file sono in `data/`. Il server li legge da `TRADING_TICKERS_DIR`, altrimenti da `TRADING_SKILLS_DIR/market-accumulation-scanner/data`.

## Scripts

| Script | Ruolo |
|---|---|
| `scripts/scanner.py` | Wrapper del codice MCP di `scan_market` per i job cron. Scrive `reports/<universe>/scan_report_*.csv` e `.html`. Nessuna logica di scoring propria |
| `scripts/deep_dive.py` | Wrapper di `analyze_stock` (via `trading_mcp.trading_cli`). `--save` scrive `reports/deep_dives/deep_dive_<ticker>.json` |
| `scripts/refresh_tickers.py` | Aggiorna i CSV degli universi in `data/` |
| `scripts/watchlist_update.py` | Aggiorna `watchlist_state.json` dai report CSV |
| `scripts/compare_reports.py` | Confronta due report CSV |
| `scripts/scheduler.py` | Installa o rimuove i job cron dello scanner |
| `scripts/uoa_flow.py` | Incrocio UOA (Step 3) |
| `scripts/gen_report.py` | Report PDF di una strategia in opzioni |

Esegui `scanner.py` e `deep_dive.py` con la venv del MCP: `~/.local/share/opencode/trading-mcp-venv/bin/python`.
