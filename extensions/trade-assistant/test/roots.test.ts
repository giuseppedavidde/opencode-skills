import assert from 'node:assert/strict';
import * as path from 'node:path';
import test from 'node:test';
import { resolveRepoRoot } from '../src/core/roots';

const REPO = path.join(path.sep, 'home', 'u', 'Progetti', 'Github', 'opencode-skills');

function existsFrom(known: string[]) {
  return (target: string): boolean => known.includes(target);
}

test('configured path wins over every other candidate', () => {
  const result = resolveRepoRoot({
    configured: '/custom/repo',
    workspaceFolders: [REPO],
    homeDir: '/home/u',
    extensionRoot: '/home/u/.vscode/extensions/x',
    exists: existsFrom([path.join(REPO, 'agents', 'trade.md'), path.join(REPO, 'skills')]),
  });
  assert.equal(result.source, 'configured');
  assert.equal(result.root, '/custom/repo');
});

test('finds the repo from a nested workspace folder', () => {
  const nested = path.join(REPO, 'extensions', 'trade-assistant');
  const result = resolveRepoRoot({
    workspaceFolders: [nested],
    homeDir: '/home/nobody',
    extensionRoot: '/home/u/.vscode/extensions/x',
    exists: existsFrom([path.join(REPO, 'agents', 'trade.md'), path.join(REPO, 'skills')]),
  });
  assert.equal(result.source, 'workspace');
  assert.equal(result.root, REPO);
});

test('falls back to the home repository when no workspace is open', () => {
  const result = resolveRepoRoot({
    workspaceFolders: [],
    homeDir: '/home/u',
    extensionRoot: '/home/u/.vscode/extensions/x',
    exists: existsFrom([path.join(REPO, 'agents', 'trade.md'), path.join(REPO, 'skills')]),
  });
  assert.equal(result.source, 'home');
  assert.equal(result.root, REPO);
});

test('returns the extension root when nothing matches and reports fallback', () => {
  const result = resolveRepoRoot({
    workspaceFolders: [],
    homeDir: '/home/u',
    extensionRoot: '/home/u/.vscode/extensions/x',
    exists: () => false,
  });
  assert.equal(result.source, 'fallback');
  assert.equal(result.root, path.resolve('/home/u/.vscode/extensions/x'));
});

test('ignores a directory that has trade.md but no skills folder', () => {
  const partial = path.join(path.sep, 'home', 'u', 'partial');
  const result = resolveRepoRoot({
    workspaceFolders: [partial],
    homeDir: '/home/nobody',
    extensionRoot: '/tmp/x',
    exists: existsFrom([path.join(partial, 'agents', 'trade.md')]),
  });
  assert.equal(result.source, 'fallback');
});
