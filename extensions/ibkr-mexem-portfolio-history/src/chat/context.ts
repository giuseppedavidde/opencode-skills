/**
 * Builds the system context handed to the chat model: the whole portfolio state
 * the "Trades in range" table already shows, in plain text.
 *
 * No `vscode` import and no credential input: the builder cannot leak a token
 * because it never receives one.
 */
import type { DatasetPayload, TradeRow } from '../panel/protocol.ts';

/** Default ceiling on the CSV rows embedded in the context. */
export const DEFAULT_MAX_CONTEXT_TRADES = 400;

export interface ChatContextOptions {
  /** Maximum number of trade rows embedded as CSV. Defaults to 400. */
  readonly maxContextTrades?: number;
  /** Display name in the header. Defaults to the extension display name. */
  readonly extensionName?: string;
}

export interface ChatContextResult {
  readonly text: string;
  readonly tradeRowsIncluded: number;
  readonly tradeRowsOmitted: number;
  /** Rough estimate: characters divided by four, rounded up. */
  readonly approxTokens: number;
}

/** Condensed writer and analyst stance, adapted from the `trade` agent. */
export const TRADE_AGENT_PERSONA = `You are the Trade analyst inside the VS Code extension "IBKR Mexem Portfolio History".

You have ONE dataset in context: the user's IBKR Flex trade confirmations, already filtered by date range and account.
This dataset is the SAME content the portfolio panel shows after "Fetch report": the notices, every summary tile,
the chart series, the monthly and per-symbol tables and the trade rows.
The user can discuss portfolio state with you directly. Answer from that dataset only.

Analytical stance:
- Evidence first. Every number you quote must come from the dataset below. Cite the figure, not a feeling.
- Read the section "Currency of every block" first. Each block names its own currency. A number has the
  currency of its block, never the currency you expect.
- The P&L column of the CSV carries its currency in the column name: realized_pnl_eur is EUR, realized_pnl_usd
  is USD. Sum that column and report the sum in that same currency.
- The base-currency P&L includes the FX result; a trade-currency P&L excludes it. They are NOT one number in
  two units. Quote both totals and say which one includes the FX effect.
- A wrong currency label is a wrong answer. Before you write a currency code, check the block that holds the
  number. If the block does not name a currency, say the currency is unknown.
- Risk matters more than return. Name drawdown, loss concentration and exposure when they are relevant.
- Say "the data does not show this" when the dataset cannot answer. Do not guess.
- Prefer concrete tables over prose for numbers. Keep a recommendation short and testable.
- A section "Live option data" may follow the trade CSV. It holds the price and the Greeks of the open option
  positions, fetched by the local trading CLI. Use it only for those positions, name its fetch time and name its
  source. Without that section you have no live quote, no option chain and no Greeks.
- Never invent a price, an implied volatility or a market event. If the user asks for a live quote that the context
  does not show, state the limitation.
- Do not give tax, legal or accounting advice as fact. Mark it as a general remark.

Writing rules (ASD-STE100, mandatory):
- Maximum 20 words per sentence in a procedure, 25 words in a description.
- One idea per sentence. Active voice. Simple tenses. Precise verbs: use, compute, check, close.
- One term per concept for the whole answer.
- Procedures go in a numbered list. One action per step.
- No idioms, no metaphor, no slang.
- Define every abbreviation at first use, for example BE = break-even.
- Exact numbers with units: EUR 1234.56. Never "about a thousand".
- No preamble and no closing filler. Start with the answer.`;

export function approximateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function amount(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  return `${currency} ${value.toFixed(2)}`;
}

