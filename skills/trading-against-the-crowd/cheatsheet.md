# Cheatsheet: Sentiment Thresholds, Position Sizing & Exit Rules

## Sentiment Indicator Thresholds

| Indicator | Buy Signal (Too Bearish) | Sell Signal (Too Bullish) |
|-----------|-------------------------|--------------------------|
| CBOE Equity-Only Put/Call (EMA10-250) | > +10% deviation | < -10% deviation (short-term only) |
| CBOE Equity-Only Put/Call (EMA5-21) | Cross zero from above | Cross zero from below |
| CBOE Total Put/Call (EMA10-250) | > +10% deviation | < -10% deviation |
| Squeeze Play II Individual Stock (EMA50-100) | 10-day high > +5% | 10-day low < -5% |
| TSW (EMA21-50) | > +10% | < -10% |
| VIX/VXO (EMA21-50) | > +5% | < -5% |
| VIX Fast (EMA1-10) | > +5% | < -5% |
| Public Short Sales NPSR (EMA4-8) | High extreme | Low extreme |
| Advisory Opinion (EMA1-4W) | > +5% bears | < -5% bears |
| Bear News BNI (EMA4-8) | > +5% | < -5% |

## Price Trigger Rules

| System | Long Trigger | Short Trigger |
|--------|-------------|--------------|
| Squeeze Play I | Close > Prev Day High | Close < Prev Day Low |
| Squeeze Play II (Stocks) | Close > 3-Day High | Close < 3-Day Low |
| Squeeze Play II (VIX) | Close > 5-Day High | Close < 5-Day Low |
| Advisory Opinion (Weekly) | Close > Prev Week High | Close < Prev Week Low |
| Bear News | Close > Prev Week High | Close < Prev Week Low |

## Exit Rules

| System | Long Exit | Short Exit |
|--------|-----------|-----------|
| Squeeze Play I | EMA21-50 crosses zero from above to below | EMA21-50 crosses zero from below to above |
| Squeeze Play II (Stocks) | EMA50-100 10-day low < -5% | EMA50-100 10-day high > +5% |
| Squeeze Play II (LEAPS) | T+30 / T+60 / T+90 time stops | T+30 / T+60 / T+90 time stops |
| TSW (LEAPS) | T+30 / T+60 / T+90 time stops | T+30 / T+60 / T+90 time stops |
| Bear News (S&P 500) | Week 2-4 time stops | Week 3-4 time stops |

## Position Sizing

| Market | Account | Position | Risk Per Trade |
|--------|---------|----------|---------------|
| S&P 500 Futures | $30,000 | 1 contract | ~$5,000 (17%) |
| DJIA Futures | $10,000 | 1 contract | ~$2,000 (20%) |
| NASDAQ 100 Futures | $15,000 | 1 contract | ~$3,000 (20%) |
| Individual Stocks | $10,000 per stock | 50% margin | 10% max loss stop |
| LEAPS | $10,000 per subsystem | ITM LEAPS | Premium paid (10-15%) |

## Key Performance Benchmarks

- **Beat Buy/Hold**: Minimum condition for any system.
- **Win/Loss Ratio**: >1.5 is good; >2.0 is excellent.
- **Consecutive Losses**: >3 is problematic for most traders.
- **Reward/Risk Index**: >90 is excellent (max 100).
- **Buy/Hold Index**: >100 means system beat buy/hold.
- **System Close Drawdown**: Should be 0 or near 0 for viable systems.
- **Max Open Trade Drawdown**: Must survive margin requirements; LEAPS solve this.

## Rules of Thumb
- Sentiment-only = premature entries. Always pair with price trigger.
- Long signals are 2-3x more reliable than short signals. Consider long-only.
- LEAPS eliminate stop-loss whipsaw — use time stops instead.
- Equity-only put/call > CBOE total > OEX (for contrarian).
- VIX > VXO > VXN.
- Public short sales > put/call ratios > implied volatility > advisory opinion.
- Fear-based indicators (high put/call, high VIX, high shorting) outperform greed-based.
- Bad data can't produce good signals. Verify put/call ratio source and smoothing.
- Optimization should show broad profitability across parameters, not a single peak.
