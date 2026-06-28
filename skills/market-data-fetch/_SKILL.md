---
name: market-data-fetch
description: "Standardized templates for fetching stock, ETF, and crypto market data using yfinance, CoinGecko, and Bitpanda. Triggers: 'fetch stock data', 'get crypto prices', 'market data', 'load portfolio', 'yfinance', 'coin gecko', 'yf.Ticker', 'CoinGeckoAPI', 'Data_for_Analysis'."
allowed-tools:
  - read
  - bash
  - task
orchestrator:
  parallel: true
  split_by: ticker
  chunk_size: 20
  merge: concat
---

# Market Data Fetch

Standardized patterns for fetching stock and crypto data, based on conventions across all your projects.

## Stock & ETF Data (yfinance)

### Single ticker — current price
```python
import yfinance as yf

def get_current_price(symbol: str) -> float | None:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        return float(data["Close"].iloc[-1]) if not data.empty else None
    except Exception:
        return None
```

### Single ticker — full info
```python
def get_ticker_info(symbol: str) -> dict | None:
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info
    except Exception:
        return None
```

### Historical prices
```python
def get_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)
    return hist
```

### Multiple tickers at once
```python
def get_prices_batch(symbols: list[str]) -> dict[str, float | None]:
    result = {}
    for s in symbols:
        try:
            ticker = yf.Ticker(s)
            data = ticker.history(period="1d")
            result[s] = float(data["Close"].iloc[-1]) if not data.empty else None
        except Exception:
            result[s] = None
    return result
```

### Ticker conventions for your projects
| Type | Example | yfinance symbol |
|------|---------|----------------|
| US stock | AAPL | `AAPL` |
| Milan ETF | SP5A.MI | `SP5A.MI` |
| Crypto-EUR | BTC | `BTC-EUR` |
| Crypto-USD | ETH | `ETH-USD` |

If a symbol has no `-`, append `-EUR` for crypto pairs:
```python
yf_symbol = f"{symbol}-EUR" if "-" not in symbol else symbol
```

### Fundamentals (quarterly financials)
```python
def get_fundamentals(symbol: str) -> dict:
    tk = yf.Ticker(symbol)
    return {
        "pe_ratio": tk.info.get("trailingPE"),
        "market_cap": tk.info.get("marketCap"),
        "dividend_yield": tk.info.get("dividendYield"),
        "eps": tk.info.get("trailingEps"),
        "sector": tk.info.get("sector"),
        "long_business_summary": tk.info.get("longBusinessSummary", "")[:1000],
    }
```

### Dividend history
```python
def get_dividend_years(ticker: yf.Ticker) -> int:
    divs = ticker.dividends
    return len(divs.index.year.unique()) if not divs.empty else 0
```

## Crypto Data

### Option A: CoinGecko (preferred for crypto volume/market data)

**API Key (demo plan, 30 calls/min, no credit card):**
```
COINGECKO_API_KEY="CG-EoA39f23q3bCsnkGuDuz11vP"
```

Best practice: load from environment (already set in your `.env` files):
```python
from pycoingecko import CoinGeckoAPI
import os

cg_key = os.getenv("COINGECKO_API_KEY")
cg = CoinGeckoAPI(demo_api_key=cg_key) if cg_key else CoinGeckoAPI()
```

Alternatively, for standalone scripts, use the key directly:
```python
cg = CoinGeckoAPI(demo_api_key="CG-EoA39f23q3bCsnkGuDuz11vP")
```

**Get current price (single):**
```python
def coingecko_price(coin_id: str = "bitcoin", vs_currency: str = "eur") -> float | None:
    try:
        data = cg.get_price(ids=coin_id, vs_currencies=vs_currency)
        return data[coin_id][vs_currency]
    except Exception:
        return None
```

**Get current price (multiple coins at once):**
```python
def coingecko_prices_batch(
    coin_ids: list[str], vs_currency: str = "eur"
) -> dict[str, float]:
    try:
        data = cg.get_price(ids=",".join(coin_ids), vs_currencies=vs_currency)
        return {cid: vals[vs_currency] for cid, vals in data.items()}
    except Exception:
        return {}
```

