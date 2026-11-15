/**
 * Live option data for the open option positions of one dataset: the command
 * template, the argument list, the chain parser, the valuation and the text
 * block. No `vscode` import and no process here; `marketDataService.ts` is the
 * only module that starts a process.
 *
 * The block never invents a number: a missing chain or a missing quote becomes
 * `n/a` and a named limitation line.
 */
import { homedir } from 'node:os';
import { formatGeneratedAt } from './context.ts';
import { OPTION_MULTIPLIER } from './optionSymbol.ts';
import type { OptionContract, OptionPosition } from './optionSymbol.ts';

/** Maximum number of distinct `ticker|expiry` pairs requested in one send. */
export const MAX_MARKET_DATA_REQUESTS = 24;

/**
 * How many CLI processes run at the same time. Each process costs 10 s to 20 s
 * and a Python interpreter, so the pool is small on purpose.
 */
export const MARKET_DATA_CONCURRENCY = 4;

/** How close a quoted strike must be to the contract strike. */
export const STRIKE_TOLERANCE = 0.001;

export interface MarketDataCommand {
  readonly command: string;
  /** Arguments before `fetch options`, typically `['-m', 'trading_mcp.trading_cli']`. */
  readonly baseArgs: readonly string[];
}

/**
 * Split a whitespace-separated template such as
 * `/path/python -m trading_mcp.trading_cli`. A leading `~/` expands to the home
 * directory. No other shell expansion: the parts go to `execFile` as an
 * argument list, never to a shell.
 */
export function parseMarketDataCommand(template: string): MarketDataCommand | null {
  if (typeof template !== 'string') {
    return null;
  }
  const parts = template
    .trim()
    .split(/\s+/)
    .filter((part) => part.length > 0);
  const command = parts[0];
  if (command === undefined) {
    return null;
  }
  const expanded = command.startsWith('~/') ? `${homedir()}${command.slice(1)}` : command;
  return { command: expanded, baseArgs: parts.slice(1) };
}

const TICKER = /^[A-Z][A-Z0-9.-]{0,9}$/i;

/** `[...baseArgs, 'fetch', 'options', ticker, '--expiry', expiry]`, or `null` for a bad ticker. */
export function buildFetchArgs(
  baseArgs: readonly string[],
  ticker: string,
  expiry: string
): string[] | null {
  const symbol = ticker.trim();
  if (!TICKER.test(symbol)) {
    return null;
  }
  return [...baseArgs, 'fetch', 'options', symbol, '--expiry', expiry];
}

/** Key of one chain: `root|expiry`, the same key on every side. */
export function chainKey(ticker: string, expiry: string): string {
  return `${ticker}|${expiry}`;
}

export interface OptionQuote {
  readonly strike: number;
  readonly bid: number | null;
  readonly ask: number | null;
  readonly delta: number | null;
  readonly theta: number | null;
  readonly impliedVolatility: number | null;
}

