import {
  EXPENSE_COLUMNS,
  INCOME_COLUMNS,
  MONTHS_IT,
  type DistributionStats,
  type MonthlyRow,
  type PatrimonioStats,
  type SavingsStats,
  type StatsResult,
} from './types';

export interface DerivedRow extends MonthlyRow {
  DateObj: Date;
  DateStr: string;
  totaleEntrate: number;
  totaleUscite: number;
  totaleCapex: number;
  totaleSpeseVista: number;
  redditoMenoSpese: number;
  flussoCassaNetto: number;
  risparmioPct: number;
  patrimonio: number;
  investimentiCumulativo: number;
}

export function num(row: MonthlyRow, column: string): number {
  const value = (row as unknown as Record<string, unknown>)[column];
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function money(row: MonthlyRow, column: string): number {
  return round2(num(row, column));
}

export function round2(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function dateOf(year: number, month: number): Date {
  return new Date(year, Math.max(0, month - 1), 1);
}

export function monthIndex(row: { Year: number; MonthNum: number }): number {
  return Number(row.Year) * 12 + Number(row.MonthNum);
}

export function monthLabelIt(date: Date): string {
  const month = MONTHS_IT[date.getMonth()] ?? '';
  return `${month} ${date.getFullYear()}`;
}

export function monthLabelItFrom(row: { Year: number; MonthNum: number }): string {
  return monthLabelIt(dateOf(Number(row.Year), Number(row.MonthNum)));
}

export function sortAscending<T extends { Year: number; MonthNum: number }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => monthIndex(a) - monthIndex(b));
}

export function sortDescending<T extends { Year: number; MonthNum: number }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => monthIndex(b) - monthIndex(a));
}

function computeTotals(row: MonthlyRow, expenseColumns: readonly string[]): DerivedRow {
  const income = INCOME_COLUMNS.reduce((sum, col) => sum + num(row, col), 0);
  const expense = expenseColumns.reduce((sum, col) => sum + num(row, col), 0);
  const capex = num(row, 'Acquisto Auto');
  const savings = income - expense;
  return {
    ...row,
    DateObj: dateOf(Number(row.Year), Number(row.MonthNum)),
    DateStr: `${row.Year}-${String(row.MonthNum).padStart(2, '0')}`,
    totaleEntrate: round2(income),
    totaleUscite: round2(expense),
    totaleCapex: round2(capex),
    totaleSpeseVista: round2(expense),
    redditoMenoSpese: round2(savings),
    flussoCassaNetto: round2(savings - capex),
    risparmioPct: income !== 0 ? (savings / income) * 100 : 0,
    patrimonio: 0,
    investimentiCumulativo: 0,
  };
}

export interface CalculatedData {
  rows: DerivedRow[];
  expenseColumns: string[];
  incomeColumns: string[];
}

export function calculateMetrics(rows: MonthlyRow[]): CalculatedData {
  const expenseColumns: string[] = [...EXPENSE_COLUMNS];
  return {
    rows: rows.map((row) => computeTotals(row, expenseColumns)),
    expenseColumns,
    incomeColumns: [...INCOME_COLUMNS],
  };
}

export function applyOptionalExpenseFilter(
  rows: DerivedRow[],
  expenseColumns: readonly string[],
  disabledCategories: readonly string[],
  includeCapexView = false,
): { rows: DerivedRow[]; activeExpenseColumns: string[] } {
  const disabled = new Set(disabledCategories);
  const activeExpenseColumns = expenseColumns.filter((col) => !disabled.has(col));
  const filtered = rows.map((row) => {
    const income = INCOME_COLUMNS.reduce((sum, col) => sum + num(row, col), 0);
    const expense = activeExpenseColumns.reduce((sum, col) => sum + num(row, col), 0);
    const capex = num(row, 'Acquisto Auto');
    const savings = income - expense;
    return {
      ...row,
      totaleEntrate: round2(income),
      totaleUscite: round2(expense),
      totaleCapex: round2(capex),
      totaleSpeseVista: round2(includeCapexView ? expense + capex : expense),
      redditoMenoSpese: round2(savings),
      flussoCassaNetto: round2(savings - capex),
      risparmioPct: income !== 0 ? (savings / income) * 100 : 0,
    } satisfies DerivedRow;
  });
  return { rows: filtered, activeExpenseColumns };
}

export interface Timeseries {
  asc: DerivedRow[];
  desc: DerivedRow[];
}

