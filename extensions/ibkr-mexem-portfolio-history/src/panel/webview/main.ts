import { Chart } from 'chart.js/auto';
import type { ChartConfiguration, ChartType } from 'chart.js';
import { isKnownCurrency } from '../../core/currency.ts';
import { formatBaseAmount, formatTradeAmount } from '../../core/format.ts';
import type { FormState, RangePreset } from '../../core/types.ts';
import type { DatasetPayload, HostMessage, SettingsSnapshot, TradeRow, WebviewMessage } from '../protocol.ts';
import {
  DEFAULT_TRADE_PAGE_SIZE,
  DEFAULT_TRADE_SORT_DIRECTION,
  DEFAULT_TRADE_SORT_KEY,
  filterTrades,
  paginate,
  parsePageSize,
  sortTrades
} from './pagination.ts';
import type { Page, SortDirection, TradePageSize, TradeSortKey } from './pagination.ts';
import { resolvePnlColumn } from './pnlColumn.ts';
import type { PnlColumnModel } from './pnlColumn.ts';

declare function acquireVsCodeApi(): {
  postMessage(message: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
};

const vscode = acquireVsCodeApi();

const POS = '#2ea043';
const NEG = '#d1242f';
const ACCENT = '#3b8eea';

const CHARTS = ['chart-equity', 'chart-drawdown', 'chart-monthly', 'chart-symbol', 'chart-histogram'] as const;
const chartInstances = new Map<string, { destroy(): void; resize(): void }>();

let settings: SettingsSnapshot | null = null;
let dataset: DatasetPayload | null = null;
let busy = false;
let maxAttempts = 0;
let deadlineMs = 0;
let fetchStartedAt = 0;
let lastIbkrStatus = '';
let elapsedTimer: number | null = null;

/** Rows appended per animation frame when a page is larger than one chunk. */
const TRADE_CHUNK_ROWS = 500;

let tradePage = 1;
let tradePageSize: TradePageSize = DEFAULT_TRADE_PAGE_SIZE;
let tradeFilter = '';
let tradeSortKey: TradeSortKey = DEFAULT_TRADE_SORT_KEY;
let tradeSortDirection: SortDirection = DEFAULT_TRADE_SORT_DIRECTION;
let tradeRenderToken = 0;
let tradeRenderHandle: number | null = null;

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) {
    throw new Error(`Missing element #${id}`);
  }
  return node as T;
}

function post(message: WebviewMessage): void {
  vscode.postMessage(message);
}

function money(value: number | null | undefined, currency: string): string {
  return formatBaseAmount(value, currency);
}

function tradeMoney(value: number | null | undefined, currency: string): string {
  return formatTradeAmount(value, currency);
}

function ratio(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function plain(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  return value.toFixed(digits);
}

function toneClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) {
    return '';
  }
  return value > 0 ? 'pos' : 'neg';
}

function baseCurrency(): string {
  return dataset?.baseCurrency ?? 'UNKNOWN';
}

/** Currency the P&L series is expressed in: the base currency by default. */
function displayCurrency(): string {
  return dataset?.displayCurrency ?? dataset?.baseCurrency ?? 'UNKNOWN';
}

/**
 * Single source of truth for the P&L column: the table cells, the header label
 * and the summary badge all read this model, so they cannot diverge.
 */
function pnlColumn(): PnlColumnModel {
  return resolvePnlColumn({ baseCurrency: baseCurrency(), displayCurrency: displayCurrency(), isKnownCurrency });
}

function currencyButtonLabel(code: string): string {
  return code === baseCurrency() ? `${code} base` : code;
}