export interface ChainData {
  readonly ticker: string;
  readonly underlyingPrice: number | null;
  readonly dte: number | null;
  readonly expiry: string | null;
  readonly calls: readonly OptionQuote[];
  readonly puts: readonly OptionQuote[];
  /** ISO time of the parse. `n/a` in the block when the caller supplies its own time. */
  readonly fetchedAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * yfinance writes `impliedVolatility: 0` for a strike without a quote and keeps
 * the fitted value in `iv_used`. A zero is not an implied volatility, so the
 * fitted value wins when the quote field is zero.
 */
function impliedVolatilityOf(raw: Record<string, unknown>): number | null {
  const quoted = finiteNumber(raw['impliedVolatility']);
  if (quoted !== null && quoted > 0) {
    return quoted;
  }
  const used = finiteNumber(raw['iv_used']);
  return used !== null && used > 0 ? used : null;
}

function toQuote(raw: unknown): OptionQuote | null {
  if (!isRecord(raw)) {
    return null;
  }
  const strike = finiteNumber(raw['strike']);
  if (strike === null) {
    return null;
  }
  return {
    strike,
    bid: finiteNumber(raw['bid']),
    ask: finiteNumber(raw['ask']),
    delta: finiteNumber(raw['delta']),
    theta: finiteNumber(raw['theta']),
    impliedVolatility: impliedVolatilityOf(raw)
  };
}

function toQuotes(raw: unknown): OptionQuote[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map(toQuote).filter((quote): quote is OptionQuote => quote !== null);
}

/**
 * The JSON of `trading_cli fetch options`. Missing fields and non-finite
 * numbers become `null`; text that is not a JSON object returns `null`. Never
 * throws.
 */
export function parseChainJson(text: string, ticker: string): ChainData | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  const payloadTicker = parsed['ticker'];
  const expiry = parsed['selected_expiry'] ?? parsed['expiry'];
  return {
    ticker:
      typeof payloadTicker === 'string' && payloadTicker.trim().length > 0
        ? payloadTicker.trim().toUpperCase()
        : ticker.trim().toUpperCase(),
    underlyingPrice: finiteNumber(parsed['underlying_price']) ?? finiteNumber(parsed['underlyingPrice']),
    dte: finiteNumber(parsed['dte']),
    expiry: typeof expiry === 'string' && expiry.trim().length > 0 ? expiry.trim() : null,
    calls: toQuotes(parsed['calls']),
    puts: toQuotes(parsed['puts']),
    fetchedAt: new Date().toISOString()
  };
}

export interface OptionRow {
  readonly contract: OptionContract;
  readonly netQuantity: number;
  /** Trade currency of the position. The money format of the block needs it. */
  readonly currency: string;
  readonly mark: number | null;
  readonly positionValue: number | null;
  readonly unrealized: number | null;
  readonly delta: number | null;
  readonly theta: number | null;
  readonly impliedVolatility: number | null;
  readonly quoteSource: 'mid' | 'none';
}

function midOf(quote: OptionQuote): number | null {
  if (quote.bid === null || quote.ask === null) {
    return null;
  }
  const sum = quote.bid + quote.ask;
  return sum > 0 ? sum / 2 : null;
}

/**
 * One row per position. `mark = (bid + ask) / 2`, `positionValue = mark * 100 *
 * netQuantity`, `unrealized = positionValue - cashFlowPerContract`. A missing
 * chain, a missing quote or a zero bid and ask give `null`, never a zero.
 */
export function valueOptions(
  positions: readonly OptionPosition[],
  chains: ReadonlyMap<string, ChainData>
): OptionRow[] {
  return positions.map((position) => {
    const chain = chains.get(chainKey(position.contract.root, position.contract.expiry));
    const quotes =
      chain === undefined ? [] : position.contract.kind === 'call' ? chain.calls : chain.puts;
    const quote =
      quotes.find((candidate) => Math.abs(candidate.strike - position.contract.strike) <= STRIKE_TOLERANCE) ??
      null;
    const mark = quote === null ? null : midOf(quote);
    const positionValue = mark === null ? null : mark * OPTION_MULTIPLIER * position.netQuantity;
    const unrealized =
      positionValue === null || !Number.isFinite(position.cashFlowPerContract)
        ? null
        : positionValue - position.cashFlowPerContract;
    return {
      contract: position.contract,
      netQuantity: position.netQuantity,
      currency: position.tradeCurrency,
      mark,
      positionValue,
      unrealized,
      delta: quote?.delta ?? null,
      theta: quote?.theta ?? null,
      impliedVolatility: quote?.impliedVolatility ?? null,
      quoteSource: mark === null ? 'none' : 'mid'
    };
  });
}

export interface MarketDataError {
  readonly ticker: string;
  readonly message: string;
}

export interface MarketDataBlockOptions {
  /** One entry per chain that failed, with the reason. */
  readonly missing?: readonly MarketDataError[];
  /** Keys skipped by {@link MAX_MARKET_DATA_REQUESTS}, named as `root|expiry`. */
  readonly omitted?: readonly string[];
}

