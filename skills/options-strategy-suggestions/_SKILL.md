---
name: options-strategy-suggestions
description: >
  Suggests specific option strategies (including Synthetic Long 2:1) based on
  the stock-crypto-analysis unified verdict and IV regime. Integrates
  Options Playbook, Options Course Workbook, Options Crash Course, and
  stock-crypto-analysis. Use when the user asks 'suggerisci strategia opzioni',
  'options strategy', 'cosa fare con le opzioni', or 'cosa fare su [ticker]'.
allowed-tools:
  - read
  - grep
  - websearch
  - task
argument-hint: [ticker, "options on X", "strategia opzioni su X"]
orchestrator:
  parallel: true
  split_by: ticker
  chunk_size: 1
  merge: none
---

# Options Strategy Suggestions

Bridges `stock-crypto-analysis` verdict and `options-*` frameworks to produce actionable option strategy recommendations. Given a unified market verdict (score, outlook, direction) and IV regime, selects the best strategy with full Greeks profile, risk/reward, and exit plan.

## Skill Dependencies

This skill loads and integrates:
- `stock-crypto-analysis` — Unified verdict (Long-Term Invest / Short-Term Spec / Avoid), per-dimension scores, direction
- `options-playbook` — 40 strategies, risk profiles, Greeks, exit rules, strategy index by outlook
- `options-course-workbook` — Trading Matrix (outlook x IV), vertical spreads, delta neutral, adjustments
- `options-crash-course` — Binary Outcome Model, strategy-market fit, risk-first mindset

## Triggers

`suggerisci strategia opzioni`, `options strategy`, `cosa fare con le opzioni`, `suggest option strategy`, `opzioni su [ticker]`, `entrata a sconto`, `synthetic long`, `opzioni [ticker] [scadenza]`, `opzioni [ticker] [mese] [anno]`, `options on [ticker] [expiry]`

## Core Framework — 4 Phases

### Phase 1 — Input (Run or Accept Verdict)

Run `stock-crypto-analysis` on the target ticker, or accept a pre-computed verdict.

Extract:
- **Final Score** (0–100)
- **Verdict**: Long-Term Investment / Short-Term Speculation / Avoid
- **Per-dimension rationales**: Wyckoff, Volume Profile, Price Action, Sentiment, Fondamentali, Crypto-specific
- **Direction**: Bullish / Bearish / Neutral / Volatile
- **Context**: Is the user already in position? Want to enter? Want to exit?

### Phase 2 — IV Regime Assessment

Determine if implied volatility is high, normal, or low:

| Regime | Condition | Implication |
|--------|-----------|-------------|
| **HIGH** | IV > 70° percentile (1yr) | Options expensive → favor sellers |
| **NORMAL** | IV 30°–70° percentile | Options fairly priced → both viable |
| **LOW** | IV < 30° percentile | Options cheap → favor buyers |

If IV percentile not available, use proxy:
- Compare current IV to HV(20). If IV/HV > 1.3 = HIGH, < 0.7 = LOW
- VIX > 30 = HIGH for SPX; VIX < 12 = LOW

### Phase 2b — Momentum Stage Filter & Entry Timing Gate (NUOVO)

**Prima di selezionare la strategia**, determinare in quale fase di momentum si trova il titolo.
Un titolo può avere un verdetto bullish ma essere in una fase di estensione che rende rischiosa
l'entrata in opzioni.

| Momentum Stage | Condizione | Cosa fare |
|---|---|---|
| **Early Stage** | Breakout recente (+5-15% in 30gg), volume in crescita, RSI < 65 | ✅ Entrata consentita — Tutte le strategie applicabili |
| **Mid Stage** | Rally +15-30% in 30-60gg, RSI 65-75, trend sano | ⚠️ Entrata consentita — Size ridotta del 30%, stop più stretti |
| **Late Stage / Exhaustion** | Rally verticale > 20% in < 15gg oppure > 30% in < 30gg | ❌ Bloccare nuove entrate con opzioni. Output: "⚠️ ESTENSIONE — Il titolo è in fase di estensione verticale. Non entrare in opzioni in estensione. Raccomandazione: attendere pullback o consolidamento di almeno 10-15gg." |
| **Distribution** | Prezzo in range stretto dopo rally, volume decrescente, RSI divergente | ⚠️ Solo strategie short premium (credit spread, IC) entro il range. Nessuna long. |
| **No Trend / Chop** | Prezzo tra EMA50-200, RSI 40-60, volume basso | ❌ Nessuna strategia opzioni direzionale. Solo Iron Condor o Calendar. |