export function prepareTimeseries(rows: DerivedRow[]): Timeseries {
  const asc = sortAscending(rows).map((row) => ({ ...row }));
  let patrimonio = 0;
  let invested = 0;
  for (const row of asc) {
    patrimonio += row.flussoCassaNetto;
    invested += num(row, 'Investimenti');
    row.patrimonio = round2(patrimonio);
    row.investimentiCumulativo = round2(invested);
    row.DateObj = dateOf(Number(row.Year), Number(row.MonthNum));
  }
  const desc = [...asc].reverse();
  return { asc, desc };
}

export function mean(values: readonly number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid] ?? 0;
  return ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

export function quantile(values: readonly number[], q: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower] ?? 0;
  const weight = position - lower;
  return (sorted[lower] ?? 0) * (1 - weight) + (sorted[upper] ?? 0) * weight;
}

export function sampleStd(values: readonly number[]): number {
  const n = values.length;
  if (n < 2) return 0;
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (n - 1);
  return Math.sqrt(variance);
}

export interface RunrateMetrics {
  avgIncome: number;
  avgExpense: number;
  avgSavings: number;
  savingsRate: number;
  medianIncome: number;
  medianExpense: number;
  medianSavings: number;
  medianSavingsRate: number;
  incomeSeries: number[];
  expenseSeries: number[];
  netSeries: number[];
  savingsRateSeries: number[];
}

export function computeRunrateMetrics(rowsAsc: readonly DerivedRow[], window = 12): RunrateMetrics {
  const tail = rowsAsc.slice(Math.max(0, rowsAsc.length - window));
  if (tail.length === 0) {
    return {
      avgIncome: 0,
      avgExpense: 0,
      avgSavings: 0,
      savingsRate: 0,
      medianIncome: 0,
      medianExpense: 0,
      medianSavings: 0,
      medianSavingsRate: 0,
      incomeSeries: [],
      expenseSeries: [],
      netSeries: [],
      savingsRateSeries: [],
    };
  }
  const incomeSeries = tail.map((row) => row.totaleEntrate);
  const expenseSeries = tail.map((row) => row.totaleUscite);
  const netSeries = tail.map((row) => row.redditoMenoSpese);
  const savingsRateSeries = tail.map((row) => row.risparmioPct);
  const avgIncome = mean(incomeSeries);
  const avgExpense = mean(expenseSeries);
  const avgSavings = avgIncome - avgExpense;
  return {
    avgIncome,
    avgExpense,
    avgSavings,
    savingsRate: avgIncome !== 0 ? (avgSavings / avgIncome) * 100 : 0,
    medianIncome: median(incomeSeries),
    medianExpense: median(expenseSeries),
    medianSavings: median(netSeries),
    medianSavingsRate: median(savingsRateSeries),
    incomeSeries,
    expenseSeries,
    netSeries,
    savingsRateSeries,
  };
}

function distributionStats(values: readonly number[], dates: readonly Date[]): DistributionStats {
  if (values.length === 0) {
    return {
      mean: 0,
      median: 0,
      std: 0,
      min: 0,
      max: 0,
      p25: 0,
      p75: 0,
      minMonth: '',
      maxMonth: '',
    };
  }
  let minIndex = 0;
  let maxIndex = 0;
  for (let i = 1; i < values.length; i += 1) {
    if ((values[i] ?? 0) < (values[minIndex] ?? 0)) minIndex = i;
    if ((values[i] ?? 0) > (values[maxIndex] ?? 0)) maxIndex = i;
  }
  return {
    mean: mean(values),
    median: median(values),
    std: sampleStd(values),
    min: values[minIndex] ?? 0,
    max: values[maxIndex] ?? 0,
    p25: quantile(values, 0.25),
    p75: quantile(values, 0.75),
    minMonth: dates[minIndex] ? monthLabelIt(dates[minIndex] as Date) : '',
    maxMonth: dates[maxIndex] ? monthLabelIt(dates[maxIndex] as Date) : '',
  };
}

function emptyStats(): StatsResult {
  return {
    nMonths: 0,
    income: distributionStats([], []),
    expense: distributionStats([], []),
    savings: {
      mean: 0,
      median: 0,
      std: 0,
      cv: null,
      positiveMonthsPct: 0,
      bestMonth: '',
      bestValue: 0,
      worstMonth: '',
      worstValue: 0,
    },
    savingsRate: distributionStats([], []),
    patrimonio: {
      initial: 0,
      final: 0,
      cagr: null,
      cagrNote: '',
      yoyGrowthPct: null,
      avgYearlyAccumulation: 0,
    },
    runwayMonths: null,
  };
}

