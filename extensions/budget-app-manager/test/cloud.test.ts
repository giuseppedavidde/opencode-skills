import { describe, expect, it } from 'vitest';
import { CloudManager, normalizeSettings } from '../src/cloud';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('CloudManager', () => {
  it('validates configuration without leaking the token', async () => {
    const manager = new CloudManager(
      { token: '', repo: 'owner/repo', branch: 'main', path: 'budget.db', csvPath: 'b.csv' },
      (async () => jsonResponse({})) as typeof fetch,
    );
    const status = await manager.status();
    expect(status.ok).toBe(false);
    expect(status.message).toContain('token');
  });

  it('reports a missing backup with 404', async () => {
    const calls: string[] = [];
    const manager = new CloudManager(
      { token: 'secret-token', repo: 'owner/repo', branch: 'main', path: 'budget.db', csvPath: 'b.csv' },
      (async (url: string | URL | Request) => {
        calls.push(String(url));
        return jsonResponse({ message: 'Not Found' }, 404);
      }) as typeof fetch,
    );
    const status = await manager.status();
    expect(status.ok).toBe(true);
    expect(status.exists).toBe(false);
    expect(calls[0]).toContain('/repos/owner/repo/contents/budget.db');
  });

  it('uploads DB and CSV on backup', async () => {
    const uploads: Array<{ url: string; body: string; auth: string }> = [];
    const fakeFetch = (async (url: string | URL | Request, init?: RequestInit) => {
      const auth = (init?.headers as Record<string, string>)?.['Authorization'] ?? '';
      if (init?.method === 'GET') return jsonResponse({ message: 'Not Found' }, 404);
      uploads.push({ url: String(url), body: String(init?.body ?? ''), auth });
      return jsonResponse({ content: {} });
    }) as typeof fetch;
    const manager = new CloudManager(
      { token: 'secret-token', repo: 'owner/repo', branch: 'main', path: 'budget.db', csvPath: 'b.csv' },
      fakeFetch,
    );
    const result = await manager.backup(Buffer.from('db-bytes'), 'csv,data');
    expect(result.ok).toBe(true);
    expect(uploads).toHaveLength(2);
    expect(uploads[0]?.url).toContain('budget.db');
    expect(uploads[1]?.url).toContain('b.csv');
    expect(uploads[0]?.auth).toBe('Bearer secret-token');
    const dbPayload = JSON.parse(uploads[0]?.body ?? '{}') as { content: string };
    expect(Buffer.from(dbPayload.content, 'base64').toString('utf8')).toBe('db-bytes');
  });

  it('restores a valid SQLite payload and rejects invalid bytes', async () => {
    const sqlite = Buffer.concat([
      Buffer.from('SQLite format 3\u0000', 'utf8'),
      Buffer.alloc(32, 1),
    ]);
    const valid = new CloudManager(
      { token: 't', repo: 'owner/repo', branch: 'main', path: 'budget.db', csvPath: 'b.csv' },
      (async () =>
        jsonResponse({
          sha: 'abc',
          size: sqlite.length,
          content: sqlite.toString('base64'),
          encoding: 'base64',
        })) as typeof fetch,
    );
    const restored = await valid.restore();
    expect(restored.ok).toBe(true);
    expect(restored.bytes?.equals(sqlite)).toBe(true);

    const invalid = new CloudManager(
      { token: 't', repo: 'owner/repo', branch: 'main', path: 'budget.db', csvPath: 'b.csv' },
      (async () =>
        jsonResponse({
          capture: undefined,
          content: Buffer.from('not a database').toString('base64'),
          encoding: 'base64',
        })) as typeof fetch,
    );
    const rejected = await invalid.restore();
    expect(rejected.ok).toBe(false);
    expect(rejected.message).toContain('SQLite');
  });
});

