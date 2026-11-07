---
name: pdf-compress
description: >
  Reduces the size of PDF files with a Python script (PyMuPDF). Use when the
  user asks to compress, shrink, optimize, or reduce a PDF, or when a workflow
  needs a smaller PDF. Handles single files, folders, recursive batches,
  encrypted PDFs, and JSON reports. Triggers: "compress PDF", "shrink PDF",
  "reduce PDF size", "optimize PDF", "PDF too large", "comprimi PDF",
  "riduci PDF", "PDF troppo grande", "ottimizza PDF", "alleggerisci PDF".
---

# PDF Compress

Compress PDF files with `compress_pdf.py`. The script uses PyMuPDF only.
It needs no Ghostscript, no qpdf, and no external command.

## When to Use

- The user asks to compress, shrink, optimize, or reduce a PDF.
- A PDF is too large for upload, email, or a knowledge-base ingest.
- A batch of PDFs needs the same compression preset.

Do not use this skill to extract text or images. Use `pdf-ingest` for that.

## Prerequisites

- Python 3.10 or later.
- PyMuPDF 1.24.3 or later.
- Pydantic 2.0 or later.

Reuse the shared virtual environment `/tmp/opencode/.venv` when it exists.

## Setup

1. Set the skill directory for the active client.

   ```bash
   # opencode
   SKILL_DIR="$HOME/.config/opencode/skills/pdf-compress"
   # VS Code, user scope
   # SKILL_DIR="$HOME/.copilot/skills/pdf-compress"
   # VS Code, workspace scope
   # SKILL_DIR=".github/skills/pdf-compress"
   ```

2. Create the environment and install the dependencies.

   ```bash
   mkdir -p /tmp/opencode
   python3 -m venv /tmp/opencode/.venv
   /tmp/opencode/.venv/bin/pip install -r "$SKILL_DIR/requirements.txt"
   ```

3. Check the script.

   ```bash
   /tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" --help
   ```

## Quick Start

Compress one file with the default preset.

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" report.pdf
```

Output: `report.compressed.pdf` in the same folder.

Select the output file.

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" report.pdf -o small.pdf
```

Compress a folder.

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" ./pdfs -O ./small --recursive
```

Compress a folder in place.

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" ./pdfs --in-place --recursive
```

Print a JSON report.

```bash
/tmp/opencode/.venv/bin/python "$SKILL_DIR/compress_pdf.py" ./pdfs -O ./small --json
```

## Presets

| Preset | Image DPI target | JPEG quality | Use for |
|---|---|---|---|
| `light` | 220 | 85 | High-quality images; small reduction |
| `balanced` | 150 | 75 | Default; good size and quality |
| `strong` | 120 | 60 | Email and web upload |
| `extreme` | 96 | 45 | Maximum reduction; check quality |

A lower DPI and a lower quality give a smaller file and lower image quality.
The `light` and `balanced` presets process only images above 300 DPI and 200 DPI.
The `strong` and `extreme` presets process images above 150 DPI and 100 DPI.

## Options

| Option | Effect |
|---|---|
| `-o, --output PATH` | Write one output file. Accepts one input only. |
| `-O, --output-dir DIR` | Write all outputs in a folder. |
| `-p, --preset NAME` | Select `light`, `balanced`, `strong`, or `extreme`. |
| `--dpi N` | Override the DPI target for all images. Range: 36 to 600. |
| `--quality N` | Override the JPEG quality. Range: 1 to 100. |
| `--effort N` | Override the stream compression effort. Range: 0 to 9. |
| `--grayscale` | Convert all images to grayscale. |
| `--no-subset-fonts` | Keep the full fonts. |
| `--password VALUE` | Open an encrypted PDF. |
| `--in-place` | Replace each input file. |
| `--suffix TEXT` | Set the generated name suffix. Default: `.compressed`. |
| `--overwrite` | Replace existing output files. |
| `-r, --recursive` | Read folders recursively. |
| `--json` | Print one JSON report on standard output. |
| `--quiet` | Hide the progress lines. |

## Behavior

- The script rewrites images, subsets fonts, adds object streams, and deflates streams.
- The script verifies the page count of each output.
- The script keeps the original when the compressed result is larger.
  It copies the original to the output path and reports `unchanged`.
- The script does not replace an existing output file without `--overwrite`.
- The script keeps the encryption of an encrypted PDF.
- The script preserves text, links, bookmarks, annotations, and metadata.
- The script keeps bitonal scans in their original compression.
- In `--in-place` mode, the script replaces a file only when the result is smaller.
- A directory input keeps its relative folder structure under `--output-dir`.
- The exit code is `0` on full success and `1` when one file fails.

## Workflow

1. Identify the input files or the input folder.
2. Start with the `balanced` preset.
3. Write the outputs to a separate folder.
4. Read the reduction percentage in the report.
5. Use `strong` or `extreme` when the file is still too large.
6. Use `light` or a higher `--quality` when the image quality is too low.
7. Run `pdf-ingest` on the compressed file when the next step extracts text.

## JSON Report

`--json` prints one object. Main fields:

| Field | Meaning |
|---|---|
| `preset` | Selected preset. |
| `settings` | Effective DPI, quality, effort, grayscale, and font flags. |
| `results` | One item for each input file. |
| `results[].status` | `compressed`, `unchanged`, or `failed`. |
| `results[].reduction_percent` | Size reduction for the file. |
| `results[].warnings` | Skipped steps, for example font subsetting. |
| `files_compressed` | Count of reduced files. |
| `files_unchanged` | Count of files that kept the original size. |
| `files_failed` | Count of failed files. |
| `bytes_before` | Total size before compression. |
| `bytes_after` | Total size after compression. |
| `reduction_percent` | Total size reduction. |

## Troubleshooting

| Message | Cause | Action |
|---|---|---|
| `missing Python dependency` | The environment has no PyMuPDF or Pydantic. | Run the Setup steps. |
| `input is not a PDF` | The file is not a PDF document. | Check the file. |
| `encrypted PDF: set --password` | The PDF has a user password. | Add `--password VALUE`. |
| `output exists` | The output file is present. | Add `--overwrite` or select another output path. |
| `compressed result was larger` | The PDF is already optimized. | Keep the original file. |
| Small reduction | The images are below the preset DPI threshold. | Add `--dpi 120` or use `strong`. |
| `page count changed` | The input file has damage. | Keep the original file. |
| Images are too soft | The DPI or the quality is too low. | Use `light` or `--quality 85`. |
| A font is missing | Font subsetting broke the font. | Add `--no-subset-fonts`. |

## Batch Parallelism

`orchestrator.json` sets `split_by` to `file` and `chunk_size` to `1`.
A dispatcher can send one PDF to each worker. Each worker runs the same command.
