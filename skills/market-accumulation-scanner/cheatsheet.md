# Cheatsheet — Market Accumulation Scanner

## Weight Table (5 Dimensions)

The source of the weights is the trading MCP only: `mcp/src/trading_mcp/weights_config.py`
(defaults, or the user file `~/.config/opencode/weights.json`) and the regime rules in
`mcp/src/trading_mcp/analysis/macro.py`. The table shows the MCP defaults. If a value differs, the MCP wins.

| # | Dimension | Default weight | Source |
|---|-----------|:------:|--------|
| 1 | Wyckoff Structure | 20% | yfinance 1y daily + Vol-Price Divergence |
| 2 | Volume Profile | 20% | yfinance 3mo daily |
| 3 | Price Action | 15% | yfinance 1mo daily + Rally Velocity |
| 4 | **Sentiment** | **20%** | 9 sub-dimensions (see below) |
| 5 | Fundamentals + Competitive | 25% | yfinance info (P/E, margins, D/E, ROE, ROA, FCF, earnings quality, value trap, price vs consensus) |

Note: Competitive Positioning (ROE, ROA, operating margins, moat proxy) has been merged into Fundamentals.
The old 6-dimension formula (including separate Competitive at 10%) is superseded by this 5-dimension formula.

### Aggregation Formula

```
vp_bullish = 100 - volprof          # volprof is an EXTENSION score
final = wyckoff * 0.20 + vp_bullish * 0.20 + pa * 0.15 + sentiment * 0.20 + fundamentals * 0.25
```

`volprof` is an extension score: low means price sits below the value area
(discount), high means price is extended above it. The scanner inverts it
before weighting because the signal is treated as mean-reversion. The IC figure
that the repository quotes for this choice uses overlapping labels: it is not a validation.
The reported `Volume Profile` dimension is already inverted, so higher always
means more bullish.

### Macro Regime Multiplier (Phase 0)

Applied post-aggregation. Controlled via `--regime` CLI arg (default: NORMAL).

| Regime | Multiplier | Sector Adjustments |
|--------|:---------:|--------------------|
| FULL | 1.08x | All sectors boosted (risk-on) |
| NORMAL | 1.00x | No adjustment |
| SELECTIVE | 1.00x | Defensive (+5%), Cyclical (-10%) |
| DEFENSIVE | 0.85x | All sectors penalized (cap at 60) |

Two adjustments are applied in this order:

1. **Dimensional weights by regime** — `get_dynamic_weights(regime)` rescales
   the five dimension weights (CRISIS raises sentiment, HIGH_VOLATILITY raises
   Wyckoff and lowers Price Action, RANGE_BOUND raises Volume Profile,
   TRENDING_BULL raises Wyckoff/sentiment, TRENDING_BEAR raises
   sentiment/Volume Profile). The scanner uses these weights during
   aggregation, so the same ticker can score differently in two regimes.
2. **Sector multiplier** — the table above, applied after aggregation.

## Sentiment Sub-Dimension Weights (9 total)

| Sub-Dimension | % of Sentiment | % of Total | Data Collection |
|:-------------:|:--------------:|:----------:|-----------------|
| Short Interest | 12% | 2.4% | yfinance (SI%, DTC, dynamic thresholds by mcap) |
| Options Sentiment | 12% | 2.4% | P/C volume, P/C OI, IV skew |
| Insider Trading | 12% | 2.4% | yfinance insider transactions |
| Retail Sentiment | 8% | 1.6% | Volume ratio, beta, analyst gap |
| Institutional | 12% | 2.4% | Holdings %, buyback yield |
| Relative Momentum | 8% | 1.6% | vs SPX on 1mo/3mo/6mo |
| Web News | 8% | 1.6% | Finviz → Yahoo RSS → Google News → MarketBeat |
| Social Media | 8% | 1.6% | WSB hotlist cross-reference |
| **Earnings Quality** | **20%** | **4.0%** | EPS growth, FCF, accrual proxy (Sloan 1996) |

**Aggregation**: Weighted average of available sub-dimensions, re-normalized.

