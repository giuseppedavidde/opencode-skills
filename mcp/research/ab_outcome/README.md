# A/B outcome harness

Measures the half the token benchmark cannot: whether the same question
produces the same **decision**. Each task runs twice — once with the result
cache cleared, once warm — and the configured decision fields are compared.
A cache may change speed; it must never change semantics.

## Run

```bash
# live: cold vs warm, writes fixtures and report
~/.local/share/opencode/trading-mcp-venv/bin/python -m research.ab_outcome.harness --record

# replay: validates fixtures without touching the network
~/.local/share/opencode/trading-mcp-venv/bin/python -m research.ab_outcome.harness
```

## What the tasks capture

| Task | Decision fields |
|---|---|
| `analyze_stock_aapl` | verdict, score, confidence, action |
| `scan_market_tech` | tickers scanned/passed, top pick, its score |
| `macro_context` | detected regime, macro window |
| `bali_signals_aapl` | availability, direction, score |
| `tsmom_signals_aapl` | availability, signal, direction, momentum score |
| `breakout_context_aapl` | bias guard, trigger, calibration verified |
| `bakshi_signals_aapl` | calibration status, ATM IV, calibrated VRP |

Volatile fields (timestamps, elapsed seconds) are deliberately excluded, so
the comparison is about the decision, not the clock.

## The other half: model with MCP vs without MCP

The harness executes the deterministic tool path. A true A/B — the same task
answered by a model with the MCP and by a model reasoning on raw data — needs
the agent runtime, because it measures a model, not this repository. The
protocol is:

1. Run each task in `tasks.json` through the agent with the trading MCP enabled
   and with it disabled (raw data + skill text).
2. Extract the same decision fields from each transcript.
3. Compare each answer against the deterministic reference values in
   `report.json` (agreement), and across repeated runs (repeatability).
4. Report agreement and repeatability per model; a model that disagrees with
   itself is not a reliable consumer of either path.

Step 3 is why the cold/warm reference is captured here: it fixes the answer the
deterministic path produces, so the model comparison has a stable anchor.

## Limitations

- Cold means the result cache was cleared; upstream provider caches are not.
- A task whose data is unavailable (weekend, rate limit) is reported as an
  error, never as "stable".
- Replay mode does not re-execute anything: it validates the recorded payloads.
