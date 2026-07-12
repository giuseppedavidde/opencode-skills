---
name: stock-crypto-analysis
version: "2.1"
description: >
  Deep single-stock/crypto analysis via trading MCP, arricchita con i segnali
  di volatility spread da Bali & Hovakimian (2009): RVol–IVol (volatility risk
  premium) e CVol–PVol (jump risk).
allowed-tools:
  - read
  - bash
  - task
  - websearch
argument-hint: [ticker or crypto name]
---

# Stock & Crypto Analysis

## Execution

### Step 1 — Macro always first
```
Call: get_macro_context()
```
Gives VIX, DXY, regime, dynamic weights. Adapt analysis to the regime.

### Step 2 — Core analysis via MCP (server already running)
```
Call: analyze_stock(ticker="<TICKER>", verbose=true, fetch_news=true, include_options_context=true)
```
Returns: composite_score, verdict, confidence, signal_alignment,
5 dimensions (Wyckoff, VP, PA, Sentiment, Fundamentals) with detail strings,
5 modifiers (MTF, SOT, Squeeze, Earnings, 6-Clue),
11 indicators, sentiment breakdown, flags, pattern, options_context.

### Step 2b — Bali volatility spread signals (Bali & Hovakimian 2009)
Dopo `analyze_stock`, arricchisci con i 2 segnali cross-sectional da opzioni:

```bash
source /tmp/opencode/.venv-quantmind/bin/activate
python3 ~/.config/opencode/skills/quant-mind-skill/bali_signals.py <TICKER> --json
```

Questo calcola:
- **RVol–IVol spread**: RV30gg - ATM straddle IV. Negativo → volatility risk premium positivo → bullish.
  Premium atteso: −0.63%/−0.73% mese per portafoglio long-short.
  Fonte: Bali & Hovakimian (2009), Table 2.
- **CVol–PVol spread**: Call ATM IV - Put ATM IV. Positivo → jump risk positivo → bullish.
  Premium atteso: +1.05%/+1.49% mese.
  Fonte: Bali & Hovakimian (2009), Table 3.

Output JSON con scores 0-100 e direzione combinata.

### Step 2c — Time Series Momentum (Moskowitz, Ooi & Pedersen 2012)
Dopo `analyze_stock`, arricchisci con il TS-MOM signal:

```bash
source /tmp/opencode/.venv-quantmind/bin/activate
python3 ~/.config/opencode/skills/quant-mind-skill/tsmom_signals.py <TICKER> --lookback 12 --json
```

Questo calcola:
- **TS-MOM signal**: sign(return_{t-12:t-1}) — segno del rendimento cumulato degli ultimi 12 mesi (escluso ultimo mese).
  Metodologia: Moskowitz, Ooi & Pedersen (2012), JFE.
- **Score 0-100**: 0 = massimo bearish (forte trend down), 100 = massimo bullish (forte trend up).
- **Position sizing**: volatility scaling con target 40% annuo (EWMA vol 60gg).
- **Sharpe lookback**: Sharpe ratio del trend negli ultimi 12 mesi.

Risultato empirico del paper: Sharpe ratio > 1.0 su portafoglio diversificato cross-asset,
universale in 58 futures su 4 asset class.

### Step 3 — Synthesize verdict (con Bali + TS-MOM signals)
Fondi il `composite_score` di analyze_stock con i segnali Bali e TS-MOM:

```
Pesi aggiornati:
  analyze_stock score:    60%
  Bali composite:         20%
  TS-MOM score:           20%
  
  final_score = composite_score × 0.60 + bali_composite × 0.20 + mom_score × 0.20
```

- final_score ≥ 70 → **Long-Term Investment**
- 50-69 → **Short-Term Speculation (Bullish)**
- < 50 → **Avoid / Wait**
- Se Bali è in forte contrasto con il verdict principale, segnalalo come
  **divergenza** (es. "analyze_stock dice bullish ma RVol–IVol è negativo")

### Step 4 — Options strategy (if applicable)
```
Call: suggest_options_strategy(ticker="<TICKER>", composite_score=<FINAL_SCORE>, verdict="<FINAL_VERDICT>")
```

Prima di suggerire la strategia, arricchisci con Bakshi & Kapadia VRP signals:

```bash
source /tmp/opencode/.venv-quantmind/bin/activate
python3 ~/.config/opencode/skills/quant-mind-skill/bakshi_kapadia_signals.py <TICKER> --json
```

Questo calcola:
- **VRP magnitude**: percentuale del premio attribuibile a volatility risk premium
- **Expected P&L per strike**: profitto atteso del venditore per ogni strike ATM/OTM/ITM
- **Optimal strike selection**: qual è lo strike migliore per vendita premium
- **Timing**: se l'IV corrente favorisce la vendita o l'acquisto di opzioni
- **Dispersion trading**: suggerimenti per dispersion strategies

Se il segnale Bali è estremo (score > 80 o < 20) o Bakshi mostra VRP alto, considera:
- **RVol << IVol** (Bali bullish) + **VRP alto** (Bakshi): short puts / put credit spread
- **RVol >> IVol** (Bali bearish) + **VRP basso**: long puts / call credit spread
- **CVol >> PVol** (jump risk up): bullish strategies con gestione dello skew
- **ATM strike** (da Bakshi): vega massimo = massimo VRP catturabile, massimo rischio
- **OTM 15-20%** (da Bakshi): vega ridotto = VRP minore ma rischio controllato

### Step 5 — Risk sizing (optional, if user wants entry plan)
```bash
python scripts/dynamic_weights.py --vix <from macro> --dxy-trend <from macro> --json
```

## Output format
1. Macro context — regime, VIX, dynamic weights
2. **Score + Verdict + Confidence** (% signal alignment, con Bali fuso)
3. **5 Dimensions** — name, score, key detail excerpt
4. **Bali Signals** — RVol–IVol spread, CVol–PVol spread, scores, direction
5. **5 Modifiers** — name, score, interpretation
6. **Key risks** — value_trap, vertical_rally, earnings proximity
7. **Entry/Exit** — from options_context VPOC/VAH/VAL
8. **Options strategy** — if applicable

## Crypto
Same flow. Engine auto-detects and adjusts weights (Wyckoff 25%, VP 25%, PA 20%, Crypto APC 30%).
I segnali Bali non si applicano al crypto (mancano opzioni standard).
