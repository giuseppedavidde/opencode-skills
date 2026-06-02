---
name: stock-crypto-analysis
description: >
  Unified market analysis that produces a single verdict (Long-Term Investment,
  Short-Term Speculation, or Avoid/Wait) by integrating 9 source skills:
  Wyckoff 2.0, Volume Profile, VPA, Price Action Volman, Trades About To Happen,
  Trading Against The Crowd, Market Data Fetch, Crypto Technical Analysis,
  and Crypto Crash Course. Use when the user wants to decide what to do with
  a stock or crypto asset, or when they ask 'cosa farne' of any financial asset.
   Includes a mandatory Phase 0 Adaptive Macro Matrix (4 windows: FULL/NORMAL/SELECTIVE/DEFENSIVE)
   with Geopolitical Sector Vector and a dynamic Risk Sizing Matrix.
allowed-tools:
  - read
  - grep
  - websearch
  - webfetch
  - task
argument-hint: [ticker, stock symbol, crypto name, or "what to do with X"]
orchestrator:
  parallel: true
  split_by: ticker
  chunk_size: 1
  merge: rank
  merge_key: final_score
  top_n: 3
---

# Stock & Crypto Unified Analysis — Hedge Fund Edition

Knowledge aggregator skill that loads 9 source skill frameworks to produce a single verdict: **Long-Term Investment**, **Short-Term Speculation**, or **Avoid/Wait**.

## Skill Dependencies

This skill loads and integrates:
- `wyckoff-2-0` — Accumulation/Distribution phases A-E, Spring/Upthrust, LPS/LPSY, 3 Laws
- `volume-profile` — VPOC, Value Area, HVN/LVN, D/P/b/Thin shapes
- `volume-price-analysis` — Validation vs Anomaly, Effort vs Result, VAP
- `price-action-volman` — Buildup, double pressure, false/tease/proper break, 25ema
- `trades-about-to-happen` — Clusters, displacement, springs/upthrusts, SOT, Weis Wave
- `trading-against-the-crowd` — Put/Call ratio, VIX, Squeeze Play, smart vs dumb money
- `market-data-fetch` — Historical data, fundamentals, holders, financials templates
- `crypto-technical-analysis` — On-chain metrics, hype analysis, indicator function framework
- `crypto-crash-course` — Tokenomics, supply mechanisms, team/whitepaper evaluation

## Triggers

`analizza`, `analysis verdict`, `cosa farne`, `short term o long term`, `investment thesis`, `unified analysis`, `analyze stock`, `analyze crypto`

## Core Principle — Weighted Multidimensional Scoring

Every asset is scored across 6 independent dimensions. Each dimension contributes a weighted sub-score (0–100). The final score determines the verdict.

### Weight Table

| # | Dimensione | Peso Stock | Peso Crypto | Skill Sorgente Primaria |
|---|-----------|-----------|-------------|------------------------|
| 1 | Wyckoff Phase | 15% | 10% | wyckoff-2-0 |
| 2 | Volume Profile | 20% | 15% | volume-profile, volume-price-analysis |
| 3 | Price Action | 20% | 15% | price-action-volman, trades-about-to-happen |
| 4 | Sentiment & Positioning | 15% | 10% | trading-against-the-crowd |
| 5 | Fondamentali | 20% | 10% | market-data-fetch |
| 6 | Competitive Positioning | 10% | 5% | market-data-fetch (nuovo) |
| 7 | Crypto Layer | — | 35% | crypto-technical-analysis, crypto-crash-course |

I pesi assicurano somma = 1.0. Wyckoff ridotto da 25%→15% per fare spazio a Competitive Positioning (10%).

---

## PHASE 0 — ADAPTIVE MACRO MATRIX

**CRITICAL**: Phase 0 runs BEFORE any asset-specific analysis. Determina la **finestra operativa**, non un blocco binario. Le crisi geopolitiche coprono il 54% dei periodi dal 2000 — il mercato non smette di funzionare, ma **cambia** quali settori performano (fonte: JP Morgan Geopolitical Risk Premium 2024).

### Step 1 — Macro Data Collection

Use `websearch` or `webfetch` to collect:

| Data Point | Source | How to fetch |
|---|---|---|
| Fed Funds Rate / latest FOMC | fred.stlouisfed.org or CNBC | `websearch "federal funds rate June 2026"` |
| DXY (US Dollar Index) weekly trend | investing.com or tradingview | `websearch "DXY chart weekly June 2026"` |
| VIX level | finance.yahoo.com | `websearch "VIX level today June 2026"` |
| US 10Y Real Yield | fred.stlouisfed.org | `websearch "US 10 year real yield today"` |
| Fear & Greed Index | coinmarketcap.com / alternative.me | `websearch "Fear and Greed Index crypto today"` |
| Geopolitical risk | Reuters / BBC | `websearch "major geopolitical events June 2026"` |
| Fed Balance Sheet / QT status | fred.stlouisfed.org | `websearch "Fed balance sheet quantitative tightening 2026"` |

### Step 2 — Macro Scorecard (0-18)

Score each condition. **1 point per condition met**. If data unavailable, assign 0.