function renderStats(): void {
  const grid = el('stats-grid');
  grid.replaceChildren();
  if (!dataset) {
    return;
  }
  const stats = dataset.analytics.stats;
  const column = pnlColumn();
  const currency = column.currency;
  const base = baseCurrency();
  const totals = dataset.pnlTotals;
  const profitFactor = stats.profitFactorInfinite
    ? '∞ (no losing trades)'
    : stats.profitFactor === null
      ? 'n/a'
      : plain(stats.profitFactor);

  const fxTitle = 'sum of fxPnl, account base currency: the part of the base P&L that comes from the exchange rate';
  const noFxTitle = 'sum of capitalGainsPnl, account base currency: the base P&L without the FX result';
  const items: { label: string; value: string; tone?: string; title?: string }[] = [
    {
      label: column.isBaseView ? 'Total realized P&L' : `Total realized P&L (${currency}, excl. FX)`,
      value: money(stats.totalRealizedPnl, currency),
      tone: toneClass(stats.totalRealizedPnl)
    },
    { label: 'P&L excluding FX', value: money(totals.capitalGainsTotal, base), tone: toneClass(totals.capitalGainsTotal), title: noFxTitle },
    { label: 'FX result', value: money(totals.fxTotal, base), tone: toneClass(totals.fxTotal), title: fxTitle },
    { label: 'Gross profit', value: money(stats.grossProfit, currency), tone: stats.grossProfit > 0 ? 'pos' : '' },
    { label: 'Gross loss', value: money(stats.grossLoss, currency), tone: stats.grossLoss < 0 ? 'neg' : '' },
    { label: 'Profit factor', value: profitFactor, title: 'gross profit / |gross loss|' },
    { label: 'Win rate', value: ratio(stats.winRate), title: 'wins / trades with realized P&L' },
    { label: 'Trades with realized P&L', value: `${stats.tradesWithPnl}`, title: `${stats.tradeRows} rows downloaded in range` },
    { label: 'Winning trades', value: `${stats.wins}`, tone: 'pos' },
    { label: 'Losing trades', value: `${stats.losses}`, tone: 'neg' },
    { label: 'Break-even trades', value: `${stats.breakEven}` },
    { label: 'Average win', value: money(stats.averageWin, currency), tone: 'pos' },
    { label: 'Average loss', value: money(stats.averageLoss, currency), tone: 'neg' },
    { label: 'Largest win', value: money(stats.largestWin, currency), tone: 'pos' },
    { label: 'Largest loss', value: money(stats.largestLoss, currency), tone: 'neg' },
    {
      label: 'Average holding period',
      value: stats.averageHoldingDays === null ? 'n/a (no open dates)' : `${plain(stats.averageHoldingDays, 1)} days`
    },
    { label: 'Best symbol', value: stats.bestSymbol ? `${stats.bestSymbol.symbol} (${money(stats.bestSymbol.pnl, currency)})` : 'n/a' },
    { label: 'Worst symbol', value: stats.worstSymbol ? `${stats.worstSymbol.symbol} (${money(stats.worstSymbol.pnl, currency)})` : 'n/a' },
    {
      label: 'Max drawdown',
      value:
        stats.maxDrawdownPct === null
          ? money(stats.maxDrawdown, currency)
          : `${money(stats.maxDrawdown, currency)} (${ratio(stats.maxDrawdownPct)})`
    },
    {
      label: 'Sharpe-like (daily, annualized)',
      value: plain(stats.sharpeLike),
      title: 'mean/stdev of daily realized P&L × √252; not return based, no risk-free rate'
    },
    { label: 'Trading days', value: `${stats.tradingDays}` }
  ];

  for (const item of items) {
    const node = document.createElement('div');
    node.className = 'stat';
    if (item.title) {
      node.title = item.title;
    }
    const label = document.createElement('span');
    label.className = 'stat-label';
    label.textContent = item.label;
    const value = document.createElement('span');
    value.className = `stat-value ${item.tone ?? ''}`.trim();
    value.textContent = item.value;
    node.append(label, value);
    grid.append(node);
  }

  const note = el('pnl-source-note');
  const fx =
    totals.capitalGainsTotal === null || totals.fxTotal === null
      ? 'This report does not carry capitalGainsPnl and fxPnl, so the FX split is unavailable.'
      : `The base view includes the FX result: ${money(totals.baseTotal, base)} = ` +
        `${money(totals.capitalGainsTotal, base)} capital gains + ${money(totals.fxTotal, base)} FX.`;
  note.textContent =
    `Realized P&L source: ${dataset.meta.rowsPnlFromFifo} trades from fifoPnlRealized, ` +
    `${dataset.meta.rowsPnlFromProceeds} approximated from netCashInBase. ` +
    `${fx} ` +
    'Sharpe-like ratio assumes 252 trading days and equal-weight daily P&L; it is not a portfolio Sharpe ratio.';
}

