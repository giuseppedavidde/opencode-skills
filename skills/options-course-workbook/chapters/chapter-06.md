# Chapter 6: Demystifying Delta

## Core Idea
**Delta measures how much an option's price changes per $1 move in the underlying**. ATM options have delta ~50 (50% chance of finishing ITM). Delta neutral trading combines long/short deltas to achieve a total position delta of zero.

## Frameworks Introduced
- **Delta Calculation**: Change in premium ÷ change in underlying price (× 100 for contracts)
- **Fixed vs Variable Deltas**: 100 shares of stock = fixed +100 (long) or −100 (short). Option deltas are **variable** — they change as the underlying moves
- **Delta Ranges**: ITM options = delta >50 (approaches 100 deep ITM). ATM = ~50. OTM = <50. OTM deep = near 0
- **Delta Signs**: Long calls = positive; Short calls = negative; Long puts = negative; Short puts = positive

## Key Concepts
- ATM options move at roughly half the rate of the underlying (delta ~0.50)
- Deep ITM options act nearly like the underlying (delta ~1.00) — useful as stock proxies via LEAPS
- Delta neutral trades rely on **magnitude**, not direction. They require **high liquidity** and **high volatility**
- Delta is also interpreted as **probability of expiring ITM**: delta of 25 = 25% chance

## Key Takeaways
1. Delta tells you both **directional exposure** and **probability of ITM finish**
2. Position delta = sum of all individual deltas in a trade
3. Delta neutral is ideal for floor traders and retail traders seeking to profit from volatility, not direction
4. Adjust trades back to delta neutral as the underlying moves
