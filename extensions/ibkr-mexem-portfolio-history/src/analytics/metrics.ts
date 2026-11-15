import { formatIsoDate } from '../core/dates.ts';
import type { Trade } from '../core/types.ts';

export interface PnlSeriesPoint {
  readonly timestamp: number;
  readonly date: string;
  readonly pnl: number;
  readonly cumulative: number;
}

export interface MonthlyBar {
  readonly month: string;
  readonly pnl: number;
  readonly trades: number;
}

export interface SymbolBar {
  readonly symbol: string;
  readonly pnl: number;
  readonly trades: number;
}

export interface HistogramBin {
  readonly from: number;
  readonly to: number;
  readonly label: string;
  readonly count: number;
}

export interface DrawdownPoint {
  readonly timestamp: number;
  readonly date: string;
  readonly drawdown: number;
}

export interface Stats {
  readonly tradeRows: number;
  readonly tradesWithPnl: number;
  readonly wins: number;
  readonly losses: number;
  readonly breakEven: number;
  readonly winRate: number | null;
  readonly totalRealizedPnl: number;
  readonly grossProfit: number;
  readonly grossLoss: number;
  readonly profitFactor: number | null;
  readonly profitFactorInfinite: boolean;
  readonly averageWin: number | null;
  readonly averageLoss: number | null;
  readonly largestWin: number | null;
  readonly largestLoss: number | null;
  /**
   * Sum of `commissionCost` in TRADE currencies. Meaningful only when every row
   * shares one currency; the UI reports commissions per currency instead.
   */
  readonly totalCommissions: number;
  readonly averageHoldingDays: number | null;
  readonly bestSymbol: SymbolBar | null;
  readonly worstSymbol: SymbolBar | null;
  readonly maxDrawdown: number;
  readonly maxDrawdownPct: number | null;
  readonly sharpeLike: number | null;
  readonly tradingDays: number;
}

export interface AnalyticsOptions {
  /** Histogram bucket count. */
  readonly histogramBins?: number;
  /** How many symbols the "P&L by symbol" chart keeps. */
  readonly topSymbols?: number;
  /** Rows whose `timestamp` is not finite are dropped from series. */
  readonly annualisationFactor?: number;
  /**
   * Currency label for the bundle. Every P&L series here is the account base
   * currency, so callers pass the detected base currency.
   */
  readonly currency?: string;
}

export interface CurrencyAnalytics {
  readonly currency: string;
  readonly stats: Stats;
  readonly curve: readonly PnlSeriesPoint[];
  readonly monthly: readonly MonthlyBar[];
  readonly bySymbol: readonly SymbolBar[];
  readonly histogram: readonly HistogramBin[];
  readonly drawdown: readonly DrawdownPoint[];
}

const DEFAULT_ANNUALISATION = 252;

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function withPnl(trades: readonly Trade[]): Trade[] {
  return trades.filter((trade) => trade.realizedPnl !== null && Number.isFinite(trade.realizedPnl));
}

function pnlOf(trade: Trade): number {
  return trade.realizedPnl ?? 0;
}