## Wyckoff — Score Table

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| Price in bottom 30% of 1Y range | +15 | 15 |
| Price in 30-60% of 1Y range | +30 | 30 |
| HH/HL pattern (last 60d) | +40 | 40 |
| LH/LL pattern (last 60d) | -20 | 0 |
| Spring detected | +30 | 30 |
| MA50 > MA200 (golden cross setup) | +15 | 15 |
| Volume decreasing in range (absorption) | +15 | 15 |
| **Volume-Price Divergence**: ↑Vol + ↓Price (Accumulation) | +25 | 25 |
| **Volume-Price Divergence**: ↓Vol + ↑Price (Distribution) | -20 | 0 |
| **Volume-Price Divergence**: ↑Vol + ↑Price (Markup) | +15 | 15 |
| **Volume-Price Divergence**: ↓Vol + ↓Price (Markdown) | -15 | 0 |
| Base | +20 | 20 |
| **Total cap** | | **100** |

## Volume Profile — Score Table

The profile is a volume-at-price histogram with 40 bins. Each bar's volume is
spread across every bin between `Low` and `High`. The value area expands
contiguously from the POC until it covers 70% of the volume.

The output is an **extension score** (0 = deep discount, 100 = extended):

| Condition | Score |
|-----------|:-----:|
| Price below VAL | 20 |
| Price inside VA | 35-65 (linear between VAL and VAH) |
| Price above VAH | 80 |
| Price within 2% of POC (inside VA) | pulled halfway to 50 |

A 1% buffer around VAL and VAH stops the regime from flipping on marginal
moves. The score is quantised to a 5-point grid. The scanner and the verdict
engine consume `100 - score` (higher = more bullish).

## Price Action — Score Table

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| RSI 40-60 | +10 | 10 |
| RSI 30-40 | +20 | 20 |
| RSI < 30 | +10 | 10 |
| 25ema rising | +15 | 15 |
| VPA net bullish > bearish (last 20) | +20 | 20 |
| Effort/Result positive | +15 | 15 |
| Cluster near S/R (buildup) | +20 | 20 |
| Base | +10 | 10 |
| **Total cap** | | **100** |

## Sentiment — Score Table

### A) Traditional Sentiment (40% del Sentiment, max 100)

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| Short interest 10-20% | +20 | 20 |
| Short interest > 20% | +35 | 35 |
| Institutional ownership > 50% | +15 | 15 |
| Days to cover > 3 | +15 | 15 |
| Days to cover > 7 | +25 | 25 |
| Base | +25 | 25 |
| **Total cap (traditional)** | | **100** |

### B) Web News Sentiment (35% del Sentiment, max 100)

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| 4+ headlines positive (upgrade, buy, beat, growth) | +40 | 40 |
| 2-3 headlines positive | +20 | 20 |
| Neutral / mixed | 0 | 0 |
| 2-3 headlines negative (downgrade, miss, cut) | -20 | 0 |
| 4+ headlines negative | -40 | 0 |
| Earnings beat / guidance raise | +30 bonus | 30 |
| Regulatory approval / partnership | +20 bonus | 20 |
| Lawsuit / investigation / SEC | -30 penalty | 0 |
| No news found | 0 | 0 |
| **Base** | **+50** | **50** |

Formula: `web_news = clamp(50 + sum(delta), 0, 100)`

#### News Source URLs (da usare con webfetch)

| Source | URL Pattern |
|--------|------------|
| **Finviz** (primario) | `https://finviz.com/quote.ashx?t={TICKER}` |
| **Yahoo Finance** (fallback) | `https://finance.yahoo.com/quote/{TICKER}/news` |
| **WSJ** (Phase 5 only) | `websearch("{TICKER} stock news 2026 site:wsj.com")` |
| **Bloomberg** (Phase 5 only) | `websearch("{TICKER} stock 2026 site:bloomberg.com")` |

**Parse Finviz news table** (da HTML via webfetch):
```
La pagina Finviz ha una tabella news sotto "News".
Cerca elementi <a class="tab-link-news"> con testo + data.
Polarità: keyword match sui titoli.
```

### C) Social Media Sentiment (25% del Sentiment, max 100)

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| WSB hotlist: Early FOMO + bullish sentiment | +40 | 40 |
| WSB hotlist: Mid FOMO + mixed sentiment | +20 | 20 |
| WSB hotlist: Late/Exit FOMO | -20 | 0 |
| Non su WSB ma X buzz positivo | +10 | 10 |
| Non su WSB | 0 | 0 |
| X buzz negativo (sell calls, panic) | -15 | 0 |
| **Base** | **+50** | **50** |

