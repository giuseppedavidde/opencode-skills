const API = 'https://api.github.com';

export interface CloudSettings {
  token: string;
  repo: string;
  branch: string;
  path: string;
  csvPath: string;
}

export interface CloudResult {
  ok: boolean;
  message: string;
  exists?: boolean;
  sha?: string;
  size?: number;
}

interface GitHubContentResponse {
  sha?: string;
  size?: number;
  content?: string;
  encoding?: string;
  message?: string;
}

export function normalizeSettings(settings: CloudSettings): CloudSettings {
  const parts = settings.repo
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean);
  const repo = parts.slice(0, 2).join('/');
  const repoPrefix = parts.slice(2).join('/');
  const rebase = (value: string): string => {
    const clean = value.trim().replace(/^\/+/, '');
    if (!repoPrefix) return clean;
    if (!clean) return repoPrefix;
    return clean.startsWith(`${repoPrefix}/`) ? clean : `${repoPrefix}/${clean}`;
  };
  return {
    ...settings,
    repo,
    path: rebase(settings.path),
    csvPath: rebase(settings.csvPath),
  };
}

export class CloudManager {
  private readonly settings: CloudSettings;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(settings: CloudSettings, fetchImpl: typeof fetch = fetch, timeoutMs = 60_000) {
    this.settings = normalizeSettings(settings);
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  private validateCommon(): string | null {
    if (!/^[\w.-]+\/[\w.-]+$/.test(this.settings.repo)) {
      return 'Repository non valido: usa il formato owner/name.';
    }
    if (!this.settings.branch) return 'Branch mancante.';
    for (const path of [this.settings.path, this.settings.csvPath]) {
      if (!path || path.startsWith('/') || path.includes('..')) {
        return 'Percorso file non valido.';
      }
    }
    return null;
  }

  private validate(): string | null {
    if (!this.settings.token) return 'GitHub token mancante.';
    return this.validateCommon();
  }

  private rawUrl(path: string): string {
    const encoded = path
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/');
    return `https://raw.githubusercontent.com/${this.settings.repo}/${this.settings.branch}/${encoded}`;
  }

  private headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.settings.token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      'User-Agent': 'budget-app-manager',
    };
  }

  private async request(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await this.fetchImpl(url, { ...init, signal: controller.signal });
    } catch (error) {
      const message = (error as Error).name === 'AbortError' ? 'timeout' : (error as Error).message;
      throw new Error(`GitHub: ${message}`);
    } finally {
      clearTimeout(timer);
    }
  }

  private contentUrl(path: string): string {
    const encoded = path
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/');
    return `${API}/repos/${this.settings.repo}/contents/${encoded}?ref=${encodeURIComponent(this.settings.branch)}`;
  }

  async status(): Promise<CloudResult> {
    const invalid = this.validate();
    if (invalid) return { ok: false, message: invalid };
    try {
      const response = await this.request(this.contentUrl(this.settings.path), {
        method: 'GET',
        headers: this.headers(),
      });
      if (response.status === 404) {
        return { ok: true, exists: false, message: 'Nessun backup remoto trovato.' };
      }
      const body = (await response.json()) as GitHubContentResponse;
      if (!response.ok) {
        return { ok: false, message: `GitHub HTTP ${response.status}: ${body.message ?? ''}` };
      }
      return {
        ok: true,
        exists: true,
        sha: body.sha,
        size: body.size,
        message: `Backup remoto presente (${body.size ?? 0} byte).`,
      };
    } catch (error) {
      return { ok: false, message: (error as Error).message };
    }
  }

  async backup(dbBytes: Buffer, csvText: string): Promise<CloudResult> {
    const invalid = this.validate();
    if (invalid) return { ok: false, message: invalid };
    if (dbBytes.byteLength > 90 * 1024 * 1024) {
      return { ok: false, message: 'Database troppo grande per la Contents API (limite 90 MB).' };
    }
    const stamp = new Date().toISOString();
    const dbResult = await this.upload(this.settings.path, dbBytes, `Budget DB backup ${stamp}`);
    if (!dbResult.ok) return dbResult;
    const csvResult = await this.upload(
      this.settings.csvPath,
      Buffer.from(csvText, 'utf8'),
      `Budget CSV backup ${stamp}`,
    );
    if (!csvResult.ok) {
      return { ok: false, message: `Database caricato, CSV fallito: ${csvResult.message}` };
    }
    return { ok: true, message: `Backup completato su ${this.settings.repo}@${this.settings.branch}.` };
  }

  private async upload(path: string, content: Buffer, message: string): Promise<CloudResult> {
    try {
      let sha: string | undefined;
      const head = await this.request(this.contentUrl(path), {
        method: 'GET',
        headers: this.headers(),
      });
      if (head.ok) {
        const body = (await head.json()) as GitHubContentResponse;
        sha = body.sha;
      } else if (head.status !== 404) {
        const body = (await head.json().catch(() => ({}))) as GitHubContentResponse;
        return { ok: false, message: `GitHub HTTP ${head.status}: ${body.message ?? ''}` };
      }
      const response = await this.request(
        `${API}/repos/${this.settings.repo}/contents/${path
          .split('/')
          .map((segment) => encodeURIComponent(segment))
          .join('/')}`,
        {
          method: 'PUT',
          headers: this.headers(),
          body: JSON.stringify({
            message,
            content: content.toString('base64'),
            branch: this.settings.branch,
            ...(sha ? { sha } : {}),
          }),
        },
      );
      const body = (await response.json().catch(() => ({}))) as GitHubContentResponse;
      if (!response.ok) {
        return { ok: false, message: `GitHub HTTP ${response.status}: ${body.message ?? ''}` };
      }
      return { ok: true, message: 'File caricato.' };
    } catch (error) {
      return { ok: false, message: (error as Error).message };
    }
  }

  async fetchCsv(): Promise<CloudResult & { text?: string }> {
    const invalid = this.validateCommon();
    if (invalid) return { ok: false, message: invalid };
    try {
      let text: string;
      let sha: string | undefined;
      if (this.settings.token) {
        const response = await this.request(this.contentUrl(this.settings.csvPath), {
          method: 'GET',
          headers: this.headers(),
        });
        const body = (await response.json().catch(() => ({}))) as GitHubContentResponse;
        if (response.status === 404) {
          return { ok: false, message: `CSV non trovato: ${this.settings.csvPath}.` };
        }
        if (!response.ok) {
          return { ok: false, message: `GitHub HTTP ${response.status}: ${body.message ?? ''}` };
        }
        if (!body.content) return { ok: false, message: 'Il CSV remoto è vuoto.' };
        const decoded =
          body.encoding === 'base64'
            ? Buffer.from(body.content.replace(/\s/g, ''), 'base64').toString('utf8')
            : body.content;
        text = decoded.replace(/^\uFEFF/, '');
        sha = body.sha;
      } else {
        const response = await this.request(this.rawUrl(this.settings.csvPath), {
          method: 'GET',
          headers: { 'User-Agent': 'budget-app-manager' },
        });
        if (response.status === 404) {
          return { ok: false, message: `CSV non trovato: ${this.settings.csvPath}.` };
        }
        if (!response.ok) {
          return { ok: false, message: `GitHub HTTP ${response.status} (accesso anonimo).` };
        }
        text = (await response.text()).replace(/^\uFEFF/, '');
      }
      if (!text.trim()) return { ok: false, message: 'Il CSV remoto è vuoto.' };
      if (!/year/i.test(text.split(/\r?\n/)[0] ?? '')) {
        return { ok: false, message: 'Il CSV remoto non ha un header valido (Year).' };
      }
      return { ok: true, message: `CSV scaricato (${text.length} byte).`, text, sha };
    } catch (error) {
      return { ok: false, message: (error as Error).message };
    }
  }

  async restore(): Promise<CloudResult & { bytes?: Buffer }> {
    const invalid = this.validate();
    if (invalid) return { ok: false, message: invalid };
    try {
      const response = await this.request(this.contentUrl(this.settings.path), {
        method: 'GET',
        headers: this.headers(),
      });
      const body = (await response.json().catch(() => ({}))) as GitHubContentResponse;
      if (!response.ok) {
        return { ok: false, message: `GitHub HTTP ${response.status}: ${body.message ?? ''}` };
      }
      if (!body.content) return { ok: false, message: 'Il file remoto non contiene dati.' };
      if (body.encoding && body.encoding !== 'base64') {
        return { ok: false, message: `Encoding non supportato: ${body.encoding}.` };
      }
      const bytes = Buffer.from(body.content.replace(/\s/g, ''), 'base64');
      if (bytes.length < 16 || bytes.subarray(0, 15).toString('utf8') !== 'SQLite format 3') {
        return { ok: false, message: 'Il file remoto non è un database SQLite valido.' };
      }
      return { ok: true, message: 'Backup scaricato.', bytes, sha: body.sha, size: body.size };
    } catch (error) {
      return { ok: false, message: (error as Error).message };
    }
  }
}