**Search coin ID from symbol:**
```python
def coingecko_search_id(symbol: str) -> str | None:
    try:
        res = cg.search(symbol)
        if res and "coins" in res and len(res["coins"]) > 0:
            return res["coins"][0]["id"]
    except Exception:
        return None
    return None
```

**Historical market chart (prices, market caps, volumes):**
```python
def coingecko_chart(
    coin_id: str, days: int = 30, vs_currency: str = "eur"
) -> dict:
    return cg.get_coin_market_chart_by_id(
        id=coin_id, vs_currency=vs_currency, days=days
    )
# Returns: {"prices": [[ts, price], ...],
#            "market_caps": [[ts, mcap], ...],
#            "total_volumes": [[ts, vol], ...]}
```

**Extended coin data (categories, description, links, genesis date):**
```python
def coingecko_coin_info(coin_id: str) -> dict:
    return cg.get_coin_by_id(id=coin_id)
```

**Trending coins (top 7 searched on CoinGecko):**
```python
def coingecko_trending() -> list[dict]:
    data = cg.get_search_trending()
    return data.get("coins", [])
```

**Simple price with 24h change:**
```python
def coingecko_price_with_change(
    coin_id: str, vs_currency: str = "eur"
) -> dict | None:
    try:
        data = cg.get_price(
            ids=coin_id,
            vs_currencies=vs_currency,
            include_24hr_change=True,
        )
        return data.get(coin_id)
    except Exception:
        return None
# Returns: {"eur": 123.45, "eur_24h_change": 2.34}
```

**All coin IDs for mapping symbols:**
```python
def coingecko_all_coins() -> list[dict]:
    """Returns list of {id, symbol, name} for all coins."""
    return cg.get_coins_list()
```

### Option B: Bitpanda public API (no key needed, EUR only)
```python
import requests

def get_bitpanda_prices() -> dict[str, float]:
    url = "https://api.bitpanda.com/v1/ticker"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                sym: float(rates["EUR"])
                for sym, rates in data.items()
                if "EUR" in rates
            }
    except Exception:
        return {}
    return {}
```

### Option C: yfinance crypto pairs
Same as stock pattern — just use `BTC-EUR`, `ETH-USD`, `SOL-EUR`, etc.

## Portfolio CSV Loading

### Load from Data_for_Analysis
```python
import pandas as pd
from pathlib import Path

DATA_DIR = Path.home() / "Progetti/Github/Data_for_Analysis"

def load_stock_portfolio() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "My_Portfolio.csv", sep=";")

def load_crypto_portfolio() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "Crypto_Portfolio_csv.csv")
```

### Calculate gain/loss with current prices
```python
def calculate_gain_loss(df: pd.DataFrame, prices_dict: dict) -> pd.DataFrame:
    results = []
    for _, row in df.iterrows():
        symbol = row["asset_collect"]
        shares = row["amount_asset_collect"]
        invested = row["amount_fiat_collect"]
        current_price = prices_dict.get(symbol)

        if current_price is not None:
            current_value = shares * current_price
            gain = current_value - invested
            gain_pct = (gain / invested) * 100 if invested else 0
        else:
            current_value = gain = gain_pct = None

        results.append({
            "asset": symbol,
            "shares": shares,
            "invested": invested,
            "current_price": current_price,
            "current_value": current_value,
            "gain": gain,
            "gain_pct": gain_pct,
        })
    return pd.DataFrame(results)
```

## Best Practices (from your codebase)

### Caching (Streamlit)
```python
import streamlit as st

@st.cache_data(ttl=900)  # 15 min
def fetch_prices_cached():
    ...
```

### Caching (generic)
```python
import time
from functools import lru_cache
from datetime import timedelta

def ttl_cache(seconds: int):
    def decorator(func):
        cache = {}
        def wrapper(*args, **kwargs):
            key = (args, tuple(kwargs.items()))
            now = time.monotonic()
            if key in cache and now - cache[key][0] < seconds:
                return cache[key][1]
            result = func(*args, **kwargs)
            cache[key] = (now, result)
            return result
        return wrapper
    return decorator
```