| # | Condizione | Punti | Long ammesso se | Short ammesso se |
|---|---|---|---|---|
| 1 | **Fed Policy** | 2 | Tassi stabili o in calo; FOMC passato da >7gg | Tassi stabili o in salita |
| 2 | **DXY Trend** | 2 | DXY < EMA50 weekly O in calo da 4+ settimane | DXY > EMA50 weekly O in salita |
| 3 | **VIX** | 2 | VIX < 25 (nessun panic) | VIX > 15 (volatilità per short) |
| 4 | **Liquidità Globale** | 2 | QT finito o in pausa; Reverse Repo stabile | QT attivo (restrizione monetaria aiuta short) |
| 5 | **Geopolitica** | 2 | Nessun conflitto attivo tra potenze economiche | Conflitto attivo = risk-off |
| 6 | **10Y Real Yield** | 2 | < 1.5% (risorse asset favorite) | > 2% (risk asset sotto pressione) |
| 7 | **Risk Sentiment** | 2 | Fear & Greed < 30 (estremo = opportunità long) | Fear & Greed > 70 (euforia = opportunità short) |
| 8 | **Eventi Macro** | 2 | Nessun evento macro critico nei prossimi 7gg | Evento macro in arrivo (CPI, NFP, FOMC) |
| 9 | **BTC Dominance (crypto)** | 2 | In calo o stabile sotto 58% | In salita sopra 62% (altcoin sotto pressione) |
| — | **TOTALE** | **18** | — | — |

### Step 2b — Geopolitical Sector Vector (nuovo)

Determinare l'impatto settoriale dell'evento geopolitico in corso. **Backtest**: 9 crisi geopolitiche maggiori 1990-2026 — difesa outperform consumer/tech del 18-24% nei 6 mesi successivi, energia +14% (fonte: Reuters Geopolitical Risk Index, Defense One).

| Tipo Evento | Settore Beneficiato | Settore Danneggiato |
|---|---|---|
| Guerra / conflitto armato | Difesa, Cybersecurity, Energia | Consumer discretionary, Tech hardware, Travel |
| Sanzioni commerciali | Domestic manufacturing | Import/export, semiconduttori, retail |
| Stretto bloccato (es. Hormuz) | Oil&Gas, Difesa, Shipping | Trasporti, Manufacturing |
| Guerra tecnologica (chip ban) | Semiconduttori domestici | Semiconduttori esposti a export |

**Regola**: Il punteggio di ogni dimensione viene modulato in base al settore dell'asset analizzato RISPETTO all'evento geopolitico corrente:
- Se l'asset opera in un settore **beneficiato** → +20 bonus a Fondamentali, +10 a Sentiment
- Se l'asset opera in un settore **danneggiato** → -20 malus a Fondamentali, -10 a Sentiment
- Se neutro → nessun effetto

### Step 3 — Adaptive Macro Verdict

Non un "passa/blocca" ma una **finestra operativa**:

| Punteggio | Finestra | Size Max | Regola Entry |
|---|---|---|---|
| **14-18** | **FULL** | 100% | Tutti i settori. Piena libertà. |
| **10-13** | **NORMAL** | 70% | Tutti i settori. Richiede 2 dimensioni ≥ 70. |
| **6-9** | **SELECTIVE** | 50% | **Solo settori che beneficiano del contesto macro**. Richiede: (1) asset score ≥ 70; (2) settore non danneggiato dall'evento geopolitico corrente. |
| **0-5** | **DEFENSIVE** | 30% (cash pesante) | Solo settori benedetti dal macro. Richiede score ≥ 80 e tutti i catalyst a favore. |

**Regola chiave**: In finestra SELECTIVE (6-9), la macro NON blocca automaticamente — ma obbliga un'analisi di **settore-relativo**. L'asset deve dimostrare che il suo settore è avvantaggiato, non solo indenne, dal contesto corrente.

Output obbligatorio in SELECTIVE/DEFENSIVE:
```
⚠️ Finestra [SELECTIVE/DEFENSIVE] — Score X/18
Settori favoriti: [lista]
Settori sfavoriti: [lista]
L'asset analizzato ([TICKER]) opera in un settore [favorito/neutro/sfavorevole].
```

---

## PHASE 0b — MULTI-TIMEFRAME TREND ALIGNMENT

**Esegui sempre**. Determina se i trend settimanale, daily e 4h sono allineati. Indipendentemente dalla finestra macro, l'allineamento multi-timeframe modula i punteggi delle fasi successive.

### Trend Classification

Usa i dati raccolti in Phase 1 (già fetchati) + EMA visual su 3 timeframe:

| Timeframe | Cosa guardare | Long condition | Short condition |
|---|---|---|---|
| **Weekly** | Prezzo vs EMA20, EMA50; pattern HH/HL o LH/LL | P > EMA20, HH/HL | P < EMA20, LH/LL |
| **Daily** | Prezzo vs EMA20, EMA50; struttura a onde | P > EMA20, massimi crescenti | P < EMA20, massimi decrescenti |
| **4h** | Trendline, S/R locali, momentum | Pullback in uptrend locale | Rimbalzo in downtrend locale |

### Alignment Score

| Condizione | Punti |
|---|---|
| Tutti e 3 allineati long | +30 alla dimensione Wyckoff |
| Tutti e 3 allineati short | +30 alla dimensione Wyckoff (lato bear) |
| Weekly + Daily allineati, 4h no | +15 alla dimensione Wyckoff, attendere entry |
| Weekly solo (daily/4h contrari) | -10 alla dimensione Wyckoff, trend usurato |
| Nessun allineamento | 0 — skip trade |

