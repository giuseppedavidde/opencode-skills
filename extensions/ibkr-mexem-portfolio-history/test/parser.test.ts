import assert from 'node:assert/strict';
import test from 'node:test';
import { FlexApiError, FlexEmptyError, FlexParseError } from '../src/flex/errors.ts';
import {
  combineDateTime,
  deriveRealizedPnl,
  detectQueryType,
  isClosingRow,
  parseEnvelope,
  parseReport,
  parseSendRequestResponse,
  parseTrades,
  toNumber
} from '../src/flex/parser.ts';
import { formatBaseAmount } from '../src/core/format.ts';
import {
  INLINE_ACTIVITY_DUPLICATE,
  INLINE_AMD_FIFO_BASE,
  INLINE_CLOSE_USD_NO_BASE_FIGURE,
  INLINE_CLOSE_USD_WITH_BASE_FIGURE,
  INLINE_CLOSE_WITHOUT_FIFO,
  INLINE_COMPACT_DATES,
  INLINE_UNKNOWN_BASE,
  fixture
} from './helpers.ts';

test('parses every TradeConfirm row from the fixture', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  assert.equal(trades.length, 14);
  assert.equal(trades[0]?.tradeDate, '2023-12-20', 'rows are sorted chronologically');
  assert.equal(trades[trades.length - 1]?.tradeDate, '2024-04-05');
});

test('maps scalar fields and normalises signs', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const close = trades.find((trade) => trade.symbol === 'AAPL' && trade.tradeDate === '2024-01-12');
  assert.ok(close);
  assert.equal(close.buySell, 'SELL');
  assert.equal(close.quantity, 10);
  assert.equal(close.tradePrice, 160);
  assert.equal(close.proceeds, 1600);
  assert.equal(close.commission, -1);
  assert.equal(close.commissionCost, 1);
  assert.equal(close.netCash, 1599);
  assert.equal(close.currency, 'EUR');
  assert.equal(close.fifoPnlRealized, 99);
  assert.equal(close.realizedPnl, 99);
  assert.equal(close.pnlSource, 'fifo');
  assert.equal(close.openCloseIndicator, 'C');
  assert.equal(close.orderReference, 'ORD-2');
  assert.equal(close.accountId, 'U0000001');
});

test('decodes XML entities in descriptions', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const spy = trades.find((trade) => trade.symbol === 'SPY');
  assert.equal(spy?.description, 'SPDR S&P 500 ETF');
});

test('opening trades carry no realized P&L', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const open = trades.find((trade) => trade.symbol === 'AAPL' && trade.tradeDate === '2024-01-05');
  assert.ok(open);
  assert.equal(open.fifoPnlRealized, null);
  assert.equal(open.realizedPnl, null);
  assert.equal(open.pnlSource, 'none');
});

test('timestamp is local naive time built from tradeDate and tradeTime', () => {
  const trades = parseTrades(fixture('trades-sample.xml'));
  const close = trades.find((trade) => trade.symbol === 'AAPL' && trade.tradeDate === '2024-01-12');
  assert.equal(close?.timestamp, new Date(2024, 0, 12, 10, 5, 0, 0).getTime());
});

test('fallback uses proceeds - commission only for closing rows', () => {
  const withFallback = parseTrades(INLINE_CLOSE_WITHOUT_FIFO, { fallbackFromProceeds: true });
  assert.equal(withFallback.length, 2);
  assert.equal(withFallback[0]?.fifoPnlRealized, null);
  assert.equal(withFallback[0]?.realizedPnl, 1099);
  assert.equal(withFallback[0]?.pnlSource, 'proceeds');
  assert.equal(withFallback[1]?.realizedPnl, 1099, 'C;O indicator still counts as a close');
  assert.equal(withFallback[1]?.pnlSource, 'proceeds');

  const withoutFallback = parseTrades(INLINE_CLOSE_WITHOUT_FIFO, { fallbackFromProceeds: false });
  assert.equal(withoutFallback[0]?.realizedPnl, null);
  assert.equal(withoutFallback[0]?.pnlSource, 'none');
});

