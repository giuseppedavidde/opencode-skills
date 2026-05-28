# Chapter 11: Wallets, Addresses & First Coins

## Core Idea
A cryptocurrency wallet stores the keys that prove ownership of coins on the blockchain. Two types are essential: a hot wallet (connected, for active trading like a checking account) and a cold wallet (offline, for long-term storage like a safety deposit box). Addresses function like email addresses but are one-use for privacy.

## Frameworks Introduced
- **Hot/Cold Wallet Strategy**: Hot wallet = spending money (small amounts); Cold wallet = savings (bulk of holdings). Transfer profits from hot to cold immediately.
- **Key Hierarchy**: Private key (your signature, never share) → Public key (like email, share freely) → Address (single-use identifier for transactions)

## Key Concepts
- **Wallet function**: Doesn't store coins (they're on the blockchain) — stores keys that prove ownership
- **Cold wallet**: Not connected to internet; immune to remote hacking. Hardware wallets recommended.
- **Hot wallet**: Internet-connected; convenient for trading; vulnerable to attacks
- **Paper wallet**: Keys written on paper; analog security but single point of failure (theft/loss)
- **Addresses**: Start with 1 or 3 (Bitcoin), 26-35 characters, case-sensitive. Use a new address for each transaction to preserve anonymity.
- **Getting first coins**: Buy from exchanges (requires verification), trade with individuals (meetup.com, localbitcoins), sell goods/services for crypto
- **Transaction flow**: Create address → seller sends coins → network propagates → wallet detects → ~10 min for first confirmation

## Anti-patterns
- Keeping all coins on an exchange ("not your keys, not your coins")
- Reusing the same address — destroys privacy by linking all transactions
- Using only a hot wallet for large amounts — inviting theft
- Writing down keys on paper without securing the paper itself

## Key Takeaways
- Use cold wallets for long-term storage and hot wallets for active trading
- Generate a new address for each transaction to maximize privacy
- Never share your private keys; treat them like the combination to a vault
- Transfer profits to cold storage immediately after each trade
