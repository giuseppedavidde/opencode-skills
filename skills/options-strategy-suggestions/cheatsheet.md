# Cheatsheet — Options Strategy Suggestions

## Strategy Selection Matrix (Outlook × IV)

| Outlook | IV Low | IV High |
|---------|--------|---------|
| **Long-Term Invest (70+)**, vuoi entrare | LEAPS Call / Bull Call Spread | **Synthetic Long 2:1** / Cash-Secured Put |
| **Long-Term Invest (70+)**, già in posizione | Covered Call | Covered Call (IV alta = buon premio) |
| **Short-Term Spec Bullish (50-69)** | Bull Call Spread / Long Call ATM | Bull Put Spread |
| **Short-Term Spec Bearish (30-49)** | Bear Put Spread / Long Put ATM | Bear Call Spread |
| **Neutral / Range** | Long Butterfly / Calendar | Iron Condor / Short Strangle |
| **Volatile (direction?)** | Long Straddle / Long Strangle | **WAIT** |
| **Avoid (< 30)** | **NO TRADE** | **NO TRADE** |

## Synthetic Long 2:1 Quick Reference

| Parameter | Rule |
|-----------|------|
| Structure | Sell 2x Put + Buy 1x Call (stessa expiry) |
| Min DTE | 45 (consigliato 60–90) |
| Score needed | ≥ 70 (Long-Term Invest) |
| IV needed | Non nel 1° decile |
| Obiettivo | Netto a credito o costo < long call singola |
| Net delta | ~1.5–2.0 |
| Theta | Positivo (se ATM/ITM) |
| Vega | Negativo (beneficia di calo IV) |
| Downside risk | 2x Put Strike – premio (significativo) |
| Assegnazione | OK — entri a sconto sulle 2 put. Chiudi la call. |

### Formula Netto
```
Netto = Call premium ricevuto (short, negativo)?? 
Wait: 

Netto = (Premio incassato sulle 2 put) - (Premio pagato sulla call)
```
- Netto positivo = **Credito** (entri gratis con premio extra)
- Netto negativo = **Debito** (costo ridotto rispetto a comprare la call sola)

### Costo Medio di Assegnazione
```
Costo medio per azione = Strike Put - (Netto ricevuto / 2)
```
Esempio: Put Strike $100, Netto credito $200 → costo medio = $100 - ($200/200sh) = $99/sh

## IV Regime Rules

| Regime | Threshold | Cosa fare |
|--------|-----------|-----------|
| **EXTREME LOW** | IV < 10° percentile | Compra premium (call/put/straddle) |
| **LOW** | IV 10°–30° percentile | Favorisci debit spreads, long calls/puts |
| **NORMAL** | IV 30°–70° percentile | Entrambi i lati validi |
| **HIGH** | IV 70°–90° percentile | Favorisci credit spreads, short premium |
| **EXTREME HIGH** | IV > 90° percentile | Vendi premium aggressivo (iron condor, short strangle hedged) |

## DTE Guidelines

| Strategy | Min | Ideal | Motivo |
|----------|-----|-------|--------|
| Synthetic Long 2:1 | 45 | 60–90 | Bilanciare premio e gamma risk |
| LEAPS Call | 365 | 500+ | Tempo per la tesi |
| Bull/Bear Call Spread | 30 | 45 | Theta decay ottimale |
| Bull/Bear Put Spread | 30 | 45 | Theta decay ottimale |
| Iron Condor | 30 | 45 | Gamma risk gestibile |
| Long Straddle | 45 | 60 | Evitare gamma explosion |
| Covered Call | 30 | 45 | Ciclo mensile |
| Cash-Secured Put | 30 | 45–60 | Probabilità assegnazione |

## Risk per Strategy

| Strategy | Max Loss | Risk Level | Size Limit |
|----------|----------|------------|------------|
| Syntetic Long 2:1 | 2× Put Strike – premio | Alto | 1–3% |
| LEAPS Call | Premium pagato | Medio | 5–10% |
| Bull/Bear Call Spread | Net debit | Basso | 5–10% |
| Bull/Bear Put Spread | Width – credit | Basso | 5–10% |
| Iron Condor | Width – credit | Basso | 5–10% |
| Long Butterfly | Net debit | Basso | 3–7% |
| Long Straddle | Premium totale | Medio | 3–7% |
| Covered Call | Stock loss – premium | Medio | Posizione esistente |
| Cash-Secured Put | Strike – premium | Medio | 3–7% |
| Short Call/Put naked | Illimitato / Strike | Molto Alto | **Evita** |

## Exit Rules Quick Reference

| Strategy | Take Profit | Stop Loss |
|----------|-------------|-----------|
| Synthetic Long 2:1 | Call +30% o put scadute 50% | Prezzo sotto put strike – 1 SD |
| LEAPS Call | +50–100% | -25% o tesi invalidata |
| Bull Call Spread | 75–100% of spread width | 100% of debit (scadenza) |
| Bull Put Spread | 50% of credit ricevuto | Width = stop |
| Bear Call Spread | 50% of credit ricevuto | Width = stop |
| Iron Condor | 50% of credit | 1× – 2× credit |
| Long Straddle | +50% after vol expansion | -50% o IV crush |
| Covered Call | Call scade OTM o stock chiamato | Stock stop-loss |
| Cash-Secured Put | Put scade OTM (keep premium) | Assegnazione (ok se voluto) |

## Execution Checklist

- [ ] Run `stock-crypto-analysis` → ottieni score + verdetto
- [ ] Check IV percentile → determina regime (High/Low/Normal)
- [ ] L'utente vuole entrare, è già in posizione, o vuole uscire?
- [ ] Consulta la matrice → seleziona strategia primaria + secondaria
- [ ] Verifica liquidità (OI > 100 per strike target)
- [ ] Calcola Greeks stimati
- [ ] Definisci exit plan (TP, SL, time stop, adjustment)
- [ ] Dimensiona posizione (1–10% di capitale in base al rischio)
- [ ] Produci output strutturato