function currentTradeRows(): TradeRow[] {
  if (!dataset) {
    return [];
  }
  return sortTrades(filterTrades(dataset.trades, tradeFilter), tradeSortKey, tradeSortDirection);
}

function buildTradeRows(rows: readonly TradeRow[], from: number, to: number, currency: string): DocumentFragment {
  const approximated = (trade: TradeRow): string => {
    const value = trade.displayPnl ?? null;
    if (value === null || trade.displayPnlExact !== false) {
      return money(value, currency);
    }
    return `~ ${money(value, currency)}`;
  };
  const fragment = document.createDocumentFragment();
  for (let index = from; index < to; index += 1) {
    const trade = rows[index];
    if (!trade) {
      continue;
    }
    const row = document.createElement('tr');
    const cells: { text: string; className?: string; title?: string }[] = [
      { text: trade.date },
      { text: trade.time },
      { text: trade.symbol },
      { text: trade.buySell },
      { text: String(trade.quantity), className: 'num' },
      { text: plain(trade.price, 4), className: 'num' },
      { text: trade.currency },
      {
        text: approximated(trade),
        className: `num ${toneClass(trade.displayPnl ?? trade.realizedPnl)}`.trim(),
        title: trade.displayPnlExact === false ? (trade.displayPnlNote ?? 'approximate conversion') : ''
      },
      { text: trade.pnlSource }
    ];
    for (const cell of cells) {
      const td = document.createElement('td');
      td.textContent = cell.text;
      if (cell.className) {
        td.className = cell.className;
      }
      if (cell.title) {
        td.title = cell.title;
      }
      row.append(td);
    }
    fragment.append(row);
  }
  return fragment;
}

function cancelTradeRender(): void {
  tradeRenderToken += 1;
  if (tradeRenderHandle !== null) {
    window.cancelAnimationFrame(tradeRenderHandle);
    tradeRenderHandle = null;
  }
}

function setTradeRendering(value: boolean): void {
  el('trades-rendering').classList.toggle('hidden', !value);
}

function renderTradeCaption(): void {
  const caption = el('trades-caption');
  const note = el('trades-truncation-note');
  if (!dataset) {
    caption.textContent = '';
    note.classList.add('hidden');
    note.textContent = '';
    return;
  }
  const inRange = dataset.meta.rowsInRange;
  const shown = dataset.trades.length;
  if (dataset.tradesTruncated) {
    caption.textContent = `Rows shown ${shown} of ${inRange} in range`;
    note.classList.remove('hidden');
    note.textContent =
      `Only the newest ${shown} of ${inRange} trades in range are listed: the payload is capped at ` +
      `maxTradeRows = ${dataset.tradesCap}. Narrow the date range or the account filter to see the rest.`;
    return;
  }
  caption.textContent = `${inRange} trade${inRange === 1 ? '' : 's'} in range`;
  note.classList.add('hidden');
  note.textContent = '';
}

function renderTradeSortIndicators(): void {
  for (const header of document.querySelectorAll<HTMLTableCellElement>('#trades-table th[data-sort]')) {
    const key = header.dataset['sort'];
    const active = key === tradeSortKey;
    header.classList.toggle('sorted', active);
    header.setAttribute('aria-sort', active ? (tradeSortDirection === 'asc' ? 'ascending' : 'descending') : 'none');
    const arrow = header.querySelector('.sort-arrow');
    if (arrow) {
      arrow.textContent = active ? (tradeSortDirection === 'asc' ? '\u25b2' : '\u25bc') : '';
    }
  }
}

function renderTradePager(page: Page<TradeRow>): void {
  const counter = el('trades-counter');
  counter.textContent =
    page.total === 0 ? 'Showing 0\u20130 of 0' : `Showing ${page.startIndex + 1}\u2013${page.endIndex} of ${page.total}`;
  el<HTMLButtonElement>('trades-prev').disabled = page.page <= 1;
  el<HTMLButtonElement>('trades-next').disabled = page.page >= page.pageCount;
  renderTradeCaption();
  renderTradeSortIndicators();
}

