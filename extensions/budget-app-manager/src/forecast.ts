import type { ForecastPoint, ForecastResult } from './types';
import { sampleStd } from './metrics';

export interface ForecastInputRow {
  DateObj: Date;
  redditoMenoSpese: number;
}

export function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

export function formatIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function buildForecast(
  rowsAsc: readonly ForecastInputRow[],
  months = 12,
  ciZ = 1.28,
): ForecastResult {
  const series = rowsAsc.map((row) => Number(row.redditoMenoSpese) || 0);
  const n = series.length;
  if (n < 2) {
    return { method: 'insufficient_data', ciLevel: 0.8, points: [] };
  }

  const t = series.map((_, index) => index);
  const meanT = t.reduce((a, b) => a + b, 0) / n;
  const meanY = series.reduce((a, b) => a + b, 0) / n;
  let covariance = 0;
  let varianceT = 0;
  for (let i = 0; i < n; i += 1) {
    const dt = (t[i] ?? 0) - meanT;
    covariance += dt * ((series[i] ?? 0) - meanY);
    varianceT += dt * dt;
  }
  const slope = varianceT > 0 ? covariance / varianceT : 0;
  const intercept = meanY - slope * meanT;
  const trend = t.map((value) => slope * value + intercept);
  const residuals = series.map((value, index) => value - (trend[index] ?? 0));

  const seasonal = new Array<number>(13).fill(0);
  const counts = new Array<number>(13).fill(0);
  for (let i = 0; i < n; i += 1) {
    const month = rowsAsc[i]?.DateObj.getMonth();
    if (month === undefined || Number.isNaN(month)) continue;
    const index = month + 1;
    seasonal[index] = (seasonal[index] ?? 0) + (residuals[i] ?? 0);
    counts[index] = (counts[index] ?? 0) + 1;
  }
  for (let m = 1; m <= 12; m += 1) {
    const count = counts[m] ?? 0;
    if (count > 0) seasonal[m] = (seasonal[m] ?? 0) / count;
  }

  const fitted = series.map((_, index) => {
    const month = rowsAsc[index]?.DateObj.getMonth();
    const season = month === undefined || Number.isNaN(month) ? 0 : seasonal[month + 1] ?? 0;
    return (trend[index] ?? 0) + season;
  });
  const fullResiduals = series.map((value, index) => value - (fitted[index] ?? 0));
  const residualStd = n > 2 ? sampleStd(fullResiduals) : 0;

  const lastDate = rowsAsc[n - 1]?.DateObj ?? new Date();
  const points: ForecastPoint[] = [];
  for (let h = 1; h <= months; h += 1) {
    const futureDate = addMonths(lastDate, h);
    const futureMonth = futureDate.getMonth() + 1;
    const prediction =
      slope * (n + h - 1) + intercept + (seasonal[futureMonth] ?? 0);
    const band = ciZ * residualStd;
    points.push({
      date: formatIsoDate(futureDate),
      net: prediction,
      lower: prediction - band,
      upper: prediction + band,
    });
  }

  return { method: 'linear_trend_seasonal', ciLevel: 0.8, points };
}
