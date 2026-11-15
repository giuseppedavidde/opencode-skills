import { readFileSync } from 'node:fs';
import type { Trade } from '../src/core/types.ts';

export function fixture(name: string): string {
  return readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8');
}

export const INLINE_CLOSE_WITHOUT_FIFO = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U0000001">
      <ConversionRates>
        <ConversionRate reportDate="20240322" fromCurrency="USD" toCurrency="EUR" rate="0.92" />
      </ConversionRates>
      <Trades>
        <TradeConfirm accountId="U0000001" symbol="AMD" currency="EUR" tradeDate="2024-03-22" tradeTime="16:30:00" buySell="SELL" quantity="10" tradePrice="110.00" proceeds="1100.00" commission="-1.00" netCash="1099.00" openCloseIndicator="C" />
        <TradeConfirm accountId="U0000001" symbol="AMD" currency="EUR" tradeDate="2024-03-22" tradeTime="16:35:00" buySell="SELL" quantity="10" tradePrice="110.00" proceeds="1100.00" commission="-1.00" netCash="1099.00" openCloseIndicator="C;O" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;

export const INLINE_COMPACT_DATES = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse>
  <FlexStatements count="1">
    <FlexStatement>
      <Trades>
        <TradeConfirm symbol="AAPL" currency="eur" tradeDate="20240131" tradeTime="093000" buySell="SELL" quantity="1" tradePrice="10" proceeds="10" commission="-1" openCloseIndicator="C" fifoPnlRealized="1" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;

/** The same Activity row, repeated in two statements. It must be counted once. */
export const INLINE_ACTIVITY_DUPLICATE = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="2">
    <FlexStatement accountId="U1234567">
      <Trades>
        <Trade accountId="U1234567" symbol="FWRA" tradeDate="20260102" dateTime="20260102;135015" buySell="BUY" quantity="419" tradePrice="7.155" proceeds="-2997.95" ibCommission="-1.79877" netCash="-2999.74877" currency="EUR" assetCategory="STK" exchange="GETTEX2" fifoPnlRealized="0" tradeID="TRD-DUP" transactionID="TXN-DUP" />
      </Trades>
    </FlexStatement>
    <FlexStatement accountId="U1234567">
      <Trades>
        <Trade accountId="U1234567" symbol="FWRA" tradeDate="20260102" dateTime="20260102;135015" buySell="BUY" quantity="419" tradePrice="7.155" proceeds="-2997.95" ibCommission="-1.79877" netCash="-2999.74877" currency="EUR" assetCategory="STK" exchange="GETTEX2" fifoPnlRealized="0" tradeID="TRD-DUP" transactionID="TXN-DUP" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;


/** Real AMD evidence: the FIFO figure is base currency, the trade is USD. */
export const INLINE_AMD_FIFO_BASE = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U16517211">
      <ConversionRates>
        <ConversionRate reportDate="20261113" fromCurrency="USD" toCurrency="EUR" rate="0.8655" />
      </ConversionRates>
      <Trades>
        <Trade symbol="AMD   261218P00300000" buySell="BUY" quantity="1" tradePrice="0.71" proceeds="-71" netCash="-71.7" netCashInBase="-64.856235" fifoPnlRealized="756.800887" capitalGainsPnl="793.83308" fxPnl="-37.032193" currency="USD" tradeDate="20261016" dateTime="20261016;100000" accountId="U16517211" tradeID="AMD-OPEN" />
        <Trade symbol="AMD   261218P00300000" buySell="SELL" quantity="-1" tradePrice="9.5" proceeds="950" netCash="949.3" netCashInBase="821.657122" fifoPnlRealized="0" currency="USD" tradeDate="20261113" dateTime="20261113;100000" accountId="U16517211" tradeID="AMD-CLOSE" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;

/** Closing USD row with no FIFO and no base-currency figure. */
export const INLINE_CLOSE_USD_NO_BASE_FIGURE = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U16517211">
      <ConversionRates>
        <ConversionRate reportDate="20261113" fromCurrency="USD" toCurrency="EUR" rate="0.8655" />
      </ConversionRates>
      <Trades>
        <Trade symbol="AMD" currency="USD" tradeDate="20261113" dateTime="20261113;100000" buySell="SELL" quantity="10" tradePrice="9.5" proceeds="950" netCash="949.3" ibCommission="-0.7" openCloseIndicator="C" tradeID="NO-BASE" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;

/** Same row, but with the base-currency figure IBKR normally supplies. */
export const INLINE_CLOSE_USD_WITH_BASE_FIGURE = INLINE_CLOSE_USD_NO_BASE_FIGURE.replace(
  'netCash="949.3"',
  'netCash="949.3" netCashInBase="821.657122"'
);

/** No AccountInformation and no ConversionRate: the base currency is unknown. */
export const INLINE_UNKNOWN_BASE = `<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U16517211">
      <Trades>
        <Trade symbol="AAPL" currency="USD" tradeDate="20261113" dateTime="20261113;100000" buySell="SELL" quantity="10" tradePrice="195" proceeds="1950" netCash="1948.8" netCashInBase="1686.5" fifoPnlRealized="43.8" accountId="U16517211" tradeID="UNKNOWN-BASE" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>`;

/** Synthetic trade with an increasing timestamp; used for cap and pagination tests. */
export function syntheticTrade(index: number): Trade {
  const timestamp = Date.UTC(2024, 0, 1) + index * 3_600_000;
  const iso = new Date(timestamp).toISOString();
  return {
    symbol: `SYM${String(index % 7)}`,
    description: 'Synthetic',
    assetCategory: 'STK',
    tradeDate: iso.slice(0, 10),
    tradeTime: iso.slice(11, 19),
    timestamp,
    buySell: index % 2 === 0 ? 'BUY' : 'SELL',
    quantity: (index % 25) + 1,
    tradePrice: 10 + (index % 90) / 4,
    proceeds: 0,
    commission: -1,
    commissionCost: 1,
    netCash: 0,
    netCashInBase: null,
    currency: 'EUR',
    exchange: 'GETTEX2',
    orderReference: `ORD-${index}`,
    accountId: 'U0000001',
    openCloseIndicator: 'C',
    fifoPnlRealized: index % 11 === 0 ? null : (index % 40) - 20,
    capitalGainsPnl: index % 11 === 0 ? null : (index % 40) - 20,
    fxPnl: null,
    realizedPnl: index % 11 === 0 ? null : (index % 40) - 20,
    pnlSource: index % 11 === 0 ? 'none' : 'fifo',
    openTimestamp: null
  };
}

export function syntheticTrades(count: number): Trade[] {
  return Array.from({ length: count }, (_unused, index) => syntheticTrade(index));
}
