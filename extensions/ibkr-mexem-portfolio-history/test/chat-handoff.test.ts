import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataset } from '../src/analytics/dataset.ts';
import { buildHandoffQuery, HANDOFF_MAX_QUERY_LENGTH, handoffHeader, handoffStamp } from '../src/chat/handoff.ts';
import { syntheticTrades } from './helpers.ts';

const RANGE = { preset: 'custom' as const, start: '2024-01-01', end: '2024-12-31' };

test('the handoff stamp is a UTC stamp that is safe in a file name', () => {
  assert.equal(handoffStamp(new Date('2026-11-15T14:40:43.967Z')), '20261115T144043Z');
});

test('the handoff header names the file, the time and the dataset range', () => {
  const dataset = buildDataset({
    trades: syntheticTrades(3),
    rowsTotal: 3,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(Date.UTC(2026, 10, 15, 14, 40)),
    baseCurrency: 'EUR'
  });
  const header = handoffHeader(dataset, '2026-11-15T14:40:43.967Z');
  const text = header.join('\n');
  assert.match(text, /^# IBKR portfolio handoff/);
  assert.match(text, /plus the live option data of the local trading CLI/);
  assert.match(text, /Generated at 2026-11-15T14:40:43\.967Z \(UTC\)/);
  assert.match(text, /Range: 2024-01-01 to 2024-12-31/);
  assert.match(text, /Base currency: EUR/);
});

test('the chat query stays under 400 characters and names the absolute path', () => {
  const handoff = '/home/giuseppe/.config/Code/User/globalStorage/giuseppe.ibkr-mexem-portfolio-history/handoff/portfolio-20261115T144043Z.md';
  const query = buildHandoffQuery(handoff);
  assert.ok(query.length < HANDOFF_MAX_QUERY_LENGTH, `the query is ${query.length} characters`);
  assert.ok(query.startsWith('@trade '));
  assert.ok(query.includes(handoff), 'the absolute path is never truncated');

  const longPath = `/home/giuseppe/.config/Code/User/globalStorage/giuseppe.ibkr-mexem-portfolio-history/handoff/${'x'.repeat(360)}.md`;
  const longQuery = buildHandoffQuery(longPath);
  assert.ok(longQuery.includes(longPath), 'even a long path is kept whole');
  assert.ok(longQuery.startsWith('@trade '));
});
