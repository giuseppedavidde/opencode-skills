import assert from 'node:assert/strict';
import test from 'node:test';
import { isKnownCurrency } from '../src/core/currency.ts';
import { formatBaseAmount } from '../src/core/format.ts';
import { resolvePnlColumn } from '../src/panel/webview/pnlColumn.ts';

function resolve(baseCurrency: string, displayCurrency: string) {
  return resolvePnlColumn({ baseCurrency, displayCurrency, isKnownCurrency });
}

test('base EUR with display EUR resolves to the base view', () => {
  const column = resolve('EUR', 'EUR');
  assert.equal(column.currency, 'EUR');
  assert.equal(column.isBaseView, true);
  assert.equal(column.known, true);
  assert.match(column.header, /EUR base, including FX/);
  assert.equal(column.header, 'Realized P&L (EUR base, including FX)');
  assert.equal(column.badge, 'P&L in EUR · account base currency');
});

test('base EUR with display USD resolves to the trade-currency view', () => {
  const column = resolve('EUR', 'USD');
  assert.equal(column.currency, 'USD');
  assert.equal(column.isBaseView, false);
  assert.equal(column.known, true);
  assert.equal(column.header, 'Realized P&L (USD, excluding FX)');
  assert.equal(column.badge, 'P&L in USD · trade currency, excluding FX');
});

test('an unknown display code falls back to the base currency and the (base) header', () => {
  for (const requested of ['UNKNOWN', '', 'eu']) {
    const column = resolve('EUR', requested);
    assert.equal(column.currency, 'EUR', `display ${JSON.stringify(requested)}`);
    assert.equal(column.known, false, `display ${JSON.stringify(requested)}`);
    assert.equal(column.isBaseView, true, `display ${JSON.stringify(requested)}`);
    assert.equal(column.header, 'Realized P&L (base)');
    assert.equal(column.badge, 'P&L currency unknown');
  }
});

test('an unknown base currency still resolves without a symbol', () => {
  const column = resolve('UNKNOWN', 'UNKNOWN');
  assert.equal(column.currency, 'UNKNOWN');
  assert.equal(column.known, false);
  assert.equal(column.isBaseView, true);
  assert.equal(column.header, 'Realized P&L (base)');
  assert.equal(formatBaseAmount(1234.5, column.currency), '1234.50 base');
});

test('table cells and header cannot disagree on currency', () => {
  const column = resolve('EUR', 'USD');
  // The table formats every cell with `column.currency`, exactly like the header.
  assert.equal(column.header.includes(column.currency), true, 'header names the cell currency');
  assert.equal(column.badge.includes(column.currency), true, 'badge names the cell currency');
  assert.equal(formatBaseAmount(1046.6, column.currency), '$1,046.60', 'cells use the header currency');

  // Regression guard for 0.7.0: the base code must never reach a USD view.
  assert.notEqual(column.currency, 'EUR');
  assert.equal(column.header.includes('EUR'), false);
  assert.equal(column.badge.includes('EUR'), false);
  assert.notEqual(formatBaseAmount(1046.6, column.currency), formatBaseAmount(1046.6, 'EUR'));
});
