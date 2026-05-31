---
name: book-to-skill
description: "Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW with Calibre) into structured agent skills, extracting frameworks, mental models, principles, techniques, and anti-patterns. Use when the user wants to study a document or turn a trading/technical book into a reusable skill."
allowed-tools:
  - bash
  - read
  - write
  - glob
  - grep
  - webfetch
  - task
argument-hint: <path-to-document> [skill-name-slug]
orchestrator:
  parallel: true
  split_by: chapter
  chunk_size: 1
  merge: none
---

# Book-to-Skill Converter

Transform written knowledge into actionable agent skills by extracting structure — not producing summaries.

## Philosophy

Books contain crystallized expertise: frameworks, principles, and techniques that took years to develop. This skill extracts that knowledge into a format OpenCode or another compatible agent can leverage repeatedly.

**Extract structure, not summaries.** A skill isn't a book report. It's a toolkit of:
- Named frameworks (mental models with clear application)
- Actionable principles (rules that guide decisions)
- Techniques (step-by-step methods)
- Anti-patterns (what to avoid and why)
- Voice calibration (how the author thinks and communicates)

**Preserve the author's precision.** Frameworks often have specific names for reasons. "The 5 Whys" isn't interchangeable with "ask why multiple times." Capture the exact formulation.

**Layer depth appropriately.** Simple books → simple skills. Complex books with 10+ frameworks → skills with reference files and on-demand chapters.

---

## Skill Locations

Generated skills default to `~/.config/opencode/skills/<slug>/` (OpenCode global skills).

---

## Step 0 — Out-of-scope check

If the argument is NOT a path to a supported document file, stop and respond:
> "book-to-skill requires a supported document path. Usage: `/book-to-skill /path/to/book.pdf [skill-name]`, or another supported format such as `.epub`, `.docx`, `.md`, `.txt`, `.html`, `.rtf`, `.mobi`, or `.azw3`."

Throughout the workflow, treat the first argument as `BOOK_PATH` and the optional second argument as `SKILL_NAME`.

---

## Step 1 — Validate input

```bash
test -f "$BOOK_PATH" && echo "FILE_OK" || echo "FILE_NOT_FOUND: $BOOK_PATH"
case "${BOOK_PATH##*.}" in
  pdf|PDF|epub|EPUB|docx|DOCX|txt|TXT|md|MD|markdown|MARKDOWN|rst|RST|adoc|ADOC|asciidoc|ASCIIDOC|html|HTML|htm|HTM|rtf|RTF|mobi|MOBI|azw|AZW|azw3|AZW3) echo "FORMAT_OK" ;;
  *) echo "FORMAT_UNKNOWN" ;;
esac
```

Check the file extension or magic bytes (`%PDF` or `PK` zip header for EPUB/DOCX).

If the file is not found or the format is not supported, stop with a clear error message listing supported formats.

---

## Step 1.5 — Identify book type

Before extracting, ask the user:

> "What kind of content does this book have? This helps me choose the best extraction method.
>
> 1. **Technical** — has code blocks, tables, formulas, diagrams (e.g. programming books, academic papers, architecture guides)
> 2. **Text-heavy** — mostly prose, few or no tables/code (e.g. management, productivity, narrative non-fiction)
> 3. **Not sure** — I'll use the fast method and warn you if quality seems limited"

Store the answer as `BOOK_TYPE`:
- Option 1 → `BOOK_TYPE=technical`
- Option 2 → `BOOK_TYPE=text`
- Option 3 → `BOOK_TYPE=text`

---

## Step 2 — Extract text from the source document

Run the extraction script, passing the book type:

```bash
SCRIPT_PATH="$HOME/.config/opencode/skills/book-to-skill/scripts/extract.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" "$SCRIPT_PATH" "$BOOK_PATH" --mode <BOOK_TYPE> --install-missing ask
```

This creates:
- `<tempdir>/book_skill_work/full_text.txt` — full extracted text
- `<tempdir>/book_skill_work/metadata.json` — title, estimated pages, token count, size, extraction_mode

Read the `output_text` path in `<tempdir>/book_skill_work/metadata.json` to understand what was extracted.

---

## Step 2.5 — Pre-flight cost estimate

Read `<tempdir>/book_skill_work/metadata.json` and present the user with an estimate **before doing any generation**:

```
📖 Source detected: <filename> (<format>)
📄 Pages/Spine items/Sections: ~<N> | Words: ~<N> | Source tokens: ~<N>K

💰 Estimated token cost:
   Input  (book reading + prompts): ~<N>K tokens
   Output (skill files generated):  ~<N>K tokens
   Total:                           ~<N>K tokens

📁 Files to be generated:
   SKILL.md + <N> chapter files + glossary + patterns + cheatsheet

➡  Proceed? (yes / analyze only)
```

Wait for the user to confirm before proceeding. If they say "analyze only", switch to analysis mode (Step 3 only).

---

## Step 2.6 — REPL-style access for large books (> 50k tokens)

For books over ~50k tokens, prefer programmatic probes over reading the whole file:

```bash
wc -w "$FULL_TEXT_PATH"
grep -n -E "^\s*(Chapter|CHAPTER)\s+[0-9]+" "$FULL_TEXT_PATH" | head -40
sed -n '<start>,<end>p' "$FULL_TEXT_PATH"
grep -c -i "<framework>" "$FULL_TEXT_PATH"
```

Use this approach for Step 3 (structure analysis), Step 7 (per-chapter summaries), and Step 8 (glossary / patterns extraction). On books under 50k tokens, a single read is fine.

---

## Step 3 — Analyze book structure

