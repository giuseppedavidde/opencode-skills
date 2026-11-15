import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataset } from '../src/analytics/dataset.ts';
import { filterTradesByRange } from '../src/core/dates.ts';
import type { ConversionRate } from '../src/core/types.ts';
import { parseReport, parseTrades } from '../src/flex/parser.ts';
import { fixture, syntheticTrade, syntheticTrades } from './helpers.ts';

const RANGE = { preset: 'custom' as const, start: '2024-01-01', end: '2024-03-31' };
const START = new Date(2024, 0, 1).getTime();
const END = new Date(2024, 2, 31, 23, 59, 59, 999).getTime();

const USD_TO_EUR: readonly ConversionRate[] = [
  { reportDate: '20240209', fromCurrency: 'USD', toCurrency: 'EUR', rate: 0.9 }
];

test('dataset reports row accounting and the local-filter limitation', () => {
  const all = parseTrades(fixture('trades-sample.xml'));
  const q1 = filterTradesByRange(all, START, END);
  const dataset = buildDataset({
    trades: q1,
    rowsTotal: all.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(2026, 10, 14, 12, 0, 0),
    baseCurrency: 'EUR'
  });

  assert.deepEqual(dataset.currencies, ['EUR']);
  assert.equal(dataset.baseCurrency, 'EUR');
  assert.equal(dataset.meta.baseCurrency, 'EUR');
  assert.equal(dataset.meta.baseCurrencySource, 'conversionRates');
  assert.equal(dataset.meta.rowsTotal, 14);
  assert.equal(dataset.meta.rowsInRange, 12);
  assert.equal(dataset.meta.rowsWithPnl, 6);
  assert.equal(dataset.meta.rowsPnlFromFifo, 6);
  assert.equal(dataset.meta.rowsPnlFromProceeds, 0);
  assert.equal(dataset.meta.range.label, 'Custom range');
  assert.deepEqual(dataset.meta.accounts, ['U0000001']);
  assert.equal(dataset.meta.accountFilter, null);
  assert.ok(dataset.meta.warnings.some((line) => line.includes('no date-range parameter')));
  assert.equal(dataset.meta.warnings.length, 1, 'no spurious warnings for a clean report');
});

test('every trade in range reaches the payload, newest first', () => {
  const trades = syntheticTrades(120);
  const dataset = buildDataset({
    trades,
    rowsTotal: trades.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: 'EUR'
  });
  assert.equal(dataset.trades.length, 120);
  assert.equal(dataset.tradesTruncated, false);
  assert.equal(dataset.tradesCap, 5000);
  assert.equal(dataset.meta.rowsInRange, 120);
  assert.equal(dataset.trades[0]?.date, syntheticTrade(119).tradeDate);
  assert.equal(dataset.trades[0]?.time, syntheticTrade(119).tradeTime);
  assert.equal(dataset.trades[119]?.date, syntheticTrade(0).tradeDate);
  assert.equal(dataset.trades[119]?.time, syntheticTrade(0).tradeTime);
  const stamps = dataset.trades.map((row) => `${row.date} ${row.time}`);
  assert.deepEqual(stamps, [...stamps].sort().reverse(), 'strictly descending by timestamp');
  assert.equal(dataset.trades[0]?.currency, 'EUR', 'each row keeps its trade currency');
});

test('the payload cap keeps the newest rows and reports the real total', () => {
  const trades = syntheticTrades(6000);
  const dataset = buildDataset({
    trades,
    rowsTotal: trades.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: 'EUR'
  });
  assert.equal(dataset.trades.length, 5000);
  assert.equal(dataset.tradesTruncated, true);
  assert.equal(dataset.tradesCap, 5000);
  assert.equal(dataset.meta.rowsInRange, 6000);
  assert.equal(dataset.trades[0]?.date, syntheticTrade(5999).tradeDate);
  assert.equal(dataset.trades[4999]?.date, syntheticTrade(1000).tradeDate, 'the newest 5000 survive');
  assert.ok(dataset.meta.warnings.some((line) => line.includes('maxTradeRows (5000)')), 'the cap is warned, never silent');
});

test('maxTradeRows overrides the payload cap', () => {
  const trades = syntheticTrades(120);
  const dataset = buildDataset({
    trades,
    rowsTotal: trades.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(),
    maxTradeRows: 10,
    baseCurrency: 'EUR'
  });
  assert.equal(dataset.trades.length, 10);
  assert.equal(dataset.tradesTruncated, true);
  assert.equal(dataset.tradesCap, 10);
  assert.equal(dataset.meta.rowsInRange, 120);
  assert.equal(dataset.trades[0]?.date, syntheticTrade(119).tradeDate);
});

