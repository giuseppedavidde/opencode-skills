---
name: momentum-breakout-guardrail
description: >
  Guardrail comportamentale contro il bias mean-reversion sui titoli in momentum.
  Previene il verdict "bullish ma cauto" su titoli in trend forte (es. HPE @ $64.5
  con call wall $65) interpretando un call wall GEX come tetto. Carica quando
  l'utente chiede di: titolo in momentum, titolo in trend, breakout, rottura di
  resistenza, sta per partire, GEX, call wall, put wall, gamma flip, long-gamma,
  short-gamma, posizione vs resistenza, verdict cauto su titolo forte, HPE-like,
  analisi di un titolo che ha già corso molto, "lo compro o aspetto".
allowed-tools: [read, grep, bash]
metadata:
  argument-hint: "[ticker] (oppure 'checklist' per la procedura di verdict)"
---

# Momentum Breakout Guardrail

Playbook operativo anti-bias. Nasce dal caso **HPE** (Fase 1–2–3): il sistema
diede un verdict **"bullish ma cauto"** a $64.5, trattando il call wall GEX $65
come resistenza/magnete in regime long-gamma. HPE esplose **+8% in una seduta**,
rompendo $65.5 → $70. L'errore: **mean-reversion applicata a un titolo in momentum**.

Questo playbook **NON promette profitti** (vedi §6 Onestà epistemica). È un
**guardrail comportamentale + checklist di processo**.

---

## 1. Regola d'oro — Momentum Override 🥇

> **Se un titolo è in trend/momentum forte, NON applicare logica mean-reversion.**

Criterio "in momentum" (tutti o quasi):
- `dist_sma200_pct > 0` (prezzo sopra SMA200)
- `ret_12m > 0` (rendimento 12 mesi positivo)
- `is_extended = true` oppure RSI alto

In questo profilo:
- L'estensione **NON è un segnale di fade**. "Ipercomprato" ≠ "da vendere".
- Il **call wall GEX NON è un tetto**: in **long-gamma** è un **ATTRATTORE/pin**
  (il dealer hedging tira il prezzo verso gli strike ad alta gamma), non una
  resistenza meccanica.
- Vietato emettere verdict ribassista/mean-reversion basato **solo** su
  "overbought", RSI alto, o vicinanza a un muro.

---

## 2. Processo operativo (obbligatorio prima di ogni verdict)

Prima di esprimere **qualsiasi** giudizio su un titolo in momentum:

```
Step 0 — Call: get_macro_context()        # regime di mercato (sempre primo)
Step 1 — Call: breakout_context(ticker="<TICKER>")   # SEMPRE, non opzionale
Step 2 — Call: analyze_stock(ticker="<TICKER>")      # contesto dimensionale
```

`breakout_context(ticker, include_gex=True)` restituisce i blocchi:

| Blocco | Campi chiave |
|---|---|
| `momentum` | `ret_12m`, `tsmom_signal`, `dist_sma200_pct`, `dist_sma50_pct`, `rsi14`, `atr14`, `is_extended`, `extension_atr_above_sma50` |
| `bias_guard` | `{flag, reason, momentum_strength}` |
| `breakout_triggers` | `{lookback_days: 252, level, volume_avg20, volume_mult: 2.0, volume_today, fired, confirmations: {close_above_level, volume_ok, above_sma200}, status}` |
| `gex` | `{regime, call_wall, put_wall, gamma_flip, wall_interpretation, available}` |
| `risk` | `{suggested_stop = entry − 2.0×ATR14, atr, atr_mult, holding_days_preferred: 120}` |
| `evidence` | `{source, edge_certified: false, caveats}` |

**Regola hard**: se `bias_guard.flag = true`, **NON** emettere verdict
ribassista/mean-reversion **senza una motivazione esplicita e più forte**
(fondamentale rotto, earnings miss, distribuzione VPA confermata su volume,
regime macro avverso documentato). La cauzione di default è **momentum-following**,
non fade.

---

## 3. Interpretazione GEX regime-aware

Usa **sempre** `gex.regime` + `gex.wall_interpretation` (il campo è già
regime-aware, non rileggerlo a mano come resistenza):

| Regime | Call wall | Implicazione operativa |
|---|---|---|
| **long_gamma** | **ATTRATTORE** (pin) | Prezzo magnetizzato verso il wall. Rottura = accelerazione. **Non è un tetto.** |
| **short_gamma** | **Checkpoint**, può essere rotto e superato | Il dealer hedging **amplifica** i movimenti. Rottura = trend in accelerazione. |
| **neutral** | Resistenza ordinaria in range | Nessun effetto magnete meccanico. Contesto neutro. |
| **unavailable** | — | Nessuna interpretazione. Non inventare un tetto. |