---

## 5-Phase Analysis Workflow

### Phase 1 — Data Collection

Load `market-data-fetch` templates. Collect:

**For all assets:**
- 1 year daily OHLCV + 3 months hourly
- Current price vs MA50, MA200
- RSI(14) on daily
- RSI(14) on weekly
- Average volume (20d) vs volume today
- CVD (Cumulative Volume Delta) — if available via exchange API, else skip
- Funding rate (for crypto perp futures)
- Liquidations data (if available via Coinglass)
- Open Interest trend (7d slope)

**For stocks:**
- P/E ratio, EPS, Market Cap
- Institutional holders % (from `Ticker.info`)
- Earnings date (next)
- Short interest % float
- Put/Call ratio (if available for the specific stock)

**For crypto (CoinGecko preferred):**
- Market cap, circulating/total/max supply
- 24h volume vs market cap ratio
- Active addresses (trend direction: 30d change %)
- Top exchange reserves (if available) — inflow or outflow trend
- Team & whitepaper availability
- Staking ratio

### Phase 2 — Technical Structure (Wyckoff + Volume Profile)

Load `wyckoff-2-0` and `volume-profile`.

**Step A — Identify Wyckoff Phase**

Examine the 1-year range:
- Is price in a clear range (40-60% of yearly range)? → Potential Accumulation or Distribution
- Is price making HH/HL? → Markup phase (Phase D-E)
- Is price making LH/LL? → Markdown phase (Phase D-E)
- Look for Springs (break below range → reversal) or Upthrusts (break above range → reversal)

**Integrate Phase 0b alignment score** into Wyckoff score as bonus/malus.

Rules:
- **Phase A** (Trend Stop): Selling/Buying climax with extreme volume → score +0 (transitional)
- **Phase B** (Cause Building): Tight range, decreasing volume for accumulation, high volume for distribution → score +40 if accumulation signs, -40 if distribution signs
- **Phase C** (Shakeout): Spring or Upthrust with clear reversal → score +80 if Spring, -80 if Upthrust
- **Phase D** (Initial Effect): SOS/SOW bar with wide range + high volume → score +60 if SOS, -60 if SOW
- **Phase E** (Full Effect): Trend established, pullbacks to structure → score +100 if in direction of accumulation, -100 if in direction of distribution

Score mapping:
| Condition | Score |
|-----------|-------|
| Accumulation (Phases B-C-D) | 80-100 |
| Markup (Phase E after accumulation) | 70-100 |
| Neutral range (no clear phase) | 40-60 |
| Distribution (Phases B-C-D) | 0-30 |
| Markdown (Phase E after distribution) | 0-20 |

**Step B — Classify Volume Profile**

Using 3-month profile data:
- **D-Profile** (bell-shaped): Balanced, accumulation vibes → score +30
- **P-Profile** (high tail, low body): Bullish, aggressive buyers → score +50
- **b-Profile** (low tail, high body): Bearish, aggressive sellers → score -30
- **Thin Profile**: Trending → score +20 if up, -20 if down

Check VPOC location relative to current price:
- Price above VPOC = bullish bias → +20
- Price below VPOC = bearish bias → -20
- Price at VPOC = neutral → 0

Value Area (VA):
- Price inside VA = fair, no edge → 0
- Price above VAH = extended, mean reversion risk → -15
- Price below VAL = extended, mean reversion risk → -15

Check VAL break vs profile shape:
- New low below VAL on b-profile = continuation → -20
- New low below VAL on P-profile = potential absorption → +10

### Phase 3 — Volume & Price Action

Load `volume-price-analysis`, `price-action-volman`, and `trades-about-to-happen`.

**Step A — VPA on Last 10 Daily Bars**

For each of the last 10 candles, classify:
- **Validation**: Volume confirms price (up+high vol = bullish; down+high vol = bearish) → score +5 per bullish validation, -5 per bearish
- **Anomaly**: Volume and price disagree → score -10 if anomaly in trend direction, +10 if anomaly against trend (potential reversal)

Count net: `vpa_score = (bullish_validations - bearish_validations) * 5 + (reversal_anomalies * 10)`

**Step B — Effort vs Result (Last 5 bars)**

Compare the price range (result) of each bar to the volume (effort):
- Wide range + high volume = healthy → +5 per bar
- Narrow range + high volume = absorption/anomaly → -5 per bar
- Wide range + low volume = trap/fake → -10 per bar
- Narrow range + low volume = low interest → 0

Sum for `er_score` (-25 to +25).

**Step C — Price Action Structure (Volman)**

Look for:
- **Buildup** at a key S/R level: tight cluster of alternating bars → +30 if present
- **False/Tease/Proper Break**: classify last breakout attempt → proper = +40, tease = +10, false = -20
- **Double Pressure** zone: converging buyers and shorts covering → +30
- **25ema slope**: rising = +15, falling = -15

Score: `volman_score` (range -35 to +100).

**Step D — Weis Patterns (trades-about-to-happen)**