function renderTradesTable(): void {
  const table = document.getElementById('trades-table') as HTMLTableElement | null;
  const body = table?.tBodies[0];
  if (!body) {
    return;
  }
  cancelTradeRender();
  const token = tradeRenderToken;
  body.replaceChildren();
  const wrap = table?.parentElement;
  if (wrap) {
    wrap.scrollTop = 0;
  }

  const rows = currentTradeRows();
  const page = paginate(rows, tradePage, tradePageSize);
  tradePage = page.page;
  renderTradePager(page);

  if (page.rows.length === 0) {
    setTradeRendering(false);
    return;
  }

  const currency = pnlColumn().currency;
  const appendChunk = (from: number): void => {
    if (token !== tradeRenderToken) {
      return;
    }
    const to = Math.min(from + TRADE_CHUNK_ROWS, page.rows.length);
    body.append(buildTradeRows(page.rows, from, to, currency));
    if (to < page.rows.length) {
      setTradeRendering(true);
      tradeRenderHandle = window.requestAnimationFrame(() => appendChunk(to));
      return;
    }
    tradeRenderHandle = null;
    setTradeRendering(false);
  };
  appendChunk(0);
}

function destroyChart(id: string): void {
  const existing = chartInstances.get(id);
  if (existing) {
    existing.destroy();
    chartInstances.delete(id);
  }
}

function mountChart<T extends ChartType>(id: string, config: ChartConfiguration<T>): void {
  const canvas = el<HTMLCanvasElement>(id);
  destroyChart(id);
  const chart = new Chart(canvas, config);
  chartInstances.set(id, chart);
}

function renderCharts(): void {
  if (!dataset) {
    for (const id of CHARTS) {
      destroyChart(id);
    }
    return;
  }
  const currency = displayCurrency();
  const analytics = dataset.analytics;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = getComputedStyle(document.body).color;

  const valueAxis = {
    ticks: {
      callback: (value: string | number) => money(Number(value), currency)
    },
    grid: { color: 'rgba(128,128,128,0.15)' }
  };

  mountChart('chart-equity', {
    type: 'line',
    data: {
      labels: analytics.curve.map((point) => point.date),
      datasets: [
        {
          label: `Cumulative P&L (${currency})`,
          data: analytics.curve.map((point) => point.cumulative),
          borderColor: ACCENT,
          backgroundColor: 'rgba(59,142,234,0.15)',
          borderWidth: 2,
          pointRadius: analytics.curve.length > 120 ? 0 : 2,
          pointHitRadius: 10,
          tension: 0.15,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => `${item.dataset.label ?? ''}: ${money(item.parsed.y, currency)}`
          }
        }
      },
      scales: { x: { grid: { display: false } }, y: valueAxis }
    }
  });

  mountChart('chart-drawdown', {
    type: 'line',
    data: {
      labels: analytics.drawdown.map((point) => point.date),
      datasets: [
        {
          label: `Drawdown (${currency})`,
          data: analytics.drawdown.map((point) => point.drawdown),
          borderColor: NEG,
          backgroundColor: 'rgba(209,36,47,0.18)',
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.1,
          fill: 'origin'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (item) => `Drawdown: ${money(item.parsed.y, currency)}` }
        }
      },
      scales: { x: { grid: { display: false } }, y: { ...valueAxis, max: 0 } }
    }
  });

  mountChart('chart-monthly', {
    type: 'bar',
    data: {
      labels: analytics.monthly.map((bar) => bar.month),
      datasets: [
        {
          label: `Monthly P&L (${currency})`,
          data: analytics.monthly.map((bar) => bar.pnl),
          backgroundColor: analytics.monthly.map((bar) => (bar.pnl >= 0 ? POS : NEG))
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (item) => money(item.parsed.y, currency) }
        }
      },
      scales: { x: { grid: { display: false } }, y: valueAxis }
    }
  });

  const orderedSymbols = [...analytics.bySymbol].sort((a, b) => a.pnl - b.pnl);
  mountChart('chart-symbol', {
    type: 'bar',
    data: {
      labels: orderedSymbols.map((bar) => bar.symbol),
      datasets: [
        {
          label: `P&L by symbol (${currency})`,
          data: orderedSymbols.map((bar) => bar.pnl),
          backgroundColor: orderedSymbols.map((bar) => (bar.pnl >= 0 ? POS : NEG))
        }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (item) => money(item.parsed.x, currency) } }
      },
      scales: { x: valueAxis, y: { grid: { display: false } } }
    }
  });

  mountChart('chart-histogram', {
    type: 'bar',
    data: {
      labels: analytics.histogram.map((bin) => bin.label),
      datasets: [
        {
          label: 'Trades',
          data: analytics.histogram.map((bin) => bin.count),
          backgroundColor: analytics.histogram.map((bin) => ((bin.from + bin.to) / 2 >= 0 ? POS : NEG)),
          categoryPercentage: 1,
          barPercentage: 0.95
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => {
              const index = items[0]?.dataIndex ?? 0;
              const bin = analytics.histogram[index];
              return bin ? `${money(bin.from, currency)} … ${money(bin.to, currency)}` : '';
            },
            label: (item) => `${item.parsed.y ?? 0} trades`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 60, autoSkip: true, maxTicksLimit: 14 } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(128,128,128,0.15)' } }
      }
    }
  });
}

