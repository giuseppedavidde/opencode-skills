#!/usr/bin/env python3
"""Reduce the file size of PDF files with PyMuPDF.

The script rewrites embedded images at a lower resolution and JPEG quality,
subsets fonts, and writes the PDF with object streams and deflate compression.
It never writes a larger file in place: when the result is bigger, the original
file stays unchanged.
"""

from __future__ import annotations

import argparse
import inspect
import os
import shutil
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, Sequence

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


class Preset(str, Enum):
    """Named compression levels."""

    LIGHT = "light"
    BALANCED = "balanced"
    STRONG = "strong"
    EXTREME = "extreme"


class PresetConfig(BaseModel):
    """Image and stream settings for one preset."""

    dpi_threshold: Optional[int] = Field(default=None, ge=1, le=1200)
    dpi_target: int = Field(ge=36, le=600)
    quality: int = Field(ge=1, le=100)
    compression_effort: int = Field(ge=0, le=9)


class CompressionSettings(BaseModel):
    """Effective settings applied to one PDF."""

    preset: Preset
    dpi_threshold: Optional[int]
    dpi_target: int
    quality: int
    compression_effort: int
    grayscale: bool = False
    subset_fonts: bool = True


class OutputOptions(BaseModel):
    """Destination options for the batch."""

    output: Optional[Path] = None
    output_dir: Optional[Path] = None
    in_place: bool = False
    suffix: str = ".compressed"


class FileResult(BaseModel):
    """Outcome for one input file."""

    source: str
    output: Optional[str] = None
    status: Literal["compressed", "unchanged", "failed"] = "failed"
    original_bytes: int = 0
    output_bytes: int = 0
    saved_bytes: int = 0
    reduction_percent: float = 0.0
    pages: int = 0
    warnings: list[str] = Field(default_factory=list)
    message: str = ""


class BatchReport(BaseModel):
    """Outcome for the complete run."""

    preset: Preset
    settings: CompressionSettings
    results: list[FileResult]
    files_total: int
    files_compressed: int
    files_unchanged: int
    files_failed: int
    bytes_before: int
    bytes_after: int
    reduction_percent: float


PRESETS: dict[Preset, PresetConfig] = {
    Preset.LIGHT: PresetConfig(
        dpi_threshold=300, dpi_target=220, quality=85, compression_effort=2
    ),
    Preset.BALANCED: PresetConfig(
        dpi_threshold=200, dpi_target=150, quality=75, compression_effort=4
    ),
    Preset.STRONG: PresetConfig(
        dpi_threshold=150, dpi_target=120, quality=60, compression_effort=6
    ),
    Preset.EXTREME: PresetConfig(
        dpi_threshold=100, dpi_target=96, quality=45, compression_effort=9
    ),
}


class PdfCompressionError(RuntimeError):
    """Raised when a PDF cannot be read, compressed, or verified."""


def _bounded_int(minimum: int, maximum: int):
    """Return an argparse converter that enforces an inclusive range."""

    def convert(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"not an integer: {value}") from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(
                f"value must be between {minimum} and {maximum}: {value}"
            )
        return number

    return convert


def human_size(size: int) -> str:
    """Format a byte count with one decimal place."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def percent_reduction(before: int, after: int) -> float:
    """Return the size reduction as a percentage."""
    if before <= 0:
        return 0.0
    return round((before - after) / before * 100, 1)


def build_settings(args: argparse.Namespace) -> CompressionSettings:
    """Merge the preset with explicit command-line overrides."""
    base = PRESETS[Preset(args.preset)]
    dpi_overridden = args.dpi is not None
    return CompressionSettings(
        preset=Preset(args.preset),
        # An explicit target applies to every image, not only high-DPI ones.
        dpi_threshold=None if dpi_overridden else base.dpi_threshold,
        dpi_target=args.dpi if dpi_overridden else base.dpi_target,
        quality=args.quality if args.quality is not None else base.quality,
        compression_effort=(
            args.effort if args.effort is not None else base.compression_effort
        ),
        grayscale=args.grayscale,
        subset_fonts=not args.no_subset_fonts,
    )


def _pdf_files(root: Path, recursive: bool) -> list[Path]:
    """Return PDF files inside a directory."""
    candidates = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def expand_inputs(
    raw_inputs: Sequence[Path], recursive: bool
) -> list[tuple[Path, Optional[Path]]]:
    """Expand files and directories into (source, relative path) pairs."""
    expanded: list[tuple[Path, Optional[Path]]] = []
    for raw in raw_inputs:
        if raw.is_dir():
            for path in _pdf_files(raw, recursive):
                expanded.append((path, path.relative_to(raw)))
        elif raw.is_file():
            expanded.append((raw, None))
        else:
            raise PdfCompressionError(f"input not found: {raw}")
    if not expanded:
        raise PdfCompressionError("no PDF files found")
    return expanded


def destination_for(
    source: Path, relative: Optional[Path], options: OutputOptions
) -> Path:
    """Compute the output path for one source file."""
    if options.in_place:
        return source
    if options.output is not None:
        return options.output
    name = f"{source.stem}{options.suffix}.pdf"
    if options.output_dir is not None:
        parent = relative.parent if relative is not None else Path()
        return options.output_dir / parent / name
    return source.with_name(name)


def _temp_path(destination: Path) -> Path:
    """Create an empty temporary PDF beside the destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.stem}.", suffix=".pdf"
    )
    os.close(handle)
    return Path(name)


