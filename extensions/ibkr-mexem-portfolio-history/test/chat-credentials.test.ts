import assert from 'node:assert/strict';
import test from 'node:test';
import { CHAT_API_KEY_SECRET, parseOpencodeAuthKey, resolveApiKey } from '../src/chat/credentials.ts';

test('the secret storage key wins over the environment and auth.json', async () => {
  const resolved = await resolveApiKey({
    readSecret: async () => 'from-secret',
    readEnv: () => 'from-env',
    readAuthFile: async () => JSON.stringify({ 'opencode-go': { type: 'api', key: 'from-auth' } })
  });
  assert.deepEqual(resolved, { key: 'from-secret', source: 'secret' });
});

test('the environment wins when the secret is empty or missing', async () => {
  const missing = await resolveApiKey({
    readSecret: async () => undefined,
    readEnv: () => 'from-env',
    readAuthFile: async () => JSON.stringify({ 'opencode-go': { key: 'from-auth' } })
  });
  assert.deepEqual(missing, { key: 'from-env', source: 'env' });

  const blank = await resolveApiKey({
    readSecret: async () => '   ',
    readEnv: () => 'from-env',
    readAuthFile: async () => undefined
  });
  assert.deepEqual(blank, { key: 'from-env', source: 'env' });
});

test('auth.json is the last fallback', async () => {
  const resolved = await resolveApiKey({
    readSecret: async () => undefined,
    readEnv: () => '',
    readAuthFile: async () => JSON.stringify({ 'opencode-go': { type: 'api', key: 'from-auth' } })
  });
  assert.deepEqual(resolved, { key: 'from-auth', source: 'opencodeAuth' });
});

test('a malformed, absent or unrelated auth.json resolves to undefined', async () => {
  const malformed = await resolveApiKey({
    readSecret: async () => undefined,
    readEnv: () => undefined,
    readAuthFile: async () => '{ not json'
  });
  assert.equal(malformed, undefined);

  const absentFile = await resolveApiKey({
    readSecret: async () => undefined,
    readEnv: () => undefined,
    readAuthFile: async () => undefined
  });
  assert.equal(absentFile, undefined);

  const otherProvider = await resolveApiKey({
    readSecret: async () => undefined,
    readEnv: () => undefined,
    readAuthFile: async () => JSON.stringify({ anthropic: { type: 'api', key: 'x' } })
  });
  assert.equal(otherProvider, undefined);
});

test('throwing readers never propagate a secret', async () => {
  const resolved = await resolveApiKey({
    readSecret: async () => {
      throw new Error('secret storage unavailable');
    },
    readEnv: () => undefined,
    readAuthFile: async () => undefined
  }).catch(() => undefined);
  assert.equal(resolved, undefined);
});

test('parseOpencodeAuthKey handles the documented shape and edge cases', () => {
  assert.equal(parseOpencodeAuthKey(JSON.stringify({ 'opencode-go': { type: 'api', key: ' abc ' } })), 'abc');
  assert.equal(parseOpencodeAuthKey(JSON.stringify({ 'opencode-go': { type: 'api' } })), undefined);
  assert.equal(parseOpencodeAuthKey(JSON.stringify({ 'opencode-go': null })), undefined);
  assert.equal(parseOpencodeAuthKey(JSON.stringify([])), undefined);
  assert.equal(parseOpencodeAuthKey('null'), undefined);
  assert.equal(parseOpencodeAuthKey(''), undefined);
  assert.equal(CHAT_API_KEY_SECRET, 'ibkrHistory.chat.apiKey');
});
