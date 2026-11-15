import assert from 'node:assert/strict';
import { homedir } from 'node:os';
import test from 'node:test';
import {
  buildFetchArgs,
  chainKey,
  MAX_MARKET_DATA_REQUESTS,
  parseChainJson,
  parseMarketDataCommand,
  renderMarketDataBlock,
  valueOptions
} from '../src/chat/marketData.ts';
import type { ChainData } from '../src/chat/marketData.ts';
import { MarketDataService, MARKET_DATA_CACHE_TTL_MS } from '../src/chat/marketDataService.ts';
import type { MarketDataRunner } from '../src/chat/marketDataService.ts';
import { buildOptionPositions } from '../src/chat/optionSymbol.ts';
import type { TradeRow } from '../src/panel/protocol.ts';

function row(overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    date: '2026-10-16',
    time: '10:00:00',
    symbol: 'LHX   261120C00320000',
    buySell: 'BUY',
    quantity: 1,
    price: 2,
    currency: 'USD',
    realizedPnl: null,
    pnlSource: 'none',
    ...overrides
  };
}

function chain(overrides: Partial<ChainData> = {}): ChainData {
  return {
    ticker: 'LHX',
    underlyingPrice: 272.35,
    dte: 5,
    expiry: '2026-11-20',
    calls: [],
    puts: [],
    fetchedAt: '2026-11-15T14:40:43.000Z',
    ...overrides
  };
}

const CLI_JSON = JSON.stringify({
  ticker: 'LHX',
  underlying_price: 272.35,
  selected_expiry: '2026-11-20',
  dte: 5,
  calls: [
    {
      strike: 320,
      bid: 3.0,
      ask: 3.4,
      impliedVolatility: 0.62,
      delta: 0.91,
      theta: -0.33
    }
  ],
  puts: [{ strike: 300, bid: 0, ask: 0, impliedVolatility: 0, iv_used: 0.49, delta: -0.95, theta: -0.12 }]
});

test('the command template splits into a command and a base argument list', () => {
  const parsed = parseMarketDataCommand('  /usr/bin/python3   -m  trading_mcp.trading_cli  ');
  assert.deepEqual(parsed, { command: '/usr/bin/python3', baseArgs: ['-m', 'trading_mcp.trading_cli'] });
  assert.equal(parseMarketDataCommand(''), null);
  assert.equal(parseMarketDataCommand('   '), null);
  const expanded = parseMarketDataCommand('~/bin/python -m trading_mcp.trading_cli');
  assert.equal(expanded?.command, `${homedir()}/bin/python`);
  assert.deepEqual(expanded?.baseArgs, ['-m', 'trading_mcp.trading_cli']);
});

test('the argument list names the subcommand, the ticker and the expiry', () => {
  assert.deepEqual(buildFetchArgs(['-m', 'trading_mcp.trading_cli'], 'LHX', '2026-11-20'), [
    '-m',
    'trading_mcp.trading_cli',
    'fetch',
    'options',
    'LHX',
    '--expiry',
    '2026-11-20'
  ]);
  assert.deepEqual(buildFetchArgs([], 'BRK.B', '2026-11-20'), ['fetch', 'options', 'BRK.B', '--expiry', '2026-11-20']);
});

test('an invalid ticker is rejected before any process starts', () => {
  assert.equal(buildFetchArgs([], 'LHX; rm -rf /', '2026-11-20'), null);
  assert.equal(buildFetchArgs([], '', '2026-11-20'), null);
  assert.equal(buildFetchArgs([], '1LHX', '2026-11-20'), null);
  assert.equal(buildFetchArgs([], 'TOOLONGTICKER', '2026-11-20'), null);
});

test('the chain parser accepts the traded CLI payload and tolerates a missing array', () => {
  const parsed = parseChainJson(CLI_JSON, 'LHX');
  assert.ok(parsed);
  assert.equal(parsed.ticker, 'LHX');
  assert.equal(parsed.underlyingPrice, 272.35);
  assert.equal(parsed.dte, 5);
  assert.equal(parsed.expiry, '2026-11-20');
  assert.equal(parsed.calls.length, 1);
  assert.equal(parsed.calls[0]?.strike, 320);
  assert.equal(parsed.calls[0]?.impliedVolatility, 0.62);
  assert.equal(parsed.puts[0]?.impliedVolatility, 0.49, 'a zero quote IV falls back to the fitted value');

  const noCalls = parseChainJson(JSON.stringify({ ticker: 'AMD', puts: [] }), 'AMD');
  assert.ok(noCalls);
  assert.deepEqual(noCalls.calls, []);
  assert.equal(noCalls.underlyingPrice, null);
  assert.equal(noCalls.dte, null);
  assert.equal(noCalls.expiry, null);

  const noisy = parseChainJson(
    JSON.stringify({ underlying_price: 'n/a', dte: null, calls: [{ strike: 1, bid: 'x', ask: null }] }),
    'STX'
  );
  assert.ok(noisy);
  assert.equal(noisy.underlyingPrice, null);
  assert.equal(noisy.calls[0]?.bid, null);
  assert.equal(noisy.calls[0]?.ask, null);
});

