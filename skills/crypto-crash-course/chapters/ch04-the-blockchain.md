# Chapter 4: The Blockchain

## Core Idea
The blockchain is a decentralized database that exists simultaneously on every computer in the network (no central server). Blocks containing verified transactions are linked cryptographically in a chain, creating a permanent, tamper-evident public record.

## Frameworks Introduced
- **Proof-of-Work Origin**: Originally invented in the 1980s to stop spam emails — a mathematical puzzle that gets harder the more solutions you request. Satoshi repurposed it as the foundation for blockchain consensus.
- **Chain of Trust**: Each block references the previous block's hash. Changing one block would require recalculating every subsequent block, which is computationally infeasible.
- **Decentralized Ledger Model**: No central database — the full ledger is copied to every node. Consensus (>50% of nodes must agree) prevents fraudulent blocks from being added.

## Key Concepts
- **Block contents**: Transaction data, position in chain, unique hash, timestamp
- **Hashing**: Miners add a cryptographic code (hash) to each block that protects information while keeping transactions publicly viewable
- **Immutability**: Once a block is added, it becomes a permanent record. Attacking the chain requires controlling >50% of network computing power.
- **Data beyond currency**: Blocks can store additional data — driver's licenses, property titles, digital rights, medical records
- **Self-defense design**: The blockchain has no offensive security; it relies on distributed verification and computational infeasibility of attacks

## Anti-patterns
- Confusing "transparent" with "no privacy" — hashes protect identity while transactions remain public
- Thinking blockchain is only for Bitcoin — it's a general-purpose technology with many applications
- Believing blockchain is invincible — a 51% attack is theoretically possible, just extremely expensive

## Key Takeaways
- Blockchain is a decentralized, transparent, immutable ledger shared across all network participants
- Each block is cryptographically linked to the previous one, making retrospective tampering detectable
- Consensus mechanisms ensure no single entity controls what gets added to the chain
- The technology extends far beyond cryptocurrency into any domain requiring trustless record-keeping