function renderCurrencyFacts(): void {
  const label = el('base-currency-label');
  const banner = el('base-currency-banner');
  const header = el('th-realized-pnl-label');
  if (!dataset) {
    label.textContent = '';
    banner.classList.add('hidden');
    banner.textContent = '';
    return;
  }
  const base = dataset.baseCurrency;
  const column = pnlColumn();
  header.textContent = column.header;
  label.textContent = column.badge;

  if (!isKnownCurrency(base)) {
    banner.classList.remove('hidden');
    banner.textContent =
      'The account base currency could not be detected from this report. Realized P&L is rendered as a plain ' +
      'number with the suffix "base". Set ibkrHistory.baseCurrency to override detection.';
    return;
  }
  if (column.isBaseView) {
    const foreign = dataset.currencies.filter((code) => code !== base);
    if (foreign.length === 0) {
      banner.classList.add('hidden');
      banner.textContent = '';
      return;
    }
    banner.classList.remove('hidden');
    banner.textContent =
      `IBKR reports realized P&L in the account base currency (${base}), including the FX result. ` +
      'Trade amounts remain in their own currency. Choose another currency above to see the trade-currency result.';
    return;
  }

  const fx = dataset.pnlTotals.fxTotal;
  const fxPart =
    fx === null
      ? 'The FX effect is not available: this report does not carry fxPnl.'
      : `The FX effect (${money(fx, base)} in this dataset) is excluded, so the total differs from the ${base} base view.`;
  banner.classList.remove('hidden');
  banner.textContent =
    `In ${column.currency} this is the trade-currency result. ${fxPart} ` +
    'Rates come from the report <ConversionRate> rows, nearest earlier report date when the exact date is missing.';
}

/** Segmented control: the base currency first, then every trade currency with a rate. */
function renderCurrencySwitch(): void {
  const wrap = el('currency-switch');
  const group = el('currency-buttons');
  const options = dataset?.displayCurrencies ?? [];
  if (!dataset || options.length <= 1) {
    wrap.classList.add('hidden');
    group.replaceChildren();
    return;
  }
  wrap.classList.remove('hidden');
  group.replaceChildren();
  const active = displayCurrency();
  for (const code of options) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = currencyButtonLabel(code);
    button.setAttribute('aria-pressed', code === active ? 'true' : 'false');
    button.title =
      code === baseCurrency()
        ? `Account base currency, includes the FX result`
        : `Trade-currency P&L, excludes the FX result`;
    button.addEventListener('click', () => {
      if (code !== displayCurrency()) {
        post({ type: 'displayCurrency', currency: code });
      }
    });
    group.append(button);
  }
}