function ratio(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function plain(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  return value.toFixed(digits);
}

/** `2026-11-14T23:20:00.000Z` -> `2026-11-14 23:20` in UTC. */
export function formatGeneratedAt(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  const date = parsed.toISOString().slice(0, 10);
  const time = parsed.toISOString().slice(11, 16);
  return `${date} ${time}`;
}

function csvCell(value: string | number | null): string {
  if (value === null) {
    return '';
  }
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * The P&L value of one row, in `currency`. `displayPnl` is the same per-row
 * value the panel formats, so the CSV column and the table header can never
 * disagree on the currency again.
 */
export function displayPnlOf(trade: TradeRow): number | null {
  const value = trade.displayPnl;
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  return trade.realizedPnl === null || !Number.isFinite(trade.realizedPnl) ? null : trade.realizedPnl;
}

/** The CSV header of the P&L column: the currency code is part of the name. */
export function tradeCsvHeader(currency: string): string {
  return `date,time,symbol,side,qty,price,trade_ccy,realized_pnl_${currency.toLowerCase()},pnl_source`;
}

function tradeCsvRow(trade: TradeRow): string {
  const pnl = displayPnlOf(trade);
  return [
    csvCell(trade.date),
    csvCell(trade.time),
    csvCell(trade.symbol),
    csvCell(trade.buySell),
    csvCell(trade.quantity),
    csvCell(trade.price),
    csvCell(trade.currency),
    csvCell(pnl === null ? '' : pnl.toFixed(2)),
    csvCell(trade.pnlSource)
  ].join(',');
}

interface SymbolAggregate {
  symbol: string;
  pnl: number;
  trades: number;
}

/** Symbol totals over the rows carried by the payload (newest-first, capped). */
export function aggregateBySymbol(rows: readonly TradeRow[]): SymbolAggregate[] {
  const buckets = new Map<string, SymbolAggregate>();
  for (const row of rows) {
    // Display-currency values, never the base-currency ones: the table header
    // names the display currency, so the sum must use the same currency.
    const pnl = displayPnlOf(row);
    if (pnl === null) {
      continue;
    }
    const symbol = row.symbol || 'UNKNOWN';
    const current = buckets.get(symbol) ?? { symbol, pnl: 0, trades: 0 };
    current.pnl += pnl;
    current.trades += 1;
    buckets.set(symbol, current);
  }
  return [...buckets.values()];
}

function monthlyTable(dataset: DatasetPayload): string[] {
  const currency = dataset.displayCurrency;
  const series = dataset.analytics.monthly;
  if (series.length > 0) {
    return [
      `| Month | Realized P&L (${currency}) | Trades |`,
      '| --- | --- | --- |',
      ...series.map((bar) => `| ${bar.month} | ${bar.pnl.toFixed(2)} | ${bar.trades} |`)
    ];
  }
  // No analytics series: derive it from the rows in the payload.
  const buckets = new Map<string, { pnl: number; trades: number }>();
  for (const row of dataset.trades) {
    if (row.realizedPnl === null || !Number.isFinite(row.realizedPnl)) {
      continue;
    }
    const month = row.date.slice(0, 7);
    if (month.length !== 7) {
      continue;
    }
    const current = buckets.get(month) ?? { pnl: 0, trades: 0 };
    current.pnl += row.realizedPnl;
    current.trades += 1;
    buckets.set(month, current);
  }
  if (buckets.size === 0) {
    return ['No month has a realized P&L value.'];
  }
  return [
    `| Month | Realized P&L (${currency}) | Trades |`,
    '| --- | --- | --- |',
    ...[...buckets.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, value]) => `| ${month} | ${value.pnl.toFixed(2)} | ${value.trades} |`)
  ];
}