Formula: `social_media = clamp(50 + sum(delta), 0, 100)`

#### WSB Hotlist Cross-Reference

Prima dello scan, esegui:
```
wsb scan → salva lista ticker con hype_score, FOMO phase, sentiment
```
Poi durante lo scan, per ogni ticker:
```
if ticker in wsb_hotlist:
    match WSB phase + sentiment → score delta
else:
    social_media = 50 (neutro, skip WSB check)
```

## Fundamentals — Score Table

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| P/E < 15 | +30 | 30 |
| P/E 15-25 | +15 | 15 |
| Revenue growth YoY > 0 | +20 | 20 |
| Profit margins > 0 | +20 | 20 |
| Debt/Equity < 1.0 | +15 | 15 |
| Debt/Equity < 0.5 | +25 | 25 |
| Market Cap > $10B | +10 | 10 |
| ROE > 20% (competitive moat) | +15 | 15 |
| ROE > 15% | +10 | 10 |
| ROA > 10% | +10 | 10 |
| ROA > 5% | +5 | 5 |
| Operating Margins > 20% (efficiency) | +10 | 10 |
| Base | +5 | 5 |
| **Total cap** | | **100** |

## Score Ranges (ranking only, not a verdict)

| Final Score | Meaning |
|:-----------:|---------------|
| 70-100 | Top of the ranking. Not a buy signal |
| 50-69 | Middle of the ranking |
| 30-49 | Weak |
| 0-29 | Bottom of the ranking |

The scan gives no verdict, stop or target. The agent prompt decides when a ticker needs `analyze_stock`.

## Filtro Anomalie Critiche

Escludi automaticamente se:
- Fundamentals = 0 AND P/E is None AND profit margins < 0

## CLI Arguments (scanner.py)

| Arg | Default | Description |
|-----|---------|-------------|
| `--universe` | `us_large` | Universe name |
| `--tickers` | None | Custom comma-separated ticker list |
| `--min-score` | 50 | Minimum score to include |
| `--top` | 15 | Number of top candidates to show |
| `--output-dir` | `.` | Directory for CSV/HTML reports |
| `--regime` | `NORMAL` | Macro regime: FULL, NORMAL, SELECTIVE, DEFENSIVE |
| `--fetch-news` | false | Fetch Finviz/Yahoo news for web news sentiment (slower) |
| `--list-tickers` | false | Print the symbols of the universe as JSON and exit |
| `--json-output` | false | Print the rows as JSON, write no file |

`scripts/scanner.py` is a thin wrapper of the MCP scanner. The old flags `--batch-size`,
`--batch-sleep` and `--wsb-hotlist` are accepted and ignored.

## CLI Examples

```bash
# Scan US large cap
python3 scripts/scanner.py --universe us_large --top 20

# Scan Italy + Germany
python3 scripts/scanner.py --tickers "ENI.MI, ISP.MI, SAP.DE, SIE.DE" --top 10

# Full scan with custom threshold
python3 scripts/scanner.py --universe all --min-score 60 --top 10

# Quick scan with low threshold to see everything
python3 scripts/scanner.py --universe us_tech --min-score 0 --top 50
```

## Universe Composition

| Universe | File | Count |
|----------|------|:-----:|
| us_large | data/us_tickers.csv (all) | ~600 |
| us_tech | data/us_tech_tickers.csv (else the Information Technology rows of us_tickers.csv) | ~100 |
| italy | data/italy_tickers.csv (else the Italy rows of europe_tickers.csv) | 40 |
| germany | data/germany_tickers.csv (else the Germany rows of europe_tickers.csv) | 40 |
| france | data/france_tickers.csv (else the France rows of europe_tickers.csv) | 40 |
| uk | data/uk_tickers.csv (else the UK rows of europe_tickers.csv) | 100 |
| spain | data/spain_tickers.csv (else the Spain rows of europe_tickers.csv) | 35 |
| crypto | data/crypto_tickers.csv | ~50 |
| all | Combined | ~900 |

## CSV Data Format

```
symbol,name,suffix,market
AAPL,Apple Inc.,,US
ENI.MI,Eni S.p.A.,.MI,Italy
```

`suffix` is the yfinance exchange suffix (`.MI`, `.DE`, `.PA`, `.L`, `.MC`).
US tickers have no suffix.
