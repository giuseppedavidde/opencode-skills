import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { MtimeAdapter } from '../src/core/sync';
import { collectSourceMtimes, createDebouncer, isServerStale, newestSourceMtime } from '../src/core/sync';

test('debouncer coalesces a burst into one run', async () => {
  let runs = 0;
  const debouncer = createDebouncer(() => {
    runs += 1;
  }, 40);
  debouncer.trigger();
  debouncer.trigger();
  debouncer.trigger();
  assert.equal(debouncer.pending, true);
  await new Promise((resolve) => setTimeout(resolve, 120));
  assert.equal(runs, 1);
  assert.equal(debouncer.pending, false);
  debouncer.trigger();
  await new Promise((resolve) => setTimeout(resolve, 90));
  assert.equal(runs, 2);
});

test('cancel drops a pending run', async () => {
  let runs = 0;
  const debouncer = createDebouncer(() => {
    runs += 1;
  }, 40);
  debouncer.trigger();
  debouncer.cancel();
  await new Promise((resolve) => setTimeout(resolve, 90));
  assert.equal(runs, 0);
  assert.equal(debouncer.pending, false);
});

test('a server is stale only when a source file is newer than the process start', () => {
  assert.equal(isServerStale(2000, [1500, 1900]), false);
  assert.equal(isServerStale(2000, [2001]), true);
  assert.equal(isServerStale(2000, [1500, 2500]), true);
  assert.equal(isServerStale(2000, []), false);
  assert.equal(isServerStale(0, [2500]), false);
  assert.equal(isServerStale(Number.NaN, [2500]), false);
  assert.equal(isServerStale(2000, [Number.NaN]), false);
});

const ROOT = '/repo/mcp/src';

function memoryMtimeAdapter(tree: Record<string, string[]>, mtimes: Record<string, number>): MtimeAdapter {
  const directories = new Set<string>([ROOT]);
  for (const [dir, entries] of Object.entries(tree)) {
    for (const entry of entries) {
      if (!entry.includes('.')) {
        directories.add(`${dir}/${entry}`);
      }
    }
  }
  return {
    readdir: (dir) => tree[dir] ?? [],
    isDirectory: (target) => directories.has(target),
    mtimeMs: (target) => {
      const value = mtimes[target];
      if (value === undefined) {
        throw new Error(`ENOENT ${target}`);
      }
      return value;
    },
  };
}

test('collects the newest python mtime and ignores caches', () => {
  const adapter = memoryMtimeAdapter(
    {
      [ROOT]: ['trading_mcp', '__pycache__', 'notes.txt'],
      [`${ROOT}/trading_mcp`]: ['main.py', 'serve.py', 'old.pyc'],
    },
    {
      [`${ROOT}/trading_mcp/main.py`]: 1200,
      [`${ROOT}/trading_mcp/serve.py`]: 3400,
      [`${ROOT}/trading_mcp/old.pyc`]: 9000,
    }
  );
  assert.deepEqual(collectSourceMtimes(ROOT, adapter).sort((a, b) => a - b), [1200, 3400]);
  assert.equal(newestSourceMtime(ROOT, adapter), 3400);
  assert.equal(newestSourceMtime('/repo/missing', adapter), 0);
});