function symbolTable(dataset: DatasetPayload): string[] {
  const currency = dataset.displayCurrency;
  const aggregates = aggregateBySymbol(dataset.trades);
  if (aggregates.length === 0) {
    return ['No symbol has a realized P&L value.'];
  }
  aggregates.sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl) || a.symbol.localeCompare(b.symbol));
  const top = aggregates.slice(0, 20);
  const rest = aggregates.slice(20);
  const lines = [
    `| Symbol | Realized P&L (${currency}) | Trades |`,
    '| --- | --- | --- |',
    ...top.map((row) => `| ${row.symbol} | ${row.pnl.toFixed(2)} | ${row.trades} |`)
  ];
  if (rest.length > 0) {
    const restPnl = rest.reduce((sum, row) => sum + row.pnl, 0);
    const restTrades = rest.reduce((sum, row) => sum + row.trades, 0);
    lines.push('');
    lines.push(
      `${rest.length} more symbol(s) are not listed: ${restTrades} trade(s), aggregate ${amount(restPnl, currency)}.`
    );
  }
  if (dataset.tradesTruncated) {
    lines.push('');
    lines.push(
      `This table covers the ${dataset.trades.length} rows in the payload, not all ${dataset.meta.rowsInRange} rows in range ` +
        `(payload cap maxTradeRows = ${dataset.tradesCap}).`
    );
  }
  return lines;
}

function commissionsBlock(dataset: DatasetPayload): string[] {
  const lines: string[] = [];
  if (dataset.commissions.length === 0) {
    lines.push('- Commissions: none reported.');
    return lines;
  }
  for (const row of dataset.commissions) {
    const estimate =
      row.estimatedBase === null
        ? 'no base estimate'
        : `≈ ${amount(row.estimatedBase, dataset.baseCurrency)}${row.complete ? '' : ' (partial)'}`;
    lines.push(
      `- Commission ${row.currency}: ${row.commissionCost.toFixed(2)} trade currency over ${row.trades} trade(s); estimate in base ${estimate}`
    );
  }
  lines.push(
    `- Commission estimate in base: ${amount(dataset.commissionEstimateBase, dataset.baseCurrency)}` +
      (dataset.commissionEstimateComplete ? ' (complete)' : ' (partial: at least one row had no report FX rate)')
  );
  return lines;
}

/**
 * The FX effect, in the account base currency, whatever the display currency is.
 * Two totals that differ by the FX result cannot be one number in two units, so
 * this block states both and the exact derivation rule.
 */
export function fxBlock(dataset: DatasetPayload): string[] {
  const base = dataset.baseCurrency;
  const totals = dataset.pnlTotals;
  const lines = [
    `## P&L currency: base vs trade currency (the FX effect)`,
    `- Account base currency: ${base}.`,
    `- Total realized P&L in the base currency, INCLUDING the FX result: ${amount(totals.baseTotal, base)}.`,
    totals.capitalGainsTotal === null
      ? '- Sum of capitalGainsPnl (excluding the FX result): not available in this report; the Flex query did not return the field.'
      : `- Sum of capitalGainsPnl, EXCLUDING the FX result: ${amount(totals.capitalGainsTotal, base)}.`,
    totals.fxTotal === null
      ? '- Sum of fxPnl: not available in this report.'
      : `- Sum of fxPnl: ${amount(totals.fxTotal, base)}.`,
    totals.identityHolds
      ? `- Identity: base total = capital-gains total + FX total (${amount(totals.baseTotal, base)} = ` +
        `${amount(totals.capitalGainsTotal, base)} + ${amount(totals.fxTotal, base)}).`
      : '- Identity: not verifiable for every row, because at least one row lacks capitalGainsPnl or fxPnl.',
    `- Displayed P&L currency of this context: ${dataset.displayCurrency}. The statistics above use it, computed per row.`,
    '- Rule for a trade-currency figure: capitalGainsPnl / rate(tradeCcy -> base, tradeDate). Never fifoPnlRealized / rate, because that reintroduces the FX result.',
    '- Rate direction: 1 unit of fromCurrency = rate units of toCurrency, read from the report <ConversionRate> rows. Missing exact date: nearest earlier report date.',
    '- The base total and a trade-currency total are NOT a unit conversion of each other: one includes the FX result, the other excludes it.'
  ];
  if (totals.rowsWithCapitalGains === 0) {
    lines.push('- No row carries capitalGainsPnl, so a trade-currency figure falls back to the base figure divided by the rate and is approximate.');
  }
  return lines;
}