Read the first 8,000 characters of the extracted `full_text.txt` to identify:
- Book **title** and **author(s)**
- **Chapter structure** (look for "Chapter N", "PART I", numbered headings, table of contents)
- **Core themes** and subject domain
- Approximate number of chapters

Then read the Table of Contents section if present to map all chapters.

**If mode is "Analyze Only":** produce the extraction report now and stop.

---

## Step 4 — Ask purpose (Full Conversion only)

Before generating, ask the user:

> "What should this skill help you do? (Pick one or more)
> 1. Apply the author's frameworks while working
> 2. Think with the author's mental models
> 3. Reference specific chapters and concepts
> 4. All of the above"

Use the answer to weight what gets highlighted in the SKILL.md Core section.

---

## Step 5 — Determine skill name

If `SKILL_NAME` was provided, use it as the skill slug.
Otherwise, propose two options and let the user choose:
- **By author-concept**: `{author-lastname}-{core-concept}` (e.g. `cialdini-influence`, `wyckoff-methodology`)
- **By title**: lowercase hyphens from book title (e.g. `designing-data-intensive-apps`)

Default to author-concept format if the book has a strong methodological identity.

Set `SKILLS_HOME=~/.config/opencode/skills` and check that `$SKILLS_HOME/<skill_name>/` does NOT already exist.
If it does, append `-2` or ask the user before overwriting.

---

## Step 6 — Create skill directory structure

```bash
mkdir -p "$SKILLS_HOME/<skill_name>/chapters"
```

---

## Step 7 — Generate chapter summaries

**TOKEN BUDGET RULE — CRITICAL:**
- Each chapter summary file: **800–1,200 tokens** (dense, not verbose)
- Files are loaded on-demand

For EACH chapter/major section identified in Step 3:

Read the corresponding section of the extracted `full_text.txt` (use grep/sed for chapter headings).

Create `$SKILLS_HOME/<skill_name>/chapters/ch<NN>-<slug>.md`:

```markdown
# Chapter N: <Full Title>

## Core Idea
<1–2 sentences>

## Frameworks Introduced
- **<Framework Name>**: <exact formulation>
  - When to use: <specific situation>
  - How: <steps or criteria>

## Key Concepts
- **<Term>**: <precise definition>

## Mental Models
<2-4 frameworks as "Use X when Y">

## Anti-patterns
- **<What to avoid>**: <why it fails>

## Code Examples *(technical books only)*
```<language>
<code>
```

## Key Takeaways
1. <Actionable insight>
2. <Actionable insight>
3. <Actionable insight>
```

---

## Step 8 — Generate supporting files

### glossary.md
Create `$SKILLS_HOME/<skill_name>/glossary.md`:
- Every significant term, alphabetically sorted
- Format: `**Term** — definition (Ch N)`
- Max 1,500 tokens

### patterns.md
Create `$SKILLS_HOME/<skill_name>/patterns.md`:
- All concrete techniques, algorithms, patterns
- Format: `## Pattern\n**When to use**: ...\n**How**: ...`
- Max 2,000 tokens

### cheatsheet.md
Create `$SKILLS_HOME/<skill_name>/cheatsheet.md`:
- Decision tables, comparison matrices, quick-reference rules
- Max 1,000 tokens

---

## Step 9 — Generate the master SKILL.md

**CRITICAL TOKEN BUDGET: Keep SKILL.md body under 4,000 tokens.**

Create `$SKILLS_HOME/<skill_name>/SKILL.md`:

```markdown
---
name: <skill_name>
description: "Knowledge base from \"<Full Title>\" by <Author(s)>. Use when applying <author>'s frameworks."
allowed-tools:
  - read
  - grep
argument-hint: [topic, framework name, or chapter number]
---

# <Full Title>
**Author**: <Author(s)> | **Chapters**: <N> | **Generated**: <YYYY-MM-DD>

## How to Use This Skill
- **Without arguments** — load core frameworks
- **With a topic** — find and read the relevant chapter
- **With chapter** — e.g. `ch05` to load that chapter
- **Browse** — ask "what chapters do you have?"

## Core Frameworks & Mental Models
<!-- ~2,000 tokens: most important frameworks and principles -->

## Chapter Index
| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-<slug>.md) | ... | ... |

## Topic Index
- **<Term>** → ch<N>

## Supporting Files
- [glossary.md](glossary.md)
- [patterns.md](patterns.md)
- [cheatsheet.md](cheatsheet.md)
```

---

## Step 10 — Cleanup and report

```bash
rm -rf /tmp/book_skill_work
```

Then report to the user:

```
✅ Skill created: ~/.config/opencode/skills/<skill_name>/

Files generated:
  SKILL.md           — core frameworks + index   (~X tokens)
  chapters/          — <N> chapter summaries     (~X tokens each)
  glossary.md        — key terms                 (~X tokens)
  patterns.md        — techniques & patterns     (~X tokens)
  cheatsheet.md      — quick reference           (~X tokens)

Usage:
  /<skill_name>               → load core frameworks
  /<skill_name> about <topic> → find and explain a topic
  /<skill_name> ch<N>         → dive into a specific chapter
```

---

## Quality Rules

1. **Extract structure, not summaries** — capture named frameworks, exact formulations, anti-patterns
2. **Preserve the author's precision** — "The 5 Whys" ≠ "ask why multiple times"
3. **Density over completeness** — a 1,000-token summary beats a 10,000-token excerpt
4. **Practitioner voice** — write "Use X when Y", not "The book explains X"
5. **Front-load SKILL.md** — most important content comes first
6. **Chapter files are on-demand** — they don't count against skill budget until loaded
7. **Never copy raw book text** — always synthesize, summarize, extract signal
8. **Topic index is critical** — it's how the agent navigates to the right chapter
