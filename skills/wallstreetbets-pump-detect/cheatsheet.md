# Cheatsheet — WallStreetBets Pump Detect

## Trigger Quick Reference

| Comando | Azione |
|---------|--------|
| `wsb scan` | Scansione completa WSB: top ticker + analisi |
| `wsb radar` | Solo hype score + FOMO phase (senza analisi) |
| `wsb su $TICKER` | Analisi approfondita su un ticker specifico su WSB |
| `pump detect` | Come `wsb scan` |
| `tendenze wsb` | Solo top 5 ticker per menzioni |

## Dataset Pesi Hype Score

| # | Dimensione | Peso | Valore Default (se dati mancanti) |
|---|-----------|:----:|:---------------------------------:|
| 1 | Mention Volume | 25% | 0 |
| 2 | Engagement | 20% | 50 (neutro) |
| 3 | Sentiment Polarity | 15% | 50 (neutro) |
| 4 | Post Authority | 15% | 40 |
| 5 | Squeeze Setup | 25% | 0 (skip se non disponibile) |

## URL Reddit JSON Pubblici

```python
# Da usare con webfetch (nessuna API key necessaria)
urls = {
    "hot":  "https://www.reddit.com/r/wallstreetbets/hot.json?limit=100",
    "new":  "https://www.reddit.com/r/wallstreetbets/new.json?limit=100",
    "top":  "https://www.reddit.com/r/wallstreetbets/top.json?limit=100&t=day",
    "rising": "https://www.reddit.com/r/wallstreetbets/rising.json?limit=100",
}
```

## Blacklist Ticker (parole comuni escluse)

```
A, I, IT, GO, BY, AT, TO, BE, ON, UP, NO, SO, OR, DO, WE, HE, ME,
US, MY, AS, IS, IN, OF, IF, AM, AN, AX, BOX, CAN, CAR, CAT, DAY,
DID, EAT, FAR, FOR, GET, GOT, HAS, HER, HIM, HIS, HOW, JOB, KEY,
LOT, MAN, MEN, NEW, NOT, NOW, OLD, ONE, OUT, OWN, PAY, PUT, RED,
RUN, SAY, SEE, SET, SHE, SIT, SIX, SON, SUN, TEN, THE, TIE, TWO,
USE, VAN, WAR, WAY, WHO, WIN, YES, YET, CEO, IPO, ETC, INC, LTD,
BIG, TOP, ALL, ANY, ARE, EACH, FEW, FED, HIT, LIT, RIO, SAO,
BOT, BUY, OFF, AGE, AGO, ART, BAD, BED, BET, BIT, BUS, CUT,
DAM, DIE, DUE, EGG, ELF, END, EYE, FAT, FLY, FUN, GAS, GUN,
GUY, HAT, HIP, ICE, ILL, ITS, JAM, JET, LAB, LAD, LAY, LEG,
LIP, MAD, MAP, MIX, NET, NOR, NUT, OIL, OWL, PAN, PAT, PEA,
PEN, PET, PIE, PIG, POT, RAT, RAW, ROD, RUB, RUG, RUM, SAT,
SAW, SEA, SEW, SIN, SIP, SKI, SKY, SLY, SPA, SPY, TAB, TAP,
TEA, TIP, TOE, TON, TOO, TOY, TUB, TWO, VAT, VET, VOW, WAX,
WEB, WED, WET, WIG, WIT, WON, WOO, YAM, YAP, YAW, YEA, YES,
```

## FOMO Phase Thresholds Riavvicinati

| Fase | Hype Score | Post 24h | Prezzo Δ 7gg | Volume Ratio (oggi/20d) |
|:----:|:----------:|:--------:|:------------:|:----------------------:|
| 🔵 Early | < 20 | 1-5 | +5-15% | 1.0-2.0x |
| 🟡 Mid | 20-60 | 5-20 | +15-50% | 2.0-5.0x |
| 🟠 Late | 60-85 | 20-50 | +50-150% | 5.0-15.0x |
| 🔴 Exit | > 85 | > 50 | > +150% | > 15.0x |

