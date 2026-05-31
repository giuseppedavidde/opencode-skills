---
name: book-to-skill-bridge
description: "Auto-generates OpenCode skills from books/documents. Wraps book-to-skill with zero interactive prompts: auto-detects book type (technical/text), auto-extracts title/author, generates skill files in ~/.config/opencode/skills/<slug>/. Supports parallel batch processing for multiple books. Use when you want to convert a book to a skill without answering questions."
allowed-tools:
  - bash
  - read
  - write
  - glob
  - grep
  - task
  - todowrite
  - question
argument-hint: <path-to-document> [skill-name-slug]  or  --batch <directory>
orchestrator:
  parallel: true
  delegated: true
  split_by: book
---

# Book-to-Skill Bridge v2 — Parallel Batch Edition

Auto-generates OpenCode skills from books with zero interactive prompts.
Wraps `book-to-skill` and pre-resolves all interactive choices automatically.

**v2 improvement**: parallel extraction + per-book 2-agent split for content generation.
Processing N books takes ~same wall time as 1 book.

## How It Differs from book-to-skill

| Feature | book-to-skill | book-to-skill-bridge v2 |
|---|---|---|
| Book type | Asks user | Auto-detects from text |
| Purpose | Asks user | Preset "all of the above" |
| Skill name | Proposes, asks | Auto-slug from title or explicit |
| Proceed confirm | Asks user | Auto-proceed |
| Install missing pkgs | Asks user | `--install-missing no` |
| Batch processing | No | Yes — `--batch <dir>` or multiple paths |
| Parallelism | Sequential | Parallel extraction + per-book 2-agent split |
| Per-book agents | 1 agent (all content) | 2 agents (chapters split 50/50) |
| Temp directory | `/tmp/book_skill_work` | `/tmp/opencode/book_skill_work` (pre-approved) |

## Argument Modes

The bridge supports three calling conventions:

| Mode | Example | Behavior |
|---|---|---|
| **Single** | `/book-to-skill-bridge book.pdf [slug]` | Process one book |
| **Multi** | `/book-to-skill-bridge a.pdf b.pdf c.pdf --slug prefix` | Process N books in parallel |
| **Batch** | `/book-to-skill-bridge --batch /path/to/dir` | All supported docs in a directory |

## Workflow

### Phase 0 — Parse arguments and validate all inputs

```bash
BOOK_PATHS=()
while [ $# -gt 0 ] && [ "$1" != "--batch" ] && [ "$1" != "--slug" ]; do
  BOOK_PATHS+=("$1")
  shift
done

EXPLICIT_SLUG_PREFIX=""
if [ "$1" = "--slug" ]; then
  shift; EXPLICIT_SLUG_PREFIX="$1"; shift
fi

if [ "$1" = "--batch" ]; then
  shift; BATCH_DIR="$1"
  BOOK_PATHS=()
  for ext in pdf epub docx txt md html rtf mobi azw3; do
    while IFS= read -r -d '' f; do BOOK_PATHS+=("$f"); done < <(find "$BATCH_DIR" -name "*.$ext" -print0 2>/dev/null)
  done
fi
```

Validate each path exists and has a supported extension. If none valid, stop.

For batch/multi: print `Processing N books in parallel with 2 agents each (N×2 = M total agents).`

### Phase 1 — Parallel extraction (bash)

```bash
SKILLS_HOME="${HOME}/.config/opencode/skills"
EXTRACT_SCRIPT="${SKILLS_HOME}/book-to-skill/scripts/extract.py"
AUTO_DETECT_SCRIPT="${SKILLS_HOME}/book-to-skill-bridge/scripts/auto_detect.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORKDIR="/tmp/opencode/book_skill_work"
mkdir -p "$WORKDIR"

for i in "${!BOOK_PATHS[@]}"; do
  BOOK="${BOOK_PATHS[$i]}"
  SLUG=$(basename "$BOOK" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g; s/^-//; s/-$//' | cut -c1-60)
  SLUGS[$i]="$SLUG"
  BOOK_WD="$WORKDIR/$SLUG"
  mkdir -p "$BOOK_WD"
  (
    echo "[$SLUG] Extracting text..."
    BOOK_SKILL_WORKDIR="$BOOK_WD" $PYTHON_BIN "$EXTRACT_SCRIPT" "$BOOK" --mode text --install-missing no 2>&1
  ) &
done
wait
```

