---
name: pdf-build
description: >
  Builds a paginated PDF from Markdown or HTML with PyMuPDF, with no browser,
  Ghostscript, LaTeX, or pandoc. Use when the user asks to generate, create,
  build, or export a PDF, convert a report or summary to PDF, or produce a
  printable document from text. Handles tables, code blocks, callouts, headers,
  footers, page numbers, batch input, and automatic layout verification.
  Triggers: "generate PDF", "create PDF", "make a PDF", "export to PDF",
  "HTML to PDF", "Markdown to PDF", "genera PDF", "crea PDF", "fai un PDF",
  "esporta in PDF", "riassunto in PDF".
allowed-tools: [read, grep, bash, edit]
metadata:
  argument-hint: "[file.md|file.html] (oppure 'check' per verificare un PDF)"
---

# PDF Build

Turn Markdown or HTML into a paginated PDF with PyMuPDF. No browser, no
Ghostscript, no LaTeX, no pandoc. One script, no layout code in the answer.

## When to Use

Use this skill when the user asks to:

- generate, create, build, or export a PDF;
- convert a report, summary, or analysis to PDF;
- produce a printable document from text;
- "fammi un PDF", "genera un PDF", "crea un PDF", "esporta in PDF".

Do not use this skill to shrink an existing PDF. Use `pdf-compress`.
Do not use this skill to extract text from a PDF. Use `pdf-ingest`.

## Why This Skill Exists

A naive PyMuPDF `Story` pipeline produces broken PDFs. Four faults are silent
and cost hours to find. This skill encodes the fixes, so no agent derives them
again.

| Fault | Symptom | Fix in this skill |
|---|---|---|
| `page-break-inside: avoid` is ignored | Tables split across pages | Blocks are measured and packed by the script |
| `background-color` on `div` or `pre` | Filled band at the top of the next page | Callouts and code blocks are wrapped in tables |
| `background-color` on `th` | Bars painted at the wrong position | Header style uses borders only |
| Empty `<div class="brk">` | Empty band at the top of the next page | Break is attached inline to the next element |

The rule behind three faults: **set `background-color` only on table cells.**

## Prerequisites

- Python 3.10 or later.
- PyMuPDF 1.24.3 or later.
- Pydantic 2.0 or later.

Reuse the shared virtual environment `/tmp/opencode/.venv` when it exists.

## Setup

1. Set the skill directory.

   ```bash
   # VS Code, user scope
   SKILL_DIR="$HOME/.copilot/skills/pdf-build"
   # opencode
   # SKILL_DIR="$HOME/.config/opencode/skills/pdf-build"
   ```

2. Create the environment and install the dependencies.

   ```bash
   mkdir -p /tmp/opencode
   python3 -m venv /tmp/opencode/.venv
   /tmp/opencode/.venv/bin/pip install -r "$SKILL_DIR/requirements.txt"
   ```

3. Check the script.

   ```bash
   /tmp/opencode/.venv/bin/python "$SKILL_DIR/build_pdf.py" --help
   ```

## Workflow

1. Write the content as a Markdown file. This costs the fewest tokens.
2. Run the script.
3. Read the report. Fix every warning and every issue.
4. Open the result only when the report says `ok`.

Do not write HTML unless the content needs features that Markdown cannot
express. Do not write Python.

### Quick start

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/build_pdf.py" report.md \
  -o report.pdf --title "Titolo del documento" --footer "Ufficio — interno"
```

### Check an existing PDF

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/build_pdf.py" report.pdf --check-only
```

### Batch

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/build_pdf.py" docs/*.md -O pdf/
```

## Markdown Support

The converter understands this subset:

| Element | Syntax |
|---|---|
| Headings | `#` to `#####` |
| Bold, italic, code | `**bold**`, `*italic*`, `` `code` `` |
| Links | `[text](url)` |
| Bullets | `- item` or `* item` |
| Numbers | `1. item` |
| Tables | pipe tables with a `|---|` separator row |
| Code blocks | triple backticks |
| Callout | `> text` becomes an ocra box |
| Rule | `---` on its own line |

The first `#` heading is the document title. Put the metadata line under it as
a plain paragraph in bold.

## Options

| Option | Effect |
|---|---|
| `-o, --output PATH` | Write one PDF. Accepts one input only. |
| `-O, --output-dir DIR` | Write all outputs in a folder. |
| `--title TEXT` | Set the PDF title metadata. |
| `--footer TEXT` | Set the left footer text. |
| `--paper NAME` | `a4` (default), `letter`, or `legal`. |
| `--landscape` | Landscape orientation. |
| `--margin N` | Margin in points. Default 52. |
| `--font NAME` | `sans` (default) or `serif`. |
| `--font-size N` | Body size in points. Default 9.6. |
| `--css PATH` | Add a CSS file. Overrides the defaults. |
| `--check-only` | Verify a PDF instead of building one. |
| `--json` | Print one JSON report on standard output. |
| `--quiet` | Hide the progress lines. |

The page number line, the footer rule, and the metadata are automatic.

## Report

The script verifies every build and prints one line per file:

```
report.md -> report.pdf: 8 pages (232 KB) [ok]
```

Read `[ISSUES]` as a failure. Each finding names the page and the fault:

| Kind | Meaning | Action |
|---|---|---|
| `overflow` | Text passes a margin | Shorten a table cell or the footer |
| `artifact` | Band painted above the top margin | Move the background to a table cell |
| `blank` | Page has no text | Check for an empty block |
| `page_count` | Planned pages differ from written pages | Report a bug in the skill |
| `render` | MuPDF cannot draw a page | Check for a malformed tag |

Exit code is `0` on full success and `1` on any issue.

## Custom Styling

Pass a CSS file with `--css`. Two rules keep the output correct:

1. Set `background-color` on `td` only. Never on `div`, `pre`, `p`, or `th`.
2. Do not set `page-break-*`. The script owns pagination.

Useful selectors: `h1`, `h2`, `h3`, `p`, `table`, `th`, `td`,
`table.callout td`, `table.code td`, `.lead`.

## Troubleshooting

| Message | Cause | Action |
|---|---|---|
| `missing Python dependency` | No PyMuPDF or Pydantic | Run the Setup steps |
| `no content blocks found` | File has no paragraph or table | Check the Markdown source |
| `remaining div(s) may render unpredictably` | A `<div>` in HTML input | Replace it with a table or remove it |
| `nested callout div` | A callout inside a callout | Flatten it to one level |
| `block taller than one page` | One table or code block exceeds a page | Split the block |
| `stray filled band above the top margin` | Background on a non-table block | Move it to a `td` |

## Design Notes

- Pagination measures the real cumulative height of each page. It does not
  estimate the sum of single blocks, because margins collapse.
- A heading is attached to the block after it, so a heading never sits alone at
  the foot of a page.
- Fonts are the MuPDF built-ins. No font file is embedded, so the output is
  small and portable.
- The report is a Pydantic model, so `--json` is stable for scripts.

## Batch Parallelism

`orchestrator.json` sets `split_by` to `file` and `chunk_size` to `1`.
A dispatcher can send one document to each worker. Each worker runs the same
command.
