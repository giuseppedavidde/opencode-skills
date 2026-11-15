import { describe, expect, it } from 'vitest';
import { findMonthRow, monthNumberOf } from '../src/webview-ui/manageMonth';

const rows = [
  { Year: 2026, MonthNum: 9, Month: 'September' },
  { Year: 2026, MonthNum: 10, Month: 'October' },
];

describe('monthNumberOf', () => {
  it('maps full and short English names', () => {
    expect(monthNumberOf('October')).toBe(10);
    expect(monthNumberOf('oct')).toBe(10);
    expect(monthNumberOf('  March ')).toBe(3);
    expect(monthNumberOf('nope')).toBe(0);
  });
});

describe('findMonthRow', () => {
  it('finds a month by name', () => {
    expect(findMonthRow(rows, 2026, 'October')?.MonthNum).toBe(10);
  });

  it('finds a month by number even when the name differs', () => {
    const drifted = [{ Year: 2026, MonthNum: 10, Month: 'Okt' }];
    expect(findMonthRow(drifted, 2026, 'October')?.MonthNum).toBe(10);
  });

  it('accepts string years from the database', () => {
    const stringy = [{ Year: '2026' as unknown as number, MonthNum: 10, Month: 'October' }];
    expect(findMonthRow(stringy, 2026, 'october')).toBeDefined();
  });

  it('returns undefined for a missing month', () => {
    expect(findMonthRow(rows, 2026, 'November')).toBeUndefined();
    expect(findMonthRow(rows, 2025, 'October')).toBeUndefined();
  });
});
