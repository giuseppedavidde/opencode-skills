import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_USER_AGENT,
  buildChatRequest,
  createToolCallState,
  finalizeToolCalls,
  mergeToolCallDeltas,
  normalizeModelId,
  parseAuthKey,
  parseCompletionJson,
  parseModelProtocols,
  parseSseLine,
  readOpencodeUsage,
  splitSseLines,
  supportsChatCompletions,
  toOpenAiTools,
  type ToolCallDelta,
} from '../src/core/opencodeGo';

const AUTH_JSON = JSON.stringify({
  'opencode-go': { key: 'oc_sk_test_value', type: 'api' },
  other: { key: 'oc_sk_other' },
});

test('parseAuthKey reads the opencode-go key', () => {
  assert.equal(parseAuthKey(AUTH_JSON), 'oc_sk_test_value');
});

test('parseAuthKey trims whitespace and rejects broken input', () => {
  assert.equal(parseAuthKey(JSON.stringify({ 'opencode-go': { key: '  oc_sk_x  ' } })), 'oc_sk_x');
  assert.equal(parseAuthKey(JSON.stringify({ 'opencode-go': { key: '   ' } })), null);
  assert.equal(parseAuthKey(JSON.stringify({ other: { key: 'oc_sk_other' } })), null);
  assert.equal(parseAuthKey('not json'), null);
  assert.equal(parseAuthKey(''), null);
});

test('normalizeModelId strips the provider prefix', () => {
  assert.equal(normalizeModelId('opencode-go/deepseek-v4.1-flash'), 'deepseek-v4.1-flash');
  assert.equal(normalizeModelId('  opencode-go/deepseek-v4.1-flash  '), 'deepseek-v4.1-flash');
  assert.equal(normalizeModelId('deepseek-v4.1-flash'), 'deepseek-v4.1-flash');
  assert.equal(normalizeModelId('opencode-go/opencode-go/x'), 'x');
  assert.equal(normalizeModelId(''), '');
});

test('normalizeModelId drops the opencode reasoning-effort suffix', () => {
  assert.equal(normalizeModelId('opencode-go/gemini-4-argon#medium'), 'gemini-4-argon');
  assert.equal(normalizeModelId('deepseek-v4.1-flash#low'), 'deepseek-v4.1-flash');
});

test('parseModelProtocols and supportsChatCompletions follow the api object of /models', () => {
  const protocols = parseModelProtocols({
    data: [
      { id: 'deepseek-v4.1-flash', api: { 'chat-completions': { base_url: 'https://x/openai/v1' } } },
      { id: 'gemini-4-argon', api: { 'generate-content': {}, interactions: {} } },
      { id: 'legacy-model' },
    ],
  });
  assert.deepEqual(protocols.get('gemini-4-argon'), ['generate-content', 'interactions']);
  assert.equal(supportsChatCompletions(protocols, 'deepseek-v4.1-flash'), true);
  assert.equal(supportsChatCompletions(protocols, 'gemini-4-argon'), false);
  assert.equal(supportsChatCompletions(protocols, 'legacy-model'), true);
  assert.equal(supportsChatCompletions(protocols, 'not-listed'), true);
  assert.equal(parseModelProtocols('not json').size, 0);
});

test('buildChatRequest sends auth, session and user agent headers', () => {
  const request = buildChatRequest({
    apiKey: 'oc_sk_test_value',
    model: 'opencode-go/deepseek-v4.1-flash',
    sessionId: 'session-42',
    messages: [{ role: 'user', content: 'hi' }],
    tools: [{ name: 'calc', description: 'Evaluate', inputSchema: { type: 'object', properties: { expression: { type: 'string' } } } }],
    stream: true,
    temperature: 0.2,
  });
  assert.equal(request.url, 'https://opencode.ai/zen/go/v1/chat/completions');
  assert.equal(request.headers.Authorization, 'Bearer oc_sk_test_value');
  assert.equal(request.headers['content-type'], 'application/json');
  assert.equal(request.headers['user-agent'], DEFAULT_USER_AGENT);
  assert.equal(request.headers['x-opencode-session'], 'session-42');
  assert.equal(request.body.model, 'deepseek-v4.1-flash');
  assert.equal(request.body.stream, true);
  assert.equal(request.body.temperature, 0.2);
  const tools = request.body.tools as Array<{ type: string; function: { name: string; parameters: unknown } }>;
  assert.equal(tools[0].type, 'function');
  assert.equal(tools[0].function.name, 'calc');
});

test('buildChatRequest honours a custom base url without trailing slash', () => {
  const request = buildChatRequest({
    baseUrl: 'https://example.test/v1/',
    apiKey: 'k',
    model: 'm',
    sessionId: 's',
    messages: [],
    stream: false,
  });
  assert.equal(request.url, 'https://example.test/v1/chat/completions');
  assert.equal(request.body.stream, false);
  assert.deepEqual(request.body.tools, []);
});

test('toOpenAiTools normalizes the parameters object', () => {
  const tools = toOpenAiTools([
    { name: 'a', description: '', inputSchema: { $schema: 'x', type: 'object', properties: { p: { type: 'string' } } } },
    { name: 'b', description: 'B tool', inputSchema: null },
    { name: 'a', description: 'duplicate', inputSchema: {} },
  ]) as Array<{ function: { name: string; description: string; parameters: Record<string, unknown> } }>;
  assert.equal(tools.length, 2);
  assert.equal(tools[0].function.description, 'a');
  assert.equal(tools[0].function.parameters.$schema, undefined);
  assert.deepEqual(tools[0].function.parameters.properties, { p: { type: 'string' } });
  assert.deepEqual(tools[1].function.parameters, { type: 'object', properties: {} });
});

