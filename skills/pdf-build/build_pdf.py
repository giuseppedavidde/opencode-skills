#!/usr/bin/env python3
"""Build a paginated PDF from HTML or Markdown with PyMuPDF.

The renderer wraps MuPDF ``Story``. Story has three defects that make a naive
pipeline produce broken output, and this module works around all three:

1. ``page-break-inside: avoid`` is ignored. Blocks are therefore measured and
   packed onto pages by this module, and a forced break is attached inline to
   the first element of every page after the first.
2. ``background-color`` on a ``div`` leaks a stray filled band at the top of the
   following page. Callouts are converted to single-cell tables before layout.
3. ``background-color`` on ``th`` paints bars at the wrong position. The default
   stylesheet uses borders only.

Usage:
    build_pdf.py report.md -o report.pdf --title "Quarterly report"
    build_pdf.py page.html -o page.pdf --footer "Company - internal"
    build_pdf.py report.pdf --check-only          # verify an existing PDF
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import pymupdf
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - dependency guard
    _REQUIREMENTS = Path(__file__).with_name("requirements.txt")
    sys.stderr.write(
        f"error: missing Python dependency: {exc.name}\n"
        "Install the dependencies in a virtual environment:\n"
        "  python3 -m venv /tmp/opencode/.venv\n"
        f"  /tmp/opencode/.venv/bin/pip install -r {_REQUIREMENTS}\n"
    )
    raise SystemExit(3) from exc

# Pydantic models carry data only; methods are not required.
# pylint: disable=too-few-public-methods

PAPERS = {"a4": "a4", "letter": "letter", "legal": "legal"}
FONTS = {"sans": "sans-serif", "serif": "serif"}
DEFAULT_CSS = """
body { font-family: %FONT%; font-size: %SIZE%pt; line-height: 1.42; color: #1c1c1c; }
h1 { font-size: 1.95em; color: #14375e; margin: 0 0 3pt 0; line-height: 1.18; }
h2 { font-size: 1.28em; color: #14375e; margin: 14pt 0 5pt 0; }
h3 { font-size: 1.08em; color: #1f5c8b; margin: 10pt 0 3pt 0; }
h4 { font-size: 1em; color: #1f5c8b; margin: 8pt 0 2pt 0; }
p { margin: 0 0 6pt 0; }
ol, ul { margin: 0 0 7pt 0; }
li { margin-bottom: 3pt; }
code { font-family: monospace; font-size: 0.92em; color: #7a2d00; }
pre { font-family: monospace; font-size: 0.86em; margin: 0; }
table.code { width: 100%; margin: 4pt 0 8pt 0; }
table.code td { background-color: #f4f6f8; border: 0.5pt solid #c8d2dc;
                padding: 5pt 7pt; }
table { border-collapse: collapse; margin: 4pt 0 9pt 0; font-size: 0.9em; }
th { color: #14375e; font-weight: bold; text-align: left;
     border: 0.6pt solid #9fb3c6; border-bottom: 1.1pt solid #14375e;
     padding: 3pt 5pt; }
td { border: 0.6pt solid #b9c8d6; padding: 3pt 5pt; vertical-align: top; }
table.callout { width: 100%; margin: 6pt 0 10pt 0; font-size: 0.95em; }
table.callout td { border: 0.6pt solid #d9a441; background-color: #fdf3e3;
                   padding: 6pt 8pt; }
.lead { font-size: 0.95em; color: #4a5a6a; margin-bottom: 12pt; }
hr { border: none; border-top: 0.6pt solid #c8d2dc; margin: 10pt 0; }
"""

BLOCK_TAGS = "h1|h2|h3|h4|h5|p|ol|ul|table|pre|blockquote|hr|div"
BLOCK_RE = re.compile(rf"<({BLOCK_TAGS})\b[^>]*>.*?</\1>|<hr\s*/?>", re.DOTALL | re.IGNORECASE)
HEADING_PREFIXES = ("<h1", "<h2", "<h3", "<h4", "<h5")


class BuildSettings(BaseModel):
    """Effective layout settings for one document."""

    paper: str = "a4"
    landscape: bool = False
    margin: float = 52.0
    font: str = "sans"
    font_size: float = 9.6
    footer: Optional[str] = None
    title: Optional[str] = None


class PageIssue(BaseModel):
    """One verification finding."""

    page: int
    kind: str
    detail: str


class BuildReport(BaseModel):
    """Outcome of one document build."""

    source: str
    output: Optional[str] = None
    pages_planned: int = 0
    pages_written: int = 0
    blocks: int = 0
    bytes_written: int = 0
    warnings: list[str] = Field(default_factory=list)
    issues: list[PageIssue] = Field(default_factory=list)
    ok: bool = True


class PdfBuildError(RuntimeError):
    """Raised when the document cannot be written."""


# --------------------------------------------------------------------------- markdown


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def markdown_to_html(source: str) -> str:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Convert a practical Markdown subset to the HTML block set we paginate.

    The body is one stateful pass over the lines. Splitting it into helpers
    would require passing six pieces of mutable state, so it stays flat.
    """
    lines = source.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    list_kind: Optional[str] = None
    in_code = False
    code: list[str] = []
    index = 0

    def flush_para() -> None:
        if para:
            out.append("<p>" + " ".join(_inline(chunk) for chunk in para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_para()
            close_list()
            if in_code:
                out.append("<pre>" + _escape("\n".join(code)) + "</pre>")
                code.clear()
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue

        if not stripped:
            flush_para()
            close_list()
            index += 1
            continue

        heading = re.match(r"^(#{1,5})\s+(.*)$", stripped)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_para()
            close_list()
            out.append("<hr/>")
            index += 1
            continue

        if stripped.startswith(">"):
            flush_para()
            close_list()
            quote = [stripped.lstrip("> ").strip()]
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip("> ").strip())
                index += 1
            body = "<br/>".join(_inline(chunk) for chunk in quote)
            out.append(f'<table class="callout"><tr><td>{body}</td></tr></table>')
            continue

        if ("|" in stripped and index + 1 < len(lines)
                and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[index + 1])):
            flush_para()
            close_list()
            header = _split_row(stripped)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index]:
                rows.append(_split_row(lines[index]))
                index += 1
            head = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            out.append(f"<table><tr>{head}</tr>{body}</table>")
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        number = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if bullet or number:
            flush_para()
            kind = "ul" if bullet else "ol"
            if list_kind != kind:
                close_list()
                out.append(f"<{kind}>")
                list_kind = kind
            out.append(f"<li>{_inline((bullet or number).group(1))}</li>")
            index += 1
            continue

        close_list()
        para.append(stripped)
        index += 1

    if in_code and code:
        out.append("<pre>" + _escape("\n".join(code)) + "</pre>")
    flush_para()
    close_list()
    return "\n".join(out)


# --------------------------------------------------------------------------- html prep


def body_of(html: str) -> str:
    match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else html


def normalise_blocks(fragment: str, warnings: list[str]) -> str:
    """Apply the structural fixes Story requires."""
    # background-color is only safe on table cells: on a div or pre it leaks a
    # filled band onto the following page. Wrap both kinds of block in a table.
    fragment = re.sub(
        r'<div\s+class="(?:callout|note)"\s*>(.*?)</div>',
        r'<table class="callout"><tr><td>\1</td></tr></table>',
        fragment,
        flags=re.DOTALL | re.IGNORECASE,
    )
    fragment = re.sub(
        r"<pre\b[^>]*>(.*?)</pre>",
        r'<table class="code"><tr><td><pre>\1</pre></td></tr></table>',
        fragment,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if re.search(r'<div\s+class="(?:callout|note)"', fragment, re.IGNORECASE):
        warnings.append("nested callout div: flatten it, nesting is not supported")
    # An empty break div leaves an empty band; breaks are applied inline instead.
    fragment = re.sub(r'<div\s+class="(?:brk|page-break)"\s*>\s*</div>', "", fragment,
                      flags=re.IGNORECASE)
    leftover = re.findall(r"<div\b[^>]*>", fragment, re.IGNORECASE)
    if leftover:
        warnings.append(f"{len(leftover)} remaining div(s) may render unpredictably")
    return fragment


def split_units(fragment: str) -> list[str]:
    """Split top-level blocks and glue each heading to the block that follows."""
    units: list[str] = []
    pending = ""
    for match in BLOCK_RE.finditer(fragment):
        block = match.group(0)
        stripped = block.lstrip()
        if stripped.lower().startswith(HEADING_PREFIXES):
            pending += block
            continue
        units.append(pending + block)
        pending = ""
    if pending:
        units.append(pending)
    return units


# --------------------------------------------------------------------------- layout


class Layout(BaseModel):
    """Geometry resolved from the settings."""

    page_w: float
    page_h: float
    left: float
    top: float
    width: float
    height: float


def make_layout(settings: BuildSettings) -> Layout:
    paper = pymupdf.paper_rect(PAPERS[settings.paper])
    page_w, page_h = paper.width, paper.height
    if settings.landscape:
        page_w, page_h = page_h, page_w
    margin = settings.margin
    return Layout(
        page_w=page_w,
        page_h=page_h,
        left=margin,
        top=margin,
        width=page_w - 2 * margin,
        height=page_h - 2 * margin - 22,
    )


def measure(unit: str, layout: Layout, css: str) -> float:
    story = pymupdf.Story(html=unit, user_css=css)
    _, filled = story.place(pymupdf.Rect(0, 0, layout.width, 20000))
    return float(filled[3] - filled[1])


def paginate(units: list[str], layout: Layout, css: str,
             warnings: list[str]) -> list[list[str]]:
    pages: list[list[str]] = []
    index = 0
    while index < len(units):
        page: list[str] = []
        while index < len(units):
            candidate = "".join(page + [units[index]])
            needed = measure(candidate, layout, css)
            if page and needed > layout.height:
                break
            if not page and needed > layout.height:
                warnings.append(f"block taller than one page ({needed:.0f}pt)")
            page.append(units[index])
            index += 1
        pages.append(page)
    return pages


def force_break(unit: str) -> str:
    """Attach the page break to the first tag; an empty div leaves a band."""
    return re.sub(r"<(\w+)([^>]*)>", r'<\1\2 style="page-break-before: always">',
                  unit, count=1)


# --------------------------------------------------------------------------- render


def render(pages: list[list[str]], layout: Layout, css: str, target: Path) -> None:
    parts: list[str] = []
    for number, units in enumerate(pages):
        if number:
            units = [force_break(units[0])] + units[1:]
        parts.extend(units)
    html = ("<html><head><meta charset='utf-8'></head><body>"
            + "".join(parts) + "</body></html>")

    content = pymupdf.Rect(layout.left, layout.top,
                           layout.left + layout.width, layout.top + layout.height)
    page = pymupdf.Rect(0, 0, layout.page_w, layout.page_h)

    def rectfn(_rect_num: int, _filled: tuple) -> tuple:
        return page, content, None

    writer = pymupdf.DocumentWriter(str(target))
    try:
        pymupdf.Story(html=html, user_css=css).write(writer, rectfn)
    finally:
        writer.close()


def decorate(target: Path, settings: BuildSettings, layout: Layout) -> None:
    doc = pymupdf.open(target)
    total = doc.page_count
    for index, page in enumerate(doc, start=1):
        baseline = layout.page_h - 28
        if settings.footer:
            page.insert_text((layout.left, baseline), settings.footer, fontsize=7.2,
                             fontname="helv", color=(0.42, 0.47, 0.53))
        label = f"Pagina {index} di {total}"
        width = pymupdf.get_text_length(label, fontname="helv", fontsize=7.2)
        page.insert_text((layout.left + layout.width - width, baseline), label,
                         fontsize=7.2, fontname="helv", color=(0.42, 0.47, 0.53))
        line_y = baseline - 9
        page.draw_line(pymupdf.Point(layout.left, line_y),
                       pymupdf.Point(layout.left + layout.width, line_y),
                       color=(0.78, 0.82, 0.86), width=0.5)
    doc.saveIncr()
    doc.close()


def stamp_title(target: Path, title: str) -> None:
    doc = pymupdf.open(target)
    # ``metadata`` is a C-extension property; pylint cannot introspect it.
    meta = doc.metadata  # pylint: disable=no-member
    meta["title"] = title
    meta["creator"] = "pdf-build"
    doc.set_metadata(meta)
    doc.saveIncr()
    doc.close()


# --------------------------------------------------------------------------- verify


def verify(target: Path, layout: Layout, expected: Optional[int] = None) -> list[PageIssue]:
    """Reopen the PDF and report layout faults."""
    issues: list[PageIssue] = []
    doc = pymupdf.open(target)
    if expected is not None and doc.page_count != expected:
        issues.append(PageIssue(page=0, kind="page_count",
                                detail=f"planned {expected}, wrote {doc.page_count}"))
    for index, page in enumerate(doc, start=1):
        blocks = page.get_text("blocks")
        if not blocks:
            issues.append(PageIssue(page=index, kind="blank", detail="no text"))
            continue
        left = min(block[0] for block in blocks)
        right = max(block[2] for block in blocks)
        top = min(block[1] for block in blocks)
        bottom = max(block[3] for block in blocks)
        if left < layout.left - 6:
            issues.append(PageIssue(page=index, kind="overflow",
                                    detail=f"left edge {left:.0f} < {layout.left:.0f}"))
        if right > layout.left + layout.width + 6:
            issues.append(PageIssue(
                page=index, kind="overflow",
                detail=f"right edge {right:.0f} > {layout.left + layout.width:.0f}"))
        if bottom > layout.page_h - 20:
            issues.append(PageIssue(page=index, kind="overflow",
                                    detail=f"bottom edge {bottom:.0f} past footer"))
        if top < layout.top - 12:
            issues.append(PageIssue(page=index, kind="overflow",
                                    detail=f"top edge {top:.0f} above margin"))
        # A leaked background band is painted above the content box; a table
        # border that legitimately starts at the top sits exactly on the margin.
        for drawing in page.get_drawings():
            rect = drawing["rect"]
            if (rect.width > 120 and rect.height < 12
                    and rect.y0 < layout.top - 1.0):
                issues.append(PageIssue(page=index, kind="artifact",
                                        detail="stray filled band above the top margin"))
                break
        try:
            page.get_pixmap(dpi=36)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            issues.append(PageIssue(page=index, kind="render", detail=str(exc)[:120]))
    doc.close()
    return issues


# --------------------------------------------------------------------------- pipeline


def build(source: Path, output: Path, settings: BuildSettings,
          extra_css: str, report: BuildReport) -> None:
    layout = make_layout(settings)
    css = (DEFAULT_CSS
           .replace("%FONT%", FONTS[settings.font])
           .replace("%SIZE%", f"{settings.font_size:.1f}")) + extra_css

    raw = source.read_text(encoding="utf-8")
    if source.suffix.lower() in {".md", ".markdown"}:
        fragment = markdown_to_html(raw)
    else:
        fragment = body_of(raw)
    fragment = normalise_blocks(fragment, report.warnings)
    units = split_units(fragment)
    report.blocks = len(units)
    if not units:
        raise PdfBuildError(f"no content blocks found in {source}")

    pages = paginate(units, layout, css, report.warnings)
    report.pages_planned = len(pages)
    output.parent.mkdir(parents=True, exist_ok=True)
    render(pages, layout, css, output)
    decorate(output, settings, layout)
    if settings.title:
        stamp_title(output, settings.title)

    doc = pymupdf.open(output)
    report.pages_written = doc.page_count
    doc.close()
    report.bytes_written = output.stat().st_size
    report.output = str(output)
    report.issues = verify(output, layout, len(pages))
    report.ok = not report.issues


def _print_report(report: BuildReport) -> None:
    state = "ok" if report.ok else "ISSUES"
    print(f"{report.source} -> {report.output}: {report.pages_written} pages "
          f"({report.bytes_written / 1024:.0f} KB) [{state}]")
    for warning in report.warnings:
        print(f"  warning: {warning}")
    for issue in report.issues:
        print(f"  page {issue.page}: {issue.kind} — {issue.detail}")


def main(argv: Optional[list[str]] = None) -> int:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Parse arguments and run the build or the check."""
    parser = argparse.ArgumentParser(
        description="Build a paginated PDF from HTML or Markdown.")
    parser.add_argument("sources", type=Path, nargs="+",
                        help="input .html or .md files")
    parser.add_argument("-o", "--output", type=Path, help="output PDF path")
    parser.add_argument("-O", "--output-dir", type=Path, help="directory for outputs")
    parser.add_argument("--title", default=None, help="document title metadata")
    parser.add_argument("--footer", default=None, help="left footer text")
    parser.add_argument("--paper", default="a4", choices=sorted(PAPERS),
                        help="paper size (default: a4)")
    parser.add_argument("--landscape", action="store_true", help="landscape orientation")
    parser.add_argument("--margin", type=float, default=52.0, help="margin in points")
    parser.add_argument("--font", default="sans", choices=sorted(FONTS))
    parser.add_argument("--font-size", type=float, default=9.6,
                        help="body size in points")
    parser.add_argument("--css", type=Path, default=None, help="extra CSS file")
    parser.add_argument("--check-only", action="store_true",
                        help="verify an existing PDF instead of building")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    parser.add_argument("--quiet", action="store_true", help="hide progress lines")
    args = parser.parse_args(argv)

    extra_css = args.css.read_text(encoding="utf-8") if args.css else ""
    settings = BuildSettings(
        paper=args.paper, landscape=args.landscape, margin=args.margin,
        font=args.font, font_size=args.font_size,
        footer=args.footer, title=args.title,
    )

    if args.check_only:
        if args.output and len(args.sources) > 1:
            parser.error("--check-only accepts one input")
        target = args.output or args.sources[0]
        layout = make_layout(settings)
        issues = verify(target, layout)
        doc = pymupdf.open(target)
        report = BuildReport(source=str(args.sources[0]), output=str(target),
                             pages_written=doc.page_count,
                             issues=issues, ok=not issues)
        doc.close()
        if args.json:
            print(report.model_dump_json(indent=2))
        else:
            print(f"{target}: {report.pages_written} pages, "
                  f"{len(issues)} issue(s)")
            for issue in issues:
                print(f"  page {issue.page}: {issue.kind} — {issue.detail}")
        return 0 if report.ok else 1

    if args.output:
        if len(args.sources) > 1:
            parser.error("-o/--output accepts one input; use -O for a directory")
        targets = [(args.sources[0], args.output)]
    else:
        targets = []
        for source in args.sources:
            directory = args.output_dir or source.parent
            targets.append((source, directory / (source.stem + ".pdf")))

    exit_code = 0
    reports: list[BuildReport] = []
    for source, output in targets:
        report = BuildReport(source=str(source))
        try:
            build(source, output, settings, extra_css, report)
        except PdfBuildError as exc:
            report.ok = False
            report.warnings.append(str(exc))
            exit_code = 1
        reports.append(report)
        if not report.ok:
            exit_code = 1
        if not args.quiet and not args.json:
            _print_report(report)

    if args.json:
        payload = ([r.model_dump() for r in reports] if len(reports) > 1
                   else reports[0].model_dump())
        print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
