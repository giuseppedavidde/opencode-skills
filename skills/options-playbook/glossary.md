# Options Glossary

## Core Concepts
- **Option**: A contract giving the holder the right, but not the obligation, to buy or sell an underlying asset at a specified price within a specified time.
- **Call Option**: Right to BUY the underlying stock at the strike price.
- **Put Option**: Right to SELL the underlying stock at the strike price.
- **Premium**: The price paid by the buyer to the seller for an option contract. = Intrinsic Value + Time Value.
- **Strike Price (Exercise Price)**: The pre-agreed price per share at which stock may be bought or sold if the option is exercised.
- **Expiration Date**: The last day an option can be exercised. For equity options: third Friday of expiration month. For index options: typically Thursday before third Friday.
- **Underlying**: The asset (stock, index, ETF) on which the option is based.

## Moneyness
- **In-the-Money (ITM)**: Call — stock above strike. Put — stock below strike.
- **Out-of-the-Money (OTM)**: Call — stock below strike. Put — stock above strike.
- **At-the-Money (ATM)**: Stock price equals (or is nearest to) the strike price.
- **Intrinsic Value**: The amount an option is ITM. Only ITM options have intrinsic value.
- **Time Value**: Premium minus intrinsic value. OTM options have 100% time value.

## Position Types
- **Long**: Ownership of an option or stock. "I am long 10 calls" = I own 10 call contracts.
- **Short**: Sold an option/stock without owning it. "I am short 5 puts" = I sold 5 put contracts.
- **Writer**: The seller of an option contract.
- **Holder**: The buyer of an option contract.

## Exercise & Assignment
- **Exercise**: When the option owner invokes the right to buy (call) or sell (put) the underlying at the strike price.
- **Assignment**: When the option writer is required to fulfill their obligation (sell stock for a call, buy stock for a put).
- **Early Exercise**: Exercising an equity option before expiration (rare — usually only for deep ITM options with no time value).
- **Cash Settlement**: Index options settle in cash, not stock.

## The Greeks
- **Delta (Δ)**: Expected change in option price per $1 change in underlying. Calls: 0 to +1. Puts: 0 to -1. ATM ≈ 0.50. Also used as probability of finishing ITM.
- **Gamma (Γ)**: Rate of change of delta per $1 move in underlying. Highest for ATM, near-term options. "Acceleration."
- **Theta (Θ)**: Daily time decay — expected decrease in option price per day. Negative for long options, positive for short options.
- **Vega (ν)**: Expected change in option price per 1-point change in implied volatility. Higher for longer-term options.
- **Rho (ρ)**: Expected change in option price per 1% change in interest rates. Only significant for LEAPS.

## Volatility
- **Historical Volatility (HV)**: Annualized standard deviation of past stock price movements.
- **Implied Volatility (IV)**: The market's expectation of future volatility, derived from option prices.
- **Volatility Crush**: Sharp decline in IV after an event (e.g., earnings), devastating to long option positions.
- **Volatility Skew**: The pattern of IV across different strike prices. Typically OTM puts have higher IV than OTM calls (equity skew).
- **Volatility Term Structure**: IV across different expiration months.
- **Standard Deviation**: Statistical measure of price dispersion. ~68% of outcomes within 1 SD, ~95% within 2 SD.

## Spread Types
- **Vertical Spread**: Options with same expiration, different strikes. Can be debit or credit.
- **Horizontal Spread (Calendar)**: Options with same strike, different expirations.
- **Diagonal Spread**: Options with different strikes AND different expirations.
- **Bull Spread**: Profits from rising stock. Vertical call spread (debit) or vertical put spread (credit).
- **Bear Spread**: Profits from falling stock. Vertical put spread (debit) or vertical call spread (credit).
- **Debit Spread**: You pay to enter (net debit). Defined risk = debit paid.
- **Credit Spread**: You receive premium to enter (net credit). Defined risk = width minus credit.

## Common Multi-Leg Strategies
- **Straddle**: Same strike — long (or short) a call and put.
- **Strangle**: Different strikes — long (or short) an OTM call and OTM put.
- **Butterfly**: Three strikes — buy wings, sell body. Low cost, defined risk, precise pin.
- **Condor**: Four strikes — two inner strikes held, two outer bought. Wider profit zone than butterfly.
- **Iron Butterfly**: Short ATM straddle + OTM wings for protection. Credit strategy.
- **Iron Condor**: Short OTM put spread + short OTM call spread. Credit strategy.
- **Collar**: Own stock + long put + short call. Protective strategy.
- **Combination (Combo)**: Long call + short put = synthetic long stock. Short call + long put = synthetic short stock.
- **Covered Call**: Own stock + sell call. Income generation.
- **Protective Put**: Own stock + buy put. Insurance.
- **Married Put**: Stock + put purchased simultaneously.
- **Buy/Write**: Stock + call sold simultaneously (same as covered call opening).
- **Fig Leaf**: Long LEAPS call + short near-term call. Leveraged covered call.
- **Front Spread**: 1 long : 2 short ratio. Ratio vertical spread.
- **Back Spread**: 1 short : 2 long ratio. Directional volatility play.
- **Calendar Spread**: Long-term option + short-term option same strike.
- **Double Diagonal**: Two diagonal spreads (call + put) for neutral/theta strategy.

## Other Terms
- **Open Interest**: Number of outstanding option contracts. Higher = better liquidity.
- **LEAPS**: Long-term Equity AnticiPation Securities. Options with > 9 months to expiration.
- **LEAPS**: Leveraged = profit/loss multiplied versus owning stock. 1 contract = 100 shares.
- **Margin**: Cash or collateral required to hold certain option positions (naked options, spreads).
- **Stop-Loss Order**: An order to close a position at a specified price to limit losses.
- **Probability Calculator**: Tool to estimate likelihood an option finishes ITM.
- **Profit + Loss Calculator**: Tool to evaluate strategy outcomes across price/time.
- **Position Delta**: Net delta of all legs combined. Used for directional exposure management.
- **Rolling**: Closing an existing option position and opening a new one at a different strike/expiration.
- **Naked Option**: Short option position without any hedging position.
- **Cash-Secured Put**: Short put with enough cash reserved to buy stock if assigned.
