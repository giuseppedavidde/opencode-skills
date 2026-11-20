---
name: stock-crypto-analysis
description: >
  Deep single-stock/crypto analysis via trading MCP, con i segnali di volatility
  spread di Bali & Hovakimian (2009) letti come ranking cross-sectional, il trend
  filter TS-MOM di Moskowitz, Ooi & Pedersen (2012) e un journal dei trade con
  equity curve giornaliera.

metadata:
  argument-hint: "[ticker or crypto name]"
---

# Stock & Crypto Analysis

## Execution

### Step 1 — Macro always first
```
Call: get_macro_context()
```
Gives VIX, DXY, regime, dynamic weights. Adapt the analysis to the regime.

### Step 2 — Core analysis via MCP (server already running)
```
Call: analyze_stock(ticker="<TICKER>", verbose=true, fetch_news=true, include_options_context=true)
```
Returns: composite_score, verdict, confidence, signal_alignment,
5 dimensions (Wyckoff, VP, PA, Sentiment, Fundamentals) with detail strings,
5 modifiers (MTF, SOT, Squeeze, Earnings, 6-Clue),
11 indicators, sentiment breakdown, flags, pattern, options_context.

### Step 2b — Bali volatility spread (Bali & Hovakimian 2009): solo ranking cross-sectional
```
Call: bali_signals(ticker="<TICKER>")
```

Cosa dice il paper:
- **RVol–IVol**: volatilità realizzata di un mese (rendimenti giornalieri) meno IV ATM a circa 30 giorni.
  Ogni mese il paper ordina **tutto il cross-section** delle azioni in quintili.
  Il portafoglio long-short (quintile alto meno quintile basso) rende circa −0.6% / −0.7% al mese (Table 2).
  La relazione tra RVol–IVol e il rendimento futuro è negativa.
- **CVol–PVol**: IV ATM della call meno IV ATM della put, con lo stesso ordinamento cross-sectional.
  La relazione con il rendimento futuro è positiva. Il paper dà il segno. Questo skill non riporta numeri non verificati.

Regole d'uso:
1. Il segnale è un **percentile nel cross-section** alla stessa data, non il segno del valore di un titolo.
2. IV > RV è lo stato normale. Un RVol–IVol negativo da solo non è "bullish".
3. Usa solo gli estremi: quintile basso o alto del ranking del tuo universo.
4. L'orizzonte è un mese. Il premio è piccolo. Non è un segnale di entrata da solo.
5. Se il tool dà solo un valore assoluto per un titolo, scrivi "Bali: non valutabile (manca il ranking)".
6. Il composite 60/40 non è nel paper. Non usarlo come evidenza.

### Step 2c — Time Series Momentum (Moskowitz, Ooi & Pedersen 2012): solo filtro di trend
```
Call: tsmom_signals(ticker="<TICKER>", lookback_months=12)
```

Cosa dice il paper:
- **Segnale**: segno del rendimento in eccesso degli ultimi 12 mesi, da t−12 a t. Il paper **non** salta l'ultimo mese.
- **Evidenza**: 58 futures su 4 asset class. Il t-stat è positivo per tutti i 58. È significativo al 5% per 52.
- **Sharpe > 1**: vale per il **portafoglio diversificato** dei 58 futures, non per uno strumento.
- **Volatility scaling**: ogni strumento ha un target di 40% annuo, con una stima EWMA della varianza (center of mass 60 giorni).
  Dentro un portafoglio di 58 strumenti, il 40% per strumento dà circa 12% di volatilità del portafoglio.

Regole d'uso:
1. Usa solo il **segno** come filtro di trend. Un segno negativo è un avviso contro un long.
2. **Non usare mai 40% / σ come size di un singolo titolo.** Su un titolo con volatilità 15% darebbe un'esposizione di 2.7×.
3. La size viene dal budget di rischio (`position-management-playbook`, sezione 1), non da TS-MOM.
4. Sui singoli titoli l'evidenza è mista e a livello di portafoglio (Lim, Wang & Yao 2018; Goyal & Jegadeesh 2018).
5. Se il tool salta l'ultimo mese o usa un'altra stima di volatilità, scrivilo come variante del paper.