test('P&L is one base-currency series; commissions stay per trade currency', () => {
  const all = parseTrades(fixture('trades-sample-multi-currency.xml'));
  const dataset = buildDataset({
    trades: all,
    rowsTotal: all.length,
    range: { preset: 'ytd', start: '2024-01-01', end: '2024-12-31' },
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: 'EUR',
    conversionRates: USD_TO_EUR
  });
  assert.deepEqual(dataset.currencies, ['EUR', 'USD']);
  assert.equal(dataset.baseCurrency, 'EUR');
  assert.equal(dataset.analytics.currency, 'EUR');
  assert.equal(dataset.analytics.stats.totalRealizedPnl, 287, '99 - 51 + 239, a single series');
  assert.equal(dataset.analytics.bySymbol.length, 3);
  assert.deepEqual(
    dataset.commissions.map((row) => [row.currency, row.commissionCost, row.estimatedBase]),
    [
      ['EUR', 1, 1],
      ['USD', 2, 1.8]
    ]
  );
  assert.equal(dataset.commissionEstimateBase, 2.8);
  assert.equal(dataset.commissionEstimateComplete, true);
  assert.ok(dataset.meta.warnings.some((line) => line.includes('2 trade currencies')));
  assert.ok(dataset.meta.warnings.some((line) => line.includes('2 accounts')));
  assert.equal(
    dataset.meta.warnings.some((line) => line.includes('per currency')),
    false,
    'the old per-currency statistics warning is gone'
  );
});

test('an unknown base currency is explicit and never guessed from trade rows', () => {
  const all = parseTrades(fixture('trades-sample-multi-currency.xml'));
  const dataset = buildDataset({
    trades: all,
    rowsTotal: all.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date()
  });
  assert.equal(dataset.baseCurrency, 'UNKNOWN');
  assert.equal(dataset.meta.baseCurrencySource, 'unknown');
  assert.equal(dataset.commissionEstimateBase, null);
  assert.ok(dataset.meta.warnings.some((line) => line.includes('base currency could not be detected')));
});

test('a base-currency override is carried into the dataset', () => {
  const all = parseTrades(fixture('trades-sample.xml'));
  const dataset = buildDataset({
    trades: all,
    rowsTotal: all.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: 'USD',
    baseCurrencySource: 'override'
  });
  assert.equal(dataset.baseCurrency, 'USD');
  assert.equal(dataset.meta.baseCurrency, 'USD');
  assert.equal(dataset.meta.baseCurrencySource, 'override');
  assert.equal(dataset.analytics.currency, 'USD');
});

test('proceeds-approximated rows are surfaced as a warning', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse><FlexStatements><FlexStatement>
<ConversionRates>
  <ConversionRate reportDate="20240322" fromCurrency="USD" toCurrency="EUR" rate="0.92" />
</ConversionRates>
<Trades>
  <TradeConfirm symbol="AMD" currency="USD" tradeDate="2024-03-22" tradeTime="16:30:00" buySell="SELL" quantity="10" tradePrice="110" proceeds="1100" commission="-1" netCash="1099" netCashInBase="1011.08" openCloseIndicator="C" />
</Trades>
</FlexStatement></FlexStatements></FlexQueryResponse>`;
  const report = parseReport(xml);
  const dataset = buildDataset({
    trades: report.trades,
    rowsTotal: report.trades.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: report.baseCurrency,
    baseCurrencySource: report.baseCurrencySource,
    conversionRates: report.conversionRates
  });
  assert.equal(dataset.meta.rowsPnlFromProceeds, 1);
  assert.ok(dataset.meta.warnings.some((line) => line.includes('netCashInBase')));
});

test('empty dataset produces an explicit warning', () => {
  const dataset = buildDataset({
    trades: [],
    rowsTotal: 0,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date()
  });
  assert.deepEqual(dataset.currencies, []);
  assert.equal(dataset.baseCurrency, 'UNKNOWN');
  assert.ok(dataset.meta.warnings.some((line) => line.includes('No trades fall inside')));
});

test('account filter is recorded in meta', () => {
  const all = parseTrades(fixture('trades-sample.xml'));
  const dataset = buildDataset({
    trades: all,
    rowsTotal: all.length,
    range: RANGE,
    accountFilter: 'U0000001',
    generatedAt: new Date(),
    baseCurrency: 'EUR'
  });
  assert.equal(dataset.meta.accountFilter, 'U0000001');
});