## Squeeze Setup Thresholds

| Condizione | Score Parziale |
|-----------|:-------------:|
| Short Interest < 10% | 0 |
| Short Interest 10-20% | 20 |
| Short Interest 20-30% | 30 |
| Short Interest > 30% | 50 |
| Borrow Fee < 10% | 0 |
| Borrow Fee 10-50% | 15 |
| Borrow Fee 50-100% | 25 |
| Borrow Fee > 100% | 30 |
| Days to Cover < 1 | 0 |
| Days to Cover 1-3 | 5 |
| Days to Cover 3-7 | 10 |
| Days to Cover > 7 | 20 |

## Sizing Guidelines per FOMO Phase

| Fase | % Portafoglio | Stop Loss | Take Profit |
|:----:|:-------------:|:---------:|:-----------:|
| Early FOMO | 3-5% | -15% | +30-50% |
| Mid FOMO | 1-3% | -10% | +20-30% |
| Late FOMO | 0% | N/A | N/A |
| Exit FOMO | 0% (o short) | N/A | N/A |

## Linguaggio Bullish vs Bearish (Sentiment Analysis)

**Bullish keywords** (+1 ciascuna): 🚀, moon, tendies, calls, yolo, squeeze, breakout, rocket, rip, omega, short squeeze, gama, gamma ramp, FOMO, superstonk, buying, cover, shorties, hedgies r fuk

**Bearish keywords** (-1 ciascuna): rug, dump, baghold, short, dead, rugpull, exit, liquidity, stop loss, margin call, capitulation, bagholder, cuck, paper hands, ftd, fail

**Neutral/skip**: DD, TA, discussion, technical, analysis, chart — indicatori di qualità, non polarità

## Comandi yfinance Rapidi

```python
import yfinance as yf
t = yf.Ticker("TICKER")
t.info.get("shortPercentOfFloat")  # Short interest %
t.info.get("heldPercentInstitutions")
t.info.get("shortRatio")           # Days to Cover
t.info.get("currentPrice")
hist = t.history(period="1mo")
vol_ratio = hist["Volume"].iloc[-1] / hist["Volume"].rolling(20).mean().iloc[-1]
```

## Aggregatori WSB Alternativi (se Reddit JSON è rate-limited)

| Fonte | URL | Metodo |
|-------|-----|--------|
| AltIndex | altindex.com/wallstreetbets | `websearch` + `webfetch` |
| SwaggyStocks | swaggystocks.com/dashboard/wallstreetbets | `webfetch` |
| WSB Tracker | wsb-tracker.com | `websearch` |

## Data Extraction from JSON

```python
# Ogni post nel JSON ha struttura:
post = {
    "title": "$GME to the moon! 🚀",
    "score": 5432,
    "upvote_ratio": 0.96,
    "num_comments": 847,
    "link_flair_text": "DD",
    "selftext": "Deep analysis...",
    "created_utc": 1748550000,
    "author": "wsb_degen_69",
    "permalink": "/r/wallstreetbets/comments/xyz123/",
    "gilded": 2,
    "total_awards_received": 5,
}
```

## Execution Checklist

1. [ ] Fetch hot.json, new.json, top.json da r/wallstreetbets
2. [ ] Estrai ticker da titoli di tutti i post (min 50 post totali)
3. [ ] Applica blacklist e valida ticker (NASDAQ list + yfinance)
4. [ ] Calcola hype score per ogni ticker
5. [ ] Determina FOMO phase per ogni candidato
6. [ ] Filtra: hype ≥ 50, max 5 ticker
7. [ ] Per ogni candidato: esegui stock-crypto-analysis
8. [ ] Se unified score ≥ 70: esegui options-strategy-suggestions
9. [ ] Output formattato con tutti i dettagli
