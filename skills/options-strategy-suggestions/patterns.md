# Composite Patterns — Options Strategy Suggestions

Each pattern links a `stock-crypto-analysis` verdict profile + IV regime to a specific option strategy.

---

## 1. Synthetic Long 2:1 — Discounted Entry

**Profilo Verdetto**: Long-Term Invest (score ≥ 70), asset che vuoi detenere, IV non bassa

**Trigger**: Score 75+, Wyckoff accumulazione (B-C) + P-Profile o D-Profile, VPA bullish validation. L'utente vuole entrare a mercato.

**Strategia**: Syntetic Long 2:1
- Sell 2x Put @ Strike A (OTM, prezzo desiderato di entrata)
- Buy 1x Call @ Strike B (OTM, upside strike)
- DTE: 60–90
- Obiettivo netto: credito

**Perché funziona**: Il verdetto long-term dà fiducia sul rialzo futuro. Le 2 put incassano premio abbassando il costo d'ingresso (o generando credito). Se il titolo scende, l'assegnazione è a sconto — era il piano B. Se sale, la call dà upside illimitato.

**Attenzione a**: Non usare se score < 70. Non usare se IV al minimo storico (premio insufficiente). Dimensionare 1-3% del capitale per il rischio 2x downside.

**Esempio**:
- Ticker a $100, score 78 (Long-Term Invest)
- Sell 2x $90 Put @ $3.50 → incassa $700
- Buy 1x $105 Call @ $4.00 → paga $400
- Netto: **$300 credito** (entri gratis!)
- Se assegnato: costo medio $90 – $1.50 = **$88.50/azione**
- Se sale sopra $105: profitto illimitato, hai già incassato $300

---

## 2. LEAPS Call — Long-Term Bullish

**Profilo Verdetto**: Long-Term Invest (score ≥ 70), IV bassa, vuoi entrare

**Trigger**: Score 75+, fondamentali solidi (P/E < 20, revenue growth, insider buying), IV < 30° percentile. L'utente vuole esposizione long senza impegnare capitale per 100 azioni.

**Strategia**: LEAPS Call
- Buy 1x Deep ITM Call (delta ≥ 0.80), 500+ DTE

**Perché funziona**: IV bassa = call economiche. Il verdetto long-term dà orizzonte sufficiente per la tesi. La LEAPS deep ITM si comporta come azioni (delta ~1) ma con 1/5 del capitale.

**Attenzione a**: Non usare se IV è alta (opzioni care). Theta è negativo ma gestibile a 500+ DTE.

**Esempio**:
- Ticker $100, score 82
- Buy $80 Call (delta 0.85), 500 DTE, $25 premium
- Costo: $2,500 vs $10,000 per 100 azioni
- Break-even: $105. Stessa esposizione con 75% meno capitale.

---

## 3. Bull Call Spread — Short-Term Bullish (IV Bassa)

**Profilo Verdetto**: Short-Term Spec Bullish (score 50-69), IV bassa

**Trigger**: Score 55+, Price Action positiva (buildup, proper break, spring), Volume Profile P-Profile. Vuoi entrare con rischio definito.

**Strategia**: Bull Call Spread
- Buy 1x ATM Call + Sell 1x OTM Call
- DTE: 45–60

**Perché funziona**: IV bassa rende le call economiche. Lo spread riduce il costo rispetto a long call nuda. Reward/risk definito.

**Attenzione a**: Max profit limitato. Scegliere strike superiore a 1 deviazione standard dal prezzo per dare spazio al movimento atteso.

---

## 4. Bull Put Spread — Short-Term Bullish (IV Alta)

**Profilo Verdetto**: Short-Term Spec Bullish (score 50-69), IV alta

**Trigger**: Score 55+, sentiment estremo (P/C ratio basso = contrarian bullish), IV > 70° percentile.

