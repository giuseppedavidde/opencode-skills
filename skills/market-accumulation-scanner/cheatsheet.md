# Cheatsheet — Market Accumulation Scanner

## Weight Table

| # | Dimension | Weight | Source |
|---|-----------|:------:|--------|
| 1 | Wyckoff Structure | 25% | yfinance 1y daily |
| 2 | Volume Profile | 20% | yfinance 3mo daily |
| 3 | Price Action | 20% | yfinance 1mo daily |
| 4 | Sentiment | 15% | yfinance info |
| 5 | Fundamentals | 20% | yfinance info |

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
| Base | +20 | 20 |
| **Total cap** | | **100** |

## Volume Profile — Score Table

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| Price inside Value Area | +20 | 20 |
| Price below VAL | +25 | 25 |
| Price above VAH | +15 | 15 |
| Price within 5% of VPOC | +10 | 10 |
| Volume ratio 1.0-2.0x | +10 | 10 |
| Volume ratio > 2.0x | +15 | 15 |
| D-Profile shape | +15 | 15 |
| VPOC rising over 3mo | +15 | 15 |
| Base | +10 | 10 |
| **Total cap** | | **100** |

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

| Condition | Delta | Max |
|-----------|:-----:|:---:|
| Short interest 10-20% | +20 | 20 |
| Short interest > 20% | +35 | 35 |
| Institutional ownership > 50% | +15 | 15 |
| Days to cover > 3 | +15 | 15 |
| Days to cover > 7 | +25 | 25 |
| Base | +25 | 25 |
| **Total cap** | | **100** |

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
| Base | +10 | 10 |
| **Total cap** | | **100** |

## Verdict Thresholds

| Final Score | Recommendation |
|:-----------:|---------------|
| 70-100 | Strong candidate → stock-crypto-analysis highly recommended |
| 50-69 | Moderate candidate → review, selective deep dive |
| 30-49 | Weak — skip unless specific pattern match |
| 0-29 | Avoid |

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
| `--batch-size` | 20 | Tickers per API batch |
| `--batch-sleep` | 1.0 | Seconds between batches |

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
| us_tech | data/us_tickers.csv (NASDAQ 100 filter) | ~100 |
| italy | data/europe_tickers.csv (Italy filter) | 40 |
| germany | data/europe_tickers.csv (Germany filter) | 40 |
| france | data/europe_tickers.csv (France filter) | 40 |
| uk | data/europe_tickers.csv (UK filter) | 100 |
| spain | data/europe_tickers.csv (Spain filter) | 35 |
| all | Combined | ~900 |

## CSV Data Format

```
symbol,name,suffix,market
AAPL,Apple Inc.,,US
ENI.MI,Eni S.p.A.,.MI,Italy
```

`suffix` is the yfinance exchange suffix (`.MI`, `.DE`, `.PA`, `.L`, `.MC`).
US tickers have no suffix.