### Pydantic models for price data
```python
from pydantic import BaseModel
from datetime import datetime

class PriceQuote(BaseModel):
    symbol: str
    price: float
    currency: str = "EUR"
    timestamp: datetime = datetime.now()

class PortfolioHolding(BaseModel):
    asset: str
    shares: float
    invested: float
    current_price: float | None = None
    current_value: float | None = None
    gain: float | None = None
    gain_pct: float | None = None
```

### Error resilience
- Always wrap API calls in `try/except` with `None` fallback
- Set explicit `timeout` on `requests.get(..., timeout=10)`
- Never assume a symbol format — check for `-` before appending `-EUR`
- Use `pd.isna()` before comparing indicator values (they can be NaN)

### Volume fallback chain
```python
def get_volume_data(symbol: str) -> tuple[float, float, str]:
    """Returns (current_volume, avg_volume, source)."""
    # 1. Try CoinGecko (most reliable for crypto)
    try:
        cg_id = coingecko_search_id(symbol)
        if cg_id:
            chart = coingecko_chart(cg_id, days=30)
            vols = [v[1] for v in chart.get("total_volumes", [])]
            if vols:
                return vols[-1], sum(vols[-20:]) / min(20, len(vols)), "CoinGecko"
    except Exception:
        pass
    # 2. Fallback to yfinance
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        if "Volume" in hist.columns and not hist.empty:
            vols = hist["Volume"].values
            return float(vols[-1]), float(vols[-20:].mean()), "Yahoo Finance"
    except Exception:
        pass
    return 0.0, 0.0, "N/A"
```

### Technical indicators (pandas-native)
```python
def compute_rsi(data: pd.Series, periods: int = 14) -> pd.Series:
    delta = data.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=periods - 1, adjust=True, min_periods=periods).mean()
    ma_down = down.ewm(com=periods - 1, adjust=True, min_periods=periods).mean()
    return 100 - (100 / (1 + ma_up / ma_down))
```

## CoinGecko API Key Setup

Add to your `.env` files or export in shell:
```
COINGECKO_API_KEY="CG-EoA39f23q3bCsnkGuDuz11vP"
```

Already present in your projects at:
- `StreamLitPrj/Crypto_Tracker/.env`
- `StreamLitPrj/IBKR_Trading/.env`

If you create a new project that needs crypto data, add it there too.

## Quick Reference: Common API Calls

| What you need | Function to use | Source |
|--------------|----------------|--------|
| Stock price | `yf.Ticker("AAPL").history(period="1d")` | yfinance |
| ETF price (Milan) | `yf.Ticker("SP5A.MI").history(period="1d")` | yfinance |
| Crypto price (EUR) | `yf.Ticker("BTC-EUR").history(period="1d")` | yfinance |
| Crypto price (all) | `get_bitpanda_prices()` | Bitpanda |
| Crypto price + 24h% | `coingecko_price_with_change("bitcoin")` | CoinGecko |
| Crypto detail | `CoinGeckoAPI().get_price(ids="bitcoin", vs_currencies="eur")` | CoinGecko |
| Crypto chart+volume | `coingecko_chart("bitcoin", days=30)` | CoinGecko |
| CoinGecko ID lookup | `coingecko_search_id("BTC")` | CoinGecko |
| Trending coins | `coingecko_trending()` | CoinGecko |
| Stock fundamentals | `yf.Ticker("AAPL").info` | yfinance |
| Portfolio CSV | `pd.read_csv(DATA_DIR / "My_Portfolio.csv", sep=";")` | local |
| Historical data | `yf.Ticker("AAPL").history(period="1y")` | yfinance |
| Dividend history | `yf.Ticker("AAPL").dividends` | yfinance |
| Financial statements | `yf.Ticker("AAPL").quarterly_financials` | yfinance |
