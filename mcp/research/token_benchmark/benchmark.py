# pylint: disable=import-outside-toplevel,duplicate-code
"""Token benchmark: does the MCP actually shrink what the model must read?

The claim under test is not "MCP is cheaper" in the abstract. It is:

    the server compresses market data *outside* the context window, and the
    compressed payload costs fewer tokens than the raw data (plus the skill
    text) a model would need to reach the same analysis by itself.

What is measured
----------------
- ``mcp_payload``: tokens of the tool's structured answer (compact JSON).
- ``raw_data``:   tokens of the same tickers' OHLCV bars, serialised the way a
                  generic data tool would hand them to a model.
- ``skills``:     tokens of the SKILL.md files that describe the framework the
                  tool implements.
- ``schema_tax``: tokens of every tool definition (input and output schemas),
                  which a client pays once per session whether or not the tool
                  is called.

What is *not* measured: model reasoning tokens, retries, multi-turn overhead.
The raw-data baseline is a lower bound when fundamentals or news are excluded,
so reported savings are conservative.

Usage
-----
    python -m research.token_benchmark.benchmark --record   # live capture + report
    python -m research.token_benchmark.benchmark            # replay fixtures
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import math
import pickle
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
OFFLINE_OHLCV = (
    PROJECT_ROOT
    / "research"
    / "breakout_calibration"
    / "data_cache"
    / "ohlcv_2010-01-01_2026-09-30_n30_adj.pkl"
)
DEFAULT_SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"
REPO_SKILLS_DIR = PROJECT_ROOT.parent / "skills"
BUDGET_PATH = Path(__file__).resolve().parent / "budget.json"

# chars/4 is the usual English/JSON approximation; no tokenizer is assumed to
# be installed. The estimator is reported with every number so a reader can
# rescale instead of trusting a magic constant.
CHARS_PER_TOKEN = 4.0

# All present in the offline calibration panel, so the replay is
# deterministic and needs no network.
SCAN_TICKERS = (
    "AAPL", "ABBV", "ABNB", "ABT", "ACN", "ADBE",
    "ADI", "ADM", "ADP", "ADSK", "AIG", "AMD",
)


@dataclass(frozen=True)
class Scenario:
    """One task compared in both worlds."""

    name: str
    tool: str
    args: dict[str, Any]
    skills: tuple[str, ...]
    raw_tickers: tuple[str, ...]
    baseline_bars: int = 252
    extra_raw_fixture: str | None = None


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="analyze_stock",
        tool="analyze_stock",
        args={"ticker": "AAPL", "fetch_news": False},
        skills=(
            "stock-crypto-analysis",
            "wyckoff-2-0",
            "volume-profile",
            "volume-price-analysis",
        ),
        raw_tickers=("AAPL",),
    ),
    Scenario(
        name="scan_market",
        tool="scan_market",
        args={
            "tickers": ",".join(SCAN_TICKERS),
            "top_n": 5,
            "fetch_news": False,
        },
        skills=("market-accumulation-scanner",),
        raw_tickers=SCAN_TICKERS,
    ),
    Scenario(
        name="bali_signals",
        tool="bali_signals",
        args={"ticker": "AAPL", "period": "1y"},
        skills=("option-volatility-pricing",),
        raw_tickers=("AAPL",),
        extra_raw_fixture="fetch_options_chain__AAPL.json",
    ),
)


@dataclass
class ScenarioResult:
    """Measured cost of one scenario on both paths."""

    name: str
    mcp_payload_tokens: int = 0
    raw_data_tokens: int = 0
    skill_tokens: int = 0
    status: str = "ok"
    note: str = ""

    @property
    def baseline_tokens(self) -> int:
        """Tokens a model needs without the MCP (raw data + skill text)."""
        return self.raw_data_tokens + self.skill_tokens

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the JSON report."""
        savings = self.baseline_tokens - self.mcp_payload_tokens
        return {
            "name": self.name,
            "status": self.status,
            "note": self.note,
            "mcp_payload_tokens": self.mcp_payload_tokens,
            "raw_data_tokens": self.raw_data_tokens,
            "skill_tokens": self.skill_tokens,
            "baseline_tokens": self.baseline_tokens,
            "savings_tokens": savings,
            "savings_vs_raw_pct": _pct(
                self.raw_data_tokens - self.mcp_payload_tokens, self.raw_data_tokens
            ),
            "savings_vs_baseline_pct": _pct(savings, self.baseline_tokens),
        }


