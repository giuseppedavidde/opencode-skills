import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ChatError,
  SseDecoder,
  buildChatRequestBody,
  chatCompletionsUrl,
  mapHttpError,
  parseSseData,
  redactTokens,
  sseDataOf,
  streamChatCompletion,
  trimHistory
} from '../src/chat/client.ts';
import type { ChatMessage } from '../src/chat/client.ts';

const KEY = 'test-key-abc123456789';

function sseResponse(chunks: readonly string[], status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    }
  });
  return new Response(stream, { status, headers: { 'content-type': 'text/event-stream' } });
}

function delta(content: string): string {
  return `data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n`;
}

function capture(): { calls: { url: string; init: RequestInit }[]; fetchImpl: typeof fetch } {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return sseResponse([delta('ok'), 'data: [DONE]\n']);
  }) as typeof fetch;
  return { calls, fetchImpl };
}

test('an SSE object split across two chunks is reassembled', () => {
  const decoder = new SseDecoder();
  const first = decoder.push('data: {"choices":[{"delta":{"content":"he');
  assert.deepEqual(first, []);
  const second = decoder.push('llo"}}]}\n');
  assert.equal(second.length, 1);
  const parsed = parseSseData(second[0] ?? '');
  assert.deepEqual(parsed, { kind: 'delta', text: 'hello' });
});

test('several events in one chunk are all emitted', () => {
  const decoder = new SseDecoder();
  const payloads = decoder.push(`${delta('a')}${delta('b')}${delta('c')}data: [DONE]\n`);
  assert.equal(payloads.length, 4);
  assert.deepEqual(
    payloads.slice(0, 3).map((payload) => parseSseData(payload)),
    [
      { kind: 'delta', text: 'a' },
      { kind: 'delta', text: 'b' },
      { kind: 'delta', text: 'c' }
    ]
  );
  assert.deepEqual(parseSseData(payloads[3] ?? ''), { kind: 'done' });
});

test('data: is accepted with and without a space, comments and empty lines are skipped', () => {
  assert.equal(sseDataOf('data: {"a":1}'), '{"a":1}');
  assert.equal(sseDataOf('data:{"a":1}'), '{"a":1}');
  assert.equal(sseDataOf(''), undefined);
  assert.equal(sseDataOf(': keep-alive'), undefined);
  assert.equal(sseDataOf('event: message'), undefined);
  const decoder = new SseDecoder();
  assert.deepEqual(decoder.push(': comment\n\nevent: ping\ndata:{"ok":true}\n'), ['{"ok":true}']);
});

test('a malformed JSON line is skipped without throwing', () => {
  const decoder = new SseDecoder();
  const payloads = decoder.push('data: {not json\n');
  assert.equal(payloads.length, 1);
  assert.deepEqual(parseSseData(payloads[0] ?? ''), { kind: 'ignore' });
});

test('[DONE] ends the stream and a partial final line is flushed', () => {
  assert.deepEqual(parseSseData('[DONE]'), { kind: 'done' });
  const decoder = new SseDecoder();
  assert.deepEqual(decoder.push('data: {"choices":[]}'), []);
  assert.deepEqual(decoder.flush(), ['{"choices":[]}']);
  assert.deepEqual(decoder.flush(), []);
});

test('the request body carries the model, stream: true and the messages in order', () => {
  const messages: ChatMessage[] = [
    { role: 'system', content: 'S' },
    { role: 'user', content: 'U' },
    { role: 'assistant', content: 'A' }
  ];
  const body = buildChatRequestBody({ model: 'glm-5.3', messages, temperature: 0.1, maxTokens: 99 });
  assert.equal(body.model, 'glm-5.3');
  assert.equal(body.stream, true);
  assert.equal(body.temperature, 0.1);
  assert.equal(body.max_tokens, 99);
  assert.deepEqual(body.messages, messages);
  assert.equal(chatCompletionsUrl('https://opencode.ai/zen/go/v1/'), 'https://opencode.ai/zen/go/v1/chat/completions');
});