**Strategia**: Bull Put Spread
- Sell 1x OTM Put + Buy 1x further OTM Put (credit)
- DTE: 45

**Perché funziona**: IV alta = premi grassi. Il credit spread incassa il premio con rischio definito. Theta lavora a tuo favore. Verdetto bullish dà direzione, IV alta dà entry vantaggiosa.

**Attenzione a**: Risk > reward (vinci piccolo, perdi grande). Probabilità alta ma loss severo se sbagli. Strike short ~1 SD OTM.

---

## 5. Bear Call Spread — Short-Term Bearish (IV Alta)

**Profilo Verdetto**: Short-Term Spec Bearish (score 30-49), IV alta

**Trigger**: Score 35-48, Wyckoff distribuzione (B-C), Upthrust, b-Profile, sentiment rialzista estremo (= contrarian bearish).

**Strategia**: Bear Call Spread
- Sell 1x OTM Call + Buy 1x further OTM Call (credit)
- DTE: 45

**Perché funziona**: Stessa logica del Bull Put ma al ribasso. IV alta = buon premio. Theta positivo.

**Attenzione a**: Rischio unlimited se short call nuda — ma lo spread lo rende definito.

---

## 6. Bear Put Spread — Short-Term Bearish (IV Bassa)

**Profilo Verdetto**: Short-Term Spec Bearish (score 30-49), IV bassa

**Trigger**: Score 35-48, prezzo esteso sopra VAH, upthrust Weis, VPA anomalia (alto volume senza progresso).

**Strategia**: Bear Put Spread
- Buy 1x ATM Put + Sell 1x OTM Put (debit)
- DTE: 45–60

**Perché funziona**: IV bassa = put economiche. Spread riduce il costo. Rischio definito.

---

## 7. Iron Condor — Neutral / Range-Bound (IV Alta)

**Profilo Verdetto**: Short-Term Spec Bearish/Neutral (score 30-49) OPPURE Neutral esplicito, IV alta

**Trigger**: Score 40-55, Volume Profile D-Profile (equilibrio), price action laterale, nessun buildup, nessun pattern Weis chiaro.

**Strategia**: Iron Condor
- Sell OTM Put + Sell OTM Call + Buy further OTM Put + Buy further OTM Call
- Winghe equidistanti, ~1 SD OTM
- DTE: 45

**Perché funziona**: IV alta = credito sostanziale. Range = alta probabilità di successo (~68% con 1 SD). Quattro gambe ma rischio definito.

**Attenzione a**: Gamma risk esplode sotto 20 DTE. Chiudi a 50% del max profit. Non tenere attraverso earnings.

---

## 8. Long Butterfly — Neutral / Range-Bound (IV Bassa)

**Profilo Verdetto**: Neutrale, IV bassa

**Trigger**: Score 40-55, prezzo incastrato tra VAH e VAL, cluster Weis, Volman buildup a S/R.

**Strategia**: Long Butterfly
- Buy 1x ITM Call + Sell 2x ATM Call + Buy 1x OTM Call
- DTE: 45–60

**Perché funziona**: Costo basso (debito). Profitto massimo se il titolo pinna allo strike centrale. IV bassa = butterfly economica.

**Attenzione a**: Vincita solo se il titolo è molto vicino allo strike centrale a scadenza. Probabilità bassa, ma R/R alto.

---

## 9. Covered Call — Income su Posizione Esistente

**Profilo Verdetto**: Long-Term Invest (score ≥ 70), già in posizione

**Trigger**: Già possiedi l'asset. Vuoi generare income. Neutrale-moderatamente bullish.

**Strategia**: Covered Call
- Own 100 shares + Sell 1x OTM Call
- DTE: 30–45
- Strike: ~0.30 delta (alta probabilità di OTM)

**Perché funziona**: Genera income mensile su posizione long. Se IV è alta, il premio è ancora più ricco. Se il titolo sale sopra lo strike, viene chiamato via al tuo target di vendita.

