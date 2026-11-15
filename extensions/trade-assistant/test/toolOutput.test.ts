import assert from 'node:assert/strict';
import test from 'node:test';
import { compressToolOutput } from '../src/core/toolOutput';

test('short output passes through unchanged', () => {
  const text = 'line one\nline two';
  assert.equal(compressToolOutput(text), text);
});

test('long lines are cut and counted', () => {
  const long = 'x'.repeat(900);
  const result = compressToolOutput(long, { maxLineChars: 100 });
  assert.ok(result.startsWith('x'.repeat(100)));
  assert.match(result, /\+800 chars/);
});

test('a huge multi-line payload keeps the head and the tail', () => {
  const rows = Array.from({ length: 4000 }, (_, index) => `row-${index}`);
  const result = compressToolOutput(rows.join('\n'), { maxChars: 1000 });
  assert.ok(result.length < 1400, `length ${result.length}`);
  assert.ok(result.startsWith('row-0'));
  assert.ok(result.trimEnd().endsWith('row-3999'));
  assert.match(result, /characters omitted/);
});

test('a single huge line with no newlines is truncated, not lost', () => {
  const result = compressToolOutput('y'.repeat(50_000), { maxChars: 500, maxLineChars: 5000 });
  assert.ok(result.length <= 1500);
  assert.ok(result.includes('y'));
});

test('carriage returns are normalized', () => {
  assert.equal(compressToolOutput('a\r\nb', {}), 'a\nb');
});
