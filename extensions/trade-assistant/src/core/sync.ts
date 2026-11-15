import * as fs from 'node:fs';
import * as path from 'node:path';

export interface Debouncer {
  trigger(): void;
  cancel(): void;
  readonly pending: boolean;
}

export interface MtimeAdapter {
  readdir(dir: string): string[];
  isDirectory(target: string): boolean;
  mtimeMs(target: string): number;
}

export function createDebouncer(run: () => void, delayMs: number): Debouncer {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const cancel = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
  };
  return {
    trigger(): void {
      cancel();
      timer = setTimeout(() => {
        timer = undefined;
        run();
      }, delayMs);
    },
    cancel,
    get pending(): boolean {
      return timer !== undefined;
    },
  };
}

export function isServerStale(serverProcessStartedAt: number, sourceMtimes: number[]): boolean {
  if (!Number.isFinite(serverProcessStartedAt) || serverProcessStartedAt <= 0) {
    return false;
  }
  return sourceMtimes.some((mtime) => Number.isFinite(mtime) && mtime > serverProcessStartedAt);
}

export function collectSourceMtimes(root: string, adapter: MtimeAdapter, extension = '.py'): number[] {
  const mtimes: number[] = [];
  const walk = (dir: string): void => {
    let entries: string[];
    try {
      entries = adapter.readdir(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.startsWith('.') || entry === '__pycache__') {
        continue;
      }
      const target = path.join(dir, entry);
      let directory = false;
      try {
        directory = adapter.isDirectory(target);
      } catch {
        directory = false;
      }
      if (directory) {
        walk(target);
        continue;
      }
      if (!target.endsWith(extension)) {
        continue;
      }
      try {
        const mtime = adapter.mtimeMs(target);
        if (Number.isFinite(mtime)) {
          mtimes.push(mtime);
        }
      } catch {
        continue;
      }
    }
  };
  walk(root);
  return mtimes;
}

export function newestSourceMtime(root: string, adapter: MtimeAdapter, extension = '.py'): number {
  const mtimes = collectSourceMtimes(root, adapter, extension);
  return mtimes.length === 0 ? 0 : Math.max(...mtimes);
}

export function createNodeMtimeAdapter(): MtimeAdapter {
  return {
    readdir: (dir) => fs.readdirSync(dir),
    isDirectory: (target) => fs.statSync(target).isDirectory(),
    mtimeMs: (target) => fs.statSync(target).mtimeMs,
  };
}
