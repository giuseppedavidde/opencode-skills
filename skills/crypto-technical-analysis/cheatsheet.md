# Crypto Technical Analysis Cheatsheet

## Indicator Quick Reference

| Indicator | Type | Range | Overbought | Oversold | Key Signal |
|-----------|------|-------|------------|----------|------------|
| RSI | Momentum | 0-100 | >70 (>75 crypto) | <30 (<25 crypto) | Divergence |
| MACD | Momentum | None | Histogram decreasing | Histogram increasing | Crossover |
| Stochastic | Leading | 0-100 | >80 | <20 | Cross below/above |
| MFI | Volume | 0-100 | >80 (or 90) | <20 (or 10) | Divergence |
| CCI | Momentum | Unbounded | >+100 | <-100 | Return to range |
| TSI | Momentum | Centerline | High values | Low values | Signal crossover |
| Bollinger Bands | Volatility | Price envelope | Touching upper | Touching lower | Band squeeze |
| Ichimoku Cloud | Composite | Cloud range | Above cloud | Below cloud | TK crossover |
| Parabolic SAR | Trend | At price | Dots above | Dots below | Dot cross |
| OBV | Volume | None | Rising | Falling | Divergence |

## Crypto-Specific Entry/Exit Rules

### Entry Rules (Combining Indicators)
1. **Trend Confirmation**: Price above 50/200 EMA for longs; below for shorts
2. **Momentum Entry**: RSI >50 (long) or <50 (short) + MACD crossover in same direction
3. **Volume Confirmation**: Volume >20-day average on breakout
4. **Pattern Trigger**: Breakout with 2 consecutive closes beyond S/R level
5. **Oscillator Confirmation**: Stochastic <20 then crossing >20 = buy; >80 then crossing <80 = sell

### Exit Rules
1. **Fixed Target**: 2:1 or 3:1 risk-reward ratio
2. **Trailing Stop**: 1.5× ATR below price (long) or above (short)
3. **Oscillator Exit**: RSI >75 (take profit long) or <25 (take profit short)
4. **Pattern Target**: Pattern height measured from breakout point (e.g., H&S = neckline to head distance)
5. **Time Stop**: If no movement in expected direction within X periods, exit

### Crypto Threshold Adjustments
- **RSI overbought**: Lower to 70 for BTC, raise to 75-80 for altcoins
- **RSI oversold**: Raise to 30 for BTC, lower to 20-25 for altcoins
- **Bollinger Bands**: Use 2.5-3 std dev for crypto (vs 2 for stocks)
- **MA periods**: 20/50/200 for daily; 50/100/200 for 4H (crypto moves faster)
- **Volume confirmation**: 1.5× average for BTC, 2× for altcoins

### Timeframe Selection
- **Scalping (minutes)**: RSI + Stochastic + 5/15 EMA cross
- **Day Trading (1H-4H)**: MACD + RSI + Bollinger Bands + S/R levels
- **Swing Trading (4H-1D)**: Ichimoku + Fibonacci + 50/200 MA cross
- **Position Trading (1W+)**: FA + halving cycles + macro S/R + 200 MA

### Divergence Trading
- **Bullish Divergence**: Price makes lower low, RSI/MFI makes higher low → BUY
- **Bearish Divergence**: Price makes higher high, RSI/MFI makes lower high → SELL
- **Hidden Bullish Divergence**: Price makes higher low, RSI makes lower low → TREND CONTINUATION (BUY)
- **Hidden Bearish Divergence**: Price makes lower high, RSI makes higher high → TREND CONTINUATION (SELL)

### Risk Management Rules
- **Per-trade risk**: 1-2% of portfolio maximum
- **Stop-loss placement**: Below most recent swing low (long) or above most recent swing high (short)
- **Daily loss limit**: Stop trading after 3 consecutive losses
- **Max positions**: 3-5 concurrent positions maximum (prevents overexposure)
- **Always trail stops** once 1:1 risk-reward is achieved

### Common Crypto Strategies
- **Golden Cross**: 50 MA crosses above 200 MA → buy (reliable on daily/weekly)
- **Death Cross**: 50 MA crosses below 200 MA → sell/hold cash (reliable for major downtrends)
- **Halving Cycle Strategy**: Buy 6 months before halving, sell 12-18 months after (Bitcoin)
- **Breakout + Retest**: Buy when price breaks resistance, then retests and holds as support
- **Oversold Bounce**: RSI <25 + bullish divergence + key support level → buy
