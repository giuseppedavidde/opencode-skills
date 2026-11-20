---
name: position-management-playbook
description: "Gestione attiva di posizioni aperte: piano di rischio in R e in % dell'equity, hard stop, uscite su tesi, valore atteso e limiti di rischio, regole di roll con fresh-trade test e limiti, assegnazione, early exercise, ex-dividend, pin risk, stress del margine, qualificazione VPA/Wyckoff dei rimbalzi, caveat volumi intraday. Carica quando l'utente chiede: posizione scomoda, uscire, exit, gestione posizione, position repair, chiudere, roll, dead cat, exit ladder, scala di uscita, riparare, fix this, cosa fare con questa posizione, coprire, hedge, assegnazione, margine."
allowed-tools: [read, grep, bash, webfetch]
metadata:
  argument-hint: "[topic (risk, discipline, scenario, vpa, ladder, trigger, roll, assignment, margin, checklist, metrics)]"
---

# Position Management Playbook

Framework operativo nato da sessioni reali di gestione su DRAM e LHX.
Le lezioni reali restano. Le regole di decisione seguono un piano di rischio scritto prima dell'entrata.

**Principio**: il mercato non conosce il tuo prezzo di ingresso. Decidi con i prezzi di oggi, la tesi e i limiti di rischio. La perdita già realizzata è un costo passato: non cambia la decisione.

---

## 1. Piano di rischio: prima dell'entrata

Ogni posizione ha un piano scritto prima dell'ordine. Senza piano, non apri la posizione.

| Voce | Regola | Default se l'utente non dà valori |
|---|---|---|
| Equity di riferimento | Valore del conto all'entrata | Chiedi all'utente |
| R (rischio pianificato) | Perdita in valuta all'hard stop. Per uno spread a rischio definito: il max loss, se lo stop non è più stretto | — |
| Rischio per trade | R ≤ limite in % dell'equity | 1% dell'equity |
| Heat del portafoglio | Somma degli R aperti ≤ limite | 6% dell'equity |
| Perdita di stress | Perdita con gap del sottostante e IV in salita (sezione 8) ≤ limite | 3% dell'equity |
| Hard stop | Livello del sottostante o perdita in valuta. Obbligatorio | — |
| Time stop | Data di uscita se la tesi non lavora | Short premium: 21 DTE. Long premium: metà della vita residua |
| Invalidazione della tesi | Prezzo e volume che dicono "la tesi è sbagliata" | — |
| Eventi | Earnings, FOMC, CPI, ex-dividend prima della scadenza | Nessuna posizione aperta senza un piano per l'evento |

Regole:
- Una posizione a rischio non definito (short put o short call nude) usa la perdita di stress come R. Se la perdita di stress supera il limite, la size è troppo grande.
- La size si calcola dal rischio: `size = (equity × rischio per trade) / R per unità`.
- Il margine non è il rischio. Il margine può crescere molto in un gap (sezione 8).

---

## 2. Disciplina del file posizioni

Ogni posizione DEVE avere un file markdown con:

```
# TICKER Position — Riepilogo Completo
Ultimo aggiornamento: DATA, TICKER @ $PREZZO

## Piano di rischio (scritto all'entrata)
Equity, R, hard stop, time stop, invalidazione della tesi, eventi

## Posizione di partenza (strategia originale)
| Leg | Strike | Scadenza | Qty | Prezzo entry | Note |

## Cronologia di TUTTE le operazioni
#1 — APERTURA (data)
#2 — ROLL/CHIUSURA (data, prezzo sottostante, motivo, numero del roll)
...

## Posizione attuale
| Leg | Strike | Scadenza | Qty | Costo base | Mark | Bid | Ask |

## P&L (REALIZZATO + NON REALIZZATO, separati), in valuta, in R e in % dell'equity
## Numeri chiave (delta, gamma, theta, vega, break-even, max loss, perdita di stress, margine)
## Eventi critici (earnings, ex-dividend, FOMC, CPI)
## Gestione in corso (scenari 🟢🟡🔴🚨 con livelli di prezzo)
```

**Regola d'oro**: aggiorna il file dopo ogni operazione. Misura il risultato in R e in % dell'equity contro il piano (sezione 11).

---

## 3. Quadro scenario-based PRIMA di agire

Non decidere "a sentimento". Definisci in anticipo:

