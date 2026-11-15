import { XMLParser } from 'fast-xml-parser';
import { parseFlexDate } from '../core/dates.ts';
import { normaliseCurrencyCode, resolveBaseCurrency, UNKNOWN_CURRENCY } from '../core/currency.ts';
import type { BaseCurrencySource, ConversionRate, PnlSource, Trade } from '../core/types.ts';
import { FlexApiError, FlexEmptyError, FlexParseError } from './errors.ts';

const ATTRIBUTE_PREFIX = '@_';

/**
 * TradeConfirm and Trade rows are attribute-only elements, so attributes must
 * be kept. A prefixed attribute name keeps them distinguishable from child
 * elements.
 */
/** Row element names: `TradeConfirm` (Trade Confirmation query) and `Trade` (Activity query, type="AF"). */
const TRADE_ROW_TAGS: readonly string[] = ['TradeConfirm', 'Trade'];

/**
 * `TradeConfirm` rows come from a Trade Confirmation query. `Trade` rows come
 * from an Activity query. Both are attribute-only elements and both may repeat,
 * so both must be forced into arrays.
 */
const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: ATTRIBUTE_PREFIX,
  parseTagValue: false,
  parseAttributeValue: false,
  trimValues: true,
  isArray: (tagName) => TRADE_ROW_TAGS.includes(tagName)
});

type XmlRecord = Record<string, unknown>;

export interface ParseOptions {
  /**
   * Approximate realized P&L for closing rows that carry no `fifoPnlRealized`.
   * The fallback uses the closing leg's `netCashInBase`, which is already in the
   * account base currency. A trade-currency figure is used only when the trade is
   * already denominated in the base currency. Rows built this way are flagged
   * with pnlSource 'proceeds'. Disable to mark every such row as unknown.
   */
  readonly fallbackFromProceeds?: boolean;
  /**
   * `ibkrHistory.baseCurrency` override. When set to a real ISO code it wins over
   * both `<AccountInformation>` and `<ConversionRate>` detection.
   */
  readonly baseCurrencyOverride?: string;
  /**
   * Transport facts of the fetch that produced this XML. Only used to fill the
   * diagnostics of a {@link FlexEmptyError}; the parser never calls the network.
   */
  readonly fetch?: {
    readonly attempts: number;
    readonly elapsedMs: number;
  };
}

export type EnvelopeResult =
  | { readonly kind: 'report'; readonly xml: string }
  | { readonly kind: 'error'; readonly code: string; readonly message: string }
  | { readonly kind: 'unknown'; readonly detail: string }
  /** A body that can never become an XML report, whatever we do: CSV output or plain text. */
  | { readonly kind: 'unsupported'; readonly detail: string };

function asRecord(value: unknown): XmlRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as XmlRecord) : null;
}

/** First genuine element name, skipping attributes and stray text nodes. */
function rootKeyOf(record: XmlRecord): string {
  for (const key of Object.keys(record)) {
    if (key.startsWith(ATTRIBUTE_PREFIX) || key === '#text' || key.startsWith('?')) {
      continue;
    }
    return key;
  }
  return '';
}

