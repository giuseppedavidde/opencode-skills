# Token benchmark — MCP vs raw data + skill text

Generated: 2026-11-06T22:35:20.783727+00:00 (mode: `offline`)
Estimator: `chars/4.0`

## Per-scenario context cost

| Scenario | MCP payload | Raw data | Skill text | Baseline | Savings | Savings % |
|---|---:|---:|---:|---:|---:|---:|
| analyze_stock | 967 | 6,590 | 6,345 | 12,935 | 11,968 | 92.5% |
| scan_market | 1,109 | 77,822 | 1,064 | 78,886 | 77,777 | 98.6% |
| bali_signals | 224 | 10,076 | 2,750 | 12,826 | 12,602 | 98.3% |

## Fixed schema tax (per session)

- Tools: **17**
- Descriptions: **1,009** tokens
- With input schemas only: **3,018** tokens
- With input + output schemas: **9,993** tokens
- Break-even over measured calls: **1** call

## Method

1. Call each tool through the real FastMCP client (`--record` saves the payload).
2. Serialise the same tickers' last 252 OHLCV bars compactly as the raw-data baseline.
3. Add the SKILL.md files that describe the framework the tool implements.
4. Count tool definitions from `tools/list` for the per-session schema tax.

## Limitations

- Token counts are estimated as len(text)/4, not tokenizer-exact.
- Raw-data baseline covers OHLCV bars; fundamentals/news are excluded, so savings are conservative.
- Model reasoning, retries and multi-turn overhead are not counted.
- Schema tax is paid per session; it is amortised over tool calls, not per call.
- Clients that omit outputSchema from the prompt pay only the input-schema tax.