function renderCommissions(): void {
  const table = document.getElementById('commissions-table') as HTMLTableElement | null;
  const body = table?.tBodies[0];
  const note = el('commission-note');
  if (!body) {
    return;
  }
  body.replaceChildren();
  note.textContent = '';
  if (!dataset) {
    return;
  }
  const base = baseCurrency();
  for (const row of dataset.commissions) {
    const tr = document.createElement('tr');
    const cells: { text: string; className?: string }[] = [
      { text: row.currency },
      { text: String(row.trades), className: 'num' },
      { text: tradeMoney(row.commissionCost, row.currency), className: 'num' },
      {
        text:
          row.estimatedBase === null
            ? 'n/a'
            : `≈ ${money(row.estimatedBase, base)}${row.complete ? '' : ' (partial)'}`,
        className: 'num'
      }
    ];
    for (const cell of cells) {
      const td = document.createElement('td');
      td.textContent = cell.text;
      if (cell.className) {
        td.className = cell.className;
      }
      tr.append(td);
    }
    body.append(tr);
  }

  const estimate = dataset.commissionEstimateBase;
  const parts = [
    'Commission amounts are in the trade currency and are never summed across currencies as if they were base amounts.'
  ];
  if (estimate === null) {
    parts.push('No base-currency estimate: the account base currency is unknown.');
  } else {
    parts.push(
      `Estimated total in ${base}: ≈ ${money(estimate, base)}. ` +
        `The estimate (report FX rate) converts each trade with the ConversionRate whose reportDate is closest to it` +
        `${dataset.commissionEstimateComplete ? '' : ' and is partial because a rate is missing'}. ` +
        'It is an estimate, never an exact IBKR figure.'
    );
  }
  note.textContent = parts.join(' ');
}

function renderHeader(): void {
  const summary = el('header-summary');
  if (!dataset) {
    summary.textContent = 'Flex Web Service · realized P&L only';
    return;
  }
  const meta = dataset.meta;
  summary.textContent =
    `${meta.range.label} (${meta.range.start} → ${meta.range.end}) · ` +
    `${meta.rowsInRange} trades in range of ${meta.rowsTotal} downloaded · accounts: ${meta.accounts.join(', ') || 'n/a'}`;
}

function renderWarnings(): void {
  const box = el('warning-box');
  if (!dataset || dataset.meta.warnings.length === 0) {
    box.classList.add('hidden');
    box.textContent = '';
    return;
  }
  box.classList.remove('hidden');
  box.textContent = dataset.meta.warnings.join('\n');
}

function renderAll(): void {
  renderHeader();
  renderWarnings();
  renderCurrencySwitch();
  renderCurrencyFacts();
  renderStats();
  renderCharts();
  renderTradesTable();
  renderCommissions();
  const results = el('results');
  results.classList.toggle('hidden', !dataset);
  const exportButton = el<HTMLButtonElement>('btn-export');
  exportButton.disabled = busy || !dataset;
}

function showError(message: string, fieldErrors: Record<string, string> = {}): void {
  const box = el('error-box');
  box.classList.remove('hidden');
  box.textContent = message;
  el('error-actions').classList.remove('hidden');
  for (const id of ['token', 'queryId', 'accountId', 'preset', 'customStart', 'customEnd']) {
    el(id).classList.remove('invalid');
  }
  for (const [field, text] of Object.entries(fieldErrors)) {
    const target = document.getElementById(field);
    if (target) {
      target.classList.add('invalid');
    }
    const hint = document.getElementById(`${field}-hint`);
    if (hint) {
      hint.textContent = text;
      hint.classList.add('error-text');
    }
  }
}

