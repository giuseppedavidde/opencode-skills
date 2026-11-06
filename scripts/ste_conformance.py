#!/usr/bin/env python3
"""ASD-STE100 conformance test for the agent workflow.

Two modes:

  --wiring   Check that every agent carries the mandatory directive and that the
             canonical skill, the global rules, and the VS Code layer are linked.
  paths...   Lint prose files (Markdown, HTML, text) against the writing rules.
             A directory argument is expanded to *.md, *.html, *.txt.
  --self-test
             Run the built-in fixtures. Each fixture asserts that a rule fires
             or stays silent. No external file is needed.

Exit code: 0 = conform, 1 = at least one FAIL finding.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, Sequence, TextIO

from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
SKILL_DIR = REPO_ROOT / "skills" / "asd-ste100"
SKILL_FILE = SKILL_DIR / "SKILL.md"
GLOBAL_RULES = REPO_ROOT / "config" / "AGENTS.md"
VSCODE_RULES = REPO_ROOT / "vscode" / "copilot-instructions.md"
DIAGRAM_SKILL = REPO_ROOT / "skills" / "interactive-trade-diagram" / "SKILL.md"

DIRECTIVE_HEADING = "## ASD-STE100 — direttiva di scrittura obbligatoria"
PROCEDURE_LIMIT = 20
DESCRIPTION_LIMIT = 25
PARAGRAPH_LIMIT = 6


class Severity(str, Enum):
    """Finding severity."""

    FAIL = "FAIL"
    WARN = "WARN"


class Finding(BaseModel):
    """Single rule violation."""

    rule: str
    title: str
    severity: Severity
    line: int
    detail: str
    excerpt: str = ""


class RuleHit(BaseModel):
    """Aggregated counter for one rule."""

    rule: str
    title: str
    severity: Severity
    hits: int = 0


class Report(BaseModel):
    """Complete result for one target."""

    target: str
    lines: int = 0
    findings: list[Finding] = Field(default_factory=list)
    rules: dict[str, RuleHit] = Field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        """Append a finding and update the rule counter."""
        self.findings.append(finding)
        hit = self.rules[finding.rule]
        self.rules[finding.rule] = hit.model_copy(update={"hits": hit.hits + 1})

    def register(self, rule: str, title: str, severity: Severity) -> None:
        """Register a rule before the first use."""
        self.rules.setdefault(rule, RuleHit(rule=rule, title=title, severity=severity))

    @property
    def failures(self) -> list[Finding]:
        """Return the FAIL findings."""
        return [item for item in self.findings if item.severity is Severity.FAIL]

    @property
    def warnings(self) -> list[Finding]:
        """Return the WARN findings."""
        return [item for item in self.findings if item.severity is Severity.WARN]


# Rule registry: id -> (title, severity)
TEXT_RULES: dict[str, tuple[str, Severity]] = {
    "R1": ("Sentence length: max 20 words (procedure) / 25 (description)", Severity.FAIL),
    "R2": ("Paragraph length: max 6 sentences", Severity.FAIL),
    "R3": ("Active voice", Severity.WARN),
    "R4": ("Forbidden verb: use a precise verb", Severity.FAIL),
    "R5": ("Forbidden connective: use a short form", Severity.FAIL),
    "R6": ("No idiom, metaphor, or slang", Severity.FAIL),
    "R7": ("No semicolon between two clauses", Severity.FAIL),
    "R8": ("No contraction", Severity.FAIL),
    "R9": ("Abbreviation defined at first use", Severity.WARN),
    "R10": ("Exact quantity, not a vague word", Severity.WARN),
    "R11": ("No emphatic adverb or adjective", Severity.WARN),
}

FORBIDDEN_VERBS: tuple[str, ...] = (
    "effettuare",
    "effettua",
    "effettuato",
    "provvedere",
    "provvedi",
    "eseguire la verifica",
    "esegui la verifica",
)

FORBIDDEN_CONNECTIVES: tuple[str, ...] = (
    "al fine di",
    "in merito a",
    "relativamente a",
    "nonché",
    "qualora",
    "si rende necessario",
    "è opportuno",
    "e/o",
)

IDIOMS: tuple[str, ...] = (
    "bagno di sangue",
    "sanguinare",
    "salassare",
    "macello",
    "a razzo",
    "in picchiata",
    "prendere al volo",
    "a colpo sicuro",
    "balla di fuoco",
    "toccata e fuga",
)

EMPHASIS: tuple[str, ...] = (
    "davvero",
    "estremamente",
    "assolutamente",
    "incredibilmente",
    "notevolmente",
    "enorme",
    "pazzesco",
    "fantastico",
    "tremendo",
)

VAGUE_QUANTITY: tuple[str, ...] = (
    "circa",
    "un po'",
    "parecchio",
    "abbastanza",
    "pressoché",
    "molti",
    "diversi",
    "alcuni",
)

REQUIRED_ABBREVIATIONS: tuple[str, ...] = (
    "IV",
    "RV",
    "VRP",
    "DTE",
    "BE",
    "ATM",
    "OTM",
    "ITM",
    "P&L",
    "GEX",
    "VIX",
    "DXY",
)

PASSIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(viene|vengono|veniva|venivano|verrà|verranno)\s+\w+"
        r"(ato|ata|ati|ate|uto|uta|uti|ute|ito|ita|iti|ite)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(è stato|è stata|sono stati|sono state|era stato|erano stati)\s+\w+"
        r"(ato|ata|ati|ate|uto|uta|uti|ute|ito|ita|iti|ite)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(is|are|was|were|be|been|being)\s+\w+ed\b", re.IGNORECASE),
)

CONTRACTION_PATTERN = re.compile(
    r"\b(don't|doesn't|didn't|isn't|aren't|wasn't|weren't|can't|won't|"
    r"it's|that's|there's|we're|you're|they're|I've|we've|they've)\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9«\"'(])")
WORD_PATTERN = re.compile(r"[0-9A-Za-zÀ-ÿ][0-9A-Za-zÀ-ÿ'’._\-/]*")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
LINK_URL = re.compile(r"\((?:https?://|mailto:)[^)]*\)")
TAG_PATTERN = re.compile(r"<[^>]+>")
HTML_BLOCK = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
DEFINITION_PATTERN = re.compile(r"\b([A-Z][A-Za-z&]{0,6})\s*=\s*\S+")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

PROCEDURE_VERBS: frozenset[str] = frozenset({
    "apri", "leggi", "calcola", "verifica", "chiudi", "usa", "controlla",
    "invia", "copia", "esegui", "imposta", "riduci", "aggiungi", "rimuovi",
    "salva", "scrivi", "confronta", "applica", "scegli", "misura", "registra",
    "proteggi", "rolla", "vendi", "compra", "mantieni", "monitora",
})


class Block(BaseModel):
    """One prose block with the source line number."""

    line: int
    text: str
    kind: str


def register_text_rules(report: Report) -> None:
    """Register all text rules on a report."""
    for rule, (title, severity) in TEXT_RULES.items():
        report.register(rule, title, severity)


def strip_code(text: str) -> str:
    """Remove fenced code blocks and keep the line count stable."""
    result: list[str] = []
    inside = False
    for line in text.splitlines():
        if FENCE_PATTERN.match(line):
            inside = not inside
            result.append("")
            continue
        result.append("" if inside else line)
    return "\n".join(result)


def normalize_html(text: str) -> str:
    """Convert an HTML document to plain text lines."""
    text = HTML_BLOCK.sub("", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|tr|h[1-6]|section)>", "\n", text, flags=re.IGNORECASE)
    text = TAG_PATTERN.sub(" ", text)
    return html.unescape(text)


def clean_line(line: str) -> str:
    """Remove markup noise from one line."""
    line = INLINE_CODE.sub(" ", line)
    line = LINK_URL.sub("", line)
    line = line.replace("**", "").replace("__", "")
    return line.strip()


def iter_blocks(lines: Sequence[str]) -> Iterator[Block]:
    """Yield prose blocks with their kind."""
    paragraph: list[str] = []
    paragraph_line = 0

    def flush() -> Iterator[Block]:
        nonlocal paragraph, paragraph_line
        if paragraph:
            yield Block(line=paragraph_line, text=" ".join(paragraph), kind="paragraph")
            paragraph = []

    for index, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            yield from flush()
            continue
        if stripped.startswith("#"):
            yield from flush()
            yield Block(line=index, text=stripped.lstrip("# ").strip(), kind="heading")
            continue
        if stripped.startswith(">"):
            yield from flush()
            continue
        if stripped.startswith("<!--"):
            yield from flush()
            continue
        if stripped.startswith("|"):
            yield from flush()
            if set(stripped) <= set("|-: "):
                continue
            yield Block(line=index, text=stripped.strip("|"), kind="table")
            continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            yield from flush()
            yield Block(line=index, text=stripped, kind="list")
            continue
        if not paragraph:
            paragraph_line = index
        paragraph.append(clean_line(stripped))
    yield from flush()


def split_sentences(text: str) -> list[str]:
    """Split a block into sentences."""
    parts = [part.strip() for part in SENTENCE_SPLIT.split(text) if part.strip()]
    return parts or [text.strip()]


def count_words(sentence: str) -> int:
    """Count the words of one sentence."""
    return len(WORD_PATTERN.findall(sentence))


def is_procedure(block: Block) -> bool:
    """Return True when a list item is an instruction, not a description."""
    if block.kind != "list":
        return False
    body = LIST_MARKER.sub("", block.text).strip().strip("*_ ")
    first = re.split(r"[\s:]+", body, maxsplit=1)[0].lower()
    return first in PROCEDURE_VERBS


def iter_violations(
    block: Block, pattern: Iterable[str]
) -> Iterator[tuple[str, str]]:
    """Yield (needle, excerpt) once for each forbidden term in the block."""
    lowered = block.text.lower()
    longest: dict[int, str] = {}
    for needle in pattern:
        term = needle.lower()
        position = lowered.find(term)
        while position >= 0:
            current = longest.get(position)
            if current is None or len(term) > len(current):
                longest[position] = needle
            position = lowered.find(term, position + 1)

    reported: set[str] = set()
    for position in sorted(longest):
        needle = longest[position]
        if needle in reported:
            continue
        reported.add(needle)
        start = max(0, position - 40)
        yield needle, block.text[start : position + len(needle) + 40]


LEXICON_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("R4", FORBIDDEN_VERBS, "verb"),
    ("R5", FORBIDDEN_CONNECTIVES, "connective"),
    ("R6", IDIOMS, "idiom"),
    ("R10", VAGUE_QUANTITY, "vague quantity"),
    ("R11", EMPHASIS, "emphasis"),
)


def make_finding(rule: str, block: Block, detail: str, excerpt: str = "") -> Finding:
    """Build a finding from the rule registry."""
    title, severity = TEXT_RULES[rule]
    return Finding(
        rule=rule,
        title=title,
        severity=severity,
        line=block.line,
        detail=detail,
        excerpt=excerpt[:120],
    )


def lint_sentence_rules(block: Block, report: Report) -> None:
    """Apply the sentence and paragraph length limits."""
    if block.kind not in {"paragraph", "list"}:
        return
    limit = PROCEDURE_LIMIT if is_procedure(block) else DESCRIPTION_LIMIT
    sentences = split_sentences(block.text)
    for sentence in sentences:
        words = count_words(sentence)
        if words > limit:
            report.add(
                make_finding("R1", block, f"{words} words, limit {limit}", sentence)
            )
    if block.kind == "paragraph" and len(sentences) > PARAGRAPH_LIMIT:
        report.add(
            make_finding(
                "R2",
                block,
                f"{len(sentences)} sentences, limit {PARAGRAPH_LIMIT}",
                block.text,
            )
        )


def lint_passive(block: Block, report: Report) -> None:
    """Apply the active voice rule."""
    for pattern in PASSIVE_PATTERNS:
        match = pattern.search(block.text)
        if match:
            report.add(
                make_finding("R3", block, f"passive form: {match.group(0)}", block.text)
            )
            return


def lint_lexicon(block: Block, report: Report) -> None:
    """Apply every word list rule."""
    for rule, terms, label in LEXICON_RULES:
        for needle, excerpt in iter_violations(block, terms):
            report.add(make_finding(rule, block, f"{label}: {needle}", excerpt))


def lint_punctuation(block: Block, report: Report) -> None:
    """Apply the semicolon and contraction rules."""
    if ";" in block.text and block.kind != "table":
        report.add(make_finding("R7", block, "semicolon found", block.text))
    for match in CONTRACTION_PATTERN.finditer(block.text):
        report.add(
            make_finding("R8", block, f"contraction: {match.group(0)}", block.text)
        )


def lint_abbreviation(
    block: Block, report: Report, defined: set[str], seen: set[str]
) -> None:
    """Apply the abbreviation rule to the curated abbreviation list."""
    for token in re.findall(r"\b[A-Z][A-Za-z&]{0,5}\b", block.text):
        upper = token.upper()
        if upper not in REQUIRED_ABBREVIATIONS or upper in seen:
            continue
        seen.add(upper)
        if upper not in defined:
            report.add(
                make_finding("R9", block, f"undefined abbreviation: {upper}", block.text)
            )


def lint_text(text: str, name: str, suffix: str) -> Report:
    """Lint one document against the writing rules."""
    report = Report(target=name)
    register_text_rules(report)

    if suffix == ".html":
        text = normalize_html(text)
    text = strip_code(text)
    lines = text.splitlines()
    report.lines = len(lines)

    if lines and lines[0].strip() == "---":
        end = next(
            (i for i, item in enumerate(lines[1:], start=1) if item.strip() == "---"),
            None,
        )
        if end is not None:
            lines = [""] * (end + 1) + lines[end + 1 :]

    defined = {match.group(1).upper() for match in DEFINITION_PATTERN.finditer(text)}
    seen: set[str] = set()

    for block in iter_blocks(lines):
        lint_sentence_rules(block, report)
        lint_passive(block, report)
        lint_lexicon(block, report)
        lint_punctuation(block, report)
        lint_abbreviation(block, report, defined, seen)

    return report


WIRING_RULES: dict[str, str] = {
    "W1": "Canonical skill exists with a valid name and description",
    "W2": "Every agent carries the directive block",
    "W3": "Directive block has 10 numbered rules and a scope line",
    "W4": "Global rules carry the directive",
    "W5": "VS Code instructions carry the directive",
    "W6": "Trade diagram skill points to the canonical skill",
    "W7": "Agents that load the directive keep the skill permission",
}


def wiring_finding(rule: str, detail: str) -> Finding:
    """Build a wiring finding for one rule."""
    return Finding(
        rule=rule,
        title=WIRING_RULES[rule],
        severity=Severity.FAIL,
        line=0,
        detail=detail,
    )


def read_text(path: Path) -> str:
    """Read a file, or return an empty string when it is absent."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_skill(report: Report) -> None:
    """Check the canonical skill file."""
    skill_text = read_text(SKILL_FILE)
    if not skill_text:
        report.add(wiring_finding("W1", f"missing {SKILL_FILE}"))
        return
    name = re.search(r"^name:\s*(\S+)", skill_text, re.MULTILINE)
    description = re.search(r"^description:\s*\S+", skill_text, re.MULTILINE)
    if not name or name.group(1) != SKILL_DIR.name:
        report.add(wiring_finding("W1", "frontmatter name does not match the directory"))
    if not description:
        report.add(wiring_finding("W1", "missing frontmatter description"))


