# A/B outcome — cold vs warm determinism

Generated: 2026-11-06T22:34:41.522571+00:00 (mode: `replay`)

Stable: **0/0** tasks

| Task | Tool | Status | Stable | Decision fields |
|---|---|---|---|---|
| analyze_stock_aapl | `analyze_stock` | recorded | — | `{"verdict": "Long-Term Investment", "composite_score": 79.3, "confidence": "LOW", "action_recommendation.action": "LONG_TERM_BUY"}` |
| scan_market_tech | `scan_market` | recorded | — | `{"tickers_scanned": 6, "tickers_passed": 5, "results[0].ticker": "MSFT", "results[0].final_score": 79.6}` |
| macro_context | `get_macro_context` | recorded | — | `{"detected_regime": "high_volatility", "macro_window": "SELECTIVE"}` |
| bali_signals_aapl | `bali_signals` | recorded | — | `{"available": true, "direction": "neutral", "composite_bali_score": 53.5}` |
| tsmom_signals_aapl | `tsmom_signals` | recorded | — | `{"available": true, "signal": 1, "direction": "bullish", "mom_score": 83.2}` |
| breakout_context_aapl | `breakout_context` | recorded | — | `{"bias_guard.flag": true, "breakout_triggers.fired": false, "breakout_triggers.status": "not fired: missing close_above_level, volume_ok", "evidence.artifact_verified": true}` |
| bakshi_signals_aapl | `bakshi_signals` | recorded | — | `{"calibrated": false, "calibration_status": "not_calibrated", "atm_iv": 0.2671, "calibrated_vrp": null}` |

## Limitations

- This harness executes the deterministic tool path, not a model.
- The with-MCP vs without-MCP comparison requires the agent runtime (see README.md).
- Cold means the result cache was cleared; upstream data caches are untouched.
- Volatile fields (timestamps, elapsed time) are excluded via decision_fields.
