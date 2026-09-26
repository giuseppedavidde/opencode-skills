---
name: wallstreetbets-pump-detect
description: >
  Renders r/wallstreetbets through the bladebro stealth browser (public JSON as
  fallback) to find stocks/ETFs being pumped, scores hype level and squeeze
  potential, detects FOMO phase, then feeds into stock-crypto-analysis and
  options-strategy-suggestions for full entry evaluation (buy underlying or
  options strategy).
metadata:
  argument-hint: '[scan, "cosa pompano su WSB", "wsb radar", "meme stock scan", "pump detect"]'
---

# WallStreetBets Pump Detect

Detects stocks and ETFs being pumped on r/wallstreetbets by rendering the subreddit through the `bladebro` stealth browser (public JSON as fallback), scores hype on 5 dimensions, detects which FOMO phase the pump is in, then feeds qualified candidates into `stock-crypto-analysis` and `options-strategy-suggestions` for full entry evaluation.

## Skill Dependencies

This skill loads and integrates:
- `bladebro` — Stealth-browser CLI/MCP that renders r/wallstreetbets (feed + comment trees) and is the primary data source
- `stock-crypto-analysis` — Unified verdict (Long-Term Invest / Short-Term Spec / Avoid), per-dimension scores, direction
- `options-strategy-suggestions` — Options strategies including Synthetic Long 2:1
- `market-data-fetch` — Current prices, volumes, short interest, borrow fee, fundamentals

## Triggers

`wsb`, `pump detect`, `wallstreetbets`, `meme stock`, `whats hot on wsb`,
`cosa pompano su wsb`, `wsb radar`, `tendenze wsb`, `cosa sta pompando`,
`scan wsb`, `meme radar`, `wsb ticker scan`

## Core Framework — 6 Phases

### Phase 1 — WSB Data Collection

Fonte **primaria**: `bladebro` stealth-browser (CLI o MCP) — renderizza Reddit con un Chrome reale, quindi restituisce i contenuti anche quando l'endpoint JSON viene bloccato o rate-limitat. L'endpoint **pubblico JSON** di Reddit resta solo come **fallback**.

**Requisiti ambiente** (il client Python `scripts/bladebro_client.py` li imposta da solo):

```
BLADEBRO_BIN=/home/giuseppe/.local/share/opencode/bladebro-node/bin/bladebro   # opzionale, override
CHROME_PATH=/home/giuseppe/.local/share/opencode/bladebro-node/chrome
BLADE_HOME=/tmp/opencode/wsb-blade
```

**Comandi bladebro** (il daemon persiste tra le chiamate: un solo Chrome per tutte):

Feed (hot / new / top):

```
bladebro see "https://www.reddit.com/r/wallstreetbets/hot/" extract auto --limit 100
bladebro see "https://www.reddit.com/r/wallstreetbets/new/" extract auto --limit 100
bladebro see "https://www.reddit.com/r/wallstreetbets/top/?t=day" extract auto --limit 100
```

L'output è la riga `extract auto:` seguita da un oggetto JSON:

```json
{"container":"reddit-feed","count":N,"items":[
  {"title","author","score","comments","date","subreddit","domain","url","content_href","type"}
]}
```

**Lazy render**: un singolo `extract auto` sul feed restituisce solo ~4 post perché Reddit renderizza il feed in modo lazy. Per un dataset pieno usare, in ordine:

1. **Browser JSON** (preferito: include `upvote_ratio` e `link_flair_text`). Il browser bladebro scarica il listing `.json` e ne offloada il risultato su un artifact:
   ```
   bladebro act navigate "https://www.reddit.com/r/wallstreetbets/hot/"
   bladebro act eval "fetch('https://www.reddit.com/r/wallstreetbets/hot.json?limit=100').then(r=>r.text())"
   ```
2. **`act collect`** (`--max N`): paginazione/scroll automatico, un solo artifact per l'intero feed.
   ```
   bladebro act collect "https://www.reddit.com/r/wallstreetbets/hot/" --max 100
   ```
3. **`act scroll` eased ripetuto** + `see extract auto`, accumulando i post finché non arrivano nuovi item.

Deduplicare sempre per `content_href`/`id`. `bladebro_client.fetch_feed_bulk(...)` implementa i tre percorsi con un parametro `target` (default 100):
```
python3 bladebro_client.py --subreddit wallstreetbets --listing hot --target 100
```

Thread di commenti (per il sentiment sul testo reale):

```
bladebro see "<post_url>" extract auto --limit 100
```

