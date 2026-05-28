# Chapter 5: Order Flow — Footprint, Imbalances & Patterns

## Core Idea
Order flow analysis (footprint) reveals the internal battle between aggressive and passive participants. Used ONLY on key trading zones (defined by context + Volume Profile), it helps validate entry triggers by identifying absorption (blocking) and initiative (directional aggression).

## Frameworks Introduced

- **Footprint Reading**: Read DIAGONALLY (BID at one level vs ASK at the level above), not horizontally. Buyers can be passive (BID) or aggressive (ASK); sellers can be passive (ASK) or aggressive (BID).

- **Imbalances**: Disproportionate volume (200-400%+ difference) between diagonal BID/ASK levels. Parameterized to avoid noise.
  - **When to use**: At predefined trading zones (VAH, VAL, VPOC, structure levels).
  - **How**: Configure minimum % disparity. Validate with price action.

- **Turning Pattern (Reversal)**
  - **Bearish Turn**: Buying Absorption (large ASK trades at candlestick top, blocking upward) + Initiative Selling (large BID trades at candlestick top, directional selling). Confirmed by downward move.
  - **Bullish Turn**: Selling Absorption (large BID trades at candlestick bottom, blocking downward) + Initiative Buying (large ASK trades at candlestick bottom, directional buying). Confirmed by upward move.
  - **When to use**: At supports/resistances where you expect reversal.
  - **How**: Look for absorption (high volume, no continuation) then initiative (high volume + closing in direction of trade + price follow-through).

- **Continuation Pattern**
  - **Control**: Initiative that appears during an already-established move. Requires at least 1-2 imbalances in the direction of the trend on a wide-range, high-volume candle.
  - **Test to Control**: Price pulls back to the control zone. Expect a new reversal pattern (takeover ± initiative) at that level.
  - **When to use**: Missed the turn entry; looking to join an established trend.
  - **How**: Identify control level → wait for price to test it → confirm with new initiative at the zone → enter.

- **Fractality**: The same patterns appear at all timeframes. A 3-candle reversal on the footprint = a session-level P/b pattern = a multi-day accumulation/distribution structure. The logic is identical; only time consumption differs.

## Key Concepts
- **Absorption (Takeover)**: Limit order blockade. Large traders place passive orders at a zone, preventing further price movement. Key signs: high volume, little-to-no price advance/decline, closing price AGAINST the imbalance direction.
- **Initiative**: Market order aggression. Large traders enter directionally. Key signs: high volume, closing IN FAVOR of imbalance, wide range.
- **Delta Rotation**: Used to confirm changing control. Example: Delta -536 → +607 suggests aggressive sellers were absorbed and buyers took over.
- **SOSbar/SOWbar in Order Flow**: A SOSbar (Sign of Strength) is confirmed by initiative buying (ASK imbalances). A SOWbar (Sign of Weakness) is confirmed by initiative selling (BID imbalances).

## Anti-patterns
- **Using Order Flow in isolation**: Without context (structure + Volume Profile), order flow is noise. Only analyze footprint at pre-defined trading zones.
- **Expecting perfect textbook patterns**: The market rarely shows ideal absorption + initiative in consecutive candles. Be flexible — prioritize initiative follow-through over absorption visibility.
- **Overtrading imbalances**: Not every 200% disparity is meaningful. Filter by zone relevance, candle context, and subsequent price reaction.

## Key Takeaways
1. Order flow is a CONFIRMATION tool, not a primary analysis tool. Context first, Volume Profile second, footprint third.
2. The ideal entry trigger: price at a defined trading zone → absorption visible (optional) → initiative appears → price follows through.
3. The "Test to Control" is Order Flow's equivalent of Wyckoff's LPS/LPSY — a pullback to a level where aggressive traders previously entered.