test('accepts compact IBKR dates and times', () => {
  const trades = parseTrades(INLINE_COMPACT_DATES);
  assert.equal(trades.length, 1);
  assert.equal(trades[0]?.timestamp, new Date(2024, 0, 31, 9, 30, 0, 0).getTime());
  assert.equal(trades[0]?.currency, 'EUR');
});

test('numeric parsing tolerates thousands separators and blanks', () => {
  assert.equal(toNumber('1,234.56'), 1234.56);
  assert.equal(toNumber('1234.56'), 1234.56);
  assert.equal(toNumber('1,5'), 1.5, 'comma decimal is not mistaken for a thousands separator');
  assert.equal(toNumber(''), 0);
  assert.equal(toNumber(undefined, 7), 7);
  assert.equal(toNumber('abc', -1), -1);
});

test('closing indicator detection', () => {
  assert.equal(isClosingRow('C'), true);
  assert.equal(isClosingRow('c'), true);
  assert.equal(isClosingRow('C;O'), true);
  assert.equal(isClosingRow('CLOSE'), true);
  assert.equal(isClosingRow('O'), false);
  assert.equal(isClosingRow(''), false);
});

test('deriveRealizedPnl prefers FIFO P&L and never double counts', () => {
  const base = { netCashInBase: null, netCash: 0, tradeCurrency: 'EUR', baseCurrency: 'EUR', fallbackFromProceeds: true };
  assert.deepEqual(
    deriveRealizedPnl({ ...base, fifoPnlRealized: 50, openCloseIndicator: 'C' }),
    { pnl: 50, source: 'fifo' }
  );
  assert.deepEqual(
    deriveRealizedPnl({ ...base, fifoPnlRealized: 0, openCloseIndicator: 'C' }),
    { pnl: 0, source: 'fifo' },
    'a real zero is preserved'
  );
  assert.deepEqual(
    deriveRealizedPnl({ ...base, fifoPnlRealized: null, openCloseIndicator: 'C', netCash: 998 }),
    { pnl: 998, source: 'proceeds' },
    'a trade already in the base currency may use the trade-currency net cash'
  );
  assert.deepEqual(
    deriveRealizedPnl({ ...base, fifoPnlRealized: null, openCloseIndicator: 'O', netCash: 998 }),
    { pnl: null, source: 'none' }
  );
});

test('the fallback never mixes currencies', () => {
  const usd = { fifoPnlRealized: null, openCloseIndicator: 'C', fallbackFromProceeds: true, netCash: 949.3, tradeCurrency: 'USD', baseCurrency: 'EUR' };

  assert.deepEqual(
    deriveRealizedPnl({ ...usd, netCashInBase: null }),
    { pnl: null, source: 'none' },
    'a USD row with no base figure must not contribute a USD amount to a base field'
  );
  assert.deepEqual(
    deriveRealizedPnl({ ...usd, netCashInBase: 821.657122 }),
    { pnl: 821.657122, source: 'proceeds' },
    'the base figure is used as-is'
  );
  assert.deepEqual(
    deriveRealizedPnl({ ...usd, netCashInBase: null, fallbackFromProceeds: false }),
    { pnl: null, source: 'none' }
  );
});

test('detects the base currency from ConversionRate toCurrency', () => {
  const report = parseReport(fixture('trades-activity-sample.xml'));
  assert.equal(report.baseCurrency, 'EUR');
  assert.equal(report.baseCurrencySource, 'conversionRates');
  assert.equal(report.conversionRates.length, 3);
  assert.ok(report.conversionRates.every((rate) => rate.toCurrency === 'EUR'));
  assert.deepEqual(report.warnings, []);
});

test('AccountInformation currency wins over ConversionRate', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1">
      <AccountInformation accountId="U1" currency="CHF" />
      <ConversionRates>
        <ConversionRate reportDate="20260102" fromCurrency="USD" toCurrency="EUR" rate="0.9123" />
      </ConversionRates>
      <Trades>
        <Trade symbol="AAPL" currency="USD" tradeDate="20260102" dateTime="20260102;100000" buySell="SELL" quantity="1" tradePrice="10" proceeds="10" netCash="9.5" fifoPnlRealized="2" tradeID="ACC-INFO" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;
  const report = parseReport(xml);
  assert.equal(report.baseCurrency, 'CHF');
  assert.equal(report.baseCurrencySource, 'account');
});

