# Patterns — Market Accumulation Scanner

Composite patterns detected by the scanner. Each pattern is defined by a
specific combination of per-dimension scores that form a recognized setup
from the source frameworks.

## 1. Accumulation Spring (Strong Long)

**Source**: Wyckoff 2.0 + Trades About to Happen

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 70-100 | Spring detected, price in 30-60% of 1Y range |
| Volume Profile | 60-80 | D-Profile, price inside VA, vol ratio 1-2x |
| Price Action | 50-80 | RSI 30-50, 25ema flat or rising, cluster near support |
| Sentiment | 40-60 | SI 10-25%, moderate squeeze potential |
| Fundamentals | 30-60 | P/E < 25 if positive, or recovering negative |

**Expected Total Score**: 55-80
**Description**: Price broke below support (Spring), reversed, and is now
building cause in an accumulation range. Volume decreasing = supply drying up.
**Action**: Strong candidate for full stock-crypto-analysis.
**Caveat**: Needs confirmation — look for SOS bar or LPS pullback.

## 2. D-Profile Value Zone (Medium-Long)

**Source**: Volume Profile + Stock-Crypto-Analysis

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 40-70 | Neutral range, MA50 rising toward MA200 |
| Volume Profile | 70-90 | D-Profile, price at VPOC or inside VA |
| Price Action | 40-60 | RSI 40-60, low volatility, flat 25ema |
| Sentiment | 40-50 | SI < 10%, neutral |
| Fundamentals | 60-90 | P/E < 20, positive growth, low D/E |

**Expected Total Score**: 50-70
**Description**: Price oscillates around VPOC in a balanced profile. Fair
value zone with good fundamentals. Institutional accumulation without drama.
**Action**: Long-term investment candidate if fundamentals support.
**Caveat**: No immediate catalyst — needs patience. Set alert for range breakout.

## 3. P-Profile Breakout (Short-Term Momentum)

**Source**: Volume Profile + Price Action

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 60-90 | Markup Phase D/E, HH/HL |
| Volume Profile | 70-90 | P-Profile, price above VAH, vol ratio > 2x |
| Price Action | 70-90 | RSI 55-70, 25ema rising sharply, VPA bullish |
| Sentiment | 50-70 | SI 10-20%, institutional interest |
| Fundamentals | 30-60 | Growing but may have high P/E |

**Expected Total Score**: 55-75
**Description**: Aggressive buying, price breaking out of value area with
increasing volume. Bullish momentum established.
**Action**: Short-term speculation entry on pullback to VPOC.
**Caveat**: Chasing breakout is risky. Wait for BUEC (Back Up to Edge of
Creek). Use tight stop.

## 4. Squeeze Setup (Short-Term Speculative)

**Source**: Trading Against the Crowd + Sentiment

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 30-50 | Range, no clear phase |
| Volume Profile | 30-50 | Neutral or b-Profile |
| Price Action | 30-50 | RSI 30-45, weak but not crashing |
| Sentiment | 70-90 | SI > 20%, DTC > 5, Inst low |
| Fundamentals | 10-30 | Weak or negative |

**Expected Total Score**: 40-60
**Description**: High short interest, days to cover elevated, but price has
stabilized. Potential short squeeze if a catalyst hits.
**Action**: High-risk speculative entry. Tight sizing (1-2%).
**Caveat**: Not all high SI stocks squeeze. Many are value traps. Requires
catalyst (earnings, news, macro). Stop loss critical.

## 5. Golden Cross Accumulation (Medium-Long)

**Source**: Wyckoff 2.0 + Fundamentals

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 65-85 | Spring or late Phase C, MA50 rising above MA200 |
| Volume Profile | 50-70 | D-Profile, price transitioning from below to inside VA |
| Price Action | 60-80 | RSI 50-65, 25ema rising, healthy VPA |
| Sentiment | 40-60 | SI moderate, Inst growing |
| Fundamentals | 60-85 | Improving margins, revenue growth, reasonable P/E |

**Expected Total Score**: 60-80
**Description**: MA50 crossed above MA200 (golden cross) during accumulation
phase. Fundamentals improving. Institutional accumulation confirmed.
**Action**: Long-term investment. Dollar-cost average into weakness.
**Caveat**: Golden cross can fail in bear markets. Confirm with volume.

## 6. b-Profile Trap (Avoid)

**Source**: Volume Profile + Price Action

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 10-30 | Markdown, LH/LL |
| Volume Profile | 10-30 | b-Profile, price below VAL |
| Price Action | 10-30 | RSI < 30 or > 70, VPA bearish |
| Sentiment | 20-40 | SI low, Inst decreasing |
| Fundamentals | 10-40 | Deteriorating |

**Expected Total Score**: 10-35
**Description**: Aggressive selling, price rejected from value area. Bears
in control. Do not buy the dip.
**Action**: Avoid. Look elsewhere.
**Caveat**: Can reverse if selling climax with massive volume occurs.

## Pattern Matching Logic

When presenting results, the scanner identifies which pattern (if any) each
ticker matches:

```
if wyckoff >= 70 and spring_detected:
    pattern = "Accumulation Spring"
elif volprof >= 70 and profile_shape == "D" and fundamentals >= 60:
    pattern = "D-Profile Value Zone"
elif volprof >= 70 and profile_shape == "P" and pa >= 70:
    pattern = "P-Profile Breakout"
elif sentiment >= 70 and short_interest > 20:
    pattern = "Squeeze Setup"
elif wyckoff >= 65 and golden_cross and fundamentals >= 60:
    pattern = "Golden Cross Accumulation"
elif volprof <= 30 and profile_shape == "b":
    pattern = "b-Profile Trap"
else:
    pattern = "Mixed / No dominant pattern"
```
