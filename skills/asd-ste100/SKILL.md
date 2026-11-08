---
name: asd-ste100
description: "Direttiva di scrittura ASD-STE100 (Simplified Technical English) per tutti gli agenti del workflow. Impone limiti di frase, voce attiva, tempi semplici, un termine per concetto, liste verticali e numeri esatti. Usa questa skill quando scrivi o revisioni un output di agente: analisi, repair, report, piani atomici, risposte di routing, messaggi di commit, testo dentro diagrammi HTML. Trigger: ASD-STE100, STE100, simplified technical english, scrivi in STE, controlla STE, riscrivi in STE, direttiva di scrittura, stile agenti."
allowed-tools: [read, grep, edit, write]
metadata:
  argument-hint: "[checklist | rewrite | regole | agenti]"
---

# ASD-STE100 — Direttiva di scrittura per il workflow agenti

Questa skill è la fonte unica della direttiva di scrittura.
Ogni agente applica la direttiva a tutto il testo che produce.
Il codice, i comandi, i nomi dei tool, i ticker e le citazioni restano esatti.

---

## 1. Ambito

| Superficie | Soggetta | Note |
|---|---|---|
| Chat e riassunti | Sì | Ogni agente, ogni risposta |
| Blocco `## VERIFICA` | Sì | Stesse regole della chat |
| Testo dentro diagrammi HTML | Sì | Titoli, etichette, note, legenda |
| Piani atomici di `coder_planner` | Sì | Passi brevi, un'azione per passo |
| Messaggi di commit e report | Sì | Oggetto e corpo |
| Contenuto di skill generate | Sì | `book-to-skill-agent` |
| Codice sorgente | No | Il codice non si riscrive per stile |
| Nomi di tool, path, ticker, API | No | Restano identici, senza traduzione |
| Testo citato da un documento | No | Citazione letterale, tra virgolette |
| Output di tool e JSON | No | Si riportano come sono |

Se una regola di questa direttiva confligge con un formato richiesto da un tool,
vince il formato del tool. Il testo intorno segue la direttiva.

---

## 2. Limiti rigidi

Questi limiti valgono per l'italiano e per l'inglese.

| Regola | Limite |
|---|---|
| Parole per frase, procedura o istruzione | massimo 20 |
| Parole per frase, descrizione o spiegazione | massimo 25 |
| Frasi per paragrafo | massimo 6 |
| Idee per frase | 1 |
| Azioni per passo di procedura | 1 |
| Parole per nome composto | massimo 3 |
| Termini diversi per lo stesso concetto | 1 |
| Punti e virgola tra due proposizioni | 0 |
| Contrazioni | 0 |
| Modi di dire, metafore, slang | 0 |

Se una frase supera il limite, si divide in due frasi.
Se un paragrafo supera 6 frasi, si apre un paragrafo nuovo.

---

## 3. Regole di scrittura

| Regola | Cosa fare | Cosa non fare |
|---|---|---|
| Voce attiva | "Il broker registra la perdita." | "La perdita viene registrata." |
| Tempi semplici | Presente, passato prossimo, futuro semplice. | Congiuntivo, condizionale composto, trapassato. |
| Verbo preciso | `usa`, `calcola`, `verifica`, `chiudi`, `leggi`, `confronta`. | `effettuare`, `provvedere`, `implementare`, `eseguire la verifica di`. |
| Un termine, un senso | `mark` solo per il valore di mercato. | `mark`, `prezzo`, `quotazione` per la stessa cosa. |
| Positivo | "Tieni la posizione aperta." | "Non chiudere la posizione." |
| Istruzione diretta | "Apri il file." | "Sarebbe meglio aprire il file." |
| Lista verticale | Una procedura va in lista numerata. | Procedura dentro un paragrafo. |
| Numero esatto | `−$3,383.54`, `+8.2%`, `45 DTE`. | "circa tremila", "un po' su", "parecchio". |
| Abbreviazione definita | "BE = break-even" alla prima occorrenza. | `BE` senza spiegazione. |
| Un tema per paragrafo | Un paragrafo, un argomento. | Tre argomenti nello stesso paragrafo. |
| Nessun avverbio di enfasi | "La perdita è elevata." | "La perdita è davvero enorme." |
| Nessuna domanda retorica | "Verifica il rischio." | "Chi non verificherebbe il rischio?" |

Eccezioni ammesse per la voce passiva: solo quando l'agente non è noto o non è rilevante.
Eccezione ammessa per `non`: solo in avvisi e divieti. Esempio: "Non superare il 2% di rischio."

---

## 4. Output in inglese — disciplina del dizionario

Quando l'output è in inglese, vale il dizionario ASD-STE100, Parte 2.

1. Usa una parola approvata. Se la parola non è approvata, usa l'alternativa approvata.
2. I nomi tecnici e i verbi tecnici sono ammessi senza limite. Esempio: `strike`, `delta`, `break-even`, `LightGBM`.
3. Un nome composto ha massimo 3 parole. Esempio: `option expiry date`, non `date of the expiry of the option`.
4. Verbi: solo forme approvate. Voce attiva. Tempi semplici.
5. Non usare la forma in `-ing` come verbo. Usa il sostantivo tecnico o una frase semplice.
6. Non usare `shall`, `should`, `may`, `might` per un'istruzione. Usa l'imperativo.
7. Un termine, un senso, per tutto il documento.

