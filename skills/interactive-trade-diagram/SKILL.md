---
name: interactive-trade-diagram
description: "Genera un diagramma HTML interattivo per ogni analisi di posizione su azioni o opzioni e per ogni proposta di strategia. Il diagramma mostra payoff, break-even, greche, waterfall del P&L, storia del trade, scenari e livelli di alert. Usa questa skill quando l'utente chiede: analizza la mia posizione, cosa fare con questa posizione, position repair, roll, strategia opzioni, come entro a mercato, che opzioni compro, diagramma, payoff, spiegami la posizione, visualizza la strategia."
allowed-tools: [read, grep, bash, edit, write]
metadata:
  argument-hint: '[ticker oppure "template" oppure "checklist"]'
---

# Interactive Trade Diagram

Un'analisi di trading si capisce con un diagramma. Un muro di testo no.
Questa skill produce un file HTML autonomo per ogni analisi di posizione o di strategia.
Il file è interattivo. Il file non richiede rete. Il file si apre con doppio clic.

---

## 1. Quando il diagramma è obbligatorio

| Tipo di richiesta | Diagramma | File |
|---|---|---|
| POSITION_REPAIR — posizione aperta su azioni o opzioni | **Sì** | `trades/<TICKER>_diagram.html` |
| STRATEGY_IDEA — "che strategia opzioni su X?" | **Sì** | `trades/<TICKER>_diagram.html` |
| NEW_ANALYSIS su un titolo con tesi operativa | **Sì** | `trades/<TICKER>_diagram.html` |
| Analisi multi-leg (spread, condor, calendar) | **Sì** | `trades/<TICKER>_diagram.html` |
| QUICK_CHECK — "quanto quota X?" | No | — |
| PORTFOLIO_SCAN — solo classifica | No. Aggiungi il diagramma solo per il primo ticker scelto | — |

**Regola**: se la risposta contiene un prezzo di ingresso, uno strike o una scadenza, allora serve il diagramma.

---

## 2. Come si costruisce

1. Copia il template.
   ```bash
   cp skills/interactive-trade-diagram/assets/template.html trades/<TICKER>_diagram.html
   ```
2. Apri il file. Trova il blocco `const CONFIG = {...}`. Sostituisci **solo** quel blocco.
3. Non toccare il motore. Il motore calcola payoff, break-even, estremi e curve.
4. Verifica il file in un browser headless.
   ```bash
   SH="$HOME/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell"
   "$SH" --no-sandbox --dump-dom file://$PWD/trades/<TICKER>_diagram.html | grep -o "<title>[^<]*</title>"
   ```
   Il titolo deve essere quello atteso. Se il titolo contiene `ERR:`, c'è un errore JavaScript. Correggi.
5. Controlla il rendering visivo.
   ```bash
   "$SH" --no-sandbox --hide-scrollbars --window-size=1200,3200 \
     --screenshot=/tmp/diag.png file://$PWD/trades/<TICKER>_diagram.html
   ```
   Apri l'immagine con lo strumento `view`. Cerca: curve fuori scala, etichette sovrapposte, tabelle vuote.
6. Collega il diagramma al documento di analisi. Aggiungi una riga in testa al markdown:
   `Diagramma interattivo: [<TICKER>_diagram.html](./<TICKER>_diagram.html)`

---

## 3. Schema del blocco CONFIG

| Campo | Tipo | Obbligatorio | Note |
|---|---|---|---|
| `ticker` | string | Sì | Simbolo. |
| `title` | string | Sì | Titolo del documento. |
| `subtitle` | string | Sì | Data, spot, giorni alla scadenza. |
| `asOf` | string | Sì | Data dei dati. Formato `gg.mm.aaaa`. |
| `spot` | number | Sì | Prezzo corrente del sottostante. |
| `r` | number | Sì | Tasso privo di rischio. Usa `^IRX / 100`. |
| `dte` | number | Sì | Giorni alla scadenza. |
| `expiryLabel` | string | Sì | Esempio `21.01.2028`. |
| `ivToday` | number | Sì | IV usata per la curva "oggi". Calibrala sul mark. |
| `realized` | number | No | P&L già incassato sulle gambe chiuse. Sommato a tutti i calcoli. |
| `legs` | array | Sì | Gamba: `{kind, side, strike, qty, entry, iv, mark}`. |
| `chips` | array | Sì | `{label, value, tone}`. `tone` = `pos`, `neg`, `warn`. |
| `zones` | array | No | Se manca, le card si generano dai dati. Meglio lasciarlo vuoto. |
| `greeks` | array | No | `{name, value, note}`. Prendi i valori da `analyze_options`. |
| `bridge` | array | No | Flussi di cassa: `{label, value, kind}`. `kind` = `flow` o `total`. |
| `timeline` | array | No | `{date, title, detail, price, cls}`. `cls` = `close` o `open`. |
| `timelineSide` | object | No | `{title, rows:[[label, value, tone]], note}`. |
| `alerts` | array | No | `{level, meaning, action, tone}`. |
| `verifica` | object | Sì | `{confidence, evidence, unverified, escalation}`. |

### `kind` delle gambe

| Valore | Significato | Esempio |
|---|---|---|
| `put` | Opzione put | `{kind:"put", side:"short", strike:280, qty:1, entry:26.19}` |
| `call` | Opzione call | `{kind:"call", side:"long", strike:300, qty:2, entry:5.10}` |
| `stock` | Azioni | `{kind:"stock", side:"long", qty:100, entry:148.20}` |

`side` vale `short` o `long`. Il moltiplicatore è 100 per le opzioni. È 1 per le azioni.