| Scenario | Colore | Condizione | Azione |
|---|---|---|---|
| Ottimale | 🟢 | Prezzo > X, volume > YM, VPA rialzista | Tieni secondo il piano |
| Monitoraggio | 🟡 | Prezzo tra X e Y, volume normale | Non toccare. Controlla time stop ed eventi |
| Attenzione | 🔴 | Prezzo < Z, volume in aumento su candele rosse | Prepara l'ordine di uscita o la copertura |
| Emergenza | 🚨 | Prezzo ≤ hard stop, o gap oltre lo stress | Esegui lo stop nella stessa sessione |

Ogni scenario DEVE avere:
- **Livello di prezzo esplicito** (per esempio "chiude sotto $265").
- **Condizione di volume** (per esempio "volume > 1.5× la media a 20 giorni").
- **Azione predefinita**: "vendi X", "chiudi lo spread", "compra la put Z". Non "valuta".

Lo scenario 🟢 non autorizza ad aggiungere. Aggiungere segue la sezione 7.

---

## 4. Caveat volumi intraday 🔥

**Lezione DRAM (31.07.2026)**: a metà sessione il volume era 70M. Il giorno prima era 152M. Il volume sembrava "in crollo". La proiezione lineare dava 140M. Il volume finale fu 99M. Il volume NON è lineare durante la giornata.

**Regole**:
- I volumi a metà sessione sono PARZIALI. Non confrontarli con il totale del giorno prima.
- Proiezione: `volume_ora × (ore_totali_sessione / ore_trascorse)`. Usala con cautela: l'ultima ora ha spesso più volume.
- Per decisioni intraday, usa il **volume relativo alla stessa ora** del giorno precedente.
- Se la decisione dipende dal volume, **aspetta la chiusura**. L'hard stop non aspetta: esegui lo stop quando il prezzo lo rompe.

---

## 5. Verifica incrociata dei dati

yfinance NON è infallibile. Volumi, prezzi e opzioni possono differire dalle fonti dirette.

**Checklist**:
- [ ] Prezzo e volume: confronta yfinance con stockanalysis.com, Yahoo Finance web o MarketWatch.
- [ ] Opzioni: bid e ask reali dal broker, non il mid teorico.
- [ ] Data degli earnings: MAI da `earnings_surprise` di yfinance. Usa Benzinga o Nasdaq.com.
- [ ] Data ex-dividend e importo: dal sito dell'emittente o dal broker.
- [ ] Se la differenza è > 2% sui volumi o > 0.5% sui prezzi: **controlla prima di agire**.

---

## 6. VPA/Wyckoff per qualificare i rimbalzi

Non tutti i rimbalzi sono uguali. Separa la domanda reale dal dead cat bounce.
Una sola candela non basta. Chiedi una conferma: due sessioni o la tenuta di un livello.

| Pattern | Volume | Chiusura | Significato | Azione |
|---|---|---|---|---|
| Marubozu verde | > 1.5× media | Sul massimo | Domanda genuina | Tieni secondo il piano |
| Candela verde con ombra superiore lunga | > media | Sotto il massimo | Venditori attivi nell'area | Cautela |
| Candela rossa con volume alto | > 1.5× media | Sul minimo | Distribuzione | Controlla l'invalidazione. Riduci o esci se il piano lo dice |
| Rimbalzo su volume in calo | < media | Qualsiasi | Dead cat bounce | Non comprare. Non aggiungere |
| Doji su volume alto | > media | Corpo piccolo | Indecisione | Aspetta la conferma |
| Inside day dopo candela ampia | < media | — | Pausa o assorbimento | Neutro, monitora |

**Regola VPA**: il volume deve confermare il movimento del prezzo. Prezzo in salita senza volume = segnale debole. Prezzo in discesa con volume = pressione reale.
La terminologia (SC, BC, LVN, VWAP) segue il glossario canonico di `volume-price-analysis`.

---

## 7. Aggiungere: mai a una posizione in perdita

**Regola**: non aggiungere mai a una posizione in perdita. Niente media al ribasso. Niente raddoppio della size.

Aggiungere è possibile solo se tutte le condizioni sono vere:
1. La posizione è in profitto.
2. La nuova quota passa le regole di entrata, da sola.
3. Il rischio totale (vecchia quota + nuova) resta ≤ il rischio per trade. Sposta lo stop se serve.
4. La heat del portafoglio resta ≤ il limite.

Una "riparazione" che aumenta la size, aggiunge short put o allunga il rischio è un'aggiunta a una posizione in perdita. Non è ammessa.