test('truncated JSON and non-object output return null instead of throwing', () => {
  assert.equal(parseChainJson(CLI_JSON.slice(0, 40), 'LHX'), null);
  assert.equal(parseChainJson('', 'LHX'), null);
  assert.equal(parseChainJson('[1,2,3]', 'LHX'), null);
  assert.equal(parseChainJson('"a string"', 'LHX'), null);
  assert.equal(parseChainJson('null', 'LHX'), null);
});

test('the mid price, the multiplier 100 and the unrealized P&L on a long and on a short', () => {
  const positions = buildOptionPositions([
    row({ symbol: 'LHX   261120C00320000', quantity: 1, price: 2 }),
    row({ symbol: 'AMD   261218P00300000', buySell: 'SELL', quantity: -2, price: 1.5 })
  ]);
  const chains = new Map<string, ChainData>([
    [
      chainKey('LHX', '2026-11-20'),
      chain({ calls: [{ strike: 320, bid: 3, ask: 3.4, delta: 0.5, theta: -0.1, impliedVolatility: 0.4 }] })
    ],
    [
      chainKey('AMD', '2026-12-18'),
      chain({
        ticker: 'AMD',
        expiry: '2026-12-18',
        puts: [{ strike: 300, bid: 2, ask: 3, delta: -0.3, theta: -0.2, impliedVolatility: 0.5 }]
      })
    ]
  ]);
  const rows = valueOptions(positions, chains);
  assert.equal(rows.length, 2);
  const long = rows.find((entry) => entry.contract.root === 'LHX');
  assert.ok(long);
  assert.equal(long.mark, 3.2);
  assert.equal(long.positionValue, 320, 'mark * 100 * 1');
  assert.equal(long.unrealized, 120, '320 - 200 paid');
  assert.equal(long.quoteSource, 'mid');
  assert.equal(long.currency, 'USD');

  const short = rows.find((entry) => entry.contract.root === 'AMD');
  assert.ok(short);
  assert.equal(short.mark, 2.5);
  assert.equal(short.positionValue, -500, 'mark * 100 * -2');
  assert.equal(short.unrealized, -200, '-500 - (-300) received');
  assert.equal(short.netQuantity, -2);
});

test('a missing chain, a missing strike and a zero quote give null, never zero', () => {
  const positions = buildOptionPositions([
    row({ symbol: 'LHX   261120C00320000', quantity: 1, price: 2 }),
    row({ symbol: 'LHX   261120C00330000', quantity: 1, price: 1 })
  ]);
  const noChain = valueOptions(positions, new Map());
  assert.deepEqual(
    noChain.map((entry) => [entry.mark, entry.positionValue, entry.unrealized, entry.delta, entry.quoteSource]),
    [
      [null, null, null, null, 'none'],
      [null, null, null, null, 'none']
    ]
  );

  const chains = new Map<string, ChainData>([
    [
      chainKey('LHX', '2026-11-20'),
      chain({
        calls: [
          { strike: 320, bid: 3, ask: 3.4, delta: 0.5, theta: -0.1, impliedVolatility: 0.4 },
          { strike: 330, bid: 0, ask: 0, delta: 0.1, theta: 0, impliedVolatility: 0 }
        ]
      })
    ]
  ]);
  const valued = valueOptions(positions, chains);
  assert.equal(valued[1]?.mark, null, 'a zero bid and a zero ask are not a price');
  assert.equal(valued[1]?.positionValue, null);
  assert.equal(valued[1]?.quoteSource, 'none');
});

test('the block states the time, the source, the spot with the DTE, then one line per contract', () => {
  const positions = buildOptionPositions([row({ quantity: 1, price: 2 })]);
  const chains = new Map<string, ChainData>([
    [
      chainKey('LHX', '2026-11-20'),
      chain({ calls: [{ strike: 320, bid: 3, ask: 3.4, delta: 0.5, theta: -0.1, impliedVolatility: 0.5 }] })
    ]
  ]);
  const rows = valueOptions(positions, chains);
  const lines = renderMarketDataBlock(rows, chains, '2026-11-15T14:40:43.000Z', {
    missing: [{ ticker: 'AMD', message: '2026-12-18: the trading CLI exited with code 1' }]
  });
  const text = lines.join('\n');

  const time = text.indexOf('Prices fetched: 2026-11-15 14:40 UTC');
  const source = text.indexOf('yfinance through the local trading CLI');
  const spot = text.indexOf('spot USD 272.35, DTE 5');
  const contract = text.indexOf('| LHX 2026-11-20 call 320.000 |');
  assert.ok(time > 0, 'the fetch time comes first');
  assert.ok(source > time, 'the source follows the time');
  assert.ok(spot > source, 'the spot follows the source');
  assert.ok(contract > spot, 'the contract line follows the spot');

  assert.match(text, /Multiplier 100/);
  assert.match(text, /USD 3\.20/, 'the mark uses the money format');
  assert.match(text, /USD 320\.00/, 'the position value uses the multiplier 100');
  assert.match(text, /USD 120\.00/, 'the unrealized P&L is stated');
  assert.match(text, /50\.0%/, 'the implied volatility is a percentage');
  assert.match(text, /Live option data is missing for AMD — 2026-12-18: the trading CLI exited with code 1/);
});

