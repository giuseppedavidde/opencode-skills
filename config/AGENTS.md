# Global Rules

## Multi-Agent Architecture
This OpenCode instance uses automatic model routing to save tokens:
- **Router (build agent)**: deepseek-v4-flash — receives all requests, classifies, delegates
- **@trade**: glm-5.2 — trading, options, market analysis 
- **@coder**: glm-5.2 — complex coding, refactoring, multi-file changes 
- **@graphify_helper**: deepseek-v4-flash — smart graphify orchestrator, builds/updates/queries knowledge graphs
- **@skill_updater**: deepseek-v4-flash — updates skills that depend on -src submodules (graphify, book-to-skill, quant-mind, karpathy)
- **@explore / @scout**: deepseek-v4-flash — code search / web research

The router delegates based on keywords. Trading requests go to @trade, complex coding to @coder, skill updates to @skill_updater, graphify requests to @graphify_helper.
All agents read these AGENTS.md rules. See opencode.json for full agent configuration.

## Python Virtual Environment Mandatory
CRITICAL: Before ANY Python operation (install, run, test), load @skills/python-venv. You MUST use a virtual environment. Never `pip install` on the system Python.
- Use a SINGLE shared venv at `/tmp/opencode/.venv` for all temporary work. Never create duplicate venvs.

## Python Development Standards
CRITICAL: Whenever working with Python, you MUST load and strictly adhere to the instructions defined in @skills/python-pydantic.

This includes:
- Mandatory use of Pydantic for data models.
- Extensive use of type hinting.
- Ensuring all code is PEP 8 compliant and pythonic.
- Verifying all Python code with `pylint` before proposing it to the user.

## Graphify Knowledge Graph
CRITICAL: Whenever you need to understand a codebase, project architecture, or file relationships, load the @skills/graphify skill and use `/graphify .` to build a knowledge graph. This turns any folder into a queryable graph with community detection, god nodes, and surprising connections.

## Trading Analysis
For ALL market analysis tasks, load the relevant @skills directly. The skills are well-organized and handle MCP usage internally.
- Market scanning → @skills/market-accumulation-scanner
- Stock/crypto analysis → @skills/stock-crypto-analysis
- Options analysis → @skills/options-analysis
- Options strategy → @skills/options-strategy-suggestions
- Market data → @skills/market-data-fetch
- Framework knowledge → use `get_skill_knowledge` for on-demand Wyckoff, VPA, VP concepts
- **Bali volatility signals** → dopo analyze_stock, carica @skills/quant-mind-skill e lancia:
  `bash python3 .../bali_signals.py <TICKER> --json`
- **Bakshi VRP signals** → durante analisi opzioni, carica @skills/quant-mind-skill e lancia:
  `bash python3 .../bakshi_kapadia_signals.py <TICKER> --json`
- **TS-MOM signal** → dopo analyze_stock, carica @skills/quant-mind-skill e lancia:
  `bash python3 .../tsmom_signals.py <TICKER> --lookback 12 --json`
- **LGBM Ensemble Signal** → usa `predict_or_train.py` (invece di predict_live.py) per garantire sempre un modello allenato. Script in `@skills/lgbm-trader-skill/scripts/predict_or_train.py`. Controlla SEMPRE il campo `model` nel JSON: se null, LGBM non contribuisce.

Always run `get_macro_context` FIRST before any analysis.

### LGBM Trading System — Integrazione Obbligatoria

L'agente trade DEVE integrare il segnale LGBM nello stesso blocco degli altri segnali (Bali, TS-MOM).

**Regole**:
1. **Sempre `predict_or_train.py`** — mai chiamare `predict_live.py` direttamente.
   `predict_or_train.py` allena automaticamente il modello se il ticker è nuovo.
2. **Verifica `model` nel JSON** — se `model` è `null`, il modello non è disponibile.
   In tal caso, NON includere LGBM nel weighted average.
3. **Ridistribuzione pesi** quando LGBM non disponibile:
   ```python
   SE modello esiste:
       final = 0.40*stock + 0.20*bali + 0.20*tsmom + 0.20*lgbm
   ALTRIMENTI:
       final = 0.50*stock + 0.25*bali + 0.25*tsmom
   ```
4. **Path script**: `/home/giuseppe/.config/opencode/skills/lgbm-trader-skill/scripts/predict_or_train.py`
5. **Training automatico**: se il ticker non ha modello, lo script allena lo stacking
   ensemble (30-60s). È un costo una tantum per ticker — dopo la prima volta va in fast path.

### Bakshi & Kapadia (2003) — Volatility Risk Premium Foundation
Paper fondante che dimostra che il volatility risk premium (VRP) ESISTE ed è NEGATIVO.
Si collega direttamente a Bali & Hovakimian: Bakshi mostra CHE il premio esiste (time-series),
Bali mostra COME varia tra azioni (cross-section).