---

## 8. Assegnazione, eventi, margine: checklist

Esegui questa checklist per ogni posizione con opzioni short, a ogni revisione.

### Assegnazione e early exercise (opzioni americane)
- [ ] **Short call ITM prima dell'ex-dividend**: il rischio di esercizio anticipato è alto se il valore temporale della call è minore del dividendo. Chiudi o rolla prima dell'ex-date.
- [ ] **Short put deep ITM**: il valore temporale vicino a zero rende probabile l'assegnazione in ogni giorno. Tassi alti aumentano il rischio.
- [ ] **Cassa per l'assegnazione**: una short put assegnata compra `100 × strike` di azioni. Controlla cassa e margine.
- [ ] **Spread con una gamba short ITM**: l'assegnazione della short lascia una posizione in azioni. La long protegge solo alla scadenza o con l'esercizio.
- [ ] **Stile e regolamento**: SPX e gli indici europei sono cash-settled e europei. SPY e le azioni sono americane e fisiche.

### Pin risk e scadenza
- [ ] Sottostante vicino a uno strike short nel giorno di scadenza: chiudi la gamba prima delle 16:00 di New York.
- [ ] Il cut-off di esercizio OCC è dopo la chiusura. Un movimento after-hours può cambiare l'esercizio della controparte.
- [ ] Non lasciare gambe short ITM o vicine allo strike nel weekend di scadenza.

### Eventi
- [ ] Earnings, FOMC, CPI o ex-dividend prima della scadenza: scrivi il piano per l'evento. Senza piano, chiudi o riduci prima dell'evento.
- [ ] Misura il movimento implicito dell'evento (straddle ATM della scadenza dopo l'evento). Confrontalo con la distanza degli strike short.

