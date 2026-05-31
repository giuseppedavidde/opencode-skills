---
name: stock-crypto-analysis
description: >
  Unified market analysis that produces a single verdict (Long-Term Investment,
  Short-Term Speculation, or Avoid/Wait) by integrating 9 source skills:
  Wyckoff 2.0, Volume Profile, VPA, Price Action Volman, Trades About To Happen,
  Trading Against The Crowd, Market Data Fetch, Crypto Technical Analysis,
  and Crypto Crash Course. Use when the user wants to decide what to do with
  a stock or crypto asset, or when they ask 'cosa farne' of any financial asset.
allowed-tools:
  - read
  - grep
  - websearch
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

# Stock & Crypto Unified Analysis

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
| 1 | Wyckoff Phase | 25% | 15% | wyckoff-2-0 |
| 2 | Volume Profile | 20% | 15% | volume-profile, volume-price-analysis |
| 3 | Price Action | 20% | 15% | price-action-volman, trades-about-to-happen |
| 4 | Sentiment | 15% | 10% | trading-against-the-crowd |
| 5 | Fondamentali | 20% | 10% | market-data-fetch |
| 6 | Crypto Layer | — | 35% | crypto-technical-analysis, crypto-crash-course |

When `is_crypto=True` use Crypto weights; otherwise use Stock weights.

## 5-Phase Analysis Workflow

### Phase 1 — Data Collection

Load `market-data-fetch` templates. Collect:

**For all assets:**
- 1 year daily OHLCV + 3 months hourly
- Current price vs MA50, MA200
- RSI(14) on daily
- Average volume (20d) vs volume today

**For stocks:**
- P/E ratio, EPS, Market Cap
- Institutional holders % (from `Ticker.info`)
- Earnings date (next)

**For crypto (CoinGecko preferred):**
- Market cap, circulating/total/max supply
- 24h volume vs market cap ratio
- Active addresses (trend direction)
- Top exchange reserves (if available)
- Team & whitepaper availability

### Phase 2 — Technical Structure (Wyckoff + Volume Profile)

Load `wyckoff-2-0` and `volume-profile`.

**Step A — Identify Wyckoff Phase**

Examine the 1-year range:
- Is price in a clear range (40-60% of yearly range)? → Potential Accumulation or Distribution
- Is price making HH/HL? → Markup phase (Phase D-E)
- Is price making LH/LL? → Markdown phase (Phase D-E)
- Look for Springs (break below range → reversal) or Upthrusts (break above range → reversal)

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

**Phase 3 aggregate**: `pa_score = (vpa_score + er_score + volman_score + weis_score) / 4`, clipped to 0-100, then remapped: >60 = bullish, 40-60 = neutral, <40 = bearish.

### Phase 4 — Sentiment (trading-against-the-crowd)

Load `trading-against-the-crowd`. Check available data:

**If Put/Call ratio available:**
- Equity-only P/C ratio extreme (>0.70 = bearish extreme = contrarian bullish; <0.40 = bullish extreme = contrarian bearish) → score +50 at extreme, -20 at consensus
- Apply Squeeze Play I logic: EMA5-21 of P/C ratio + price trigger (close > prev high / close < prev low) → +40 for signal, 0 otherwise

**If VIX available:**
- VIX > 30 = fear extreme → contrarian bullish +30
- VIX < 12 = complacency → contrarian bearish -20

**General sentiment:**
- Multi-stream convergence (P/C + VIX + short interest all at extreme) → +50
- Divergence between streams → 0
- No data available → 0 (neutral)

Score: `sentiment_score` (range -40 to +80), clipped to 0-100.

### Phase 5 — Crypto Layer (only if crypto)

Load `crypto-technical-analysis` and `crypto-crash-course`.

**Step A — On-Chain Metrics (crypto-technical-analysis)**
- Active addresses rising = adoption → +30
- Exchange reserves falling = accumulation → +30
- Staking ratio > 30% = committed holders → +20
- Circulation vs market cap ratio: low = diamond hands → +20

**Step B — Hype Analysis**
- Social momentum (trending on CoinGecko, Twitter volume): high + no fundamental reason = hype → -30
- Sustained organic interest = healthy → +20

