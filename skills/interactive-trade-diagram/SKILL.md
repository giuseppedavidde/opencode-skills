---
name: interactive-trade-diagram
description: "Genera un diagramma HTML interattivo per ogni analisi di posizione su azioni o opzioni e per ogni proposta di strategia. Il diagramma mostra payoff, break-even, zone di profitto e perdita, greche del modello, P&L di chiusura bid/ask, andamento giornaliero, storia del trade, scenari con stress di IV e livelli di alert. Usa questa skill quando l'utente chiede: analizza la mia posizione, cosa fare con questa posizione, position repair, roll, strategia opzioni, come entro a mercato, che opzioni compro, diagramma, payoff, spiegami la posizione, visualizza la strategia."
allowed-tools: [read, grep, bash, edit, write]
metadata:
  argument-hint: '[ticker oppure "template" oppure "checklist"]'
---

# Interactive Trade Diagram

Un'analisi di trading si capisce con un diagramma. Un muro di testo no.
Questa skill produce un file HTML autonomo per ogni analisi di posizione o di strategia.
Il file è interattivo. Il file non usa la rete. Il file si apre con doppio clic.

---

## 1. Quando il diagramma è obbligatorio

| Tipo di richiesta | Diagramma | File |
|---|---|---|
| POSITION_REPAIR — posizione aperta su azioni o opzioni | **Sì** | `trades/<TICKER>_diagram.html` |
| STRATEGY_IDEA — "che strategia opzioni su X?" | **Sì** | `trades/<TICKER>_diagram.html` |
| NEW_ANALYSIS su un titolo con tesi operativa | **Sì** | `trades/<TICKER>_diagram.html` |
| Analisi multi-leg (spread, condor, calendar, diagonal) | **Sì** | `trades/<TICKER>_diagram.html` |
| QUICK_CHECK — "quanto quota X?" | No | — |
| PORTFOLIO_SCAN — solo classifica | No. Aggiungi il diagramma solo per il primo ticker scelto | — |

**Standard**: ogni diagramma di posizione include la vista giornaliera. La vista giornaliera è parte dello standard.

**Regola**: se la risposta contiene un prezzo di ingresso, uno strike o una scadenza, allora serve il diagramma.

---

## 2. Come si costruisce

1. Copia il template.
   ```bash
   cp skills/interactive-trade-diagram/assets/template.html trades/<TICKER>_diagram.html
   ```
2. Apri il file. Trova il blocco tra `CONFIG-BEGIN` e `CONFIG-END`. Sostituisci **solo** `const CONFIG = {...};`.
3. Non toccare il motore. Il motore calcola payoff, break-even, zone, estremi, greche e curve.
4. Esegui il self-test. Il self-test non usa un browser. Serve solo `node` (versione 22 o più recente).
   ```bash
   node skills/interactive-trade-diagram/scripts/check_diagram.mjs trades/<TICKER>_diagram.html
   ```
   - Exit code 0 e `RISULTATO: OK`: il file è valido.
   - Exit code 1: leggi le righe `ERRORE:`. Correggi il CONFIG. Esegui di nuovo il self-test.
   - Le righe `AVVISO:` non bloccano. Scrivi ogni avviso nella sezione "non verificato" della risposta.
   - `--json` stampa il riepilogo del motore: break-even, zone, max profit, max loss, P&L di chiusura.
5. Il self-test carica il file con il modulo `vm` di node e con un DOM minimo. Il self-test esegue il motore e simula clic, slider, tasti e mouse. Il self-test controlla:
   - errori JavaScript e titolo `ERR:`;
   - errori di validazione del CONFIG;
   - valori `NaN`, `undefined` o `Infinity` nel DOM;
   - ogni cambio di segno del payoff ha un break-even; ogni zona ha un solo segno;
   - nessun punto del payoff supera il max profit o il max loss;
   - tabella giornaliera e mappa di calore con gli stessi giorni;
   - nessuna risorsa remota (CDN, script, fetch).
6. Collega il diagramma al documento di analisi. Aggiungi una riga in testa al markdown:
   `Diagramma interattivo: [<TICKER>_diagram.html](./<TICKER>_diagram.html)`

