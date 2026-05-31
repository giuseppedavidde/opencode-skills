---
name: pdf-ingest
description: >
  PDF extraction helper for both Karpathy LLM Wiki and Graphify workflows. Use when
  a .pdf file is found in raw/<topic>/ during ingest. Extracts text, tables, and
  images from PDF using extract_pdf.py. Supports OCR fallback for scanned pages.
  Images stored per-workflow convention. Triggers: ".pdf in raw/", "ingest PDF",
  "PDF found", "extract PDF".
allowed-tools:
  - read
  - write
  - bash
  - grep
  - task
orchestrator:
  parallel: true
  split_by: file
  chunk_size: 1
  merge: none
---

# PDF Ingest Skill

Helper skill for **Karpathy LLM Wiki** (`karpathy-llm-wiki`) and **Graphify**
(`graphify`). Activates when a `.pdf` file is detected in `raw/<topic>/` during
the ingest phase. Both workflows use the same extraction engine; output paths
differ by convention.

## When to Use

- User provides a PDF as ingest source
- A `.pdf` file already exists in `raw/<topic>/`
- Any step of either Karpathy or Graphify ingest encounters a PDF file

## Prerequisites

- Wiki root must contain `.venv/` with dependencies installed
- `tesseract` must be installed system-wide (`tesseract --version`)
- If `.venv/` missing: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

## Workflow

### Step 1 — Copy PDF to raw/

If not already there, save PDF to:
```
raw/<topic>/YYYY-MM-DD-descriptive-slug.pdf
```

Use same naming rules as karpathy-llm-wiki raw files.

### Step 2 — Run extract_pdf.py

```bash
<wiki_root>/.venv/bin/python \
  ~/.config/opencode/skills/pdf-ingest/extract_pdf.py \
  raw/<topic>/YYYY-MM-DD-slug.pdf \
  --wiki-root <wiki_root> \
  --topic <topic>
```

**Output produced:**
```
raw/<topic>/YYYY-MM-DD-slug.pdf.extracted/
    text.md       ← full text, one section per page; OCR pages marked *(OCR)*
    tables.md     ← all tables in markdown format
```

Images output depends on the workflow:

**For Karpathy** (`karpathy-llm-wiki`):
```
wiki/images/<topic>/YYYY-MM-DD-slug/
    p1_img1.png
    p2_img1.png
    ...
```

**For Graphify** (`graphify`):
```
graphify-out/images/<topic>/<book-slug>/
    p<N>_img<M>.png
```

### Step 3 — Create raw metadata file

Create `raw/<topic>/YYYY-MM-DD-slug.md` (the standard raw file for this source):

```markdown
---
source: <original PDF URL or "local file">
collected: YYYY-MM-DD
published: YYYY-MM-DD or Unknown
---

<!-- PDF extracted via extract_pdf.py -->
<!-- text: raw/<topic>/YYYY-MM-DD-slug.pdf.extracted/text.md -->
<!-- tables: raw/<topic>/YYYY-MM-DD-slug.pdf.extracted/tables.md -->
<!-- images: <workflow-specific path> -->

[paste or summarize key content from text.md here]
```

### Step 4 — Continue workflow

**For Karpathy:** Compile wiki article following standard `karpathy-llm-wiki` compile
rules. Reference extracted images using paths relative to `wiki/<topic>/article.md`:
```markdown
![Figure caption](../images/<topic>/YYYY-MM-DD-slug/p1_img1.png)
```
Only reference images relevant to the article content. Then update `wiki/index.md`
and `wiki/log.md`, cascade-update related articles.

**For Graphify:** The extracted `text.md` and images feed into semantic extraction
(concept/edge generation) and image description (Task subagents). Images are
organized per-book inside `graphify-out/images/<topic>/<book-slug>/`. After batch
description, merge image nodes into the graph via `build_merge()`.

## OCR Notes

- Pages with < 50 chars extracted text trigger automatic OCR via tesseract
- OCR pages marked with `*(OCR)*` in `text.md` section headers
- OCR accuracy depends on scan quality; review OCR output before compiling article
- If tesseract missing: script exits with clear error — install via system package manager

## Image Reference Format

From `wiki/<topic>/article.md`:
```markdown
![Description](../images/<topic>/<slug>/p<N>_img<M>.png)
```

From `wiki/index.md` or cross-topic articles — use path relative to current file.

## Error Handling

| Error | Action |
|---|---|
| `TesseractNotFoundError` | Install tesseract system-wide, re-run |
| PDF encrypted/password-protected | Inform user, skip extraction |
| No images extracted | Normal — not all PDFs have embedded images |
| `text.md` empty after OCR | Low-quality scan; inform user, manual transcription needed |