def check_agent_block(agent: Path, report: Report) -> None:
    """Check the directive block of one agent."""
    text = read_text(agent)
    if DIRECTIVE_HEADING not in text:
        report.add(wiring_finding("W2", f"{agent.name}: directive block missing"))
        return
    block = text.split(DIRECTIVE_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    numbered = re.findall(r"^\d{1,2}\.\s", block, re.MULTILINE)
    if len(numbered) < 10:
        report.add(
            wiring_finding("W3", f"{agent.name}: {len(numbered)} numbered rules, expected 10")
        )
    if "Si applica a:" not in block:
        report.add(wiring_finding("W3", f"{agent.name}: missing scope line"))
    if "skills/asd-ste100/SKILL.md" not in block:
        report.add(wiring_finding("W3", f"{agent.name}: missing canonical skill path"))


def check_agents(report: Report) -> None:
    """Check every agent definition."""
    agent_files = sorted(AGENTS_DIR.glob("*.md"))
    if not agent_files:
        report.add(wiring_finding("W2", "no agent file found"))
        return
    for agent in agent_files:
        check_agent_block(agent, report)


def check_layers(report: Report) -> None:
    """Check the global rules, the VS Code layer, and the diagram skill."""
    if "## ASD-STE100" not in read_text(GLOBAL_RULES):
        report.add(wiring_finding("W4", f"missing section in {GLOBAL_RULES}"))
    vscode_text = read_text(VSCODE_RULES)
    if "## Writing directive (ASD-STE100)" not in vscode_text:
        report.add(wiring_finding("W5", f"missing section in {VSCODE_RULES}"))
    if "asd-ste100" not in vscode_text:
        report.add(wiring_finding("W5", "asd-ste100 missing from the mandatory skills list"))
    if "asd-ste100" not in read_text(DIAGRAM_SKILL):
        report.add(
            wiring_finding("W6", "interactive-trade-diagram does not reference asd-ste100")
        )


def check_permissions(report: Report) -> None:
    """Check that the agents that load the directive keep the skill permission."""
    for agent_name in ("skill_updater.md", "book-to-skill-agent.md"):
        agent = AGENTS_DIR / agent_name
        if not agent.is_file():
            report.add(wiring_finding("W7", f"{agent_name}: file not found"))
            continue
        if not re.search(r"^  skill:\s*$", read_text(agent), re.MULTILINE):
            report.add(wiring_finding("W7", f"{agent_name}: missing skill permission"))


def check_wiring() -> Report:
    """Check that the directive is wired into every layer."""
    report = Report(target=str(REPO_ROOT))
    for rule, title in WIRING_RULES.items():
        report.register(rule, title, Severity.FAIL)
    check_skill(report)
    check_agents(report)
    check_layers(report)
    check_permissions(report)
    return report


SELF_TEST_CASES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("R1-long-sentence", "text", "La " + "parola " * 30 + "fine.", "R1", True),
    ("R1-short-sentence", "text", "Il prezzo sale. Il rischio scende.", "R1", False),
    (
        "R1-procedure-bullet",
        "text",
        "- Verifica il margine disponibile prima di inviare l'ordine di roll "
        "alla scadenza di ottobre con il broker attuale e controlla il risultato finale.",
        "R1",
        True,
    ),
    (
        "R1-descriptive-bullet",
        "text",
        "- Il premio incassato resta positivo anche se il tempo passa e il prezzo "
        "si muove contro la posizione in modo lento.",
        "R1",
        False,
    ),
    ("R1-code-exempt", "text", "```\neffettuare al fine di\n```\nTesto breve.", "R4", False),
    ("R2-six-sentences", "text", "Una. Due. Tre. Quattro. Cinque. Sei.", "R2", False),
    (
        "R2-seven-sentences",
        "text",
        "Una. Due. Tre. Quattro. Cinque. Sei. Sette.",
        "R2",
        True,
    ),
    ("R3-passive", "text", "La perdita viene registrata dal broker.", "R3", True),
    ("R3-active", "text", "Il broker registra la perdita.", "R3", False),
    ("R4-verb", "text", "Effettuare il calcolo.", "R4", True),
    ("R4-clean", "text", "Calcola il valore.", "R4", False),
    ("R5-connective", "text", "Al fine di ridurre il rischio, chiudi la posizione.", "R5", True),
    ("R6-idiom", "text", "La posizione è un bagno di sangue.", "R6", True),
    ("R7-semicolon", "text", "Il prezzo sale; il rischio scende.", "R7", True),
    ("R8-contraction", "text", "It's a loss. Don't wait.", "R8", True),
    ("R9-abbreviation", "text", "L'IV è alta.", "R9", True),
    ("R9-defined", "text", "IV = implied volatility. L'IV è alta.", "R9", False),
    ("R10-vague", "text", "Il prezzo è circa tremila.", "R10", True),
    ("R10-exact", "text", "Il prezzo è −$3,383.54.", "R10", False),
    ("R11-emphasis", "text", "La perdita è davvero enorme.", "R11", True),
)