test('the setting override beats both detections', () => {
  const report = parseReport(fixture('trades-activity-sample.xml'), { baseCurrencyOverride: 'USD' });
  assert.equal(report.baseCurrency, 'USD');
  assert.equal(report.baseCurrencySource, 'override');
});

test('a missing base currency is UNKNOWN and never renders a dollar sign', () => {
  const report = parseReport(INLINE_UNKNOWN_BASE);
  assert.equal(report.baseCurrency, 'UNKNOWN');
  assert.equal(report.baseCurrencySource, 'unknown');
  assert.ok(report.warnings.some((line) => line.includes('base currency is unknown')));
  const rendered = formatBaseAmount(1234.56, report.baseCurrency);
  assert.equal(rendered, '1234.56 base');
  assert.equal(rendered.includes('$'), false);
});

test('the real AMD row keeps fifoPnlRealized as a base-currency amount', () => {
  const report = parseReport(INLINE_AMD_FIFO_BASE);
  assert.equal(report.baseCurrency, 'EUR');
  const closed = report.trades.find((trade) => trade.symbol === 'AMD   261218P00300000' && trade.realizedPnl !== null);
  assert.ok(closed);
  assert.equal(closed.realizedPnl, 756.800887);
  assert.equal(closed.pnlSource, 'fifo');
  assert.equal(closed.currency, 'USD', 'the trade currency is still USD');
  assert.equal(closed.fifoPnlRealized, 756.800887);
  const rendered = formatBaseAmount(closed.realizedPnl, report.baseCurrency);
  assert.match(rendered, /€756\.80/);
  assert.equal(rendered.includes('$'), false);
});

test('a closing USD row without a base figure yields pnlSource none', () => {
  const withoutBase = parseReport(INLINE_CLOSE_USD_NO_BASE_FIGURE);
  assert.equal(withoutBase.baseCurrency, 'EUR');
  const row = withoutBase.trades[0];
  assert.equal(row?.currency, 'USD');
  assert.equal(row?.realizedPnl, null);
  assert.equal(row?.pnlSource, 'none');

  const withBase = parseReport(INLINE_CLOSE_USD_WITH_BASE_FIGURE);
  const funded = withBase.trades[0];
  assert.equal(funded?.realizedPnl, 821.657122);
  assert.equal(funded?.pnlSource, 'proceeds');
});

test('empty input is a typed parse error, not a crash', () => {
  assert.throws(() => parseTrades('   '), (error: unknown) => error instanceof FlexParseError);
});

test('well-formed XML without trades raises FlexEmptyError', () => {
  assert.throws(
    () => parseTrades('<FlexQueryResponse><FlexStatements><FlexStatement /></FlexStatements></FlexQueryResponse>'),
    (error: unknown) => error instanceof FlexEmptyError
  );
});

test('error envelopes surface as FlexApiError with an actionable hint', () => {
  assert.throws(
    () =>
      parseTrades(
        '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>'
      ),
    (error: unknown) => {
      assert.ok(error instanceof FlexApiError);
      assert.equal(error.code, '1012');
      assert.match(error.userMessage, /Token has expired/);
      assert.match(error.userMessage, /Flex Web Service Configuration/);
      return true;
    }
  );
});

test('SendRequest envelope parsing', () => {
  const ok = parseSendRequestResponse(
    "<FlexStatementResponse timestamp='x'><Status>Success</Status><ReferenceCode>1234567890</ReferenceCode><url>legacy</url></FlexStatementResponse>"
  );
  assert.deepEqual(ok, { kind: 'reference', referenceCode: '1234567890' });

  const fail = parseSendRequestResponse(
    "<FlexStatementResponse timestamp='x'><Status>Fail</Status><ErrorCode>1015</ErrorCode><ErrorMessage>Token is invalid.</ErrorMessage></FlexStatementResponse>"
  );
  assert.equal(fail.kind, 'error');

  assert.equal(parseSendRequestResponse('').kind, 'unknown');
  assert.equal(parseSendRequestResponse('<html>nope</html>').kind, 'unknown');
});

