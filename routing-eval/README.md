# OpenCode Router Evaluation Harness

Misura l'accuratezza delle decisioni di routing del router di OpenCode (delegazione a subagent specialisti).

> Questo progetto vive dentro il repo `opencode-skills` (`routing-eval/`) ed è
> installato come symlink in `~/.config/opencode/routing-eval/`. I percorsi qui
> sotto sono relativi; nessun path macchina-specifico è hardcoded.

## Quick Start

```bash
# Lavora dal symlink installato o direttamente dal repo (stesso contenuto)
cd ~/.config/opencode/routing-eval
/tmp/opencode/.venv/bin/pip install -r requirements.txt

# Esegui entrambe le valutazioni
/tmp/opencode/.venv/bin/python run_eval.py --all
```

## Modalità

| Flag | Descrizione |
|---|---|
| `--history` | Replay del classificatore su TUTTE le sessioni storiche nel DB |
| `--golden`  | Precision/recall/F1 su golden set curato (60 casi) |
| `--all`     | Entrambe le modalità |

Opzionale: `--output-dir /path/to/dir` per specificare la directory dei report.

## Output

- **Terminale**: tabella riassuntiva con accuracy, misrouting rate, metriche per categoria, confusion matrix, top 10 misrouted cases.
- **`data/reports/history_report_*.json`**: report completo con tutti i dettagli.
- **`data/reports/golden_report_*.json`**: report completo golden set.
- **`data/misrouted_report.jsonl`**: tutte le query misclassificate (replay storico) per revisione manuale.
- **`data/history_dataset.jsonl`**: dataset storico estratto dal DB (riutilizzabile, non richiede il DB dopo la prima estrazione).

## Come interpretare i numeri

- **Accuracy**: percentuale di decisioni corrette rispetto al comportamento reale.
- **Misrouting rate**: 1 - accuracy. Se >20% c'è un problema sistematico.
- **Precision per categoria**: tra tutte le query classificate come X, quante erano davvero X.
- **Recall per categoria**: tra tutte le query che dovevano essere X, quante sono state correttamente classificate.
- **F1**: media armonica di precision e recall.

Categorie target:
- **TRADE**: delegato a @trade
- **CODER**: delegato a @coder
- **GRAPHIFY**: delegato a @graphify_helper
- **SKILL_UPDATER**: delegato a @skill_updater
- **BOOK_TO_SKILL**: delegato a @book-to-skill-agent
- **SIMPLE**: gestito direttamente dal router (nessuna delega)

## Aggiungere casi al golden set

Modifica `data/golden_set.json` e aggiungi un nuovo oggetto:

```json
{
  "id": 31,
  "text": "la tua nuova richiesta utente qui",
  "expected": "TRADE",
  "note": "perché questa è la categoria giusta",
  "category": "TRADE"
}
```

Il campo `multiplicity` (opzionale, default 1) viene calcolato automaticamente dal classificatore: conta il numero di oggetti indipendenti nella richiesta (ticker multipli, più nomi skill, più file/moduli). Per i casi multi-oggetto, il reason conterrà il flag `→ multi:N`.

Poi rilancia `python run_eval.py --golden`.

## Aggiornare il classificatore

Il classificatore in `src/classifier.py` replica le regole keyword-based del router. Quando il router reale viene aggiornato (cambiano trigger keyword o priorità), aggiorna gli array di keyword in `classifier.py`:

- `TRADE_KEYWORDS` / `TRADE_EXACT`: keyword di trading
- `CODER_KEYWORDS`: keyword di coding complesso
- `GRAPHIFY_KEYWORDS` / `GRAPHIFY_EXACT`: keyword di graphify
- `SKILL_UPDATER_KEYWORDS`: keyword di aggiornamento skill
- `BOOK_TO_SKILL_KEYWORDS`: keyword di conversione libri

L'ordine di priorità è: trade > skill_updater > book_to_skill > graphify (exact) > graphify > coder > simple.

## Struttura del progetto

```
routing-eval/
├── run_eval.py          # CLI runner (entry point)
├── conformance_test.py  # Test di conformità del classificatore
├── stats_report.py      # CLI telemetria live (/routing-stats)
├── requirements.txt     # Pydantic v2
├── src/
│   ├── models.py        # Pydantic v2 data models
│   ├── extractor.py     # DB extraction → history_dataset.jsonl
│   ├── live_stats.py    # Aggregazione telemetria live
│   └── classifier.py    # RouterClassifier (keyword-based rules)
├── data/
│   ├── golden_set.json          # 30 casi curati per regression testing
│   ├── history_dataset.jsonl    # Dataset storico esportato
│   ├── misrouted_report.jsonl   # Casi di misrouting per revisione
│   └── reports/                 # Report JSON generati
└── README.md
```

## Dependencies

- Python 3.10+
- Pydantic v2 (`pip install -r requirements.txt`)
- SQLite3 (built-in)

Usa il venv condiviso: `/tmp/opencode/.venv`