Il file mostra ogni errore anche nel browser: il titolo diventa `ERR: <messaggio>` e appare un banner rosso. Gli avvisi appaiono in un banner giallo.

---

## 3. Schema del blocco CONFIG

### Campi globali

| Campo | Tipo | Obbligatorio | Note |
|---|---|---|---|
| `ticker` | string | Sì | Simbolo. |
| `title` | string | Sì | Titolo del documento. |
| `subtitle` | string | Sì | Data, spot, giorni alla scadenza front. |
| `asOf` | string | Sì | Data dei dati. Formato `gg.mm.aaaa` o `aaaa-mm-gg`. |
| `asOfTime` | string | Per 0DTE e 1DTE | Ora dei dati a New York, `HH:MM`. Default `16:00`. |
| `currency` | string | No | Codice ISO di 3 lettere. Default `USD`. Tutte le gambe usano questa valuta. |
| `spot` | number | Sì | Prezzo del sottostante all'ora `asOf`. |
| `r` | number | Sì | Tasso privo di rischio in decimali. Usa `^IRX / 100`. Il valore 0 è valido. |
| `q` | number | No | Dividend yield continuo in decimali. Default 0. |
| `expiryISO` | string | Sì, con opzioni | Scadenza **front**: la scadenza più vicina tra le gambe. Formato `aaaa-mm-gg`. |
| `dte` | number | Sì, con opzioni | Giorni di calendario da `asOf` a `expiryISO`. Il motore controlla l'uguaglianza. |
| `expiryLabel` | string | No | Etichetta della scadenza front. Default dalla data `expiryISO`. |
| `ivToday` | number | No | IV di default per le gambe senza `iv`. Riferimento di `daily.iv`. |
| `realized` | number | No | P&L già realizzato sulle gambe chiuse. Sommato a ogni curva. Default 0. |
| `style` | string | No | `european` (default) o `american` per tutte le gambe. |
| `volModel` | object | No | Regola spot-vol: `{rule, slope}`. Vedi la sezione 4. |
| `legs` | array | Sì | Gambe aperte. Vedi sotto. |
| `chips` | array | No | Solo fatti di input: `{label, value, tone}`. `tone` = `pos`, `neg`, `warn`. |
| `autoChips` | boolean | No | Default `true`: il motore aggiunge P&L, BE, max profit, max loss e DTE. |
| `zones` | array | No | Lascia `null`. Il motore genera le card dai segni del payoff. |
| `scenarios` | array | No | Prezzi della tabella scenari. Default automatico. |
| `xmin`, `xmax` | number | No | Limiti dell'asse dei prezzi. Default automatico. |
| `greeks` | array | No | `{name, value, note}` da `analyze_options`. Il motore mostra anche le greche del suo modello. |
| `bridge` | array | No | Flussi di cassa: `{label, value, kind}`. `kind` = `flow` o `total`. |
| `timeline` | array | No | `{date, title, detail, price, cls}`. `cls` = `close` o `open`. |
| `timelineSide` | object | No | `{title, rows:[[label, value, tone]], note}`. |
| `alerts` | array | No | `{level, meaning, action, tone}`. |
| `daily` | object | No | Vista giornaliera. Vedi sotto. |
| `verifica` | object | Sì | `{confidence, evidence, unverified, escalation}`. |

### `legs` — una riga per gamba

| Campo | Tipo | Obbligatorio | Note |
|---|---|---|---|
| `kind` | string | Sì | `call`, `put` o `stock`. |
| `side` | string | Sì | `long` o `short`. |
| `qty` | number | Sì | Numero di contratti o di azioni. Sempre positivo. |
| `strike` | number | Sì, opzioni | Strike. |
| `entry` | number | Sì | Prezzo di ingresso per azione (premio o prezzo del titolo). |
| `iv` | number | Sì, opzioni | IV della gamba in decimali (0.45 = 45%). Calibrala sul mark. Default `ivToday`. |
| `expiry` | string | Sì, multi-scadenza | Scadenza della gamba, `aaaa-mm-gg`. Default `expiryISO`. |
| `mark` | number | No | Valore di mercato per azione (mid o mark del broker). |
| `bid`, `ask` | number | No | Quotazioni per azione. Il P&L di chiusura usa il bid per le long e l'ask per le short. |
| `mult` | number | No | Moltiplicatore. Default 100 per le opzioni, 1 per le azioni. Mini, aggiustate, EU: scrivilo. |
| `currency` | string | No | Deve essere uguale a `currency`. Converti prima i prezzi. |
| `style` | string | No | `american`: il valore della gamba non scende sotto l'intrinseco. |
| `opened` | string | No | Data di apertura, `aaaa-mm-gg`. Serve alla ricostruzione storica. |