def resolve_skills_dir(explicit: Path | None) -> Path:
    """Use the explicit dir, else the installed skills, else the repo copy."""
    if explicit is not None:
        return explicit
    return DEFAULT_SKILLS_DIR if DEFAULT_SKILLS_DIR.exists() else REPO_SKILLS_DIR


def estimate_tokens(text: str) -> int:
    """Approximate token count for a JSON/text payload."""
    return int(round(len(text) / CHARS_PER_TOKEN))


def compact_json(payload: Any) -> str:
    """Serialise the way a client puts the payload in front of a model."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _pct(delta: int, total: int) -> float:
    """Percentage of ``delta`` over ``total`` (0.0 when total is 0)."""
    return round(100.0 * delta / total, 1) if total else 0.0


def bars_payload(bars: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    """Render the last ``limit`` bars exactly as a data tool would."""
    frame = bars.tail(limit)
    out: list[dict[str, Any]] = []
    for idx, row in frame.iterrows():
        out.append(
            {
                "date": str(idx),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
        )
    return out


@functools.lru_cache(maxsize=1)
def _offline_panel() -> dict[str, pd.DataFrame]:
    """Load the calibration OHLCV panel once per process."""
    if not OFFLINE_OHLCV.exists():
        return {}
    with OFFLINE_OHLCV.open("rb") as handle:
        return pickle.load(handle)


def load_offline_bars(ticker: str) -> pd.DataFrame | None:
    """Read the cached OHLCV panel used by the breakout calibration study."""
    return _offline_panel().get(ticker)


def load_live_bars(ticker: str) -> pd.DataFrame | None:
    """Fetch bars through the shared DataProvider (cache-aware)."""
    from trading_mcp.data.provider import data_provider  # local import: offline mode

    frame = data_provider.get_hist(ticker, period="1y")
    return frame if frame is not None and not frame.empty else None


def skill_text_tokens(skills_dir: Path, names: tuple[str, ...]) -> tuple[int, list[str]]:
    """Token size of the SKILL.md files that describe the tool's framework."""
    total = 0
    missing: list[str] = []
    for name in names:
        path = skills_dir / name / "SKILL.md"
        if not path.exists():
            missing.append(name)
            continue
        total += estimate_tokens(path.read_text(encoding="utf-8"))
    return total, missing


def schema_tax(server: Any) -> dict[str, Any]:
    """Measure the fixed per-session cost of the tool definitions."""
    from fastmcp import Client  # local import keeps offline runs light

    async def _list() -> list[Any]:
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(_list())
    per_tool: list[dict[str, Any]] = []
    input_tokens = output_tokens = description_tokens = 0
    for tool in tools:
        definition_in = {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
        }
        definition_out = {**definition_in, "outputSchema": tool.outputSchema}
        input_tokens += estimate_tokens(compact_json(definition_in))
        output_tokens += estimate_tokens(compact_json(definition_out))
        description_tokens += estimate_tokens(tool.description or "")
        per_tool.append(
            {
                "tool": tool.name,
                "description_tokens": estimate_tokens(tool.description or ""),
                "input_schema_tokens": estimate_tokens(compact_json(tool.inputSchema)),
                "output_schema_tokens": estimate_tokens(compact_json(tool.outputSchema)),
            }
        )
    return {
        "tool_count": len(tools),
        "description_tokens": description_tokens,
        "with_input_schema_only_tokens": input_tokens,
        "with_output_schema_tokens": output_tokens,
        "per_tool": per_tool,
    }