**Do NOT re-extract with Docling.**

### Phase 2 — Parallel auto-detect (bash)

```bash
for i in "${!BOOK_PATHS[@]}"; do
  SLUG="${SLUGS[$i]}"
  BOOK_WD="$WORKDIR/$SLUG"
  (
    DETECTED=$($PYTHON_BIN "$AUTO_DETECT_SCRIPT" "$BOOK_WD/full_text.txt")
    echo "$DETECTED" > "$BOOK_WD/auto_detect.json"
  ) &
done
wait
```

Read each `auto_detect.json` to populate `MODE`, `TITLE`, `AUTHOR` per book.

If `EXPLICIT_SLUG_PREFIX` is set, override all slugs:
```bash
if [ -n "$EXPLICIT_SLUG_PREFIX" ]; then
  for i in "${!BOOK_PATHS[@]}"; do
    SLUGS[$i]="${EXPLICIT_SLUG_PREFIX}-$((i+1))"
  done
fi
```

Check slug collisions, create directories:
```bash
for i in "${!SLUGS[@]}"; do
  SLUG="${SLUGS[$i]}"
  if [ -d "${SKILLS_HOME}/${SLUG}" ]; then
    n=2
    while [ -d "${SKILLS_HOME}/${SLUG}-${n}" ]; do n=$((n+1)); done
    SLUGS[$i]="${SLUG}-${n}"
  fi
  mkdir -p "${SKILLS_HOME}/${SLUGS[$i]}/chapters"
done
```

### Phase 3 — Launch 2 agents per book (parallel content generation)

For each book, launch TWO task agents that split the chapter workload:

**Agent A** — odd-numbered chapters + glossary.md
**Agent B** — even-numbered chapters + patterns.md + cheatsheet.md + SKILL.md

Launch all agents in parallel. Do NOT wait between agents.

**LLM instruction for launching agents:**

For each book, build TWO prompts by finding the chapter structure first (read first 8000 chars, grep for headings), then splitting into odds/evens.

Build Agent A prompt:
```
Generate {ceil(N/2)} chapter files and the glossary for "{TITLE}" by {AUTHOR}.

SOURCE: /tmp/opencode/book_skill_work/{SLUG}/full_text.txt
OUTPUT: ~/.config/opencode/skills/{SLUG}/
MODE: {MODE} (technical → include Anti-patterns in chapters)

Your chapters (ODD numbers only):
{list of odd chapter titles}

Generate these files:
{files list, one per line: chapters/ch<NN>-{SLUG}.md}

Chapter format (800-1200 tokens each):
  # Chapter N: Title
  ## Core Idea
  ## Frameworks Introduced
  ## Key Concepts
  { "## Anti-patterns" if technical else "" }
  ## Key Takeaways

Also generate:
  glossary.md (~1500 tokens, alphabetical, all key terms)

Read the source text starting at the chapter's position (use grep/sed for boundaries).
Focus on density and actionable insights.

Return JSON: {{"chapters_created": N, "glossary_created": bool, "files": [...]}}
```

Build Agent B prompt:
```
Generate {floor(N/2)} chapter files + patterns + cheatsheet + SKILL.md for "{TITLE}" by {AUTHOR}.

SOURCE: /tmp/opencode/book_skill_work/{SLUG}/full_text.txt
OUTPUT: ~/.config/opencode/skills/{SLUG}/
MODE: {MODE}

Your chapters (EVEN numbers only):
{list of even chapter titles}

Generate these files:
{files list, one per line: chapters/ch<NN>-{SLUG}.md}

Chapter format (800-1200 tokens):
  # Chapter N: Title
  ## Core Idea
  ## Frameworks Introduced
  ## Key Concepts
  { "## Anti-patterns" if technical else "" }
  ## Key Takeaways

Also generate:
  glossary.md — already handled by Agent A. Do NOT create it.
  patterns.md — only if mode=technical, max 2000 tokens, setups with When/How/Trade-offs
  cheatsheet.md — max 1000 tokens, decision tables, quick-reference rules
  SKILL.md — max 4000 tokens, complete chapter index for ALL chapters (odds+evens)

SKILL.md format:
  ---
  name: {SLUG}
  description: "Knowledge base from '{TITLE}' by {AUTHOR}."
  allowed-tools: [read, grep]
  argument-hint: [topic, framework, or chapter number]
  ---
  # {TITLE}
  **Author**: {AUTHOR} | **Chapters**: {N} | **Generated**: 2026-05-28

  ## Core Frameworks & Mental Models
  (front-load frameworks, ~2000 tokens)

  ## Chapter Index
  | # | Title | Key Frameworks |
  (list ALL chapters: odds + evens)

  ## Topic Index

  ## Supporting Files
  - [glossary.md](glossary.md)
  - [patterns.md](patterns.md)
  - [cheatsheet.md](cheatsheet.md)

Read source text to find the complete chapter structure (both odds and evens).
The chapter index in SKILL.md must cover ALL books chapters.

Return JSON: {{"chapters_created": N, "skill_complete": bool, "files": [...]}}
```