Esempi:

| Gamba | Esempio |
|---|---|
| Put short | `{kind:"put", side:"short", strike:280, qty:1, entry:26.19, iv:0.7545, mark:40.83, bid:40.10, ask:41.50, expiry:"2028-01-21"}` |
| Call long | `{kind:"call", side:"long", strike:300, qty:2, entry:5.10, iv:0.52, expiry:"2027-01-15"}` |
| Azioni | `{kind:"stock", side:"long", qty:100, entry:148.20, mark:151.05}` |

Il campo `dte` della gamba è superato. Il motore lo accetta con un avviso. Scrivi `expiry`.

### `daily` — vista giornaliera

| Campo | Tipo | Default | Note |
|---|---|---|---|
| `iv` | number | `ivToday` | IV base della vista. Lo shift vale `iv − ivToday` su ogni gamba. |
| `ivStress` | number | 10 | Punti di IV dei pulsanti e delle colonne di stress. |
| `paths` | array | auto | `{label, short, color, to}`. Massimo 6. `to: null` = spot costante. `color` in esadecimale. |
| `heat` | object | auto | `{min, max}` della scala colori. |
| `hist` | array | null | Righe `{date, close, est, note, legs, realized}`. `date` in `aaaa-mm-gg`. |
| `histIv` | number | `daily.iv` | IV di riferimento della ricostruzione storica. |
| `lineNote`, `dayNote`, `histNote` | string | generata | Note del grafico, della tabella e della storia. |

### `bridge` — flussi di cassa, non P&L

Il ponte somma **incassi e pagamenti**, non profitti e perdite.
Esempio corretto: credito +501, costo di chiusura −2,420, nuovo credito +2,619 → cumulato 700.
Esempio sbagliato: credito +501, realized −1,919, nuovo credito +2,619 → cumulato 1,201. Doppio conteggio.

---

## 4. Regole del motore

| Tema | Regola |
|---|---|
| Tempo | Ogni gamba scade alle 16:00 di New York della sua data. T = tempo di calendario da `asOf` + `asOfTime` alla scadenza, diviso 365 giorni. L'ora legale USA è inclusa. |
| Valore | Una gamba viva vale Black-Scholes-Merton con la sua IV, `r`, `q` e il suo T. Una gamba scaduta vale l'intrinseco. |
| Curva "a scadenza" | P&L alla scadenza **front**. Le gambe più lontane restano vive e valgono BSM. Calendar e diagonal hanno break-even e max P&L corretti. |
| Break-even | Cercati su tutto [0, ∞). A scadenza, senza gambe vive, il payoff è lineare a tratti: soluzione esatta. Con gambe vive: griglia logaritmica, bisezione e asintoto per S → ∞. |
| Zone | Intervalli di segno tra i break-even ordinati. Ogni zona ha il suo massimo o minimo. Vale per strutture rialziste, ribassiste, neutrali e illimitate. |
| Max profit, max loss | Estremi sulle zone. "Illimitato" quando la pendenza per S → ∞ non è zero. |
| P&L | `realized + Σ segno × (valore − entry) × qty × mult`. |
| P&L di chiusura | Bid per le long, ask per le short. Senza quotazione: mark con l'etichetta "mid/mark". Senza mark: modello BSM. |
| Theta 1 g | `P&L(giorno + 1) − P&L(giorno)` a spot costante. Una long ha theta negativa. |
| P(ITM) | N(d2) per le call, N(−d2) per le put, alla scadenza della gamba. Misura risk-neutral, lognormale. Non è una probabilità reale. Il delta non è una probabilità. |
| Probabilità di zona | Lognormale risk-neutral alla scadenza front, con la IV ATM interpolata tra gli strike front. |
| Regola spot-vol | `sticky-strike`: IV fissa per strike. `sticky-delta`: la IV segue la moneyness sullo smile delle gambe della stessa scadenza. `slope`: punti di IV per +1% di spot, per esempio −0.5. |
| Stress di IV | Pulsanti ±`ivStress`: ridisegnano linee, mappa di calore e tabella. La tabella scenari ha le colonne "Oggi IV −x" e "Oggi IV +x". |
| Storia | Ogni riga usa le sue `legs` e il suo `realized`. Senza `legs`, la riga usa le gambe attuali. Se una gamba attuale ha `opened` dopo la data, la riga è rifiutata. |
| Griglia | Passi dell'asse, dello slider, degli scenari e della mappa scalano con il prezzo. Funziona anche sotto $5. |
| Testo | Ogni stringa del CONFIG entra come testo, mai come HTML. |

