import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataset } from '../src/analytics/dataset.ts';
import {
  aggregateBySymbol,
  approximateTokens,
  buildChatContext,
  currencyMapBlock,
  displayPnlOf,
  formatGeneratedAt,
  panelNoticeBlock,
  seriesBlock,
  tradeCsvHeader
} from '../src/chat/context.ts';
import type { DatasetPayload } from '../src/panel/protocol.ts';
import { syntheticTrades } from './helpers.ts';

const RANGE = { preset: 'custom' as const, start: '2024-01-01', end: '2024-12-31' };

function datasetWith(count: number): DatasetPayload {
  const trades = syntheticTrades(count);
  return buildDataset({
    trades,
    rowsTotal: count,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(Date.UTC(2026, 10, 14, 23, 20)),
    baseCurrency: 'EUR',
    maxTradeRows: 5000
  });
}

test('the context carries the statistics, the monthly table and the symbol table', () => {
  const dataset = datasetWith(60);
  const context = buildChatContext(dataset);
  assert.match(context.text, /# Portfolio context/);
  assert.match(context.text, /Base currency: EUR \(source: /);
  assert.match(context.text, /## Statistics \(EUR, full filtered set\)/);
  assert.match(context.text, /Total realized P&L \(EUR, includes the FX result\): EUR /);
  assert.match(context.text, /Profit factor \(gross profit \/ \|gross loss\|\): /);
  assert.match(context.text, /Max drawdown: /);
  assert.match(context.text, /## Monthly realized P&L/);
  assert.match(context.text, /\| Month \| Realized P&L \(EUR\) \| Trades \|/);
  assert.match(context.text, /## Realized P&L by symbol \(top 20 by absolute P&L\)/);
  assert.match(context.text, /\| Symbol \| Realized P&L \(EUR\) \| Trades \|/);
  assert.match(context.text, /## Warnings/);
  assert.match(context.text, /## Currency semantics \(do not mix\)/);
  assert.match(context.text, /## Limitations/);
  assert.match(context.text, /Never invent a price/);
  assert.equal(context.text.includes('You are the Trade analyst'), false, 'the persona is composed by the host, not by the builder');
});

test('the context carries every summary tile the panel shows', () => {
  const context = buildChatContext(datasetWith(60));
  for (const label of [
    'P&L excluding FX',
    'FX result',
    'Trades with realized P&L',
    'Profit factor',
    'Win rate',
    'Wins / losses / break-even',
    'Average win',
    'Average loss',
    'Largest win',
    'Largest loss',
    'Max drawdown',
    'Sharpe-like (daily, annualized)',
    'Trading days',
    'Average holding days',
    'Best symbol',
    'Worst symbol'
  ]) {
    assert.match(context.text, new RegExp(`- ${label.replace(/[()/&.]/g, '\\$&')}`), `missing tile ${label}`);
  }
  assert.match(context.text, /## Chart series \(panel charts, reduced\)/);
  assert.match(context.text, /## Panel notices \(verbatim from the portfolio panel\)/);
});

test('a trade-currency view labels the total as excluding the FX result', () => {
  const dataset = datasetWith(60);
  assert.equal(dataset.displayCurrency, dataset.baseCurrency);
  assert.match(buildChatContext(dataset).text, /Total realized P&L \(EUR, includes the FX result\)/);
  const trade = { ...dataset, displayCurrency: 'USD' };
  assert.match(buildChatContext(trade).text, /Total realized P&L \(USD, trade currency, EXCLUDES the FX result\)/);
});

test('the panel notices name the currencies and the FX effect', () => {
  const dataset = datasetWith(20);
  assert.deepEqual(panelNoticeBlock(dataset), ['- None.']);
  const multi = { ...dataset, currencies: ['EUR', 'USD'], displayCurrency: 'USD', pnlTotals: { ...dataset.pnlTotals, fxTotal: -142.87 } };
  const notices = panelNoticeBlock(multi).join('\n');
  assert.match(notices, /2 trade currencies \(EUR, USD\)/);
  assert.match(notices, /In USD this is the trade-currency result/);
  assert.match(notices, /EUR -142\.87/);
});

test('the series block reports the curve ends and the deepest drawdown', () => {
  const lines = seriesBlock(datasetWith(60)).join('\n');
  assert.match(lines, /Cumulative realized P&L curve: /);
  assert.match(lines, /Deepest drawdown point: /);
});

test('a non-base view names the CSV column after the display currency', () => {
  const dataset = datasetWith(10);
  const trade = { ...dataset, displayCurrency: 'USD' };
  const context = buildChatContext(trade);
  assert.match(context.text, /realized_pnl_usd,pnl_source/);
  assert.equal(context.text.includes('realized_pnl_eur,pnl_source'), false);
  assert.match(context.text, /## Currency of every block/);
});

test('the symbol table sums the display currency, never the base currency', () => {
  const dataset = datasetWith(12);
  const baseRows = dataset.trades.filter((row) => row.displayPnl !== null && row.displayPnl !== undefined);
  const displayTotal = baseRows.reduce((sum, row) => sum + (displayPnlOf(row) ?? 0), 0);
  const aggregates = aggregateBySymbol(dataset.trades);
  const symbolTotal = aggregates.reduce((sum, row) => sum + row.pnl, 0);
  assert.ok(Math.abs(symbolTotal - displayTotal) < 0.01, `symbol total ${symbolTotal} must equal display total ${displayTotal}`);
});

test('the currency map states the currency of each block', () => {
  const dataset = datasetWith(10);
  const lines = currencyMapBlock({ ...dataset, displayCurrency: 'USD', currencies: ['EUR', 'USD'] }).join('\n');
  assert.match(lines, /Statistics, monthly table and symbol table: USD/);
  assert.match(lines, /CSV column realized_pnl_usd: USD/);
  assert.match(lines, /account base currency/);
  assert.match(lines, /Do not label it with the base currency/);
});

test('the CSV is capped and the omitted count is exact', () => {
  const dataset = datasetWith(500);
  assert.equal(dataset.trades.length, 500);
  assert.equal(dataset.tradesTruncated, false);
  const context = buildChatContext(dataset, { maxContextTrades: 400 });
  assert.equal(context.tradeRowsIncluded, 400);
  assert.equal(context.tradeRowsOmitted, 100);
  assert.match(context.text, /## Trades \(newest first: 400 of 500\)/);
  assert.match(context.text, /100 trade row\(s\) are omitted from the CSV/);
  const csvRows = context.text.split('\n').filter((line) => /^\d{4}-\d{2}-\d{2},/.test(line));
  assert.equal(csvRows.length, 400);
});

test('the omitted count covers rows dropped by the payload cap too', () => {
  const trades = syntheticTrades(500);
  const dataset = buildDataset({
    trades,
    rowsTotal: 500,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(Date.UTC(2026, 10, 14, 23, 20)),
    baseCurrency: 'EUR',
    maxTradeRows: 120
  });
  assert.equal(dataset.trades.length, 120);
  assert.equal(dataset.tradesTruncated, true);
  const context = buildChatContext(dataset, { maxContextTrades: 100 });
  assert.equal(context.tradeRowsIncluded, 100);
  assert.equal(context.tradeRowsOmitted, 400);
});

test('the CSV is newest first and uses the documented header', () => {
  const dataset = datasetWith(10);
  const context = buildChatContext(dataset);
  const lines = context.text.split('\n');
  const headerIndex = lines.indexOf(tradeCsvHeader(dataset.displayCurrency));
  assert.equal(tradeCsvHeader('EUR'), 'date,time,symbol,side,qty,price,trade_ccy,realized_pnl_eur,pnl_source');
  assert.equal(tradeCsvHeader('USD'), 'date,time,symbol,side,qty,price,trade_ccy,realized_pnl_usd,pnl_source');
  assert.ok(headerIndex > 0, 'the CSV header must be present');
  const first = lines[headerIndex + 1] ?? '';
  assert.ok(first.startsWith(dataset.trades[0]?.date ?? 'missing'), `first CSV row must be the newest trade: ${first}`);
});

test('the currency note is explicit and never mixes trade currencies', () => {
  const context = buildChatContext(datasetWith(20));
  assert.match(context.text, /realized_pnl_base is the account base currency \(EUR\)/);
  assert.match(context.text, /trade_ccy is the trade currency/);
  assert.match(context.text, /Commission/);
  assert.match(context.text, /Never sum amounts of different trade currencies/);
});

test('the token estimate is non-zero and monotonic in the number of rows', () => {
  const small = buildChatContext(datasetWith(20), { maxContextTrades: 20 });
  const large = buildChatContext(datasetWith(200), { maxContextTrades: 200 });
  assert.ok(small.approxTokens > 0);
  assert.ok(large.approxTokens > small.approxTokens);
  assert.equal(small.approxTokens, approximateTokens(small.text));
  assert.equal(approximateTokens('abcd'), 1);
  assert.equal(approximateTokens(''), 0);
});

test('the context never contains a credential', () => {
  const credential = 'sk-live-0123456789abcdef0123456789';
  const dataset = datasetWith(50);
  const context = buildChatContext(dataset);
  const serialised = JSON.stringify(dataset);
  assert.equal(serialised.includes(credential), false, 'the fixture must not carry the fake key');
  assert.equal(context.text.includes(credential), false);
  assert.equal(/Bearer\s+\S+/.test(context.text), false, 'no bearer header in the context');
  assert.equal(/api[_-]?key/i.test(context.text), false, 'the context names no API key');
});

test('symbol aggregation keeps the base-currency rows and ignores unknown P&L', () => {
  const dataset = datasetWith(30);
  const aggregates = aggregateBySymbol(dataset.trades);
  assert.ok(aggregates.length > 0);
  const total = aggregates.reduce((sum, row) => sum + row.trades, 0);
  assert.equal(total, dataset.trades.filter((row) => row.realizedPnl !== null).length);
});

test('the generated timestamp is rendered without seconds', () => {
  assert.equal(formatGeneratedAt('2026-11-14T23:20:45.123Z'), '2026-11-14 23:20');
  assert.equal(formatGeneratedAt('not-a-date'), 'not-a-date');
});