**Regola speciale per Synthetic Long 2:1**: Se momentum stage = Mid Stage o Late Stage,
bloccare la raccomandazione. La struttura 2:1 amplifica il downside in estensione.

**Override**: Se il titolo opera in settore benedetto dal Geopolitical Sector Vector, la
soglia Late Stage si allarga: bloccare solo se rally > 30% in < 15gg (invece di 20%).

### Phase 3 — Strategy Selection Matrix

Combine verdict/outlook + IV regime + Momentum Stage to select primary and secondary strategies.

| Outlook (da Verdetto) | IV Regime | Strategia Primaria | Secondaria | DTE Range |
|---|---|---|---|---|
| **Long-Term Invest (70+)**, vuoi entrare | Medio-Alta | **Synthetic Long 2:1** | Cash-Secured Put | ≥ 45 |
| **Long-Term Invest (70+)**, vuoi entrare | Bassa | LEAPS Call | Bull Call Spread | ≥ 365 / ≥ 90 |
| **Long-Term Invest (70+)**, già in posizione | Qualsiasi | Covered Call | Collar | 30–60 |
| **Short-Term Spec Bullish (50-69)** | Bassa | Bull Call Spread | Long Call ATM | 45–60 |
| **Short-Term Spec Bullish (50-69)** | Alta | Bull Put Spread | — | 45 |
| **Short-Term Spec Bearish (30-49)** | Bassa | Bear Put Spread | Long Put ATM | 45–60 |
| **Short-Term Spec Bearish (30-49)** | Alta | Bear Call Spread | — | 45 |
| **Neutral / Range** | Bassa | Long Butterfly | Calendar Spread | 45–60 |
| **Neutral / Range** | Alta | Iron Condor | Short Strangle (hedged) | 45 |
| **Volatile (direction?)** | Bassa + Catalyst | Long Straddle | Long Strangle | 60 |
| **Volatile (direction?)** | Alta | **WAIT** | — | — |
| **Avoid (< 30)** | Qualsiasi | **NO TRADE** | Attesa | — |

**Nota**: Se Momentum Stage = Late Stage / Exhaustion, tutte le strategie con delta positivo (o direzionali bullish) sono bloccate, indipendentemente dal verdetto. Eccezione: settore benedetto dal Geopolitical Sector Vector (soglia estensione più alta).

**Override Geopolitico**: Se l'asset opera in settore benedetto da macro evento geopolitico (es. difesa durante guerra), la finestra per strategie long si allarga: consentite anche in finestra SELECTIVE se score ≥ 75 e Momentum Stage ≤ Mid Stage.

#### Synthetic Long 2:1 — Regole di Attivazione

Si attiva quando TUTTE queste condizioni sono vere:
1. `stock-crypto-analysis` score ≥ 70 (Long-Term Invest)
2. L'utente vuole **entrare a mercato** (non è già in posizione)
3. IV non è nel 1° decile (non estremamente bassa)
4. L'asset è qualcosa che l'utente è **disposto a detenere** (assegnazione non è un problema)
5. Orizzonte minimo **≥ 45 DTE** (consigliato 60–90 per bilanciare premio e rischio gamma)
6. **Momentum Stage ≠ Mid Stage, Late Stage o No Trend** (vedi Phase 2b)

Struttura:
```
Sell 2x Put @ Strike A (OTM, prezzo di entrata desiderato)
Buy  1x Call @ Strike B (OTM o ATM, upside strike)
Both same expiration, ≥ 45 DTE
Obiettivo: netto a CREDITO o costo < long call singola
```
- **Delta**: ~1.5–2.0 (più aggressivo di Synthetic Long 1:1)
- **Theta**: Positivo se ITM o ATM (2x put decay > 1x call decay)
- **Vega**: Negativo (put vega 2x > call vega 1x, favorisce calo IV)
- **Rischio chiave**: Downside 2x sotto strike put. Dimensionare con parsimonia.
- **Assegnazione**: Se assegnato sulle 2 put, chiudere la call OTM per recupero parziale, oppure tenerla per upside futuro.