function money(value: number | null, code: string): string {
  if (value === null || !Number.isFinite(value)) {
    return 'n/a';
  }
  return `${code} ${value.toFixed(2)}`;
}

function decimals(value: number | null): string {
  return value === null || !Number.isFinite(value) ? 'n/a' : value.toFixed(4);
}

function percent(value: number | null): string {
  return value === null || !Number.isFinite(value) ? 'n/a' : `${(value * 100).toFixed(1)}%`;
}

function contractLabel(contract: OptionContract): string {
  return `${contract.root} ${contract.expiry} ${contract.kind} ${contract.strike.toFixed(3)}`;
}

function currencyFor(rows: readonly OptionRow[], key: string): string {
  const row = rows.find((candidate) => chainKey(candidate.contract.root, candidate.contract.expiry) === key);
  const code = row?.currency.trim() ?? '';
  return code.length > 0 ? code : 'USD';
}

/**
 * The markdown block, in this order: the UTC fetch time, the yfinance source
 * through the local trading CLI, the spot and the DTE per ticker, one line per
 * contract with the mark, the position value, the unrealized P&L and the
 * Greeks, then the limitations.
 */
export function renderMarketDataBlock(
  rows: readonly OptionRow[],
  chains: ReadonlyMap<string, ChainData>,
  fetchedAtIso: string,
  options: MarketDataBlockOptions = {}
): string[] {
  const lines: string[] = [
    '## Live option data',
    `Prices fetched: ${formatGeneratedAt(fetchedAtIso)} UTC.`,
    'These prices come from yfinance through the local trading CLI. They are not IBKR quotes and not execution prices.',
    'Spot price per ticker with the days to expiry (DTE):'
  ];

  const keys = [...new Set(rows.map((row) => chainKey(row.contract.root, row.contract.expiry)))].sort();
  if (keys.length === 0) {
    lines.push('- none.');
  }
  for (const key of keys) {
    const chain = chains.get(key);
    if (!chain) {
      continue;
    }
    const [ticker = key, expiry = 'n/a'] = key.split('|');
    const code = currencyFor(rows, key);
    const spot = money(chain.underlyingPrice, code);
    const dte = chain.dte === null ? 'n/a' : String(chain.dte);
    lines.push(`- ${ticker} ${expiry}: spot ${spot}, DTE ${dte}.`);
  }

  if (rows.length > 0) {
    lines.push(
      '',
      '| Contract | Net qty | Strike | Mark | Position value | Unrealized P&L | Delta | Theta | IV |',
      '| --- | --- | --- | --- | --- | --- | --- | --- | --- |'
    );
    for (const row of rows) {
      lines.push(
        `| ${contractLabel(row.contract)} | ${row.netQuantity} | ${money(row.contract.strike, row.currency)} | ` +
          `${money(row.mark, row.currency)} | ${money(row.positionValue, row.currency)} | ` +
          `${money(row.unrealized, row.currency)} | ${decimals(row.delta)} | ${decimals(row.theta)} | ` +
          `${percent(row.impliedVolatility)} |`
      );
    }
  }

  lines.push(
    '',
    `Multiplier ${OPTION_MULTIPLIER} applies to every line: position value = mark * ${OPTION_MULTIPLIER} * net quantity, ` +
      `and unrealized P&L = position value - trade cash flow, where the trade cash flow is price * ${OPTION_MULTIPLIER} * quantity.`,
    'Mark = (bid + ask) / 2. A quote with no bid and no ask gives n/a, never a zero.'
  );

  const missing = options.missing ?? [];
  const omitted = options.omitted ?? [];
  for (const error of missing) {
    lines.push(`Live option data is missing for ${error.ticker} — ${error.message}`);
  }
  if (omitted.length > 0) {
    lines.push(
      `Live option data was requested for ${MAX_MARKET_DATA_REQUESTS} chains only; not requested: ` +
        `${omitted.join(', ')}. Narrow the position list or raise the cap.`
    );
  }
  return lines;
}
