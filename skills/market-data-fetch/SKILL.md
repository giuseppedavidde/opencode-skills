---


name: market-data-fetch
description: >
  Fetches market data via trading MCP. Use when user asks for
  "fetch data", "get price", "option chain", "stock data", "crypto price".
---

# Market Data Fetch

## Execution — Use MCP tools (server already running)

### Stock data
```
Call: fetch_stock_data(ticker="<TICKER>", period="1y")
```
Returns: current_price, OHLCV, info (PE, sector, marketCap...), indicators (MA50, MA200, RSI14, ATR14).

### Crypto data
```
Call: fetch_crypto_data(coin_id="<COIN>", period="1y")
```
Returns: current_price_usd, market_cap, OHLCV, CoinGecko info.

### Options chain
```
Call: fetch_options_chain(ticker="<TICKER>", expiry=None)
```
Returns: calls, puts with Greeks, IV metrics, P/C ratios.
Weekend fallback: cached data from last 7 days.

### CLI (standalone, terminal use)
```bash
trading-cli fetch stock AAPL --period 1y
trading-cli fetch crypto bitcoin --period 6mo
trading-cli fetch options AAPL --expiry 2026-09-18
```

## Data sources
- Stocks/ETFs: yfinance (free, no API key)
- Crypto: CoinGecko API (free tier, key: CG-EoA39f23q3bCsnkGuDuz11vP)
