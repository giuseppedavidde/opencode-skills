import {
  applyOptionalExpenseFilter,
  availableMonthRefs,
  calculateMetrics,
  computeRunrateMetrics,
  computeStatMetrics,
  monthLabelIt,
  num,
  prepareTimeseries,
  rollingMean,
  type DerivedRow,
} from '../metrics';
import { addMonths, buildForecast } from '../forecast';
import { MONTHS_IT, type DistributionStats, type TimeWindow } from '../types';
import { el, fmtEur, fmtEur0, fmtNum, fmtPct, clear } from './dom';
import * as charts from './charts';
import type { UiContext } from './context';

const WINDOWS: TimeWindow[] = [3, 6, 12, 24, 'All'];

function card(title: string, subtitle?: string): { section: HTMLElement; body: HTMLElement } {
  const section = el('section', { className: 'card' });
  const head = el('div', { className: 'card-head' }, [
    el('h2', { text: title }),
    subtitle ? el('p', { className: 'muted', text: subtitle }) : null,
  ]);
  const body = el('div', { className: 'card-body' });
  section.append(head, body);
  return { section, body };
}

function metric(
  label: string,
  value: string,
  delta?: string,
  deltaClass?: 'up' | 'down' | 'flat',
  caption?: string,
): HTMLElement {
  return el('div', { className: 'metric-card' }, [
    el('div', { className: 'metric-label', text: label }),
    el('div', { className: 'metric-value', text: value }),
    delta
      ? el('div', { className: `metric-delta ${deltaClass ?? 'flat'}`, text: delta })
      : null,
    caption ? el('div', { className: 'metric-caption', text: caption }) : null,
  ]);
}

function grid(children: HTMLElement[], columns = 4): HTMLElement {
  const node = el('div', { className: 'metric-grid' });
  node.style.gridTemplateColumns = `repeat(auto-fit, minmax(${columns >= 4 ? 190 : 240}px, 1fr))`;
  for (const child of children) node.append(child);
  return node;
}

function distGrid(distribution: DistributionStats, formatter: (value: number) => string): HTMLElement {
  return el('div', { className: 'stat-grid' }, [
    metric('Media', formatter(distribution.mean)),
    metric('Mediana', formatter(distribution.median)),
    metric('Dev. Std', formatter(distribution.std)),
    metric('Min', formatter(distribution.min), distribution.minMonth, 'flat'),
    metric('Max', formatter(distribution.max), distribution.maxMonth, 'flat'),
    metric('P25 / P75', `${formatter(distribution.p25)} / ${formatter(distribution.p75)}`),
  ]);
}