describe('CloudManager.fetchCsv', () => {
  it('downloads the configured CSV path', async () => {
    const calls: string[] = [];
    const manager = new CloudManager(
      {
        token: 'secret-token',
        repo: 'giuseppedavidde/StreamLitPrj',
        branch: 'main',
        path: 'Budget_App/budget.db',
        csvPath: 'Budget_App/budget_database.csv',
      },
      (async (url: string | URL | Request) => {
        calls.push(String(url));
        return jsonResponse({
          sha: 'abc',
          encoding: 'base64',
          content: Buffer.from('Year,MonthNum,Month\n2025,1,January\n', 'utf8').toString('base64'),
        });
      }) as typeof fetch,
    );
    const result = await manager.fetchCsv();
    expect(result.ok).toBe(true);
    expect(result.text).toContain('2025,1,January');
    expect(calls[0]).toContain('/repos/giuseppedavidde/StreamLitPrj/contents/Budget_App/budget_database.csv');
  });

  it('reads the CSV anonymously from the raw URL when no token is set', async () => {
    const calls: Array<{ url: string; auth?: string }> = [];
    const manager = new CloudManager(
      {
        token: '',
        repo: 'giuseppedavidde/StreamLitPrj',
        branch: 'main',
        path: 'Budget_App/budget.db',
        csvPath: 'Budget_App/budget_database.csv',
      },
      (async (url: string | URL | Request, init?: RequestInit) => {
        calls.push({
          url: String(url),
          auth: (init?.headers as Record<string, string>)?.['Authorization'],
        });
        return new Response('Year,MonthNum,Month\n2026,9,September\n', { status: 200 });
      }) as typeof fetch,
    );
    const result = await manager.fetchCsv();
    expect(result.ok).toBe(true);
    expect(result.text).toContain('September');
    expect(calls[0]?.url).toBe(
      'https://raw.githubusercontent.com/giuseppedavidde/StreamLitPrj/main/Budget_App/budget_database.csv',
    );
    expect(calls[0]?.auth).toBeUndefined();
  });

  it('rejects a CSV without a Year header', async () => {
    const manager = new CloudManager(
      { token: 't', repo: 'owner/repo', branch: 'main', path: 'db.sqlite', csvPath: 'x.csv' },
      (async () =>
        jsonResponse({ encoding: 'base64', content: Buffer.from('a,b\n1,2', 'utf8').toString('base64') })) as typeof fetch,
    );
    const result = await manager.fetchCsv();
    expect(result.ok).toBe(false);
    expect(result.message).toContain('header');
  });
});

describe('normalizeSettings', () => {
  it('moves an extra repo segment into the file paths', () => {
    const normalized = normalizeSettings({
      token: '',
      repo: 'giuseppedavidde/StreamLitPrj/Budget_App',
      branch: 'main',
      path: 'budget.db',
      csvPath: 'budget_database.csv',
    });
    expect(normalized.repo).toBe('giuseppedavidde/StreamLitPrj');
    expect(normalized.path).toBe('Budget_App/budget.db');
    expect(normalized.csvPath).toBe('Budget_App/budget_database.csv');
  });

  it('keeps paths that already contain the folder prefix', () => {
    const normalized = normalizeSettings({
      token: '',
      repo: 'giuseppedavidde/StreamLitPrj/Budget_App',
      branch: 'main',
      path: 'Budget_App/budget.db',
      csvPath: 'Budget_App/budget_database.csv',
    });
    expect(normalized.path).toBe('Budget_App/budget.db');
    expect(normalized.csvPath).toBe('Budget_App/budget_database.csv');
  });

  it('leaves owner/name repositories unchanged', () => {
    const normalized = normalizeSettings({
      token: '',
      repo: 'giuseppedavidde/StreamLitPrj',
      branch: 'main',
      path: 'Budget_App/budget.db',
      csvPath: 'Budget_App/budget_database.csv',
    });
    expect(normalized.path).toBe('Budget_App/budget.db');
  });
});
