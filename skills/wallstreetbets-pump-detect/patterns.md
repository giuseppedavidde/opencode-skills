# Composite Patterns — WallStreetBets Pump Detect

These are multi-dimensional pattern signatures that strongly bias toward a specific action. When 3+ conditions align, confidence increases. Patterns integrate WSB hype data with `stock-crypto-analysis` framework scores.

---

## 🔥 The Classic Meme Squeeze (Strong Buy — Urgent)

**Components**: WSB Early Phase + SI > 20% + Borrow Fee rising + Volume spike

**Signal**: A ticker with 3-15 new WSB posts in the last 24 hours (Early-to-Mid FOMO), short interest above 20% of float, borrow fee increasing day-over-day, volume 2-5x the 20-day average. Posts are a mix of genuine DD and meme hype. Price is up 10-30% from the recent low but still below 52w high.

**Scores**: Hype 25-60, Squeeze Setup 60-90, Sentiment bullish 60-80%

**Expected Unified**: 50-85 → **Short-Term Spec or Long-Term Invest**

**Management**: Entry ASAP. Synthetic Long 2:1 (sell 2 puts at 15-20% below current, buy 1 call at 10-20% OTM). Stop loss at swing low pre-pump. Target: previous resistance level or 1.5x the initial pump move. Watch borrow fee daily — if it drops 30%+, take profits.

**Historic examples**: GME Jan '21, AMC May '21, KOSS, BBBY Aug '22

---

## 📊 DD-Pump Continuation (Cautious Buy)

**Components**: High DD ratio > 40% + Strong analysis + Mid FOMO + Fundamental catalyst

**Signal**: A ticker where > 40% of WSB posts have "DD" or "Technical Analysis" flair, the posts contain detailed analysis (not just memes), the ticker has a real catalyst (earnings beat, product launch, regulatory approval). Hype score 30-60. Upvote ratio > 0.90. FOMO Phase is Mid but the DD posts provide fundamental justification.

**Scores**: Hype 30-60, Post Authority 60-80, Sentiment 60-80%

**Expected Unified**: 60-85 → **Long-Term Invest or Short-Term Spec (Bullish)**

**Management**: Entry on pullback after the initial pump wave. Do NOT chase. Use limit order at 10ema or 20ema. Sizing 2-3% of portfolio. Options: Bull Put Spread (45 DTE) if IV high, or Synthetic Long 2:1 if score ≥ 70.

**Historic examples**: RKLB Mar '26 (Neutron update), PLTR earnings, NVDA pre-earnings

---

## 💀 Fake Pump / Bagholder Trap (Strong Avoid or Short)

**Components**: Late FOMO + Declining engagement + Price extended + Short interest falling

**Signal**: Hype score 70+, but engagement is declining (fewer comments per post, lower upvote ratios despite high post count). Price has already moved 100%+. Short interest dropped from 30%+ to < 10% (squeeze already played out). "Diamond hands" and "hold the line" posts dominate — defensive language. News coverage is mainstream.

**Scores**: Hype 70-100 (but declining), Squeeze Setup 0-10 (exhausted)

**Expected Unified**: 30-50 → **Avoid** (or Short if system allows)

**Management**: DO NOT BUY. If you have a position: sell immediately. If you want to short: Bear Call Spread (sell call at 0.30 delta, buy call at 0.15 delta, 30-45 DTE).

**Historic examples**: BBBY Aug '22 (post-peak), GME Jun '21 (post-January peak), AMC Jun '21

---

## 📈 Earnings Hype Pump (Options Play)

**Components**: Pre-earnings + High DD ratio + IV expansion + Volume buildup

**Signal**: WSB posts about an upcoming earnings report > 5 days away (allows time for options setup). DD posts analyzing the earnings potential dominate. IV is expanding (options getting more expensive). Price is in a tight range (accumulation before catalyst). Hype score 30-50 (building, not peaked).

**Scores**: Hype 30-50 (rising), Post Authority 60-80, Squeeze Setup 0-30 (not the driver)

**Expected Unified**: 60-85 → **Short-Term Spec (Bullish)**