function monthKey(timestamp: number): string | null {
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  const date = new Date(timestamp);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${date.getFullYear()}-${month}`;
}

function dateKey(timestamp: number): string | null {
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  return formatIsoDate(new Date(timestamp));
}

export function sortByTimestamp(trades: readonly Trade[]): Trade[] {
  return [...trades].sort((a, b) => {
    const left = Number.isFinite(a.timestamp) ? a.timestamp : Number.MAX_SAFE_INTEGER;
    const right = Number.isFinite(b.timestamp) ? b.timestamp : Number.MAX_SAFE_INTEGER;
    return left - right;
  });
}

/** Cumulative realized P&L over closing trades, in chronological order. */
export function buildCurve(trades: readonly Trade[]): PnlSeriesPoint[] {
  const sorted = sortByTimestamp(withPnl(trades));
  let cumulative = 0;
  const points: PnlSeriesPoint[] = [];
  for (const trade of sorted) {
    const pnl = pnlOf(trade);
    cumulative += pnl;
    points.push({
      timestamp: trade.timestamp,
      date: dateKey(trade.timestamp) ?? trade.tradeDate,
      pnl: round2(pnl),
      cumulative: round2(cumulative)
    });
  }
  return points;
}

export function monthlyPnl(trades: readonly Trade[]): MonthlyBar[] {
  const buckets = new Map<string, { pnl: number; trades: number }>();
  for (const trade of withPnl(trades)) {
    const key = monthKey(trade.timestamp);
    if (!key) {
      continue;
    }
    const current = buckets.get(key) ?? { pnl: 0, trades: 0 };
    current.pnl += pnlOf(trade);
    current.trades += 1;
    buckets.set(key, current);
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([month, value]) => ({ month, pnl: round2(value.pnl), trades: value.trades }));
}

export function symbolPnl(trades: readonly Trade[], topSymbols = 20): SymbolBar[] {
  const buckets = new Map<string, { pnl: number; trades: number }>();
  for (const trade of withPnl(trades)) {
    const key = trade.symbol || 'UNKNOWN';
    const current = buckets.get(key) ?? { pnl: 0, trades: 0 };
    current.pnl += pnlOf(trade);
    current.trades += 1;
    buckets.set(key, current);
  }
  const all = [...buckets.entries()].map(([symbol, value]) => ({
    symbol,
    pnl: round2(value.pnl),
    trades: value.trades
  }));
  all.sort((a, b) => b.pnl - a.pnl);
  if (all.length <= topSymbols) {
    return all;
  }
  const best = all.slice(0, Math.ceil(topSymbols / 2));
  const worst = all.slice(-Math.floor(topSymbols / 2));
  const merged = [...best, ...worst];
  const seen = new Set<string>();
  return merged.filter((item) => {
    if (seen.has(item.symbol)) {
      return false;
    }
    seen.add(item.symbol);
    return true;
  });
}

export function histogram(values: readonly number[], binCount = 24): HistogramBin[] {
  const finite = values.filter((value) => Number.isFinite(value));
  if (finite.length === 0) {
    return [];
  }
  const bins = Math.max(1, Math.min(200, Math.trunc(binCount)));
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  if (min === max) {
    return [{ from: round2(min), to: round2(max), label: `${round2(min).toFixed(2)}`, count: finite.length }];
  }
  const width = (max - min) / bins;
  const counts = new Array<number>(bins).fill(0);
  for (const value of finite) {
    let index = Math.floor((value - min) / width);
    if (index < 0) {
      index = 0;
    }
    if (index >= bins) {
      index = bins - 1;
    }
    counts[index] = (counts[index] ?? 0) + 1;
  }
  return counts.map((count, index) => {
    const from = min + width * index;
    const to = index === bins - 1 ? max : min + width * (index + 1);
    return {
      from: round2(from),
      to: round2(to),
      label: `${round2(from).toFixed(2)} … ${round2(to).toFixed(2)}`,
      count
    };
  });
}

/** Drawdown of the cumulative realized curve: always <= 0. */
export function drawdownSeries(curve: readonly PnlSeriesPoint[]): DrawdownPoint[] {
  let peak = Number.NEGATIVE_INFINITY;
  const points: DrawdownPoint[] = [];
  for (const point of curve) {
    if (point.cumulative > peak) {
      peak = point.cumulative;
    }
    points.push({
      timestamp: point.timestamp,
      date: point.date,
      drawdown: round2(point.cumulative - peak)
    });
  }
  return points;
}

function dailyPnl(trades: readonly Trade[]): { key: string; pnl: number }[] {
  const buckets = new Map<string, number>();
  for (const trade of withPnl(trades)) {
    const key = dateKey(trade.timestamp);
    if (!key) {
      continue;
    }
    buckets.set(key, (buckets.get(key) ?? 0) + pnlOf(trade));
  }
  return [...buckets.entries()]
    .map(([key, pnl]) => ({ key, pnl }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

/**
 * Daily Sharpe-like ratio: mean/stdev of the daily realized P&L series in
 * account currency, annualised with sqrt(252). It is NOT a return-based Sharpe:
 * daily P&L is not divided by equity, and no risk-free rate is subtracted.
 */
export function sharpeLike(trades: readonly Trade[], annualisationFactor = DEFAULT_ANNUALISATION): number | null {
  const series = dailyPnl(trades).map((entry) => entry.pnl);
  if (series.length < 2) {
    return null;
  }
  const mean = series.reduce((sum, value) => sum + value, 0) / series.length;
  const variance = series.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (series.length - 1);
  const deviation = Math.sqrt(variance);
  if (!(deviation > 0) || !Number.isFinite(deviation)) {
    return null;
  }
  return round2((mean / deviation) * Math.sqrt(annualisationFactor));
}

export function averageHoldingDays(trades: readonly Trade[]): number | null {
  const durations: number[] = [];
  for (const trade of trades) {
    if (trade.realizedPnl === null || trade.openTimestamp === null) {
      continue;
    }
    if (!Number.isFinite(trade.openTimestamp) || !Number.isFinite(trade.timestamp)) {
      continue;
    }
    const days = (trade.timestamp - trade.openTimestamp) / 86_400_000;
    if (days >= 0) {
      durations.push(days);
    }
  }
  if (durations.length === 0) {
    return null;
  }
  return round2(durations.reduce((sum, value) => sum + value, 0) / durations.length);
}

export function computeStats(trades: readonly Trade[], options: AnalyticsOptions = {}): Stats {
  const closing = withPnl(trades);
  const values = closing.map(pnlOf);
  const wins = values.filter((value) => value > 0);
  const losses = values.filter((value) => value < 0);
  const breakEven = values.filter((value) => value === 0);
  const grossProfit = wins.reduce((sum, value) => sum + value, 0);
  const grossLoss = losses.reduce((sum, value) => sum + value, 0);
  const totalRealizedPnl = grossProfit + grossLoss;

  let profitFactor: number | null = null;
  let profitFactorInfinite = false;
  if (grossLoss !== 0) {
    profitFactor = round2(grossProfit / Math.abs(grossLoss));
  } else if (grossProfit > 0) {
    profitFactorInfinite = true;
  }

  const symbols = symbolPnl(trades, Number.MAX_SAFE_INTEGER);
  const bestSymbol = symbols.length > 0 ? (symbols[0] ?? null) : null;
  const worstSymbol = symbols.length > 0 ? (symbols[symbols.length - 1] ?? null) : null;

  const curve = buildCurve(trades);
  const drawdown = drawdownSeries(curve);
  let maxDrawdown = 0;
  let maxDrawdownPct: number | null = null;
  let peak = Number.NEGATIVE_INFINITY;
  for (const point of curve) {
    if (point.cumulative > peak) {
      peak = point.cumulative;
    }
    if (peak > 0) {
      const pct = (point.cumulative - peak) / peak;
      if (maxDrawdownPct === null || pct < maxDrawdownPct) {
        maxDrawdownPct = pct;
      }
    }
  }
  for (const point of drawdown) {
    if (point.drawdown < maxDrawdown) {
      maxDrawdown = point.drawdown;
    }
  }

  const annualisation = options.annualisationFactor ?? DEFAULT_ANNUALISATION;

  return {
    tradeRows: trades.length,
    tradesWithPnl: closing.length,
    wins: wins.length,
    losses: losses.length,
    breakEven: breakEven.length,
    winRate: closing.length === 0 ? null : round4(wins.length / closing.length),
    totalRealizedPnl: round2(totalRealizedPnl),
    grossProfit: round2(grossProfit),
    grossLoss: round2(grossLoss),
    profitFactor,
    profitFactorInfinite,
    averageWin: wins.length === 0 ? null : round2(grossProfit / wins.length),
    averageLoss: losses.length === 0 ? null : round2(grossLoss / losses.length),
    largestWin: wins.length === 0 ? null : round2(Math.max(...wins)),
    largestLoss: losses.length === 0 ? null : round2(Math.min(...losses)),
    totalCommissions: round2(trades.reduce((sum, trade) => sum + trade.commissionCost, 0)),
    averageHoldingDays: averageHoldingDays(trades),
    bestSymbol,
    worstSymbol,
    maxDrawdown: round2(maxDrawdown),
    maxDrawdownPct: maxDrawdownPct === null ? null : round4(maxDrawdownPct),
    sharpeLike: sharpeLike(trades, annualisation),
    tradingDays: dailyPnl(trades).length
  };
}

export function computeAnalytics(trades: readonly Trade[], options: AnalyticsOptions = {}): CurrencyAnalytics {
  // All P&L series are base currency. `currency` only labels them.
  const currency = options.currency ?? trades[0]?.currency ?? 'UNKNOWN';
  const curve = buildCurve(trades);
  return {
    currency,
    stats: computeStats(trades, options),
    curve,
    monthly: monthlyPnl(trades),
    bySymbol: symbolPnl(trades, options.topSymbols ?? 20),
    histogram: histogram(
      withPnl(trades).map(pnlOf),
      options.histogramBins ?? 24
    ),
    drawdown: drawdownSeries(curve)
  };
}

/** Group trades by currency, preserving first-seen order. */
export function groupByCurrency(trades: readonly Trade[]): Map<string, Trade[]> {
  const groups = new Map<string, Trade[]>();
  for (const trade of trades) {
    const key = trade.currency || 'UNKNOWN';
    const bucket = groups.get(key);
    if (bucket) {
      bucket.push(trade);
    } else {
      groups.set(key, [trade]);
    }
  }
  return groups;
}
