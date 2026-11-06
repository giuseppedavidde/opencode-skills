# Token benchmark

Measures the context cost of the trading MCP against the alternative of doing
the same work with raw data plus skill text. The point is to replace a
marketing claim ("80–95% fewer tokens") with a reproducible number.

## Run

```bash
# replay the recorded fixtures against the offline OHLCV panel (deterministic)
~/.local/share/opencode/trading-mcp-venv/bin/python -m research.token_benchmark.benchmark

# recapture the tool payloads from the live server, then measure
~/.local/share/opencode/trading-mcp-venv/bin/python -m research.token_benchmark.benchmark --record
```

Outputs: [`report.json`](./report.json) and [`report.md`](./report.md).
Recorded payloads live in [`fixtures/`](./fixtures); `--record` is the only
mode that touches the network.

## What is compared

| Path | Tokens counted |
|---|---|
| MCP | The tool's structured answer, compact JSON |
| Without MCP | The same tickers' last 252 OHLCV bars + the `SKILL.md` files describing the framework |

The schema tax — every tool definition sent to the client once per session —
is reported separately, because it is paid whether or not a tool is called.

## Latest result (offline replay)

| Scenario | MCP payload | Raw data | Skill text | Savings |
|---|---:|---:|---:|---:|
| `analyze_stock` | 967 | 6,590 | 6,345 | 92.5% |
| `scan_market` (12 tickers) | 1,109 | 77,822 | 1,064 | 98.6% |
| `bali_signals` | 224 | 10,076 | 2,750 | 98.3% |

Fixed cost per session (17 tools): **3,018 tokens** for the input schemas,
**9,993 tokens** including the typed output schemas and provenance fields.
Break-even is one call against the smallest scenario measured.

## Budget gate

[`budget.json`](./budget.json) records the limits CI enforces. A regression is
a reviewed change, not a silent one:

```bash
python -m research.token_benchmark.benchmark --check-budget   # exit 1 on violation
```

Limits are the measured baseline plus ~15-20% headroom. Adding a tool fails
the gate until `max_tools` is raised on purpose.

## Limitations (read before quoting the numbers)

- Tokens are estimated as `len(text) / 4`; no tokenizer is installed. JSON
  token density is close to that ratio but not identical.
- The baseline covers OHLCV bars only. Fundamentals, news and sentiment are
  excluded, so the savings are a **lower bound**.
- Model reasoning, retries and multi-turn overhead are not counted. The
  benchmark measures what enters the context window, not what the model does
  with it.
- The schema tax depends on the client: a client that omits `outputSchema`
  from the prompt pays 3,018 tokens, not 8,425.
- Fixtures are real payloads from one capture (2026-11-06). Market data
  changes; the *shape* and the order of magnitude do not.

## Tests

`tests/test_token_benchmark.py` runs the harness offline and checks that each
recorded fixture validates against the response model advertised by the
server. A change that breaks the wire contract fails there before it reaches a
conversation.
