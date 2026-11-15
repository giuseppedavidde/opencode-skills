import { describe, expect, it } from 'vitest';
import {
  applyOptionalExpenseFilter,
  calculateMetrics,
  computeRunrateMetrics,
  computeStatMetrics,
  prepareTimeseries,
  type DerivedRow,
} from '../src/metrics';
import type { MonthlyRow } from '../src/types';

function row(
  year: number,
  monthNum: number,
  month: string,
  overrides: Partial<MonthlyRow> = {},
): MonthlyRow {
  return {
    Year: year,
    MonthNum: monthNum,
    Month: month,
    Stipendio: 0,
    'Reddito aggiuntivo': 0,
    Alimentari: 0,
    Bancomat: 0,
    Carburante: 0,
    'Cene, Pranzo': 0,
    'Immobili (affitto, mutuo, tasse, assicurazione)': 0,
    Investimenti: 0,
    Medicinali: 0,
    'PayPal + Abbonamenti': 0,
    'Spese Straordinarie': 0,
    'Acquisto Auto': 0,
    Trasporti: 0,
    'Viaggi, Divertimento': 0,
    ...overrides,
  };
}

const rows: MonthlyRow[] = [
  row(2025, 1, 'January', { Stipendio: 3000, Alimentari: 300, Investimenti: 500 }),
  row(2025, 2, 'February', {
    Stipendio: 3000,
    Alimentari: 400,
    Investimenti: 500,
    'Acquisto Auto': 2000,
  }),
  row(2025, 3, 'March', { Stipendio: 3500, Alimentari: 200 }),
];

function series(): DerivedRow[] {
  const calculated = calculateMetrics(rows);
  const filtered = applyOptionalExpenseFilter(
    calculated.rows,
    calculated.expenseColumns,
    [],
    false,
  );
  return prepareTimeseries(filtered.rows).asc;
}

describe('calculateMetrics / prepareTimeseries', () => {
  it('computes totals, capex and net cash flow', () => {
    const asc = series();
    expect(asc).toHaveLength(3);
    expect(asc[0]?.totaleEntrate).toBe(3000);
    expect(asc[0]?.totaleUscite).toBe(800);
    expect(asc[0]?.redditoMenoSpese).toBe(2200);
    expect(asc[1]?.totaleCapex).toBe(2000);
    expect(asc[1]?.flussoCassaNetto).toBe(100);
    expect(asc[1]?.patrimonio).toBe(2300);
    expect(asc[2]?.patrimonio).toBe(5600);
    expect(asc[2]?.investimentiCumulativo).toBe(1000);
  });

  it('keeps capex out of recurring expenses but inside net worth', () => {
    const asc = series();
    expect(asc[1]?.totaleUscite).toBe(900);
    expect(asc[1]?.totaleSpeseVista).toBe(900);
    expect(asc[1]?.patrimonio).toBe(2300);
  });

  it('recalculates totals with optional expense filters', () => {
    const calculated = calculateMetrics(rows);
    const filtered = applyOptionalExpenseFilter(
      calculated.rows,
      calculated.expenseColumns,
      ['Investimenti'],
      true,
    );
    const asc = prepareTimeseries(filtered.rows).asc;
    expect(filtered.activeExpenseColumns).not.toContain('Investimenti');
    expect(asc[0]?.totaleUscite).toBe(300);
    expect(asc[0]?.patrimonio).toBe(2700);
    expect(asc[1]?.flussoCassaNetto).toBe(600);
    expect(asc[1]?.totaleSpeseVista).toBe(2400);
  });

  it('sorts descending for the UI', () => {
    const calculated = calculateMetrics(rows);
    const desc = prepareTimeseries(calculated.rows).desc;
    expect(desc[0]?.Month).toBe('March');
    expect(desc[2]?.Month).toBe('January');
  });
});

describe('computeRunrateMetrics', () => {
  it('computes mean, median and savings rate', () => {
    const runrate = computeRunrateMetrics(series(), 12);
    expect(runrate.avgIncome).toBeCloseTo(3166.6667, 3);
    expect(runrate.avgExpense).toBeCloseTo(633.3333, 3);
    expect(runrate.avgSavings).toBeCloseTo(2533.3333, 3);
    expect(runrate.savingsRate).toBeCloseTo(80, 3);
    expect(runrate.medianIncome).toBe(3000);
    expect(runrate.medianExpense).toBe(800);
    expect(runrate.medianSavings).toBe(2200);
    expect(runrate.incomeSeries).toEqual([3000, 3000, 3500]);
  });

  it('uses only the requested window', () => {
    const runrate = computeRunrateMetrics(series(), 1);
    expect(runrate.avgIncome).toBe(3500);
    expect(runrate.avgExpense).toBe(200);
  });
});

describe('computeStatMetrics', () => {
  it('computes distributions and patrimonio metrics', () => {
    const stats = computeStatMetrics(series());
    expect(stats.nMonths).toBe(3);
    expect(stats.income.mean).toBeCloseTo(3166.6667, 3);
    expect(stats.income.min).toBe(3000);
    expect(stats.income.max).toBe(3500);
    expect(stats.income.minMonth).toBe('Gennaio 2025');
    expect(stats.income.maxMonth).toBe('Marzo 2025');
    expect(stats.expense.max).toBe(900);
    expect(stats.savings.bestMonth).toBe('Marzo 2025');
    expect(stats.savings.worstMonth).toBe('Febbraio 2025');
    expect(stats.savings.positiveMonthsPct).toBe(100);
    expect(stats.patrimonio.initial).toBe(2200);
    expect(stats.patrimonio.final).toBe(5600);
    expect(stats.patrimonio.cagr).toBeCloseTo((5600 / 2200) ** 4 - 1, 6);
    expect(stats.patrimonio.avgYearlyAccumulation).toBeCloseTo(22400, 6);
    expect(stats.runwayMonths).toBeCloseTo(7.3, 1);
    expect(stats.patrimonio.yoyGrowthPct).toBeNull();
  });

  it('returns empty stats for no rows', () => {
    const stats = computeStatMetrics([]);
    expect(stats.nMonths).toBe(0);
    expect(stats.runwayMonths).toBeNull();
  });

  it('computes YoY when the previous year is present', () => {
    const withPrevious = [
      row(2024, 3, 'March', { Stipendio: 1000 }),
      row(2025, 3, 'March', { Stipendio: 2000 }),
    ];
    const calculated = calculateMetrics(withPrevious);
    const asc = prepareTimeseries(calculated.rows).asc;
    const stats = computeStatMetrics(asc);
    expect(stats.patrimonio.yoyGrowthPct).toBeCloseTo(200, 6);
  });
});
