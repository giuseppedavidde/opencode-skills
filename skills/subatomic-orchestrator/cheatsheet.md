# Cheatsheet — Subatomic Orchestrator

## Quick Start

```bash
# Scan 5 mercati EU in parallelo
/orchestrate --skills market-accumulation-scanner \
  --items italy,germany,france,uk,spain --split-by market --top 10

# Deep dive 3 ticker in parallelo
/orchestrate --skills stock-crypto-analysis \
  --items DBK.DE,SGRO.L,PST.MI --split-by ticker --top 3

# Pipeline completa
/orchestrate --pipeline \
  --phase-1 "wallstreetbets-pump-detect --top 3" \
  --phase-2 "stock-crypto-analysis --split-by ticker" \
  --phase-3 "options-strategy-suggestions --split-by ticker"
```

## Orchestrator Frontmatter Reference

```yaml
orchestrator:
  parallel: true|false           # abilita parallel dispatch
  delegated: true|false          # true = skill già parallela, non toccare
  split_by: ticker|market|file|chapter|query|none
  chunk_size: N                  # items per chunk
  merge: rank|concat|json_merge|none
  merge_key: field_name          # sorting key for rank mode
  top_n: N                       # top results to return
  type: kb|action|hybrid         # natura della skill
```

## Dispatch Mechanism Selector

| Chunk Size | Items per Agent | Meccanismo | Output |
|:----------:|:---------------:|------------|--------|
| 1 | 1 ticker/analysis | `task` tool | JSON diretto |
| 2-4 | 2-4 item | `task` tool | JSON diretto |
| 5-20 | Scanner batch | `@agent` mention | File su disco |
| 20+ | Data fetch | `@agent` mention | File su disco |

## Merge Mode Selector

| Mode | Quando usarlo | Esempio |
|------|--------------|---------|
| `rank` | Risultati con score numerico | Scanner, analysis |
| `concat` | Array di risultati senza ranking | Multi-fetch, multi-analysis |
| `json_merge` | Oggetti con nodi/edges | Graph extraction |
| `none` | Output non aggregabile | Per-file processing |

## Default Chunk Sizes

| split_by | Default | Note |
|----------|:-------:|------|
| ticker (scan) | 15 | Come batch-size dello scanner |
| ticker (analysis) | 1 | Ogni analysis è complessa |
| market | 1 | 1 agent per market |
| file | 20 | Come graphify chunks |
| chapter | 1 | Generazione 1 chapter per agent |
| query | 1 | Ogni fetch è veloce |

## Parallel Limit & Timing

```
parallel_limit = 8             # default, configurabile --parallel-limit N
time_per_item = 2s             # scanner medio per ticker
time_per_analysis = 50s        # analysis completa per ticker

agents      = ceil(items / chunk_size)
batches     = ceil(agents / parallel_limit)
wall_time   = batches × chunk_size × time_per_item
```

## Error Handling

```
chunk_mancante   → warn + skip
json_invalido    → warn + skip
> 50% falliti    → STOP + suggerisci serial fallback
skill_no_orch    → run infer.py, fallback a singola esecuzione
```

## Scripts

```bash
# Scoprire metadati di una skill
python3 scripts/infer.py ../stock-crypto-analysis/SKILL.md

# Calcolare chunk per dispatch
python3 scripts/dispatch.py --items-count 250 --chunk-size 15

# Aggregare risultati
python3 scripts/aggregate.py --input /tmp/orch_*.json --mode rank --key score --top 10
```

## Speedup Atteso

| Workload | Items | Sequenziale | Orchestrato | Speedup |
|----------|:----:|:-----------:|:-----------:|:-------:|
| EU scan | 250 | 180s | 35s | **5x** |
| US scan | 500 | 360s | 50s | **7x** |
| Deep dive 6 ticker | 6 | 360s | 70s | **5x** |
| Pipeline WSB+analysis | — | 300s | 120s | **2.5x** |
| Multi-query | 4 | 8s | 2s | **4x** |