function statisticsBlock(dataset: DatasetPayload): string[] {
  const stats = dataset.analytics.stats;
  const currency = dataset.displayCurrency;
  const base = dataset.baseCurrency;
  const profitFactor = stats.profitFactorInfinite
    ? 'infinite (no losing trade)'
    : plain(stats.profitFactor);
  const best = stats.bestSymbol;
  const worst = stats.worstSymbol;
  // The panel labels the first tile by view: the trade-currency total excludes
  // the FX result, the base total includes it. One number, one label.
  const totalLabel =
    currency === base
      ? `Total realized P&L (${base}, includes the FX result)`
      : `Total realized P&L (${currency}, trade currency, EXCLUDES the FX result)`;
  return [
    `- ${totalLabel}: ${amount(stats.totalRealizedPnl, currency)}`,
    `- P&L excluding FX (${base}, sum of capitalGainsPnl): ${amount(dataset.pnlTotals.capitalGainsTotal, base)}`,
    `- FX result (${base}, sum of fxPnl): ${amount(dataset.pnlTotals.fxTotal, base)}`,
    `- Trades with realized P&L: ${stats.tradesWithPnl} of ${stats.tradeRows} row(s) downloaded in range`,
    `- Gross profit: ${amount(stats.grossProfit, currency)}`,
    `- Gross loss: ${amount(stats.grossLoss, currency)}`,
    `- Profit factor (gross profit / |gross loss|): ${profitFactor}`,
    `- Win rate (wins / trades with realized P&L): ${ratio(stats.winRate)}`,
    `- Wins / losses / break-even: ${stats.wins} / ${stats.losses} / ${stats.breakEven}`,
    `- Average win: ${amount(stats.averageWin, currency)}`,
    `- Average loss: ${amount(stats.averageLoss, currency)}`,
    `- Largest win: ${amount(stats.largestWin, currency)}`,
    `- Largest loss: ${amount(stats.largestLoss, currency)}`,
    `- Max drawdown: ${amount(stats.maxDrawdown, currency)} (${ratio(stats.maxDrawdownPct)})`,
    `- Sharpe-like (daily, annualized): ${plain(stats.sharpeLike)}`,
    '- Sharpe-like rule: mean / standard deviation of daily realized P&L, multiplied by the square root of 252. ' +
      'It is not a return-based portfolio Sharpe ratio and it uses no risk-free rate.',
    `- Trading days: ${stats.tradingDays}`,
    `- Average holding days: ${stats.averageHoldingDays === null ? 'n/a (no open dates)' : plain(stats.averageHoldingDays, 1)}`,
    `- Best symbol: ${best ? `${best.symbol} ${amount(best.pnl, currency)} over ${best.trades} trade(s)` : 'n/a'}`,
    `- Worst symbol: ${worst ? `${worst.symbol} ${amount(worst.pnl, currency)} over ${worst.trades} trade(s)` : 'n/a'}`,
    ...commissionsBlock(dataset)
  ];
}

/**
 * The two banners the panel shows, in the same words. A user who reads a
 * banner in the panel must find the same statement in the context.
 */
export function panelNoticeBlock(dataset: DatasetPayload): string[] {
  const base = dataset.baseCurrency;
  const currency = dataset.displayCurrency;
  const lines: string[] = [];
  const foreign = dataset.currencies.filter((code) => code !== base);
  if (foreign.length > 0) {
    lines.push(
      `- This report covers ${dataset.currencies.length} trade currencies (${dataset.currencies.join(', ')}). ` +
        `IBKR reports realized P&L in the account base currency (${base}), including the FX result. ` +
        'Trade amounts remain in their own currency. Choose another currency to see the trade-currency result.'
    );
  }
  if (currency !== base) {
    const fx = dataset.pnlTotals.fxTotal;
    const fxPart =
      fx === null
        ? 'The FX effect is not available: this report does not carry fxPnl.'
        : `The FX effect (${amount(fx, base)} in this dataset) is excluded, so the total differs from the ${base} base view.`;
    lines.push(
      `- In ${currency} this is the trade-currency result. ${fxPart} ` +
        'Rates come from the report <ConversionRate> rows, nearest earlier report date when the exact date is missing.'
    );
  }
  return lines.length > 0 ? lines : ['- None.'];
}

