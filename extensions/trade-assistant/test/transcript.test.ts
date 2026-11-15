import assert from 'node:assert/strict';
import * as path from 'node:path';
import { test } from 'node:test';
import type { TranscriptFs, TranscriptRecord } from '../src/core/transcript';
import {
  appendRecord,
  createRecord,
  deleteSession,
  exportSession,
  listSessions,
  newSessionId,
  parseTranscript,
  readSession,
  sanitizeSessionId,
  sessionFilePath,
  summaryOf,
} from '../src/core/transcript';

function memoryFs(): TranscriptFs & { files: Map<string, string> } {
  const files = new Map<string, string>();
  return {
    files,
    ensureDir: () => undefined,
    append: (file, text) => {
      files.set(file, `${files.get(file) ?? ''}${text}`);
    },
    read: (file) => {
      const value = files.get(file);
      if (value === undefined) {
        throw new Error(`ENOENT ${file}`);
      }
      return value;
    },
    exists: (file) => files.has(file),
    listFiles: (dir) =>
      [...files.keys()].filter((file) => path.dirname(file) === dir).map((file) => path.basename(file)),
    remove: (file) => {
      files.delete(file);
    },
  };
}

const DIR = path.join('/storage', 'chat');

function sampleRecords(sessionId: string): TranscriptRecord[] {
  const start = new Date('2026-11-14T10:00:00.000Z');
  return [
    createRecord('session_meta', sessionId, { meta: { source: 'test' } }, start),
    createRecord('user', sessionId, { text: 'Analyze ENI.MI and show the option chain' }, new Date('2026-11-14T10:00:01.000Z')),
    createRecord('assistant', sessionId, { text: 'I will fetch the quote first.' }, new Date('2026-11-14T10:00:02.000Z')),
    createRecord(
      'tool_call',
      sessionId,
      { name: 'fetch_stock_data', callId: 'call-1', args: { ticker: 'ENI.MI' } },
      new Date('2026-11-14T10:00:03.000Z')
    ),
    createRecord(
      'tool_result',
      sessionId,
      { name: 'fetch_stock_data', callId: 'call-1', ok: true, text: '{"last":14.52}' },
      new Date('2026-11-14T10:00:04.000Z')
    ),
    createRecord('assistant', sessionId, { text: 'ENI.MI last is 14.52.' }, new Date('2026-11-14T10:00:05.000Z')),
  ];
}

test('appends and reads a session round-trip in order', () => {
  const fs = memoryFs();
  const sessionId = '20261114-100000-ab12';
  const file = sessionFilePath(DIR, sessionId);
  const records = sampleRecords(sessionId);
  for (const record of records) {
    appendRecord(fs, file, record);
  }
  const restored = readSession(fs, file);
  assert.equal(restored.length, records.length);
  assert.deepEqual(
    restored.map((record) => record.kind),
    ['session_meta', 'user', 'assistant', 'tool_call', 'tool_result', 'assistant']
  );
  assert.equal(restored[1].text, 'Analyze ENI.MI and show the option chain');
  assert.deepEqual(restored[3].args, { ticker: 'ENI.MI' });
  assert.equal(restored[4].ok, true);
  assert.equal(restored[0].sessionId, sessionId);
});

test('a missing session file reads as an empty transcript', () => {
  const fs = memoryFs();
  assert.deepEqual(readSession(fs, sessionFilePath(DIR, 'absent')), []);
});

test('summary keeps the first user line, counts messages and timestamps', () => {
  const sessionId = '20261114-100000-ab12';
  const records = sampleRecords(sessionId);
  records[1].text = `${'x'.repeat(200)}\nsecond line`;
  const summary = summaryOf(records);
  assert.equal(summary.sessionId, sessionId);
  assert.equal(summary.title.length, 80);
  assert.ok(summary.title.endsWith('…'));
  assert.equal(summary.messageCount, 3);
  assert.equal(summary.toolCallCount, 1);
  assert.equal(summary.createdAt, '2026-11-14T10:00:00.000Z');
  assert.equal(summary.updatedAt, '2026-11-14T10:00:05.000Z');

  const empty = summaryOf([]);
  assert.equal(empty.title, 'Untitled chat');
  assert.equal(empty.messageCount, 0);
});

test('lists sessions newest first and skips unrelated files', () => {
  const fs = memoryFs();
  const older = sampleRecords('20261114-090000-aaaa');
  const newer = sampleRecords('20261114-110000-bbbb');
  newer.forEach((record, index) => {
    record.ts = new Date(Date.parse('2026-11-14T11:00:00.000Z') + index * 1000).toISOString();
  });
  for (const record of older) {
    appendRecord(fs, sessionFilePath(DIR, '20261114-090000-aaaa'), record);
  }
  for (const record of newer) {
    appendRecord(fs, sessionFilePath(DIR, '20261114-110000-bbbb'), record);
  }
  fs.files.set(path.join(DIR, 'notes.txt'), 'ignore me');
  fs.files.set(path.join(DIR, 'empty.jsonl'), '');

  const sessions = listSessions(fs, DIR);
  assert.equal(sessions.length, 2);
  assert.equal(sessions[0].sessionId, '20261114-110000-bbbb');
  assert.equal(sessions[1].sessionId, '20261114-090000-aaaa');
});

test('exports markdown with tool calls and results', () => {
  const markdown = exportSession(sampleRecords('20261114-100000-ab12'));
  assert.ok(markdown.startsWith('# Analyze ENI.MI and show the option chain'));
  assert.ok(markdown.includes('## User'));
  assert.ok(markdown.includes('## Assistant'));
  assert.ok(markdown.includes('### Tool call: `fetch_stock_data`'));
  assert.ok(markdown.includes('"ticker": "ENI.MI"'));
  assert.ok(markdown.includes('### Tool result: `fetch_stock_data` (ok)'));
  assert.ok(markdown.includes('{"last":14.52}'));
});

test('deletes a session file and tolerates a missing file', () => {
  const fs = memoryFs();
  const file = sessionFilePath(DIR, '20261114-100000-ab12');
  for (const record of sampleRecords('20261114-100000-ab12')) {
    appendRecord(fs, file, record);
  }
  assert.equal(fs.exists(file), true);
  deleteSession(fs, file);
  assert.equal(fs.exists(file), false);
  deleteSession(fs, file);
  assert.equal(fs.exists(file), false);
});

test('session ids are filesystem safe and path traversal is stripped', () => {
  const id = newSessionId(new Date('2026-11-14T16:08:44'), () => 0.5);
  assert.match(id, /^20261114-160844-[0-9a-f]{4}$/);
  assert.equal(sanitizeSessionId('../../etc/passwd'), 'etcpasswd');
  assert.equal(sanitizeSessionId('20261114-100000-ab12'), '20261114-100000-ab12');
  assert.ok(sessionFilePath(DIR, '../escape').startsWith(DIR));
});

test('parseTranscript tolerates junk lines', () => {
  const good = JSON.stringify({ id: '1', ts: '2026-11-14T10:00:00.000Z', kind: 'user', sessionId: 's1', text: 'hi' });
  const parsed = parseTranscript([good, 'not json', '', '{"kind":"user"}', '[]'].join('\n'));
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].text, 'hi');
});