Look for:
- **Spring** (false breakdown below support) → +60 on daily timeframe
- **Upthrust** (false breakout above resistance) → -60
- **Cluster** near S/R (absorption) → +30
- **Displacement without follow-through** → +20 (exhaustion against trend)
- **Shortening of Thrust (SOT)** after 3+ pushes in trend → +40 if in trend direction, -40 if against
- **Confluence of lines** (multiple trend/S/R lines at same price) → +20

Score: `weis_score` (range -80 to +120).

**Step E — Rally Velocity & Exhaustion Check** (nuovo — basato su Jegadeesh 1990: rally >20% in 15gg hanno >70% probabilità di pullback nel mese successivo)

Analizzare la velocità del movimento recente per identificare estensioni insostenibili:

| Condizione | Impatto |
|---|---|
| Rally > 20% in < 15 sedute | **-20** alla PA (mean reversion risk) |
| Rally > 30% in < 20 sedute | **-35** (exhaustion gap, >70% probabilità retrace) |
| Rally > 50% in < 30 sedute | **-50** (vertical rally = unsustainable) |
| 5+ candele consecutive verdi su daily | **-10** (buying climax) |
| Volume in calo durante il rally (ultimi 3gg < media 20gg) | **-15** (loss of momentum) |
| Gap up non riempito da >10gg | **-10** (gap fill magnet) |

**Bonus** (movimento sano):
- Rally graduale (< 10% in 20gg) su volume crescente → **+20** (sostenibile)
- Pullback within trend su volume calante → **+15** (consolidamento sano)
- Range trading 20+ gg con contrazione volume → **+10** (accumulazione silenziosa)

**Esaurimento opzioni**: Se Rally Velocity score è -35 o peggiore:
- Bloccare nuove raccomandazioni Long con opzioni
- Output: "⚠️ RALLY VERTICALE — Il titolo ha già prezzato le buone notizie. Non entrare in opzioni in estensione. Attendi pullback o consolidamento."

`velocity_score` = somma di tutte le condizioni sopra (range -50 a +20).

**Phase 3 aggregate**: `pa_score = (vpa_score + er_score + volman_score + weis_score + velocity_score) / 5`, clipped to 0-100, then remapped: >60 = bullish, 40-60 = neutral, <40 = bearish.

### Phase 4 — Sentiment & Positioning (Enhanced)

Load `trading-against-the-crowd`. Go beyond simple sentiment — also check positioning data.

**Step A — Sentiment Extremes**

**If Put/Call ratio available:**
- Equity-only P/C ratio extreme (>0.70 = bearish extreme = contrarian bullish; <0.40 = bullish extreme = contrarian bearish) → score +50 at extreme, -20 at consensus
- Apply Squeeze Play I logic: EMA5-21 of P/C ratio + price trigger (close > prev high / close < prev low) → +40 for signal, 0 otherwise

**If VIX available:**
- VIX > 30 = fear extreme → contrarian bullish +30
- VIX < 12 = complacency → contrarian bearish -20

**Fear & Greed Index (crypto):**
- 0-15: Extreme Fear (capitulation) → +40 contrarian bullish
- 16-24: Fear → +20 contrarian bullish
- 25-45: Neutral → 0
- 46-75: Greed → -20 contrarian bearish
- 76-100: Extreme Greed → -40 contrarian bearish

**Step B — Positioning Data**

Check these when available via websearch or Coinglass:

**Funding Rate (crypto perp):**
- Negativo da >12h (short pagano long) → +20 (long positioning cheap, shorts crowded)
- Positivo da >12h (long pagano short) → -20 (longs crowded)
- Estremamente negativo (< -0.1%) → +40 (capitulation short squeeze setup)
- Stabile vicino a zero → 0

**Open Interest trend (7d):**
- OI in calo + prezzo in calo = deleveraging → +10 (pulizia)
- OI in salita + prezzo piatto/calo = short building → +30 (potenziale squeeze)
- OI in salita + prezzo in salita = trend sano → +20
- OI in calo + prezzo in salita = distribuzione → -30

**Liquidations data:**
- Grandi short liquidations recenti → -10 (già squeezati, fuel esaurito)
- Grandi long liquidations recenti → +30 (capitolazione, fuel per rimbalzo)
- Cluster di liquidazioni sopra il prezzo → resistenza
- Cluster di liquidazioni sotto il prezzo → magnet (liq hunting)

**Exchange Flow:**
- Net outflow da exchange (whale accumulation) → +30
- Net inflow a exchange (whale distribution) → -30

**Short Interest (stocks):**
- > 20% float → +40 (squeeze potential)
- 10-20% → +20
- < 5% → -10 (no squeeze fuel)

**Step C — BTC Dominance (only for crypto analysis)**

- BTC.D in calo → altcoin possono performare → +10
- BTC.D in salita > 62% → altcoin sotto pressione → -20
- BTC.D stabile → 0

**Step D — Earnings Quality Trend** (nuovo — per stocks)

Se disponibili 4+ trimestri di earnings surprise:

| Condizione | Impatto |
|---|---|
| Surprise % in calo per 2+ trim consecutivi | -20 (momentum si esaurisce) |
| Surprise negativo nell'ultimo trimestre | -30 (trend invertito) |
| Guidance rivista al ribasso nell'ultimo quarter | -40 (management vede problemi) |
| Surprise % in crescita per 2+ trim consecutivi | +20 (execution in accelerazione) |
| Guidance alzata + surprise positivo | +25 |