**Attenzione a**: Up-side limitato. Se il titolo sale molto, perdi quei guadagni. Valuta il roll up invece di lasciar chiamare le azioni.

---

## 10. Long Straddle — Volatile / Event-Driven (IV Bassa)

**Profilo Verdetto**: Qualsiasi, ma con catalyst imminente (earnings, FDA, IPO, halving). IV bassa.

**Trigger**: Earnings o evento noto entro 2 settimane. IV < 30° percentile. Titolo ha fatto movimenti > 2x del premio totale negli ultimi 4 earnings.

**Strategia**: Long Straddle
- Buy 1x ATM Call + Buy 1x ATM Put (same strike, same expiry)
- DTE: 60 (per dare tempo al catalyst + decay gestibile)

**Perché funziona**: IV bassa = premio contenuto. Catalyst = asimmetria (unlimited upside, rischio limitato al premio).

**Attenzione a**: Theta è doppio negativo. Assicurati che il catalyst sia abbastanza vicino (≤ 2 settimane) da giustificare il costo. Se IV è ALTA, **non** usare Straddle — usa Spread.

---

## 11. Cash-Secured Put — Buy the Dip

**Profilo Verdetto**: Long-Term Invest (score ≥ 70), vuoi comprare a sconto, IV non bassa

**Trigger**: Score 75+, vuoi entrare ma il prezzo è sopra il tuo target. Preferisci aspettare un ritracciamento e farti pagare per l'attesa.

**Strategia**: Cash-Secured Put
- Sell 1x Put @ Strike A (prezzo di acquisto desiderato)
- DTE: 45–60
- Cash collateral: Strike × 100

**Perché funziona**: Se il titolo scende sotto strike → compri a sconto (strike – premio). Se resta sopra → tieni il premio e riprovi. Perfetto per chi è long-term bullish ma vuole un entry migliore.

**Attenzione a**: Devi avere il cash per comprare 100 azioni se assegnato. Se il titolo crolla, compri a un prezzo che ora è sopra il mercato (ma eri disposto a pagarlo).

---

## 12. Collar — Proteggi Posizione Esistente

**Profilo Verdetto**: Long-Term Invest (score ≥ 70), già in posizione con gain, vuoi proteggere senza vendere

**Trigger**: Score alto, hai gain non realizzati, sei nervous su short-term ma bullish long-term.

**Strategia**: Collar
- Own 100 shares
- Buy 1x OTM Put (protezione, strike ~ -10%)
- Sell 1x OTM Call (finanzia la put, strike ~ +10-15%)
- DTE: 60–90

**Perché funziona**: Protegge il downside senza costo (la call finanzia la put). Blocca i gain in un range. Nessun costo upfront.

**Attenzione a**: Up-side limitato. Se il titolo sale sopra la call, le tue azioni vengono chiamate via. Scegli strike che riflettono il tuo target di uscita.

---

## 13. Short Strangle (Hedged) — High IV Neutral

**Profilo Verdetto**: Neutrale (score 40-55), IV Molto Alta (> 85° percentile)

**Trigger**: IV estremamente alta (VIX > 30, o IV > 90° percentile). Range-bound. Volume Profile D-profile.

**Strategia**: Short Strangle con hedge
- Sell 1x OTM Put @ 1.5 SD
- Sell 1x OTM Call @ 1.5 SD
- DTE: 30–45
- Hedge: buy 1x wings estrema per definire il rischio (→ Iron Condor)

**Nota**: Preferisci Iron Condor (rischio definito) a Short Strangle nudo. Lo Short Strangle è solo per All-Stars.

**Perché funziona**: IV massima = premio massimo. Theta positivo. Se IV cala (mean reversion), guadagno extra da vega.

**Attenzione a**: Gamma risk letale < 20 DTE. Chiudi prima. Vedi l'Iron Condor come alternativa a rischio definito.
