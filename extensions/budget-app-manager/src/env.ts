import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

interface CacheEntry {
  mtimeMs: number;
  values: Record<string, string>;
}

export class DotEnv {
  private readonly roots: string[];
  private readonly cache = new Map<string, CacheEntry>();

  constructor(roots: readonly string[]) {
    this.roots = [...new Set(roots.filter(Boolean))];
  }

  get(name: string): string | undefined {
    for (const root of this.roots) {
      const values = this.read(join(root, '.env'));
      if (values[name]) return values[name];
    }
    return undefined;
  }

  private read(file: string): Record<string, string> {
    if (!existsSync(file)) return {};
    try {
      const mtimeMs = statSync(file).mtimeMs;
      const cached = this.cache.get(file);
      if (cached && cached.mtimeMs === mtimeMs) return cached.values;
      const values = parseDotEnv(readFileSync(file, 'utf8'));
      this.cache.set(file, { mtimeMs, values });
      return values;
    } catch {
      return {};
    }
  }
}

export function parseDotEnv(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!match) continue;
    const key = match[1] ?? '';
    let value = (match[2] ?? '').trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}