/** Reads a value from either a child element or an attribute of the same name. */
function readText(record: XmlRecord, key: string): string {
  for (const value of [record[key], record[`${ATTRIBUTE_PREFIX}${key}`]]) {
    if (typeof value === 'string') {
      return value.trim();
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
  }
  return '';
}

/**
 * Parse a numeric field. Handles IBKR's occasional thousands separators without
 * mangling a comma decimal separator.
 */
export function toNumber(raw: unknown, fallback = 0): number {
  if (typeof raw === 'number') {
    return Number.isFinite(raw) ? raw : fallback;
  }
  if (typeof raw !== 'string') {
    return fallback;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return fallback;
  }
  let normalised = trimmed;
  if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(trimmed)) {
    normalised = trimmed.replace(/,/g, '');
  } else if (/^-?\d+,\d{1,2}$/.test(trimmed)) {
    normalised = trimmed.replace(',', '.');
  }
  const parsed = Number(normalised);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toNumberOrNull(raw: unknown): number | null {
  if (typeof raw !== 'string' && typeof raw !== 'number') {
    return null;
  }
  const trimmed = String(raw).trim();
  if (!trimmed) {
    return null;
  }
  const parsed = toNumber(trimmed, Number.NaN);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseTimeOfDay(value: string): { hours: number; minutes: number; seconds: number } {
  const colon = /^(\d{1,2}):(\d{2})(?::(\d{2}))?/.exec(value.trim());
  if (colon) {
    return {
      hours: Number(colon[1] ?? 0),
      minutes: Number(colon[2] ?? 0),
      seconds: Number(colon[3] ?? 0)
    };
  }
  const compact = /^(\d{2})(\d{2})(\d{2})$/.exec(value.trim());
  if (compact) {
    return { hours: Number(compact[1]), minutes: Number(compact[2]), seconds: Number(compact[3]) };
  }
  return { hours: 0, minutes: 0, seconds: 0 };
}

/** Local naive epoch ms for a trade date plus optional time of day. */
export function combineDateTime(dateValue: string, timeValue: string): number {
  const date = parseFlexDate(dateValue);
  if (!date) {
    return Number.NaN;
  }
  const { hours, minutes, seconds } = parseTimeOfDay(timeValue);
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    hours,
    minutes,
    seconds,
    0
  ).getTime();
}

export function isClosingRow(openCloseIndicator: string): boolean {
  const normalised = openCloseIndicator.trim().toUpperCase();
  if (!normalised) {
    return false;
  }
  return normalised === 'C' || normalised.includes('CLOSE') || /(^|[;,\s])C($|[;,\s])/.test(normalised);
}

/**
 * Decide which realized P&L a row contributes.
 *
 * Trade Confirmation rows (`TradeConfirm`) carry `openCloseIndicator`, so the
 * indicator is authoritative: a closing row keeps its `fifoPnlRealized` value
 * even when that value is `0`, because IBKR really did realize zero.
 *
 * Activity rows (`Trade`, type="AF") carry no `openCloseIndicator`, and IBKR
 * writes `fifoPnlRealized="0"` on rows whose cost basis is not closed yet. A `0`
 * there is not a result, so it must never reach the statistics. The rule is:
 * with no indicator, trust `fifoPnlRealized` only when it is non-zero.
 *
 * Currency invariant: the result is always **base currency**.
 * - `fifoPnlRealized` is already base currency, because IBKR reports it in the
 *   account base currency.
 * - The fallback never mixes currencies. It uses the closing leg's
 *   `netCashInBase` (base currency). A trade-currency figure (`netCash`) is used
 *   only when the trade currency equals the base currency. When no base figure
 *   exists the row becomes `{ pnl: null, source: 'none' }`.
 *
 * Returns `{ pnl: null, source: 'none' }` when no realized result is attributable
 * to the row.
 */
export interface RealizedPnlInput {
  readonly fifoPnlRealized: number | null;
  readonly openCloseIndicator: string;
  /** Closing leg's net cash in the account base currency, signed. */
  readonly netCashInBase: number | null;
  /** Closing leg's net cash in the trade currency, signed. */
  readonly netCash: number;
  readonly tradeCurrency: string;
  readonly baseCurrency: string;
  readonly fallbackFromProceeds: boolean;
}

export function deriveRealizedPnl(input: RealizedPnlInput): { pnl: number | null; source: PnlSource } {
  const {
    fifoPnlRealized,
    openCloseIndicator,
    netCashInBase,
    netCash,
    tradeCurrency,
    baseCurrency,
    fallbackFromProceeds
  } = input;
  const hasIndicator = openCloseIndicator.trim().length > 0;
  const closing = isClosingRow(openCloseIndicator);
  if (fifoPnlRealized !== null) {
    if (hasIndicator) {
      return { pnl: fifoPnlRealized, source: 'fifo' };
    }
    // Activity row: a zero means "not closed yet", never a realized result.
    return fifoPnlRealized === 0 ? { pnl: null, source: 'none' } : { pnl: fifoPnlRealized, source: 'fifo' };
  }
  if (!fallbackFromProceeds || !closing) {
    return { pnl: null, source: 'none' };
  }
  // Base-currency figure: safe whatever the trade currency is.
  if (netCashInBase !== null && Number.isFinite(netCashInBase) && netCashInBase !== 0) {
    return { pnl: netCashInBase, source: 'proceeds' };
  }
  // No base figure. Trade-currency arithmetic is legitimate only when the trade
  // currency IS the base currency, so the value stays in the base currency.
  const trade = normaliseCurrencyCode(tradeCurrency);
  const base = normaliseCurrencyCode(baseCurrency);
  if (trade && base && trade === base && Number.isFinite(netCash) && netCash !== 0) {
    return { pnl: netCash, source: 'proceeds' };
  }
  return { pnl: null, source: 'none' };
}

/** `dateTime="20260102;135015"` -> compact date plus HHMMSS time. */
function splitDateTime(value: string): { date: string; time: string } {
  const trimmed = value.trim();
  if (!trimmed) {
    return { date: '', time: '' };
  }
  const separator = trimmed.includes(';') ? ';' : ' ';
  const [date = '', time = ''] = trimmed.split(separator);
  return { date: date.trim(), time: time.trim() };
}

function toTrade(
  row: XmlRecord,
  options: { readonly fallbackFromProceeds: boolean; readonly baseCurrency: string }
): Trade {
  const symbol = readText(row, 'symbol');
  const dateTime = splitDateTime(readText(row, 'dateTime'));
  const tradeDate = readText(row, 'tradeDate') || dateTime.date;
  const tradeTime = readText(row, 'tradeTime') || dateTime.time;
  const openCloseIndicator = readText(row, 'openCloseIndicator');
  const proceeds = toNumber(readText(row, 'proceeds'));
  // Activity rows report the commission as `ibCommission`. Trade Confirmation
  // rows report it as `commission`. Prefer `ibCommission`, fall back to the other.
  const commissionRaw = readText(row, 'ibCommission') || readText(row, 'commission');
  const commission = toNumber(commissionRaw);
  const commissionCost = Math.abs(commission);
  const netCash = toNumber(readText(row, 'netCash'));
  const netCashInBaseRaw = toNumberOrNull(readText(row, 'netCashInBase'));
  const fifoPnlRealized = toNumberOrNull(readText(row, 'fifoPnlRealized'));
  // Optional in a Trade Confirmation query: absent means null, never 0.
  const capitalGainsPnl = toNumberOrNull(readText(row, 'capitalGainsPnl'));
  const fxPnl = toNumberOrNull(readText(row, 'fxPnl'));
  const currency = (readText(row, 'currency') || UNKNOWN_CURRENCY).toUpperCase();
  const { pnl, source } = deriveRealizedPnl({
    fifoPnlRealized,
    openCloseIndicator,
    netCashInBase: netCashInBaseRaw,
    netCash,
    tradeCurrency: currency,
    baseCurrency: options.baseCurrency,
    fallbackFromProceeds: options.fallbackFromProceeds
  });
  const openRaw = readText(row, 'openDateTime') || readText(row, 'openDate');
  const openTimestamp = openRaw ? combineDateTime(openRaw.split(/[ T]/)[0] ?? openRaw, openRaw.split(/[ T]/)[1] ?? '') : null;

  return {
    symbol: symbol || 'UNKNOWN',
    description: readText(row, 'description') || symbol || 'UNKNOWN',
    assetCategory: readText(row, 'assetCategory'),
    tradeDate,
    tradeTime,
    timestamp: dateTime.date
      ? combineDateTime(dateTime.date, dateTime.time || tradeTime)
      : combineDateTime(tradeDate, tradeTime),
    buySell: readText(row, 'buySell'),
    quantity: toNumber(readText(row, 'quantity')),
    tradePrice: toNumber(readText(row, 'tradePrice')),
    proceeds,
    commission,
    commissionCost,
    netCash,
    netCashInBase: netCashInBaseRaw,
    currency,
    exchange: readText(row, 'exchange'),
    orderReference: readText(row, 'orderReference'),
    accountId: readText(row, 'accountId'),
    openCloseIndicator,
    fifoPnlRealized,
    capitalGainsPnl,
    fxPnl,
    realizedPnl: pnl,
    pnlSource: source,
    openTimestamp: openTimestamp !== null && Number.isFinite(openTimestamp) ? openTimestamp : null
  };
}

/**
 * Depth guard for the recursive collector. An Activity report nests rows as
 * `FlexQueryResponse > FlexStatements > FlexStatement > Trades > Trade`, which
 * is depth 4. 64 leaves room for wrapper elements without allowing a hostile
 * document to exhaust the stack.
 */
const MAX_COLLECT_DEPTH = 64;

/**
 * Collect every trade row from every `Trades` and `TradeConfirm` block in the
 * document. An Activity Flex Query emits one `FlexStatement` per day, each with
 * its own `Trades` block, so stopping at the first block loses most rows.
 */
function collectTradeRows(node: unknown, out: XmlRecord[], depth = 0): void {
  if (depth > MAX_COLLECT_DEPTH) {
    return;
  }
  if (Array.isArray(node)) {
    for (const item of node) {
      collectTradeRows(item, out, depth + 1);
    }
    return;
  }
  const record = asRecord(node);
  if (!record) {
    return;
  }
  for (const tag of TRADE_ROW_TAGS) {
    const value = record[tag];
    const items = Array.isArray(value) ? value : [value];
    for (const item of items) {
      const row = asRecord(item);
      if (row) {
        out.push(row);
      }
    }
  }
  for (const [key, value] of Object.entries(record)) {
    if (key.startsWith(ATTRIBUTE_PREFIX) || key === '#text' || key.startsWith('?') || TRADE_ROW_TAGS.includes(key)) {
      continue;
    }
    collectTradeRows(value, out, depth + 1);
  }
}

/**
 * Stable identity of a row, used to drop a row that appears twice. IBKR repeats
 * the same execution when a report aggregates several accounts or when a section
 * is nested twice. `tradeID` identifies one execution; `transactionID` identifies
 * one order and can cover several partial fills, so `tradeID` wins when present.
 * Without either, the full attribute tuple is the identity.
 */
function rowIdentity(record: XmlRecord): string {
  const tradeId = readText(record, 'tradeID');
  if (tradeId) {
    return `tradeID:${tradeId}`;
  }
  const transactionId = readText(record, 'transactionID');
  if (transactionId) {
    return `transactionID:${transactionId}`;
  }
  return Object.keys(record)
    .filter((key) => key.startsWith(ATTRIBUTE_PREFIX))
    .sort()
    .map((key) => `${key}=${String(record[key])}`)
    .join('|');
}

function dedupeRows(rows: readonly XmlRecord[]): XmlRecord[] {
  const seen = new Set<string>();
  const unique: XmlRecord[] = [];
  for (const row of rows) {
    const identity = rowIdentity(row);
    if (seen.has(identity)) {
      continue;
    }
    seen.add(identity);
    unique.push(row);
  }
  return unique;
}

/** Row shape actually present in the document. */
export type FlexRowShape = 'AF' | 'TradeConfirm' | 'unknown';

export interface QueryTypeInfo {
  /** `TradeConfirm` when `<TradeConfirm>` rows are present, `AF` when only `<Trade>` rows are. */
  readonly shape: FlexRowShape;
  /** The root `type` attribute (`type="AF"` for an Activity Flex Query), or '' when absent. */
  readonly declaredType: string;
}

/**
 * Detect the query flavour from the document, without a full XML parse so the
 * answer is available even when parsing later fails. `TradeConfirm` wins because
 * its presence is decisive; otherwise a `<Trade>` row means an Activity query.
 */
export function detectQueryType(xml: string): QueryTypeInfo {
  const body = xml.replace(/^\uFEFF/, '');
  const declared = /<FlexQueryResponse\b[^>]*\btype\s*=\s*"([^"]*)"/.exec(body)?.[1]?.trim() ?? '';
  if (/<TradeConfirm[\s/>]/.test(body)) {
    return { shape: 'TradeConfirm', declaredType: declared };
  }
  if (/<Trade[\s/>]/.test(body)) {
    return { shape: 'AF', declaredType: declared };
  }
  return { shape: 'unknown', declaredType: declared };
}