def call_tool(server: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call a tool through the real MCP client and return structured output."""
    from fastmcp import Client

    async def _call() -> dict[str, Any]:
        async with Client(server) as client:
            result = await client.call_tool(name, args)
            return result.structured_content or {}

    return asyncio.run(_call())


def record_fixtures(server: Any) -> dict[str, str]:
    """Capture live tool outputs, plus the raw chain needed by the Bali baseline."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for scenario in SCENARIOS:
        try:
            payload = call_tool(server, scenario.tool, scenario.args)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  SKIP {scenario.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        path = FIXTURES_DIR / f"{scenario.name}__live.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        written[scenario.name] = str(path)
        print(f"  wrote {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size} bytes)")

    try:
        from trading_mcp.data.provider import data_provider

        expiries = data_provider.get_options_expirations("AAPL")
        expiry = next(
            (item for item in expiries if 20 <= _dte(item) <= 90),
            expiries[0] if expiries else None,
        )
        if expiry:
            chain = call_tool(server, "fetch_options_chain", {"ticker": "AAPL", "expiry": expiry})
            path = FIXTURES_DIR / "fetch_options_chain__AAPL.json"
            path.write_text(
                json.dumps(chain, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            written["fetch_options_chain"] = str(path)
            print(f"  wrote {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size} bytes)")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  SKIP option chain: {type(exc).__name__}: {exc}", file=sys.stderr)
    return written


def _dte(expiry: str) -> int:
    """Days to expiry from an ISO date, or a neutral value on parse errors."""
    try:
        parsed = datetime.strptime(expiry, "%Y-%m-%d").date()
        return (parsed - datetime.now(timezone.utc).date()).days
    except (TypeError, ValueError):
        return 0


def load_fixture(name: str) -> dict[str, Any] | None:
    """Read a recorded tool payload, if present."""
    path = FIXTURES_DIR / f"{name}__live.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def measure_scenario(
    scenario: Scenario,
    mcp_payload: dict[str, Any] | None,
    bars_by_ticker: dict[str, pd.DataFrame | None],
    skills_dir: Path,
) -> ScenarioResult:
    """Compute both paths for one scenario."""
    result = ScenarioResult(name=scenario.name)
    if mcp_payload is None:
        result.status = "skipped"
        result.note = "no recorded fixture; run with --record"
        return result

    result.mcp_payload_tokens = estimate_tokens(compact_json(mcp_payload))

    raw_parts: list[str] = []
    missing_bars: list[str] = []
    for ticker in scenario.raw_tickers:
        frame = bars_by_ticker.get(ticker)
        if frame is None or frame.empty:
            missing_bars.append(ticker)
            continue
        raw_parts.append(compact_json(bars_payload(frame, scenario.baseline_bars)))
    if scenario.extra_raw_fixture:
        extra = FIXTURES_DIR / scenario.extra_raw_fixture
        if extra.exists():
            raw_parts.append(extra.read_text(encoding="utf-8"))
    result.raw_data_tokens = sum(estimate_tokens(part) for part in raw_parts)

    result.skill_tokens, missing_skills = skill_text_tokens(skills_dir, scenario.skills)

    notes: list[str] = []
    if missing_bars:
        notes.append(f"barre mancanti: {', '.join(missing_bars)}")
    if missing_skills:
        notes.append(f"skill mancanti: {', '.join(missing_skills)}")
    if missing_bars:
        result.status = "partial"
    result.note = "; ".join(notes)
    return result


def build_report(results: list[ScenarioResult], tax: dict[str, Any], mode: str) -> dict[str, Any]:
    """Assemble the JSON report, including schema-tax amortisation."""
    measured = [item for item in results if item.status in ("ok", "partial")]
    savings = [item.baseline_tokens - item.mcp_payload_tokens for item in measured]
    mean_savings = sum(savings) / len(savings) if savings else 0.0
    total_schema = tax["with_output_schema_tokens"]
    break_even = math.ceil(total_schema / mean_savings) if mean_savings > 0 else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "estimator": f"chars/{CHARS_PER_TOKEN}",
        "schema_tax": tax,
        "scenarios": [item.to_dict() for item in results],
        "summary": {
            "scenarios_measured": len(measured),
            "mean_savings_tokens_per_call": round(mean_savings),
            "schema_break_even_calls": break_even,
            "schema_tax_pct_of_one_call": (
                _pct(total_schema, int(mean_savings)) if mean_savings else 0.0
            ),
        },
        "limitations": [
            "Token counts are estimated as len(text)/4, not tokenizer-exact.",
            "Raw-data baseline covers OHLCV bars; fundamentals/news are excluded, "
            "so savings are conservative.",
            "Model reasoning, retries and multi-turn overhead are not counted.",
            "Schema tax is paid per session; it is amortised over tool calls, not per call.",
            "Clients that omit outputSchema from the prompt pay only the input-schema tax.",
        ],
    }


def load_budget(path: Path = BUDGET_PATH) -> dict[str, Any]:
    """Read the committed budget, or an empty one when absent."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check_budget(report: dict[str, Any], budget: dict[str, Any]) -> list[str]:
    """Return budget violations (payload growth, schema size, tool count)."""
    violations: list[str] = []
    limits = budget.get("max_payload_tokens", {})
    measured = {row["name"]: row for row in report["scenarios"]}
    for name, limit in limits.items():
        row = measured.get(name)
        if row is None or row.get("status") == "skipped":
            violations.append(f"{name}: missing measurement (fixture not recorded)")
            continue
        if row["mcp_payload_tokens"] > limit:
            violations.append(
                f"{name}: payload {row['mcp_payload_tokens']} tokens > budget {limit}"
            )
    tax = report["schema_tax"]
    checks = (
        ("max_schema_tokens", tax["with_output_schema_tokens"], "schema tokens"),
        ("max_description_tokens", tax["description_tokens"], "description tokens"),
        ("max_tools", tax["tool_count"], "tool count"),
    )
    for key, value, label in checks:
        if key in budget and value > budget[key]:
            violations.append(f"{label}: {value} > budget {budget[key]}")
    return violations


def render_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable report."""
    lines = [
        "# Token benchmark — MCP vs raw data + skill text",
        "",
        f"Generated: {report['generated_at']} (mode: `{report['mode']}`)",
        f"Estimator: `{report['estimator']}`",
        "",
        "## Per-scenario context cost",
        "",
        "| Scenario | MCP payload | Raw data | Skill text | Baseline | Savings | Savings % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["scenarios"]:
        if row["status"] == "skipped":
            lines.append(f"| {row.get('name', '?')} | — | — | — | — | — | skipped: {row['note']} |")
            continue
        marker = "" if row["status"] == "ok" else " ⚠"
        lines.append(
            f"| {row.get('name', '?')}{marker} | {row['mcp_payload_tokens']:,} "
            f"| {row['raw_data_tokens']:,} | "
            f"{row['skill_tokens']:,} | {row['baseline_tokens']:,} | {row['savings_tokens']:,} | "
            f"{row['savings_vs_baseline_pct']}% |"
        )
    tax = report["schema_tax"]
    summary = report["summary"]
    lines += [
        "",
        "## Fixed schema tax (per session)",
        "",
        f"- Tools: **{tax['tool_count']}**",
        f"- Descriptions: **{tax['description_tokens']:,}** tokens",
        f"- With input schemas only: **{tax['with_input_schema_only_tokens']:,}** tokens",
        f"- With input + output schemas: **{tax['with_output_schema_tokens']:,}** tokens",
        f"- Break-even over measured calls: **{summary['schema_break_even_calls']}** "
        f"call{'' if summary['schema_break_even_calls'] == 1 else 's'}",
        "",
        "## Method",
        "",
        "1. Call each tool through the real FastMCP client (`--record` saves the payload).",
        "2. Serialise the same tickers' last 252 OHLCV bars compactly as the raw-data baseline.",
        "3. Add the SKILL.md files that describe the framework the tool implements.",
        "4. Count tool definitions from `tools/list` for the per-session schema tax.",
        "",
        "## Limitations",
        "",
    ]
    lines += [f"- {item}" for item in report["limitations"]]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point: record fixtures and/or replay them into a report."""
    parser = argparse.ArgumentParser(description="Token benchmark for trading-mcp")
    parser.add_argument(
        "--record", action="store_true", help="call the live tools and save fixtures"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="measure against live data instead of the offline panel",
    )
    parser.add_argument("--skills-dir", type=Path, default=None)
    parser.add_argument(
        "--json", type=Path, default=Path(__file__).resolve().parent / "report.json"
    )
    parser.add_argument(
        "--markdown", type=Path, default=Path(__file__).resolve().parent / "report.md"
    )
    parser.add_argument("--check-budget", action="store_true", help="fail on budget violations")
    args = parser.parse_args(argv)

    from trading_mcp.mcp import initialize_mcp

    args.skills_dir = resolve_skills_dir(args.skills_dir)
    server = initialize_mcp(
        str(args.skills_dir),
        str(args.skills_dir / "market-accumulation-scanner" / "data"),
    )

    if args.record:
        print("Recording live fixtures...")
        record_fixtures(server)

    mode = "live" if (args.live or args.record) else "offline"
    bars_loader = load_live_bars if mode == "live" else load_offline_bars
    tickers = sorted({ticker for scenario in SCENARIOS for ticker in scenario.raw_tickers})
    bars_by_ticker: dict[str, pd.DataFrame | None] = {}
    for ticker in tickers:
        try:
            bars_by_ticker[ticker] = bars_loader(ticker)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  bars unavailable for {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
            bars_by_ticker[ticker] = None

    results = [
        measure_scenario(scenario, load_fixture(scenario.name), bars_by_ticker, args.skills_dir)
        for scenario in SCENARIOS
    ]
    report = build_report(results, schema_tax(server), mode)
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"wrote {args.json} and {args.markdown}")

    if args.check_budget:
        violations = check_budget(report, load_budget())
        if violations:
            print("token budget violated:", file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
            return 1
        print("token budget OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