**Launch all agents:**

```bash
echo "Launching $(( ${#BOOK_PATHS[@]} * 2 )) agents ($(printf '%s' "${#BOOK_PATHS[@]}") books × 2)..."
# Use the 'task' tool for each agent — see prompts above
```

Print the number of launched agents and their task IDs.

**Timeout note:** Each agent typically takes 3-8 minutes depending on book size.
- Books < 50K tokens: ~3 min per agent
- Books 50-100K tokens: ~5 min per agent
- Books > 100K tokens: ~8 min per agent
Total wall time ≈ max(agent times) across all books.

### Phase 4 — Patch SKILL.md with complete chapter index

After all agents complete, for each book read the generated chapter files and ensure SKILL.md has the correct complete chapter index:

```bash
for i in "${!SLUGS[@]}"; do
  SLUG="${SLUGS[$i]}"
  SKILL_FILE="${SKILLS_HOME}/${SLUG}/SKILL.md"
  CHAPTER_DIR="${SKILLS_HOME}/${SLUG}/chapters"

  echo "Checking $SLUG..."
  ls "$CHAPTER_DIR"/
done
```

If any chapter files are missing (e.g. agent failed), print a warning but continue.

If SKILL.md appears to be missing chapters from the other agent's set, patch the chapter index. This is a lightweight operation: read all existing chapter files, extract their headings, and rebuild the chapter index table in SKILL.md.

To detect missing chapters, count the actual `.md` files in chapters/ and cross-reference with the chapter index in SKILL.md. If there's a mismatch, fix the index.

### Phase 5 — Report

```
✅ Batch complete: {N} skills generated

| # | Skill | Chapters | Files |
|---|-------|----------|-------|
| 1 | {slug} | {N} | SKILL.md + {N} ch + gl + pa + chs |

⚡ Parallel speedup: {N}-book time ≈ single-book time
```

## Quality Rules

1. **No interactive prompts** — all decisions auto-resolved
2. **Trading emphasis** — setup rules, volume, price action front-loaded
3. **Density over completeness** — 1,000-token summary beats 10,000-token excerpt
4. **Front-load SKILL.md** — most important content first
5. **Chapter files on-demand** — loaded only when referenced
6. **Parallel execution** — never process books sequentially when N > 1
7. **2-agent split** — always split chapters odds/evens for 2x speedup
8. **Skip Docling re-extraction** — pdftotext is sufficient

## Performance Model

Single book:
- Phase 1 (extract): ~2s (pdftotext)
- Phase 2 (auto-detect): ~0.5s
- Phase 3 (2 agents parallel): max(Agent A time, Agent B time) ≈ ~5 min
- Phase 4 (patch): ~5s
- Total wall time: ~5 min vs ~10 min with 1 agent

N books (e.g. 10):
- Phase 1: ~2s (all extracted in parallel)
- Phase 2: ~0.5s
- Phase 3: ~max(agent time) ≈ ~5-8 min (2N agents in parallel)
- Phase 4: ~30s
- Total: ~5-8 min vs ~80-100 min sequential

Actual agent times vary by book size:
| Book size | Agent time |
|-----------|-----------|
| < 30K tokens | ~2 min |
| 30-60K tokens | ~4 min |
| 60-100K tokens | ~6 min |
| > 100K tokens | ~10 min |

## Timing Expectations

- **Each agent runs independently** with its own token budget
- **Total cost** = sum of all 2N agents' token usage
- **Wall time** ≈ max(wall time of any single agent) — the parallel speedup
- Books are processed simultaneously, not sequentially
