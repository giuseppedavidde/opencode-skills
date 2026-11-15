import assert from 'node:assert/strict';
import test from 'node:test';
import { RateTable } from '../src/core/rates.ts';
import type { ConversionRate } from '../src/core/types.ts';

const ROWS: ConversionRate[] = [
  { reportDate: '20260105', fromCurrency: 'USD', toCurrency: 'EUR', rate: 0.9 },
  { reportDate: '20260110', fromCurrency: 'USD', toCurrency: 'EUR', rate: 0.8 },
  { reportDate: '20260110', fromCurrency: 'GBP', toCurrency: 'EUR', rate: 1.2 }
];

const table = new RateTable(ROWS, 'EUR');

test('an exact report date wins', () => {
  assert.equal(table.rate('USD', 'EUR', '20260105'), 0.9);
  assert.equal(table.rate('USD', 'EUR', '20260110'), 0.8);
});

test('a missing date falls back to the nearest earlier report date, never a later one', () => {
  assert.equal(table.rate('USD', 'EUR', '20260107'), 0.9, 'between two rows uses the earlier one');
  assert.equal(table.rate('USD', 'EUR', '20260112'), 0.8);
  assert.equal(table.rate('USD', 'EUR', '20251231'), null, 'no earlier row: undefined, not a guess');
});

test('the inverse direction answers 1/rate with the same date rule', () => {
  assert.ok(Math.abs((table.rate('EUR', 'USD', '20260110') ?? 0) - 1 / 0.8) < 1e-12);
  assert.equal(table.rate('EUR', 'GBP', '20260110'), 1 / 1.2);
});

test('the same currency is exactly 1', () => {
  assert.equal(table.rate('EUR', 'EUR', '20260110'), 1);
});

test('a missing pair is undefined, never a cross rate through a third currency', () => {
  assert.equal(table.rate('GBP', 'USD', '20260110'), null);
  assert.equal(table.has('GBP', 'USD'), false);
  assert.equal(table.has('USD', 'EUR'), true);
  assert.equal(table.has('EUR', 'USD'), true, 'an inverse pair counts as present');
});

test('an empty table answers undefined for every pair', () => {
  const empty = new RateTable([], 'EUR');
  assert.equal(empty.rate('USD', 'EUR', '20260110'), null);
  assert.equal(empty.has('USD', 'EUR'), false);
  assert.equal(empty.rate('EUR', 'EUR', '20260110'), 1);
});

test('invalid rows are ignored instead of poisoning the table', () => {
  const weird = new RateTable(
    [
      { reportDate: 'not-a-date', fromCurrency: 'USD', toCurrency: 'EUR', rate: 0.9 },
      { reportDate: '20260110', fromCurrency: 'USD', toCurrency: 'EUR', rate: 0 },
      { reportDate: '20260110', fromCurrency: 'usd', toCurrency: 'eur', rate: 0.85 }
    ],
    'EUR'
  );
  assert.equal(weird.rate('USD', 'EUR', '20260110'), 0.85);
});