export function renderDashboard(root: HTMLElement, ctx: UiContext): void {
  const { state } = ctx;
  clear(root);

  const calculated = calculateMetrics(state.rows);
  const disabled: string[] = [];
  if (!state.filters.investimenti) disabled.push('Investimenti');
  if (!state.filters.straordinarie) disabled.push('Spese Straordinarie');
  const filtered = applyOptionalExpenseFilter(
    calculated.rows,
    calculated.expenseColumns,
    disabled,
    state.filters.capex,
  );
  const { asc, desc } = prepareTimeseries(filtered.rows);
  const activeExpenseColumns = filtered.activeExpenseColumns;
  const availableMonths = availableMonthRefs(state.rows);

  if (asc.length === 0) {
    root.append(
      card(
        '📊 Dashboard',
        'Nessun dato. Apri Gestione Dati per inserire il primo mese oppure importa un estratto conto.',
      ).section,
    );
    return;
  }

  let selectedRef = state.selectedMonth;
  if (!selectedRef || !availableMonths.includes(selectedRef)) {
    selectedRef = availableMonths[0] ?? '';
    state.selectedMonth = selectedRef;
  }
  const selected =
    asc.find((row) => `${row.Month} ${row.Year}` === selectedRef) ?? asc[asc.length - 1];
  if (!selected) return;

  const windowMonths = state.window === 'All' ? null : Number(state.window);
  const refMonthIt = MONTHS_IT[selected.DateObj.getMonth()] ?? selected.Month;

  const runrate = computeRunrateMetrics(asc, 12);
  const stats = computeStatMetrics(asc);
  const forecast = buildForecast(asc, 12, 1.28);

  let hasGrowth = false;
  let growthVal = 0;
  let growthPct = 0;
  let hasInvestGrowth = false;
  let investGrowthVal = 0;
  let investGrowthPct = 0;
  if (windowMonths === null) {
    growthVal = selected.patrimonio;
    hasGrowth = true;
    investGrowthVal = selected.investimentiCumulativo;
    hasInvestGrowth = true;
  } else {
    const targetDate = addMonths(selected.DateObj, -windowMonths);
    const past = desc.find((row) => row.DateObj.getTime() <= targetDate.getTime());
    if (past) {
      growthVal = selected.patrimonio - past.patrimonio;
      growthPct = past.patrimonio !== 0 ? (growthVal / Math.abs(past.patrimonio)) * 100 : 0;
      hasGrowth = true;
      investGrowthVal = selected.investimentiCumulativo - past.investimentiCumulativo;
      investGrowthPct =
        past.investimentiCumulativo !== 0
          ? (investGrowthVal / Math.abs(past.investimentiCumulativo)) * 100
          : 0;
      hasInvestGrowth = true;
    }
  }

  const header = el('div', { className: 'page-head' }, [
    el('div', {}, [
      el('h1', { text: '📊 Dashboard' }),
      el('p', {
        className: 'muted',
        text: `Storico: ${monthLabelIt(asc[0]!.DateObj)} → ${monthLabelIt(asc[asc.length - 1]!.DateObj)}`,
      }),
    ]),
    el('button', {
      className: 'btn ghost',
      text: '⟳ Aggiorna dati',
      attrs: { type: 'button' },
    }),
  ]);
  (header.lastElementChild as HTMLElement).addEventListener('click', () => {
    ctx.post({ type: 'refreshAll' });
    ctx.toast('info', 'Aggiornamento richiesto.');
  });
  root.append(header);

  // Filters
  const filters = card('🎛️ Filtri', 'I filtri modificano solo la vista, non i dati salvati.');
  const monthSelect = el('select', { className: 'control' });
  for (const option of availableMonths) {
    const opt = el('option', { text: option });
    opt.value = option;
    opt.selected = option === selectedRef;
    monthSelect.append(opt);
  }
  monthSelect.addEventListener('change', () => {
    state.selectedMonth = monthSelect.value;
    ctx.persist();
    ctx.post({ type: 'loadTransactions', monthRef: monthSelect.value });
    ctx.renderMain();
  });

  const windowSelect = el('select', { className: 'control' });
  for (const option of WINDOWS) {
    const opt = el('option', { text: option === 'All' ? 'Tutto lo storico' : `${option} mesi` });
    opt.value = String(option);
    opt.selected = String(option) === String(state.window);
    windowSelect.append(opt);
  }
  windowSelect.addEventListener('change', () => {
    state.window = (windowSelect.value === 'All' ? 'All' : Number(windowSelect.value)) as TimeWindow;
    ctx.persist();
    ctx.renderMain();
  });

  const toggle = (
    label: string,
    checked: boolean,
    onChange: (value: boolean) => void,
  ): HTMLElement => {
    const input = el('input', { attrs: { type: 'checkbox' } }) as HTMLInputElement;
    input.checked = checked;
    input.addEventListener('change', () => onChange(input.checked));
    return el('label', { className: 'toggle' }, [input, el('span', { text: label })]);
  };

  filters.body.append(
    el('div', { className: 'filter-row' }, [
      el('label', { className: 'field' }, [
        el('span', { text: 'Mese selezionato' }),
        monthSelect,
      ]),
      el('label', { className: 'field' }, [
        el('span', { text: 'Orizzonte trend' }),
        windowSelect,
      ]),
      el('div', { className: 'field' }, [
        el('span', { text: 'Spese incluse' }),
        el('div', { className: 'toggle-list' }, [
          toggle('💼 Investimenti', state.filters.investimenti, (value) => {
            state.filters.investimenti = value;
            ctx.persist();
            ctx.renderMain();
          }),
          toggle('🎢 Spese Straordinarie', state.filters.straordinarie, (value) => {
            state.filters.straordinarie = value;
            ctx.persist();
            ctx.renderMain();
          }),
          toggle('🚗 Acquisto Auto (vista)', state.filters.capex, (value) => {
            state.filters.capex = value;
            ctx.persist();
            ctx.renderMain();
          }),
        ]),
      ]),
    ]),
  );
  root.append(filters.section);

  // Top metrics
  const top = card('💎 Patrimonio e investimenti');
  const growthDelta = hasGrowth
    ? `${growthVal >= 0 ? '+' : ''}${fmtEur(growthVal)} (${fmtPct(growthPct)})`
    : 'n/a';
  const investDelta = hasInvestGrowth
    ? `${investGrowthVal >= 0 ? '+' : ''}${fmtEur(investGrowthVal)} (${fmtPct(investGrowthPct)})`
    : 'n/a';
  top.body.append(
    el('div', { className: 'hero-grid' }, [
      metric('🏦 PATRIMONIO TOTALE PROIETTATO', fmtEur(selected.patrimonio), growthDelta, growthVal >= 0 ? 'up' : 'down'),
      metric('📈 TOTALE INVESTITO PROIETTATO', fmtEur(selected.investimentiCumulativo), investDelta, investGrowthVal >= 0 ? 'up' : 'down'),
      el('div', { className: 'side-note' }, [
        el('div', { className: 'metric-label', text: 'Dati al' }),
        el('div', { className: 'side-note-value', text: `${refMonthIt} ${selected.Year}` }),
        el('div', { className: 'metric-caption', text: `Orizzonte ${state.window} mesi` }),
      ]),
    ]),
  );
  root.append(top.section);

  // Run-rate
  const runrateCard = card('⚡ Run-rate & KPI (ultimi 12 mesi)', 'Media, mediana e sparkline delle ultime 12 mensilità.');
  const sparkIncome = el('div', { className: 'spark' });
  const sparkExpense = el('div', { className: 'spark' });
  const sparkSavings = el('div', { className: 'spark' });
  const sparkRate = el('div', { className: 'spark' });
  runrateCard.body.append(
    el('div', { className: 'runrate-grid' }, [
      el('div', { className: 'kpi' }, [
        metric('Media Entrate', fmtEur0(runrate.avgIncome), `Mediana ${fmtEur0(runrate.medianIncome)}`),
        sparkIncome,
      ]),
      el('div', { className: 'kpi' }, [
        metric('Media Uscite', fmtEur0(runrate.avgExpense), `Mediana ${fmtEur0(runrate.medianExpense)}`),
        sparkExpense,
      ]),
      el('div', { className: 'kpi' }, [
        metric('Risparmio Medio', fmtEur0(runrate.avgSavings), `Mediana ${fmtEur0(runrate.medianSavings)}`),
        sparkSavings,
      ]),
      el('div', { className: 'kpi' }, [
        metric('Tasso Risparmio', fmtPct(runrate.savingsRate), `Mediana ${fmtPct(runrate.medianSavingsRate)}`),
        sparkRate,
      ]),
    ]),
  );
  root.append(runrateCard.section);
  charts.sparkline(sparkIncome, runrate.incomeSeries, '#2ecc71');
  charts.sparkline(sparkExpense, runrate.expenseSeries, '#e74c3c');
  charts.sparkline(sparkSavings, runrate.netSeries, '#f1c40f');
  charts.sparkline(sparkRate, runrate.savingsRateSeries, '#3498db');

  // Stats
  const statsCard = card(
    '📊 Statistiche Patrimonio',
    `Statistiche descrittive su tutto lo storico (${stats.nMonths} mesi) — si aggiornano con i filtri spese.`,
  );
  statsCard.body.append(
    el('div', { className: 'stats-columns' }, [
      el('div', {}, [
        el('h3', { text: '💰 Entrate' }),
        distGrid(stats.income, (value) => fmtEur0(value)),
      ]),
      el('div', {}, [
        el('h3', { text: '💸 Uscite (filtrate)' }),
        distGrid(stats.expense, (value) => fmtEur0(value)),
      ]),
    ]),
    el('div', { className: 'stats-columns' }, [
      el('div', {}, [
        el('h3', { text: '🐷 Risparmio mensile netto' }),
        el('div', { className: 'stat-grid' }, [
          metric('Media', fmtEur0(stats.savings.mean)),
          metric('Mediana', fmtEur0(stats.savings.median)),
          metric('Dev. Std', fmtEur0(stats.savings.std)),
          metric('CV (std/media)', stats.savings.cv === null ? 'n/a' : stats.savings.cv.toFixed(2)),
          metric('Mesi positivi', `${Math.round(stats.savings.positiveMonthsPct)}%`),
          metric('Miglior mese', fmtEur0(stats.savings.bestValue), stats.savings.bestMonth, 'up'),
        ]),
        el('p', {
          className: 'muted',
          text: `Miglior mese: ${stats.savings.bestMonth} — Peggiore: ${stats.savings.worstMonth} (${fmtEur0(stats.savings.worstValue)})`,
        }),
      ]),
      el('div', {}, [
        el('h3', { text: '📈 Tasso Risparmio' }),
        distGrid(stats.savingsRate, (value) => fmtPct(value)),
      ]),
    ]),
    el('div', { className: 'stats-columns' }, [
      el('div', {}, [
        el('h3', { text: '🏦 Patrimonio' }),
        el('div', { className: 'stat-grid' }, [
          metric('Iniziale', fmtEur0(stats.patrimonio.initial)),
          metric('Finale', fmtEur0(stats.patrimonio.final)),
          metric('CAGR', stats.patrimonio.cagr === null ? 'n/a' : fmtPct(stats.patrimonio.cagr * 100, 2)),
          metric('Crescita YoY', stats.patrimonio.yoyGrowthPct === null ? 'n/a' : fmtPct(stats.patrimonio.yoyGrowthPct)),
          metric('Accumulo medio annuo', fmtEur0(stats.patrimonio.avgYearlyAccumulation)),
        ]),
        el('p', {
          className: 'muted',
          text: `CAGR = (fin/iniz)^(12/mesi) − 1.${stats.patrimonio.cagrNote ? ` ${stats.patrimonio.cagrNote}.` : ''}`,
        }),
      ]),
      el('div', {}, [
        el('h3', { text: '⏳ Runway' }),
        el('div', { className: 'stat-grid' }, [
          metric(
            'Mesi di copertura',
            stats.runwayMonths === null ? 'n/a' : stats.runwayMonths.toFixed(1),
          ),
        ]),
        el('p', {
          className: 'muted',
          text: 'Runway = (Patrimonio − Totale Investito) / Uscite medie mensili. Se ≤ 0 viene mostrato n/a.',
        }),
      ]),
    ]),
  );
  root.append(statsCard.section);

  // Patrimonio
  const patrimonioCard = card('📈 Evoluzione Patrimonio (con proiezione 12 mesi)');
  const patrimonioDiv = el('div', { className: 'chart' });
  patrimonioCard.body.append(patrimonioDiv);
  root.append(patrimonioCard.section);
  charts.patrimonioChart(patrimonioDiv, asc, forecast.points);

  // Investimenti
  const investCard = card('📈 Andamento Investimenti', 'Cumulativo e flusso mensile.');
  const investDiv = el('div', { className: 'chart' });
  investCard.body.append(investDiv);
  root.append(investCard.section);
  charts.investedCharts(investDiv, asc);

  // Month KPI + gauge
  const monthCard = card('📅 Mese selezionato', `Riferimento: ${refMonthIt} ${selected.Year}`);
  const gaugeDiv = el('div', { className: 'gauge' });
  const expensesOnly = activeExpenseColumns.map((column) => ({
    column,
    value: num(selected, column),
  }));
  const topCategory = [...expensesOnly].sort((a, b) => b.value - a.value)[0];
  const usciteVista = state.filters.capex ? selected.totaleSpeseVista : selected.totaleUscite;
  monthCard.body.append(
    el('div', { className: 'month-grid' }, [
      el('div', { className: 'gauge-wrap' }, [
        gaugeDiv,
        el('div', {
          className: `net-highlight ${selected.redditoMenoSpese > 0 ? 'up' : 'down'}`,
          text: fmtEur(selected.redditoMenoSpese),
        }),
      ]),
      el('div', {}, [
        el('div', { className: 'metric-grid three' }, [
          metric('Entrate Totali', fmtEur(selected.totaleEntrate), 'Incassato', 'up'),
          metric('Uscite Totali', fmtEur(usciteVista), '- Speso', 'down'),
          metric('Spese in conto capitale (capex)', fmtEur(selected.totaleCapex), 'CAPEX', 'flat'),
        ]),
        el('div', { className: 'critical' }, [
          el('h3', { text: '⚠️ Categoria Critica' }),
          el('p', {
            text: topCategory
              ? `${topCategory.column}: ${fmtEur(topCategory.value)}`
              : 'Nessuna spesa nel mese.',
          }),
          el('div', { className: 'progress' }, [
            el('div', {
              className: 'progress-bar',
              attrs: {
                style: `width:${Math.min(
                  topCategory && selected.totaleEntrate ? topCategory.value / selected.totaleEntrate : 0,
                  1,
                ) * 100}%`,
              },
            }),
          ]),
          el('p', { className: 'muted', text: 'Pressione sul Budget' }),
        ]),
      ]),
    ]),
  );
  root.append(monthCard.section);
  charts.gaugeChart(gaugeDiv, selected.risparmioPct);

  // Cash flow
  let trendRows = asc.filter((row) => row.DateObj.getTime() <= selected.DateObj.getTime());
  if (windowMonths !== null) trendRows = trendRows.slice(-windowMonths);
  const cashCard = card('🌊 Flusso di Cassa', `${trendRows.length} mensilità visualizzate.`);
  const cashDiv = el('div', { className: 'chart' });
  cashCard.body.append(cashDiv);
  root.append(cashCard.section);
  charts.cashflowChart(cashDiv, trendRows, selected.DateStr);

  // Waterfall
  const waterfallRows = expensesOnly
    .filter((entry) => entry.value !== 0)
    .sort((a, b) => b.value - a.value);
  const topExpenses = waterfallRows.slice(0, 6);
  const otherExpenses = waterfallRows.slice(6).reduce((sum, entry) => sum + entry.value, 0);
  const wfLabels = ['Entrate'];
  const wfValues = [selected.totaleEntrate];
  const wfMeasures = ['absolute'];
  for (const entry of topExpenses) {
    wfLabels.push(entry.column);
    wfValues.push(-entry.value);
    wfMeasures.push('relative');
  }
  if (otherExpenses > 0) {
    wfLabels.push('Altre spese');
    wfValues.push(-otherExpenses);
    wfMeasures.push('relative');
  }
  wfLabels.push('Risparmio Netto');
  wfValues.push(0);
  wfMeasures.push('total');
  const waterfallCard = card(`🌊 Waterfall — ${refMonthIt} ${selected.Year}`);
  const waterfallDiv = el('div', { className: 'chart' });
  waterfallCard.body.append(waterfallDiv);
  root.append(waterfallCard.section);
  charts.waterfallChart(waterfallDiv, wfLabels, wfValues, wfMeasures);

  // Breakdown + details
  const breakdownCard = card('🍩 Breakdown Spese e dettaglio');
  const donutDiv = el('div', { className: 'chart' });
  const breakdownData = expensesOnly.filter((entry) => entry.value > 0);
  const detailWrap = el('div', { className: 'detail-tabs' });
  const tabButtons = el('div', { className: 'tab-buttons' });
  const monthTab = el('button', { className: 'tab active', text: 'Mese Selezionato', attrs: { type: 'button' } });
  const periodTab = el('button', {
    className: 'tab',
    text: windowMonths === null ? 'Tutto lo storico' : `Periodo (${windowMonths} mesi)`,
    attrs: { type: 'button' },
  });
  const monthPane = el('div', { className: 'tab-pane' });
  const periodPane = el('div', { className: 'tab-pane hidden' });
  tabButtons.append(monthTab, periodTab);
  detailWrap.append(tabButtons, monthPane, periodPane);
  monthTab.addEventListener('click', () => {
    monthTab.classList.add('active');
    periodTab.classList.remove('active');
    monthPane.classList.remove('hidden');
    periodPane.classList.add('hidden');
  });
  periodTab.addEventListener('click', () => {
    periodTab.classList.add('active');
    monthTab.classList.remove('active');
    periodPane.classList.remove('hidden');
    monthPane.classList.add('hidden');
  });

  const nonZeroMonth = expensesOnly
    .filter((entry) => entry.value !== 0)
    .sort((a, b) => b.value - a.value);
  const positiveMonthTotal = expensesOnly
    .filter((entry) => entry.value > 0)
    .reduce((sum, entry) => sum + entry.value, 0);
  monthPane.append(
    el('p', { className: 'muted', text: 'Top 5 Voci' }),
    simpleTable(
      ['Categoria', 'Importo', '%'],
      nonZeroMonth.slice(0, 5).map((entry) => [
        entry.column,
        fmtEur(entry.value),
        positiveMonthTotal > 0 ? fmtPct((entry.value / positiveMonthTotal) * 100) : '0%',
      ]),
    ),
  );
  if (nonZeroMonth.length > 5) {
    const details = el('details', { className: 'expander' }, [
      el('summary', {
        text: nonZeroMonth.some((entry) => entry.value < 0)
          ? '🔍 Altre Spese e Rimborsi'
          : '🔍 Altre Spese',
      }),
    ]);
    details.append(
      simpleTable(
        ['Categoria', 'Importo', '%'],
        nonZeroMonth.slice(5).map((entry) => [
          entry.column,
          fmtEur(entry.value),
          positiveMonthTotal > 0 ? fmtPct((entry.value / positiveMonthTotal) * 100) : '0%',
        ]),
      ),
    );
    monthPane.append(details);
  }

  const periodSums = activeExpenseColumns.map((column) => ({
    column,
    total: trendRows.reduce((sum, row) => sum + num(row, column), 0),
  }));
  const periodMeans = trendRows.length > 0 ? periodSums.map((entry) => entry.total / trendRows.length) : periodSums.map(() => 0);
  const positivePeriodTotal = periodSums.filter((entry) => entry.total > 0).reduce((sum, entry) => sum + entry.total, 0);
  const periodRows = periodSums
    .map((entry, index) => ({ ...entry, mean: periodMeans[index] ?? 0 }))
    .filter((entry) => entry.total !== 0)
    .sort((a, b) => b.total - a.total);
  periodPane.append(
    el('p', { className: 'muted', text: `Analisi su ${trendRows.length} mensilità` }),
    simpleTable(
      ['Categoria', 'Totale', 'Media Mensile', '% Incidenza'],
      periodRows.map((entry) => [
        entry.column,
        fmtEur(entry.total),
        fmtEur(entry.mean),
        positivePeriodTotal > 0 ? fmtPct((entry.total / positivePeriodTotal) * 100) : '0%',
      ]),
    ),
  );
  breakdownCard.body.append(
    el('div', { className: 'breakdown-grid' }, [
      el('div', {}, [el('h3', { text: 'Ripartizione' }), donutDiv]),
      detailWrap,
    ]),
  );
  root.append(breakdownCard.section);
  if (breakdownData.length > 0) {
    charts.donutChart(donutDiv, breakdownData.map((entry) => entry.column), breakdownData.map((entry) => entry.value));
  } else {
    donutDiv.textContent = 'Nessuna spesa positiva nel mese.';
  }

  // Daily transactions
  const monthRef = `${selected.Month} ${selected.Year}`;
  const transactions = state.transactions.filter((row) => row.month_ref === monthRef);
  const txCard = card('🧾 Transazioni Giornaliere', `${transactions.length} transazioni per ${refMonthIt} ${selected.Year}.`);
  if (transactions.length === 0) {
    txCard.body.append(
      el('p', {
        className: 'muted',
        text: 'Nessuna transazione giornaliera per questo mese. Importa un estratto conto in Gestione Mese.',
      }),
    );
    const go = el('button', { className: 'btn', text: 'Vai a Gestione Mese', attrs: { type: 'button' } });
    go.addEventListener('click', () => {
      ctx.state.page = 'month';
      ctx.persist();
      ctx.renderAll();
    });
    txCard.body.append(go);
  } else {
    txCard.body.append(
      simpleTable(
        ['Data', 'Descrizione', 'Categoria', 'Importo'],
        transactions.map((row) => [row.date, row.description, row.category, fmtEur(row.amount)]),
      ),
    );
  }
  root.append(txCard.section);

  // Benchmark
  const benchmarkCard = card('🎯 Benchmark: Spesa Effettiva vs Budget Pianificato');
  const targetColumns = Object.keys(state.targets).filter((column) =>
    activeExpenseColumns.includes(column),
  );
  if (targetColumns.length === 0) {
    benchmarkCard.body.append(
      el('p', {
        className: 'muted',
        text: 'Nessun target salvato. Imposta i target mensili in Gestione Dati.',
      }),
    );
    const go = el('button', { className: 'btn', text: 'Imposta target', attrs: { type: 'button' } });
    go.addEventListener('click', () => {
      ctx.state.page = 'data';
      ctx.persist();
      ctx.renderAll();
    });
    benchmarkCard.body.append(go);
  } else {
    const actual = targetColumns.map((column) => num(selected, column));
    const target = targetColumns.map((column) => Number(state.targets[column] ?? 0));
    const benchDiv = el('div', { className: 'chart' });
    const deltaDiv = el('div', { className: 'chart' });
    benchmarkCard.body.append(
      el('div', { className: 'two-col' }, [
        el('div', {}, [el('p', { className: 'muted', text: 'Effettivo vs Target' }), benchDiv]),
        el('div', {}, [el('p', { className: 'muted', text: 'Scostamento (verde = sotto budget)' }), deltaDiv]),
      ]),
    );
    root.append(benchmarkCard.section);
    charts.benchmarkChart(benchDiv, targetColumns, actual, target, false);
    charts.benchmarkChart(deltaDiv, targetColumns, actual, target, true);
  }
  if (targetColumns.length === 0) root.append(benchmarkCard.section);

  // Savings advanced
  const savingsCard = card('🏆 Analisi Risparmio Avanzata');
  const rateDiv = el('div', { className: 'chart' });
  const bestMonths = [...desc]
    .sort((a, b) => b.risparmioPct - a.risparmioPct)
    .slice(0, 3);
  const best = bestMonths[0];
  const avgExpenses = activeExpenseColumns.map((column) => ({
    column,
    mean: asc.reduce((sum, row) => sum + num(row, column), 0) / asc.length,
  }));
  const drivers =
    best !== undefined
      ? activeExpenseColumns
          .map((column) => {
            const average = avgExpenses.find((entry) => entry.column === column)?.mean ?? 0;
            return { column, diff: num(best, column) - average };
          })
          .sort((a, b) => a.diff - b.diff)
          .slice(0, 3)
      : [];
  const incomeDiff =
    best !== undefined
      ? best.totaleEntrate -
        asc.reduce((sum, row) => sum + row.totaleEntrate, 0) / asc.length
      : 0;

  savingsCard.body.append(
    el('div', { className: 'chart' }, [rateDiv]),
    el('div', { className: 'two-col' }, [
      el('div', {}, [
        el('h3', { text: '🌟 Mesi Migliori' }),
        ...bestMonths.map((row, index) =>
          el('div', { className: 'rank' }, [
            el('div', { className: 'rank-value', text: `#${index + 1} ${fmtPct(row.risparmioPct)}` }),
            el('div', {}, [
              el('div', { text: `${MONTHS_IT[row.DateObj.getMonth()]} ${row.Year}` }),
              el('div', { className: 'muted', text: `Netto: ${fmtEur0(row.redditoMenoSpese)}` }),
            ]),
          ]),
        ),
      ]),
      el('div', {}, [
        el('h3', { text: '🔍 Driver di Successo' }),
        best
          ? el('p', {
              text: `Nel mese migliore (${MONTHS_IT[best.DateObj.getMonth()]} ${best.Year}) hai speso meno della media in:`,
            })
          : el('p', { className: 'muted', text: 'Dati insufficienti.' }),
        ...drivers
          .filter((entry) => entry.diff < 0)
          .map((entry) =>
            el('div', { className: 'driver', text: `• ${entry.column}: ${fmtEur0(entry.diff)} rispetto alla media` }),
          ),
        incomeDiff > 0
          ? el('p', { className: 'good', text: `💰 Inoltre, hai guadagnato ${fmtEur0(incomeDiff)} in più della media.` })
          : null,
      ]),
    ]),
  );
  root.append(savingsCard.section);
  charts.savingsRateChart(
    rateDiv,
    asc.map((row) => `${row.DateStr}-01`),
    asc.map((row) => row.risparmioPct),
  );

  // Net savings
  const netCard = card('💶 Risparmio Netto Mensile', 'Barre mensili e media mobile a 6 mesi.');
  const netDiv = el('div', { className: 'chart' });
  netCard.body.append(netDiv);
  root.append(netCard.section);
  charts.netChart(
    netDiv,
    asc.map((row) => `${row.DateStr}-01`),
    asc.map((row) => row.redditoMenoSpese),
    rollingMean(asc.map((row) => row.redditoMenoSpese), 6),
  );

  // Heatmap
  const heatCard = card('🗓️ Heatmap Spese Mensili (Anno × Mese)');
  const heatDiv = el('div', { className: 'chart' });
  heatCard.body.append(heatDiv);
  root.append(heatCard.section);
  const years = [...new Set(asc.map((row) => row.Year))].sort((a, b) => a - b);
  const matrix = years.map((year) => {
    const rowValues: (number | null)[] = [];
    for (let month = 1; month <= 12; month += 1) {
      const row = asc.find((item) => item.Year === year && item.MonthNum === month);
      rowValues.push(row ? row.totaleUscite : null);
    }
    return rowValues;
  });
  charts.heatmapChart(heatDiv, years.map(String), matrix);

  // Trend categories
  const trendCard = card('📊 Trend Spese per Categoria', 'Top 5 categorie + Altro.');
  const trendDiv = el('div', { className: 'chart' });
  trendCard.body.append(trendDiv);
  root.append(trendCard.section);
  const totals = activeExpenseColumns.map((column) => ({
    column,
    total: asc.reduce((sum, row) => sum + num(row, column), 0),
  }));
  const topColumns = [...totals].sort((a, b) => b.total - a.total).slice(0, 5).map((entry) => entry.column);
  const otherColumns = activeExpenseColumns.filter((column) => !topColumns.includes(column));
  const series = topColumns.map((column) => ({
    name: column,
    values: asc.map((row) => num(row, column)),
  }));
  if (otherColumns.length > 0) {
    series.push({
      name: 'Altro',
      values: asc.map((row) => otherColumns.reduce((sum, column) => sum + num(row, column), 0)),
    });
  }
  charts.trendCategoriesChart(
    trendDiv,
    asc.map((row) => `${row.DateStr}-01`),
    series,
  );

  // YoY
  const yoyCard = card(`🔁 Confronto Anno su Anno — ${refMonthIt}`);
  const yoyDiv = el('div', { className: 'chart' });
  yoyCard.body.append(yoyDiv);
  root.append(yoyCard.section);
  const targetYears = [selected.Year - 2, selected.Year - 1, selected.Year];
  const yoyRows = asc
    .filter((row) => row.Month === selected.Month && targetYears.includes(row.Year))
    .sort((a, b) => a.Year - b.Year);
  charts.yoyChart(
    yoyDiv,
    yoyRows.map((row) => `${row.Month} ${row.Year}`),
    yoyRows.map((row) => row.totaleEntrate),
    yoyRows.map((row) => row.totaleUscite),
    yoyRows.map((row) => row.redditoMenoSpese),
  );
}

function simpleTable(headers: readonly string[], rows: readonly (readonly string[])[]): HTMLElement {
  const table = el('table', { className: 'data-table' });
  const head = el('thead');
  const headRow = el('tr');
  for (const header of headers) headRow.append(el('th', { text: header }));
  head.append(headRow);
  const body = el('tbody');
  for (const row of rows) {
    const tr = el('tr');
    for (const cell of row) tr.append(el('td', { text: cell }));
    body.append(tr);
  }
  table.append(head, body);
  return table;
}

export function selectedDerived(ctx: UiContext): DerivedRow[] {
  const calculated = calculateMetrics(ctx.state.rows);
  const disabled: string[] = [];
  if (!ctx.state.filters.investimenti) disabled.push('Investimenti');
  if (!ctx.state.filters.straordinarie) disabled.push('Spese Straordinarie');
  const filtered = applyOptionalExpenseFilter(
    calculated.rows,
    calculated.expenseColumns,
    disabled,
    ctx.state.filters.capex,
  );
  return prepareTimeseries(filtered.rows).asc;
}

export function formatWindowLabel(window: TimeWindow): string {
  return window === 'All' ? 'tutto lo storico' : `${window} mesi`;
}
