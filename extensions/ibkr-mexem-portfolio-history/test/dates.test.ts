import assert from 'node:assert/strict';
import test from 'node:test';
import {
  filterTradesByAccount,
  filterTradesByRange,
  parseFlexDate,
  parseIsoDate,
  rangeToMs,
  resolveRange
} from '../src/core/dates.ts';

const NOW = new Date(2024, 2, 15, 12, 0, 0, 0);

test('year to date starts on January 1st', () => {
  const result = resolveRange('ytd', '', '', NOW);
  assert.deepEqual(result, { ok: true, range: { preset: 'ytd', start: '2024-01-01', end: '2024-03-15' } });
});

test('rolling presets are inclusive and end today', () => {
  const last30 = resolveRange('last30', '', '', NOW);
  assert.ok(last30.ok);
  assert.equal(last30.range.start, '2024-02-15');
  assert.equal(last30.range.end, '2024-03-15');

  const last90 = resolveRange('last90', '', '', NOW);
  assert.ok(last90.ok);
  assert.equal(last90.range.start, '2023-12-17');

  const last365 = resolveRange('last365', '', '', NOW);
  assert.ok(last365.ok);
  assert.equal(last365.range.start, '2023-03-17');
});

test('custom range validation', () => {
  assert.deepEqual(resolveRange('custom', '2024-01-01', '2024-01-31', NOW), {
    ok: true,
    range: { preset: 'custom', start: '2024-01-01', end: '2024-01-31' }
  });
  assert.equal(resolveRange('custom', '2024-02-01', '2024-01-01', NOW).ok, false);
  assert.equal(resolveRange('custom', '2024-13-01', '2024-01-31', NOW).ok, false);
  assert.equal(resolveRange('custom', '', '', NOW).ok, false);
});

test('strict ISO parsing rejects impossible dates', () => {
  assert.equal(parseIsoDate('2024-02-29')?.getDate(), 29);
  assert.equal(parseIsoDate('2023-02-29'), null);
  assert.equal(parseIsoDate('2024-02-31'), null);
  assert.equal(parseIsoDate('2024-1-1'), null);
  assert.equal(parseIsoDate('garbage'), null);
});

test('flex dates accept both layouts', () => {
  assert.equal(parseFlexDate('2024-01-31')?.getMonth(), 0);
  assert.equal(parseFlexDate('20240131')?.getDate(), 31);
});

test('range window is inclusive to the last millisecond of the end day', () => {
  const { startMs, endMs } = rangeToMs({ start: '2024-01-01', end: '2024-01-31' });
  assert.equal(startMs, new Date(2024, 0, 1, 0, 0, 0, 0).getTime());
  assert.equal(endMs, new Date(2024, 0, 31, 23, 59, 59, 999).getTime());
});

test('filtering keeps both boundaries and drops adjacent days', () => {
  const rows = [
    { timestamp: new Date(2023, 11, 31, 23, 59, 59, 999).getTime(), id: 'before' },
    { timestamp: new Date(2024, 0, 1, 0, 0, 0, 0).getTime(), id: 'first' },
    { timestamp: new Date(2024, 0, 31, 23, 59, 59, 999).getTime(), id: 'last' },
    { timestamp: new Date(2024, 1, 1, 0, 0, 0, 0).getTime(), id: 'after' },
    { timestamp: Number.NaN, id: 'invalid' }
  ];
  const { startMs, endMs } = rangeToMs({ start: '2024-01-01', end: '2024-01-31' });
  assert.deepEqual(
    filterTradesByRange(rows, startMs, endMs).map((row) => row.id),
    ['first', 'last']
  );
});

test('account filter is optional and case-insensitive', () => {
  const rows = [
    { accountId: 'U0000001' },
    { accountId: 'u0000002' },
    { accountId: '' }
  ];
  assert.equal(filterTradesByAccount(rows, '').length, 3);
  assert.deepEqual(
    filterTradesByAccount(rows, 'u0000002').map((row) => row.accountId),
    ['u0000002']
  );
});
