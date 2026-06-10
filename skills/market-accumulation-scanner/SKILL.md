---
name: market-accumulation-scanner
description: >
  Scans US (NYSE/NASDAQ S&P 500, NASDAQ 100) and European (FTSE MIB, DAX 40,
  CAC 40, FTSE 100, IBEX 35) stock markets for tickers exhibiting accumulation
  patterns, Wyckoff Springs, favorable Volume Profile setups, and fundamental
  value — derived from the stock-crypto-analysis 5-dimensional framework
  with enhancement modifiers (Multi-TF, SOT/Weis Wave, Squeeze Play,
  Earnings Surprise, 6-Clue Test). Supports US, European, and Crypto universes.
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
argument-hint: [universe name (us_large, us_tech, italy, germany, france, uk, spain, all, crypto) or custom ticker list like "MSFT, AAPL, ENI.MI"]
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
- `wallstreetbets-pump-detect` — Reddit/WSB pump detection crossover
- `book-to-skill` — News aggregation patterns from authoritative sources

## Triggers

`scan accumulation`, `scanner`, `screening mercati`, `market scan`,
`find stocks`, `cerca ticker`, `scan europe`, `scan US`, `stock screener`,
`accumulation scan`, `find me stocks to analyze`, `cosa cercare`,
`scan setups`, `scansiona [ticker list]`,
`analizza [singolo ticker]`, `scansiona [singolo ticker]`,
`[ticker] scan`, `[ticker] opzioni [scadenza]`,
`scansiona [ticker] e opzioni [scadenza]`,
`analisi [ticker] con opzioni [scadenza]`,
`confronta report`, `compare reports`, `A/B test scanner`,
`confronto A/B`, `report comparison`, `differenze report`

## Tooling

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/compare_reports.py` | Confronto A/B tra report vecchio e nuovo formato | `python3 scripts/compare_reports.py <vecchio.csv> <nuovo.csv> [--report output.md]` |
| `scripts/scheduler.py` | Scheduling cron di scan periodici | `python3 scripts/scheduler.py --setup` |
| `scripts/watchlist_update.py` | Aggiornamento watchlist con evoluzione score | `python3 scripts/watchlist_update.py` |

### Report Comparison (A/B Test)

Per confrontare l'impatto delle nuove funzionalità (competitive dimension, sentiment breakdown):
```bash
# Confronto manuale
python3 scripts/compare_reports.py <vecchio.csv> <nuovo.csv> --report reports/comparison.md

# Confronto automatico (ultimi due report)
python3 scripts/compare_reports.py --auto --report reports/comparison_latest.md
```

Il report mostra:
- Delta final_score per ticker comuni
- Impatto della dimensione competitive (+5.0 per score=100)
- Analisi sentiment breakdown (aggregato vs media sub-dimensioni)
- Statistiche aggregate (ticker migliorati/peggiorati)

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

**5 Dimensions** (each 0–100, weighted) + Enhancement Modifiers:

| # | Dimensione | Peso | Metriche Chiave | Enhancement Modifiers |
|---|-----------|:----:|-----------------|----------------------|
| 1 | **Wyckoff** | 20% | Range position, HH/HL, Spring, MA50/200, volume trend | **SOT/Weis Wave** (±10), **6-Clue Test** (±10) |
| 2 | **Volume Profile** | 20% | Price vs VPOC/VA, vol ratio, profile shape | — |
| 3 | **Price Action** | 15% | RSI, 25ema slope, VPA validations, Rally Velocity | **Multi-Timeframe Analysis** (±10) |
| 4 | **Sentiment** | 20% | 9 sub-dimensions: SI, Options, Insider, Retail, Institutional, Momentum, Web News, Social Media, Earnings Quality | **Squeeze Play System** (±10) |
| 5 | **Fundamentals** | 25% | P/E + EQM, Value Trap Check, Price vs Consensus, revenue, margins, D/E, ROE, ROA | **Earnings Surprise Trend** (±10) |

**Aggregazione** (5 dimensioni + modifiers):
```
wyckoff_adj = wyckoff + sot_mod + clue6_mod
pa_adj = pa + mtf_mod
sentiment_adj = sentiment + squeeze_mod
fundamentals_adj = fundamentals + earnings_surprise_mod