test('envelope detection separates report from error and garbage', () => {
  assert.equal(parseEnvelope(fixture('trades-sample.xml')).kind, 'report');
  const error = parseEnvelope('<FlexStatementResponse><Status>Fail</Status><ErrorCode>1019</ErrorCode><ErrorMessage>busy</ErrorMessage></FlexStatementResponse>');
  assert.equal(error.kind, 'error');
  assert.equal(parseEnvelope('<html><body>gateway timeout</body></html>').kind, 'unknown');
  assert.equal(parseEnvelope('').kind, 'unknown');
});

test('combineDateTime rejects impossible dates without throwing', () => {
  assert.ok(Number.isNaN(combineDateTime('2024-02-31', '10:00:00')));
  assert.ok(Number.isNaN(combineDateTime('not-a-date', '')));
});

test('parseEnvelope accepts every documented report root shape', () => {
  const shapes = [
    '<?xml version="1.0" encoding="UTF-8"?><FlexQueryResponse><FlexStatements count="1" /></FlexQueryResponse>',
    '\n\n\t<?xml version="1.0" encoding="UTF-8"?>\n<FlexQueryResponse type="AF"><FlexStatements count="0" /></FlexQueryResponse>',
    '<?xml version="1.0"?><FlexStatement accountId="U0000001"><Trades /></FlexStatement>',
    '<FlexStatement accountId="U0000001"><Trades /></FlexStatement>'
  ];
  for (const shape of shapes) {
    const result = parseEnvelope(shape);
    assert.equal(result.kind, 'report', `expected a report for ${JSON.stringify(shape.slice(0, 60))}`);
  }
});

test('parseEnvelope rejects HTML pages and non-XML bodies', () => {
  assert.equal(parseEnvelope('<html><body>503 gateway timeout</body></html>').kind, 'unknown');
  assert.equal(parseEnvelope('<!DOCTYPE html><html><body>login</body></html>').kind, 'unknown');
  assert.equal(parseEnvelope('<FlexStatementResponse><Status>Fail</Status><ErrorCode>1019</ErrorCode></FlexStatementResponse>').kind, 'error');
  const csv = parseEnvelope('"ClientAccountID","CurrencyPrimary"\n"U1234567","USD"');
  assert.equal(csv.kind, 'unsupported');
  assert.match(csv.kind === 'unsupported' ? csv.detail : '', /not XML/);
});

/* ------------------------------------------------------------------ *
 * Activity Flex Query (type="AF"): <Trade> rows, one FlexStatement    *
 * per day, no openCloseIndicator.                                     *
 * ------------------------------------------------------------------ */

test('parses an Activity Flex Query and aggregates every FlexStatement', () => {
  const trades = parseTrades(fixture('trades-activity-sample.xml'));
  assert.equal(trades.length, 11, 'all three statements must contribute rows');
  const symbols = new Set(trades.map((trade) => trade.symbol));
  for (const symbol of ['FWRA', 'TSLA', 'VWCE', 'MSFT']) {
    assert.ok(symbols.has(symbol), `${symbol} from another statement must be present`);
  }
});

test('rows are collected from every statement, not only the first', () => {
  const blocks = Array.from({ length: 30 }, (_, index) => {
    const day = String(index + 1).padStart(2, '0');
    return (
      `<FlexStatement accountId="U1234567"><Trades><Trade accountId="U1234567" symbol="S${index}" ` +
      `tradeDate="202601${day}" dateTime="202601${day};100000" buySell="BUY" quantity="1" ` +
      `tradePrice="1" proceeds="-1" ibCommission="-1" netCash="-2" currency="EUR" tradeID="T${index}" />` +
      '</Trades></FlexStatement>'
    );
  }).join('');
  const xml = `<?xml version="1.0"?><FlexQueryResponse type="AF"><FlexStatements count="30">${blocks}</FlexStatements></FlexQueryResponse>`;
  assert.equal(parseTrades(xml).length, 30);
});