test('the fetch call uses the bearer header and streams the deltas', async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return sseResponse([delta('Hel'), delta('lo') + 'data: [DONE]\n']);
  }) as typeof fetch;

  const deltas: string[] = [];
  const result = await streamChatCompletion({
    baseUrl: 'https://opencode.ai/zen/go/v1',
    apiKey: KEY,
    model: 'deepseek-v4-pro',
    messages: [{ role: 'user', content: 'hi' }],
    fetchImpl,
    onDelta: (text) => deltas.push(text)
  });

  assert.equal(result.text, 'Hello');
  assert.deepEqual(deltas, ['Hel', 'lo']);
  const call = calls[0];
  assert.ok(call);
  assert.equal(call.url, 'https://opencode.ai/zen/go/v1/chat/completions');
  assert.equal(call.init.method, 'POST');
  const headers = call.init.headers as Record<string, string>;
  assert.equal(headers.Authorization, `Bearer ${KEY}`);
  assert.equal(headers['Content-Type'], 'application/json');
  const body = JSON.parse(String(call.init.body)) as { model: string; stream: boolean; messages: ChatMessage[] };
  assert.equal(body.model, 'deepseek-v4-pro');
  assert.equal(body.stream, true);
  assert.deepEqual(body.messages, [{ role: 'user', content: 'hi' }]);
});

test('401 maps to a key error and the key never appears in the message', async () => {
  const fetchImpl = (async () =>
    new Response(`{"error":"bad key","echo":"Authorization: Bearer ${KEY}"}`, { status: 401 })) as typeof fetch;
  await assert.rejects(
    streamChatCompletion({
      baseUrl: 'https://opencode.ai/zen/go/v1',
      apiKey: KEY,
      model: 'm',
      messages: [{ role: 'user', content: 'x' }],
      fetchImpl
    }),
    (error: unknown) => {
      assert.ok(error instanceof ChatError);
      assert.equal(error.status, 401);
      assert.match(error.message, /API key rejected/);
      assert.equal(error.message.includes(KEY), false, 'the key must never appear in an error');
      assert.equal(/Bearer\s+[A-Za-z0-9]/.test(error.message), false, 'bearer tokens are redacted');
      return true;
    }
  );
});

test('429 maps to a rate-limit hint with a retry and no key', async () => {
  const fetchImpl = (async () => new Response(`quota ${KEY}`, { status: 429 })) as typeof fetch;
  await assert.rejects(
    streamChatCompletion({
      baseUrl: 'https://opencode.ai/zen/go/v1',
      apiKey: KEY,
      model: 'm',
      messages: [{ role: 'user', content: 'x' }],
      fetchImpl
    }),
    (error: unknown) => {
      assert.ok(error instanceof ChatError);
      assert.match(error.message, /Rate limit/);
      assert.match(error.message, /Retry/);
      assert.equal(error.message.includes(KEY), false);
      return true;
    }
  );
});

test('402, 404 and 5xx map to distinct messages', () => {
  assert.match(mapHttpError(402), /Quota exhausted/);
  assert.match(mapHttpError(404), /Model name unknown/);
  assert.match(mapHttpError(503), /service returned an error \(HTTP 503\)/);
  assert.match(mapHttpError(418), /HTTP 418/);
  assert.equal(redactTokens(`Bearer ${KEY}`).includes(KEY), false);
  assert.equal(redactTokens(`sk-abcdefgh12345678`), 'sk-***');
});

test('maxHistoryMessages keeps the system message and the newest turns', () => {
  const messages: ChatMessage[] = [{ role: 'system', content: 'S' }];
  for (let index = 0; index < 20; index += 1) {
    messages.push({ role: index % 2 === 0 ? 'user' : 'assistant', content: `m${index}` });
  }
  const trimmed = trimHistory(messages, 10);
  assert.equal(trimmed[0]?.role, 'system');
  assert.equal(trimmed.length, 11);
  assert.equal(trimmed[1]?.role, 'user', 'the history starts with a user turn');
  assert.equal(trimmed[trimmed.length - 1]?.content, 'm19', 'the newest turn survives');
  assert.equal(trimmed.some((message) => message.content === 'm0'), false);
});

test('a conversation under the cap is unchanged', () => {
  const messages: ChatMessage[] = [
    { role: 'system', content: 'S' },
    { role: 'user', content: 'a' },
    { role: 'assistant', content: 'b' }
  ];
  assert.deepEqual(trimHistory(messages, 20), messages);
});

test('the injected fetch is used instead of the global one', async () => {
  const { calls, fetchImpl } = capture();
  const result = await streamChatCompletion({
    baseUrl: 'https://example.test/v1',
    apiKey: KEY,
    model: 'm',
    messages: [{ role: 'user', content: 'x' }],
    fetchImpl
  });
  assert.equal(result.text, 'ok');
  assert.equal(calls.length, 1);
});
