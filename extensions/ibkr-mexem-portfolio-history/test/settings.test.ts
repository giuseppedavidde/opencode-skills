import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_INITIAL_DELAY_MS,
  DEFAULT_MAX_ATTEMPTS,
  DEFAULT_MAX_DELAY_MS,
  DEFAULT_MAX_SEND_ATTEMPTS,
  DEFAULT_DEADLINE_MS
} from '../src/flex/client.ts';
import {
  RETRY_BOUNDS,
  clampNumber,
  resolveBaseCurrencyOverride,
  resolveRequestTimeoutMs,
  resolveRetrySettings
} from '../src/config/settingsCore.ts';
import { resolveBaseCurrency } from '../src/core/currency.ts';

test('retry defaults match the documented production values', () => {
  assert.equal(DEFAULT_DEADLINE_MS, 900_000);
  assert.equal(DEFAULT_MAX_ATTEMPTS, 120);
  assert.equal(DEFAULT_INITIAL_DELAY_MS, 2_000);
  assert.equal(DEFAULT_MAX_DELAY_MS, 20_000);
  assert.equal(DEFAULT_MAX_SEND_ATTEMPTS, 4);
  const resolved = resolveRetrySettings({});
  assert.deepEqual(resolved, {
    maxAttempts: 120,
    maxSendAttempts: 4,
    initialDelayMs: 2_000,
    maxDelayMs: 20_000,
    deadlineMs: 900_000
  });
});

test('read values are clamped to the bounds published in package.json', () => {
  assert.equal(resolveRetrySettings({ maxAttempts: 1 }).maxAttempts, RETRY_BOUNDS.maxAttempts.min);
  assert.equal(resolveRetrySettings({ maxAttempts: 99_999 }).maxAttempts, RETRY_BOUNDS.maxAttempts.max);
  assert.equal(resolveRetrySettings({ maxSendAttempts: 0 }).maxSendAttempts, RETRY_BOUNDS.maxSendAttempts.min);
  assert.equal(resolveRetrySettings({ maxSendAttempts: 99 }).maxSendAttempts, RETRY_BOUNDS.maxSendAttempts.max);
  assert.equal(resolveRetrySettings({ deadlineMs: 1 }).deadlineMs, RETRY_BOUNDS.deadlineMs.min);
  assert.equal(resolveRetrySettings({ deadlineMs: 99_999_999 }).deadlineMs, RETRY_BOUNDS.deadlineMs.max);
  assert.equal(resolveRetrySettings({ initialDelayMs: 10 }).initialDelayMs, 250);
  // Clamped to the 1000 ms floor, then raised to the default initial delay.
  assert.equal(resolveRetrySettings({ maxDelayMs: 10 }).maxDelayMs, DEFAULT_INITIAL_DELAY_MS);
});

test('a user override is honoured and rounded', () => {
  const resolved = resolveRetrySettings({
    maxAttempts: 240,
    maxSendAttempts: 6,
    initialDelayMs: 3_000,
    maxDelayMs: 30_000,
    deadlineMs: 1_800_000
  });
  assert.deepEqual(resolved, {
    maxAttempts: 240,
    maxSendAttempts: 6,
    initialDelayMs: 3_000,
    maxDelayMs: 30_000,
    deadlineMs: 1_800_000
  });
});

test('maxDelayMs never falls below initialDelayMs', () => {
  const resolved = resolveRetrySettings({ initialDelayMs: 50_000, maxDelayMs: 2_000 });
  assert.equal(resolved.initialDelayMs, 50_000);
  assert.equal(resolved.maxDelayMs, 50_000);
});

test('non-numeric and missing values fall back instead of producing NaN', () => {
  assert.equal(clampNumber(Number.NaN, 0, 10, 7), 7);
  assert.equal(clampNumber(undefined, 0, 10, 7), 7);
  assert.equal(resolveRetrySettings({ maxAttempts: Number.POSITIVE_INFINITY }).maxAttempts, 120);
  assert.equal(resolveRetrySettings({ maxSendAttempts: Number.NaN }).maxSendAttempts, 4);
  assert.equal(resolveRequestTimeoutMs(undefined), 30_000);
  assert.equal(resolveRequestTimeoutMs(5), 1_000);
});


test('ibkrHistory.baseCurrency auto keeps detection, a code overrides it', () => {
  assert.equal(resolveBaseCurrencyOverride('auto'), null);
  assert.equal(resolveBaseCurrencyOverride(undefined), null);
  assert.equal(resolveBaseCurrencyOverride(' other '), null);
  assert.equal(resolveBaseCurrencyOverride(' eur '), 'EUR');
  assert.equal(resolveBaseCurrencyOverride('USD'), 'USD');

  assert.equal(resolveBaseCurrency('EUR'), 'EUR');
  assert.equal(resolveBaseCurrency('EUR', 'USD'), 'USD', 'the setting must override detection');
  assert.equal(resolveBaseCurrency('EUR', 'auto'), 'EUR');
  assert.equal(resolveBaseCurrency('', undefined), 'UNKNOWN');
  assert.equal(resolveBaseCurrency('USD', null), 'USD');
});
