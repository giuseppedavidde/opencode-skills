# Breakout Calibration — Phase 1

Offline research study that calibrates, with real historical data, the
operational rules for trading **momentum breakouts** and quantifies the
**mean-reversion bias** that made the analysis system misclassify the
HPE breakout as "bullish but cautious".

This is the **evidence-first** deliverable of a 3-part project. It does
not touch the live MCP code: it produces calibrated thresholds, a full
statistical report, and a machine-readable config for Phase 2.

## TL;DR — recommended thresholds

| Parameter | Value | Evidence |
|---|---|---|
| Breakout definition | close > prior **252-day** high (52w) | IS+OOS robustness |
| Volume confirmation | volume > **2.0x** prior 20-day avg | largest edge within each lookback |
| Trend filter | **close > SMA200** (auto-true for 52w highs) | 100% of 252d breakouts are in uptrends |
| Market filter | **not required** | SPY uptrend did not add edge |
| Stop | **2.0 x ATR(14)** (~4.6% avg) | best expectancy/risk at the preferred horizon |
| Preferred holding | **60–120 trading days** | edge grows with horizon; 120 is the tested maximum |
| Expected (OOS) | hit ~**59–61%**, excess **+1.5% to +2.4%** over 60–120d | 2021–2026 out-of-sample |

**Warning that fixes the HPE bug:** extension is **not** a fade signal.
The top 12m-momentum and top distance-from-SMA200 quintiles post
**positive** excess returns at 5–60 days. The most extreme 52-week
breakouts (close > SMA200 by >20%) had *higher* excess (+0.26% h20,
+0.87% h60) than the average breakout. Fading a name in a confirmed
uptrend making fresh relative-strength highs is contraindicated.

## Sample & data

- **Universe**: point-in-time S&P 500 constituents
  (`src/trading_mcp/data/historical_universe_sp500.csv`).
- **Source**: Yahoo Finance daily auto-adjusted OHLCV via `yfinance`.
- **Symbols loaded**: ~495 / 507 requested.
- **Period**: 2010-01-01 → 2026-09-30 (~4,200 trading days, ~1.96M stock-days).
- **Split**: in-sample ≤ 2020-12-31, out-of-sample ≥ 2021-01-01.

### Known data limitations (declared, not hidden)

1. **Survivorship bias** — the universe CSV lists ~500 *current* members
   plus only 4 explicit delistings. Delisted/removed names from 2010–2026
   are largely absent, so absolute returns are mildly upward biased. The
   *relative* breakout-vs-baseline comparison is far less affected.
2. **No historical GEX / options data** — call walls, gamma exposure and
   "magnet" behaviour **could not be backtested**. GEX remains a
   qualitative overlay only. Everything below is calibrated on
   price / volume / momentum.
3. **Delisted ticker API failures** (e.g. EQR, EA, FRC) are logged and skipped.

## Methodology

- **Breakout**: close strictly above the prior N-day high (rolling high
  shifted by one bar → no look-ahead). Optional volume gate: volume >
  k × prior 20-day average volume.
- **Forward returns**: close-to-close at 5/10/20/60/120 trading days.
- **Baseline**: unconditional same-horizon return of all stock-days.
  `excess = event mean − baseline mean` (the detrending required before
  any test).
- **Significance**: one-sample t-test of excess vs 0; cells with n < 30
  are flagged `sample_ok = false`.
- **Momentum test**: per-date cross-sectional quintiles (rank pct) for
  `dist_sma200`, `rsi14`, `mom12`, `ret_1d`.
- **Stops**: ATR(14) multiples, first-touch rule: a trade is stopped the
  first time the low touches `entry × (1 − m × ATR%)`, else it exits at
  the horizon close. Selected by expectancy/risk with a ≥25% win-rate floor.
- **Data-mining control**: White's Reality Check via a **circular block
  bootstrap** (block = 20 days) over daily per-config excess series,
  plus a Bonferroni cross-check.

## Key results

### Baseline (unconditional, full sample)

| Horizon | Mean | Hit rate |
|---|---|---|
| 5d | +0.36% | 54.8% |
| 10d | +0.71% | 56.4% |
| 20d | +1.43% | 58.3% |
| 60d | +4.30% | 63.0% |
| 120d | +8.67% | 67.0% |

### Breakout grid (in-sample, h20) — the headline finding

