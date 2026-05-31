---
name: market-accumulation-scanner
description: >
  Scans US (NYSE/NASDAQ S&P 500, NASDAQ 100) and European (FTSE MIB, DAX 40,
  CAC 40, FTSE 100, IBEX 35) stock markets for tickers exhibiting accumulation
  patterns, Wyckoff Springs, favorable Volume Profile setups, and fundamental
  value — derived from the stock-crypto-analysis 6-dimensional framework.
  Use when the user asks "scan accumulation", "scanner", "screening mercati",
  "market scan", "find stocks", "cerca ticker", "scan europe", "scan US",
  "stock screener", "accumulation scan", "find me stocks to analyze",
  "cosa cercare", "scan setups", "scansiona [ticker list]".
allowed-tools:
  - read
  - write
  - bash
  - glob
  - grep
  - task
argument-hint: [universe name (us_large, us_tech, italy, germany, france, uk, spain, all) or custom ticker list like "MSFT, AAPL, ENI.MI"]
orchestrator:
  parallel: true
  split_by: ticker
  chunk_size: 15
  merge: rank
  merge_key: final_score
  top_n: 15
---

# Market Accumulation Scanner

Scans large universes of US and European stocks through the
**stock-crypto-analysis** scoring framework to surface tickers in
accumulation phases, with healthy volume profile structures, bullish
price action, favorable sentiment setups, and solid fundamentals.

## Skill Dependencies

- `stock-crypto-analysis` — Full unified verdict on top candidates
- `market-data-fetch` — Data collection patterns
- `python-venv` — Python environment for the scanner script
- `wyckoff-2-0` — Wyckoff phase/Spring detection
- `volume-profile` — VPOC, Value Area, profile shapes
- `volume-price-analysis` — Validation/Anomaly, Effort/Result
- `price-action-volman` — 25ema, buildup, price structure
- `trades-about-to-happen` — Springs, clusters, SOT
- `trading-against-the-crowd` — Short interest, sentiment

## Triggers

`scan accumulation`, `scanner`, `screening mercati`, `market scan`,
`find stocks`, `cerca ticker`, `scan europe`, `scan US`, `stock screener`,
`accumulation scan`, `find me stocks to analyze`, `cosa cercare`,
`scan setups`, `scansiona [ticker list]`

## Core Framework — 5 Phase Workflow

### Phase 1 — Define Universe

#### Pre-built Universes

| Name | Markets | Size | Suffix | Source |
|------|---------|:----:|--------|--------|
| `us_large` | NYSE, NASDAQ | ~500 | — | SPY constituents |
| `us_tech` | NASDAQ | ~100 | — | QQQ constituents |
| `italy` | Milan | 40 | `.MI` | FTSE MIB |
| `germany` | Frankfurt | 40 | `.DE` | DAX 40 |
| `france` | Euronext Paris | 40 | `.PA` | CAC 40 |
| `uk` | London | 100 | `.L` | FTSE 100 |
| `spain` | Madrid | 35 | `.MC` | IBEX 35 |
| `all` | All combined | ~900 | mixed | — |

#### Custom Ticker List

Pass comma-separated tickers to skip universe loading:

```
scan accumulation on MSFT, AAPL, ENI.MI, SAP.DE, BNP.PA
```

Ticker lists are in `data/us_tickers.csv` and `data/europe_tickers.csv`.

### Phase 2 — Multi-Dimensional Screening

Use the **subatomic-orchestrator** for parallel dispatch on large universes
or multi-market scans. The scanner script supports two modes:

- `--list-tickers` — output ticker symbols as JSON array (for chunking)
- `--json-output` — output scored results as JSON array (for aggregation)

#### A) Large Universe Scan (us_large ~600, us_tech ~100, all ~900)

1. Load `subatomic-orchestrator` skill
2. Get ticker list:
   ```bash
   python3 scripts/scanner.py --universe us_large --list-tickers
   ```
3. Apply **Pattern 1 (Batch Analysis)** with `split_by: ticker`, `chunk_size: 15`
4. Split tickers into chunks of 15
5. Dispatch each chunk via `task` tool:
   ```
   Run market-accumulation-scanner on tickers: AAPL, MSFT, NVDA, ...
   Execute from the skill directory:
     source .venv/bin/activate && \
     python3 scripts/scanner.py --tickers "AAPL,MSFT,NVDA,..." --json-output
   Return the JSON array of scored results.
   ```
6. Merge all chunk results, sort by `final_score` descending
7. Apply `--min-score` filter and take top N
8. Generate report (console table + CSV + HTML)

#### B) Multi-Market Scan (italy, germany, france, uk, spain, or all)