### Phase 4 — Output Recommendation

For each selected strategy, produce:

```
## 🎯 Strategia: [Nome]
### Perché
- Da stock-crypto-analysis: Score XX% (Verdetto)
- IV Regime: [HIGH/LOW/NORMAL]
- Dimensione guida: [Wyckoff/VolProf/PA/Sentiment/Fondamentali] → score XX → [implicazione]

### Struttura del Trade
- **Direzione**: [Bullish / Bearish / Neutral]
- **Strike**: Buy [Qty]x [Call/Put] @ $XX, Sell [Qty]x [Call/Put] @ $YY
- **Expiration**: [DTE]gg (data)
- **Netto**: [Credito/Debito] $XX
- **Breakeven**: $XX

### Greeks Snapshot
| Greek | Valore | Impatto |
|-------|--------|---------|
| Delta | +X.XX | Direzionalità |
| Gamma | X.XX | Accelerazione |
| Theta | $X.XX/g | Time decay |
| Vega | $X.XX | IV sensitivity |

### Risk / Reward
- **Max Loss**: $XX (%)
- **Max Profit**: $XX (%)
- **Probabilità**: ~XX%
- **Rischio**: [Basso / Medio / Alto]

### Exit Plan
- **Take Profit**: XX% del max profit o [condizione]
- **Stop Loss**: XX% della max loss o prezzo $XX
- **Time Stop**: [DTE]gg senza movimento → chiudi
- **Adjustment**: [Roll, spread adjustment, early assignment gestione]

### Strategia Secondaria
[Nome] — [quando preferirla alla primaria]
```

For Synthetic Long 2:1, add:

```
### Discounted Entry — Parametri Specifici
- **Prezzo di entrata desiderato** (Put Strike A): $XX
- **Upside strike** (Call Strike B): $XX
- **Netto**: [Credito/Debito] $XX
- **Costo medio se assegnato sulle put**: $XX – premio incassato = $XX (sconto vs mercato)
- **Break-even upside**: Strike B + netto debito (o Strike B se a credito)
- **Caso peggiore**: Prezzo a $0 → perdita = 2 × Put Strike A – premio incassato
```

## Chained Execution (from stock-crypto-analysis)

When invoked by `stock-crypto-analysis` (via `market-accumulation-scanner` Auto-Chain
Mode), the unified verdict and all scores are pre-computed. The user may also specify
a **target expiration** (e.g. "Dec 2026", "June 2026", "47 DTE", "Jan 2028").

### Input Format (Chained Mode)

The agent receives:
- `ticker`: symbol (e.g., "IGV")
- `unified_score`: XX (0-100, from stock-crypto-analysis)
- `verdict`: "Long-Term Investment" / "Short-Term Speculation" / "Avoid"
- `direction`: "Bullish" / "Bearish" / "Neutral"
- `per_dimension_scores`: dict of {dimension: score}
- `expiry`: [optional] "Dec 2026", "Jun 18", "45 DTE", etc.

### Phase 1 — Input (Chained)

No need to run `stock-crypto-analysis`. Accept pre-computed values.

**Parse expiry** from user input:

| Input utente | Interpretazione |
|-------------|----------------|
| "Dec 2026" | Terzo venerdì di Dicembre 2026 → 2026-12-18 |
| "Jun 18" | 2026-06-18 |
| "June 2026" | Terzo venerdì di Giugno 2026 → 2026-06-19 |
| "47 DTE" | Oggi + 47 giorni |
| "Jan 2028" | Terzo venerdì di Gennaio 2028 → 2028-01-21 |
| Nessuna scadenza | Usa DTE minima di default (45 per Syn Long 2:1) |

### Phase 2 — IV Regime Assessment

Standard (fetch current IV dal ticker). Se il ticker non ha opzioni liquide,
usa HV(20) come proxy.

### Phase 2b — Momentum Stage Filter (Chained)

Stesso check della modalità standalone: calcola momentum stage dal prezzo recente (via websearch o dati scanner). Se il titolo arriva dallo scanner, usa i dati price action già raccolti per valutare rally velocity.

### Phase 3 — Strategy Selection (Chained)

Usa la Strategy Selection Matrix standard, ma con queste regole aggiuntive:

