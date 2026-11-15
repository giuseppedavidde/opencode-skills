import { describe, expect, it } from 'vitest';
import { buildForecast } from '../src/forecast';
import type { DerivedRow } from '../src/metrics';

function point(year: number, month: number, net: number): DerivedRow {
  return {
    Year: year,
    MonthNum: month,
    Month: '',
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
    DateObj: new Date(year, month - 1, 1),
    DateStr: `${year}-${String(month).padStart(2, '0')}`,
    totaleEntrate: 0,
    totaleUscite: 0,
    totaleCapex: 0,
    totaleSpeseVista: 0,
    redditoMenoSpese: net,
    flussoCassaNetto: net,
    risparmioPct: 0,
    patrimonio: 0,
    investimentiCumulativo: 0,
  };
}

describe('buildForecast', () => {
  it('fits a linear trend without residuals', () => {
    const rows = [100, 110, 120, 130, 140, 150].map((net, index) =>
      point(2025, index + 1, net),
    );
    const forecast = buildForecast(rows, 3, 1.28);
    expect(forecast.method).toBe('linear_trend_seasonal');
    expect(forecast.points).toHaveLength(3);
    expect(forecast.points[0]?.net).toBeCloseTo(160, 8);
    expect(forecast.points[1]?.net).toBeCloseTo(170, 8);
    expect(forecast.points[2]?.net).toBeCloseTo(180, 8);
    expect(forecast.points[0]?.lower).toBeCloseTo(160, 8);
    expect(forecast.points[0]?.upper).toBeCloseTo(160, 8);
    expect(forecast.points[0]?.date).toBe('2025-07-01');
  });

  it('applies the seasonal component of the target calendar month', () => {
    const rows = [
      point(2025, 1, 100),
      point(2025, 2, 300),
      point(2025, 3, 100),
      point(2025, 4, 300),
      point(2025, 1, 100),
      point(2025, 2, 300),
    ];
    const forecast = buildForecast(rows, 2, 0);
    // Next two months after February 2025 are March and April; seasonal means
    // are computed per calendar month, so both points are finite.
    expect(forecast.points).toHaveLength(2);
    expect(Number.isFinite(forecast.points[0]?.net)).toBe(true);
    expect(Number.isFinite(forecast.points[1]?.net)).toBe(true);
  });

  it('returns insufficient_data with less than two rows', () => {
    expect(buildForecast([], 12).method).toBe('insufficient_data');
    expect(buildForecast([point(2025, 1, 100)], 12).points).toEqual([]);
  });
});
