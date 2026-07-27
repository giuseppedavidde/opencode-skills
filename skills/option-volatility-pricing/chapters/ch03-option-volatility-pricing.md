# Chapter 3: Contract Specifications and Option Terminology

## Core Idea
Every option contract is defined by four essential specifications—type, underlying, expiration date, and exercise price—that together determine rights, obligations, and value. Mastery of this terminology is non-negotiable for any trader because miscommunication in the marketplace can be financially catastrophic.

## Frameworks Introduced
- **The Four Pillars of Contract Specification**: (1) Type—call vs. put; (2) Underlying—what is being bought or sold (100 shares for stock options, one futures contract for futures options); (3) Expiration Date—when the right to exercise ceases; (4) Exercise/Strike Price—the price at which the underlying is delivered upon exercise.
- **Exercise and Assignment Mechanics**: The buyer exercises to convert the option into an underlying position; the exchange randomly assigns a seller to take the opposite side. After assignment, all rights and obligations under the option cease.
- **Settlement Types**: Options can settle into (1) the physical underlying, (2) a futures position, or (3) cash. Stock options use stock-type settlement (immediate payment); futures options may use futures-type settlement (no cash changes hands).
- **AM vs. PM Expiration**: Stock index options typically use AM settlement (based on opening prices) to avoid end-of-day imbalances; individual stock options use traditional PM settlement.
- **Serial and Midcurve Options**: Serial options expire in months without a corresponding futures month; midcurve options are short-term options on long-term futures.

## Key Concepts
- **Standardized vs. Custom Contracts**: Exchange-traded options have standardized terms; OTC (dealer) options can be tailored to the buyer's needs.
- **Option Price Components**: Intrinsic value (the amount by which an option is in-the-money) plus time value/premium (the additional amount reflecting time and volatility).
- **Moneyness**: In-the-money (ITM), at-the-money (ATM), and out-of-the-money (OTM) describe the relationship between underlying price and exercise price.

## Anti-patterns
- Assuming all options settle identically—settlement procedures (stock-type vs. futures-type) radically affect interest-rate sensitivity and cash flows.
- Ignoring the difference between AM and PM expiration when holding positions through the last trading day.
- Failing to verify the exact underlying contract for serial options, leading to unintended exposure.

## Key Takeaways
1. The four contract specifications (type, underlying, expiry, strike) fully define every option contract.
2. Exercise converts an option into an underlying position; assignment is random for the seller.
3. Settlement type determines whether interest rates affect the option's present value.
4. Standardized contracts on exchanges guarantee contract integrity through the clearinghouse.
5. Understanding moneyness (ITM/ATM/OTM) is foundational for all subsequent option analysis.
