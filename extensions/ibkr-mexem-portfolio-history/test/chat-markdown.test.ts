import assert from 'node:assert/strict';
import test from 'node:test';
import { escapeHtml, renderMarkdown } from '../src/chat/markdown.ts';

test('a script tag from the model is escaped and never becomes an element', () => {
  const html = renderMarkdown('<script>alert(1)</script>');
  assert.equal(html.includes('<script'), false, 'no raw script tag may survive');
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;\/script&gt;/);
});

test('an image tag with an inline handler is escaped', () => {
  const html = renderMarkdown('<img src=x onerror="alert(1)">');
  assert.equal(html.includes('<img'), false);
  assert.match(html, /onerror=&quot;/);
});

test('bold, italic and inline code survive the escaping pass', () => {
  const html = renderMarkdown('**total** and *risk* and `pnl`');
  assert.match(html, /<strong>total<\/strong>/);
  assert.match(html, /<em>risk<\/em>/);
  assert.match(html, /<code>pnl<\/code>/);
});

test('a fenced block becomes a pre/code block with escaped content', () => {
  const html = renderMarkdown('```csv\na,b\n<c>\n```');
  assert.match(html, /<pre><code class="language-csv">/);
  assert.match(html, /&lt;c&gt;/);
  assert.equal(html.includes('<c>'), false);
});

test('unordered and ordered lists render as lists', () => {
  const unordered = renderMarkdown('- one\n- two');
  assert.match(unordered, /<ul><li>one<\/li><li>two<\/li><\/ul>/);
  const ordered = renderMarkdown('1. first\n2. second');
  assert.match(ordered, /<ol><li>first<\/li><li>second<\/li><\/ol>/);
});

test('a pipe table renders a header and body', () => {
  const html = renderMarkdown('| Symbol | P&L |\n| --- | --- |\n| AMD | 10.00 |');
  assert.match(html, /<table><thead><tr><th>Symbol<\/th><th>P&amp;L<\/th><\/tr><\/thead>/);
  assert.match(html, /<tbody><tr><td>AMD<\/td><td>10.00<\/td><\/tr><\/tbody>/);
});

test('markdown syntax inside inline code is not applied', () => {
  const html = renderMarkdown('`**not bold**`');
  assert.match(html, /<code>\*\*not bold\*\*<\/code>/);
  assert.equal(html.includes('<strong>'), false);
});

test('escapeHtml covers the five dangerous characters', () => {
  assert.equal(escapeHtml(`<>&"'`), '&lt;&gt;&amp;&quot;&#39;');
});

test('plain text with a newline becomes one paragraph', () => {
  const html = renderMarkdown('line one\nline two');
  assert.equal(html, '<p>line one line two</p>');
});

test('an empty answer produces an empty render', () => {
  assert.equal(renderMarkdown(''), '');
});
