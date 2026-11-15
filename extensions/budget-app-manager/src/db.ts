import { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import initSqlJs, { type BindParams, type Database } from 'sql.js';
import {
  BUDGET_COLUMNS,
  type DbInfo,
  type MerchantEntry,
  type MonthlyKey,
  type MonthlyRow,
  type TransactionRecord,
} from './types';
import { normalizeMerchant } from './importer/merchant';
import { cleanAmount } from './importer/classify';
import { parseCsvTable, toCsv } from './importer/csv';

const MONEY_COLUMNS = BUDGET_COLUMNS.filter(
  (column) => column !== 'Year' && column !== 'MonthNum' && column !== 'Month',
);

function quote(identifier: string): string {
  return `"${identifier.replace(/"/g, '""')}"`;
}

const MONTHLY_COLUMNS_SQL = BUDGET_COLUMNS.map((column) => quote(column)).join(', ');

const SCHEMA_MONTHLY = `
CREATE TABLE IF NOT EXISTS monthly_budget (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  "Year" INTEGER,
  "MonthNum" INTEGER,
  "Month" TEXT,
${MONEY_COLUMNS.map((column) => `  ${quote(column)} REAL DEFAULT 0.0`).join(',\n')},
  UNIQUE("Year", "MonthNum")
);
`;

const SCHEMA_TRANSACTIONS = `
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  description TEXT,
  amount REAL NOT NULL,
  category TEXT,
  source TEXT,
  imported_at TEXT DEFAULT (datetime('now')),
  month_ref TEXT
);
`;

const SCHEMA_TARGETS = `
CREATE TABLE IF NOT EXISTS budget_targets (
  category TEXT PRIMARY KEY,
  monthly_target REAL NOT NULL DEFAULT 0.0
);
`;

const SCHEMA_MERCHANTS = `
CREATE TABLE IF NOT EXISTS merchant_categories (
  merchant_normalized TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'llm',
  confidence REAL DEFAULT 0.8,
  times_seen INTEGER DEFAULT 1,
  first_seen TEXT,
  last_seen TEXT
);
`;

export interface DbOpenOptions {
  dbPath: string;
  seedPath: string;
  wasmPath: string;
}

type SqlRow = Record<string, unknown>;

export class BudgetDb {
  private db: Database;
  private readonly options: DbOpenOptions;
  private readonly sql: Awaited<ReturnType<typeof initSqlJs>>;

  private constructor(
    db: Database,
    options: DbOpenOptions,
    sql: Awaited<ReturnType<typeof initSqlJs>>,
  ) {
    this.db = db;
    this.options = options;
    this.sql = sql;
  }

  static async open(options: DbOpenOptions): Promise<BudgetDb> {
    mkdirSync(dirname(options.dbPath), { recursive: true });
    const SQL = await initSqlJs({ locateFile: () => options.wasmPath });
    let database: Database;
    if (existsSync(options.dbPath)) {
      try {
        database = new SQL.Database(readFileSync(options.dbPath));
      } catch {
        const corrupt = `${options.dbPath}.corrupt-${Date.now()}`;
        try {
          copyFileSync(options.dbPath, corrupt);
        } catch {
          // ignore
        }
        database = new SQL.Database();
      }
    } else {
      database = new SQL.Database();
    }
    const instance = new BudgetDb(database, options, SQL);
    instance.initSchema();
    instance.seedMerchantsFromJson(options.seedPath);
    instance.persist();
    return instance;
  }

  get dbPath(): string {
    return this.options.dbPath;
  }

  get exportPath(): string {
    return `${this.options.dbPath}.sqlite-export`;
  }

  private initSchema(): void {
    this.db.run(SCHEMA_MONTHLY);
    this.db.run(SCHEMA_TRANSACTIONS);
    this.db.run(SCHEMA_TARGETS);
    this.db.run(SCHEMA_MERCHANTS);
    this.ensureMonthlyColumns();
  }

  private ensureMonthlyColumns(): void {
    const existing = new Set(
      this.all<{ name: string }>('PRAGMA table_info(monthly_budget)').map((row) =>
        String(row.name),
      ),
    );
    for (const column of BUDGET_COLUMNS) {
      if (!existing.has(column)) {
        this.db.run(`ALTER TABLE monthly_budget ADD COLUMN ${quote(column)} REAL DEFAULT 0.0`);
      }
    }
  }

  private all<T extends SqlRow>(sql: string, params: BindParams = []): T[] {
    const statement = this.db.prepare(sql);
    try {
      statement.bind(params);
      const rows: T[] = [];
      while (statement.step()) {
        rows.push(statement.getAsObject() as T);
      }
      return rows;
    } finally {
      statement.free();
    }
  }

  private run(sql: string, params: BindParams = []): void {
    this.db.run(sql, params);
  }

  private backup(): void {
    if (existsSync(this.options.dbPath)) {
      try {
        copyFileSync(this.options.dbPath, `${this.options.dbPath}.bak`);
      } catch {
        // A failed backup must not block the write; the next one will retry.
      }
    }
  }

  private persist(): void {
    const bytes = this.db.export();
    const target = this.options.dbPath;
    const temp = `${target}.tmp`;
    writeFileSync(temp, bytes);
    try {
      renameSync(temp, target);
    } catch {
      try {
        unlinkSync(target);
      } catch {
        // ignore
      }
      renameSync(temp, target);
    }
  }

  private transactional(action: () => void): void {
    this.db.run('BEGIN');
    try {
      action();
      this.db.run('COMMIT');
    } catch (error) {
      try {
        this.db.run('ROLLBACK');
      } catch {
        // ignore
      }
      throw error;
    }
  }

  loadData(): MonthlyRow[] {
    const rows = this.all<SqlRow>(
      `SELECT ${MONTHLY_COLUMNS_SQL} FROM monthly_budget ORDER BY "Year" DESC, "MonthNum" DESC`,
    );
    return rows.map((row) => this.mapMonthly(row));
  }

  private mapMonthly(row: SqlRow): MonthlyRow {
    const mapped = {
      Year: Number(row.Year ?? 0),
      MonthNum: Number(row.MonthNum ?? 0),
      Month: String(row.Month ?? ''),
    } as unknown as MonthlyRow;
    const bag = mapped as unknown as Record<string, number>;
    for (const column of MONEY_COLUMNS) {
      bag[column] = Number(row[column] ?? 0) || 0;
    }
    return mapped;
  }

  saveData(rows: readonly MonthlyRow[], deleted: readonly MonthlyKey[] = []): void {
    this.backup();
    this.transactional(() => {
      for (const key of deleted) {
        this.run('DELETE FROM monthly_budget WHERE "Year" = ? AND "MonthNum" = ?', [
          Number(key.Year) || 0,
          Number(key.MonthNum) || 0,
        ]);
      }
      const placeholders = BUDGET_COLUMNS.map(() => '?').join(', ');
      const updates = BUDGET_COLUMNS.filter(
        (column) => column !== 'Year' && column !== 'MonthNum',
      )
        .map((column) => `${quote(column)} = excluded.${quote(column)}`)
        .join(', ');
      const sql = `INSERT INTO monthly_budget (${MONTHLY_COLUMNS_SQL}) VALUES (${placeholders})
        ON CONFLICT("Year", "MonthNum") DO UPDATE SET ${updates}`;
      for (const row of rows) {
        const params: (string | number | null)[] = BUDGET_COLUMNS.map((column) => {
          if (column === 'Month') return String(row.Month ?? '');
          if (column === 'Year' || column === 'MonthNum') return Number(row[column]) || 0;
          return Number(row[column]) || 0;
        });
        this.run(sql, params);
      }
    });
    this.persist();
  }

  exportToCsv(filePath: string): void {
    const rows = this.loadData();
    const data = rows.map((row) =>
      BUDGET_COLUMNS.map((column) => {
        if (column === 'Month') return row.Month;
        return Number(row[column]) || 0;
      }),
    );
    writeFileSync(filePath, toCsv(BUDGET_COLUMNS, data), 'utf8');
  }

  migrateFromCsv(csvPath: string, force = false): number {
    if (!existsSync(csvPath)) return 0;
    const count = this.count('monthly_budget');
    if (count > 0 && !force) return 0;
    const table = parseCsvTable(readFileSync(csvPath));
    if (table.records.length === 0) return 0;
    const present = BUDGET_COLUMNS.filter((column) => table.headers.includes(column));
    if (present.length === 0) return 0;

    this.backup();
    this.transactional(() => {
      if (force) this.run('DELETE FROM monthly_budget');
      for (const record of table.records) {
        const row = {} as Record<string, string | number>;
        for (const column of BUDGET_COLUMNS) {
          const raw = record[column] ?? '';
          if (column === 'Year' || column === 'MonthNum') row[column] = Number(raw) || 0;
          else if (column === 'Month') row[column] = raw;
          else row[column] = cleanAmount(raw);
        }
        const params = BUDGET_COLUMNS.map((column) => row[column] ?? (column === 'Month' ? '' : 0));
        this.run(
          `INSERT OR REPLACE INTO monthly_budget (${MONTHLY_COLUMNS_SQL}) VALUES (${BUDGET_COLUMNS.map(() => '?').join(', ')})`,
          params,
        );
      }
    });
    this.persist();
    return table.records.length;
  }

  saveTransactions(records: readonly TransactionRecord[]): number {
    const rows = records.map((record) => [
      String(record.date ?? ''),
      String(record.description ?? ''),
      Number(record.amount) || 0,
      record.category ?? '',
      record.source ?? 'bank_import',
      record.month_ref ?? '',
    ]);
    this.backup();
    this.transactional(() => {
      this.run('DELETE FROM transactions');
      const sql =
        'INSERT INTO transactions (date, description, amount, category, source, month_ref) VALUES (?, ?, ?, ?, ?, ?)';
      for (const params of rows) this.run(sql, params);
    });
    this.persist();
    return rows.length;
  }

  loadTransactions(monthRef?: string): TransactionRecord[] {
    const rows = monthRef
      ? this.all<SqlRow>(
          'SELECT id, date, description, amount, category, source, imported_at, month_ref FROM transactions WHERE month_ref = ? ORDER BY "date"',
          [monthRef],
        )
      : this.all<SqlRow>(
          'SELECT id, date, description, amount, category, source, imported_at, month_ref FROM transactions ORDER BY "date"',
        );
    return rows.map((row) => ({
      id: Number(row.id ?? 0),
      date: String(row.date ?? ''),
      description: String(row.description ?? ''),
      amount: Number(row.amount ?? 0),
      category: String(row.category ?? ''),
      source: String(row.source ?? ''),
      imported_at: row.imported_at ? String(row.imported_at) : undefined,
      month_ref: String(row.month_ref ?? ''),
    }));
  }

  getBudgetTargets(): Record<string, number> {
    try {
      const rows = this.all<SqlRow>('SELECT category, monthly_target FROM budget_targets');
      const result: Record<string, number> = {};
      for (const row of rows) {
        result[String(row.category)] = Number(row.monthly_target ?? 0);
      }
      return result;
    } catch {
      return {};
    }
  }

  saveBudgetTargets(targets: Record<string, number>): void {
    this.backup();
    this.transactional(() => {
      this.run('DELETE FROM budget_targets');
      for (const [category, value] of Object.entries(targets)) {
        this.run(
          'INSERT OR REPLACE INTO budget_targets (category, monthly_target) VALUES (?, ?)',
          [category, Number(value) || 0],
        );
      }
    });
    this.persist();
  }

  getMerchantMap(): Record<string, MerchantEntry> {
    try {
      const rows = this.all<SqlRow>(
        'SELECT merchant_normalized, category, source, confidence, times_seen, first_seen, last_seen FROM merchant_categories',
      );
      const result: Record<string, MerchantEntry> = {};
      for (const row of rows) {
        const merchant = String(row.merchant_normalized ?? '');
        result[merchant] = {
          merchant,
          category: String(row.category ?? ''),
          source: String(row.source ?? 'llm'),
          confidence: Number(row.confidence ?? 0.8),
          times_seen: Number(row.times_seen ?? 1),
          first_seen: row.first_seen ? String(row.first_seen) : null,
          last_seen: row.last_seen ? String(row.last_seen) : null,
        };
      }
      return result;
    } catch {
      return {};
    }
  }

  getMerchantList(): MerchantEntry[] {
    return Object.values(this.getMerchantMap()).sort((a, b) =>
      a.merchant.localeCompare(b.merchant),
    );
  }

  getMerchantCount(): number {
    return this.count('merchant_categories');
  }

  upsertMerchant(
    merchant: string,
    category: string,
    source = 'llm',
    confidence = 0.7,
    persist = true,
  ): boolean {
    const key = normalizeMerchant(merchant);
    if (!key) return false;
    const now = nowIso();
    try {
      this.transactional(() => {
        const existing = this.all<SqlRow>(
          'SELECT source FROM merchant_categories WHERE merchant_normalized = ?',
          [key],
        );
        if (existing[0] && String(existing[0].source) === 'manual') {
          throw new ManualGuard();
        }
        this.run(
          `INSERT INTO merchant_categories
             (merchant_normalized, category, source, confidence, times_seen, first_seen, last_seen)
           VALUES (?, ?, ?, ?, 1, ?, ?)
           ON CONFLICT(merchant_normalized) DO UPDATE SET
             category = excluded.category,
             source = excluded.source,
             confidence = excluded.confidence,
             times_seen = merchant_categories.times_seen + 1,
             last_seen = excluded.last_seen
           WHERE merchant_categories.source != 'manual'`,
          [key, String(category), source, Number(confidence) || 0.7, now, now],
        );
      });
    } catch (error) {
      if (error instanceof ManualGuard) return false;
      throw error;
    }
    if (persist) this.persist();
    return true;
  }

  persistNow(): void {
    this.persist();
  }

  setMerchantManual(merchant: string, category: string): boolean {
    const key = normalizeMerchant(merchant);
    if (!key) return false;
    const now = nowIso();
    this.run(
      `INSERT INTO merchant_categories
         (merchant_normalized, category, source, confidence, times_seen, first_seen, last_seen)
       VALUES (?, ?, 'manual', 1.0, 1, ?, ?)
       ON CONFLICT(merchant_normalized) DO UPDATE SET
         category = excluded.category,
         source = 'manual',
         confidence = 1.0,
         times_seen = merchant_categories.times_seen + 1,
         last_seen = excluded.last_seen`,
      [key, String(category), now, now],
    );
    this.persist();
    return true;
  }

  deleteMerchant(merchant: string): boolean {
    const key = normalizeMerchant(merchant);
    if (!key) return false;
    this.run('DELETE FROM merchant_categories WHERE merchant_normalized = ?', [key]);
    const changed = this.db.getRowsModified() > 0;
    if (changed) this.persist();
    return changed;
  }

  seedMerchantsFromJson(path: string): number {
    if (!existsSync(path)) return 0;
    if (this.getMerchantCount() > 0) return 0;
    let data: unknown;
    try {
      data = JSON.parse(readFileSync(path, 'utf8')) as unknown;
    } catch {
      return 0;
    }
    if (!Array.isArray(data)) return 0;
    this.backup();
    const now = nowIso();
    let inserted = 0;
    for (const entry of data) {
      if (!entry || typeof entry !== 'object') continue;
      const record = entry as Record<string, unknown>;
      const merchant = normalizeMerchant(String(record.merchant ?? ''));
      const category = String(record.category ?? '');
      const source = String(record.source ?? 'seeded');
      const confidence = Number(record.confidence ?? 0.6);
      if (!merchant || !category) continue;
      this.run(
        `INSERT OR IGNORE INTO merchant_categories
           (merchant_normalized, category, source, confidence, times_seen, first_seen, last_seen)
         VALUES (?, ?, ?, ?, 1, ?, ?)`,
        [merchant, category, source, confidence || 0.6, now, now],
      );
      inserted += 1;
    }
    if (inserted > 0) this.persist();
    return inserted;
  }

  getDbInfo(): DbInfo {
    let size = 0;
    if (existsSync(this.options.dbPath)) {
      try {
        size = statSync(this.options.dbPath).size / 1024;
      } catch {
        size = 0;
      }
    }
    let backupTime: string | null = null;
    const backup = `${this.options.dbPath}.bak`;
    if (existsSync(backup)) {
      try {
        backupTime = formatLocalDateTime(statSync(backup).mtime);
      } catch {
        backupTime = null;
      }
    }
    return {
      dbPath: this.options.dbPath,
      dbSizeKb: size,
      rowCount: this.count('monthly_budget'),
      lastBackupTime: backupTime,
      transactionCount: this.count('transactions'),
      merchantCount: this.count('merchant_categories'),
    };
  }

  private count(table: string): number {
    try {
      const rows = this.all<SqlRow>(`SELECT COUNT(*) AS total FROM ${table}`);
      return Number(rows[0]?.total ?? 0);
    } catch {
      return 0;
    }
  }

  readBytes(): Buffer {
    if (existsSync(this.options.dbPath)) {
      return readFileSync(this.options.dbPath);
    }
    return Buffer.from(this.db.export());
  }

  restoreFromBytes(bytes: Buffer | Uint8Array): void {
    this.backup();
    const next = new this.sql.Database(new Uint8Array(bytes));
    this.db.close();
    this.db = next;
    this.initSchema();
    this.persist();
  }

  close(): void {
    this.db.close();
  }
}

class ManualGuard extends Error {
  constructor() {
    super('manual');
  }
}

export function nowIso(): string {
  const now = new Date();
  const pad = (value: number): string => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function formatLocalDateTime(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
