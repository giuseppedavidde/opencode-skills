import assert from 'node:assert/strict';
import test from 'node:test';
import { filterTradesByRange } from '../src/core/dates.ts';
import type { Trade } from '../src/core/types.ts';
import {
  averageHoldingDays,
  buildCurve,
  computeAnalytics,
  computeStats,
  drawdownSeries,
  groupByCurrency,
  histogram,
  monthlyPnl,
  sharpeLike,
  symbolPnl
} from '../src/analytics/metrics.ts';
import { parseTrades } from '../src/flex/parser.ts';
import { fixture } from './helpers.ts';

const ALL = parseTrades(fixture('trades-sample.xml'));
const Q1 = filterTradesByRange(
  ALL,
  new Date(2024, 0, 1, 0, 0, 0, 0).getTime(),
  new Date(2024, 2, 31, 23, 59, 59, 999).getTime()
);

const BASE_TRADE: Trade = {
  symbol: 'X',
  description: 'X',
  assetCategory: 'STK',
  tradeDate: '2024-01-01',
  tradeTime: '00:00:00',
  timestamp: new Date(2024, 0, 1).getTime(),
  buySell: 'SELL',
  quantity: 1,
  tradePrice: 1,
  proceeds: 1,
  commission: -1,
  commissionCost: 1,
  netCash: 0,
  netCashInBase: null,
  currency: 'EUR',
  exchange: 'X',
  orderReference: '',
  accountId: 'U1',
  openCloseIndicator: 'C',
  fifoPnlRealized: 0,
  capitalGainsPnl: 0,
  fxPnl: 0,
  realizedPnl: 0,
  pnlSource: 'fifo',
  openTimestamp: null
};

function trade(patch: Partial<Trade> & { realizedPnl: number }): Trade {
  return {
    ...BASE_TRADE,
    ...patch,
    realizedPnl: patch.realizedPnl,
    fifoPnlRealized: patch.fifoPnlRealized ?? patch.realizedPnl
  };
}

test('local range filter keeps exactly the first quarter', () => {
  assert.equal(ALL.length, 14);
  assert.equal(Q1.length, 12);
  assert.ok(Q1.every((row) => row.tradeDate >= '2023-12-21'));
});

test('monthly aggregation', () => {
  const months = monthlyPnl(Q1);
  assert.deepEqual(months, [
    { month: '2024-01', pnl: 48, trades: 2 },
    { month: '2024-02', pnl: 208, trades: 2 },
    { month: '2024-03', pnl: 138, trades: 2 }
  ]);
});

test('symbol aggregation is sorted and capped for the chart', () => {
  const symbols = symbolPnl(Q1);
  assert.deepEqual(
    symbols.map((entry) => [entry.symbol, entry.pnl]),
    [
      ['NVDA', 239],
      ['AAPL', 99],
      ['AMD', 99],
      ['SPY', 39],
      ['TSLA', -31],
      ['MSFT', -51]
    ]
  );
  assert.equal(symbolPnl(Q1, 4).length, 4, 'top-N keeps both tails');
});

test('cumulative curve is monotonic in time and matches the sum', () => {
  const curve = buildCurve(Q1);
  assert.equal(curve.length, 6);
  assert.equal(curve[curve.length - 1]?.cumulative, 394);
  for (let index = 1; index < curve.length; index += 1) {
    assert.ok((curve[index]?.timestamp ?? 0) >= (curve[index - 1]?.timestamp ?? 0));
  }
});

test('drawdown series never goes positive', () => {
  const series = drawdownSeries(buildCurve(Q1));
  assert.equal(series.length, 6);
  assert.ok(series.every((point) => point.drawdown <= 0));
  assert.equal(Math.min(...series.map((point) => point.drawdown)), -51);
});

test('full statistics for the fixture quarter', () => {
  const stats = computeStats(Q1);
  assert.equal(stats.tradeRows, 12);
  assert.equal(stats.tradesWithPnl, 6);
  assert.equal(stats.wins, 4);
  assert.equal(stats.losses, 2);
  assert.equal(stats.breakEven, 0);
  assert.equal(stats.totalRealizedPnl, 394);
  assert.equal(stats.grossProfit, 476);
  assert.equal(stats.grossLoss, -82);
  assert.equal(stats.profitFactor, 5.8);
  assert.equal(stats.profitFactorInfinite, false);
  assert.equal(stats.winRate, 0.6667);
  assert.equal(stats.averageWin, 119);
  assert.equal(stats.averageLoss, -41);
  assert.equal(stats.largestWin, 239);
  assert.equal(stats.largestLoss, -51);
  assert.equal(stats.totalCommissions, 12);
  assert.equal(stats.maxDrawdown, -51);
  assert.equal(stats.maxDrawdownPct, -0.5152);
  assert.equal(stats.bestSymbol?.symbol, 'NVDA');
  assert.equal(stats.worstSymbol?.symbol, 'MSFT');
  assert.equal(stats.averageHoldingDays, null, 'TradeConfirm fixtures have no openDate');
  assert.equal(stats.tradingDays, 6);
});

