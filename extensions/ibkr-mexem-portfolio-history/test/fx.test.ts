import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDataset, computePnlTotals } from '../src/analytics/dataset.ts';
import { buildChatContext } from '../src/chat/context.ts';
import { pnlInCurrency } from '../src/core/pnl.ts';
import { RateTable } from '../src/core/rates.ts';
import type { Trade } from '../src/core/types.ts';
import { csvColumns, tradesToCsv } from '../src/export/csv.ts';
import { parseReport } from '../src/flex/parser.ts';
import type { DatasetPayload } from '../src/panel/protocol.ts';
import { fixture } from './helpers.ts';

const REPORT = parseReport(fixture('trades-fx-sample.xml'));
const RATES = new RateTable(REPORT.conversionRates, REPORT.baseCurrency);
const RANGE = { preset: 'custom' as const, start: '2026-01-01', end: '2026-12-31' };

/** Rate of the LHX closing leg, copied from the report `<ConversionRate>` row. */
const LHX_RATE = 0.87554;
const LHX_FIFO = 2881.630354;
const LHX_CAPITAL_GAINS = 2936.168699;

function mustFind(predicate: (trade: Trade) => boolean): Trade {
  const trade = REPORT.trades.find(predicate);
  if (!trade) {
    throw new Error('fixture row missing');
  }
  return trade;
}

const LHX = mustFind((trade) => trade.symbol.startsWith('LHX'));

function build(displayCurrency?: string, trades: readonly Trade[] = REPORT.trades): DatasetPayload {
  return buildDataset({
    trades,
    rowsTotal: trades.length,
    range: RANGE,
    accountFilter: '',
    generatedAt: new Date(Date.UTC(2026, 11, 12, 12, 0)),
    baseCurrency: REPORT.baseCurrency,
    baseCurrencySource: REPORT.baseCurrencySource,
    conversionRates: REPORT.conversionRates,
    displayCurrency
  });
}

test('the parser keeps capitalGainsPnl and fxPnl, and null when absent', () => {
  assert.equal(LHX.capitalGainsPnl, LHX_CAPITAL_GAINS);
  assert.equal(LHX.fxPnl, -54.538345);
  assert.equal(LHX.fifoPnlRealized, LHX_FIFO);
  const withoutFields = parseReport(`<?xml version="1.0"?>
<FlexQueryResponse><FlexStatements><FlexStatement>
<ConversionRates><ConversionRate reportDate="20260110" fromCurrency="USD" toCurrency="EUR" rate="0.9" /></ConversionRates>
<Trades><TradeConfirm symbol="AMD" currency="USD" tradeDate="2026-01-10" buySell="SELL" quantity="1" tradePrice="10" netCash="9.3" openCloseIndicator="C" fifoPnlRealized="1.5" /></Trades>
</FlexStatement></FlexStatements></FlexQueryResponse>`);
  assert.equal(withoutFields.trades.length, 1);
  assert.equal(withoutFields.trades[0]?.capitalGainsPnl, null);
  assert.equal(withoutFields.trades[0]?.fxPnl, null);
});

test('the base view returns fifoPnlRealized unchanged and includes the FX result', () => {
  const view = pnlInCurrency(LHX, 'EUR', RATES);
  assert.equal(view.value, LHX_FIFO);
  assert.equal(view.basis, 'base');
  assert.equal(view.exact, true);
});

test('the trade-currency view returns capitalGainsPnl / rate, 3353.5517 USD', () => {
  const view = pnlInCurrency(LHX, 'USD', RATES);
  assert.equal(view.basis, 'no-fx');
  assert.equal(view.exact, true);
  assert.ok(view.value !== null);
  assert.ok(Math.abs(view.value - 3353.5517) < 0.001, `expected 3353.5517 USD, got ${view.value}`);
  // The wrong rule: fifoPnlRealized / rate reintroduces the FX result.
  assert.ok(Math.abs(view.value - LHX_FIFO / LHX_RATE) > 1, 'fifoPnlRealized / rate must not be the answer');
});