final = wyckoff_adj * 0.20 + volprof * 0.20 + pa_adj * 0.15 + sentiment_adj * 0.20 + fundamentals_adj * 0.25
```

### Enhancement Modifiers (da libri di trading)

| Modifier | Fonte | Effetto | Range |
|----------|-------|---------|-------|
| **Multi-Timeframe Analysis** | VPA (Coulling) | Allinea trend su 3 TF (20d/50d/200d) | ±10 su PA |
| **SOT + Weis Wave** | Trades About to Happen (Weis) | Shortening of Thrust + onde volume + Crabel NR7/ID-NR4 | ±10 su Wyckoff |
| **Squeeze Play System** | Trading Against the Crowd (Summa) | Sentiment oscillator EMA + price trigger + Smart Money divergence | ±10 su Sentiment |
| **Earnings Surprise Trend** | Earnings data (yfinance) | Beat/miss streak, avg surprise magnitude | ±10 su Fundamentals |
| **6-Clue Test** | Wyckoff 2.0 (Villahermosa) | 6 indizi formali accumulazione/distribuzione | ±10 su Wyckoff |

### Crypto Universe (Alert-Predict-Confirm)

Per crypto (`--universe crypto`), il framework usa:
- **Wyckoff** 25% + **Volume Profile** 25% + **Price Action** 20% + **Crypto APC** 30%
- **Alert-Predict-Confirm** (Crypto Technical Analysis - John & Law): RSI divergence (Alert), MACD crossover (Predict), Volume confirmation (Confirm). Tutti e 3 allineati = segnale forte.

### Sentiment — Sub-Dimension Breakdown

The Sentiment score (15% of total) is itself an aggregation of 3 sub-dimensions:

| Sub-Dimension | Weight in Sentiment | Weight in Total | Source |
|:-------------:|:------------------:|:---------------:|--------|
| **Traditional** | 40% | 6.0% | yfinance info (short interest, DTC, institutional ownership) |
| **Web News** | 35% | 5.25% | Finviz RSS, Yahoo Finance news, WSJ headlines via websearch/webfetch |
| **Social Media** | 25% | 3.75% | Reddit r/wallstreetbets (via wallstreetbets-pump-detect), X/Twitter buzz via websearch |

**Formula Sentiment**:
```python
sentiment = traditional * 0.40 + web_news * 0.35 + social_media * 0.25
```

#### Traditional Sentiment (0-100)
Same as current: short interest, days to cover, institutional ownership.

#### Web News Sentiment (0-100)
Collected per ticker during scan using:
1. **Primary**: `webfetch` on `https://finviz.com/quote.ashx?t=TICKER` — extract news headlines table
2. **Fallback**: `webfetch` on Yahoo Finance news feed for the ticker
3. **Deep dive** (Phase 5 only): `websearch` for "TICKER stock news 2026 WSJ" + `webfetch` on professional sources

Score from headline polarity (first 10 headlines):
| Signal | Score Δ |
|--------|:-------:|
| 4+ positive headlines (upgrade, buy, beat, growth) | +40 |
| 2-3 positive headlines | +20 |
| Neutral / mixed (0-1 positive, 0-1 negative) | 0 |
| 2-3 negative headlines (downgrade, miss, cut, investigation) | -20 |
| 4+ negative headlines | -40 |
| No news found | 0 (skip, score from other sub-dimensions) |
| Earnings beat / guidance raise | +30 bonus |
| Regulatory approval / partnership | +20 bonus |
| Lawsuit / investigation / SEC | -30 penalty |

Base: 50. Final web_news = clamp(50 + score_delta, 0, 100).

