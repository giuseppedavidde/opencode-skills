# Way of the Turtle — Trading Patterns

## Pattern 1: The Breakout Entry (Core Turtle Pattern)

**When**: Price exceeds the N-day high (long) or N-day low (short), where N=20 for short-term system, N=55 for long-term system. The breakout must be on the close, not intraday.

**How**:
1. Identify the highest high (or lowest low) of the last 20 days
2. Place a buy stop just above the 20-day high (or sell stop below the 20-day low)
3. Enter on the open of the day AFTER the breakout closes beyond the level
4. Size position using the N factor: 1 unit = 1% of account ÷ market ATR in dollars
5. Add up to 3 additional units on subsequent ½-N favorable moves (pyramiding)

**Trade-offs**:
- **Pros**: Captures every major trend; mechanically objective; statistically validated edge
- **Cons**: 65-70% losing trades; whipsaws in choppy markets; painful during trendless periods
- **Maximum drawdown expectation**: Equal to expected annual return (30% CAGR → 30% DD)

**Source**: Ch. 5, 9, 10, Bonus Chapter

---

## Pattern 2: Support/Resistance Breakdown Entry

**When**: A previously established support or resistance level breaks, indicating one side has won the psychological battle. Particularly powerful when the level has been tested 2+ times and held.

**How**:
1. Mark recent swing highs (resistance) and swing lows (support) — the more tests, the stronger the level
2. Wait for price to close beyond the level (not just intraday probe)
3. Enter in the direction of the break
4. Place stop just inside the broken level (~½ ATR beyond it)
5. The edge comes from the gap between traders' anchored perception and the new reality

**Trade-offs**:
- **Pros**: Tight logical stop (small risk); clear invalidation; exploits mass psychology
- **Cons**: False breakouts happen; requires patience to wait for the right level
- **Key insight**: The cost of being wrong is lowest at points of price instability

**Source**: Ch. 6

---

## Pattern 3: The Trend Filter (350/25-day MA)

**When**: Adding a trend filter to breakout signals to trade only in the direction of the dominant trend. Used in Donchian Trend system and Triple Moving Average system.

**How**:
1. Calculate 25-day EMA and 350-day EMA
2. If 25-day EMA > 350-day EMA → only take LONG signals
3. If 25-day EMA < 350-day EMA → only take SHORT signals
4. Ignore all signals against the dominant trend

**Trade-offs**:
- **Pros**: Filters out ~50% of losing counter-trend trades; improves win rate
- **Cons**: Misses the earliest part of trend reversals; can be wrong at major inflection points
- **Empirical evidence**: The Donchian Trend system with this filter had 39.7% win rate vs. unfiltered systems with lower rates

**Source**: Ch. 5, 10

---

## Pattern 4: Time-Based Exit (80-Day Rule)

**When**: Holding a position for a fixed time period regardless of price action. The Donchian Time Exit system exits after exactly 80 calendar days.

**How**:
1. Enter on a Donchian breakout with trend filter
2. No stop loss — none at all
3. Exit after 80 days from entry, regardless of P&L
4. That's the entire exit rule

**Trade-offs**:
- **Pros**: Surprisingly robust — outperformed all other systems in Nov 2006 shock with ZERO performance degradation; no stop-hunting; no emotional decisions
- **Cons**: Can give back enormous profits if trend reverses on day 10; psychologically brutal to watch
- **Key result**: CAGR 57.2%, MAR 1.31 — better than the stop-based Donchian Trend (CAGR 29.4%, MAR 0.80)
- **Implication**: A good **entry** edge alone can make a system profitable

**Source**: Ch. 10

---

## Pattern 5: Volatility-Based Position Sizing (The N Factor)

**When**: Every trade entry. The core Turtle innovation that normalizes risk across all markets.

**How**:
1. Calculate ATR(20) for the market — this is N
2. Convert N to dollars (contract multiplier × N)
3. Unit size = floor(1% of account equity ÷ dollar N)
4. For a $1M account with gold N = $1,000/contract → unit = 10 contracts
5. Apply hard limits: max 4 units per market, 6 per correlated group, 10-12 per direction

**Trade-offs**:
- **Pros**: Automatically reduces position size in volatile markets; same dollar risk per market; survived 1987 crash when stop-distance sizing would have blown up
- **Cons**: Requires ATR calculation; positions may seem counterintuitively small in quiet markets
- **Critical**: Unit limits matter — some markets in correlated groups lag and generate mostly losses

**Source**: Ch. 8, Bonus Chapter

---

## Pattern 6: Pyramiding (Adding to Winners)

**When**: The original trade moves in your favor by ½ N (half an ATR). Add another unit at the new level.

**How**:
1. Enter initial unit at breakout
2. If price moves ½ N in your favor, add 2nd unit
3. If price moves another ½ N, add 3rd unit
4. If price moves another ½ N, add 4th unit (max)
5. Each unit has its own stop at 2 N from its specific entry

**Trade-offs**:
- **Pros**: Maximizes exposure during the strongest trends; automatically scales into winners; the 4th unit often produces the highest R-multiples
- **Cons**: Increases average entry price; all units can be stopped out simultaneously in reversals; amplifies drawdowns at trend ends
- **Turtle reality**: Not all Turtles pyramided. Curtis often went all-in on the first signal.

**Source**: Ch. 9, Bonus Chapter

---

## Pattern 7: The Anti-Ego Setup (Systematic Discipline)

**When**: Every trade. More a meta-pattern than a market pattern — it's about the trader, not the market.

**How**:
1. Define ALL rules before trading (entries, exits, position size, risk limits)
2. Execute EVERY signal mechanically — no discretion
3. Keep a trade log: did you follow the rules? (not: did you make money?)
4. If you skip a signal and it would have won: note that following the system matters more than one trade
5. If you skip a signal and it would have lost: don't celebrate — you broke the rules

**Trade-offs**:
- **Pros**: Eliminates cognitive biases; backtestable; psychologically sustainable
- **Cons**: Boring; ego gets no credit for wins; requires faith during drawdowns
- **The Turtle advantage**: They had Rich Dennis's authority as a backstop for their faith

**Source**: Ch. 2, 4, 14

---

## Pattern Quick-Reference Matrix

| Pattern | Timeframe | Win Rate | Best Market State | Key Risk |
|---------|-----------|----------|-------------------|----------|
| Breakout (20-day) | Weeks-months | 35-40% | Trending & Quiet | Whipsaw in chop |
| S/R Breakdown | Days-weeks | 40-50% | Any with clear S/R | False breakout |
| Trend Filter (MA) | Months | +5-10% improvement | Trending | Late at reversals |
| Time Exit (80-day) | ~3 months | ~58% | Any trending | Early trend death |
| N Factor Sizing | Per trade | N/A | All | Gap risk |
| Pyramiding | Weeks | Fewer but bigger wins | Strong trends | Amplified reversals |
