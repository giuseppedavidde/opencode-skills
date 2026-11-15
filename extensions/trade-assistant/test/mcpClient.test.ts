import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  isUnsafeToolName,
  normalizeInputSchema,
  outcomeText,
  parseRpcLines,
  parseToolList,
  toChatTools,
} from '../src/core/mcpClient';

test('parses newline framed JSON-RPC messages and keeps the partial tail', () => {
  const first = parseRpcLines('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\r\n{"jsonrpc":"2.0","id":2,"res');
  assert.equal(first.messages.length, 1);
  assert.equal(first.messages[0].id, 1);
  assert.deepEqual(first.messages[0].result, { ok: true });
  assert.equal(first.rest, '{"jsonrpc":"2.0","id":2,"res');

  const second = parseRpcLines(`${first.rest}ult":{"tools":[]}}\n`);
  assert.equal(second.messages.length, 1);
  assert.equal(second.messages[0].id, 2);
  assert.equal(second.rest, '');
});

test('ignores malformed lines, blank lines and non-object payloads', () => {
  const buffer = ['[1,2,3]', 'not json', '', '{"jsonrpc":"2.0","id":7,"result":{}}', '"text"'].join('\n');
  const parsed = parseRpcLines(`${buffer}\n`);
  assert.equal(parsed.messages.length, 1);
  assert.equal(parsed.messages[0].id, 7);
  assert.equal(parsed.rest, '');
});

test('maps tools/list output to chat tool schemas', () => {
  const result = {
    tools: [
      {
        name: 'fetch_stock_data',
        description: 'Fetch complete stock data.',
        inputSchema: {
          $schema: 'http://json-schema.org/draft-07/schema#',
          type: 'object',
          properties: { ticker: { type: 'string' } },
          required: ['ticker'],
        },
      },
      { name: 'no_schema' },
      { description: 'without a name' },
      { name: 'fetch_stock_data', description: 'duplicate' },
    ],
  };
  const tools = parseToolList(result);
  assert.equal(tools.length, 2);
  assert.equal(tools[0].name, 'fetch_stock_data');
  assert.equal(tools[1].name, 'no_schema');
  assert.equal(tools[1].description, '');

  const chat = toChatTools(tools);
  assert.deepEqual(chat[0].inputSchema, {
    type: 'object',
    properties: { ticker: { type: 'string' } },
    required: ['ticker'],
  });
  assert.equal(chat[0].description, 'Fetch complete stock data.');
  assert.equal(chat[1].description, 'no_schema');
  assert.deepEqual(chat[1].inputSchema, { type: 'object', properties: {} });
});

test('normalizes an unusable input schema to an empty object schema', () => {
  assert.deepEqual(normalizeInputSchema(undefined), { type: 'object', properties: {} });
  assert.deepEqual(normalizeInputSchema({ type: 'array' }), { type: 'object', properties: {} });
});

test('blocks unsafe trading tool names and allows read-only tools', () => {
  const blocked = [
    'place_order',
    'place_option_order',
    'trade_execute',
    'buy_stock',
    'buy',
    'sell_position',
    'close_position',
    'transfer_funds',
    'ORDER_STATUS',
  ];
  for (const name of blocked) {
    assert.equal(isUnsafeToolName(name), true, `${name} must be blocked`);
  }
  const allowed = [
    'fetch_stock_data',
    'analyze_stock',
    'analyze_options',
    'suggest_options_strategy',
    'scan_market',
    'fetch_options_chain',
    'get_macro_context',
    'skill_lookup',
  ];
  for (const name of allowed) {
    assert.equal(isUnsafeToolName(name), false, `${name} must stay allowed`);
  }
});

test('joins textual tool result blocks and stringifies structured ones', () => {
  assert.equal(
    outcomeText({ content: [{ type: 'text', text: 'alpha' }, { type: 'text', text: 'beta' }] }),
    'alpha\nbeta'
  );
  assert.equal(outcomeText({ content: [{ type: 'json', value: 1 }] }), JSON.stringify({ type: 'json', value: 1 }));
  assert.equal(outcomeText('plain'), 'plain');
  assert.equal(outcomeText({ content: [] }), '');
});