/**
 * Root elements IBKR has been observed to return for a finished report.
 * `FlexQueryResponse` wraps one or more `FlexStatements`; an Activity query can
 * also arrive as a bare `FlexStatement`.
 */
const REPORT_ROOTS: ReadonlySet<string> = new Set(['FlexQueryResponse', 'FlexStatement']);

/** True when the body is an XML-like document at all. */
function looksLikeXml(body: string): boolean {
  return body.startsWith('<');
}

/**
 * Detect what a GetStatement body is: the finished report, an error envelope,
 * something unparseable that may still succeed later (an HTML gateway page), or
 * a body that can never become a report (CSV or free text).
 *
 * The documented Content-Type is `text/plain;charset=UTF-8` and the payload
 * format follows the Flex Query template, so a CSV template returns CSV here.
 */
export function parseEnvelope(text: string): EnvelopeResult {
  const body = text.replace(/^\uFEFF/, '').trim();
  if (!body) {
    return { kind: 'unknown', detail: 'empty response body' };
  }
  if (!looksLikeXml(body)) {
    return {
      kind: 'unsupported',
      detail:
        'the response is not XML. Set the Flex Query output format to XML in Client Portal ' +
        '(Reporting > Flex Queries); a CSV template cannot be charted'
    };
  }
  let doc: unknown;
  try {
    doc = parser.parse(body);
  } catch (error) {
    return { kind: 'unknown', detail: error instanceof Error ? error.message : String(error) };
  }
  const record = asRecord(doc);
  if (!record) {
    return { kind: 'unknown', detail: 'response is not an XML object' };
  }
  const rootKey = rootKeyOf(record);
  if (rootKey === 'FlexStatementResponse') {
    const envelope = asRecord(record['FlexStatementResponse']);
    if (!envelope) {
      return { kind: 'unknown', detail: 'FlexStatementResponse is not an object' };
    }
    const status = readText(envelope, 'Status');
    const code = readText(envelope, 'ErrorCode');
    const message = readText(envelope, 'ErrorMessage');
    if (status.toLowerCase() === 'success' && !code) {
      return { kind: 'unknown', detail: 'FlexStatementResponse reported success without a statement' };
    }
    return { kind: 'error', code, message };
  }
  if (/^html$/i.test(rootKey)) {
    return { kind: 'unknown', detail: 'an HTML page was returned instead of an XML report (gateway or login page)' };
  }
  if (REPORT_ROOTS.has(rootKey)) {
    return { kind: 'report', xml: body };
  }
  return { kind: 'unknown', detail: `unexpected root element <${rootKey || 'empty'}>` };
}