#### Social Media Sentiment (0-100)
Collected via cross-reference with `wallstreetbets-pump-detect`:

1. **Pre-scan**: Before main scan, run `wallstreetbets-pump-detect` once to get the current WSB hotlist (hype score, mention count, sentiment for each ticker mentioned)
2. **Cross-reference**: During scan, for each ticker, check if it appears in the WSB hotlist
3. **X/Twitter check**: `websearch` for "TICKER stock 2026" and gauge tweet sentiment from first ~10 results

| Condition | Score Δ |
|-----------|:-------:|
| Ticker on WSB hotlist, early FOMO, bullish sentiment | +40 |
| Ticker on WSB hotlist, mid FOMO, mixed sentiment | +20 |
| Ticker on WSB hotlist, late/exit FOMO | -20 |
| Not on WSB hotlist but positive X buzz | +10 |
| Not on WSB hotlist | 0 |
| Negative X buzz (prominent sell calls, panic) | -15 |

Base: 50. Final social_media = clamp(50 + score_delta, 0, 100).

#### Data Collection Efficiency

For large scans (600+ tickers):
- Skip web_news and social_media during Phase 2 (bulk scoring) → set to neutral 50
- Apply news + social overlay **only for top N candidates** (Phase 5 Deep Dive)
- Exception: if a ticker is already in the WSB hotlist, it gets a flag during scan

For small scans (< 50 tickers or custom list):
- Fetch web_news for all tickers in batch (1s sleep between)
- Cross-reference WSB hotlist

### Aggiornamento Report — Sentiment Breakdown

In report output, the Sentiment column shows a composite color:
```
SENT=72 | (T:80 N:65 S:70)
                  ^     ^
                  |     social_media (WSB + X)
                  web_news (Finviz, WSJ, Yahoo)
                  Traditional (SI + DTC + Inst)
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

### Phase 5 — Deep Dive on Top 3 (or Single Ticker)

Load `stock-crypto-analysis` for each of the top 3 candidates, now enriched with news and social context collected in Phase 2:

```
Per ogni candidato:
1. Esegui stock-crypto-analysis con i dati di news/social già raccolti
2. Unified Verdict + Score + Razionale per dimensione
3. Web News Snapshot (ultime 5-10 headlines con sentiment)
4. Social Media Snapshot (WSB hype score, X buzz direzione)
5. Raccomandazione finale (Entry / Watchlist / Avoid)
```

#### News Deep Dive (Phase 5 only)

For each top-3 candidate, fetch deeper news context:

```python
# 1. Finviz headlines
ticker_news_url = f"https://finviz.com/quote.ashx?t={ticker}"
# webfetch → parse news table → polarity score

# 2. Yahoo Finance news
ticker = yf.Ticker(ticker)
news = ticker.news  # latest 50+ headlines

# 3. Professional sources (for key candidates only)
websearch(f"{ticker} stock analysis 2026 site:wsj.com")
websearch(f"{ticker} stock rating 2026 site:bloomberg.com")
```

#### Social Deep Dive (Phase 5 only)

Run `wallstreetbets-pump-detect` specifically for the ticker:

```
wsb scan on $TICKER
# → Hype score, FOMO phase, mention count, sentiment
```

Also check X/Twitter:
```
websearch for "TICKER stock 2026" and gauge tweet polarity
websearch for "$TICKER" and filter for recent tweet reactions
```

### Phase 6 — Auto-Chain Mode (Single Ticker Analysis)

When the user asks to **scan/analyze a single ticker** (1 ticker, not a universe), or
when they ask for a scan with options expiry (e.g. "scan IGV and opzioni Dec 2026"),
the agent should chain automatically through all 3 skills:

```
User: "Scansiona IGV e aiutami con le opzioni Dec 2026"
                         ↓