**Phase 4 Aggregate**:
```
sentiment_sub_scores = [put_call, vix, fear_greed, funding, oi, liquidations, exchange_flow, short_interest, earnings_quality_trend]
available = [s for s in sentiment_sub_scores if s is not None]
sentiment_score = sum(available) / len(available) * 10 if available else 45
```
Clipped to 0-100.

### Phase 5 — Crypto Layer (only if crypto)

Load `crypto-technical-analysis` and `crypto-crash-course`.

**Step A — On-Chain Metrics (crypto-technical-analysis)**
- Active addresses rising 30d → adoption +30
- Active addresses falling 30d → waning interest -15
- Exchange reserves falling (accumulation) → +30
- Exchange reserves rising (distribution) → -30
- Staking ratio > 30% → committed holders +20
- Circulation vs market cap ratio low (< 20%) → diamond hands +20

**Step B — Hype Analysis**
- Social momentum (trending on CoinGecko, Twitter volume): high + no fundamental reason = hype → -30
- Sustained organic interest over 90d -> healthy +20

**Step C — Fundamental Project Health (crypto-crash-course)**
- Public team with verifiable track record → +20
- Clear whitepaper with working product → +20
- Deflationary tokenomics (burning, halving) → +20
- Utility (not just store of value) → +15
- Strong community (Discord/Telegram active, GitHub commits) → +15

**Step D — Developer Activity**
- GitHub commits trend (30d): rising = +15, stable = +5, falling = -10
- Protocol revenue (if applicable): growing = +20

Score: `crypto_score = sum of all above`, clipped to 0-100.

### Phase 5b — Fondamentali (for stocks)

If stock (not crypto):

**Fundamentals check (market-data-fetch):**

#### Step A — Earnings Quality Modifier (nuovo, basato su Sloan 1996)

Non usare P/E come punteggio grezzo. Calcolare P/E base score, poi applicare Earnings Quality Modifier.

**P/E Base Score**:
- P/E < 12 = +30; P/E < 20 = +20; P/E < 30 = +10; P/E > 40 = -20

**Earnings Quality Modifier** (backtest: Sloan 1996, Richardson et al 2005 — earnings quality predice returns p<0.01):

| Earnings Surprise Trend | Modifier |
|---|---|
| 3+ trim consecutivi di sorpresa in crescita | +20 |
| 2+ trim stabili positivi | +10 |
| Misto (alterna positivo/negativo) | 0 |
| 2+ trim consecutivi di sorpresa in calo | **-20** |
| Guidance negativa + surprise in calo | **-30** |

**P/E effective score** = P/E base + Earnings Quality Modifier (clipped 0-50)

#### Step B — Value Trap Check (nuovo)

Se il P/E è basso (< 15), verificare se è "cheap for a reason":

| Condizione | Penalità |
|---|---|
| P/E < 15 **MA** EPS in calo YoY | -20 |
| P/E < 15 **MA** revenue growth < 2% | -15 |
| P/E < 15 **MA** profit margins in calo 2+ trim consecutivi | -20 |
| P/E basso vs settore **MA** Debt/Equity > 2.0 | -15 |

Se 2+ condizioni sono vere: `fundamental_score` cap a 40. Aggiungere nota: ⚠️ Value Trap Alert.

#### Step C — Standard Fundamentals (invariato)

- Revenue growth YoY positive → +20
- Institutional ownership > 50% → +15
- Positive earnings surprise last 4 quarters → +25
- Next earnings in > 4 weeks (no event risk) → +10
- Insider buying (recent filings) → +20
- PEG ratio < 1.5 → +20
- Debt/Equity < 1.0 → +15

#### Step D — Price vs Consensus Divergence (nuovo)

| Condizione | Penalità/Bonus |
|---|---|
| Prezzo > 110% del mean analyst target | -25 ("ahead of fundamentals") |
| Prezzo > 80% del high analyst target | -15 ("priced for perfection") |
| Prezzo < mean analyst target | +10 ("room to run") |
| Prezzo < 80% del mean target | +20 ("oversold vs fair value") |

Se current price > mean target: non considerare il target mean come upside potenziale. Aggiungere avviso: "Il mercato sconta più degli analisti. Rischio mean reversion."

**Score: `fundamental_score` = P/E effective + Value Trap adj + Standard adj + Consensus adj, clipped 0-100.**

---

### Phase 5c — Competitive Positioning (Nuova Dimensione, peso 10%)

Analizza la posizione competitiva del business indipendentemente dal setup tecnico o di prezzo. **Backtest**: Porter (1980) — vantaggio competitivo sostenibile è il miglior predittore di outperformance long-term; Wiggins & Ruefli (2002) — persistenza della performance è correlata a moat e pricing power.

**Scoring** (0-100):

