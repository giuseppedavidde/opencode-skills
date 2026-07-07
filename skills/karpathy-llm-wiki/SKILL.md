---
name: karpathy-llm-wiki
description: "Use when building or maintaining a personal LLM-powered knowledge base. Triggers: ingesting sources into a wiki, querying wiki knowledge, linting wiki quality, 'add to wiki', 'what do I know about', 'wiki-ingest', 'wiki-query', 'wiki-lint', or any mention of 'LLM wiki' or 'Karpathy wiki'."
allowed-tools:
  - read
  - write
  - bash
  - glob
  - grep
  - webfetch
orchestrator:
  parallel: false
---

# Karpathy LLM Wiki

Build and maintain a personal knowledge base using LLMs. Based on the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy, implemented by the [llm-wiki-newsroom](https://github.com/alfadur7/llm-wiki-newsroom) framework.

Core idea: the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources. The wiki is a persistent, compounding artifact.

## Three-Layer Architecture

- **raw/** — Immutable source documents (articles, papers, images). The LLM reads but never modifies.
- **wiki/** — LLM-generated markdown files. Summaries, entities, concepts, cross-references. The LLM owns this layer.
- **Schema** — These instructions tell the LLM how to structure the wiki.

## Directory Structure

```
raw/          # Source documents (immutable)
wiki/         # Agent-maintained knowledge base
  index.md    # Page catalog
  overview.md # Living synthesis
  sources/    # Per-source summaries
  entities/   # People, companies, projects
  concepts/   # Ideas, frameworks, methods
  overviews/  # Cluster landscape overviews
  contradictions/ # Conflict analysis
  syntheses/  # Saved query answers
  timelines/  # Chronological hubs
  trails/     # Associative paths (Memex)
graph/        # Knowledge graph (auto-generated)
tools/        # Python scripts (no API keys needed)
```

## Key Operations

1. **Ingest** (`/wiki-ingest <file>`) — Read a source → write summary → update entities/concepts → rebuild graph → lint
2. **Query** (`/wiki-query <question>`) — Search wiki → synthesize answer with [[wikilinks]] citations
3. **Lint** (`/wiki-lint [--fix]`) — Health check: broken links, orphans, contradictions, stale summaries
4. **Graph** (`/wiki-graph`) — Build/rebuild knowledge graph from wiki pages
5. **Discover** (`/wiki-discover <seed>`) — Find unexpected connections via graph traversal

## Tools

Python scripts in `tools/` run locally (no API keys):
- `python tools/build.py` — rebuild graph, clusters, index
- `python tools/lint.py` — health-check groups
- `python tools/query.py graph path|neighbors|explain` — graph queries
- `python tools/discover.py surprising` — bridge-hub ranking

## Page Format

Every wiki page uses frontmatter:
```yaml
---
title: "Page Title"
type: source | entity | concept | synthesis | trail | timeline | overview | contradiction
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

Use `[[PageName]]` wikilinks for cross-references.

## Log

Append to `log.md`: `## [YYYY-MM-DD] <operation> | <Title>`

For the full 5-role multi-agent workflow with self-evolving guidelines, see `.claude/` and `CLAUDE.md` in the upstream submodule at `skills/karpathy-llm-wiki-src/`.