/**
 * The chart series the panel draws, reduced to the facts an answer may need:
 * the cumulative curve ends, the worst drawdown and its date, the histogram
 * tails. Every value comes from `dataset.analytics`, never from a rescale.
 */
export function seriesBlock(dataset: DatasetPayload): string[] {
  const analytics = dataset.analytics;
  const currency = dataset.displayCurrency;
  const lines: string[] = [];
  const curve = analytics.curve;
  if (curve.length > 0) {
    const first = curve[0];
    const last = curve[curve.length - 1];
    const start = curve[0];
    const peak =
      start === undefined
        ? undefined
        : curve.reduce((best, point) => (point.cumulative > best.cumulative ? point : best), start);
    if (first && last && peak) {
      lines.push(
        `- Cumulative realized P&L curve: ${curve.length} point(s), from ${first.date} (${amount(first.cumulative, currency)}) ` +
          `to ${last.date} (${amount(last.cumulative, currency)}); peak ${amount(peak.cumulative, currency)} on ${peak.date}.`
      );
    }
  }
  const drawdown = analytics.drawdown;
  if (drawdown.length > 0) {
    const start = drawdown[0];
    const worst =
      start === undefined
        ? undefined
        : drawdown.reduce((low, point) => (point.drawdown < low.drawdown ? point : low), start);
    if (worst) {
      lines.push(`- Deepest drawdown point: ${amount(worst.drawdown, currency)} on ${worst.date}.`);
    }
  }
  const histogram = analytics.histogram;
  if (histogram.length > 0) {
    const start = histogram[0];
    const busiest =
      start === undefined
        ? undefined
        : histogram.reduce((top, bin) => (bin.count > top.count ? bin : top), start);
    if (busiest) {
      lines.push(
        `- Daily P&L histogram: ${histogram.length} bin(s); the fullest bin is ${busiest.label} with ${busiest.count} day(s).`
      );
    }
  }
  return lines.length > 0 ? lines : ['- No chart series in this payload.'];
}

/**
 * One line per block, naming the exact currency of every number in it. A sum
 * of the CSV column must never be reported in the currency of the statistics
 * block, and vice versa.
 */
export function currencyMapBlock(dataset: DatasetPayload): string[] {
  const base = dataset.baseCurrency;
  const currency = dataset.displayCurrency;
  const same = currency === base;
  return [
    `- Statistics, monthly table and symbol table: ${currency}${same ? ' (account base currency)' : ' (trade currency, excludes the FX result)'}.`,
    `- CSV column realized_pnl_${currency.toLowerCase()}: ${currency}, the same per-row value the panel shows in "Realized P&L".`,
    `- Header lines "Base currency" and the FX block: ${base}, the account base currency.`,
    `- trade_ccy column and the price column: the trade currency of that row. Never sum them across rows.`,
    '- A sum of the CSV column is a display-currency sum. Do not label it with the base currency.',
    '- A base-currency total and a display-currency total are two different numbers when the currencies differ. Quote both and name each one.',
    '- When the user asks "how much did I make on SYMBOL", sum the CSV column of that symbol and report it in the CSV currency. Cross-check the result against the symbol table.'
  ];
}

