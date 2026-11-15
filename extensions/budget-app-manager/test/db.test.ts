import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { BudgetDb } from '../src/db';
import type { MonthlyRow } from '../src/types';

const wasmPath = resolve('node_modules/sql.js/dist/sql-wasm.wasm');
const tempDirs: string[] = [];

function tempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'budget-db-test-'));
  tempDirs.push(dir);
  return dir;
}

function row(year: number, monthNum: number, month: string): MonthlyRow {
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
  };
}

async function openDb(dir: string, name = 'budget.db'): Promise<BudgetDb> {
  const seedPath = join(dir, 'merchant_seed.json');
  if (!existsSync(seedPath)) {
    writeFileSync(
      seedPath,
      JSON.stringify([
        { merchant: 'BILLA', category: 'Alimentari', source: 'seeded', confidence: 0.9 },
      ]),
    );
  }
  return BudgetDb.open({ dbPath: join(dir, name), seedPath, wasmPath });
}

afterEach(() => {
  while (tempDirs.length > 0) {
    const dir = tempDirs.pop();
    if (dir) rmSync(dir, { recursive: true, force: true });
  }
});

describe('BudgetDb', () => {
  it('creates the schema, seeds merchants and persists rows', async () => {
    const dir = tempDir();
    const db = await openDb(dir);
    expect(db.getMerchantCount()).toBe(1);

    const january = row(2025, 1, 'January');
    january.Stipendio = 3000;
    january.Alimentari = 200;
    const february = row(2025, 2, 'February');
    february.Stipendio = 3100;
    db.saveData([january, february]);

    const rows = db.loadData();
    expect(rows).toHaveLength(2);
    expect(rows[0]?.Month).toBe('February');
    expect(rows[1]?.Stipendio).toBe(3000);
    expect(existsSync(join(dir, 'budget.db.bak'))).toBe(true);

    january.Alimentari = 250;
    db.saveData([january]);
    expect(db.loadData().find((item) => item.MonthNum === 1)?.Alimentari).toBe(250);

    db.saveData([january], [{ Year: 2025, MonthNum: 2 }]);
    expect(db.loadData()).toHaveLength(1);
    db.close();
  });

  it('stores targets and transactions', async () => {
    const dir = tempDir();
    const db = await openDb(dir);
    db.saveBudgetTargets({ Alimentari: 300, Trasporti: 50 });
    expect(db.getBudgetTargets()).toEqual({ Alimentari: 300, Trasporti: 50 });

    db.saveTransactions([
      {
        date: '2025-01-10',
        description: 'BILLA',
        amount: -25,
        category: 'Alimentari',
        source: 'bank_import',
        month_ref: 'January 2025',
      },
      {
        date: '2025-02-10',
        description: 'ÖBB',
        amount: -20,
        category: 'Trasporti',
        source: 'bank_import',
        month_ref: 'February 2025',
      },
    ]);
    expect(db.loadTransactions('January 2025')).toHaveLength(1);
    expect(db.loadTransactions()).toHaveLength(2);
    db.close();
  });

  it('never overwrites manual merchant corrections', async () => {
    const dir = tempDir();
    const db = await openDb(dir);
    expect(db.setMerchantManual('BILLA', 'Spese Straordinarie')).toBe(true);
    expect(db.upsertMerchant('BILLA', 'Alimentari', 'llm')).toBe(false);
    const entry = db.getMerchantMap()['billa'];
    expect(entry?.category).toBe('Spese Straordinarie');
    expect(entry?.source).toBe('manual');
    expect(entry?.times_seen).toBe(2);

    expect(db.upsertMerchant('HOFER', 'Alimentari', 'llm')).toBe(true);
    expect(db.getMerchantMap()['hofer']?.source).toBe('llm');
    expect(db.deleteMerchant('HOFER')).toBe(true);
    expect(db.getMerchantMap()['hofer']).toBeUndefined();
    db.close();
  });

  it('exports CSV and migrates it into a fresh database', async () => {
    const dir = tempDir();
    const db = await openDb(dir);
    const january = row(2025, 1, 'January');
    january.Stipendio = 3000;
    january.Alimentari = 123.45;
    db.saveData([january]);
    const csvPath = join(dir, 'budget_database.csv');
    db.exportToCsv(csvPath);
    expect(readFileSync(csvPath, 'utf8')).toContain('2025,1,January');

    const db2 = await openDb(dir, 'copy.db');
    expect(db2.migrateFromCsv(csvPath)).toBe(1);
    expect(db2.loadData()[0]?.Alimentari).toBe(123.45);
    db.close();
    db2.close();
  });

  it('restores from exported bytes', async () => {
    const dir = tempDir();
    const db = await openDb(dir);
    db.saveData([row(2025, 1, 'January')]);
    const bytes = db.readBytes();
    db.saveData([row(2025, 2, 'February')]);
    expect(db.loadData()).toHaveLength(2);
    db.restoreFromBytes(bytes);
    expect(db.loadData()).toHaveLength(1);
    expect(db.loadData()[0]?.Month).toBe('January');
    db.close();
  });
});
