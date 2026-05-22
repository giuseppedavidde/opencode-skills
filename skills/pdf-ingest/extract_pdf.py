"""
extract_pdf.py — PDF extractor for Karpathy LLM Wiki ingest.

Extracts text, tables, and images from a PDF file.
- pdfplumber: text + tables
- pymupdf: embedded images
- pytesseract: OCR fallback for scanned pages (< OCR_THRESHOLD chars/page)

Usage:
    python extract_pdf.py <pdf_path> --wiki-root <wiki_root> --topic <topic>

Output:
    raw/<topic>/<slug>.pdf.extracted/
        text.md
        tables.md
    wiki/images/<topic>/<slug>/
        p<N>_img<M>.png
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

import pdfplumber
import pymupdf  # type: ignore[import-untyped]
import pytesseract
from PIL import Image
from pydantic import BaseModel, Field

# Pages with fewer chars than this trigger OCR fallback
OCR_THRESHOLD: int = 50


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PageText(BaseModel):
    """Text extracted from a single PDF page."""

    page_number: int = Field(..., ge=1)
    text: str
    ocr_used: bool = False


class TableRow(BaseModel):
    """Single row from a PDF table."""

    cells: list[str]


class ExtractedTable(BaseModel):
    """Table extracted from a PDF page."""

    page_number: int = Field(..., ge=1)
    rows: list[TableRow]


class ExtractionResult(BaseModel):
    """Full extraction result for one PDF."""

    pdf_path: Path
    pages: list[PageText]
    tables: list[ExtractedTable]
    image_paths: list[Path]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_from_path(pdf_path: Path) -> str:
    """Return stem of PDF filename as slug."""
    return pdf_path.stem


def _ocr_page(page: "pymupdf.Page") -> str:  # type: ignore[name-defined]
    """Render page as image and run tesseract OCR."""
    mat = pymupdf.Matrix(2.0, 2.0)  # 2× zoom for better OCR accuracy
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def _table_to_markdown(table: ExtractedTable) -> str:
    """Convert ExtractedTable to markdown table string."""
    if not table.rows:
        return ""
    rows = table.rows
    header = "| " + " | ".join(rows[0].cells) + " |"
    separator = "| " + " | ".join(["---"] * len(rows[0].cells)) + " |"
    body_lines = [
        "| " + " | ".join(row.cells) + " |" for row in rows[1:]
    ]
    return "\n".join([header, separator] + body_lines)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_text_and_tables(
    pdf_path: Path,
    mupdf_doc: "pymupdf.Document",  # type: ignore[name-defined]
) -> tuple[list[PageText], list[ExtractedTable]]:
    """Extract text and tables using pdfplumber; OCR fallback via pymupdf."""
    pages: list[PageText] = []
    tables: list[ExtractedTable] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            raw_text: Optional[str] = page.extract_text()
            text = raw_text.strip() if raw_text else ""
            ocr_used = False

            if len(text) < OCR_THRESHOLD:
                mupdf_page = mupdf_doc[i]
                text = _ocr_page(mupdf_page).strip()
                ocr_used = True

            pages.append(PageText(page_number=page_num, text=text, ocr_used=ocr_used))

            raw_tables = page.extract_tables()
            for raw_table in raw_tables:
                if not raw_table:
                    continue
                rows = [
                    TableRow(cells=[str(cell) if cell is not None else "" for cell in row])
                    for row in raw_table
                ]
                tables.append(ExtractedTable(page_number=page_num, rows=rows))

    return pages, tables


def extract_images(
    mupdf_doc: "pymupdf.Document",  # type: ignore[name-defined]
    images_out_dir: Path,
) -> list[Path]:
    """Extract embedded images from PDF using pymupdf."""
    images_out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for page_index, page in enumerate(mupdf_doc):
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            base_image = mupdf_doc.extract_image(xref)
            image_bytes: bytes = base_image["image"]
            ext: str = base_image["ext"]
            out_path = images_out_dir / f"p{page_index + 1}_img{img_index + 1}.{ext}"

            with open(out_path, "wb") as fh:
                fh.write(image_bytes)
            saved.append(out_path)

    return saved


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_text_md(pages: list[PageText], out_dir: Path) -> None:
    """Write extracted text to text.md."""
    lines: list[str] = []
    for page in pages:
        ocr_note = " *(OCR)*" if page.ocr_used else ""
        lines.append(f"## Page {page.page_number}{ocr_note}\n")
        lines.append(page.text or "*(no text extracted)*")
        lines.append("\n\n---\n")
    (out_dir / "text.md").write_text("\n".join(lines), encoding="utf-8")


def write_tables_md(tables: list[ExtractedTable], out_dir: Path) -> None:
    """Write extracted tables to tables.md."""
    if not tables:
        (out_dir / "tables.md").write_text("*(no tables found)*\n", encoding="utf-8")
        return
    lines: list[str] = []
    for table in tables:
        lines.append(f"## Page {table.page_number}\n")
        lines.append(_table_to_markdown(table))
        lines.append("\n\n---\n")
    (out_dir / "tables.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(pdf_path: Path, wiki_root: Path, topic: str) -> ExtractionResult:
    """Run full extraction pipeline."""
    slug = _slug_from_path(pdf_path)
    extracted_dir = pdf_path.parent / f"{pdf_path.name}.extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    images_out_dir = wiki_root / "wiki" / "images" / topic / slug

    mupdf_doc: pymupdf.Document = pymupdf.open(str(pdf_path))  # type: ignore[attr-defined]

    pages, tables = extract_text_and_tables(pdf_path, mupdf_doc)
    image_paths = extract_images(mupdf_doc, images_out_dir)

    mupdf_doc.close()

    write_text_md(pages, extracted_dir)
    write_tables_md(tables, extracted_dir)

    result = ExtractionResult(
        pdf_path=pdf_path,
        pages=pages,
        tables=tables,
        image_paths=image_paths,
    )

    print(f"[extract_pdf] text.md    → {extracted_dir / 'text.md'}")
    print(f"[extract_pdf] tables.md  → {extracted_dir / 'tables.md'}")
    print(f"[extract_pdf] images ({len(image_paths)}) → {images_out_dir}")
    ocr_pages = [p.page_number for p in pages if p.ocr_used]
    if ocr_pages:
        print(f"[extract_pdf] OCR used on pages: {ocr_pages}")

    return result


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Extract text/tables/images from PDF.")
    parser.add_argument("pdf_path", type=Path, help="Path to input PDF file")
    parser.add_argument("--wiki-root", type=Path, required=True, help="Root of the wiki (contains raw/ and wiki/)")
    parser.add_argument("--topic", type=str, required=True, help="Topic subdirectory name (e.g. 'mqtt', 'can-bus')")
    args = parser.parse_args()

    pdf_path: Path = args.pdf_path.resolve()
    wiki_root: Path = args.wiki_root.resolve()

    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if not wiki_root.exists():
        print(f"ERROR: wiki-root not found: {wiki_root}", file=sys.stderr)
        sys.exit(1)

    run(pdf_path, wiki_root, args.topic)


if __name__ == "__main__":
    main()