**Step C — Fundamental Project Health (crypto-crash-course)**
- Public team with verifiable track record → +20
- Clear whitepaper with working product → +20
- Deflationary tokenomics (burning, halving) → +20
- Utility (not just store of value) → +15
- Strong community (Discord/Telegram active, GitHub commits) → +15

Score: `crypto_score = sum of all above`, clipped to 0-100.

### Phase 5b — Fondamentali (for stocks)

If stock (not crypto):

**Fundamentals check (market-data-fetch):**
- P/E < 25 = +20; P/E < 15 = +40; P/E > 40 = -20
- Revenue growth YoY positive → +20
- Institutional ownership > 50% → +15
- Positive earnings surprise last 4 quarters → +25
- Next earnings in > 4 weeks (no event risk) → +10
- Insider buying (recent filings) → +20

Score: `fundamental_score` (0-100).

## Scoring Aggregation

### Final Score Formula

```python
weights = {
    "wyckoff": 0.25,   # 0.15 for crypto
    "volprof": 0.20,   # 0.15 for crypto
    "pa": 0.20,        # 0.15 for crypto
    "sentiment": 0.15, # 0.10 for crypto
    "fundamentals": 0.20 if not crypto else 0.10,
    "crypto": 0.0 if not crypto else 0.35,
}
# Ensure weights sum to 1.0

final_score = (
    wyckoff_score * weights["wyckoff"] +
    volprof_score * weights["volprof"] +
    pa_score * weights["pa"] +
    sentiment_score * weights["sentiment"] +
    fundamental_score * weights["fundamentals"] +
    crypto_score * weights["crypto"]
)
```

### Verdict Thresholds

| Final Score | Verdetto | Azione |
|------------|----------|--------|
| 70-100 | **Long-Term Investment** | Entry con piano DCA o singolo, PT a 6-12 mesi |
| 50-69 | **Short-Term Speculation (Bullish)** | Entry tattico, PT a 1-4 settimane, stop stretto |
| 30-49 | **Short-Term Speculation (Bearish / Neutrale)** | Solo se setup perfetto, altrimenti wait |
| 0-29 | **Avoid / Wait** | Nessuna azione, rivisita tra 1 mese |

## Output Template

```
## 📊 Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Score: XX% (pesato su 6 dimensioni)

### Perché
- **Wyckoff Phase** ([fase A-E]): [breve spiegazione] → [+/-X punti]
- **Volume Profile** ([shape D/P/b/Thin]): [VA, VPOC, posizione prezzo] → [+/-X punti]
- **Price Action** ([setup]): [VPA, Volman, Weis pattern] → [+/-X punti]
- **Sentiment** ([segnale]): [P/C, VIX, estremo] → [+/-X punti]
- **Fondamentali** ([metriche]): [P/E, crescita, holder] → [+/-X punti]
  [Se crypto] **Crypto Layer** ([on-chain, hype, progetto]): → [+/-X punti]

### Raccomandazione
- **Direzione**: Long / Short / Neutrale
- **Entry**: $XX.XX – $XX.XX
- **Stop Loss**: $XX.XX
- **Target 1**: $XX.XX (30% posizione)
- **Target 2**: $XX.XX (70% posizione)
- **Orizzonte**: 1-4 settimane / 3-12 mesi
- **Gestione**: DCA / Singolo ingresso / Scaling

### Rischio
- Livello: [Basso / Medio / Alto]
- Fattori chiave: [earnings, news, breakout/fallimento setup, vol/liq]
```

## Execution Order

1. Determine `is_crypto` from asset name or user context
2. Load all 9 skill frameworks via `load_skills_knowledge(["wyckoff-2-0", ...])`
3. Fetch data using `market-data-fetch` templates (Phase 1)
4. Run Phases 2-5 sequentially, computing each dimension score
5. Apply weights, compute final score, map to verdict
6. Output formatted verdict with rationale per dimension
7. Always include risk factors specific to the asset

## Anti-Patterns

- **Don't** produce a verdict if data is insufficient (score = 0 or N/A in 3+ dimensions). Instead say "Dati insufficienti — impossibile produrre verdetto."
- **Don't** hedge the verdict. If score is 72, say LONG-TERM INVEST, not "potrebbe essere long ma anche short."
- **Don't** mix stock and crypto weights. Use the correct weight table based on asset type.
- **Don't** skip any phase even if data is partial. Assign 0 to unavailable dimensions and note it.
