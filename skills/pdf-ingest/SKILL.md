---
name: pdf-ingest
description: >
  PDF extraction helper for Karpathy LLM Wiki ingest. Use when a .pdf file is found
  in raw/<topic>/ during ingest. Extracts text, tables, and images from PDF using
  extract_pdf.py. Supports OCR fallback for scanned pages. Images saved to
  wiki/images/<topic>/<slug>/ and referenced in compiled wiki articles.
  Triggers: ".pdf in raw/", "ingest PDF", "PDF found", "extract PDF".
---

# PDF Ingest Skill

Helper skill for `karpathy-llm-wiki`. Activates when a `.pdf` file is detected
in `raw/<topic>/` during the ingest phase.

## When to Use

- User provides a PDF as ingest source
- A `.pdf` file already exists in `raw/<topic>/`
- Any step of the Karpathy wiki ingest encounters a PDF file

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

wiki/images/<topic>/YYYY-MM-DD-slug/
    p1_img1.png
    p2_img1.png
    ...
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
<!-- images: wiki/images/<topic>/YYYY-MM-DD-slug/ -->

[paste or summarize key content from text.md here]
```

### Step 4 — Compile wiki article

Read `text.md` and `tables.md` as source material. Compile wiki article following
standard karpathy-llm-wiki compile rules.

**Reference extracted images** in the compiled article using paths relative to
`wiki/<topic>/article.md`:

```markdown
![Figure caption](../images/<topic>/YYYY-MM-DD-slug/p1_img1.png)
```

Only reference images that are relevant to the article content. Do not dump all
images blindly.

### Step 5 — Continue normal ingest

Resume karpathy-llm-wiki workflow:
- Update `wiki/index.md`
- Append to `wiki/log.md`
- Cascade-update related articles

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