Controlli automatici sui dati (avvisi):

- La IV di ogni gamba deve riprodurre il mark. Tolleranza: 2% del mark, minimo 0.02, o mezzo spread.
- Spread bid/ask oltre il 25% del mid.
- 0DTE senza `asOfTime`.
- Call europee vive con `q > 0`: il modello dà una perdita senza limite per S → ∞.

---

## 5. Regole di scrittura — ASD-STE100

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

## 6. Dati ammessi

Ogni numero viene da una fonte. Nessun numero si stima a mano.

| Dato | Fonte |
|---|---|
| Spot, OHLCV, ATR, RSI | `fetch_stock_data` oppure `analyze_stock` |
| Strike, bid, ask, IV, OI | `fetch_options_chain` |
| Delta, theta, vega di riferimento | `analyze_options` |
| Mark di posizione | CSV IBKR dell'utente, se disponibile |
| GEX, put wall, call wall | `gex_analysis` |
| VIX, DXY, Fed | `get_macro_context` |
| Curve, break-even, zone, max profit, max loss, P(ITM), theta del modello | Motore del template |

Se un dato manca, scrivi "non disponibile". Non inventare il valore.
La IV di ogni gamba deve riprodurre il mark. Il motore lo controlla e dà un avviso. Se la IV della catena non riproduce il mark, usa la IV implicita del mark e dichiaralo nella sezione "non verificato".

---

## 7. Struttura del diagramma

| Sezione | Contenuto | Interazione |
|---|---|---|
| Banner | Errori in rosso, avvisi in giallo | — |
| 1 · Payoff | Curva alla scadenza front, curva di oggi, curva del giorno; area blu = profitto, area arancio = perdita; linee di spot, strike e ogni BE; card di zona | Slider, trascinamento, 4 viste, tooltip |
| 2 · Andamento giornaliero | Grafico a linee, mappa di calore, tabella, storia | Slider del giorno, pulsanti IV, legenda cliccabile, mappa con tastiera |
| 3 · Anatomia | Gambe, scadenze, entry, mark, bid/ask, P&L di chiusura, P(ITM), economia, greche del modello | — |
| 4 · Ponte del P&L | Flussi di cassa a cascata | — |
| 5 · Storia | Passaggi della posizione, confronto prima/dopo | Clic su un passaggio |
| 6 · Scenari | Prezzi con P&L a scadenza, oggi, oggi IV −x, oggi IV +x, esito | Clic su una riga |
| 7 · Alert | Livelli da monitorare | — |

La sezione 2 è obbligatoria quando la scadenza front è dopo `asOf` e c'è almeno una opzione. Il passo è adattivo: 1 giorno fino a 120 giorni, poi `ceil(giorni/120)`. Massimo 121 colonne. Il giorno 0 è `asOf`. L'ultimo giorno è la scadenza front.
La mappa di calore usa arancio (perdita) e blu (profitto). La palette è leggibile anche per i daltonici. Il valore di ogni cella appare con il mouse e con il focus della tastiera (Tab, poi le frecce).
Le sezioni 4, 5 e 7 sono opzionali. Se il dato manca, la sezione si nasconde da sola.

---