| Sub-dimensione | Dettaglio | Punteggio |
|---|---|---|
| **Market Share Trend** | In crescita ultimi 2 anni | +30 |
| | Stabile | 0 |
| | In calo | **-30** |
| **Competitive Moat** | Brevetti / tecnologia proprietaria / contratti gov esclusivi | +20 |
| | Barriere all'entrata moderate (regolamentazione, capital intensity) | +10 |
| | Commodity / facile sostituibile | **-20** |
| **Pricing Power** | Margini in espansione, costi trasferiti a clienti | +20 |
| | Margini stabili | 0 |
| | Margini sotto pressione (input costs non trasferibili) | **-20** |
| **Diversificazione** | Multi-settore / multi-prodotto (no single point of failure) | +15 |
| | Concentrato su 1-2 linee di business | 0 |
| | Dipendente da 1 cliente/mercato | **-15** |
| **Barriere all'uscita concorrenti** | Alto (regolamentazione, brevetti, scala) | +15 |
| | Basso (facile entrata nuovi competitor) | -15 |

**Calcolo**: `competitive_score = sum of all available sub-scores`, clipped 0-100.

**Output obbligatorio** nel verdetto:
```
- **Competitive Positioning**: [market share trend], [moat type], [pricing power] → [+/-X punti]
```

### Final Score Formula

```python
weights = {
    "wyckoff": 0.15,   # 0.10 for crypto (ridotto per Competitive)
    "volprof": 0.20,   # 0.15 for crypto
    "pa": 0.20,        # 0.15 for crypto
    "sentiment": 0.15, # 0.10 for crypto
    "fundamentals": 0.20 if not crypto else 0.10,
    "competitive": 0.10 if not crypto else 0.05,  # nuova dimensione
    "crypto": 0.0 if not crypto else 0.35,
}
# Ensure weights sum to 1.0

analysis_score = (
    wyckoff_score * weights["wyckoff"] +
    volprof_score * weights["volprof"] +
    pa_score * weights["pa"] +
    sentiment_score * weights["sentiment"] +
    fundamental_score * weights["fundamentals"] +
    competitive_score * weights["competitive"] +
    crypto_score * weights["crypto"]
)
```

### Final Composite Score with Adaptive Macro Penalty

```python
# Adaptive Macro Matrix: il peso della macro dipende dalla finestra
# FULL: 10% | NORMAL: 20% | SELECTIVE: 30% | DEFENSIVE: 40%
macro_weight_map = {"full": 0.10, "normal": 0.20, "selective": 0.30, "defensive": 0.40}
macro_weight = macro_weight_map.get(macro_window, 0.20)  # default normal

composite_score = (
    macro_score / 18 * 100 * macro_weight +
    analysis_score * (1 - macro_weight)
)
# composite_score = 0-100
```

### Verdict Thresholds

| Composite Score | Verdetto | Azione |
|---------------|----------|--------|
| 70-100 | **Long-Term Investment** | Entry con piano DCA o singolo, PT a 6-12 mesi |
| 50-69 | **Short-Term Speculation (Bullish)** | Entry tattico, PT a 1-4 settimane, stop stretto |
| 30-49 | **Short-Term Speculation (Bearish / Neutrale)** | Solo se setup perfetto, altrimenti wait |
| 0-29 | **Avoid / Wait** | Nessuna azione, rivisita tra 1 mese |

### Risk Sizing Matrix

Calcola la dimensione della posizione in base al composite score e alla finestra macro (Adaptive Macro Matrix):

| Finestra Macro | Analysis Score | Max Position | Stop Loss | Leverage Max |
|---|---|---|---|---|
| FULL | ≥ 80 | 10% portfolio | 4% | 2x |
| FULL | 60-79 | 7% portfolio | 5% | 1.5x |
| FULL | 40-59 | 4% portfolio | 7% | 1x |
| FULL | < 40 | 1% portfolio | 10% | 1x |
| NORMAL | ≥ 75 | 5% portfolio | 5% | 1x |
| NORMAL | 50-74 | 3% portfolio | 7% | 1x |
| NORMAL | < 50 | 0 (no trade) | — | — |
| SELECTIVE | ≥ 80 e settore favorito | 3% portfolio | 8% | 1x |
| SELECTIVE | ≥ 70 e settore favorito | 2% portfolio | 10% | 1x |
| SELECTIVE | < 70 o settore sfavorito | **0 (no trade)** | — | — |
| DEFENSIVE | ≥ 80 e settore benedetto | 2% portfolio | 12% | 1x |
| DEFENSIVE | Altro | **0 (no trade)** | — | — |

**Regola aggiuntiva**: Mai più del 25% del portfolio totale in un singolo settore (crypto/stock).

**Regola concentrazione temporale**: Se l'utente ha già 2+ posizioni in opzioni con scadenza entro 60gg l'una dall'altra, riduci size del 30%.

---

## Exit & Invalidation Rules

Ogni raccomandazione include queste regole di uscita:

### Technical Invalidation

| Scenario | Azione |
|---|---|
| Prezzo perde il minimo della candela di entrata (4h close sotto) | Taglia 50% posizione |
| Prezzo perde il supporto strutturale successivo (daily close) | Esci tutto |
| RSI daily torna sopra 70 (se long partito da ipervenduto) | Prendi profitto 50% |
| RSI daily scende sotto 30 (se short partito da ipercomprato) | Prendi profitto 50% |
| EMA20 daily incrocia EMA50 daily al ribasso (da long) | Esci tutto |

### Sentiment / Regime Change