test('parseSseLine reads text deltas and the done marker', () => {
  const text = parseSseLine(
    'data: {"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}'
  );
  assert.equal(text?.deltaText, 'Hello');
  assert.equal(parseSseLine('data: [DONE]')?.done, true);
  assert.equal(parseSseLine(''), null);
  assert.equal(parseSseLine(': keep-alive'), null);
  assert.deepEqual(parseSseLine('event: ping'), { event: 'ping' });
  assert.equal(parseSseLine('data: {"choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}'), null);
  assert.equal(parseSseLine('data: {"choices":[{"delta":{"content":"cut'), null, 'partial buffers are ignored');
});

test('parseSseLine reads streamed tool call deltas', () => {
  const event = parseSseLine(
    'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"read_file","arguments":"{\\"path\\":\\""}}]},"finish_reason":null}]}'
  );
  assert.equal(event?.toolCallDeltas?.length, 1);
  assert.equal(event?.toolCallDelta?.index, 0);
  assert.equal(event?.toolCallDelta?.id, 'call_1');
  assert.equal(event?.toolCallDelta?.name, 'read_file');
  assert.equal(event?.toolCallDelta?.argumentsText, '{"path":"');
});

test('splitSseLines reassembles chunks that break inside a JSON payload', () => {
  const first = splitSseLines('', 'data: {"choices":[{"delta":{"content":"Hel');
  assert.deepEqual(first.lines, []);
  const second = splitSseLines(first.rest, 'lo"}}]}\ndata: [DONE]\n');
  assert.equal(second.lines.length, 2);
  assert.equal(parseSseLine(second.lines[0])?.deltaText, 'Hello');
  assert.equal(parseSseLine(second.lines[1])?.done, true);
  assert.equal(second.rest, '');
});

test('mergeToolCallDeltas joins fragmented arguments by index', () => {
  const state = createToolCallState();
  const chunks: ToolCallDelta[] = [
    { index: 0, id: 'call_abc', name: 'read_file' },
    { index: 0, argumentsText: '{"path":' },
    { index: 0, argumentsText: '"/etc/hostname"}' },
    { index: 1, id: 'call_def', name: 'list_dir' },
    { index: 1, argumentsText: '{"path":"/tmp"}' },
  ];
  mergeToolCallDeltas(state, chunks);
  const calls = finalizeToolCalls(state);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].id, 'call_abc');
  assert.equal(calls[0].name, 'read_file');
  assert.equal(calls[0].argumentsText, '{"path":"/etc/hostname"}');
  assert.deepEqual(calls[0].argumentsObject, { path: '/etc/hostname' });
  assert.equal(calls[0].parseError, false);
  assert.deepEqual(calls[1].argumentsObject, { path: '/tmp' });
});

test('mergeToolCallDeltas flags invalid JSON arguments', () => {
  const state = createToolCallState();
  mergeToolCallDeltas(state, [{ index: 0, id: 'call_x', name: 'read_file' }, { index: 0, argumentsText: '{"path":' }]);
  const calls = finalizeToolCalls(state);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].parseError, true);
  assert.equal(calls[0].argumentsObject, null);
});

test('parseCompletionJson reads a non-streaming tool call without index', () => {
  const body = JSON.stringify({
    id: 'x',
    model: 'deepseek-v4.1-flash',
    choices: [
      {
        index: 0,
        finish_reason: 'tool_calls',
        message: {
          role: 'assistant',
          content: null,
          tool_calls: [
            { id: 'call_1', type: 'function', function: { name: 'calc', arguments: '{"expression":"17*23"}' } },
          ],
        },
      },
    ],
    usage: { prompt_tokens: 299, completion_tokens: 50, cost: 0.0001 },
  });
  const parsed = parseCompletionJson(body);
  assert.equal(parsed.text, '');
  assert.equal(parsed.finishReason, 'tool_calls');
  assert.equal(parsed.toolCalls.length, 1);
  assert.equal(parsed.toolCalls[0].name, 'calc');
  assert.deepEqual(parsed.toolCalls[0].argumentsObject, { expression: '17*23' });
  assert.equal(parsed.usage?.promptTokens, 299);
  assert.equal(parsed.usage?.completionTokens, 50);
  assert.equal(parsed.usage?.cost, 0.0001);
});

test('parseCompletionJson reports invalid JSON instead of throwing', () => {
  const parsed = parseCompletionJson('<html>oops</html>');
  assert.ok(parsed.parseError);
  assert.equal(parsed.text, '');
  assert.deepEqual(parsed.toolCalls, []);
});

test('readOpencodeUsage accepts a nested or a bare usage object', () => {
  assert.deepEqual(readOpencodeUsage({ usage: { prompt_tokens: 1, completion_tokens: 2, cost: 3 } }), {
    promptTokens: 1,
    completionTokens: 2,
    cost: 3,
  });
  assert.deepEqual(readOpencodeUsage({ prompt_tokens: 5, completion_tokens: 6 }), {
    promptTokens: 5,
    completionTokens: 6,
    cost: null,
  });
  assert.equal(readOpencodeUsage({ usage: null }), null);
  assert.equal(readOpencodeUsage(null), null);
});