export function buildChatContext(dataset: DatasetPayload, options: ChatContextOptions = {}): ChatContextResult {
  const cap = Math.max(1, Math.trunc(options.maxContextTrades ?? DEFAULT_MAX_CONTEXT_TRADES));
  const name = options.extensionName ?? 'IBKR Mexem Portfolio History';
  const meta = dataset.meta;
  const currency = dataset.baseCurrency;

  const selected = dataset.trades.slice(0, cap);
  const totalRows = dataset.tradesTruncated ? Math.max(meta.rowsInRange, dataset.trades.length) : dataset.trades.length;
  const omitted = Math.max(0, totalRows - selected.length);

  const lines: string[] = [
    `# Portfolio context — ${name}`,
    '',
    `Generated: ${meta.generatedAt}`,
    `Range: ${meta.range.start} → ${meta.range.end} (${meta.range.label})`,
    `Account filter: ${meta.accountFilter ?? 'none (all accounts)'}`,
    `Accounts: ${meta.accounts.length > 0 ? meta.accounts.join(', ') : 'unknown'}`,
    `Base currency: ${currency} (source: ${meta.baseCurrencySource})`,
    `Trade currencies: ${meta.tradeCurrencies.length > 0 ? meta.tradeCurrencies.join(', ') : 'unknown'}`,
    `Rows: ${meta.rowsTotal} returned by IBKR, ${meta.rowsInRange} inside the range, ${meta.rowsWithPnl} with realized P&L`,
    `P&L provenance: ${meta.rowsPnlFromFifo} row(s) from fifoPnlRealized, ${meta.rowsPnlFromProceeds} row(s) approximated from netCashInBase`,
    '',
    `## Currency of every block (read this first)`,
    ...currencyMapBlock(dataset),
    '',
    `## Panel notices (verbatim from the portfolio panel)`,
    ...panelNoticeBlock(dataset),
    '',
    `## Statistics (${dataset.displayCurrency}, full filtered set)`,
    ...statisticsBlock(dataset),
    '',
    `## Chart series (panel charts, reduced)`,
    ...seriesBlock(dataset),
    '',
    ...fxBlock(dataset),
    '',
    `## Monthly realized P&L (full filtered set)`,
    ...monthlyTable(dataset),
    '',
    `## Realized P&L by symbol (top 20 by absolute P&L)`,
    ...symbolTable(dataset),
    '',
    `## Trades (newest first: ${selected.length} of ${totalRows})`,
    '```csv',
    tradeCsvHeader(dataset.displayCurrency),
    ...selected.map(tradeCsvRow),
    '```'
  ];

  if (omitted > 0) {
    lines.push(
      '',
      `${omitted} trade row(s) are omitted from the CSV to keep the context small. ` +
        'The statistics, the monthly table and the symbol table above already cover every row in range. ' +
        'Ask for a narrower date range if you need those rows one by one.'
    );
  }

  lines.push('', '## Warnings');
  if (meta.warnings.length === 0) {
    lines.push('- None.');
  } else {
    for (const warning of meta.warnings) {
      lines.push(`- ${warning}`);
    }
  }

  lines.push(
    '',
    '## Currency semantics (do not mix)',
    `- realized_pnl_base is the account base currency (${currency}).`,
    '- trade_ccy is the trade currency of that row: the price and the commission use it.',
    '- Commissions are reported per trade currency, never converted silently.',
    '- Never sum amounts of different trade currencies. Use the base-currency P&L for totals.',
    `- A P&L in a trade currency (for example USD) excludes the FX result; the base total (${currency}) includes it.`,
    `- UNKNOWN as base currency means the report had no evidence: treat every P&L value as unlabelled, not as EUR.`,
    '',
    '## Limitations',
    '- No live quote, no option chain and no Greeks, unless a section "Live option data" appears above.',
    '- No news and no macro data.',
    '- The Flex Web Service applies no date range: IBKR returned the period saved in the query, and the extension filtered it locally.',
    '- Realized P&L is realized only. Open positions and unrealized P&L are not in this dataset, except in the "Live option data" block, which covers the open option positions only.',
    '- Never invent a price, a volatility or a market event. Say the dataset cannot answer instead.'
  );

  const text = lines.join('\n');
  return {
    text,
    tradeRowsIncluded: selected.length,
    tradeRowsOmitted: omitted,
    approxTokens: approximateTokens(text)
  };
}