| Input | Regola |
|-------|--------|
| `expiry` fornito | Se DTE < 45 → avvisa che DTE < min raccomandata. Strategia secondaria se necessario. |
| `expiry` fornito e score ≥ 70 | Synthetic Long 2:1 con expiry = data specificata. Calcola strike come sempre. |
| `expiry` non fornito | Usa DTE ideale per la strategia selezionata (60-90 per Syn Long 2:1) |
| `verdict` = Avoid | Salta — nessuna strategia |
| `verdict` = Short-Term Spec | Bull Put Spread o Bear Call Spread, DTE 30-45 |

### Phase 4 — Output (Chained)

Output ridotto, senza ripetere i dati già mostrati dalle skill precedenti:

```
## 🎯 Strategia Opzioni: [Nome]
**Scadenza**: [data] (XXX DTE) | **IV Regime**: [HIGH/NORMAL/LOW]

### Struttura del Trade
- **Strike**: Buy [Qty]x [Call/Put] @ $XX | Sell [Qty]x [Call/Put] @ $YY
- **Netto**: [Credito/Debito] $XX | **Breakeven**: $XX

### Greeks Snapshot
| Greek | Valore | Impatto |
|-------|--------|---------|
| Delta | X.XX | [direzionalità] |
| Gamma | X.XX | [accelerazione] |
| Theta | $X.XX/g | [time decay] |
| Vega | $X.XX | [IV sensitivity] |

### Risk / Reward
- **Max Loss**: $XX (%) | **Max Profit**: $XX (%) | **Probabilità**: ~XX%
- **Rischio**: [Basso / Medio / Alto]

### Exit Plan
- **TP**: XX% del max profit o [condizione specifica]
- **SL**: XX% della max loss o prezzo $XX
- **Time Stop**: [DTE]gg senza movimento → chiudi
- **Adjustment**: [Roll / spread adjustment / early assignment]

--- 

*Strategia generata da options-strategy-suggestions in Chained Mode*
*Basata su unified verdict score XX dalla catena scanner → stock-crypto-analysis*
```

### DTE Guidelines
| Strategy | Min DTE | Ideal DTE | Reason |
|----------|---------|-----------|--------|
| Synthetic Long 2:1 | 45 | 60–90 | Balance premium vs gamma risk |
| LEAPS Call | 365 | 500+ | Time for thesis to play out |
| Bull/Bear Call Spread | 30 | 45 | Theta decay sweet spot |
| Bull/Bear Put Spread | 30 | 45 | Theta decay sweet spot |
| Iron Condor | 30 | 45 | Theta decay + gamma manageable |
| Long Straddle | 45 | 60 | Avoid gamma explosion <30 DTE |
| Covered Call | 30 | 45 | Monthly income cycle |
| Cash-Secured Put | 30 | 45–60 | Assignment probability management |

### Risk Level Mapping
| Max Loss Profile | Risk Level | Position Sizing |
|-----------------|-----------|-----------------|
| Limited (debit paid) | Basso | 5–10% of capital |
| Limited (spread width) | Medio | 3–7% of capital |
| Substantial (strike – premium) | Alto | 1–3% of capital |
| Unlimited (naked short) | Molto Alto | Avoid unless All-Stars |

### When NOT to Trade
- Verdetto = **Avoid** (score < 30): nessuna strategia
- IV = **HIGH** per strategie long premium (volatility crush risk)
- IV = **LOW** per strategie short premium (premio insufficiente)
- Bid-ask spread > 10% of option price (illiquidità)
- Open interest < 100 per lo strike target
- Earnings announcement entro 7 giorni (IV premium distorce il trade)

## Anti-Patterns
- **Non** suggerire strategie senza verificare la direzione dal verdetto
- **Non** suggerire Synthetic Long 2:1 se score < 70 o IV è al minimo storico o momentum stage ≠ Early Stage
- **Non** omettere exit plan — ogni trade ha un piano di uscita
- **Non** suggerire Long Straddle/Strangle con IV alta (volatility crush garantito)
- **Non** usare DTE < 45 per nessuna strategia short premium (gamma risk)
- **Non** raddoppiare su una posizione in perdita — chiudi e rivaluta
- **Non** ignorare il Momentum Stage prima di consigliare qualsiasi strategia opzioni
- **Non** suggerire entrate con opzioni in titoli con rally verticale >20% in 15gg, indipendentemente dal punteggio fondamentali