Every breakout configuration under-performed the unconditional baseline
**in-sample**: excess ranges from −0.28% (N20 + 2x vol) to about −1.0%
(no volume filter). This means a naive "breakout" rule has *no* edge on
average — **the edge lives entirely in the conditioning**.

### Out-of-sample validation (2021–2026)

| Config | h5 | h20 | h60 | h120 |
|---|---|---|---|---|
| N252 + 2x vol | +0.25% (p=.047) | +0.50% (p=.031) | +1.48% (p=.002) | +2.41% (p=.002) |
| N63 + 1.5x vol | +0.02% | +0.24% (p=.056) | +0.79% (p=.001) | n/a |
| N252 + 1.5x vol | +0.18% (p=.023) | +0.61% (p<.001) | +1.30% (p<.001) | n/a |

The OOS edge is consistent with the *regime hypothesis*: 2021–2026 was a
strong-momentum regime, so breakouts worked; 2010–2020 was choppier and
they did not. This is honest evidence, not a certified alpha.

### Reality Check

Observed best in-sample excess (h20): **−0.19%** (N20 + 2x vol).
Bootstrap p = **0.891**; Bonferroni p = 0.013 (significant only in the
wrong direction). Conclusion: **no breakout configuration beats the
baseline in-sample once selection bias is accounted for**. The in-sample
edge is not real; the OOS edge is regime-dependent.

### Momentum vs mean-reversion (h20 excess by quintile)

| Metric | Q1 | Q3 | Q5 (most extended) |
|---|---|---|---|
| `dist_sma200` | +0.19% | −0.17% | **+0.15%** |
| `mom12` | +0.08% | −0.14% | **+0.23%** |
| `rsi14` | +0.15% | +0.01% | −0.08% |

Extended / high-momentum names **do not mean-revert** on 5–60d horizons;
if anything the top momentum/extension quintiles have slightly positive
excess. Mean-reversion is the wrong bet for a fresh relative-strength high.

## Reproducing

```bash
VENV=~/.local/share/opencode/trading-mcp-venv
cd opencode-skills/mcp

# smoke run (120 symbols, ~1 min)
$VENV/bin/python -m research.breakout_calibration.run_calibration --quick

# full run (~1-2 min with cache warm; downloads only on first run)
$VENV/bin/python -m research.breakout_calibration.run_calibration

# tests + lint
$VENV/bin/python -m pytest research/breakout_calibration/test_calibration.py -q
$VENV/bin/python -m pylint research/breakout_calibration --disable=duplicate-code
```

OHLCV is cached in `data_cache/` (pickle) so reruns are fast.

## Outputs

| File | Purpose |
|---|---|
| `output/thresholds.json` | calibrated thresholds + caveats, consumed by Phase 2 |
| `output/report.json` | full machine-readable report (all cells) |
| `output/report.md` | human-readable tables |

## Module layout

| Module | Responsibility |
|---|---|
| `config.py` | sample period, grid, split dates, bootstrap settings |
| `schema.py` | Pydantic v2 models for every artifact |
| `dataset.py` | universe loading + cached yfinance OHLCV |
| `features.py` | indicators (SMA, ATR, RSI, volume, momentum), breakout mask |
| `calibration.py` | horizon stats, profit factor, White Reality Check |
| `run_calibration.py` | orchestration + artifact rendering |
| `test_calibration.py` | 12 synthetic-data unit tests |

## Verified vs assumed

**Verified** (real data, reproducible): breakout grid IS/OOS, baseline,
regime conditioning, momentum quintiles, stop/expectancy curves, Reality
Check, the mean-reversion-bias quantification.

**Assumed / not verified**: entry at close without slippage or
commission; uniform daily liquidity across the universe; GEX overlaid
qualitatively only; the point-in-time universe has survivorship bias.

## Handoff to Phase 2

Phase 2 should load `output/thresholds.json` and enforce:

1. a **quantified breakout trigger** (not a vibe): close > prior 252d high
   with 2x volume and close > SMA200;
2. an **anti-mean-reversion guard**: never fade a name satisfying the
   breakout trigger solely because it is "extended" or "at a gamma wall";
3. stop at `2.0 × ATR(14)` and a 60–120 day hold budget;
4. GEX treated as a **tie-breaker / risk overlay**, never as a
   standalone sell signal.