export function computeStatMetrics(rowsAsc: readonly DerivedRow[]): StatsResult {
  const rows = rowsAsc;
  const n = rows.length;
  if (n === 0) return emptyStats();

  const dates = rows.map((row) => row.DateObj);
  const income = rows.map((row) => row.totaleEntrate);
  const expense = rows.map((row) => row.totaleUscite);
  const savings = rows.map((row) => row.redditoMenoSpese);
  const rate = rows.map((row) => row.risparmioPct);
  const patrimony = rows.map((row) => row.patrimonio);
  const invested = rows.map((row) => row.investimentiCumulativo);

  const savingsMean = mean(savings);
  const savingsStd = sampleStd(savings);
  let bestIndex = 0;
  let worstIndex = 0;
  for (let i = 1; i < n; i += 1) {
    if ((savings[i] ?? 0) > (savings[bestIndex] ?? 0)) bestIndex = i;
    if ((savings[i] ?? 0) < (savings[worstIndex] ?? 0)) worstIndex = i;
  }
  const savingsStats: SavingsStats = {
    mean: savingsMean,
    median: median(savings),
    std: savingsStd,
    cv: savingsMean !== 0 ? savingsStd / savingsMean : null,
    positiveMonthsPct: (savings.filter((value) => value > 0).length / n) * 100,
    bestMonth: monthLabelIt(dates[bestIndex] as Date),
    bestValue: savings[bestIndex] ?? 0,
    worstMonth: monthLabelIt(dates[worstIndex] as Date),
    worstValue: savings[worstIndex] ?? 0,
  };

  const initial = patrimony[0] ?? 0;
  const final = patrimony[n - 1] ?? 0;
  let cagr: number | null = null;
  let cagrNote = '';
  let effectiveStart = 0;
  if (initial > 0) {
    effectiveStart = 0;
  } else {
    const firstPositive = patrimony.findIndex((value) => value > 0);
    if (firstPositive >= 0) {
      effectiveStart = firstPositive;
      cagrNote = `partenza da ${monthLabelIt(dates[firstPositive] as Date)} (primo mese con patrimonio > 0)`;
    } else {
      effectiveStart = 0;
      cagrNote = 'patrimonio mai positivo nel periodo';
    }
  }
  const effectiveInitial = patrimony[effectiveStart] ?? 0;
  const cagrMonths = n - effectiveStart;
  if (effectiveInitial > 0 && final > 0 && cagrMonths > 0) {
    cagr = (final / effectiveInitial) ** (12 / cagrMonths) - 1;
  }

  let yoy: number | null = null;
  const last = rows[n - 1];
  if (last) {
    const previous = rows.find(
      (row) => row.Year === last.Year - 1 && row.Month === last.Month,
    );
    if (previous && previous.patrimonio !== 0) {
      yoy = ((final - previous.patrimonio) / Math.abs(previous.patrimonio)) * 100;
    }
  }

  const years = n / 12;
  const patrimonioStats: PatrimonioStats = {
    initial,
    final,
    cagr,
    cagrNote,
    yoyGrowthPct: yoy,
    avgYearlyAccumulation: years > 0 ? final / years : 0,
  };

  const avgExpense = mean(expense);
  const liquid = final - (invested[n - 1] ?? 0);
  let runway: number | null = null;
  if (avgExpense > 0) {
    runway = liquid / avgExpense;
    if (runway <= 0) runway = null;
  }

  return {
    nMonths: n,
    income: distributionStats(income, dates),
    expense: distributionStats(expense, dates),
    savings: savingsStats,
    savingsRate: distributionStats(rate, dates),
    patrimonio: patrimonioStats,
    runwayMonths: runway === null ? null : Math.round(runway * 10) / 10,
  };
}

export function rollingMean(values: readonly number[], window: number): number[] {
  const result: number[] = [];
  for (let i = 0; i < values.length; i += 1) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    result.push(mean(slice));
  }
  return result;
}

export function availableMonthRefs(rows: readonly MonthlyRow[]): string[] {
  return sortDescending(rows).map((row) => `${row.Month} ${row.Year}`);
}
