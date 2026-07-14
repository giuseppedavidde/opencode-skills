---


name: subatomic-orchestrator
description: >
  Meta-skill that decomposes any workload into independent sub-tasks, dispatches
  them to parallel agents, and aggregates results. Works with any opencode skill
  that declares orchestrator frontmatter. Use when: scanning multiple markets,
  analyzing multiple tickers, processing multiple files, or any embarrassingly
  parallel task across existing skills.

metadata:
  argument-hint: "/orchestrate --skills <skill1,skill2> --items <item1,item2,...> [--split-by ticker|market|file|chapter|query] [--top N] [--pipeline]"
---

# Subatomic Orchestrator

Meta-skill per decomporre workload in agenti paralleli e riaggregare i risultati.
Non esegue task direttamente — orchestra skill esistenti.

## How It Works — 4 Phase Cycle

```
┌─────────────────────────────────────────────────────┐
│ 1. DISCOVERY                                       │
│    Legge il frontmatter orchestrator: della skill   │
│    target (o inferisce da struttura)                │
│    ↓                                                │
│ 2. DECOMPOSITION                                    │
│    Split input items in chunk secondo split_by      │
│    Calcola numero agenti, chunk_size, parallel_batch │
│    ↓                                                │
│ 3. DISPATCH                                         │
│    Lancia tutti gli agent in parallelo              │
│    • task tool per chunk piccoli (JSON diretto)      │
│    • @agent mention per chunk grandi (file su disco) │
│    ↓                                                │
│ 4. AGGREGATION                                      │
│    Merge risultati: rank | concat | json_merge | none│
│    Sort, dedup, top_n                               │
└─────────────────────────────────────────────────────┘
```

## Discovery — Come Legge le Skill

Legge il frontmatter `orchestrator:` di qualsiasi SKILL.md.

**Sezione orchestrator già presente** (skill già adattate):
```yaml
orchestrator:
  parallel: true                  # false = non parallelizzabile
  delegated: true                 # true = già gestisce il suo parallelismo
  split_by: ticker                # ticker | market | file | chapter | query | none
  chunk_size: 15                  # items per chunk
  merge: rank                     # rank | concat | json_merge | none
  merge_key: final_score          # chiave per ordinamento
  top_n: 15                       # top risultati da restituire
  type: kb                        # kb = knowledge base (solo contesto)
```

**Sezione assente** → `scripts/infer.py` analizza:
| Pattern in SKILL.md | Inferenza |
|---|---|
| `--tickers` o `--universe` in script CLI | `split_by: ticker` |
| `--files` o `--source` | `split_by: file` |
| Capitoli numerati | `split_by: chapter` |
| `final_score` o `score` in output | `merge: rank`, `merge_key: score` |
| Nessun argomento iterabile | `parallel: false` |

## Patterns Disponibili

### Pattern 1: Batch Analysis (`/orchestrate --split-by ticker`)

N item indipendenti → M chunk → M agent in parallelo → merge sorted.

```
/orchestrate --skills stock-crypto-analysis \
  --items DBK.DE,SGRO.L,PST.MI --split-by ticker --top 3
```

| Chunk | Default | Min |
|-------|:-------:|:---:|
| Scansione mercati | 15/chunk | 5 |
| Deep dive analysis | 1/chunk | 1 |
| File processing | 20/chunk | 5 |
| Chapter generation | 1/chunk | 1 |

### Pattern 2: Market Scan (`/orchestrate --split-by market`)

1 agent per market indipendente, merge globale sorted per score.

```
/orchestrate --skills market-accumulation-scanner \
  --items italy,germany,france,uk,spain --split-by market --top 10
```

### Pattern 3: Multi-Skill Pipeline (`/orchestrate --pipeline`)

Fasi sequenziali, ogni fase parallelizzata internamente.

```
/orchestrate --pipeline \
  --phase-1 "wallstreetbets-pump-detect --top 3" \
  --phase-2 "stock-crypto-analysis --split-by ticker" \
  --phase-3 "options-strategy-suggestions --split-by ticker"
```

### Pattern 4: Multi-Query Research (`/orchestrate --split-by query`)

