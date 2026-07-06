# Strategy Selection Patterns

## Pattern 1: Income Generation
**When to use**: You own stocks and want monthly/quarterly income. Neutral to slightly bullish. Willing to cap upside.
**How**: Sell covered calls (30-45 DTE, OTM, ~2% premium relative to stock price). Repeat monthly.
**Trade-off**: Generates consistent income but caps upside. Stock loss risk remains.
**Variations**: Sell OTM cash-secured puts if you want to acquire stock. Fig Leaf (LEAPS instead of stock) for leverage.

## Pattern 2: Portfolio Protection
**When to use**: You have unrealized gains you want to protect. Bullish long-term but worried short-term. Approaching earnings or uncertain news.
**How**: Buy protective puts (choose strike = acceptable "deductible"). Or use a collar (sell call to fund put) for zero-cost protection.
**Trade-off**: Puts cost premium (reduces profit). Collar caps upside. Both define your downside.

## Pattern 3: Stock Purchase at Discount
**When to use**: You want to buy a stock below current price. Long-term bullish. Have cash available.
**How**: Sell cash-secured puts at your target buy price. Collect premium while waiting. If assigned, you own stock at net-discount. If not assigned, keep premium.
**Trade-off**: Miss upside if stock rallies above strike. Must have cash to buy if assigned.

## Pattern 4: Directional Speculation (Bullish)
**When to use**: Strong conviction stock will rise. Want defined risk. Moderate time horizon.
**How**: 
- Strongly bullish, expect large move: Long Call (prefer ITM, delta ≥ .80)
- Bullish with specific target: Long Call Spread
- High probability bullish (neutral-bullish): Short Put Spread
- Leveraged bullish: Long Combination (synthetic stock)
- Extremely bullish, volatile stock: Back Spread w/ Calls
**Trade-off**: Long calls have time decay and require timing. Spreads reduce cost but cap profit.

## Pattern 5: Directional Speculation (Bearish)
**When to use**: Strong conviction stock will fall.
**How**:
- Strongly bearish: Long Put (ITM preferred, delta ≤ -.80)
- Bearish with specific target: Long Put Spread
- High probability bearish (neutral-bearish): Short Call Spread
- Bearish with less margin: Short Combination (synthetic short)
- Extremely bearish, volatile: Back Spread w/ Puts
**Trade-off**: Long puts cost premium and decay. Short calls have unlimited risk.

## Pattern 6: Neutral / Range-Bound Trading
**When to use**: Stock expected to trade sideways. Low volatility environment. No catalyst expected.
**How**:
- High conviction on pin price: Iron Butterfly (narrow range)
- Moderate range: Iron Condor (sells ~1 SD OTM strikes)
- Collect credit with time decay: Short Put Spread + Short Call Spread (aka Iron Condor)
**Trade-off**: High probability of small profit. Risk of large loss if stock breaks out. Must manage before events.

## Pattern 7: Directionally Uncertain / Volatility Play
**When to use**: Expect big move but don't know direction (earnings, FDA ruling, merger). IV is low relative to historic.
**How**:
- Large move expected: Long Straddle (ATM, same strike)
- Cheaper entry for massive move: Long Strangle (OTM strikes)
- Pay-later approach: Back Spread (credit possible)
**Trade-off**: Straddles cost more but need smaller move. Strangles cheaper but need larger move. Time decay is severe.

## Pattern 8: Volatility Premium Selling
**When to use**: IV is high (before earnings, fear events). Expect volatility to revert to mean. IV crush anticipated.
**How**: 
- Neutral with defined risk: Iron Condor (most common)
- Pin-action confidence: Iron Butterfly
- Aggressive (unlimited risk): Short Straddle or Short Strangle
**Trade-off**: Defined-risk iron condor is preferred for retail traders. Short straddle/strangle is All-Stars only.

