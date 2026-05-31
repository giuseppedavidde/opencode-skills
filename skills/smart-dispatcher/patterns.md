# Patterns — Smart Dispatcher

## Intent Classification Table

| Intent | Keywords (italiano) | Keywords (english) | Confidence boost |
|--------|-------------------|--------------------|-----------------|
| `market_scan` | scan, screening, scansiona, mercato/i, mercat*, cerca ticker, ticker da comprare, accumulazione, setup, opportunità | market scan, scan, screening, find stocks, accumulation, setups, tickers to watch, what to buy | +0.2 se include nomi di mercati (italy, germany, etc.) |
| `deep_dive` | analizza, analisi, deep dive, cosa fare, cosa farne, cosa fare con, cosa fare di, cosa fare su, verdict, unified analysis, parere su, giudizio su | analyze, analysis, what to do with, verdict, opinion on, should I buy, investment thesis | +0.2 se include simboli ticker |
| `options_suggest` | opzioni, opzioni su, strategia opzioni, strategia opzioni su, suggerisci opzioni, covered call, put, call, opzione | options on, options strategy, suggest options, covered call, put, call | +0.3 se include "opzioni" o "options" |
| `wsb_detect` | wsb, wallstreetbets, pump, pompano, pompaggio, meme stock, meme, fomo, cosa pompano, radar wsb | wsb, wallstreetbets, pump, pumping, meme stock, meme, what's pumping, wsb radar, squeeze | +0.2 se include "wsb" o "wallstreet" |
| `data_fetch` | fetch, prendi, dati di, dati su, quotazione, prezzo di, prezzo, price, stock price, azione | fetch, get data, price of, quote, stock price, market data, financial data | +0.2 se include ticker + "prezzo" o "price" |
| `full_pipeline` | cosa comprare, cosa fare oggi, migliori occasioni, migliori setup, wsb + analisi, wallstreetbets analisi | what to buy, best opportunities, best setups today, wsb analysis | +0.3 se include "comprare"/"buy" + "oggi"/"today" |

## Market Aliases — Mappa Completa

### Da nome geografico a universo orchestrator

| Chiave (italiano) | Chiave (english) | Universo |
|-------------------|-------------------|----------|
| nasdaq, tecnologici americani, qqq | nasdaq, tech stocks, qqq | `us_tech` |
| america, stati uniti, usa, s&p, nyse, sp500, large cap | us, usa, america, s&p 500, nyse | `us_large` |
| italia, milano, italy, mib, ftse mib, piazza affari | italy, italian, milan | `italy` |
| germania, germany, dax, francoforte, tedesco | germany, german, dax, frankfurt | `germany` |
| francia, france, parigi, cac 40, paris | france, french, paris, cac | `france` |
| inghilterra, uk, londra, ftse 100, london | uk, england, london, ftse | `uk` |
| spagna, spain, madrid, ibex 35, ibex | spain, spanish, madrid, ibex | `spain` |
| europa, europeo, mercati europei, eu | europe, european, eu | `all_eu` = italy+germany+france+uk+spain |
| mondo, tutto, globale, global, mercati globali, all | world, global, all, whole world | `all` = us_large+us_tech+all_eu |

### Da settore a universo

| Settore | Universo |
|---------|----------|
| banche, assicurazioni, finanziari | `all_eu` (per ora) |
| tech, tecnologia, tecnologici | `us_tech` |
| energia, oil, gas | `all` |

## Parameter Extraction — Regex

```python
# Numeri dopo "top/best/primi/top/primes"
TOP_RE = re.compile(r'(?:top|best|migliori?|primi?|prime?)\s*(\d+)', re.IGNORECASE)

# Ticker: 1-5 lettere + eventuale suffisso .MI .DE .PA .L .MC
TICKER_RE = re.compile(r'\b([A-Za-z]{1,5}(?:\.(?:MI|DE|PA|L|MC))?)\b')

# Nomi mercato (vedi tabella aliases sopra)
MARKET_RE = re.compile(
    r'\b(italy|italia|germany|germania|france|francia|spain|spagna|'
    r'uk|inghilterra|nasdaq|europa|europe|usa|america|mondo|world)\b',
    re.IGNORECASE
)
```

## Confidence Scoring

```python
confidence = 0.0
if keyword_match(intent_keywords):
    confidence += 0.5
if market_match:
    confidence += 0.3  # intent = market_scan
if ticker_match:
    confidence += 0.3  # intent = deep_dive, options, data_fetch
if top_match:
    confidence += 0.1

if confidence >= 0.8:
    execute()       # esegui direttamente
elif confidence >= 0.5:
    ask_user()      # chiedi conferma
else:
    fallback()      # chiedi di essere più specifico
```

## Orchestrator Command Templates

```python
COMMANDS = {
    "market_scan": "--skills market-accumulation-scanner "
                   "--items {markets} --split-by market --top {top}",

    "deep_dive": "--skills stock-crypto-analysis "
                 "--items {tickers} --split-by ticker --top {top}",

    "options_suggest": "--skills options-strategy-suggestions "
                       "--items {tickers} --split-by ticker",

    "wsb_detect": "--skills wallstreetbets-pump-detect",

    "data_fetch": "--skills market-data-fetch "
                  "--items {tickers} --split-by ticker --merge concat",

    "full_pipeline": "--pipeline "
                     "--phase-1 \"wallstreetbets-pump-detect --top {top}\" "
                     "--phase-2 \"stock-crypto-analysis --split-by ticker\" "
                     "--phase-3 \"options-strategy-suggestions --split-by ticker\"",
}
```

## Example Output per Intent

### market_scan
```
📊 Smart Scan: Italia, Germania, Francia
Orchestrato: 3 agent paralleli | Tempo: 84s → 32s (2.6x)

  #1  DBK.DE   66.0  Deutsche Bank AG         Accumulation Spring
  #2  BNP.PA   59.8  BNP Paribas              Accumulation Spring
  #3  SAB.MC   62.0  Banco de Sabadell        Accumulation Spring
  #4  MBG.DE   60.8  Mercedes-Benz Group      Accumulation Spring
  #5  ISP.MI   60.8  Intesa Sanpaolo          Accumulation Spring
```

### deep_dive
```
🎯 Deep Dive: DBK.DE, SGRO.L, PST.MI
Orchestrato: 3 agent paralleli | Tempo: 180s → 65s (2.8x)

#1 — DBK.DE — LONG-TERM INVEST 🟢 (76%)
  P/E 8.8 | Spring Wyckoff | Margini 23%
  Entry $26.47-$27.86 | SL $25.63 | T1 $30.65 | T2 $34.83

#2 — SGRO.L — LONG-TERM INVEST 🟢 (76%)
  P/E 17.6 | Inst 83% | Margini 76%
  Entry £686-£722 | SL £665 | T1 £795 | T2 £903
```

### wsb_detect
```
🔥 WSB Radar
Fonte: r/wallstreetbbs | 15 minuti fa

  GME (62 mentions) — Hype Score: 78 — Squeeze Potential: ALTA
  AMC (45 mentions) — Hype Score: 65 — Squeeze Potential: MEDIA
  BBBY (12 mentions) — Hype Score: 42 — Squeeze Potential: BASSA

→ Vuoi analizzare GME con stock-crypto-analysis?
```