/** Generic recursive collector for one element name (`ConversionRate`, ...). */
function collectElements(node: unknown, tag: string, out: XmlRecord[], depth = 0): void {
  if (depth > MAX_COLLECT_DEPTH) {
    return;
  }
  if (Array.isArray(node)) {
    for (const item of node) {
      collectElements(item, tag, out, depth + 1);
    }
    return;
  }
  const record = asRecord(node);
  if (!record) {
    return;
  }
  const value = record[tag];
  const items = Array.isArray(value) ? value : [value];
  for (const item of items) {
    const row = asRecord(item);
    if (row) {
      out.push(row);
    }
  }
  for (const [key, child] of Object.entries(record)) {
    if (key.startsWith(ATTRIBUTE_PREFIX) || key === '#text' || key.startsWith('?') || key === tag) {
      continue;
    }
    collectElements(child, tag, out, depth + 1);
  }
}

/** `<ConversionRate reportDate="..." fromCurrency="USD" toCurrency="EUR" rate="0.8655" />` */
function toConversionRate(row: XmlRecord): ConversionRate | null {
  const fromCurrency = normaliseCurrencyCode(readText(row, 'fromCurrency'));
  const toCurrency = normaliseCurrencyCode(readText(row, 'toCurrency'));
  const rate = toNumber(readText(row, 'rate'), Number.NaN);
  if (!fromCurrency || !toCurrency || !Number.isFinite(rate) || rate <= 0) {
    return null;
  }
  return { reportDate: readText(row, 'reportDate'), fromCurrency, toCurrency, rate };
}

