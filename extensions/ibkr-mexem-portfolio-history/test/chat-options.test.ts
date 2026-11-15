import assert from 'node:assert/strict';
import test from 'node:test';
import { buildOptionPositions, openOptionPositions, parseOptionSymbol } from '../src/chat/optionSymbol.ts';
import type { TradeRow } from '../src/panel/protocol.ts';

function row(overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    date: '2026-10-16',
    time: '10:00:00',
    symbol: 'LHX   261120C00320000',
    buySell: 'BUY',
    quantity: 1,
    price: 0.71,
    currency: 'USD',
    realizedPnl: null,
    pnlSource: 'none',
    ...overrides
  };
}

test('the OCC-like symbol of the report parses into root, expiry, kind and strike', () => {
  assert.deepEqual(parseOptionSymbol('LHX   261120C00320000'), {
    root: 'LHX',
    expiry: '2026-11-20',
    kind: 'call',
    strike: 320
  });
  assert.deepEqual(parseOptionSymbol('AMD   261218P00300000'), {
    root: 'AMD',
    expiry: '2026-12-18',
    kind: 'put',
    strike: 300
  });
  assert.deepEqual(parseOptionSymbol('STX 261218P00490000'), {
    root: 'STX',
    expiry: '2026-12-18',
    kind: 'put',
    strike: 490
  });
});

test('a padded root with an internal space or a dot is kept whole', () => {
  assert.equal(parseOptionSymbol('BRK B 261120C00320000')?.root, 'BRK B');
  assert.equal(parseOptionSymbol('BRK.B 261120C00320000')?.root, 'BRK.B');
  assert.equal(parseOptionSymbol('  LHX   261120C00320000  ')?.root, 'LHX');
});

test('a stock symbol, an empty string and a malformed symbol return null', () => {
  assert.equal(parseOptionSymbol('LHX'), null);
  assert.equal(parseOptionSymbol('AAPL'), null);
  assert.equal(parseOptionSymbol(''), null);
  assert.equal(parseOptionSymbol('   '), null);
  assert.equal(parseOptionSymbol('261120C00320000'), null, 'a missing root is malformed');
  assert.equal(parseOptionSymbol('LHX   261120C00320'), null, 'seven strike digits are malformed');
  assert.equal(parseOptionSymbol('LHX   261120X00320000'), null, 'the kind must be C or P');
});

test('a bad date returns null instead of a contract on a wrong day', () => {
  assert.equal(parseOptionSymbol('LHX   261320C00320000'), null, 'month 13 does not exist');
  assert.equal(parseOptionSymbol('LHX   261140C00320000'), null, 'November has 30 days');
  assert.equal(parseOptionSymbol('LHX   261100C00320000'), null, 'month 00 does not exist');
  assert.equal(parseOptionSymbol('LHX   261229C00320000')?.expiry, '2026-12-29');
});

test('the signed quantity sums to the net position and the cash flow uses the multiplier 100', () => {
  const positions = buildOptionPositions([
    row({ quantity: 1, price: 0.71 }),
    row({ quantity: 1, price: 0.71 }),
    row({ buySell: 'SELL', quantity: -1, price: 9.5 })
  ]);
  assert.equal(positions.length, 1);
  const position = positions[0];
  assert.ok(position);
  assert.equal(position.netQuantity, 1);
  assert.equal(position.tradeCurrency, 'USD');
  assert.equal(position.rows.length, 3);
  assert.equal(Number(position.cashFlowPerContract.toFixed(4)), 71 + 71 - 950);
});

test('one contract per root, expiry, kind and strike, in a stable order', () => {
  const positions = buildOptionPositions([
    row({ symbol: 'STX 261218P00490000', quantity: -1, price: 1.2 }),
    row({ symbol: 'LHX   261120C00320000', quantity: 1, price: 0.71 }),
    row({ symbol: 'AMD   261218P00300000', quantity: 2, price: 3.4 }),
    row({ symbol: 'LHX   261120P00320000', quantity: 1, price: 1.1 }),
    row({ symbol: 'AAPL', quantity: 10, price: 195 })
  ]);
  assert.deepEqual(
    positions.map((position) => `${position.contract.root} ${position.contract.expiry} ${position.contract.kind} ${position.contract.strike}`),
    ['AMD 2026-12-18 put 300', 'LHX 2026-11-20 call 320', 'LHX 2026-11-20 put 320', 'STX 2026-12-18 put 490']
  );
});

test('openOptionPositions drops a flat contract and keeps buildOptionPositions complete', () => {
  const rows = [
    row({ quantity: 1, price: 0.71 }),
    row({ buySell: 'SELL', quantity: -1, price: 9.5 }),
    row({ symbol: 'AMD   261218P00300000', quantity: -2, price: 3.4 })
  ];
  assert.equal(buildOptionPositions(rows).length, 2, 'a closed contract stays inspectable');
  assert.deepEqual(
    openOptionPositions(rows).map((position) => [position.contract.root, position.netQuantity]),
    [['AMD', -2]]
  );
});

test('the realized sum uses the display value of the rows and is null without one', () => {
  const withPnl = buildOptionPositions([
    row({ quantity: 1, displayPnl: 12.5 }),
    row({ buySell: 'SELL', quantity: -1, displayPnl: -2.5 })
  ]);
  assert.equal(withPnl[0]?.realizedPnlSum, 10);
  assert.equal(buildOptionPositions([row()])[0]?.realizedPnlSum, null);
});