test('Activity rows take the commission from ibCommission and keep both currencies', () => {
  const trades = parseTrades(fixture('trades-activity-sample.xml'));
  const buy = trades.find((trade) => trade.symbol === 'FWRA' && trade.buySell === 'BUY');
  assert.ok(buy);
  assert.equal(buy.commission, -1.79877, 'commission must come from ibCommission');
  assert.equal(buy.commissionCost, 1.79877, 'the cost is sign-normalised');
  const totalCommission = trades.reduce((sum, trade) => sum + trade.commissionCost, 0);
  assert.ok(Math.abs(totalCommission - 16.24877) < 1e-6, `total commission was ${totalCommission}`);
  assert.deepEqual([...new Set(trades.map((trade) => trade.currency))].sort(), ['EUR', 'USD']);
  assert.deepEqual([...new Set(trades.map((trade) => trade.assetCategory))].sort(), ['OPT', 'STK']);
});

test('Activity rows build tradeTime and timestamp from dateTime', () => {
  const trades = parseTrades(fixture('trades-activity-sample.xml'));
  const buy = trades.find((trade) => trade.symbol === 'FWRA' && trade.buySell === 'BUY');
  assert.ok(buy);
  assert.equal(buy.tradeDate, '20260102');
  assert.equal(buy.tradeTime, '135015');
  assert.equal(buy.timestamp, new Date(2026, 0, 2, 13, 50, 15, 0).getTime());
  assert.equal(buy.openCloseIndicator, '', 'Activity rows carry no close indicator');
  assert.equal(buy.orderReference, '', 'Activity rows carry no order reference');
});

test('an Activity zero FIFO value is never treated as a realized result', () => {
  const trades = parseTrades(fixture('trades-activity-sample.xml'));

  const openBuy = trades.find((trade) => trade.symbol === 'FWRA' && trade.buySell === 'BUY');
  assert.equal(openBuy?.fifoPnlRealized, 0);
  assert.equal(openBuy?.realizedPnl, null, 'BUY with fifo 0 and no indicator is not a result');
  assert.equal(openBuy?.pnlSource, 'none');

  const closedSell = trades.find((trade) => trade.symbol === 'FWRA' && trade.buySell === 'SELL');
  assert.equal(closedSell?.fifoPnlRealized, 120.5);
  assert.equal(closedSell?.realizedPnl, 120.5, 'SELL with a non-zero fifo value is a result');
  assert.equal(closedSell?.pnlSource, 'fifo');

  const zeroSell = trades.find((trade) => trade.symbol === 'VWCE' && trade.quantity === 5);
  assert.equal(zeroSell?.fifoPnlRealized, 0);
  assert.equal(zeroSell?.realizedPnl, null, 'SELL with fifo 0 and no indicator is not a result');
  assert.equal(zeroSell?.pnlSource, 'none');
});

test('a row repeated in a second statement is counted once', () => {
  const trades = parseTrades(INLINE_ACTIVITY_DUPLICATE);
  assert.equal(trades.length, 1);
  assert.equal(trades[0]?.commission, -1.79877);
});

test('detectQueryType names the row shape and the declared type', () => {
  assert.deepEqual(detectQueryType(fixture('trades-activity-sample.xml')), { shape: 'AF', declaredType: 'AF' });
  assert.equal(detectQueryType(fixture('trades-sample.xml')).shape, 'TradeConfirm');
  assert.deepEqual(
    detectQueryType('<FlexQueryResponse type="AF"><FlexStatements count="0" /></FlexQueryResponse>'),
    { shape: 'unknown', declaredType: 'AF' }
  );
});

test('an empty report carries the fetch facts and the body snippet', () => {
  const xml =
    '<FlexQueryResponse type="AF"><FlexStatements count="3"><FlexStatement><Trades /></FlexStatement></FlexStatements></FlexQueryResponse>';
  assert.throws(
    () => parseTrades(xml, { fetch: { attempts: 7, elapsedMs: 42_000 } }),
    (error: unknown) => {
      assert.ok(error instanceof FlexEmptyError);
      assert.equal(error.diagnostics.attempts, 7);
      assert.equal(error.diagnostics.elapsedMs, 42_000);
      assert.equal(error.diagnostics.lastStatus, 'report');
      assert.match(error.diagnostics.lastBodySnippet ?? '', /FlexQueryResponse/);
      assert.match(error.userMessage, /Trade Confirmation/);
      assert.match(error.userMessage, /Trades/);
      return true;
    }
  );
});
