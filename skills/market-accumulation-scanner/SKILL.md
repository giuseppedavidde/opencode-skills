---


name: market-accumulation-scanner
description: >
  Scans stock/crypto markets for accumulation patterns via trading MCP.
  Use when the user asks "scan", "scanner", "market scan", "find stocks".
metadata:
  argument-hint: "[universe or ticker list]"
---

# Market Scanner

## Execution

### Step 1 — Scan via MCP (server already running, zero cold start)
```
Call: scan_market(universe="<NAME>", min_score=50, top_n=15, fetch_news=True)
```

For custom tickers:
```
Call: scan_market(tickers="AAPL,MSFT,NVDA", min_score=40, top_n=10, fetch_news=True)
```

The MCP server uses ThreadPoolExecutor (20 workers) — ~45s for 500 tickers.
Returns ranked JSON with dimensions, modifiers, indicators, sentiment breakdown.

### Step 2 — Salva i risultati dello scan su file
Il server MCP `scan_market` restituisce JSON nel contesto — NON scrive file.
Salva l'output del tool in un file temporaneo così `uoa_flow.py` può incrociarlo:

```
python3 -c "import json,pathlib; pathlib.Path('/tmp/opencode/scan_results.json').write_text(json.dumps(<ARRAY_RISULTATI>))"
```

Oppure qualsiasi metodo equivalente (Write tool, heredoc). L'importante è che
`/tmp/opencode/scan_results.json` contenga un array JSON di oggetti con campo
`ticker` (o `symbol`). Formato esatto atteso da `--scan-json`:

```json
[
  {"ticker": "AAPL", "final_score": 85.2},
  {"ticker": "MSFT", "final_score": 78.1}
]
```

`uoa_flow.py` (`load_scan_map`) accetta: array di dict con chiave `ticker`
**o** `symbol` (entrambe gestite); oppure un dict con lista `results`/`tickers`.
Il punteggio per l'incrocio è letto da `final_score`, `score` o `finalScore`
(opzionale — serve solo per `scan_score`; il flag `in_scan` basta il simbolo).

### Step 3 — UOA Flow (DEFAULT, sempre)
Incrocia le Unusual Options Activity (UOA) di Barchart con i risultati dello
scan appena salvato. Il bridge `opencli barchart flow` fornisce il feed
(screening/contesto: ri-ancorare sui tool nativi prima di decidere).

```
# dalla dir della skill (scripts/ è qui)
/home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/python scripts/uoa_flow.py --limit 100 --scan-json /tmp/opencode/scan_results.json
```

(`python3` va altrettanto bene se ha `yfinance`+`pydantic`; fallback anche la
venv della skill `.venv/bin/python`.)

Le bande OTM rispecchiano `gen_report.py` (~righe 356-385): put ideale
12-22% OTM (hard bound 4-45%), call ideale 0-15% OTM (hard bound 0-35%).
I segnali nella banda ideale vanno in tabella primaria, quelli solo dentro
l'hard bound in sezione "wide"; il resto (incluso ITM) è scartato.
Filtri noise: notional (`--min-notional`), volume (`--min-volume`), penny
(`--min-price`), finestra DTE (`--dte-min`/`--dte-max`). Rank: banda ideale
prima, poi `in_scan` prima, poi Vol/OI discendente.

Il campo `iv` del feed Barchart è anomalo (0.4%-11%) e NON va usato per
decisioni. Output opzionale strutturato con `--json-out`.

**Se fallisce** (bridge giù, opencli assente, Barchart login mancante): NON
bloccare lo screening. Nota all'utente che l'UOA non è disponibile e prosegui
con lo scan normale. Lo script esce con un hint diagnostico leggibile.

### Step 4 — Vista unica all'utente
Presenta in un'unica vista:
1. Tabella scan: `# | Ticker | Score | Pattern | Sector | Price | Flags`
2. Tabella UOA (banda ideale + wide) con flag `InScan` evidenziato (`✓` =
   ticker presente nello scan). Nota che le UOA sono contesto/screening, da
   ri-ancorare sui tool nativi prima di decidere.

### Step 5 — Deep dive top 3
```
Call: analyze_stock(ticker="<TOP_TICKER>", verbose=true, fetch_news=true)
```
Repeat for top 3 candidates. Se un ticker del deep dive ha UOA in banda
ideale (flag `InScan ✓`), menzionalo nel report.

### Step 6 — Options (if requested)
Chain to `options-strategy-suggestions` skill.

## Universes
`us_large` | `us_tech` | `all` | `italy` | `germany` | `france` | `uk` | `spain` | `crypto`