test('sharpe-like ratio matches an independent computation', () => {
  const daily = [99, -51, 239, -31, 39, 99];
  const mean = daily.reduce((sum, value) => sum + value, 0) / daily.length;
  const variance = daily.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (daily.length - 1);
  const expected = Math.round((mean / Math.sqrt(variance)) * Math.sqrt(252) * 100) / 100;
  assert.equal(sharpeLike(Q1), expected);
});

test('zero trades produce a fully neutral stats object', () => {
  const stats = computeStats([]);
  assert.equal(stats.tradesWithPnl, 0);
  assert.equal(stats.totalRealizedPnl, 0);
  assert.equal(stats.winRate, null);
  assert.equal(stats.profitFactor, null);
  assert.equal(stats.profitFactorInfinite, false);
  assert.equal(stats.averageWin, null);
  assert.equal(stats.averageLoss, null);
  assert.equal(stats.largestWin, null);
  assert.equal(stats.largestLoss, null);
  assert.equal(stats.bestSymbol, null);
  assert.equal(stats.maxDrawdown, 0);
  assert.equal(stats.maxDrawdownPct, null);
  assert.equal(stats.sharpeLike, null);
  assert.equal(stats.tradingDays, 0);
});

test('zero losses makes the profit factor infinite instead of NaN', () => {
  const stats = computeStats([trade({ realizedPnl: 10 }), trade({ realizedPnl: 5 })]);
  assert.equal(stats.grossLoss, 0);
  assert.equal(stats.profitFactor, null);
  assert.equal(stats.profitFactorInfinite, true);
  assert.equal(stats.winRate, 1);
});

test('all losses still reports a finite profit factor of zero', () => {
  const stats = computeStats([trade({ realizedPnl: -10 }), trade({ realizedPnl: -5 })]);
  assert.equal(stats.profitFactor, 0);
  assert.equal(stats.profitFactorInfinite, false);
  assert.equal(stats.winRate, 0);
  assert.equal(stats.averageWin, null);
});

test('single zero-result trade yields break-even accounting', () => {
  const stats = computeStats([trade({ realizedPnl: 0 })]);
  assert.equal(stats.breakEven, 1);
  assert.equal(stats.wins, 0);
  assert.equal(stats.losses, 0);
  assert.equal(stats.winRate, 0);
  assert.equal(stats.profitFactor, null);
  assert.equal(stats.profitFactorInfinite, false);
});

test('histogram handles empty and degenerate inputs', () => {
  assert.deepEqual(histogram([]), []);
  const single = histogram([5, 5, 5], 10);
  assert.equal(single.length, 1);
  assert.equal(single[0]?.count, 3);
  const spread = histogram([-10, -1, 0, 1, 10], 4);
  assert.equal(spread.reduce((sum, bin) => sum + bin.count, 0), 5);
});

test('drawdown on a hand-built curve', () => {
  const curve = [
    { timestamp: 1, date: '2024-01-01', pnl: 100, cumulative: 100 },
    { timestamp: 2, date: '2024-01-02', pnl: -150, cumulative: -50 },
    { timestamp: 3, date: '2024-01-03', pnl: 20, cumulative: -30 },
    { timestamp: 4, date: '2024-01-04', pnl: 230, cumulative: 200 }
  ];
  assert.deepEqual(
    drawdownSeries(curve).map((point) => point.drawdown),
    [0, -150, -130, 0]
  );
});

test('average holding period uses open dates when present', () => {
  const holding = [
    trade({
      realizedPnl: 10,
      openTimestamp: new Date(2024, 0, 1).getTime(),
      timestamp: new Date(2024, 0, 11).getTime()
    }),
    trade({
      realizedPnl: -5,
      openTimestamp: new Date(2024, 0, 1).getTime(),
      timestamp: new Date(2024, 0, 6).getTime()
    })
  ];
  assert.equal(averageHoldingDays(holding), 7.5);
  assert.equal(averageHoldingDays([trade({ realizedPnl: 1 })]), null);
});

test('analytics bundles every series for one currency', () => {
  const analytics = computeAnalytics(Q1);
  assert.equal(analytics.currency, 'EUR');
  assert.equal(analytics.curve.length, 6);
  assert.equal(analytics.monthly.length, 3);
  assert.equal(analytics.histogram.reduce((sum, bin) => sum + bin.count, 0), 6);
  assert.equal(analytics.drawdown.length, 6);
  assert.equal(analytics.bySymbol.length, 6);
});

test('multi-currency fixture is grouped, never summed', () => {
  const groups = groupByCurrency(parseTrades(fixture('trades-sample-multi-currency.xml')));
  assert.deepEqual([...groups.keys()].sort(), ['EUR', 'USD']);
  assert.equal(groups.get('EUR')?.length, 1);
  assert.equal(groups.get('USD')?.length, 2);
});
