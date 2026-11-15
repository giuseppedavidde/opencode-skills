/**
 * Minimal markdown renderer for model output.
 *
 * Security rule: the whole input is escaped before any tag is produced, so the
 * model can never inject HTML. No DOM access and no `vscode`, so `node:test`
 * covers the rendered string.
 */

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const PLACEHOLDER = '\u0000';

function placeholder(index: number): string {
  return `${PLACEHOLDER}${index}${PLACEHOLDER}`;
}

/** True for a line that is exactly one placeholder token. */
function isPlaceholderOnly(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length < 3 || !trimmed.startsWith(PLACEHOLDER) || !trimmed.endsWith(PLACEHOLDER)) {
    return false;
  }
  const inner = trimmed.slice(1, -1);
  return inner.length > 0 && !/\D/.test(inner);
}

function renderTableRow(line: string): string[] {
  const body = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return body.split('|').map((cell) => cell.trim());
}

function isSeparatorRow(line: string): boolean {
  const cells = renderTableRow(line);
  if (cells.length === 0) {
    return false;
  }
  return cells.every((cell) => /^:?-{2,}:?$/.test(cell));
}

function inline(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/(^|[\s(])_([^_\n]+)_(?=[\s.,!?;:)]|$)/g, '$1<em>$2</em>');
}

function renderBlocks(escaped: string): string {
  const lines = escaped.split('\n');
  const out: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';

    if (line.trim().length === 0) {
      index += 1;
      continue;
    }

    if (line.trim().startsWith('|') && isSeparatorRow(lines[index + 1] ?? '')) {
      const header = renderTableRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && (lines[index] ?? '').trim().startsWith('|')) {
        rows.push(renderTableRow(lines[index] ?? ''));
        index += 1;
      }
      const head = `<thead><tr>${header.map((cell) => `<th>${inline(cell)}</th>`).join('')}</tr></thead>`;
      const body = rows
        .map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`)
        .join('');
      out.push(`<table>${head}<tbody>${body}</tbody></table>`);
      continue;
    }

    const unordered = /^\s*[-*+]\s+(.*)$/.exec(line);
    if (unordered) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^\s*[-*+]\s+(.*)$/.exec(lines[index] ?? '');
        if (!match) {
          break;
        }
        items.push(`<li>${inline(match[1] ?? '')}</li>`);
        index += 1;
      }
      out.push(`<ul>${items.join('')}</ul>`);
      continue;
    }

    const ordered = /^\s*\d+\.\s+(.*)$/.exec(line);
    if (ordered) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = /^\s*\d+\.\s+(.*)$/.exec(lines[index] ?? '');
        if (!match) {
          break;
        }
        items.push(`<li>${inline(match[1] ?? '')}</li>`);
        index += 1;
      }
      out.push(`<ol>${items.join('')}</ol>`);
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? '';
      if (current.trim().length === 0) {
        break;
      }
      if (current.trim().startsWith('|') && isSeparatorRow(lines[index + 1] ?? '')) {
        break;
      }
      if (/^\s*[-*+]\s+/.test(current) || /^\s*\d+\.\s+/.test(current)) {
        break;
      }
      paragraph.push(current);
      index += 1;
    }
    const joined = paragraph.join(' ');
    // A fenced code block that arrived on its own line stays a block element.
    if (paragraph.length === 1 && isPlaceholderOnly(joined)) {
      out.push(joined);
      continue;
    }
    out.push(`<p>${inline(joined)}</p>`);
  }

  return out.join('\n');
}

/**
 * Escape, then apply a small markdown subset: fenced code, inline code, bold,
 * italic, unordered and ordered lists, simple pipe tables.
 */
export function renderMarkdown(markdown: string): string {
  const source = markdown.replace(/\r\n/g, '\n');
  const codes: string[] = [];
  const segments: { code: boolean; text: string }[] = [];
  const fence = /```([^\n`]*)\n?([\s\S]*?)(?:```|$)/g;
  let cursor = 0;
  let match = fence.exec(source);
  while (match !== null) {
    if (match.index > cursor) {
      segments.push({ code: false, text: source.slice(cursor, match.index) });
    }
    const language = (match[1] ?? '').trim().toLowerCase();
    const safeLanguage = /^[a-z0-9+#._-]*$/.test(language) ? language : '';
    const body = escapeHtml(match[2] ?? '');
    codes.push(safeLanguage ? `<pre><code class="language-${safeLanguage}">${body}</code></pre>` : `<pre><code>${body}</code></pre>`);
    segments.push({ code: true, text: placeholder(codes.length - 1) });
    cursor = match.index + match[0].length;
    match = fence.exec(source);
  }
  if (cursor < source.length) {
    segments.push({ code: false, text: source.slice(cursor) });
  }

  let html = '';
  for (const segment of segments) {
    if (segment.code) {
      html += `\n\n${segment.text}\n\n`;
      continue;
    }
    const escaped = escapeHtml(segment.text);
    const withInlineCode = escaped.replace(/`([^`\n]+)`/g, (_all: string, code: string) => {
      codes.push(`<code>${code}</code>`);
      return placeholder(codes.length - 1);
    });
    html += `\n\n${renderBlocks(withInlineCode)}\n\n`;
  }

  let result = html.trim();
  for (let index = 0; index < codes.length; index += 1) {
    result = result.split(placeholder(index)).join(codes[index] ?? '');
  }
  return result;
}