[market-accumulation-scanner]
  1. Identifica: input = 1 ticker → Auto-Chain Mode
   2. Esegue scanner.sh --tickers "IGV" --fetch-news (6-dimension score con Competitive Positioning)
  3. Mostra score scanner completo (con tutte e 8 le sub-dimensioni sentiment)
  4. Chiama:
     ↓
  [stock-crypto-analysis]
    5. Carica stock-crypto-analysis skill
    6. Esegue unified verdict (6-dimension + Adaptive Macro Matrix + modificatori)
    7. Se score ≥ 70, chiama:
       ↓
    [options-strategy-suggestions]
      8. Carica options-strategy-suggestions skill
      9. Usa scadenza fornita dall'utente (Dec 2026) o default ≥45 DTE
      10. Produce strategia opzioni (Synthetic Long 2:1 preferita)
      11. Output completo unificato
```

#### Rules for Auto-Chain Mode

| Condition | Action |
|-----------|--------|
| 1 ticker, nessuna scadenza menzionata | Scanner → stock-crypto-analysis. Fermati al unified verdict. |
| 1 ticker, scadenza opzioni menzionata | Scanner → stock-crypto-analysis → options-strategy-suggestions con expiry specificato |
| 1 ticker, "cosa fare" / "cosa farne" | Scanner → stock-crypto-analysis. Unified verdict + raccomandazione. |
| 2-5 ticker | Scanner normale (classifica). Senza deep dive automatico. |
| 6+ ticker o universe | Scanner normale (classifica). Phase 5 solo top 3. |

#### Single Ticker Output Template (Auto-Chain)

```
## 📋 Market Accumulation Scan — [TICKER] ([DATE])

### Scanner Score: XX/100

| Dimensione | Peso | Score | Dettaglio |
|-----------|:----:|:-----:|-----------|
| Wyckoff | 15% | XX/100 | [range position, MA50/200, volume trend] |
| Volume Profile | 20% | XX/100 | [VPOC, VA, vol ratio] |
| Price Action | 20% | XX/100 | [RSI, 25ema, VPA, Rally Velocity] |
| Competitive Positioning | 10% | XX/100 | [ROE, margins, ROA, mcap — moat proxy] |
| Sentiment | 15% | XX/100 | (see breakdown below, includes Earnings Quality) |
| Fundamentals | 20% | XX/100 | [P/E + EQM, Value Trap, Price vs Consensus] |

### Sentiment Breakdown (9 sub-dimensions)

| Sub-dimensione | Peso | Score | Dettaglio |
|:--------------:|:----:|:-----:|-----------|
| Short Interest | 12% | XX/100 | SI XX% | DTC X.X → [dettaglio] |
| Options Sentiment | 12% | XX/100 | P/C vol X.XX | OI X.XX | IV skew X.XX → [dettaglio] |
| Insider Trading | 12% | XX/100 | Buys=X Sells=X → [dettaglio] |
| Institutional | 12% | XX/100 | Inst XX% | Buyback X.X% → [dettaglio] |
| **Earnings Quality** | **20%** | **XX/100** | **EPS growth, accrual proxy, FCF — Sloan 1996** |
| Web News | 8% | XX/100 | [N bullish / N bearish / N total headlines] |
| Social Media | 8% | XX/100 | WSB hype XX | FOMO [phase] | [sentiment] |
| Retail Sentiment | 8% | XX/100 | Vol ratio X.Xx | Beta X.X → [dettaglio] |
| Relative Momentum | 8% | XX/100 | 1mo X.X% | 3mo X.X% | 6mo X.X% → [dettaglio] |
| Web News | XX/100 | [N bullish / N bearish / N total headlines] |
| Social Media | XX/100 | WSB hype XX | FOMO [phase] | [sentiment] |

### Headlines (Finviz)
- [BULL/BEAR/NEU]: [headline 1]
- [BULL/BEAR/NEU]: [headline 2]
...

→ **Score soglia**: se ≥50 → avvio catena automatica

