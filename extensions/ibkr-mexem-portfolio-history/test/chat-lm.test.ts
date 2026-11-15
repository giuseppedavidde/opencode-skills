import assert from 'node:assert/strict';
import test from 'node:test';
import {
  describeLanguageModelError,
  modelLabel,
  selectModel,
  toLmMessages,
  toModelOptions
} from '../src/chat/lm.ts';
import type { LanguageModelInfoLike } from '../src/chat/lm.ts';
import {
  CHAT_NOTICE_HTTP,
  CHAT_NOTICE_LM,
  DEFAULT_CHAT_BACKEND,
  DEFAULT_CHAT_MODEL,
  chatNotice
} from '../src/chat/protocol.ts';
import { resolveChatBackend, resolveChatSettings } from '../src/chat/chatSettings.ts';
import type { ChatSettingsSource } from '../src/chat/chatSettings.ts';
import { buildChatRequestBody, trimHistory } from '../src/chat/client.ts';
import type { ChatMessage } from '../src/chat/client.ts';

function config(values: Record<string, unknown> = {}): ChatSettingsSource {
  return {
    get<T>(section: string, fallback: T): T {
      return (section in values ? values[section] : fallback) as T;
    }
  };
}

test('the model list is deduplicated by id and labelled from name, family, then id', () => {
  const models: LanguageModelInfoLike[] = [
    { id: 'zeta', name: 'Zeta' },
    { id: 'alpha', name: 'alpha' },
    { id: 'alpha', name: 'Alpha duplicate' },
    { id: 'gamma', name: '', family: 'gamma-family' },
    { id: 'delta', name: '', family: '' },
    { id: '  ', name: 'blank id' }
  ];
  const options = toModelOptions(models);
  assert.deepEqual(options, [
    { id: 'alpha', label: 'alpha' },
    { id: 'delta', label: 'delta' },
    { id: 'gamma', label: 'gamma-family' },
    { id: 'zeta', label: 'Zeta' }
  ]);
  assert.equal(modelLabel({ id: 'x', name: ' Name ' }), 'Name');
  assert.equal(modelLabel({ id: 'x', name: '', family: 'fam' }), 'fam');
  assert.equal(modelLabel({ id: 'x', name: '' }), 'x');
});

test('an empty model list stays empty, never a placeholder', () => {
  assert.deepEqual(toModelOptions([]), []);
});

test('selectModel prefers the exact id, then the family, then the first model', () => {
  const models: LanguageModelInfoLike[] = [
    { id: 'glm-5.3', name: 'GLM 5.3', family: 'glm' },
    { id: 'deepseek-v4.1-flash', name: 'DeepSeek V4.1 Flash', family: 'deepseek' }
  ];
  assert.equal(selectModel(models, 'glm-5.3')?.id, 'glm-5.3');
  assert.equal(selectModel(models, 'deepseek')?.id, 'deepseek-v4.1-flash');
  assert.equal(selectModel(models, 'deepseek-v4-pro')?.id, 'glm-5.3', 'an unknown id falls back to the first model');
  assert.equal(selectModel(models, '  ')?.id, 'glm-5.3');
  assert.equal(selectModel([], 'glm-5.3'), undefined);
});

test('the persona and the context ride in the first user message', () => {
  const messages = toLmMessages('PERSONA', 'CONTEXT', [], 'question');
  assert.equal(messages.length, 1, 'no history means one message, so the turns alternate');
  assert.equal(messages[0]?.role, 'user');
  assert.ok(messages[0]?.content.includes('PERSONA'));
  assert.ok(messages[0]?.content.includes('CONTEXT'));
  assert.ok(messages[0]?.content.includes('question'));
  assert.ok(messages[0]?.content.startsWith('PERSONA\n\n---\n\nCONTEXT'));
});