COUNT_CASES: tuple[tuple[str, str, str, int], ...] = (
    ("R4-no-double-count", "Effettuare il roll.", "R4", 1),
    ("R11-two-terms", "La perdita è davvero enorme.", "R11", 2),
)


def run_self_test(output: TextIO) -> int:
    """Run the embedded fixtures and print the result."""
    failures = 0
    for name, kind, text, rule, expected in SELF_TEST_CASES:
        suffix = ".html" if kind == "html" else ".md"
        report = lint_text(text, name, suffix)
        found = any(item.rule == rule for item in report.findings)
        status = "ok" if found is expected else "FAIL"
        if found is not expected:
            failures += 1
        print(f"  [{status}] {name}: {rule} expected={expected} found={found}", file=output)

    for name, text, rule, expected_count in COUNT_CASES:
        report = lint_text(text, name, ".md")
        found = sum(1 for item in report.findings if item.rule == rule)
        status = "ok" if found == expected_count else "FAIL"
        if found != expected_count:
            failures += 1
        print(
            f"  [{status}] {name}: {rule} expected_count={expected_count} "
            f"found={found}",
            file=output,
        )

    wiring = check_wiring()
    for finding in wiring.findings:
        print(f"  [FAIL] wiring {finding.rule}: {finding.detail}", file=output)
        failures += 1

    verdict = "PASS" if failures == 0 else f"FAIL ({failures})"
    print(f"\nself-test: {verdict}", file=output)
    return 0 if failures == 0 else 1


