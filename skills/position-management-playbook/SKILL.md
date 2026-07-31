---
name: position-management-playbook
description: "Gestione attiva di posizioni in difficoltà: exit ladder, rolling, protezione downside, disciplina documentale, verifica incrociata dati, qualificazione VPA/Wyckoff dei rimbalzi, caveat volumi intraday. Carica quando l'utente chiede: posizione scomoda, uscire, exit, gestione posizione, position repair, chiudere, roll, dead cat, exit ladder, scala di uscita, riparare, fix this, cosa fare con questa posizione, coprire, hedge."
allowed-tools: [read, grep, bash, webfetch]
argument-hint: [topic (discipline, scenario, vpa, ladder, trigger, checklist, metrics)]
---

# Position Management Playbook

Framework operativo distillato da sessioni reali di gestione attiva su DRAM e LHX.
Non è teoria: ogni regola nasce da una decisione presa sul campo con soldi veri.

---

## 1. Disciplina del file posizioni

Ogni posizione DEVE avere un file markdown con:

```
# TICKER Position — Riepilogo Completo
Ultimo aggiornamento: DATA, TICKER @ $PREZZO

## Posizione di partenza (strategia originale)
| Leg | Strike | Scadenza | Qty | Prezzo entry | Note |

## Cronologia di TUTTE le operazioni
#1 — APERTURA (data)
#2 — ROLL/CHIUSURA (data, prezzo sottostante)
...

## Posizione attuale
| Leg | Strike | Scadenza | Qty | Costo base | Valore attuale |

## P&L (REALIZZATO + UNREALIZED separati)
## Numeri chiave (delta, gamma, theta, vega, breakeven, max loss)
## Eventi critici (earnings, IPO, catalyst)
## Gestione in corso (scenari 🟢🟡🔴🚨 con livelli di prezzo)
```

**Regola d'oro**: aggiornare SEMPRE dopo ogni operazione. Confrontare il P&L netto con la max loss della strategia originale — è la metrica di successo della gestione attiva.

Esempio LHX: strategia originale Bull Call Spread con max loss $947. Dopo 3 roll/chiusure di short call, perdita netta ridotta a ~$200. **Risultato: −79% di loss evitata.**

---

## 2. Quadro scenario-based PRIMA di agire

Mai decidere "a sentimento". Definire in anticipo:

| Scenario | Colore | Condizione | Azione |
|---|---|---|---|
| Ottimale | 🟢 | Prezzo > X, volume > YM, VPA rialzista | Tieni / aggiungi |
| Monitoraggio | 🟡 | Prezzo tra X e Y, volume normale | Non toccare, theta lavora |
| Attenzione | 🔴 | Prezzo < Z, volume in aumento su rossa | Prepara exit/hedge |
| Emergenza | 🚨 | Prezzo < W, VPA distributiva, gap down | Esegui protezione/stop |

Ogni scenario DEVE avere:
- **Livello di prezzo esplicito** (es. "chiude sotto $265")
- **Condizione di volume** (es. "con volume > 1.5x la media 20gg")
- **Azione predefinita** (non "valutare" — ma "vendere X", "rollare Y", "comprare put Z")

---

## 3. Caveat volumi intraday 🔥

**Lezione DRAM (31.07.2026)**: 70M di volume a metà sessione sembravano "crollo dei volumi" (giorno prima: 152M). Proiezione lineare: 140M — in realtà il finale fu 99M. Il volume NON è lineare nell'arco della giornata.

**Regole**:
- I volumi a metà sessione sono PARZIALI. Non si possono confrontare raw con il giorno prima.
- Proiettare: `volume_ora × (ore_totali_session / ore_trascorse)` — ma con cautela: l'ultima ora ha spesso più volume.
- Per decisioni intraday, usare il **volume relativo alla stessa ora** del giorno precedente, non il totale.
- Se possibile, **aspettare la chiusura** prima di decisioni basate sul volume.

---

## 4. Verifica incrociata dei dati