```json
{"container":"reddit-comments","post":{...},"count":N,"total":M,"items":[
  {"id","author","score","date","depth","text","url"}
]}
```

**Payloads >12KB**: bladebro offloads the extract to `$BLADE_HOME/artifacts/<id>.json` and stdout returns a `(N bytes) → path` reference plus a truncated preview; `bladebro_client.parse_extract_output` follows that reference and reads the full JSON automatically.

**Retry JS-challenge**: la prima load di un URL reddit.com può restituire solo la pagina challenge. In tal caso eseguire `bladebro act wait settle 3000` e rileggere (`bladebro see extract auto`), fino a 2 tentativi — `bladebro_client` lo fa automaticamente.

**Block / rate-limit**: Reddit può servire una interstitial di rate-limit (codici tipo `01a0de31…`, testi "rate limit" / "you've been blocked") oppure rispondere **403** al JSON pubblico. `bladebro_client` rileva URL e firme testuali e applica un **backoff esponenziale bounded**: prima ri-setta/re-wait, poi riprova ruotando eventualmente l'endpoint listing (`hot`/`new`/`top`). Se tutte le sorgenti risultano bloccate solleva `BladebroBlockedError` — **mai un dataset vuoto silenzioso**. I caller (`realtime_monitor`, `multi_platform_sentiment`) surfaceano l'errore invece di trattarlo come "zero post".

**Fallback JSON** (se bladebro non è disponibile o restituisce feed vuoto):

```
https://www.reddit.com/r/wallstreetbets/hot.json?limit=100
https://www.reddit.com/r/wallstreetbets/new.json?limit=100
https://www.reddit.com/r/wallstreetbets/top.json?limit=100&t=day
```

Parse `data.children[]` → `title`, `score`, `upvote_ratio`, `num_comments`, `link_flair_text`, `selftext`, `created_utc`, `author`, `permalink`, `url`, `gilded`.

Se anche il JSON è rate-limited, ultimo fallback: `websearch` per "most mentioned WSB stocks today 2026" e aggregatori (AltIndex, SwaggyStocks, WSB Tracker).

I comment tree ora alimentano il **Sentiment Polarity reale** (Phase 3, dimensione 3): il sentiment va calcolato anche sul testo dei commenti, non solo sui titoli dei post.

### Phase 2 — Ticker Extraction

**Step A — Extract raw candidates** from each post:

1. `$TICKER` pattern: regex `\$[A-Z]{1,5}` (e.g., `$GME`, `$NVDA`)
2. ALLCAPS words 1-5 characters in title (e.g., `GME`, `NVDA`, `AMC`, `BB`)
3. Exclude words in the blacklist (see cheatsheet)
4. Include only if validated against a known ticker set:

**Step B — Validate candidates** — implemented in `scripts/ticker_validation.py`:

1. **Bundled NASDAQ-trader universe** — `scripts/data/us_tickers.txt.gz` (~12,900 active symbols: 7,131 stocks + 5,736 ETFs) built from `nasdaqlisted.txt` + `otherlisted.txt`; provenance/date in `scripts/data/us_tickers.meta.json`. Matching is case-insensitive, so `avgo`/`goog` count like `AVGO`/`GOOG`; the blacklist still applies. Refresh with `python ticker_validation.py --refresh-snapshot` (a fresh copy is also auto-cached under `~/.cache/opencode/wsb-pump-detect/`).
2. **yfinance fallback** — symbols absent from the universe are checked via `yf.Ticker(candidate).info`; only `EQUITY`/`ETF` quote types count (mutual funds and ECN quotes are rejected). The fallback runs inside the shared trading venv `~/.local/share/opencode/trading-mcp-venv/bin/python` (which already ships yfinance) — no package is installed into the skill's `scripts/.venv`.
3. **Flags** — each validated ticker carries `is_etf` and `is_leverage` (SPY/QQQ → ETF, TQQQ/SQQQ → ETF+leverage). The realtime hot loop uses the bundled universe (offline, deterministic) and enables the yfinance fallback only when `WSB_TICKER_YFINANCE=1`.

CLI: `python ticker_validation.py --validate GME avgo TQQQ --json`.

**Step C — Weight each post-ticker occurrence**:

```
post_weight = (post.score / 100) + (post.upvote_ratio * 10) + (post.num_comments / 5)
ticker_raw_score = SUM(post_weight for all posts mentioning the ticker)
```

### Phase 3 — Hype Scoring (0–100)

Score each validated ticker across 5 dimensions:

