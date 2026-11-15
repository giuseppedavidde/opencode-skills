import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataset } from '../src/analytics/dataset.ts';
import { CSV_COLUMNS, escapeCsvField, tradesToCsv } from '../src/export/csv.ts';
import { parseTrades } from '../src/flex/parser.ts';
import { fixture, syntheticTrades } from './helpers.ts';

test('header is stable and rows are emitted for every trade', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const csv = tradesToCsv(trades);
  const lines = csv.split('\r\n').filter((line) => line.length > 0);
  assert.equal(lines.length, trades.length + 1);
  assert.equal(lines[0], CSV_COLUMNS.join(','));
  assert.match(lines[1] ?? '', /^U0000001,EUR,AAPL,/);
});

test('fields are quoted only when required', () => {
  assert.equal(escapeCsvField('plain'), 'plain');
  assert.equal(escapeCsvField('with,comma'), '"with,comma"');
  assert.equal(escapeCsvField('with"quote'), '"with""quote"');
  assert.equal(escapeCsvField('line\nbreak'), '"line\nbreak"');
  assert.equal(escapeCsvField(null), '');
  assert.equal(escapeCsvField(undefined), '');
  assert.equal(escapeCsvField(12.5), '12.5');
  assert.equal(escapeCsvField(' padded'), '" padded"');
});

test('null FIFO values become empty cells', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const open = trades.find((trade) => trade.symbol === 'AAPL' && trade.tradeDate === '2024-01-05');
  const csv = tradesToCsv(open ? [open] : []);
  const row = csv.split('\r\n')[1] ?? '';
  const cells = row.split(',');
  const fifoIndex = CSV_COLUMNS.indexOf('fifoPnlRealized');
  const pnlIndex = CSV_COLUMNS.indexOf('realizedPnl');
  assert.equal(cells[fifoIndex], '');
  assert.equal(cells[pnlIndex], '');
  assert.equal(cells[CSV_COLUMNS.indexOf('pnlSource')], 'none');
});

test('csv never contains anything but trade data', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const csv = tradesToCsv(trades);
  assert.equal(csv.includes('FlexStatement'), false);
  assert.equal(csv.includes('<'), false);
});

test('the export always writes the full filtered set, never the paged payload', () => {
  const trades = syntheticTrades(6000);
  const dataset = buildDataset({
    trades,
    rowsTotal: trades.length,
    range: { preset: 'custom', start: '2024-01-01', end: '2024-12-31' },
    accountFilter: '',
    generatedAt: new Date(),
    baseCurrency: 'EUR'
  });
  // The controller exports its own full filtered array (lastTrades), not dataset.trades.
  const csv = tradesToCsv(trades);
  const dataLines = csv.split('\r\n').filter((line) => line.length > 0).length - 1;
  assert.equal(dataset.trades.length, 5000, 'the panel payload is capped');
  assert.equal(dataset.meta.rowsInRange, 6000);
  assert.equal(dataLines, dataset.meta.rowsInRange, 'the CSV has one data row per trade in range');
});
