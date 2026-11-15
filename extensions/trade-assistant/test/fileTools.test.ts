import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import test from 'node:test';
import {
  FILE_ROOTS_SETTING,
  FileToolService,
  collectFiles,
  READ_FILE_LINE_CAP,
  expandPath,
  globToRegExp,
  isBlockedPath,
  isWithin,
} from '../src/core/fileTools';

const HOME = path.join(path.sep, 'home', 'u');

test('expandPath expands the home marker', () => {
  assert.equal(expandPath('~/notes.txt', [], HOME), path.join(HOME, 'notes.txt'));
  assert.equal(expandPath('~', [], HOME), HOME);
});

test('expandPath keeps absolute paths and resolves relative ones against an existing base', () => {
  assert.equal(expandPath('/abs/file.txt', [HOME], HOME), path.join(path.sep, 'abs', 'file.txt'));
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-expand-'));
  try {
    fs.mkdirSync(path.join(base, 'docs'));
    fs.writeFileSync(path.join(base, 'docs', 'a.txt'), 'x');
    const resolved = expandPath('docs/a.txt', [path.join(base, 'missing'), base], HOME);
    assert.equal(resolved, path.join(base, 'docs', 'a.txt'));
    const fallback = expandPath('nope.txt', [base], HOME);
    assert.equal(fallback, path.join(base, 'nope.txt'));
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
});

test('isWithin refuses a sibling directory that only shares a prefix', () => {
  assert.equal(isWithin('/a/b', ['/a/b']), true);
  assert.equal(isWithin('/a/b/c', ['/a/b']), true);
  assert.equal(isWithin('/a/bc', ['/a/b']), false);
  assert.equal(isWithin('/a/b', ['/a/c']), false);
});

test('isBlockedPath refuses credentials and key material', () => {
  assert.equal(isBlockedPath(path.join(HOME, '.ssh', 'id_rsa')), true);
  assert.equal(isBlockedPath(path.join(HOME, '.local', 'share', 'opencode', 'auth.json')), true);
  assert.equal(isBlockedPath(path.join(HOME, '.netrc')), true);
  assert.equal(isBlockedPath(path.join(HOME, 'certs', 'server.pem')), true);
  assert.equal(isBlockedPath(path.join(HOME, 'credentials.json')), true);
  assert.equal(isBlockedPath(path.join(HOME, '.aws', 'credentials')), true);
  assert.equal(isBlockedPath(path.join(HOME, 'notes', 'todo.md')), false);
});

test('globToRegExp matches basenames and deep paths', () => {
  assert.equal(globToRegExp('*.md').test('a/b/deep.md'), true);
  assert.equal(globToRegExp('**/*.md').test('deep.md'), true);
  assert.equal(globToRegExp('**/*.md').test('a/b/c.md'), true);
  assert.equal(globToRegExp('src/**/*.ts').test('src/core/fileTools.ts'), true);
  assert.equal(globToRegExp('src/**/*.ts').test('test/fileTools.ts'), false);
});

test('file tools refuse paths outside the configured roots', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-root-'));
  try {
    const service = new FileToolService(() => ({ roots: [root], homeDir: HOME }));
    const outside = await service.call('read_file', { path: path.join(os.tmpdir(), 'somewhere-else.txt') });
    assert.equal(outside.isError, true);
    assert.match(outside.text, new RegExp(FILE_ROOTS_SETTING.replace(/\./g, '\\.')));
    const traversal = await service.call('read_file', { path: path.join(root, '..', 'escape.txt') });
    assert.equal(traversal.isError, true);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('read_file returns numbered lines and caps the output', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-read-'));
  try {
    const file = path.join(root, 'big.txt');
    const rows: string[] = [];
    for (let index = 1; index <= 1000; index += 1) {
      rows.push(`line ${index}`);
    }
    fs.writeFileSync(file, rows.join('\n'));
    const service = new FileToolService(() => ({ roots: [root], homeDir: HOME }));
    const result = await service.call('read_file', { path: 'big.txt' });
    assert.equal(result.isError, false);
    const numbered = result.text.split('\n').filter((line) => /^\d+: /.test(line));
    assert.equal(numbered.length, READ_FILE_LINE_CAP);
    assert.equal(numbered[0], '1: line 1');
    assert.equal(numbered[READ_FILE_LINE_CAP - 1], `${READ_FILE_LINE_CAP}: line ${READ_FILE_LINE_CAP}`);
    assert.match(result.text, /line cap/);
    const range = await service.call('read_file', { path: 'big.txt', startLine: 3, endLine: 4 });
    assert.match(range.text, /^3: line 3$/m);
    assert.match(range.text, /^4: line 4$/m);
    assert.doesNotMatch(range.text, /^5: line 5$/m);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('read_file refuses a blocked path inside an allowed root', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-block-'));
  try {
    const sshDir = path.join(root, '.ssh');
    fs.mkdirSync(sshDir);
    fs.writeFileSync(path.join(sshDir, 'id_rsa'), 'PRIVATE');
    const service = new FileToolService(() => ({ roots: [root], homeDir: HOME }));
    const result = await service.call('read_file', { path: path.join(root, '.ssh', 'id_rsa') });
    assert.equal(result.isError, true);
    assert.match(result.text, /blocked/);
    assert.doesNotMatch(result.text, /PRIVATE/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('read_file refuses binary content', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-bin-'));
  try {
    fs.writeFileSync(path.join(root, 'blob.bin'), Buffer.from([1, 0, 2, 3]));
    const service = new FileToolService(() => ({ roots: [root], homeDir: HOME }));
    const result = await service.call('read_file', { path: 'blob.bin' });
    assert.equal(result.isError, true);
    assert.match(result.text, /binary/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('list_dir, find_files and search_text work inside a root', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-list-'));
  try {
    fs.mkdirSync(path.join(root, 'sub'));
    fs.mkdirSync(path.join(root, 'node_modules'));
    fs.writeFileSync(path.join(root, 'alpha.txt'), 'needle here\nsecond\n');
    fs.writeFileSync(path.join(root, 'sub', 'beta.txt'), 'nothing\nanother needle\n');
    fs.writeFileSync(path.join(root, 'node_modules', 'skip.txt'), 'needle\n');
    const service = new FileToolService(() => ({ roots: [root], homeDir: HOME }));

    const listing = await service.call('list_dir', { path: root });
    assert.equal(listing.isError, false);
    assert.match(listing.text, /dir\tsub/);
    assert.match(listing.text, /file\talpha\.txt \(19 bytes\)/);

    const found = await service.call('find_files', { pattern: '**/*.txt', path: root });
    assert.equal(found.isError, false);
    assert.match(found.text, /alpha\.txt/);
    assert.match(found.text, /beta\.txt/);
    assert.doesNotMatch(found.text, /skip\.txt/);

    const searched = await service.call('search_text', { pattern: 'needle', path: root, glob: '**/*.txt' });
    assert.equal(searched.isError, false);
    assert.match(searched.text, /alpha\.txt:1: needle here/);
    assert.match(searched.text, /beta\.txt:2: another needle/);
    assert.doesNotMatch(searched.text, /skip\.txt/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('file tools refuse every action when no root is configured', async () => {
  const service = new FileToolService(() => ({ roots: [], homeDir: HOME }));
  const result = await service.call('list_dir', { path: HOME });
  assert.equal(result.isError, true);
  assert.match(result.text, new RegExp(FILE_ROOTS_SETTING.replace(/\./g, '\\.')));
  const unknown = await service.call('nope', {});
  assert.equal(unknown.isError, true);
});

test('collectFiles follows symlinked directories and reports no truncation', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'filetools-symlink-'));
  const real = path.join(base, 'real');
  fs.mkdirSync(real, { recursive: true });
  fs.writeFileSync(path.join(real, 'SKILL.md'), '# skill');
  fs.symlinkSync(real, path.join(base, 'linked'), 'dir');
  const walked = collectFiles(base);
  assert.equal(walked.truncated, false);
  assert.ok(walked.files.some((file) => file.endsWith(path.join('linked', 'SKILL.md'))));
  fs.rmSync(base, { recursive: true, force: true });
});

test('collectFiles sets truncated when the entry cap is reached', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'filetools-cap-'));
  for (let index = 0; index < 6; index += 1) {
    fs.writeFileSync(path.join(base, `f${index}.txt`), 'x');
  }
  const walked = collectFiles(base, 3);
  assert.equal(walked.truncated, true);
  assert.ok(walked.files.length < 6);
  fs.rmSync(base, { recursive: true, force: true });
});
