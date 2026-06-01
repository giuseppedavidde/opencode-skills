# Patterns — Market Accumulation Scanner

Composite patterns detected by the scanner. Each pattern is defined by a
specific combination of per-dimension scores that form a recognized setup
from the source frameworks.

## 1. Accumulation Spring (Strong Long)

**Source**: Wyckoff 2.0 + Trades About to Happen + Web News Confirmation

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 70-100 | Spring detected, price in 30-60% of 1Y range |
| Volume Profile | 60-80 | D-Profile, price inside VA, vol ratio 1-2x |
| Price Action | 50-80 | RSI 30-50, 25ema flat or rising, cluster near support |
| Sentiment | 40-60 | T:40-60 (SI 10-25%), N:50-70 (news neutre/positive), S:40-50 (non su WSB) |
| Fundamentals | 30-60 | P/E < 25 if positive, or recovering negative |

**Expected Total Score**: 55-80
**Description**: Price broke below support (Spring), reversed, and is now
building cause in an accumulation range. Volume decreasing = supply drying up.
**Action**: Strong candidate for full stock-crypto-analysis.
**Caveat**: Needs confirmation — look for SOS bar or LPS pullback.

## 2. D-Profile Value Zone (Medium-Long)

**Source**: Volume Profile + Stock-Crypto-Analysis + News Stability

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 40-70 | Neutral range, MA50 rising toward MA200 |
| Volume Profile | 70-90 | D-Profile, price at VPOC or inside VA |
| Price Action | 40-60 | RSI 40-60, low volatility, flat 25ema |
| Sentiment | 40-60 | T:40-50 (SI < 10%), N:60-80 (news positive/stabili), S:40-50 (non su WSB) |
| Fundamentals | 60-90 | P/E < 20, positive growth, low D/E |

**Expected Total Score**: 50-70
**Description**: Price oscillates around VPOC in a balanced profile. Fair
value zone with good fundamentals. Institutional accumulation without drama.
**Action**: Long-term investment candidate if fundamentals support.
**Caveat**: No immediate catalyst — needs patience. Set alert for range breakout.

## 3. P-Profile Breakout (Short-Term Momentum)

**Source**: Volume Profile + Price Action + Social Buzz

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 60-90 | Markup Phase D/E, HH/HL |
| Volume Profile | 70-90 | P-Profile, price above VAH, vol ratio > 2x |
| Price Action | 70-90 | RSI 55-70, 25ema rising sharply, VPA bullish |
| Sentiment | 50-85 | T:50-70 (SI 10-20%), N:50-70 (news miste), S:60-90 (WSB hype/mid FOMO, X buzz) |
| Fundamentals | 30-60 | Growing but may have high P/E |

**Expected Total Score**: 55-75
**Description**: Aggressive buying, price breaking out of value area with
increasing volume. Bullish momentum established.
**Action**: Short-term speculation entry on pullback to VPOC.
**Caveat**: Chasing breakout is risky. Wait for BUEC (Back Up to Edge of
Creek). Use tight stop.

## 4. Squeeze Setup (Short-Term Speculative)

**Source**: Trading Against the Crowd + Traditional Sentiment + Social Overlay

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 30-50 | Range, no clear phase |
| Volume Profile | 30-50 | Neutral or b-Profile |
| Price Action | 30-50 | RSI 30-45, weak but not crashing |
| Sentiment | 60-90 | T:80-95 (SI > 25%, DTC > 7), N:40-60 (news miste), S:60-90 (WSB inizio hype, squeeze language) |
| Fundamentals | 10-30 | Weak or negative |

**Expected Total Score**: 40-60
**Description**: High short interest, days to cover elevated, but price has
stabilized. Potential short squeeze if a catalyst hits.
**Action**: High-risk speculative entry. Tight sizing (1-2%).
**Caveat**: Not all high SI stocks squeeze. Many are value traps. Requires
catalyst (earnings, news, macro). Stop loss critical.

## 5. Golden Cross Accumulation (Medium-Long)

**Source**: Wyckoff 2.0 + Fundamentals + News Confirmation

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 65-85 | Spring or late Phase C, MA50 rising above MA200 |
| Volume Profile | 50-70 | D-Profile, price transitioning from below to inside VA |
| Price Action | 60-80 | RSI 50-65, 25ema rising, healthy VPA |
| Sentiment | 50-75 | T:50-70 (SI moderate, Inst growing), N:60-80 (earnings beat, guidance raise), S:40-50 (non su WSB — istituzionale, non hype) |
| Fundamentals | 60-85 | Improving margins, revenue growth, reasonable P/E |