## 8. Checklist prima della consegna

1. Il self-test dà exit code 0 e `RISULTATO: OK`.
2. Il titolo del file non contiene `ERR:`. Il banner rosso non è visibile.
3. Le zone seguono i segni del payoff tra i break-even ordinati. Esempi: short call = profitto sotto il BE; iron condor = profitto tra i due BE; long straddle = perdita tra i due BE.
4. Il max profit e il max loss coincidono con il calcolo Python.
5. Ogni break-even coincide con il calcolo Python. Ogni break-even ha una linea nel grafico.
6. `expiryISO` è la scadenza front. `dte` coincide con `asOf` + giorni.
7. Ogni gamba di una calendar o di una diagonal ha `expiry`.
8. Il P&L di chiusura usa bid e ask, oppure mostra l'etichetta "mid/mark".
9. Il ponte del P&L chiude sul totale giusto.
10. Le sezioni vuote sono nascoste.
11. Il diagramma è leggibile a 430 px di larghezza.
12. Ogni numero ha una fonte.
13. Il documento markdown collega il diagramma.
14. Ogni avviso del self-test è nella sezione "non verificato".

Esegui la verifica Python dei punti 4 e 5 prima di consegnare. L'esempio è una short put a scadenza singola.

```python
# esempio: short put, qty contratti, realized già incassato
K, entry, mark, qty, mult, realized = 280, 26.19, 40.83, 1, 100, -1919.0
credit_cum = entry + realized/(qty*mult)       # 7.00 per azione
print("BE", K - credit_cum)                     # 273.00
print("max profit", credit_cum*qty*mult)        # +700
print("max loss", (credit_cum - K)*qty*mult)    # −27,300 a S = 0
print("P&L al mark", realized + (entry - mark)*qty*mult)
```

Per calendar e diagonal la curva a scadenza dipende dalla gamba viva. Confronta con `check_diagram.mjs --json`, non con un calcolo a mano.

---

## 9. Manutenzione del motore

- Test del motore: `node skills/interactive-trade-diagram/tests/test_diagram.mjs`. Il test confronta 9 casi con un riferimento Python indipendente e prova i casi di errore.
- Casi: long call, short put, iron condor, call calendar, short call 0DTE, straddle con IV alta, r = 0, put diagonal in EUR, covered call su un titolo da $3.
- Valori di riferimento: `tests/fixtures/golden_cases.json`. Rigenera con:
  ```bash
  uv run --no-project --with numpy --with scipy python skills/interactive-trade-diagram/tests/reference.py --write
  ```
- Senza `--write`, `reference.py` ricalcola i valori e li confronta con la fixture.

---

## 10. Anti-pattern

- ❌ **Sommare il credito al P&L.** Il credito cumulato non è il P&L. Il P&L è `credito cumulato − valore della posizione`.
- ❌ **Usare il P&L realizzato dentro il ponte dei flussi.** Il ponte usa i flussi di cassa.
- ❌ **Disegnare a mano il payoff.** Il motore lo calcola da `legs`. Aggiungi gambe, non pixel.
- ❌ **Scrivere BE, max profit o max loss nei chips.** Il motore li calcola. Un valore a mano può contraddire il grafico.
- ❌ **Mostrare il mark come costo di chiusura.** Per chiudere paghi l'ask e incassi il bid. Dai `bid` e `ask`.
- ❌ **Inventare la IV.** Calibra la IV sul mark. Dichiara la differenza.
- ❌ **Usare il delta come probabilità.** P(ITM) = N(d2) o N(−d2), misura risk-neutral.
- ❌ **Una sola scadenza per una calendar.** Ogni gamba ha la sua `expiry`. `expiryISO` è la front.
- ❌ **Consegnare senza self-test.** Un errore di CONFIG si scopre solo con `check_diagram.mjs`.
- ❌ **Scrivere frasi lunghe nel diagramma.** Il diagramma si legge in 10 secondi.
- ❌ **Dimenticare il segno del delta.** Una short put ha delta **positivo**. La posizione guadagna quando il sottostante sale.
- ❌ **Consegnare un diagramma di posizione senza la vista giornaliera.** La vista giornaliera è parte dello standard.