function clearAlerts(): void {
  for (const id of ['error-box', 'info-box']) {
    const box = el(id);
    box.classList.add('hidden');
    box.textContent = '';
  }
  el('error-actions').classList.add('hidden');
  for (const id of ['token', 'queryId', 'accountId', 'preset', 'customStart', 'customEnd']) {
    el(id).classList.remove('invalid');
  }
  const tokenHint = document.getElementById('token-hint');
  if (tokenHint) {
    tokenHint.classList.remove('error-text');
  }
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function updateProgressMeta(): void {
  const meta = el('progress-meta');
  if (!busy) {
    meta.textContent = '';
    return;
  }
  const parts = [`Elapsed ${formatElapsed(Date.now() - fetchStartedAt)}`];
  if (lastIbkrStatus) {
    parts.push(`last IBKR status: ${lastIbkrStatus}`);
  }
  meta.textContent = parts.join(' · ');
}

/** Days covered by the selected range, used only for the "large range" hint. */
function rangeDays(): number {
  const preset = el<HTMLSelectElement>('preset').value as RangePreset;
  if (preset === 'last30') {
    return 30;
  }
  if (preset === 'last90') {
    return 90;
  }
  if (preset === 'last365') {
    return 365;
  }
  if (preset === 'ytd') {
    const now = new Date();
    return Math.ceil((now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / 86_400_000);
  }
  const start = el<HTMLInputElement>('customStart').value;
  const end = el<HTMLInputElement>('customEnd').value;
  const startMs = Date.parse(`${start}T00:00:00`);
  const endMs = Date.parse(`${end}T00:00:00`);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
    return 0;
  }
  return Math.round((endMs - startMs) / 86_400_000);
}

function updateRangeHint(): void {
  el('range-hint').classList.toggle('hidden', rangeDays() <= 90);
}

function setBusy(value: boolean, message = ''): void {
  busy = value;
  const fetchButton = el<HTMLButtonElement>('btn-fetch');
  const cancelButton = el<HTMLButtonElement>('btn-cancel');
  const exportButton = el<HTMLButtonElement>('btn-export');
  fetchButton.disabled = value;
  cancelButton.disabled = !value;
  exportButton.disabled = value || !dataset;
  fetchButton.textContent = value ? 'Fetching…' : 'Fetch report';
  el('status').textContent = message;
  const progress = el('progress');
  progress.classList.toggle('hidden', !value);
  if (value) {
    if (elapsedTimer === null) {
      fetchStartedAt = Date.now();
      lastIbkrStatus = '';
      elapsedTimer = window.setInterval(updateProgressMeta, 1_000);
    }
    updateProgressMeta();
  } else {
    if (elapsedTimer !== null) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
    el('progress-bar').style.width = '0%';
    el('progress-text').textContent = '';
    el('progress-meta').textContent = '';
  }
}

function toggleCustomFields(): void {
  const preset = el<HTMLSelectElement>('preset').value;
  const isCustom = preset === 'custom';
  el('custom-start-field').classList.toggle('hidden', !isCustom);
  el('custom-end-field').classList.toggle('hidden', !isCustom);
  updateRangeHint();
}

function todayIso(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function applySettings(value: SettingsSnapshot): void {
  settings = value;
  const token = el<HTMLInputElement>('token');
  token.value = '';
  token.placeholder = value.hasToken ? 'token stored — leave blank to reuse' : 'paste your Flex token';
  const queryId = el<HTMLInputElement>('queryId');
  queryId.value = '';
  queryId.placeholder = value.hasQueryId ? `stored: ${value.queryIdMasked}` : 'e.g. 1234567';
  el<HTMLInputElement>('accountId').value = value.accountFilter;
  const preset = el<HTMLSelectElement>('preset');
  preset.value = value.preset;
  const start = el<HTMLInputElement>('customStart');
  const end = el<HTMLInputElement>('customEnd');
  start.value = value.customStart || todayIso(-30);
  end.value = value.customEnd || todayIso(0);
  toggleCustomFields();
  updateRangeHint();
}

function collectForm(): FormState {
  return {
    token: el<HTMLInputElement>('token').value,
    queryId: el<HTMLInputElement>('queryId').value.trim(),
    preset: el<HTMLSelectElement>('preset').value as RangePreset,
    customStart: el<HTMLInputElement>('customStart').value,
    customEnd: el<HTMLInputElement>('customEnd').value,
    accountId: el<HTMLInputElement>('accountId').value.trim()
  };
}

function localValidate(): boolean {
  const form = collectForm();
  const errors: Record<string, string> = {};
  if (form.queryId && !/^\d{3,12}$/.test(form.queryId)) {
    errors['queryId'] = 'Query ID must be numeric (3 to 12 digits).';
  }
  if (!form.queryId && settings && !settings.hasQueryId) {
    errors['queryId'] = 'Query ID is required.';
  }
  if (form.preset === 'custom') {
    if (!form.customStart || !form.customEnd) {
      errors['customStart'] = 'Both custom dates are required.';
    } else if (form.customStart > form.customEnd) {
      errors['customStart'] = 'Start date must be before or equal to end date.';
    }
  }
  const messages = Object.values(errors);
  if (messages.length > 0) {
    showError(messages.join(' '), errors);
    return false;
  }
  return true;
}

function submit(): void {
  if (busy) {
    return;
  }
  clearAlerts();
  if (!localValidate()) {
    return;
  }
  post({ type: 'fetch', form: collectForm() });
}

function handleMessage(event: MessageEvent<HostMessage>): void {
  const message = event.data;
  switch (message.type) {
    case 'state':
      maxAttempts = message.maxAttempts;
      deadlineMs = message.deadlineMs;
      applySettings(message.settings);
      el('status').textContent = message.settings.lastFetchIso
        ? `Last successful fetch: ${message.settings.lastFetchIso} · limit ${Math.round(deadlineMs / 60_000)} min`
        : `Limit ${Math.round(deadlineMs / 60_000)} min · up to ${maxAttempts} polls`;
      break;
    case 'busy':
      setBusy(message.busy, message.message);
      break;
    case 'progress': {
      const ratioValue = message.maxAttempts > 0 ? Math.min(1, message.attempt / message.maxAttempts) : 0;
      const share = message.phase === 'send' ? 0.05 : 1;
      el('progress-bar').style.width = `${Math.round(ratioValue * share * 100)}%`;
      const label = message.phase === 'send' ? 'attempt' : 'poll';
      el('progress-text').textContent = `${message.message} (${label} ${message.attempt}/${message.maxAttempts})`;
      if (message.lastStatus) {
        lastIbkrStatus = message.lastStatus;
      }
      updateProgressMeta();
      break;
    }
    case 'data': {
      dataset = message.dataset;
      // A currency switch re-expresses the same rows: keep the filter and the page.
      if (message.reason !== 'currency') {
        tradePage = 1;
        tradeFilter = '';
        el<HTMLInputElement>('trades-filter').value = '';
        clearAlerts();
      }
      renderAll();
      el('status').textContent =
        message.reason === 'currency'
          ? `Realized P&L shown in ${message.dataset.displayCurrency}`
          : `Fetched ${message.dataset.meta.rowsTotal} rows at ${message.dataset.meta.generatedAt}`;
      break;
    }
    case 'error':
      showError(message.message, { ...message.fieldErrors });
      el('status').textContent = '';
      break;
    case 'info': {
      const box = el('info-box');
      box.classList.remove('hidden');
      box.textContent = message.message;
      break;
    }
    case 'requestFetch':
      submit();
      break;
    default:
      break;
  }
}

function applyTradeSort(key: TradeSortKey): void {
  if (key === tradeSortKey) {
    tradeSortDirection = tradeSortDirection === 'asc' ? 'desc' : 'asc';
  } else {
    tradeSortKey = key;
    tradeSortDirection = key === 'date' ? 'desc' : 'asc';
  }
  tradePage = 1;
  renderTradesTable();
}

function wireTradeTable(): void {
  el<HTMLSelectElement>('trades-page-size').addEventListener('change', (event) => {
    tradePageSize = parsePageSize((event.target as HTMLSelectElement).value);
    tradePage = 1;
    renderTradesTable();
  });
  el('trades-prev').addEventListener('click', () => {
    tradePage = Math.max(1, tradePage - 1);
    renderTradesTable();
  });
  el('trades-next').addEventListener('click', () => {
    tradePage += 1;
    renderTradesTable();
  });
  el<HTMLInputElement>('trades-filter').addEventListener('input', (event) => {
    tradeFilter = (event.target as HTMLInputElement).value;
    tradePage = 1;
    renderTradesTable();
  });
  for (const header of document.querySelectorAll<HTMLTableCellElement>('#trades-table th[data-sort]')) {
    const key = header.dataset['sort'] as TradeSortKey | undefined;
    if (!key) {
      continue;
    }
    header.addEventListener('click', () => applyTradeSort(key));
    header.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        applyTradeSort(key);
      }
    });
  }
}

function wireEvents(): void {
  el<HTMLFormElement>('settings-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submit();
  });
  el('btn-cancel').addEventListener('click', () => post({ type: 'cancel' }));
  el('btn-export').addEventListener('click', () => post({ type: 'export' }));
  el('btn-docs').addEventListener('click', () => post({ type: 'openDocs' }));
  el('btn-clear').addEventListener('click', () => post({ type: 'clearCredentials' }));
  el('preset').addEventListener('change', toggleCustomFields);
  el('customStart').addEventListener('change', updateRangeHint);
  el('customEnd').addEventListener('change', updateRangeHint);
  el('btn-copy-diagnostics').addEventListener('click', () => post({ type: 'copyDiagnostics' }));
  wireTradeTable();
  window.addEventListener('message', handleMessage);
  window.addEventListener('resize', () => {
    for (const chart of chartInstances.values()) {
      chart.resize();
    }
  });
}

wireEvents();
setBusy(false);
post({ type: 'ready' });