Load `subatomic-orchestrator` and apply **Pattern 2 (Market Scan)**:
- 1 agent per market, each running:
  ```bash
  python3 scripts/scanner.py --universe germany --json-output
  ```
- Merge global results sorted by `final_score`, take global top N

For "scan all" specifically, also scan `us_large` and `us_tech` as single
markets each (4 agents total for EU + 2 for US = 6 agents, one batch).

#### C) Small / Custom Ticker List (≤15 tickers)

Direct execution — overhead of parallel dispatch > gain:

```bash
python3 scripts/scanner.py --tickers "MSFT, AAPL, ENI.MI" --top 15
python3 scripts/scanner.py --universe us_large --min-score 50 --top 15
```

**5 Dimensions** (each 0–100, weighted):

| # | Dimension | Weight | Key Metrics |
|---|-----------|:------:|-------------|
| 1 | **Wyckoff** | 25% | Range position, HH/HL, Spring, MA50/200, volume trend |
| 2 | **Volume Profile** | 20% | Price vs VPOC/VA, vol ratio, profile shape |
| 3 | **Price Action** | 20% | RSI, 25ema slope, VPA validations, Effort/Result |
| 4 | **Sentiment** | 15% | Short interest %, Inst ownership, DTC |
| 5 | **Fundamentals** | 20% | P/E, revenue growth, margins, D/E, mkt cap |

**Aggregation**:
```
final = wyckoff * 0.25 + volprof * 0.20 + pa * 0.20 + sentiment * 0.15 + fundamentals * 0.20
```

See `cheatsheet.md` for per-dimension scoring tables and `patterns.md` for
composite pattern definitions.

### Phase 3 — Ranking & Filtering

1. Sort by `final_score` descending
2. Filter: `score >= min_score` (default 50)
3. Exclude tickers with critical anomalies (score 0 in fundamentals + undefined P/E + negative margins)
4. Take top N (default 15)

### Phase 4 — Report Generation

3 outputs:
- **Console table** — colored top 15 with per-dimension breakdown
- **CSV** — `scan_report_YYYY-MM-DD_HHMM.csv` (all scores)
- **HTML** — `scan_report_YYYY-MM-DD_HHMM.html` (color-coded table + histogram + expandable details)

### Phase 5 — Deep Dive on Top 3

Load `stock-crypto-analysis` for each of the top 3 candidates:

```
Per ogni candidato:
1. Esegui stock-crypto-analysis
2. Unified Verdict + Score + Razionale per dimensione
3. Raccomandazione finale (Entry / Watchlist / Avoid)
```

## Output Template

```
## 📋 Market Accumulation Scan — [DATE]

**Universe**: [name] | **Tickers screened**: XXX
**Candidates found**: Y (score >= 50) | **Top 15 shown**
**Reports**: scan_report_[ts].csv | scan_report_[ts].html

### Top 15 Ranked

| # | Ticker | Name      | Score | WYCK | VP  | PA  | SENT | FUND | Pattern               |
|---|--------|-----------|:-----:|:----:|:---:|:---:|:----:|:----:|-----------------------|
| 1 | $AAPL  | Apple Inc | 82    | 85   | 75  | 78  | 60   | 90   | Accumulation Spring   |
| 2 | ...    | ...       | ...   | ...  | ... | ... | ...  | ...  | ...                   |

### #1: $TICKER — Pattern Match
- Wyckoff: [score] → [dettaglio]
- Volume Profile: [score] → [dettaglio]
- Price Action: [score] → [dettaglio]
- Sentiment: [score] → [dettaglio]
- Fundamentals: [score] → [dettaglio]

→ Loading stock-crypto-analysis for full verdict...

### Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Score: XX%

**Rationale**:
- Wyckoff: ... → +/-X pts
- Volume Profile: ... → +/-X pts
- Price Action: ... → +/-X pts
- Sentiment: ... → +/-X pts
- Fundamentals: ... → +/-X pts

### Raccomandazione Finale
| Azione | Entry | Stop Loss | Target | Orizzonte | Sizing |
|--------|-------|-----------|--------|-----------|--------|
| **Entry** | $XX-XX | $XX | $XX | X mesi | X% |

[Ripetere per #2 e #3]
```

## Performance & Rate-Limiting

- Tickers processed in batches of 20 with 1s sleep between batches
- Full US scan (~600): ~4-6 min | EU (~250): ~2 min | All (~900): ~7-10 min
- Auto-retry on rate-limit (3 attempts with exponential backoff)

## Anti-Patterns

- **Non** trattare gli score come raccomandazioni — sono filtri preliminari
- **Non** saltare il deep dive (Phase 5) — lo scanner è un pre-filter
- **Non** includere penny stocks (<$1) nella stessa classifica
- **Non** ignorare il report CSV/HTML — i dati raw aiutano ad affinare scan futuri
