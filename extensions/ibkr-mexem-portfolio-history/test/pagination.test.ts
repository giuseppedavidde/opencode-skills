import assert from 'node:assert/strict';
import test from 'node:test';
import type { TradeRow } from '../src/panel/protocol.ts';
import {
  DEFAULT_TRADE_PAGE_SIZE,
  filterTrades,
  paginate,
  parsePageSize,
  sortTrades
} from '../src/panel/webview/pagination.ts';

function row(index: number, overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    date: `2024-01-${String((index % 28) + 1).padStart(2, '0')}`,
    time: `${String(index % 24).padStart(2, '0')}:00:00`,
    symbol: index % 2 === 0 ? 'AAPL' : 'MSFT',
    buySell: index % 3 === 0 ? 'SELL' : 'BUY',
    quantity: index,
    price: 100 + index,
    currency: 'EUR',
    realizedPnl: index % 5 === 0 ? null : index - 10,
    pnlSource: index % 5 === 0 ? 'none' : 'fifo',
    ...overrides
  };
}

const ROWS = Array.from({ length: 412 }, (_unused, index) => row(index));

test('first page returns one page worth of rows', () => {
  const page = paginate(ROWS, 1, 100);
  assert.equal(page.rows.length, 100);
  assert.equal(page.page, 1);
  assert.equal(page.pageCount, 5);
  assert.equal(page.total, 412);
  assert.equal(page.startIndex, 0);
  assert.equal(page.endIndex, 100);
  assert.equal(page.rows[0], ROWS[0]);
});

test('last page is partial', () => {
  const page = paginate(ROWS, 5, 100);
  assert.equal(page.rows.length, 12);
  assert.equal(page.page, 5);
  assert.equal(page.startIndex, 400);
  assert.equal(page.endIndex, 412);
  assert.equal(page.rows[11], ROWS[411]);
});

test('a page beyond the end clamps to the last page', () => {
  const page = paginate(ROWS, 99, 100);
  assert.equal(page.page, 5);
  assert.equal(page.rows.length, 12);
  assert.equal(page.startIndex, 400);
});

test('a page below one clamps to the first page', () => {
  const page = paginate(ROWS, 0, 100);
  assert.equal(page.page, 1);
  assert.equal(page.startIndex, 0);
});

test('pageSize all returns every row as page one', () => {
  const page = paginate(ROWS, 3, 'all');
  assert.equal(page.rows.length, 412);
  assert.equal(page.page, 1);
  assert.equal(page.pageCount, 1);
  assert.equal(page.startIndex, 0);
  assert.equal(page.endIndex, 412);
});

test('exact boundaries and empty sets', () => {
  const fifty = paginate(ROWS.slice(0, 50), 1, 50);
  assert.equal(fifty.rows.length, 50);
  assert.equal(fifty.pageCount, 1);
  const empty = paginate([], 4, 250);
  assert.equal(empty.rows.length, 0);
  assert.equal(empty.page, 1);
  assert.equal(empty.pageCount, 1);
  assert.equal(empty.total, 0);
  assert.equal(empty.startIndex, 0);
  assert.equal(empty.endIndex, 0);
});

test('parsePageSize accepts the offered values only', () => {
  assert.equal(parsePageSize('50'), 50);
  assert.equal(parsePageSize('100'), 100);
  assert.equal(parsePageSize('250'), 250);
  assert.equal(parsePageSize('all'), 'all');
  assert.equal(parsePageSize('999'), DEFAULT_TRADE_PAGE_SIZE);
  assert.equal(parsePageSize(''), DEFAULT_TRADE_PAGE_SIZE);
});

test('the filter matches symbol, side and source, case-insensitively', () => {
  assert.equal(filterTrades(ROWS, '').length, 412);
  assert.equal(filterTrades(ROWS, '  ').length, 412);
  assert.equal(filterTrades(ROWS, 'aapl').length, 206);
  assert.equal(filterTrades(ROWS, 'sell').length, 138);
  assert.equal(filterTrades(ROWS, 'NONE').length, 83);
  assert.equal(filterTrades(ROWS, 'nothing').length, 0);
  assert.notEqual(filterTrades(ROWS, ''), ROWS, 'the filter returns a copy');
});

test('sorting by date defaults to descending when asked, and is stable', () => {
  const sample = [row(2), row(0), row(1)];
  const descending = sortTrades(sample, 'date', 'desc');
  assert.deepEqual(
    descending.map((entry) => entry.quantity),
    [2, 1, 0]
  );
  const ascending = sortTrades(sample, 'date', 'asc');
  assert.deepEqual(
    ascending.map((entry) => entry.quantity),
    [0, 1, 2]
  );
  assert.deepEqual(
    sample.map((entry) => entry.quantity),
    [2, 0, 1],
    'the input is never mutated'
  );
});

test('sorting by symbol, quantity and price toggles direction', () => {
  const sample = [row(1), row(4), row(2)];
  assert.deepEqual(sortTrades(sample, 'symbol', 'asc').map((entry) => entry.symbol), ['AAPL', 'AAPL', 'MSFT']);
  assert.deepEqual(sortTrades(sample, 'quantity', 'desc').map((entry) => entry.quantity), [4, 2, 1]);
  assert.deepEqual(sortTrades(sample, 'price', 'asc').map((entry) => entry.price), [101, 102, 104]);
});

test('rows without realized P&L stay last in both directions', () => {
  const sample = [row(0), row(1), row(2)];
  assert.deepEqual(sortTrades(sample, 'pnl', 'asc').map((entry) => entry.quantity), [1, 2, 0]);
  assert.deepEqual(sortTrades(sample, 'pnl', 'desc').map((entry) => entry.quantity), [2, 1, 0]);
});