**Rottura accelerativa**: quando il prezzo supera il call wall in regime
long-gamma, il pin si sposta al wall successivo → movimento rapido. In
short-gamma la rottura è già amplificata dal hedging.

`analyze_gex(ticker)` è il tool sottostante per il dettaglio GEX puro, se serve
approfondire oltre l'overlay di `breakout_context`.

---

## 4. Trigger di breakout e gestione

**Definizione trigger** (`breakout_triggers`):
- Chiusura **sopra il livello di 252 giorni** (massimo rolling)
- **Volume > 2.0×** la media 20 giorni (`volume_mult`)
- Prezzo **sopra SMA200**

I tre booleani vivono in `confirmations`. `fired = true` richiede **tutte** le
condizioni. `status` è la stringa di stato. **Condizionale, NON certificato** (§6).

**Gestione**:
- **Stop** = entry − **2.0 × ATR14** (`risk.suggested_stop`)
- **Orizzonte preferito** = **120 giorni** (`risk.holding_days_preferred`)
- Sizing coerente con l'ATR (rischio per trade costante in unità di ATR)

**Check anti-chasing** (obbligatorio dopo un grande movimento):
- Dopo un rialzo violento l'**IV è cara** → le opzioni lunghe sono costose.
- Preferire **strutture a spread** (debit spread, call spread) invece di long
  call naked, oppure **attendere un pullback** verso SMA20/SMA50.
- Non inseguire il prezzo con entry a mercato dopo il gap.

---

## 5. Formato output consigliato (verdict a valle)

Ogni verdict su titolo in momentum DEVE riportare, in quest'ordine:

1. **Bias check** — `bias_guard.flag` + `momentum_strength`; se flag=true,
   dichiarare esplicitamente che la logica mean-reversion è **esclusa**.
2. **Momentum snapshot** — `ret_12m`, `dist_sma200_pct`, `rsi14`, `is_extended`.
3. **Trigger status** — `level`, `volume_today` vs `volume_avg20`×2, i 3
   `confirmations`, `fired`, `status`.
4. **GEX** — `regime`, `call_wall`, `put_wall`, `gamma_flip`, `wall_interpretation`
   (mai riscrivere il wall come "tetto" in long-gamma).
5. **Risk** — `suggested_stop`, `atr`, `holding_days_preferred`.
6. **Anti-chasing** — IV/struttura consigliata; se dopo un run, segnalare il
   rischio di entry tardiva.
7. **Disclaimer onestà** — citare `evidence.edge_certified = false` (§6).

---

## 6. Onestà epistemica (OBBLIGATORIO)

- `evidence.edge_certified` è **sempre `false`**. La Fase 1 ha provato che
  **nessuna configurazione di breakout grezza batte il baseline in-sample**.
- La regola di breakout **NON è un edge dimostrato**: è un **framework di processo**.
- **Caveats da citare**: survivorship bias, data-mining bias, campione in-sample,
  nessuna validazione out-of-sample.
- **VIETATO** presentare questo playbook come garanzia di profitto, aspettativa di
  win-rate, o "sistema che funziona". È un **guardrail contro un bias noto**.

---

## 7. Esempio negativo — il caso HPE

**Cosa è stato fatto (SBAGLIATO)**:
- HPE a $64.5, chiaramente in momentum (sopra SMA200, ret_12m > 0).
- Letto il call wall GEX $65 come **resistenza/magnete**.
- Verdict: **"bullish ma cauto"** → bias mean-reversion su titolo in trend.
- Ignorato che in **long-gamma il call wall è un attrattore**, non un tetto.

**Cosa è successo**: HPE **+8% in una seduta**, rottura $65.5 → **$70**. Il
"tetto" è stato sfondato con accelerazione.

**Cosa si doveva fare**:
1. Chiamare `breakout_context("HPE")` → `bias_guard.flag = true`.
2. Leggere `gex.wall_interpretation`: in long-gamma il wall è **attrattore**.
3. Verdict **momentum-following** (o neutro), **non** mean-reversion.
4. Gestione: stop = entry − 2×ATR14, orizzonte 120gg, no fade del wall.
5. Disclaimer: `edge_certified = false`, nessuna garanzia.

---

## Riferimenti incrociati

- **stock-crypto-analysis**: pipeline `analyze_stock` + Bali + TS-MOM
- **options-analysis**: IV, greche, struttura a spread post-run
- **options-strategy-suggestions**: scelta strategia data la verdict
- **position-management-playbook**: gestione della posizione già aperta
- **evidence-based-technical-analysis**: data-mining bias, Reality Check
- **way-of-the-turtle**: trend following, stop e position sizing
- **volume-price-analysis**: conferma volume della rottura