**Management**: Enter 5-10 days before earnings. Options strategy depends on thesis:
- **Bullish thesis**: Bull Call Spread (buy ATM call, sell OTM call, 45 DTE covering earnings)
- **Neutral-to-bullish**: Synthetic Long 2:1 if score ≥ 70
- **Volatile (direction unknown)**: Long Call Butterfly (if IV already high — don't buy straddle pre-earnings)

Exit: 50% at earnings gap up, 50% trailing stop. Never hold through earnings unless defined risk.

**Historic examples**: Any ticker with earnings and strong WSB DD

---

## 🪙 Crypto Pump on WSB (Mixed — Run Crypto Analysis)

**Components**: Crypto ticker mentioned + Moon language + No fundamental catalyst

**Signal**: A crypto ticker (BTC, ETH, SOL, DOGE, XRP, etc.) appears in WSB titles with "🚀", "moon", "wen $X", "crypto pump". No new fundamental catalyst (no ETF approval, no halving). Posts are mostly low-quality (Meme/Shitpost flair, low upvote ratio). Volume spikes but no Wyckoff accumulation structure.

**Scores**: Hype 40-80, Post Authority 10-30 (mostly memes), Squeeze Setup 0 (crypto doesn't have short interest)

**Expected Unified**: Run with `is_crypto=True` weights. Typically 30-60 → **Short-Term Spec or Avoid**

**Management**: Load `stock-crypto-analysis` with crypto weights (crypto layer = 35%). In most cases crypto WSB pumps are retail FOMO with no fundamental basis — score typically < 50 (Avoid). Only enter if:
1. Crypto layer score > 70 (strong on-chain, tokenomics, community)
2. FOMO phase = Early (not Late/Exit)
3. Price near support level (not extended)

If conditions met: buy spot (not leveraged), size 1-2% max. No options on crypto for WSB pumps.

**Historic examples**: DOGE May '21, BTC Nov '21 (near top), various altcoin pumps

---

## 🔍 Squeeze Setup Revival (Watchlist — Prepare)

**Components**: High SI still > 30% + Borrow fee elevated + Price dormant + WSB mentions low

**Signal**: A ticker with extremely high short interest (30%+), borrow fee elevated (50%+), but the price has not moved significantly. WSB mentions are LOW (0-3 posts/day) — the squeeze hasn't been discovered yet. Volume is 1x or below average. This is a pre-squeeze setup, not a pump.

**Scores**: Hype 0-15, Squeeze Setup 80-100

**Expected Unified**: 50-70 → **Short-Term Spec** (pre-squeeze, high R/R)

**Management**: Enter slowly. Accumulate 2-3% position over several days. Do NOT post about it on WSB (calling attention triggers retail and reduces your edge). Options: Cash-Secured Put (put at 20% below current, 45 DTE) to collect premium while waiting. If price stays flat, collect theta. If price drops, you enter the shorted stock cheaper. Watch for the catalyst that ignites the squeeze.

**Historic examples**: GME pre-Jan '21 (SI 100%+ but price flat for months), many small-caps

---

## Pattern Quick-Reference Matrix

| Pattern | FOMO Phase | Entry? | Strategy | Risk Level |
|---------|:----------:|:------:|----------|:----------:|
| Classic Meme Squeeze | Early-Mid | ✅ Urgent | Syn Long 2:1 / Bull Put Spread | Alto |
| DD-Pump Continuation | Mid | ✅ Cautious | Bull Put Spread / Syn Long 2:1 | Medio |
| Fake Pump / Bag Trap | Late-Exit | ❌ NO | Bear Call Spread (short) | Basso |
| Earnings Hype Pump | Pre-earnings | ✅ Setup | Bull Call Spread / Butterfly | Medio |
| Crypto Pump | Early-Late | ⚠️ Conditional + crypto analysis | Spot only, 1-2% max | Molto Alto |
| Squeeze Setup Revival | Pre-pump | ✅ Accumulate | Cash-Secured Put, poi Syn Long | Medio-Alto |