/** `<AccountInformation currency="EUR">` with an optional nested `<Account>`. */
function accountInformationCurrency(records: readonly XmlRecord[]): string {
  for (const record of records) {
    const direct = normaliseCurrencyCode(readText(record, 'currency'));
    if (direct) {
      return direct;
    }
    const account = record['Account'];
    const nested = Array.isArray(account) ? account.map(asRecord) : [asRecord(account)];
    for (const item of nested) {
      if (item) {
        const code = normaliseCurrencyCode(readText(item, 'currency'));
        if (code) {
          return code;
        }
      }
    }
  }
  return '';
}

export interface ParseReportResult {
  readonly trades: readonly Trade[];
  readonly baseCurrency: string;
  readonly baseCurrencySource: BaseCurrencySource;
  readonly conversionRates: readonly ConversionRate[];
  readonly warnings: readonly string[];
}

/**
 * Parse a Flex report into trades plus the account currency facts.
 *
 * Base currency precedence:
 * 1. `options.baseCurrencyOverride` (`ibkrHistory.baseCurrency`, not `auto`).
 * 2. `<AccountInformation currency="...">` when the query returns it.
 * 3. The `toCurrency` shared by every `<ConversionRate>` row.
 * 4. `UNKNOWN`.
 *
 * The `currency` attribute of a trade is the TRADE currency. `fifoPnlRealized`,
 * `netCashInBase`, `cost` and the derived `realizedPnl` are base currency.
 */