test('a row without capitalGainsPnl falls back to the base figure and is marked inexact', () => {
  const view = pnlInCurrency({ ...LHX, capitalGainsPnl: null }, 'USD', RATES);
  assert.equal(view.basis, 'no-fx');
  assert.equal(view.exact, false);
  assert.ok(view.value !== null);
  assert.ok(Math.abs(view.value - LHX_FIFO / LHX_RATE) < 0.001);
  assert.match(view.reason ?? '', /capitalGainsPnl is absent/);
});

test('an unknown rate returns null instead of a guessed value', () => {
  const early = pnlInCurrency({ ...LHX, tradeDate: '2020-01-01' }, 'USD', RATES);
  assert.equal(early.value, null);
  assert.equal(early.basis, 'no-fx');

  const thirdCurrency = pnlInCurrency({ ...LHX, currency: 'GBP' }, 'GBP', RATES);
  assert.equal(thirdCurrency.value, null);
});

test('a row with no realized P&L stays null in every currency', () => {
  const open: Trade = { ...LHX, realizedPnl: null };
  assert.equal(pnlInCurrency(open, 'EUR', RATES).value, null);
  assert.equal(pnlInCurrency(open, 'USD', RATES).value, null);
});

test('the three aggregates reproduce the report and the identity holds', () => {
  const totals = computePnlTotals(REPORT.trades);
  assert.ok(Math.abs(totals.baseTotal - 4585.0542) < 0.001, `base ${totals.baseTotal}`);
  assert.ok(totals.capitalGainsTotal !== null);
  assert.ok(Math.abs(totals.capitalGainsTotal - 4727.9276) < 0.001, `capital gains ${totals.capitalGainsTotal}`);
  assert.ok(totals.fxTotal !== null);
  assert.ok(Math.abs(totals.fxTotal - -142.8734) < 0.001, `fx ${totals.fxTotal}`);
  assert.equal(totals.identityHolds, true);
  assert.ok(Math.abs(totals.baseTotal - (totals.capitalGainsTotal + totals.fxTotal)) < 0.001);
  assert.equal(totals.rowsWithCapitalGains, 3);
  assert.equal(totals.rowsWithFx, 3);
});

test('the dataset offers the base currency first, then the trade currency', () => {
  const dataset = build();
  assert.deepEqual(dataset.displayCurrencies, ['EUR', 'USD']);
  assert.equal(dataset.displayCurrency, 'EUR');
  assert.equal(dataset.conversionRates.length, 2);
  assert.equal(dataset.trades[0]?.displayPnl, dataset.trades[0]?.realizedPnl);
});

test('the same trades in base and in USD produce different gross profit', () => {
  const base = build();
  const usd = build('USD');
  assert.equal(usd.displayCurrency, 'USD');
  assert.equal(usd.analytics.currency, 'USD');
  assert.ok(Math.abs(base.analytics.stats.grossProfit - 4585.0542) < 0.01, 'stats round to cents');
  // Every row of the fixture is a USD win, so the USD gross profit is the sum of
  // capitalGainsPnl converted at each trade date. It is not the base figure
  // divided by one rate: the FX result is excluded and the rate is per row.
  const expected =
    LHX_CAPITAL_GAINS / LHX_RATE + (1167.429371 + 624.32953) / 0.87228;
  assert.ok(Math.abs(usd.analytics.stats.grossProfit - expected) < 0.01, `usd gross ${usd.analytics.stats.grossProfit}`);
  assert.ok(usd.analytics.stats.grossProfit !== base.analytics.stats.grossProfit);
  assert.ok(usd.analytics.stats.grossProfit > base.analytics.stats.grossProfit, 'EUR 1 buys more than USD 1');
  assert.equal(usd.pnlTotals.baseTotal, base.pnlTotals.baseTotal, 'the FX block stays in the base currency');
  assert.equal(usd.analytics.stats.averageHoldingDays, base.analytics.stats.averageHoldingDays);
});