Fetch parallelo di dati indipendenti dalla stessa skill.

```
/orchestrate --skills market-data-fetch \
  --items "P/E DBK.DE,SI DBK.DE,inst DBK.DE" --split-by query
```

## Dispatch Mechanisms

### task tool (default, chunk < 5 items)
Ogni agente torna JSON direttamente. Merge immediato.
```
task("Run {skill} on: {items}. Return JSON array with keys: {merge_keys}")
```

### @agent mention (chunk >= 5 items)
Ogni agente scrive su disco. Merge via aggregate.py.
```
@agent Chunk 1 of M: Run {skill} on {items}. Write /tmp/orch_chunk_1.json
@agent Chunk 2 of M: Run {skill} on {items}. Write /tmp/orch_chunk_2.json
```

### Misto (pipeline mode)
```
Fase 1: task agent per fetch parallelo
Fase 2: main session fa merge + decide prossima fase
Fase 3: task agent per analisi parallela
```

## Performance Model

| Scenario | Items | Chunk | Agenti | Sequenziale | Parallelo | Speedup |
|----------|-------|-------|--------|:-----------:|:---------:|:-------:|
| Scanner EU (5 mercati) | 250 | 15 | ~17 | ~3 min | ~35s | **5x** |
| Deep dive 6 ticker | 6 | 1 | 6 | ~6 min | ~70s | **5x** |
| Pipeline WSB→analysis→options | — | — | ~7 | ~5 min | ~2 min | **2.5x** |
| Multi-query research | 4 query | 1 | 4 | ~8s | ~2s | **4x** |
| Full scan US+EU | ~900 | 15 | ~60 | ~10 min | ~75s | **8x** |

Il parallel_limit effettivo dipende dal provider LLM. Default: 8 agent simultanei.

## Result Aggregation

Ogni agente produce un JSON. `scripts/aggregate.py` li unisce:

### rank mode
```python
def merge_rank(files, key="score", top_n=15):
    """Sort by key desc, take top N."""
    all_results = []
    for f in files:
        all_results.extend(json.load(open(f)))
    return sorted(all_results, key=lambda x: x[key], reverse=True)[:top_n]
```

### concat mode
```python
def merge_concat(files):
    """Simply concatenate arrays."""
    all_results = []
    for f in files:
        all_results.extend(json.load(open(f)))
    return all_results
```

### json_merge mode
```python
def merge_json(files):
    """Merge JSON objects (nodes+edges style)."""
    merged = {"nodes": [], "edges": [], "hyperedges": []}
    for f in files:
        d = json.load(open(f))
        for k in merged:
            merged[k].extend(d.get(k, []))
    return merged
```

## Error Handling

| Condizione | Azione |
|-----------|--------|
| Chunk file mancante | Warn, continua (non abortire) |
| Agente torna JSON invalido | Warn, skip chunk |
| > 50% chunk falliti | Stop. Suggerisci chunk più piccoli o serial fallback |
| Skill non ha orchestrator | Usa infer.py, se fallisce → esecuzione singola |

## Anti-Patterns

- **Non** parallelizzare task intrinsecamente sequenziali (debug, analisi multi-fase dello stesso asset)
- **Non** usare chunk < 3 item salvo analysis complesse — overhead dispatch > gain
- **Non** ignorare partial failure — documenta sempre quanti chunk hanno fallito
- **Non** usare `--pipeline` per task che non hanno fasi distinte
- **Non** omettere `--merge-key` quando `merge: rank` — senza non sa cosa ordinare

## Scripts

```
scripts/infer.py      → Legge SKILL.md, estrae/indovina metadati orchestrator
scripts/dispatch.py   → Calcola chunk, genera prompt per task tool / @agent
scripts/aggregate.py  → Merge risultati da N agenti (rank | concat | json_merge)
```

## CLI Usage

```bash
python3 scripts/infer.py ../stock-crypto-analysis/SKILL.md
python3 scripts/dispatch.py --items-count 250 --chunk-size 15 --parallel-limit 8
python3 scripts/aggregate.py --input /tmp/orch_chunk_*.json --mode rank --key score --top 10
```