def _open_document(source: Path, password: Optional[str]) -> "pymupdf.Document":
    """Open a PDF and authenticate it when required."""
    try:
        document = pymupdf.open(source)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise PdfCompressionError(f"cannot open PDF: {exc}") from exc
    if not document.is_pdf:
        document.close()
        raise PdfCompressionError("input is not a PDF")
    if document.needs_pass:
        if not password or not document.authenticate(password):
            document.close()
            raise PdfCompressionError(
                "encrypted PDF: set --password with a valid value"
            )
    return document


def _rewrite_images(
    document: "pymupdf.Document",
    settings: CompressionSettings,
    warnings: list[str],
) -> None:
    """Downsample and recompress embedded images."""
    try:
        # PyMuPDF 1.24 names this argument "biton"; later versions use "bitonal".
        parameters = inspect.signature(document.rewrite_images).parameters
        bitonal_key = "bitonal" if "bitonal" in parameters else "biton"
        document.rewrite_images(
            **{
                "dpi_threshold": settings.dpi_threshold,
                "dpi_target": settings.dpi_target,
                "quality": settings.quality,
                "lossy": True,
                "lossless": True,
                # Bitonal scans use CCITT compression; a JPEG rewrite makes them worse.
                bitonal_key: False,
                "color": True,
                "gray": True,
                "set_to_gray": settings.grayscale,
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        warnings.append(f"image rewrite skipped: {exc}")


def _subset_fonts(document: "pymupdf.Document", warnings: list[str]) -> None:
    """Subset fonts when possible."""
    try:
        document.subset_fonts()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        warnings.append(f"font subsetting skipped: {exc}")


def _verify_output(path: Path, expected_pages: int) -> None:
    """Check that the output is a readable PDF with the original page count."""
    try:
        check = pymupdf.open(path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise PdfCompressionError(f"compressed PDF is not readable: {exc}") from exc
    try:
        if check.page_count != expected_pages:
            raise PdfCompressionError(
                "page count changed: "
                f"{expected_pages} pages became {check.page_count} pages"
            )
    finally:
        check.close()


def _save_document(
    document: "pymupdf.Document",
    temp_path: Path,
    settings: CompressionSettings,
) -> None:
    """Write the compressed PDF to the temporary path."""
    parameters = inspect.signature(document.save).parameters
    options: dict[str, object] = {
        "garbage": 4,
        "clean": True,
        "deflate": True,
        "deflate_images": True,
        "deflate_fonts": True,
        "use_objstms": 1,
        "preserve_metadata": True,
    }
    if "compression_effort" in parameters:
        options["compression_effort"] = settings.compression_effort
    if "raise_on_repair" in parameters:
        options["raise_on_repair"] = False
    document.save(temp_path, **options)


def compress_file(
    source: Path,
    destination: Path,
    settings: CompressionSettings,
    password: Optional[str],
    overwrite: bool,
) -> FileResult:
    """Compress one PDF and return its result."""
    original_size = source.stat().st_size
    result = FileResult(
        source=str(source),
        output=str(destination),
        original_bytes=original_size,
    )
    same_file = destination.resolve() == source.resolve()
    if destination.exists() and not same_file and not overwrite:
        raise PdfCompressionError(f"output exists: {destination} (use --overwrite)")

    document = _open_document(source, password)
    pages = document.page_count
    temp_path = _temp_path(destination)
    warnings: list[str] = []
    try:
        try:
            _rewrite_images(document, settings, warnings)
            if settings.subset_fonts:
                _subset_fonts(document, warnings)
            _save_document(document, temp_path, settings)
        finally:
            document.close()

        _verify_output(temp_path, pages)
        new_size = temp_path.stat().st_size
        result.pages = pages
        result.warnings = warnings
        if new_size < original_size:
            shutil.copymode(source, temp_path)
            os.replace(temp_path, destination)
            result.status = "compressed"
            result.output_bytes = new_size
            result.saved_bytes = original_size - new_size
            result.reduction_percent = percent_reduction(original_size, new_size)
            return result

        result.status = "unchanged"
        result.output_bytes = original_size
        result.message = "compressed result was larger; original kept"
        if not same_file:
            shutil.copy2(source, destination)
        return result
    finally:
        if temp_path.exists():
            temp_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="compress_pdf.py",
        description="Reduce the file size of PDF files with PyMuPDF.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF files or folders")
    parser.add_argument("-o", "--output", type=Path, help="output file (one input)")
    parser.add_argument(
        "-O", "--output-dir", type=Path, help="output folder for batch runs"
    )
    parser.add_argument(
        "-p",
        "--preset",
        choices=[preset.value for preset in Preset],
        default=Preset.BALANCED.value,
        help="compression preset (default: balanced)",
    )
    parser.add_argument(
        "--dpi",
        type=_bounded_int(36, 600),
        help="override the image DPI target",
    )
    parser.add_argument(
        "--quality",
        type=_bounded_int(1, 100),
        help="override the JPEG quality",
    )
    parser.add_argument(
        "--effort",
        type=_bounded_int(0, 9),
        help="override the stream compression effort",
    )
    parser.add_argument(
        "--grayscale", action="store_true", help="convert all images to grayscale"
    )
    parser.add_argument(
        "--no-subset-fonts", action="store_true", help="skip font subsetting"
    )
    parser.add_argument("--password", help="password for an encrypted PDF")
    parser.add_argument(
        "--in-place", action="store_true", help="replace each input file"
    )
    parser.add_argument(
        "--suffix",
        default=".compressed",
        help="suffix for generated names (default: .compressed)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="replace existing output files"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="read folders recursively"
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="print a JSON report"
    )
    parser.add_argument("--quiet", action="store_true", help="hide progress lines")
    parser.add_argument("--version", action="version", version="1.0.0")
    return parser


def _validate_options(
    parser: argparse.ArgumentParser, args: argparse.Namespace, count: int
) -> None:
    """Reject conflicting output options."""
    if args.in_place and (args.output or args.output_dir):
        parser.error("--in-place cannot be used with --output or --output-dir")
    if args.output and args.output_dir:
        parser.error("--output cannot be used with --output-dir")
    if args.output and count > 1:
        parser.error("--output accepts one input file only")
    if Path(args.suffix).name != args.suffix:
        parser.error("--suffix cannot contain path separators")


def _failed_result(
    source: Path, destination: Optional[Path], message: str
) -> FileResult:
    """Build a failure result for one input."""
    size = source.stat().st_size if source.is_file() else 0
    return FileResult(
        source=str(source),
        output=str(destination) if destination is not None else None,
        status="failed",
        original_bytes=size,
        output_bytes=size,
        message=message,
    )


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> BatchReport:
    """Run the compression batch and return the report."""
    settings = build_settings(args)
    expanded = expand_inputs(args.inputs, args.recursive)
    _validate_options(parser, args, len(expanded))
    output_options = OutputOptions(
        output=args.output,
        output_dir=args.output_dir,
        in_place=args.in_place,
        suffix=args.suffix,
    )

    results: list[FileResult] = []
    for source, relative in expanded:
        destination = destination_for(source, relative, output_options)
        try:
            result = compress_file(
                source,
                destination,
                settings,
                args.password,
                args.overwrite,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            result = _failed_result(source, destination, str(exc))
        results.append(result)
        if not args.as_json and not args.quiet:
            print(_format_result(result))

    before = sum(
        result.original_bytes for result in results if result.status != "failed"
    )
    after = sum(result.output_bytes for result in results if result.status != "failed")
    return BatchReport(
        preset=settings.preset,
        settings=settings,
        results=results,
        files_total=len(results),
        files_compressed=sum(result.status == "compressed" for result in results),
        files_unchanged=sum(result.status == "unchanged" for result in results),
        files_failed=sum(result.status == "failed" for result in results),
        bytes_before=before,
        bytes_after=after,
        reduction_percent=percent_reduction(before, after),
    )


def _format_result(result: FileResult) -> str:
    """Format one result as a single progress line."""
    if result.status == "failed":
        return f"FAIL  {result.source}: {result.message}"
    detail = (
        f"{human_size(result.original_bytes)} -> "
        f"{human_size(result.output_bytes)} "
        f"(-{result.reduction_percent:.1f}%)"
    )
    if result.status == "unchanged":
        detail = f"{human_size(result.original_bytes)} (unchanged)"
    return f"OK    {result.source} -> {result.output}  {detail}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run(args, parser)
    except PdfCompressionError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if args.as_json:
        print(report.model_dump_json(indent=2))
    elif not args.quiet:
        print(
            f"Done: {report.files_compressed} compressed, "
            f"{report.files_unchanged} unchanged, {report.files_failed} failed. "
            f"Total {human_size(report.bytes_before)} -> "
            f"{human_size(report.bytes_after)} "
            f"(-{report.reduction_percent:.1f}%)."
        )
    return 1 if report.files_failed else 0


if __name__ == "__main__":
    sys.exit(main())