test('the block writes n/a for a missing number and names an omitted chain', () => {
  const positions = buildOptionPositions([row({ quantity: 1, price: 2 })]);
  const lines = renderMarketDataBlock(valueOptions(positions, new Map()), new Map(), '2026-11-15T14:40:43.000Z', {
    omitted: [chainKey('AMD', '2026-12-18')]
  });
  const text = lines.join('\n');
  assert.match(text, /\| LHX 2026-11-20 call 320\.000 \| 1 \| USD 320\.00 \| n\/a \| n\/a \| n\/a \| n\/a \| n\/a \| n\/a \|/);
  assert.match(text, new RegExp(`requested for ${MAX_MARKET_DATA_REQUESTS} chains only`));
  assert.match(text, /AMD\|2026-12-18/);
});

test('two identical requests inside the cache window start one process', async () => {
  const calls: { command: string; args: readonly string[] }[] = [];
  let clock = 1_000;
  const runner: MarketDataRunner = async (command, args) => {
    calls.push({ command, args });
    return { stdout: CLI_JSON, stderr: '', code: 0 };
  };
  const service = new MarketDataService({
    commandTemplate: '/usr/bin/python -m trading_mcp.trading_cli',
    runner,
    now: () => clock
  });

  const first = await service.fetchChains([{ ticker: 'LHX', expiry: '2026-11-20' }]);
  assert.equal(first.chains.size, 1);
  assert.equal(first.errors.length, 0);
  assert.equal(first.requested, 1);
  assert.deepEqual(calls[0]?.args.slice(0, 5), ['-m', 'trading_mcp.trading_cli', 'fetch', 'options', 'LHX']);

  clock += 60_000;
  const second = await service.fetchChains([{ ticker: 'LHX', expiry: '2026-11-20' }]);
  assert.equal(second.chains.size, 1);
  assert.equal(calls.length, 1, 'the second request inside ten minutes uses the cache');

  clock += MARKET_DATA_CACHE_TTL_MS + 1;
  await service.fetchChains([{ ticker: 'LHX', expiry: '2026-11-20' }]);
  assert.equal(calls.length, 2, 'an expired entry is fetched again');
});

test('the service deduplicates, caps the pairs and reports the error without throwing', async () => {
  const keys: string[] = [];
  const runner: MarketDataRunner = async (_command, args) => {
    const ticker = args[4] ?? '';
    keys.push(ticker);
    return ticker === 'AMD'
      ? { stdout: '', stderr: 'boom: no chain', code: 1 }
      : { stdout: CLI_JSON, stderr: '', code: 0 };
  };
  const service = new MarketDataService({ commandTemplate: '/usr/bin/python -m x', runner, now: () => 0 });

  const requests = [
    { ticker: 'LHX', expiry: '2026-11-20' },
    { ticker: 'LHX', expiry: '2026-11-20' },
    ...Array.from({ length: MAX_MARKET_DATA_REQUESTS + 3 }, (_unused, index) => ({
      ticker: `T${index}`,
      expiry: '2026-11-20'
    }))
  ];
  const result = await service.fetchChains(requests);
  const unique = MAX_MARKET_DATA_REQUESTS + 4;
  assert.equal(result.requested, unique, 'the duplicate pair is counted once');
  assert.equal(keys.length, MAX_MARKET_DATA_REQUESTS, 'at most MAX_MARKET_DATA_REQUESTS processes run');
  assert.equal(result.omitted.length, unique - MAX_MARKET_DATA_REQUESTS);

  const failing = await new MarketDataService({
    commandTemplate: '/usr/bin/python -m x',
    runner: async () => ({ stdout: '', stderr: 'boom: no chain', code: 1 }),
    now: () => 0
  }).fetchChains([{ ticker: 'AMD', expiry: '2026-12-18' }]);
  assert.equal(failing.chains.size, 0);
  assert.equal(failing.errors.length, 1);
  assert.match(failing.errors[0]?.message ?? '', /exited with code 1: boom: no chain/);

  const empty = await new MarketDataService({ commandTemplate: '   ' }).fetchChains([
    { ticker: 'LHX', expiry: '2026-11-20' }
  ]);
  assert.equal(empty.errors.length, 1);
  assert.match(empty.errors[0]?.message ?? '', /marketDataCommand is empty/);
});