export function parseReport(xml: string, options: ParseOptions = {}): ParseReportResult {
  const resolved = {
    fallbackFromProceeds: options.fallbackFromProceeds ?? true
  };
  const body = xml.replace(/^\uFEFF/, '').trim();
  if (!body) {
    throw new FlexParseError('empty document');
  }

  let doc: unknown;
  try {
    doc = parser.parse(body);
  } catch (error) {
    throw new FlexParseError(error instanceof Error ? error.message : String(error));
  }

  const envelope = parseEnvelope(body);
  if (envelope.kind === 'error') {
    throw new FlexApiError(envelope.code, envelope.message);
  }

  const collected: XmlRecord[] = [];
  collectTradeRows(doc, collected);
  const rows = dedupeRows(collected);

  const rateRecords: XmlRecord[] = [];
  collectElements(doc, 'ConversionRate', rateRecords);
  const conversionRates: ConversionRate[] = [];
  for (const record of rateRecords) {
    const rate = toConversionRate(record);
    if (rate) {
      conversionRates.push(rate);
    }
  }

  const accountRecords: XmlRecord[] = [];
  collectElements(doc, 'AccountInformation', accountRecords);

  const warnings: string[] = [];
  let detected = accountInformationCurrency(accountRecords);
  let source: BaseCurrencySource = detected ? 'account' : 'unknown';

  if (!detected && conversionRates.length > 0) {
    const counts = new Map<string, number>();
    for (const rate of conversionRates) {
      counts.set(rate.toCurrency, (counts.get(rate.toCurrency) ?? 0) + 1);
    }
    const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const top = ordered[0];
    if (top) {
      detected = top[0];
      source = 'conversionRates';
    }
    if (ordered.length > 1) {
      warnings.push(
        `ConversionRates disagree on toCurrency (${ordered.map(([code, count]) => `${code} x${count}`).join(', ')}). ` +
          `Using ${detected} as the account base currency.`
      );
    }
  }

  const override = normaliseCurrencyCode(options.baseCurrencyOverride);
  const baseCurrency = override || resolveBaseCurrency(detected);
  const baseCurrencySource: BaseCurrencySource = override ? 'override' : source;
  if (baseCurrency === UNKNOWN_CURRENCY) {
    warnings.push(
      'No AccountInformation currency and no ConversionRate rows: the account base currency is unknown. ' +
        'Realized P&L is shown as plain numbers with the suffix "base".'
    );
  }

  const trades: Trade[] = [];
  for (const row of rows) {
    trades.push(toTrade(row, { fallbackFromProceeds: resolved.fallbackFromProceeds, baseCurrency }));
  }

  if (trades.length === 0) {
    throw new FlexEmptyError({
      attempts: options.fetch?.attempts ?? 0,
      elapsedMs: options.fetch?.elapsedMs ?? 0,
      lastStatus: 'report',
      lastErrorCode: '',
      lastBodySnippet: body.slice(0, 500)
    });
  }

  trades.sort((a, b) => {
    const left = Number.isFinite(a.timestamp) ? a.timestamp : Number.MAX_SAFE_INTEGER;
    const right = Number.isFinite(b.timestamp) ? b.timestamp : Number.MAX_SAFE_INTEGER;
    return left - right;
  });

  return {
    trades,
    baseCurrency,
    baseCurrencySource,
    conversionRates,
    warnings
  };
}