## Pattern 9: Calendar / Time Decay Advantage
**When to use**: Expect stock to stay near a price. Want to exploit difference in decay rates between expiration months.
**How**: 
- Neutral: Long Calendar Spread (sell front, buy back same strike)
- Slightly directional: Diagonal Spread (different strikes and months)
**Trade-off**: Defined risk. Need stock near short strike at front expiration. Model-dependent P&L.

## Pattern 10: Low-Cost Defined-Risk Pin Play
**When to use**: Expect stock to pin at a specific price at expiration. Near expiration. Low volatility.
**How**: Long Butterfly (call or put — equidistant strikes). Low cost, high leverage on pin.
**Trade-off**: Very low cost but max profit only at exact pin. Wider profit zone: use Condor instead.

## Pattern 11: Leveraged Stock Replacement
**When to use**: Want stock-like returns with less capital. Long-term horizon (>1 year). Bullish.
**How**: Buy deep ITM LEAPS call (delta ≥ .80). Acts as stock substitute. Less capital than buying 100 shares.
**Trade-off**: LEAPS expire — not indefinite like stock. Time decay accelerates in final year. Theta and rho matter more.

## Pattern 12: Earnings / Event Play
**When to use**: Approaching known catalytic event.
**How**:
- Expect big move either way and IV is low: Long Straddle or Long Strangle
- Expect move but IV is already high: Long Call Spread or Long Put Spread (reduce IV cost)
- Expect stock to NOT move despite event: Short Straddle or Iron Condor (very risky — event gap risk)
**Trade-off**: Earnings are the most common volatility event. IV typically expands before and collapses after. Be careful of volatility crush.

## Pattern 13: Risk Audit Checklist per Posizioni Multigamba

**Quando**: Ogni volta che analizzi una posizione esistente con 2+ gambe.

**Checklist**:
1. **Naked Options?** — C'è una short call senza azioni/LEAPS a copertura? Short put senza cash?
2. **Gamma Sign** — Il gamma totale è positivo o negativo? Negativo = la posizione peggiora più velocemente in movimento.
3. **Ratio Imbalance** — Il rapporto tra gambe short e long è equilibrato? (es. 2 short put : 1 long call = sbilanciato 2:1)
4. **Deep OTM** — Ci sono gambe con delta < 0.15? Falsa sicurezza: se il prezzo arriva lì, gamma esplode.
5. **Gap Analysis** — C'è una zona di prezzo dove la protezione non funziona? (es. put a 50 in un collar, prezzo tra 50 e 60 = gap scoperto)
6. **Expiry Mismatch** — Le protezioni scadono prima dei rischi che coprono?
7. **Theta Direction** — Il theta totale è positivo (time lavora per te) o negativo?

**Azioni correttive per ogni flag**:
- Naked → aggiungi spread o copertura
- Gamma negativo → aggiungi long gamma (compra opzioni ATM)
- Ratio sbilanciato → aggiusta quantità
- Deep OTM → chiudi o rolla più vicino
- Gap → aggiungi spread nel gap
- Expiry mismatch → rolla protezione

## Pattern 14: Exit Rules Framework

Non un pattern di trading ma un **metodo per definire le exit rules** di qualsiasi posizione.

Per ogni posizione, definire SEMPRE:
1. **Take Profit** — A quanto chiudi (es. $2,000 totali, o +50% sul max profit teorico)
2. **Hard Stop Loss** — Prezzo sotto il quale chiudi TASSATIVAMENTE (es. DRAM sotto $45)
3. **Soft Stop Loss** — Drawdown massimo tollerato (es. P&L sotto -$1,000)
4. **Time Stop** — Data oltre la quale chiudi (es. 1 Novembre per opzioni Dec). Motivo: gamma risk esplode sotto 45 DTE; theta non è più sfruttabile.
5. **Trailing Stop** — Se P&L raggiunge X e poi perde Y%, chiudi
6. **Binary Event Rule** — Non tenere posizioni attraverso earnings/catalyst. Chiudi 3-5 giorni prima o assicurati che la posizione sia immune.
7. **Roll Limit** — Non rollare più di N volte la stessa gamba. Dopo N roll, è meglio chiudere e rientrare.