| # | Dimensione | Peso | Metrica |
|---|-----------|:----:|---------|
| 1 | **Mention Volume** | 25% | Numero post unici nelle ultime 24h, crescita rispetto al periodo precedente, commenti totali |
| 2 | **Engagement** | 20% | Upvote ratio medio, score medio, award count, ratio commenti/posts |
| 3 | **Sentiment Polarity** | 15% | Parole bullish (🚀, moon, tendies, calls, yolo, rip, squeeze, breakout, rocket) vs bearish (rug, dump, baghold, short, rip, dead, rugpull, exit) nei titoli **e nei commenti (comment tree bladebro)** |
| 4 | **Post Authority** | 15% | Percentuale di post con flair "DD" o "Technical Analysis" vs "Meme"/"Shitpost". Post di utenti con storia verificabile |
| 5 | **Squeeze Setup** | 25% | Short interest %, borrow fee (utilizzo rate), days to cover. Volume spike vs media 20d. Prezzo % da 52w low |

**Scoring formula per dimensione** (ciascuna 0-100):

```
mention_volume = min(n_posts * 10 + n_comments / 20, 100)
engagement = avg_upvote_ratio * 80 + min(avg_score / 10, 20)
sentiment = (bullish_ratio - bearish_ratio + 1) * 50   # 0 = all bearish, 50 = neutral, 100 = all bullish
post_authority = dd_ratio * 60 + (1 - meme_ratio) * 40
squeeze_setup = min(short_interest * 2, 50) + min(borrow_fee * 10, 30) + min(days_to_cover * 5, 20)
```

**Aggregazione**:
```python
hype_score = (
    mention_volume * 0.25 +
    engagement * 0.20 +
    sentiment * 0.15 +
    post_authority * 0.15 +
    squeeze_setup * 0.25
)
```

**Dati mancanti e rinormalizzazione dei pesi**: `upvote_ratio` e `link_flair_text` esistono solo se i post sono stati letti dal **browser JSON** (percorso 1); con `act collect`/scroll non sono esposti. **Engagement** (dim 2) è calcolabile solo se almeno un post ha `upvote_ratio`; **Post Authority** (dim 4) solo se almeno un post ha `flair`. Se una dimensione non ha dati reali viene marcata *UNAVAILABLE* e i pesi delle dimensioni disponibili vengono **rinormalizzati** (la somma torna a 1). Non si usa alcun default fittizio (niente `upvote_ratio=0.5`).

**Squeeze Setup (dim 5)**: sono **market data**, non dati WSB. Recuperarli dal trading MCP (`fetch_stock_data` → `shortPercentOfFloat` e `shortRatio` = days to cover; `analyze_stock` → dimensione squeeze) o via `market-data-fetch`, e passarli esplicitamente. Il *borrow fee* spesso non è disponibile da yfinance: la dimensione usa allora i soli campi presenti e rinormalizza sui massimi dei campi disponibili (o risulta *UNAVAILABLE* se nessuno è presente).

Lo scoring è implementato in modo deterministico in `scripts/hype_score.py`:
```
python3 hype_score.py --ticker META --target 100 \
  --squeeze-json '{"short_interest_pct":1.41,"days_to_cover":1.68}'
```

### Phase 4 — FOMO Phase Detection

Use hype score + price action + time context to determine pump phase:

| Fase | Hype Score | Post Count | Price Change | Media Coverage | Segnali Linguistici | Azione |
|:----:|:----------:|:----------:|:------------:|:--------------:|-------------------|--------|
| 🔵 **Early** | < 20 | 1-5 | +5-15% dal minimo 7gg | Nessuna | "DD inside", "sotto prezzo", "deep value" | **ENTRY** — migliore R/R |
| 🟡 **Mid** | 20-60 | 5-20 | +15-50% | Citazioni su r/all | "squeeze", "🚀", "calls", "moon" | **ENTRY CAUTO** — sizing 50% |
| 🟠 **Late** | 60-85 | 20-50 | +50-150% | Notizie mainstream | "diamond hands", "holding", "non vendo" | **NO ENTRY** — you are exit liquidity |
| 🔴 **Exit** | > 85 | > 50 | > +150% | TG1, Bloomberg | "hodl forever", "shorties r fuk", "soldi facili" | **EXIT / SHORT** |

Determinare la fase:
1. Calcolare hype score (da Phase 3) → mappare alla tabella
2. Verificare con `yfinance` il price change % negli ultimi 7/30gg
3. Cercare su Google News se ci sono articoli mainstream sul ticker
4. Validare con la linguistica dominante nei post

### Phase 5 — Full Analysis (soglia dinamica)