/**
 * Trades only, for callers that do not need the currency facts.
 * Delegates to {@link parseReport}, so both entry points share one code path.
 */
export function parseTrades(xml: string, options: ParseOptions = {}): Trade[] {
  return [...parseReport(xml, options).trades];
}

export type SendRequestResult =
  | { readonly kind: 'reference'; readonly referenceCode: string }
  | { readonly kind: 'error'; readonly code: string; readonly message: string }
  | { readonly kind: 'unknown'; readonly detail: string };

/** Interpret the body of a /SendRequest call. */
export function parseSendRequestResponse(text: string): SendRequestResult {
  const body = text.replace(/^\uFEFF/, '').trim();
  if (!body) {
    return { kind: 'unknown', detail: 'empty response body' };
  }
  let doc: unknown;
  try {
    doc = parser.parse(body);
  } catch (error) {
    return { kind: 'unknown', detail: error instanceof Error ? error.message : String(error) };
  }
  const record = asRecord(doc);
  const envelope = record && rootKeyOf(record) === 'FlexStatementResponse' ? asRecord(record['FlexStatementResponse']) : null;
  if (!record || !envelope) {
    return { kind: 'unknown', detail: 'response is not a FlexStatementResponse' };
  }
  const status = readText(envelope, 'Status');
  const referenceCode = readText(envelope, 'ReferenceCode');
  const code = readText(envelope, 'ErrorCode');
  const message = readText(envelope, 'ErrorMessage');
  if (status.toLowerCase() === 'success' && referenceCode) {
    return { kind: 'reference', referenceCode };
  }
  if (code) {
    return { kind: 'error', code, message };
  }
  return { kind: 'unknown', detail: `unexpected envelope (Status="${status}")` };
}