Key findings da applicare:
1. **Delta-hedged call portfolios underperformano zero**: ATM S&P 500 calls perdono ~$0.43
   (8% del valore), 68% delle osservazioni negative. Il VRP è strutturalmente negativo.
2. **La perdita è massima per opzioni ATM** (vega massimo) e diminuisce per OTM/ITM.
   → Le strategie di vendita opzioni sono più redditizie su strikes ATM.
3. **La perdita aumenta con la volatilità**: a vol bassa (8%) il premio è −3.6% del valore,
   a vol alta (16%) arriva a −19.6%. → Timing: vendere opzioni quando IV è alta.

Implicazioni per il trading:
- **Short options strutturalmente profittevoli** nel lungo periodo, MA con jump risk
- **Dispersion trading**: vendere index options, comprare single-stock options
- **Variance swap analogy**: il delta-hedged portfolio replica un variance swap
- Il VRP è distinto dal jump risk (robustezza anche controllando per skew/kurtosi)

### Bali & Hovakimian (2009) Signals
Two cross-sectional volatility spread signals che traducono Bakshi & Kapadia in segnali stock-specifici:
1. **RVol–IVol spread** (Volatility Risk Premium): RV30gg - ATM straddle IV.
   - Score 0-100 (100 = bearish: RV >> IV → volatility risk premium esaurito)
   - Negative spread → expected returns positive (Bali Table 2: −0.63%/−0.73%/month)
   - Positive spread → expected returns negative
   - Bakshi conferma: RV < IV = VRP pagato → vendita opzioni profittevole
2. **CVol–PVol spread** (Jump Risk): Call ATM IV - Put ATM IV.
   - Score 0-100 (100 = bullish: Call IV >> Put IV → jump risk up)
   - Positive spread → expected returns positive (Bali Table 3: +1.05%/+1.49%/month)
   - Negative spread → expected returns negative
3. **Composite Bali**: 60% RVol-bullish + 40% CVol-PVol (merged into analyze_stock verdict at 20% weight)

### Moskowitz, Ooi & Pedersen (2012) — Time Series Momentum
Paper fondante del trend-following sistematico. Aggiunge una dimensione oggettiva di trend
alla stock analysis, indipendente dai fattori cross-sectional.

Key findings da applicare:
1. **Universale**: 58/58 futures mostrano TS-MOM positivo, in 4 asset class (equity, valute,
   commodity, bonds). Sharpe ratio > 1.0 su portafoglio diversificato.