### Step 3 — Synthesize verdict
Usa il `composite_score` restituito da `analyze_stock`. Il server MCP calcola il composite.
I pesi sono in `mcp/src/trading_mcp/weights_config.py` e le regole di regime in `mcp/src/trading_mcp/analysis/macro.py`. Non ricalcolarli.
Bali e TS-MOM sono una conferma qualitativa. Non ri-pesare a mano i punteggi.

- final_score ≥ 70 → **Long-Term Investment**
- 50-69 → **Short-Term Speculation (Bullish)**
- < 50 → **Avoid / Wait**
- Le soglie non hanno una validazione out-of-sample. Scrivi "verdetto non validato" nel report.
- Se Bali o TS-MOM contraddicono il verdetto, segnalalo come **divergenza** (per esempio "analyze_stock dice bullish, TS-MOM a 12 mesi è negativo").

### Step 4 — Options strategy (if applicable)
```
Call: suggest_options_strategy(ticker="<TICKER>", composite_score=<FINAL_SCORE>, verdict="<FINAL_VERDICT>")
```

Regole:
1. Con un verdetto **Avoid / Wait** non aprire una posizione nuova.
2. Usa solo strutture a **rischio definito**: spread verticali, iron condor, calendar, diagonal, opzioni long.
   Rifiuta una proposta con gambe short nude o con `max_loss` zero o mancante.
3. La size viene dal budget di rischio: max loss della struttura ≤ rischio per trade.
4. Genera il diagramma con `interactive-trade-diagram` ed esegui il suo self-test.

`bakshi_signals` misura il volatility risk premium con i numeri di Bakshi & Kapadia (2003).
Quei numeri vengono da call **delta-hedged sull'indice S&P 500** (1988-1995).
Sui singoli titoli il premio è molto più piccolo (Bakshi & Kapadia 2003b) o assente (Driessen, Maenhout & Vilkov 2009).
- Su un singolo titolo non usare `bakshi_signals` come ragione per vendere premio.
- Su un indice usalo solo come contesto: il risultato del paper è per posizioni delta-hedged, non per opzioni short nude.
- La perdita in dollari è massima ATM. In % del premio è massima OTM. Nessuna delle due è una scelta di strike.

### Step 5 — Risk sizing and journal
1. Calcola la size dal budget di rischio del `position-management-playbook` (rischio per trade, heat, stress).
2. `scripts/dynamic_weights.py` stampa solo i pesi MCP per regime. Non è uno strumento di sizing.
   ```bash
   python scripts/dynamic_weights.py --vix <VIX> --equity-trend up --dxy-trend <trend> --json
   ```
3. Registra ogni trade eseguito nel journal. Prezzo di ingresso e size sono obbligatori.
   ```bash
   python scripts/log_trade.py new --ticker <T> --verdict-file verdict.json --entry-price <fill> --size-pct <% equity>
   python scripts/log_trade.py exit --trade-id <id> --exit-price <fill> --reason <target_1|stop_loss|...>
   python scripts/feedback_loop.py            # equity curve giornaliera, Sharpe, drawdown
   ```
   - Un verdetto Avoid si registra con `--size-pct 0`: è un segnale senza posizione (flat). Il report lo confronta con il movimento del titolo.
   - Il file è `$OPENCODE_SKILLS_DATA_DIR/trade_log.jsonl`, poi `~/Progetti/Github/Data_for_Analysis`, poi `~/.local/share/opencode-skills`.
   - Lo Sharpe usa i rendimenti giornalieri della equity curve (giorni di calendario, √365). Con meno di 30 giorni o meno di 5 giorni con P&L il report scrive "insufficient data".

## Output format
1. Macro context — regime, VIX, dynamic weights
2. **Score + Verdict + Confidence** (% signal alignment). Scrivi "verdetto non validato".
3. **5 Dimensions** — name, score, key detail excerpt
4. **Bali Signals** — percentile cross-sectional, oppure "non valutabile"
5. **TS-MOM** — segno a 12 mesi come filtro di trend
6. **5 Modifiers** — name, score, interpretation
7. **Key risks** — value_trap, vertical_rally, earnings proximity
8. **Entry/Exit** — from options_context VPOC/VAH/VAL, con stop e size dal budget di rischio
9. **Options strategy** — solo a rischio definito, se applicabile

## Crypto
Same flow. Il motore riconosce le crypto e usa i pesi crypto del MCP (`get_weights().crypto`).
I segnali Bali non si applicano alle crypto (mancano opzioni standard sul cross-section).