**Expected Total Score**: 60-80
**Description**: MA50 crossed above MA200 (golden cross) during accumulation
phase. Fundamentals improving. Institutional accumulation confirmed.
**Action**: Long-term investment. Dollar-cost average into weakness.
**Caveat**: Golden cross can fail in bear markets. Confirm with volume.

## 6. News Catalyst Buildup (Medium-Long)

**Source**: Web News Sentiment + Wyckoff + Volume Profile

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 40-70 | Neutral range or late Phase B, price in 30-60% of range |
| Volume Profile | 50-70 | D-Profile or thin profile, vol ratio 1-2x |
| Price Action | 40-60 | RSI 40-55, low volatility, tight consolidation |
| Sentiment | 60-85 | T:40-60 (SI moderato), N:80-100 (4+ headlines positive, earnings beat, new contract), S:40-50 (non su WSB ancora) |
| Fundamentals | 60-80 | Improving revenue, P/E < 25, positive margins |

**Expected Total Score**: 55-75
**Description**: Multiple positive news headlines (earnings beat, contract win,
regulatory approval, product launch) but price hasn't moved yet. News is
accumulating like a catalyst stack but price is still consolidating. This is
typical of institutional accumulation before a breakout.
**Action**: Accumulate ahead of expected catalyst. Size 3-5%. Stop loss below
consolidation low.
**Caveat**: "Buy the rumor, sell the news" — if price already ran on the first
positive headline, you are late. Check that news volume > price volume.

## 7. WSB Hype Confirmation (Short-Term Speculative)

**Source**: wallstreetbets-pump-detect + Price Action + Volume Profile

| Dimension | Score Range | Typical Values |
|-----------|:-----------:|:--------------:|
| Wyckoff | 30-60 | Range or early breakout, not yet in clear markup |
| Volume Profile | 50-70 | P-Profile or thin profile developing, vol ratio > 2x |
| Price Action | 50-70 | RSI 50-65, breakout bar with high volume |
| Sentiment | 70-90 | T:50-70 (SI variabile), N:40-60 (news miste), S:80-100 (WSB hype mid-FOMO, early mentions, bullish sentiment) |
| Fundamentals | 20-50 | Often secondary — narrative-driven |

**Expected Total Score**: 50-70
**Description**: Ticker appears on WSB radar with rising hype score and bullish
sentiment. Volume is spiking, price breaking out of a consolidation range.
WSB is in Early-to-Mid FOMO phase (not yet Late/Exit). News mentions the ticker
but hasn't reached mainstream saturation.
**Action**: Short-term momentum trade. Size 1-3% (reduced due to WSB volatility).
Entry on pullback to 10ema or breakout retest. Stop loss below breakout level.
**Caveat**: WSB moves are fast and violent. The pump can reverse in hours. Use
tight trailing stops. Do NOT convert to long-term position — these are trades,
not investments.

## 8. b-Profile Trap (Avoid)

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
ticker matches. The Sentiment now includes 3 sub-dimensions (T=traditional,
N=web_news, S=social) used in pattern detection:

```python
if wyckoff >= 70 and spring_detected:
    pattern = "Accumulation Spring"
elif volprof >= 70 and profile_shape == "D" and fundamentals >= 60:
    pattern = "D-Profile Value Zone"
elif volprof >= 70 and profile_shape == "P" and pa >= 70 and social >= 60:
    pattern = "P-Profile Breakout"
elif social >= 70 and social >= 60 and pa >= 50 and vol_ratio > 2:
    pattern = "WSB Hype Confirmation"
elif web_news >= 80 and wyckoff <= 70 and pa >= 40 and pa <= 60:
    pattern = "News Catalyst Buildup"
elif traditional >= 80 and short_interest > 20:
    pattern = "Squeeze Setup"
elif wyckoff >= 65 and golden_cross and fundamentals >= 60:
    pattern = "Golden Cross Accumulation"
elif volprof <= 30 and profile_shape == "b":
    pattern = "b-Profile Trap"
else:
    pattern = "Mixed / No dominant pattern"
```

Note: `social` = social_media score, `web_news` = web_news score,
`traditional` = traditional sentiment score. The aggregated `sentiment` is
still used for final_score calculation. These 3 sub-scores are used for
pattern matching.