| Scenario | Azione |
|---|---|
| Fear & Greed scende sotto 10 (panico estremo) da long in loss | HOLD — non uscire in capitolazione |
| Fear & Greed scende sotto 10 da long in profit | Prendi 50% |
| VIX > 35 durante posizione long | Riduci 50% |
| FOMC/CPI/NFP entro 48h | Riduci 50% o chiudi prima dell'evento |

### Time-Based

| Condizione | Azione |
|---|---|
| Position in loss da >10 giorni di calendario senza segnali di inversione | Taglia a zero |
| Position in profit da >14 giorni MA trend si sta esaurendo (SOT, divergenza RSI) | Prendi 100% |
| Short-term trade aperto da >21 giorni (oltre l'orizzonte) | Chiudi e rivaluta |

---

## Output Template

```
## 📊 Adaptive Macro Matrix: [FULL / NORMAL / SELECTIVE / DEFENSIVE]
Score: X/18

### Macro Detail
- [✅/❌] Fed Policy: [tasso X%, FOMC passato/tra Xgg]
- [✅/❌] DXY Trend: [X.XX, tendenza]
- [✅/❌] VIX: [X.XX]
- [✅/❌] Liquidità: [QT attivo/pausa]
- [✅/❌] Geopolitica: [evento in corso / nessuno] → Impatto settoriale: [beneficiato/danneggiato/neutro per questo asset]
- [✅/❌] 10Y Real Yield: [X.XX%]
- [✅/❌] Risk Sentiment: [F&G X]
- [✅/❌] Eventi Macro: [prossimo evento tra Xgg]
- [✅/❌] BTC Dominance: [X.XX%, trend] (solo crypto)

⚠️ Finestra [SELECTIVE/DEFENSIVE]:
Settori favoriti: [lista]
Settori sfavoriti: [lista]
L'asset opera in un settore [favorito/neutro/sfavorevole].

### MULTI-TIMEFRAME: [ALLINEATO / PARZIALE / NON ALLINEATO]
- Weekly: [trend]
- Daily: [trend]
- 4h: [trend]

---

## 📊 Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Analysis Score: X% | Composite Score: X% | Adaptive Macro x Analysis

### Perché
- **Wyckoff Phase** ([fase A-E]): [breve spiegazione] → [+/-X punti]
- **Volume Profile** ([shape D/P/b/Thin]): [VA, VPOC, posizione prezzo] → [+/-X punti]
- **Price Action** ([setup]): [VPA, Volman, Weis pattern] → [+/-X punti]
- **Sentiment & Positioning** ([segnale]): [P/C, VIX, funding, OI, liquidations] → [+/-X punti]
- **Fondamentali** ([metriche]): [P/E, EPS trend, margins] → [+/-X punti]
- **Competitive Positioning** ([vantaggio/svantaggio]): [market share, moat, pricing power] → [+/-X punti]
  [Se crypto] **Crypto Layer** ([on-chain, hype, progetto]): → [+/-X punti]

### Raccomandazione
- **Direzione**: Long / Short / Neutrale
- **Entry**: €XX.XX – €XX.XX
- **Stop Loss**: €XX.XX (X%)
- **Target 1**: €XX.XX (30% posizione, X:R)
- **Target 2**: €XX.XX (70% posizione, X:R)
- **Orizzonte**: 1-4 settimane / 3-12 mesi
- **Sizing**: X% del portafoglio (basato su Risk Sizing Matrix)

### Exit & Invalidation
- **Technical**: [invalidation levels]
- **Event-based**: [cosa fare prima di FOMC/CPI/etc.]
- **Time-based**: [quando tagliare se non funziona]

### Rischio
- Livello: [Basso / Medio / Alto]
- Fattori chiave: [earnings, news, breakout/fallimento setup, vol/liq]
```

---

## Execution Order

1. Determine `is_crypto` from asset name or user context
2. **RUN PHASE 0 — ADAPTIVE MACRO MATRIX**
   - Fetch macro data via `websearch`
   - Compute Macro score (0-18)
   - Determine macro window: FULL / NORMAL / SELECTIVE / DEFENSIVE
   - If SELECTIVE or DEFENSIVE: run Geopolitical Sector Vector
   - Output window + settori favoriti/sfavoriti
3. Run **Phase 0b — Multi-Timeframe Alignment**
4. If macro window = DEFENSIVE AND asset settore NON benedetto: output "NO TRADE — DEFENSIVE window, settore sfavorito", STOP
5. Otherwise: proceed with Phase 1-5
6. Load all 9 skill frameworks via `load_skills_knowledge(["wyckoff-2-0", ...])`
7. Fetch data using `market-data-fetch` templates (Phase 1)
8. Run Phases 2-5 sequentially, computing each dimension score (include new Competitive Positioning dimension)
9. Apply Adaptive Macro penalty + weights, compute composite score, map to verdict
10. Apply Risk Sizing Matrix based on composite score + macro window
11. Output formatted verdict with Adaptive Macro detail + risk sizing + exit rules
12. Always include invalidation criteria specific to the asset
13. If composite score ≥ 70 **e** la richiesta include una scadenza opzioni → passa a `options-strategy-suggestions`

---

## Chained Execution (from market-accumulation-scanner)

When invoked by `market-accumulation-scanner` (Auto-Chain Mode), still run
Phase 0 Adaptive Macro Matrix first. If DEFENSIVE window AND asset settore NON benedetto, return NO TRADE.

When invoked by `market-accumulation-scanner` (Auto-Chain Mode), the scanner
has already computed the 5-dimension score. In this mode:

| Dimensione | Source | Come usarlo |
|-----------|--------|------------|
| Wyckoff | Scanner score + detail | Converti in punteggio (0-100) per questa fase. **Aggiungi bonus/malus Phase 0b.** |
| Volume Profile | Scanner score + detail | Già calcolato. Usalo direttamente. |
| Price Action | Scanner score + detail | Già calcolato. **Applica Rally Velocity Check.** |
| Sentiment & Positioning | Scanner score + **8 sub-scores** | **Applica Earnings Surprise Degradation.** |
| Fondamentali | Scanner score + detail | **Applica Value Trap, Earnings Quality Modifier, Price vs Consensus.** |
| Competitive Positioning | Nuovo — calcola ex-novo | Market share, moat, pricing power da websearch. |

**Procedura in Chained Mode**:

1. **PHASE 0 FIRST** — Adaptive Macro Matrix indipendente dallo scanner
2. Verifica macro window + Geopolitical Sector Vector (settore favorito/sfavorevole)
3. Se DEFENSIVE + settore sfavorito → NO TRADE
4. Phase 0b — Multi-timeframe alignment
5. Usa i dati dello scanner come base
6. **Applica i nuovi modificatori**: Value Trap, Earnings Quality, Rally Velocity, Price vs Consensus, Competitive Positioning
7. **Non ripetere** la raccolta dati (Phase 1) — usa i dati dello scanner
8. Esegui Phases 2-5, arricchendo ogni dimensione con i dettagli dello scanner
9. Per la dimensione Sentiment & Positioning, usa gli 8 sub-scores + earnings surprise degradation
10. Per Fondamentali, applica Earnings Quality Modifier + Value Trap Check + Price vs Consensus
11. Verifica con dati freschi via `websearch` o `webfetch` solo se qualche dimensione è poco chiara
12. Produci output con formato ridotto (senza ripetere le tabelle di scoring già mostrate dallo scanner)
13. Se composite score ≥ 70 **e** la richiesta include una scadenza opzioni → passa a `options-strategy-suggestions`, che applicherà il Momentum Stage Filter

**Output Chained Mode** (ridotto, senza ridondanza):

```
## 📊 Adaptive Macro: [FULL / NORMAL / SELECTIVE / DEFENSIVE]
Score: X/18
Settore asset: [favorito/neutro/sfavorevole] vs evento geopolitico corrente

### MULTI-TIMEFRAME: [ALLINEATO / PARZIALE / NON ALLINEATO]

## 📊 Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Composite Score: X% (Macro X/18 + Analysis X%)

### Perché
Basato sui dati scanner + modificatori:
- **Wyckoff** ([fase]): scanner score XX → [+/-X punti]
- **Volume Profile** ([shape]): scanner score XX → [+/-X punti]
- **Price Action** ([setup]): scanner score XX + Rally Velocity check → [+/-X punti]
- **Sentiment & Positioning**: scanner 8-dim + Earnings Surprise Trend → [+/-X punti]
- **Fondamentali**: scanner score XX + Value Trap + Earnings Quality Modifier → [+/-X punti]
- **Competitive Positioning**: [market share, moat, pricing power] → [+/-X punti]

### Raccomandazione
- **Direzione**: Long / Short
- **Entry**: €XX.XX – €XX.XX | **Stop**: €XX.XX (X%)
- **Target**: €XX.XX | **Orizzonte**: X mesi
- **Sizing**: X% del portafoglio (Risk Sizing Matrix — finestra [window])
- **Exit**: [invalidation levels]

### Rischio
- Livello: [Basso / Medio / Alto]
- Fattori chiave: [specifici]
```

Non includere il dettaglio grezzo dello scanner (già mostrato prima). Produci solo
il valore aggiunto delle 9 skill framework + Adaptive Macro Matrix.

---

## Anti-Patterns

- **Don't** produrre un verdetto se i dati sono insufficienti (score = 0 o N/A in 3+ dimensioni). Invece: "Dati insufficienti — impossibile produrre verdetto."
- **Don't** hedge the verdict. If score is 72, say LONG-TERM INVEST, not "potrebbe essere long ma anche short."
- **Don't** mix stock and crypto weights. Use the correct weight table based on asset type.
- **Don't** skip any phase even if data is partial. Assign 0 to unavailable dimensions and note it.
- **Don't** saltare PHASE 0 — mai consigliare entry senza Adaptive Macro Matrix.
- **Don't** ignorare il Geopolitical Sector Vector in finestra SELECTIVE/DEFENSIVE. Deve essere calcolato e pesato.
- **Don't** usare P/E basso come segnale univoco di valore. Applicare sempre Earnings Quality Modifier + Value Trap Check prima di assegnare punteggio Fundamentali.
- **Don't** raccomandare entry in titoli con rally verticale >20% in 15gg senza applicare Rally Velocity Check.
- **Don't** exceed Risk Sizing Matrix limits. Mai più di quanto indicato dalla matrice.
- **Don't** ignorare la concentrazione settoriale o temporale. Applicare le regole di riduzione size.