### Stress del margine e del P&L
- [ ] Calcola la perdita con spot −20% e +20%. Aggiungi IV +10 punti per le posizioni short vega. Usa le colonne "Oggi IV ±x" del diagramma.
- [ ] La perdita di stress resta ≤ il limite del piano (default 3% dell'equity).
- [ ] Calcola il margine richiesto nello scenario di stress (Reg-T o portfolio margin del broker). Il margine di stress resta ≤ 50% della liquidità in eccesso. Il broker può liquidare in automatico.
- [ ] Max loss della posizione in % dell'equity: scrivilo nel file. Rischio non definito: usa la perdita di stress.

---

## 9. Trigger di uscita

Le uscite seguono la tesi, il valore atteso e i limiti di rischio. Il break-even e il prezzo di ingresso non sono trigger.

| Trigger | Condizione | Azione |
|---|---|---|
| Hard stop | Prezzo ≤ stop, o perdita ≥ R pianificato | Chiudi nella stessa sessione |
| Limite di rischio | Perdita di stress o margine di stress oltre il limite | Riduci la size o compra protezione |
| Tesi fallita | Il livello di invalidazione rompe con volume | Chiudi |
| Valore atteso | Il valore atteso di tenere, con i prezzi di oggi, non supera il valore di chiudere | Chiudi |
| Time stop | Data del piano raggiunta | Chiudi, o applica il fresh-trade test della sezione 10 |
| Target | Target della tesi raggiunto | Chiudi o riduci secondo il piano |
| Evento | Evento prima della scadenza senza piano | Chiudi o riduci prima dell'evento |

Come si stima il valore atteso di tenere:
1. Usa i prezzi di oggi: bid per le long, ask per le short.
2. Elenca gli scenari della tesi con una probabilità tua. Dichiarala come stima.
3. Le probabilità del modello (N(d2), P(ITM)) sono risk-neutral. Non sono una previsione reale.
4. Sottrai costi, spread e rischio di assegnazione.

### Hard stop sulle opzioni
- Lo stop è obbligatorio. Il livello è scritto nel piano.
- Lo stop si misura sul sottostante o sulla perdita in valuta. Il solo prezzo dell'opzione salta con la IV e con lo spread.
- Un alert serve a eseguire lo stop, non a rimandarlo. Quando il livello rompe, chiudi con un ordine limite: prima al mid, poi verso il prezzo peggiore.
- Un ordine stop a mercato su un'opzione illiquida può eseguire lontano dal mid. Usa ordini limite.

---

## 10. Roll: solo se il nuovo trade passa le regole di entrata

Un roll è due decisioni: chiudere la posizione vecchia e aprire una posizione nuova. Valuta la nuova posizione come un trade nuovo.

### Condizioni (tutte obbligatorie)
1. **Fresh-trade test**: apriresti oggi questa nuova posizione, con questa size, se fossi flat? Se no, chiudi.
2. **Regole di entrata**: la nuova posizione passa le regole della strategia, la liquidità, il calendario eventi e il rischio per trade.
3. **Limite di roll**: massimo 2 roll per posizione. Dopo il secondo roll, chiudi o lascia scadere secondo il piano.
4. **Limite di tenor**: il DTE della nuova gamba short ≤ 2 × il DTE della gamba all'apertura, con un massimo di 90 giorni.
5. **Rischio**: il roll non aumenta R, la perdita di stress o il margine oltre i limiti.

Il credito netto non è un criterio. Un credito può nascondere più rischio: più tempo, più size o uno strike peggiore.

### Confronto chiudere vs rollare

| Voce | Chiudere ora | Rollare |
|---|---|---|
| P&L realizzato oggi (bid/ask) | X | X (uguale: la perdita è già nel prezzo) |
| Nuovo R in valuta e in % dell'equity | 0 | Y |
| Perdita di stress (spot ±20%, IV +10) | 0 | Z |
| Margine di stress | 0 | M |
| Giorni di esposizione aggiunti | 0 | D |
| Valore atteso della nuova posizione | 0 | E (stima dichiarata) |
| Numero del roll | — | n di 2 |

Rolla solo se E > 0 e se Y, Z, M e D rispettano i limiti. Altrimenti chiudi.

**Esempio (STX)**: short put 490 a 44 DTE, rollata su una put 280 a 443 DTE per un credito netto di +$199. Il tenor passa da 44 a 443 giorni: il roll supera il limite di tenor. Il credito non rende il roll accettabile.

---

## 11. Exit ladder (lezione LHX) 🔑

La scala di uscita mostra il costo del tempo. È uno strumento di pianificazione. Non è un trigger.

### Formula
```
P&L totale = P&L realizzato + (valore opzione − entry) × qty × mult
```

### Procedura
1. Calcola il **P&L realizzato** cumulativo di tutte le gambe chiuse.
2. Per ogni livello di P&L totale (−1 R, −0.5 R, 0, +1 R, +2 R), calcola il **valore dell'opzione necessario**: `valore = (P&L target − realizzato) / (qty × mult) + entry`.
3. Con Black-Scholes (o con la catena reale), trova il prezzo del sottostante per quel valore a 2-3 orizzonti (oggi, +60 giorni, +120 giorni).
4. Presenta una tabella:

| P&L target | Valore opzione | Spot oggi (DTE=X) | Spot +60 g | Spot +120 g |
|---|---:|---:|---:|---:|
| −1 R (stop) | X,XX | $XXX | $XXX | $XXX |
| −0.5 R | X,XX | $XXX | $XXX | $XXX |
| 0 | X,XX | $XXX | $XXX | $XXX |
| +1 R | X,XX | $XXX | $XXX | $XXX |

### Principio
> **Il theta rema contro le long.** Ogni mese senza movimento sposta più in alto i livelli della tabella. La tabella a 3 orizzonti mostra questo costo. La decisione usa i trigger della sezione 9: tesi, valore atteso, limiti di rischio e time stop.

---

## 12. Protezione (hedge)

- **Livello**: prezzo del sottostante dove compri la protezione. Scrivilo nel piano.
- **Strumento**: put spread, put, collar.
- **Costo**: confronta il costo della copertura con la perdita di stress che elimina. Il premio incassato in passato non è il budget.
- **Esempio DRAM**: put spread quando il sottostante rompe un supporto chiave con volume.
- Una copertura non sostituisce l'hard stop. La copertura riduce il gap risk. Lo stop limita la perdita.

---

## 13. Checklist operativa (quando una posizione è scomoda)

Esegui in ordine, ogni volta:

1. **[ ] Aggiorna il file posizione** con P&L realizzato e non realizzato, in valuta, in R e in % dell'equity.
2. **[ ] Confronta la perdita attuale con R e con i limiti** della sezione 1.
3. **[ ] Prendi dati freschi**: `analyze_options(legs, expiry)` per le greche, la catena per bid e ask.
4. **[ ] Esegui la checklist di assegnazione, eventi e margine** (sezione 8).
5. **[ ] Controlla la tesi** con VPA/Wyckoff (sezione 6). Il livello di invalidazione è rotto?
6. **[ ] Controlla i trigger** della sezione 9. Un trigger attivo decide l'azione.
7. **[ ] Se pensi a un roll**: applica le condizioni e la tabella della sezione 10.
8. **[ ] Decidi**: tieni secondo il piano, chiudi, riduci, copri o rolla. Non aggiungere a una posizione in perdita.
9. **[ ] Genera il diagramma** con `interactive-trade-diagram`. Usa le colonne di stress IV e il P&L di chiusura bid/ask.
10. **[ ] Registra la decisione** nel file: trigger, motivo, R, % dell'equity, numero del roll.

---

## 14. Metriche di successo

Il risultato si misura contro il piano, non contro la max loss teorica della strategia.

| Metrica | Formula | Uso |
|---|---|---|
| Risultato in R | P&L totale / R pianificato | Ogni trade |
| Risultato in % dell'equity | P&L totale / equity all'entrata | Ogni trade |
| Expectancy | Media dei risultati in R | Su almeno 20 trade |
| Hit rate e payoff | % dei trade in profitto; R medio dei profitti / R medio delle perdite | Su almeno 20 trade |
| Drawdown | Massima discesa della curva cumulata in R | Su tutto il registro |
| Aderenza al piano | % delle uscite con un trigger del piano | Ogni trade |
| Effetto della riparazione | R finale della posizione riparata − R se chiusa alla data della riparazione | Ogni riparazione |

**Esempi reali**:
- **LHX**: bull call spread a debito. R = $947 (il debito, senza stop più stretto). Risultato netto: −$200 = −0.21 R. La regola misura il risultato contro R, non contro una "loss evitata".
- **DRAM**: naked put senza stop e senza R definito. Lezione: senza R non puoi misurare il risultato. Definisci lo stop o la protezione prima dell'entrata.

La "loss evitata" contro la max loss teorica non è una metrica. Su una naked put, ogni perdita sembra un successo.

---

## 15. Anti-pattern (cosa NON fare)

| Errore | Conseguenza | Lezione |
|---|---|---|
| Vendere call coperte con IV rank < 20° percentile | Premio magro, rimbalzo limitato | LHX: non vendere call dopo il crollo a $263 |
| Usare il credito netto come criterio del roll | Più rischio nascosto in tempo e size | Sezione 10: fresh-trade test e limiti |
| Rollare per non realizzare la perdita | La perdita resta e il rischio cresce | La perdita è già nel prezzo di oggi |
| Superare 2 roll o il limite di tenor | Esposizione senza fine | STX: 44 → 443 giorni |
| Aggiungere a una posizione in perdita | Martingala: la size cresce quando la tesi fallisce | Sezione 7 |
| Ancorare l'uscita al break-even o al prezzo di ingresso | Effetto disposizione: tieni le perdite, chiudi i profitti | Sezione 9 |
| Decidere su volumi intraday parziali | Falso segnale | DRAM 31.07: 70M ≠ "volume dimezzato" |
| Non aggiornare il file posizione | Perdi il quadro del P&L cumulativo | Il file è la memoria |
| Aspettare "che torni" senza piano | Il theta e il rischio crescono | LHX: −$5.26/giorno |
| Fidarsi ciecamente di yfinance | Dati errati, decisioni errate | Sezione 5 |
| Rimandare l'hard stop con un alert | La perdita supera R | Sezione 9 |
| Tenere una short ITM prima dell'ex-dividend | Assegnazione anticipata | Sezione 8 |
| Misurare il successo come "loss evitata" | Ogni riparazione sembra un successo | Sezione 14 |

---

## Riferimenti incrociati

- **options-playbook** (`patterns.md`, pattern 13 e 14): audit delle gambe, take profit, hard stop, time stop, regola degli eventi, limite di roll.
- **interactive-trade-diagram**: scenari con stress di IV, P&L di chiusura bid/ask, zone e break-even.
- **option-volatility-pricing**: greche, theta, smile, early exercise (cap. 16).
- **volume-price-analysis**: glossario canonico VPA/Wyckoff/Volume Profile.
- **wyckoff-2-0**: qualificazione di accumulazione e distribuzione.
- **trading-in-the-zone**: disciplina nel chiudere una perdita, nessuna agenda per "tornare in pari".
- **evidence-based-technical-analysis**: non fare data-mining dei pattern di rimbalzo.