| Non approvato | Approvato |
|---|---|
| `utilize`, `employ` | `use` |
| `commence`, `initiate` | `start` |
| `terminate` | `stop` o `end` |
| `ascertain` | `check` |
| `in the event that` | `if` |
| `prior to` | `before` |
| `subsequent to` | `after` |
| `is able to` | `can` |
| `it is necessary to` | `you must` |
| `a large number of` | `many` |

---

## 5. Output in italiano — regole equivalenti

Il dizionario ASD-STE100 vale per l'inglese. Per l'italiano si applicano i limiti
della sezione 2 e le regole della sezione 3, con queste sostituzioni.

| Evita | Usa |
|---|---|
| `effettuare`, `eseguire` | `fai`, `calcola`, `verifica` |
| `provvedere a` | `fai` |
| `implementare` (fuori dal codice) | `crea`, `aggiungi` |
| `ottimizzare` senza metro | `riduci X a Y` |
| `significativo`, `considerevole` | il numero esatto |
| `al fine di` | `per` |
| `in merito a`, `relativamente a` | `su`, `per` |
| `nonché` | `e` |
| `qualora` | `se` |
| `si rende necessario` | `devi` |
| `è opportuno` | `fai` |

Un nome tecnico inglese resta in inglese. Esempi: `strike`, `expiry`, `roll`, `break-even`, `drawdown`.
Non tradurre due volte lo stesso termine. Scegli una forma e mantienila.

---

## 6. Formati

### Procedura
Numera i passi. Un'azione per passo. Verbo all'imperativo.

```markdown
1. Apri il file `positions.json`.
2. Leggi il campo `legs`.
3. Calcola il payoff a scadenza.
```

### Avviso
Inizia con il rischio, poi l'azione. Massimo 20 parole.

```markdown
**Attenzione:** il rischio massimo supera il 2% del capitale. Riduci il numero di contratti.
```

### Tabella
Una metrica per colonna. Intestazione breve. Numeri con unità nella cella.

### Diagramma HTML
Titoli ed etichette seguono la stessa direttiva. Massimo 25 parole per nota.
Le etichette dei grafici usano il termine tecnico, non una frase.

### Blocco `## VERIFICA`
Quattro righe. Ogni riga è una frase breve. Nessun aggettivo di enfasi.

---

## 7. Controllo prima della consegna

Esegui questo controllo su ogni risposta prima di inviarla.

1. Ogni frase di procedura ha massimo 20 parole.
2. Ogni frase descrittiva ha massimo 25 parole.
3. Ogni paragrafo ha massimo 6 frasi.
4. La voce è attiva, salvo le eccezioni della sezione 3.
5. I tempi sono semplici.
6. Lo stesso concetto ha lo stesso nome in tutta la risposta.
7. Le procedure sono liste numerate.
8. Ogni numero ha la sua unità e non è arrotondato a parole.
9. Ogni abbreviazione è definita alla prima occorrenza.
10. Non ci sono modi di dire, metafore o enfasi.

Se un punto fallisce, riscrivi la frase. Non inviare la risposta con il punto aperto.

---

## 8. Esempi di riscrittura

| Prima | Dopo |
|---|---|
| "La posizione sta sanguinando e sarebbe opportuno effettuare un roll per evitare che vada completamente a zero." | "La posizione perde. Fai un roll. Il roll riduce lo strike. Il rischio di azzeramento scende." |
| "A seguito dell'analisi effettuata, si è potuto constatare che la volatilità implicita risulta essere significativamente superiore alla volatilità realizzata." | "L'IV è 34%. La RV è 22%. L'IV supera la RV di 12 punti. Il premio è alto." |
| "It should be noted that the position could potentially be adjusted in the event that the price falls below the strike." | "The price is below the strike. Adjust the position." |
| "Non è da escludere l'ipotesi di un peggioramento del quadro macro." | "Il quadro macro può peggiorare." |
| "Effettua la verifica del margine prima di procedere all'invio dell'ordine." | "Verifica il margine. Poi invia l'ordine." |

---

## 9. Applicazione per agente

| Agente | Superfici soggette | Nota |
|---|---|---|
| `router` | Classificazione, riassunto, domanda di chiarimento | Massimo 3 righe per riassunto. Nessun preambolo. |
| `coder` | Prosa, messaggi di commit, note di modifica | Il codice e i commenti richiesti restano fuori. |
| `coder_planner` | Passi atomici, dettagli, verifica | Un'azione per passo. Nessuna frase composta. |
| `graphify_helper` | Report, numeri, prossimi passi | Numeri esatti di nodi e archi. |
| `pdf_reader` | Analisi, citazioni, caveat | La citazione resta letterale. La frase intorno è STE. |
| `skill_updater` | Report di aggiornamento, note | Commit e hash riportati esatti. |
| `book-to-skill-agent` | Contenuto delle skill generate | I framework restano completi. La prosa è STE. |
| `trade` | Analisi, verdetto, testo del diagramma | Numeri da tool. Nessuna stima a parole. |

---

## 10. Dove è collegata la direttiva

1. `skills/asd-ste100/SKILL.md` — questa skill, fonte unica.
2. `agents/*.md` — blocco obbligatorio in ogni agente.
3. `config/AGENTS.md` — regola globale.
4. `skills/interactive-trade-diagram/SKILL.md` — regole del diagramma.
5. `scripts/ste_conformance.py` — test di conformità. Controlla il cablaggio e misura il testo.

Se una regola cambia, cambia qui. Gli agenti leggono questa skill.