yfinance NON è infallibile. Volumi, prezzi, e dati di opzioni possono differire da fonti più dirette.

**Checklist**:
- [ ] Prezzo e volume: confrontare yfinance con stockanalysis.com, Yahoo Finance web, o MarketWatch
- [ ] Opzioni: bid/ask reali dal broker, non mid teorico
- [ ] Earnings date: MAI da `earnings_surprise` di yfinance — usare Benzinga o Nasdaq.com
- [ ] Se c'è discrepanza >2% su volumi o >0.5% su prezzi: **approfondire prima di agire**

---

## 5. VPA/Wyckoff per qualificare i rimbalzi

Non tutti i rimbalzi sono uguali. Distinguere accumulazione reale da dead cat bounce:

| Pattern | Volume | Closing | Significato | Azione |
|---|---|---|---|---|
| Marubozu verde | >1.5x media | Sul massimo | Domanda genuina (accumulazione) | Tieni / aggiungi |
| Candela verde con ombra sup. lunga | > media | Sotto il max | Venditori attivi in area | Cautela |
| Candela rossa con volume alto | >1.5x media | Sul minimo | Distribuzione (selling pressure) | Riduci / esci |
| Rimbalzo su volume in calo | < media | Qualsiasi | Dead cat bounce (no domanda) | NON comprare |
| Doji su volume alto | > media | Corpo piccolo | Indecisione, battaglia in corso | Aspetta conferma |
| Inside day dopo candela ampia | < media | — | Pausa / assorbimento | Neutro, monitora |

**Regola VPA**: il volume DEVE confermare il movimento del prezzo. Prezzo su senza volume = falso segnale. Prezzo giù con volume = pressione reale.

---

## 6. Exit Ladder (lezione LHX) 🔑

Quando una posizione long call/put è in perdita, costruire la scala di uscita:

### Formula
```
P&L Totale = P&L Realizzato + (Valore Opzione × 100 − Costo Entry)
```

### Procedura
1. Calcolare il **P&L realizzato** cumulativo da tutte le leg chiuse
2. Per ogni target di P&L totale (max loss, −50%, breakeven, +10%, +25%...), calcolare il **valore dell'opzione necessario**: `Call_Needed = (Target_P&L − Realized + Costo_Entry) / 100`
3. Usare Black-Scholes (o la chain reale) per mappare **valore opzione → prezzo sottostante** a 2-3 orizzonti temporali (oggi, +60gg, +120gg)
4. Presentare come tabella:

| P&L Target | Call $ | Spot Oggi (DTE=X) | Spot +60gg | Spot +120gg |
|---|---:|---:|---:|---:|---:|
| Max Loss | 0,00 | — | — | — |
| −$XXX (oggi) | X,XX | $XXX | $XXX | $XXX |
| **$0 BREAKEVEN** | **X,XX** | **$XXX** | **$XXX** | **$XXX** |
| +$XXX | X,XX | $XXX | $XXX | $XXX |

### Trigger di uscita
| Zona | Condizione | Azione |
|---|---|---|
| 🟡 **Zona decisionale** | Spot a −2% dal breakeven | Prepara ordine limite |
| 🟢 **Zona pari** | Spot al breakeven o +1% | Chiudi in pari, non essere avido |
| 🚀 **Zona profitto** | Spot al target +10%/+25% | Chiudi, hai recuperato |

### Principio chiave
> **Il theta rema contro**. Ogni mese che passa senza movimento del sottostante, il breakeven si allontana. La tabella a 3 orizzonti serve proprio a mostrare questo deterioramento. Se lo spot è a −2% dal breakeven OGGI, chiudi. Se aspetti 60 giorni, il breakeven sarà già scappato a +5%.

---

## 7. Trigger di protezione

Prima che il dolore arrivi, definire:

### Copertura (hedge)
- **Livello**: prezzo sottostante sotto il quale comprare protezione
- **Strumento**: put spread, put semplice, collar
- **Costo max**: non superare il 20-30% del premio incassato o del P&L realizzato
- **Esempio DRAM**: comprare put spread quando il sottostante rompe un supporto chiave con volume