2. **Signal**: sign(return_{t-12:t-1}) — segno del rendimento cumulato degli ultimi 12 mesi
   (escludendo l'ultimo mese). Holding period: 1 mese.
3. **Volatility scaling**: posizione = signal × (target_vol / σ_EWMA). Target: 40% annuo.
   Riduce posizioni quando la vol è alta (TSLA 0.74x) e le aumenta quando è bassa (SPY 2.83x).
4. **TS-MOM ≠ XSMOM**: il time series momentum è guidato dall'auto-covarianza dei rendimenti,
   non dal ranking relativo. Spiega interamente il cross-sectional momentum (UMD alpha non significativo).
5. **Payoff straddle-like**: performa meglio nei mercati estremi (up E down) — hedge per crash risk.
   Non correlato a VIX, TED spread, sentiment.

Score 0-100: 0=forte bearish, 100=forte bullish (merged into analyze_stock verdict at 20% weight)

### Position Repair Mandatory (CRITICAL)
When a user presents an EXISTING options position and asks what to do / how to fix it:
1. Run the standard flow: macro → `analyze_stock` → `analyze_options` → `suggest_options_strategy`
2. **MANDATORY RISK AUDIT** — after step 1, audit the position for these risk flags:
   - **Naked options** (short call/put without protection) → propose a spread to cap max loss
   - **Negative gamma** on a directional position → propose adding long options to flip gamma positive
   - **Unbalanced ratio** (e.g., 2:1 short vs long) → propose rebalancing to reduce leverage
   - **Deep OTM positions** (delta < 0.15 total) → propose repair or close
3. For EACH risk flag found, test at least 2 strikes with `analyze_options` in parallel
4. Present a comparison table (current vs proposed adjustments) with: max loss, breakeven, net credit/debit, delta, gamma
5. The directional verdict alone is NOT sufficient — always optimize risk regardless of outlook
6. Query `get_skill_knowledge("options-playbook")` for relevant strategy definitions when proposing repairs

### Options Execution Rules (CRITICAL — zero tolerance)
These rules apply to ANY options trade proposal (repair, diagonal, spread, roll, etc.):

1. **TIME-SHIFTED PREMIUMS — NEVER quote today's premium for a future date.**
   - If proposing "on date X, sell Y strike @ $Z", $Z must be computed as: today's_premium − (theta × days_until_X) − (delta × expected_price_move).
   - Use `bash` with `python3` to compute this. Show the work.
   - Example WRONG: "Il 10 luglio vendi 300C Jul17 @ $3.18" — $3.18 is today, not July 10.
   - Example RIGHT: compute theta decay over N days, subtract from today's mid.

2. **BID-ASK SPREADS — never assume fills at mid.**
   - Fetch real bid/ask via `fetch_options_chain` or `analyze_options`. If unavailable, estimate spread as 25-35% of mid for LHX-tier liquidity and flag the uncertainty.
   - Compute P&L using the **bid** for sells and the **ask** for buys.
   - If spread >50% of mid, warn the user the trade may not be executable at acceptable prices.

3. **ROLL BREAK-EVEN — compute the exact price where roll flips from credit to debit.**
   - Use `bash` with `python3`. Sweep prices from current to short strike + 20%.
   - At each price: estimate buyback cost of current short option (intrinsic + residual time value) vs premium of new short option at roll strike/expiry.
   - Report the break-even price. Never say "you can always roll at a credit."

4. **CHECK ALL EXPIRATIONS — never propose only the nearest monthly.**
   - Inspect `expirations` array from `analyze_stock` options_context.
   - Evaluate at least the next 4-5 expirations (weekly + monthly) before recommending a strike/expiry.
   - Skip expirations that encompass binary events (earnings) unless user explicitly accepts the risk.

 5. **PROBABILITY CHECK — never propose adjustment with <50% estimated success probability.**
   - For each proposed trade, check `max_profit_prob` from `analyze_options`.
   - If <50%, either widen the strike or skip the trade. Do not propose sub-coinflip trades.

### Trading outputs + Headroom Compression
Trading outputs (scans, analyses, options chains) are large JSON payloads.
Compress them with `headroom_compress` BEFORE reasoning over the content.
- scan results with 10+ tickers → compress immediately, retrieve only top 3 for deep dive
- analyze_stock → compress, retrieve only dimensions/verdict/confidence
- fetch_options_chain → compress the full chain, retrieve only ATM strikes + IV metrics
- Never paste raw trading JSON into reasoning context uncompressed
- Batch compress: if scan + 3× analyze_stock return in one turn, compress all in parallel

## Headroom Compression — MANDATORY & ACTIVE
CRITICAL: You MUST use headroom to compress content and minimize token usage at ALL times.
This is NOT optional or situational: every session must demonstrate measurable compression.
A session that ends with `headroom_stats` showing 0 compressions is a FAILED session.

### When to compress (threshold: ≥800 chars of tool output)
Compress with `headroom_compress` BEFORE reasoning over the content, in these cases:
1. **Any tool result ≥800 chars** — bash, read, grep, glob, webfetch, task outputs.
2. **JSON/CSV reports** — scanner outputs, deep-dive JSON, options chain dumps, earnings data.
3. **Multi-file reads** — when reading 2+ files in parallel, compress each non-trivial one.
4. **Skill content** — when a loaded skill's SKILL.md is long, compress it after first read.
5. **Large bash outputs** — piped command results, directory listings, log tails.

### Workflow rules — GOAL: maximize token savings
- **Compress the RAW tool output, not a summary**: ALWAYS pass the original, intact tool result
  to `headroom_compress`. NEVER substitute it with your own hand-written summary, excerpt, or
  paraphrase. A summary bypasses the compressor and yields `router:noop` (0 tokens saved).
  The compressor needs the full text to achieve real 70-85% reduction.
- **Compress early, retrieve late**: compress on first sight, use `headroom_retrieve` with the hash
  only when you actually need full detail (numbers, exact strings, code).
- **Always prefer compression over truncation** — Never use head/tail to limit output when you
  can compress and retrieve on demand.
- **Check `headroom_stats` at least twice per session**: once mid-session, once at the end.
- **Quote hashes, not full content** — when referring to compressed data, reference the hash,
  don't re-paste the original.
- **Batch compress**: if multiple tools return large content in one turn, call `headroom_compress`
  once per result, in parallel.
- **Verify non-noop**: after each compress, confirm the returned `strategy` is NOT `router:noop`.
  If it IS noop, the input was too small or already compressed — feed larger raw content next time.

### Anti-patterns (forbidden)
- **Passing a hand-written summary to `headroom_compress` instead of the raw tool output** (causes
  noop, 0 savings — this is the #1 failure mode).
- Reasoning over >800-char tool output without compressing it first.
- Pasting full scanner JSON / analysis JSON into your reasoning context uncompressed.
- Ending a session without calling `headroom_stats`.
- Using `head`/`tail`/`limit` on tool outputs instead of compressing.
- Treating the rule as "best effort": it is a hard requirement, like using a Python venv.