test('an unconvertible row is excluded from the stats and counted in the warning', () => {
  const early: Trade = { ...LHX, symbol: 'EARLY', tradeDate: '2020-01-01' };
  const trades = [...REPORT.trades, early];
  const usd = build('USD', trades);
  const base = build(undefined, trades);
  assert.ok(
    usd.meta.warnings.some((line) => line.startsWith('1 trade(s) could not be converted to USD')),
    usd.meta.warnings.join('\n')
  );
  const unconverted = usd.trades.filter((row) => row.displayPnl === null && row.realizedPnl !== null);
  assert.equal(unconverted.length, 1);
  assert.equal(usd.analytics.stats.grossProfit, build('USD').analytics.stats.grossProfit, 'the row adds nothing');
  assert.ok(Math.abs(base.analytics.stats.grossProfit - (4585.0542 + LHX_FIFO)) < 0.01);
});

test('the CSV carries both P&L columns with their currency codes', () => {
  const columns = csvColumns({ displayCurrency: 'USD', rateTable: RATES });
  assert.equal(columns.includes('realizedPnl'), true, 'the base column is still there');
  assert.equal(columns.includes('realized_pnl_USD'), true);
  assert.equal(columns.at(-1), 'realized_pnl_USD');

  const csv = tradesToCsv(REPORT.trades, { displayCurrency: 'USD', rateTable: RATES });
  const [header, first] = csv.split('\r\n');
  assert.equal(header, columns.join(','));
  const cells = (first ?? '').split(',');
  const baseIndex = columns.indexOf('realizedPnl');
  const usdIndex = columns.indexOf('realized_pnl_USD');
  assert.equal(Number(cells[baseIndex]), LHX_FIFO);
  assert.ok(Math.abs(Number(cells[usdIndex]) - 3353.5517) < 0.001);

  // No options: the header stays exactly the historical column list.
  assert.equal(tradesToCsv(REPORT.trades).split('\r\n')[0], csvColumns().join(','));
});

test('the CSV keeps the base column and the display column in both views', () => {
  const base = REPORT.baseCurrency;
  const inBase = csvColumns({ displayCurrency: base, rateTable: RATES });
  assert.equal(inBase.includes('realizedPnl'), true, 'the base column is always written');
  assert.equal(inBase.includes(`realized_pnl_${base}`), true, 'the base view still names its currency');

  const inUsd = csvColumns({ displayCurrency: 'USD', rateTable: RATES });
  assert.equal(inUsd.includes('realizedPnl'), true, 'the base column survives the USD view');
  assert.equal(inUsd.includes('realized_pnl_USD'), true, `the USD view is labelled USD, not ${base}`);
  assert.equal(inUsd.includes(`realized_pnl_${base}`), false);

  const [header, first] = tradesToCsv(REPORT.trades, { displayCurrency: base, rateTable: RATES }).split('\r\n');
  assert.equal(header, inBase.join(','));
  const cells = (first ?? '').split(',');
  assert.equal(Number(cells[inBase.indexOf('realizedPnl')]), Number(cells[inBase.indexOf(`realized_pnl_${base}`)]));
});

test('the chat context states both totals and the derivation rule', () => {
  const context = buildChatContext(build('USD')).text;
  assert.match(context, /## P&L currency: base vs trade currency \(the FX effect\)/);
  assert.match(context, /INCLUDING the FX result: EUR 4585\.05/);
  assert.match(context, /EXCLUDING the FX result: EUR 4727\.93/);
  assert.match(context, /Sum of fxPnl: EUR -142\.87/);
  assert.match(context, /capitalGainsPnl \/ rate\(tradeCcy -> base, tradeDate\)/);
  assert.match(context, /NOT a unit conversion of each other/);
  assert.match(context, /Displayed P&L currency of this context: USD/);
});