### Stop loss su opzioni
- Non usare stop loss di mercato su opzioni (spread bid/ask killer)
- Usare **price alert** + decisione manuale
- Per le short: **riacquistare se il sottostante supera un livello tecnico chiave** (non se l'opzione sale del X%)
- Per le long: **vendere se il valore temporale residuo < 10% del premio pagato** e il sottostante non si è mosso

---

## 8. Checklist operativa (quando una posizione è scomoda)

Eseguire in ordine, ogni volta:

1. **[ ] Aggiorna il file posizione** con P&L realizzato e unrealized corrente
2. **[ ] Confronta P&L netto con max loss originale** — quanto male può ancora andare?
3. **[ ] Fetch dati freschi**: `analyze_options(legs, expiry)` per greche attuali
4. **[ ] Costruisci Exit Ladder** a 3 orizzonti temporali (Sezione 6)
5. **[ ] Analisi VPA/Wyckoff** del sottostante (Sezione 5): il movimento recente è domanda genuina o dead cat?
6. **[ ] Definisci scenari 🟢🟡🔴🚨** con prezzi e volumi espliciti (Sezione 2)
7. **[ ] Verifica incrociata dati** (Sezione 4) se i volumi sono sospetti
8. **[ ] Decidi: chiudere ora, aspettare trigger, o comprare protezione**
9. **[ ] Se chiudi/rolli**: aggiorna immediatamente il file posizione
10. **[ ] Calcola la metrica di successo**: loss evitata = max_loss_originale − loss_effettiva

---

## 9. Metriche di successo della gestione attiva

Non si misura il successo in "profitto o perdita" — si misura in **quanto della max loss originale è stata evitata**.

| Metrica | Formula | DRAM | LHX |
|---|---|---|---|
| Max Loss originale | Dalla strategia iniziale | Rischio naked put | $947 |
| Loss effettiva | P&L netto attuale | Floor protetto | ~$200 |
| **Loss evitata** | Max Loss − Loss effettiva | Significativa | ~$747 |
| **Efficienza** | Loss evitata / Max Loss | — | **79%** |

**Obiettivo**: loss evitata > 50% della max loss originale. Se sotto il 30%, la gestione attiva non sta funzionando — chiudere e ripartire.

---

## 10. Anti-pattern (cosa NON fare)

| Errore | Conseguenza | Lezione |
|---|---|---|
| Vendere call coperte con IV rank < 20° percentile | Premio magro, cappi un rimbalzo | LHX: non vendere call dopo il crollo a $263 |
| Rollare senza controllare il net credit | Peggiori la posizione | DRAM: ogni roll deve dare credito netto positivo |
| Basare decisioni su volumi intraday parziali | Falso segnale | DRAM 31.07: 70M ≠ "volume dimezzato" |
| Non aggiornare il file posizione | Perdi il quadro del P&L cumulativo | Entrambe: il file è la memoria |
| Aspettare "che torni" senza exit ladder | Il theta ti mangia vivo | LHX: −$5.26/giorno |
| Fidarsi ciecamente di yfinance | Dati errati → decisioni errate | Sezione 4 |
| Chiudere in fretta una posizione che potrebbe rimbalzare | Perdita inutile | VPA/Wyckoff per qualificare |
| NON chiudere quando il breakeven è a portata | Avidità → perdita peggiore | Exit ladder: se sei a −2%, chiudi |

---

## Riferimenti incrociati

- **options-playbook**: strategie standard di repair (roll, collar, spread)
- **option-volatility-pricing**: greche, theta decay, volatility smile
- **wyckoff-2-0**: qualificazione accumulazione/distribuzione
- **volume-price-analysis**: effort vs result, conferma volume/prezzo
- **trading-in-the-zone**: disciplina psicologica nel chiudere una perdita
- **evidence-based-technical-analysis**: non data-mining i pattern di rimbalzo