→ Loading stock-crypto-analysis for unified verdict...
────────────────────────────────────

### Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Score: XX%

**Perché**:
- Wyckoff: [fase] → [+/-X pts]
- Volume Profile: [shape] → [+/-X pts]
- Price Action: [setup] → [+/-X pts]
- Sentiment: [segnale] → [+/-X pts]
- Fondamentali: [metriche] → [+/-X pts]

**Raccomandazione**:
| Azione | Entry | Stop Loss | Target | Orizzonte | Sizing |
|--------|-------|-----------|--------|-----------|--------|
| [Entry/Wait/Avoid] | $XX-XX | $XX | $XX | X mesi | X% |

→ Se score ≥ 70 → Loading options-strategy-suggestions...
────────────────────────────────────

### 🎯 Strategia Opzioni: [Nome strategia]

**Scadenza**: [data] (XXX DTE)
**IV Regime**: [HIGH / NORMAL / LOW] (IV XX%)

**Struttura del Trade**:
- [Qty]x [Call/Put] @ $XXX
- Netto: [Credito/Debito] $XXX
- Breakeven: $XXX

**Greeks Snapshot**:
| Greek | Valore | Impatto |
|-------|--------|---------|
| Delta | X.XX | Direzionalità |
| Gamma | X.XX | Accelerazione |
| Theta | $X.XX/g | Time decay |
| Vega | $X.XX | IV sensitivity |

**Risk / Reward**:
- Max Loss: $XX (%) | Max Profit: $XX (%) | Probabilità: ~XX%
- Rischio: [Basso / Medio / Alto]

**Exit Plan**:
- TP: XX% del max profit o [condizione]
- SL: XX% della max loss o prezzo $XX
- Time Stop: [DTE]gg senza movimento
- Adjustment: [Roll, spread adjustment]
```

## Output Template (Multi-Ticker Scan)
```
## 📋 Market Accumulation Scan — [DATE]

**Universe**: [name] | **Tickers screened**: XXX
**Candidates found**: Y (score >= 50) | **Top 15 shown**
**Reports**: scan_report_[ts].csv | scan_report_[ts].html

### Top 15 Ranked

| # | Ticker | Name      | Score | WYCK | VP  | PA  | COMP | SENT | FUND | Pattern               |
|---|---|---|---|---|---|---|---|---|---|-----------------------|
| 1 | $AAPL  | Apple Inc | 82    | 85   | 75  | 78  | 100  | 60   | 90   | Accumulation Spring   |
| 2 | ...    | ...       | ...   | ...  | ... | ... | ...  | ...  | ...                   |

### #1: $TICKER — Pattern Match
- Wyckoff: [score] → [dettaglio]
- Volume Profile: [score] → [dettaglio]
- Price Action: [score] → [dettaglio] (incl. Rally Velocity)
- Competitive Positioning: [score] → [ROE, margins, mcap — moat proxy]
- Sentiment: [score] → (T:XX N:XX S:XX EQ:XX)
  - Traditional: SI XX% | DTC X.X | Inst XX% → [+/-X pts]
  - Web News: [positivo/neutro/negativo] → [+/-X pts]
    - [Headline 1], [Headline 2], ...
  - Social Media: [WSB: hype XX / X buzz] → [+/-X pts]
  - Earnings Quality: [EPS growth, accrual proxy] → [+/-X pts]
- Fundamentals: [score] → [P/E + EQM, Value Trap check, Price vs Consensus]

→ Loading stock-crypto-analysis for full verdict...

### Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Score: XX%

**Rationale**:
- Wyckoff: ... → +/-X pts
- Volume Profile: ... → +/-X pts
- Price Action: ... → +/-X pts (Rally Velocity: ...)
- Competitive Positioning: ... → +/-X pts
- Sentiment: ... → +/-X pts (Earnings Quality: ...)
- Fundamentals: ... → +/-X pts (Earnings Quality Modifier, Value Trap, Price vs Consensus)

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
