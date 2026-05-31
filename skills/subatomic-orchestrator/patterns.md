# Patterns — Subatomic Orchestrator

## Pattern 1: Batch Analysis

**When**: N item indipendenti (ticker, file, query) da processare con la stessa skill.

**Split strategy**: `ceil(N / chunk_size)` chunk, ogni chunk contenente `chunk_size` item.

**Agent prompt template** (task tool):
```
Run {skill_name} on these items: {item_list}.
Return a JSON array of results. Each result must have keys: {merge_keys}.
Output ONLY valid JSON, no explanation.
```

**Agent prompt template** (@agent, chunk >=5):
```
@agent Chunk {n} of {total}: Run {skill_name} on these items: {item_list}.
Write results to /tmp/orch_chunk_{n}.json as a JSON array.
Each result must have keys: {merge_keys}.
Output ONLY valid JSON.
```

**Result contract** (per item):
```json
{
  "symbol": "DBK.DE",
  "score": 76,
  "wyckoff": 90,
  "volprof": 70,
  ...
}
```

**Aggregation**: `rank` mode — sort by `merge_key` desc, take `top_n`.

**Error handling**: Se un chunk fallisce, warn e skip. Se >50% falliti, abort.

**Performance**:
```
agents = ceil(N / chunk_size)
wall = ceil(agents / parallel_limit) * chunk_size * time_per_item
```

---

## Pattern 2: Market Scan

**When**: Scansione multi-mercato dove ogni mercato è indipendente.

**Split strategy**: 1 agent per market. I market sono noti (italy, germany, etc.).

**Agent prompt template**:
```
Run market-accumulation-scanner on the {market_name} universe.
Return top {top_n} candidates as a JSON array sorted by final_score descending.
Include: symbol, name, final_score, wyckoff, volprof, pa, sentiment, fundamentals, pattern.
```

**Result contract**:
```json
[{"symbol": "DBK.DE", "final_score": 66.0, ...}, ...]
```

**Aggregation**: `rank` mode — merge tutti i risultati, sort by `final_score` desc, take global `top_n`.

**Edge case**: Se un mercato non ha dati (tutti falliti), skip silenziosamente.

**Example payload**:
```
items = ["italy", "germany", "france", "uk", "spain"]
chunks = [["italy"], ["germany"], ["france"], ["uk"], ["spain"]]
agents = 5
parallel_batches = ceil(5 / 8) = 1
wall_time ≈ 30s (max scan singolo) + 2s merge
```

---

## Pattern 3: Multi-Skill Pipeline

**When**: Workflow con fasi sequenziali, ogni fase parallelizzata internamente.

**Split strategy**: Per fase.

```
Fase 1 (fetch/scan)     → parallelo
Fase 2 (analyze)        → parallelo (dipende da risultati Fase 1)
Fase 3 (suggest/report) → parallelo (dipende da risultati Fase 2)
```

**Agent prompt template** (Fase 1):
```
Run {skill_1} and return top {top_n} candidates.
```

**Agent prompt template** (Fase 2, dopo merge Fase 1):
```
Run {skill_2} on each of: {top_candidates_from_phase_1}.
```

**Agent prompt template** (Fase 3, dopo merge Fase 2):
```
Run {skill_3} on each of: {top_candidates_from_phase_2}.
```

**Aggregation**: Per fase si usa merge appropriato (rank o concat).

**Dependency tracking**:
```
phase_1_output = dispatch(skill_1, items_all)
phase_1_merged = aggregate(phase_1_output, rank, score, top_3)
phase_2_output = dispatch(skill_2, phase_1_merged)
phase_2_merged = aggregate(phase_2_output, rank, score, top_3)
phase_3_output = dispatch(skill_3, phase_2_merged)
final_result = aggregate(phase_3_output, concat)
```

**Error handling**: Se Fase 1 fallisce, pipeline si ferma. Se una branch di Fase 2 fallisce, le altre continuano.

**Example**: WSB pump detect → stock-crypto-analysis → options-strategy-suggestions

---

## Pattern 4: Multi-Query Research

**When**: Fetch parallelo di dati indipendenti dalla stessa skill.

**Split strategy**: 1 query per agent. Ogni query è una richiesta atomica.

**Agent prompt template**:
```
Using {skill_name}, fetch: {query}.
Return the result as a JSON object: {"query": "...", "result": ...}
```

**Result contract**:
```json
{"query": "P/E DBK.DE", "result": 8.8}
{"query": "SI DBK.DE", "result": 0.05}
```

**Aggregation**: `concat` mode — assemblea tutti i risultati in un unico oggetto.

**Performance**:
```
agents = N queries
wall = max(time_per_query) ≈ 2s (API calls paralleli)
```

---

## Pattern Selection Matrix

| Hai | Usa Pattern | split_by | merge |
|-----|------------|----------|-------|
| N ticker da analizzare | Batch Analysis | ticker | rank |
| N mercati da scan | Market Scan | market | rank |
| Workflow multi-fase | Pipeline | per fase | vario |
| N query indipendenti | Multi-Query | query | concat |
| N file da processare | Batch Analysis | file | concat |
| N capitoli da generare | Batch Analysis | chapter | none |

## Serial Fallback

Se il dispatch parallelo fallisce (troppi chunk persi):

1. Esegui 1 chunk alla volta nella sessione principale
2. Ogni chunk: leggi items, esegui skill, produci stesso JSON
3. Salva in `/tmp/orch_chunk_N.json`
4. Merge normalmente con aggregate.py

```python
def serial_fallback(items, chunk_size, skill_fn):
    results = []
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i+chunk_size]
        result = skill_fn(chunk)  # esecuzione singola
        results.append(result)
    return merge_rank(results)  # o merge concat / json
```