### `bridge` — flussi di cassa, non P&L

Il ponte somma **incassi e pagamenti**, non profitti e perdite.
Esempio corretto: credito +501, costo di chiusura −2,420, nuovo credito +2,619 → cumulato 700.
Esempio sbagliato: credito +501, realized −1,919, nuovo credito +2,619 → cumulato 1,201. Doppio conteggio.

---

## 4. Regole di scrittura — ASD-STE100

La fonte unica è la skill `asd-ste100` (`skills/asd-ste100/SKILL.md`). Caricala quando revisioni un testo.
Tutto il testo del diagramma e della risposta segue queste regole.

| Regola | Cosa fare | Cosa non fare |
|---|---|---|
| Frasi brevi | Massimo 20 parole per frase. Massimo 25 in una nota. | Frasi con tre proposizioni. |
| Un'idea per frase | "Il roll ha ridotto lo strike. Il tempo è aumentato." | "Il roll ha ridotto lo strike anche se il tempo è aumentato." |
| Voce attiva | "Il broker registra la perdita." | "La perdita viene registrata." |
| Tempi semplici | Presente, passato prossimo, futuro semplice. | Congiuntivo, condizionale composto. |
| Verbi precisi | "usa", "calcola", "verifica", "chiudi". | "effettuare", "provvedere", "implementare". |
| Liste verticali | Una procedura va in lista numerata. | Procedura dentro un paragrafo. |
| Un termine, un senso | "mark" sempre per il valore di mercato. | "mark", "prezzo", "quotazione" per la stessa cosa. |
| Abbreviazioni | Definisci alla prima occorrenza: "BE = break-even". | Usare sigle non spiegate. |
| Niente modi di dire | "Il risultato è negativo." | "È un bagno di sangue." |
| Numeri esatti | "−$3,383.54". | "circa tremila". |

La risposta in chat segue le stesse regole. Massimo 6 righe di testo prima della tabella.

---

## 5. Dati ammessi

Ogni numero viene da una fonte. Nessun numero si stima a mano.

| Dato | Fonte |
|---|---|
| Spot, OHLCV, ATR, RSI | `fetch_stock_data` oppure `analyze_stock` |
| Strike, bid, ask, IV, OI | `fetch_options_chain` |
| Delta, theta, vega, P(ITM) | `analyze_options` |
| Mark di posizione | CSV IBKR dell'utente, se disponibile |
| GEX, put wall, call wall | `gex_analysis` |
| VIX, DXY, Fed | `get_macro_context` |
| Curve "oggi", break-even, max profit | Motore del template, in JavaScript |

Se un dato manca, scrivi "non disponibile". Non inventare il valore.

La IV di `ivToday` deve riprodurre il mark. Verifica con un piccolo calcolo Python. Se la IV della catena non riproduce il mark, usa la IV implicita del fill e dichiaralo nella sezione "non verificato".

---

## 6. Struttura del diagramma

| Sezione | Contenuto | Interazione |
|---|---|---|
| 1 · Payoff | Curva a scadenza, curva di oggi, area verde e rossa, linee SPOT, strike e BE | Slider, trascinamento, 3 viste, tooltip |
| 2 · Anatomia | Gambe, entry, mark, P&L, greche, economia | — |
| 3 · Ponte del P&L | Flussi di cassa a cascata | — |
| 4 · Storia | Passaggi della posizione, confronto prima/dopo | Clic su un passaggio |
| 5 · Scenari | Tabella prezzi con P&L e esito | Clic su una riga |
| 6 · Alert | Livelli da monitorare | — |

Le sezioni 3, 4 e 6 sono opzionali. Se il dato manca, la sezione si nasconde da sola.

---

## 7. Checklist prima della consegna

1. Il titolo del file è corretto. Non contiene `ERR:`.
2. Il grafico ha la curva a scadenza e la curva di oggi.
3. La zona verde è sopra il break-even. La zona rossa è sotto.
4. Il max profit e il max loss coincidono con il calcolo Python.
5. Il break-even coincide con il calcolo Python.
6. Il ponte del P&L chiude sul totale giusto.
7. Le sezioni vuote sono nascoste.
8. Il diagramma è leggibile a 430 px di larghezza.
9. Ogni numero ha una fonte.
10. Il documento markdown collega il diagramma.

Esegui la verifica Python dei punti 4 e 5 prima di consegnare.

```python
# esempio: short put
entry, mark, qty, K, mult = 26.19, 40.83, 1, 280, 100
cum = 7.00
print("BE", K - cum)
print("max profit", cum*mult)
print("max loss", (K*mult) - cum*mult)
print("P&L", (cum - mark)*qty*mult)
```

---

## 8. Anti-pattern

- ❌ **Sommare il credito al P&L.** Il credito cumulato non è il P&L. Il P&L è `credito cumulato − valore della posizione`.
- ❌ **Usare il P&L realizzato dentro il ponte dei flussi.** Il ponte usa i flussi di cassa.
- ❌ **Disegnare a mano il payoff.** Il motore lo calcola da `legs`. Aggiungi gambe, non pixel.
- ❌ **Mostrare il mark come costo di chiusura.** Per chiudere paghi l'ask. Scrivilo.
- ❌ **Inventare la IV.** Calibra la IV sul mark. Dichiara la differenza.
- ❌ **Consegnare senza screenshot.** Un grafico vuoto si scopre solo guardandolo.
- ❌ **Scrivere frasi lunghe nel diagramma.** Il diagramma si legge in 10 secondi.
- ❌ **Dimenticare il segno del delta.** Una short put ha delta **positivo**. La posizione guadagna quando il sottostante sale.