Per ogni ticker con **hype_score ≥ 50**, eseguire `stock-crypto-analysis` (max 5 ticker per scan).

Caricare `stock-crypto-analysis` e raccogliere:
- Unified Verdict (Long-Term Invest / Short-Term Spec / Avoid)
- Score 0-100
- Per-dimension rationales
- Direzione

Se lo score finale del unified verdict è ≥ 50 e la FOMO Phase non è Late/Exit, procedere.

### Phase 6 — Options Strategy (se applicabile)

Se **tutte** queste condizioni sono vere:
1. Unified verdict score ≥ 70
2. FOMO Phase = Early o Mid
3. IV non al 1° decile (non estremamente bassa)
4. Ci sono opzioni liquide (OI > 100 allo strike target)

→ Caricare `options-strategy-suggestions` e produrre raccomandazione.

Priorità suggerimenti Synthetic Long 2:1:
- Per ticker WSB, l'alta IV tipica rende il premio delle put vendute molto ricco
- La struttura 2:1 (sell 2 put + buy 1 call) sfrutta l'alto IV per incassare premium
- DTE minimo 45, ideale 60-90

Se unified verdict < 70 ma hype_score ≥ 50:
→ Raccomandare acquisto sottostante con sizing ridotto (1-3% del portafoglio)
→ Stop loss su violazione del minimo del range pre-pump

## Output Template

```
## 🚨 WSB Pump Radar — [DATE]

### #1: $TICKER

**Hype Score**: XX/100
- Mention Volume (25%): XX/100 → [+X.XX]
- Engagement (20%): XX/100 → [+X.XX]
- Sentiment (15%): XX% bull → [+X.XX]
- Post Authority (15%): DD/Meme ratio → [+X.XX]
- Squeeze Setup (25%): SI XX% | Fee XX% | DTC X.X → [+X.XX]

**FOMO Phase**: [🔵Early / 🟡Mid / 🟠Late / 🔴Exit]
- Post in 24h: XX | Avg Score: XXX | Avg Upvote: XX%
- Price Δ 7gg: +XX% | Price Δ 30gg: +XX%
- Media coverage: [Nessuna / Niche / Mainstream / Saturation]

**Squeeze Metrics**:
- Short Interest: XX% of float
- Borrow Fee: XX% (utilization: XX%)
- Days to Cover: X.X
- Volume Ratio (today/20d): X.Xx

---

→ Running stock-crypto-analysis...

### Unified Verdict: [LONG-TERM INVEST / SHORT-TERM SPEC / AVOID]
Score: XX%

**Rationale**:
- Wyckoff: [fase] → [+/-X punti]
- Volume Profile: [shape] → [+/-X punti]
- Price Action: [setup] → [+/-X punti]
- Sentiment: [segnale] → [+/-X punti]
- Fondamentali: [metriche] → [+/-X punti]

### Raccomandazione
| Aspetto | Valore |
|---------|--------|
| Azione | **[Entry / Wait / Avoid]** |
| Sizing | XX% del portafoglio |
| Entry | $XX.XX – $XX.XX |
| Stop Loss | $XX.XX |
| Target | $XX.XX |
| Orizzonte | 1-4 settimane |

### Strategia Opzioni
[Se applicabile]
- **Structure**: Synthetic Long 2:1 / Bear Call Spread / Bull Put Spread
- **Put Strike A** (entry desiderato): $XX
- **Call Strike B** (upside): $XX
- **Expiration**: [DTE]gg (data)
- **Netto**: €XX credito/debito
- **Rischio**: [Basso / Medio / Alto]

### Risk Factors
1. [FOMO phase specific risk]
2. [Short squeeze already played out?]
3. [Earnings / catalyst timeline]
4. [Borrow fee spiking → short covering accelerant]
```

## Anti-Patterns

- **Non** comprare in FOMO Phase Late o Exit — il retail è già dentro e tu sei exit liquidity
- **Non** confondere hype con squeeze potential. Un ticker molto citato non è necessariamente in short squeeze
- **Non** entrare con sizing pieno in Mid Phase — usare sizing ridotto (50% del normale)
- **Non** ignorare lo short interest. Se è calato rapidamente, lo squeeze è già avvenuto
- **Non** fare Synthetic Long 2:1 su ticker WSB se IV è al 90° percentile — il downside risk è 2x
- **Non** eseguire l'analisi su più di 5 ticker per scan — qualità > quantità
- **Non** fidarsi di DD posts su WSB come analisi fondamentale — sono tesi, non research
- **Non** dimenticare lo stop loss — i pump finiscono sempre, spesso violentemente