test('history stays user and assistant, the question comes last', () => {
  const history: ChatMessage[] = [
    { role: 'system', content: 'S' },
    { role: 'user', content: 'u1' },
    { role: 'assistant', content: 'a1' }
  ];
  const messages = toLmMessages('PERSONA', 'CONTEXT', history, 'u2');
  assert.deepEqual(
    messages.map((message) => message.role),
    ['user', 'user', 'assistant', 'user']
  );
  assert.equal(messages[0]?.content, 'PERSONA\n\n---\n\nCONTEXT');
  assert.equal(messages[1]?.content, 'u1');
  assert.equal(messages[2]?.content, 'a1');
  assert.equal(messages[messages.length - 1]?.content, 'u2');
  assert.equal(messages.some((message) => (message.role as string) === 'system'), false);
});

test('the trimmed history keeps the alternation the language model expects', () => {
  const turns: ChatMessage[] = [];
  for (let index = 0; index < 20; index += 1) {
    turns.push({ role: index % 2 === 0 ? 'user' : 'assistant', content: `m${index}` });
  }
  const trimmed = trimHistory(turns, 4);
  assert.equal(trimmed[0]?.role, 'user');
  const messages = toLmMessages('PERSONA', 'CONTEXT', trimmed, 'now');
  assert.equal(messages[1]?.role, 'user', 'the first turn after the preamble is a user turn');
  assert.equal(messages[messages.length - 1]?.role, 'user');
});

test('the default backend is lm and only http selects the HTTP client', () => {
  assert.equal(DEFAULT_CHAT_BACKEND, 'lm');
  assert.equal(resolveChatBackend(undefined), 'lm');
  assert.equal(resolveChatBackend('lm'), 'lm');
  assert.equal(resolveChatBackend('http'), 'http');
  assert.equal(resolveChatBackend('HTTP'), 'lm');
  const defaults = resolveChatSettings(config());
  assert.equal(defaults.backend, 'lm');
  assert.equal(defaults.model, DEFAULT_CHAT_MODEL);
  assert.equal(defaults.baseUrl, 'https://opencode.ai/zen/go/v1');
  assert.equal(defaults.temperature, 0.3);
  assert.equal(defaults.maxTokens, 2048);
  assert.equal(defaults.maxContextTrades, 400);
  assert.equal(defaults.maxHistoryMessages, 20);
});

test('the http backend still builds the request body from the settings', () => {
  const settings = resolveChatSettings(
    config({ 'chat.backend': 'http', 'chat.model': 'glm-5.3', 'chat.temperature': 0.1, 'chat.maxTokens': 512 })
  );
  assert.equal(settings.backend, 'http');
  const messages: ChatMessage[] = [
    { role: 'system', content: 'S' },
    { role: 'user', content: 'U' }
  ];
  const body = buildChatRequestBody({
    model: settings.model,
    messages,
    temperature: settings.temperature,
    maxTokens: settings.maxTokens
  });
  assert.equal(body.model, 'glm-5.3');
  assert.equal(body.stream, true);
  assert.equal(body.temperature, 0.1);
  assert.equal(body.max_tokens, 512);
  assert.deepEqual(body.messages, messages);
});

test('the privacy notice follows the active backend', () => {
  assert.equal(chatNotice('lm'), CHAT_NOTICE_LM);
  assert.equal(chatNotice('http'), CHAT_NOTICE_HTTP);
  assert.match(CHAT_NOTICE_LM, /VS Code language model provider/);
  assert.match(CHAT_NOTICE_HTTP, /opencode\.ai/);
  assert.equal(chatNotice(DEFAULT_CHAT_BACKEND), CHAT_NOTICE_LM);
});

test('a language model error keeps the cause and names the action', () => {
  const noPermissions = Object.assign(new Error('denied'), { code: 'NoPermissions' });
  assert.match(describeLanguageModelError(noPermissions), /did not grant access/);
  const blocked = Object.assign(new Error('quota'), { code: 'Blocked' });
  assert.match(describeLanguageModelError(blocked), /quota is exhausted/);
  const notFound = Object.assign(new Error('gone'), { code: 'NotFound' });
  assert.match(describeLanguageModelError(notFound), /no longer available/);
  assert.match(describeLanguageModelError(new Error('boom')), /language model request failed: boom/);
  assert.match(describeLanguageModelError('plain'), /plain/);
});