def expand_paths(paths: Sequence[Path]) -> list[Path]:
    """Expand directories into lintable files."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            for suffix in ("*.md", "*.html", "*.txt"):
                files.extend(sorted(path.glob(suffix)))
        elif path.is_file():
            files.append(path)
    return files


def print_report(report: Report, output: TextIO, show_warn: bool) -> None:
    """Print one report as text."""
    visible = report.findings
    print(f"\n{report.target}  ({report.lines} lines, {len(visible)} findings)", file=output)
    if visible:
        for finding in visible:
            if finding.severity is Severity.WARN and not show_warn:
                continue
            print(
                f"  {finding.severity.value:4} {finding.rule:3} "
                f"line {finding.line}: {finding.detail}",
                file=output,
            )
            if finding.excerpt:
                print(f"       {finding.excerpt}", file=output)


def summarize(reports: Sequence[Report], output: TextIO) -> int:
    """Print the summary table and return the exit code."""
    totals: dict[str, RuleHit] = {}
    for report in reports:
        for rule, hit in report.rules.items():
            current = totals.get(rule)
            if current is None:
                totals[rule] = hit
            else:
                totals[rule] = current.model_copy(update={"hits": current.hits + hit.hits})

    print("\nRules", file=output)
    for rule in sorted(totals):
        hit = totals[rule]
        status = "ok" if hit.hits == 0 else hit.severity.value
        print(
            f"  {rule:3} {status:4} {hit.hits:4}  {hit.title}",
            file=output,
        )

    failures = sum(len(report.failures) for report in reports)
    warnings = sum(len(report.warnings) for report in reports)
    verdict = "PASS" if failures == 0 else "FAIL"
    print(f"\nVerdict: {verdict} ({failures} FAIL, {warnings} WARN)", file=output)
    return 0 if failures == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="ASD-STE100 conformance test for the agent workflow",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to lint. A directory expands to *.md, *.html, *.txt",
    )
    parser.add_argument(
        "--wiring",
        action="store_true",
        help="Check that every agent carries the directive (default with no paths)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the embedded fixtures",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat WARN findings as failures",
    )
    parser.add_argument(
        "--no-warn",
        action="store_true",
        help="Hide WARN findings in the detail list",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write the full report to a JSON file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the conformance test."""
    args = build_parser().parse_args(argv)
    output = sys.stdout

    if args.self_test:
        return run_self_test(output)

    if not args.paths:
        report = check_wiring()
        print_report(report, output, show_warn=not args.no_warn)
        return summarize([report], output)

    files = expand_paths(args.paths)
    if not files:
        print("No file found. Pass a file, a directory, or --wiring.", file=sys.stderr)
        return 1

    reports: list[Report] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        report = lint_text(text, str(path), path.suffix.lower())
        reports.append(report)
        print_report(report, output, show_warn=not args.no_warn)

    if args.json:
        payload = [report.model_dump(mode="json") for report in reports]
        args.json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    exit_code = summarize(reports, output)
    if args.strict and any(report.warnings for report in reports):
        print("Strict mode: WARN findings count as failures.", file=output)
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
