# Cheatsheet — Stock/Crypto Unified Analysis

## Weights Quick Reference

| Dimensione | Stock | Crypto |
|-----------|-------|--------|
| Wyckoff Phase | 25% | 15% |
| Volume Profile | 20% | 15% |
| Price Action | 20% | 15% |
| Sentiment | 15% | 10% |
| Fondamentali | 20% | 10% |
| Crypto Layer | — | 35% |
| **Totale** | **100%** | **100%** |

## Phase Scoring Summary

### Phase 2 — Wyckoff Score (0-100)

| Condizione | Score |
|-----------|-------|
| Accumulation (B-C-D) | 80-100 |
| Markup (E after acc) | 70-100 |
| Neutral range | 40-60 |
| Distribution (B-C-D) | 0-30 |
| Markdown (E after dist) | 0-20 |

### Phase 2 — Volume Profile Adjustments (+/-)

| Condizione | Score Δ |
|-----------|--------|
| D-Profile | +30 |
| P-Profile | +50 |
| b-Profile | -30 |
| Thin Profile ↑ | +20 |
| Thin Profile ↓ | -20 |
| Price above VPOC | +20 |
| Price below VPOC | -20 |
| Price > VAH (extended) | -15 |
| Price < VAL (extended) | -15 |

### Phase 3 — Price Action Components

| Segnale | Score Δ | Fonte |
|---------|--------|-------|
| Buildup at S/R | +30 | Volman |
| Proper Break | +40 | Volman |
| Tease Break | +10 | Volman |
| False Break | -20 | Volman |
| Double Pressure | +30 | Volman |
| 25ema rising | +15 | Volman |
| 25ema falling | -15 | Volman |
| Spring (daily) | +60 | Weis |
| Upthrust | -60 | Weis |
| Cluster near S/R | +30 | Weis |
| SOT in trend dir | +40 | Weis |
| SOT vs trend | -40 | Weis |
| Confluence lines | +20 | Weis |
| VPA bullish val. (ea) | +5 | Coulling |
| VPA bearish val. (ea) | -5 | Coulling |
| VPA anomaly vs trend | +10 | Coulling |
| E/R healthy bar (ea) | +5 | Coulling |
| E/R absorption (ea) | -5 | Coulling |
| E/R trap bar (ea) | -10 | Coulling |

### Phase 4 — Sentiment

| Condizione | Score Δ | Fonte |
|-----------|--------|-------|
| P/C extreme bullish | +50 | Summa |
| P/C extreme bearish | +50 | Summa |
| P/C consensus | -20 | Summa |
| Squeeze Play I signal | +40 | Summa |
| VIX > 30 (fear) | +30 | Summa |
| VIX < 12 (complacency) | -20 | Summa |
| Multi-stream convergence | +50 | Summa |

### Phase 5a — Crypto Layer

| Segnale | Score Δ | Fonte |
|---------|--------|-------|
| Active addresses ↑ | +30 | Crypto TA |
| Exchange reserves ↓ | +30 | Crypto TA |
| Staking > 30% | +20 | Crypto TA |
| Low circ/mcap ratio | +20 | Crypto TA |
| Sustainable organic interest | +20 | Crypto TA |
| Pure hype (no fundamentals) | -30 | Crypto TA |
| Public team + track record | +20 | Crash Course |
| Clear whitepaper + working product | +20 | Crash Course |
| Deflationary tokenomics | +20 | Crash Course |
| Clear utility | +15 | Crash Course |
| Strong community + GitHub | +15 | Crash Course |

### Phase 5b — Fondamentali (Stock)

| Segnale | Score Δ |
|---------|--------|
| P/E < 15 | +40 |
| P/E 15-25 | +20 |
| P/E > 40 | -20 |
| Revenue growth YoY+ | +20 |
| Institutional > 50% | +15 |
| Earnings beat 4Q in row | +25 |
| Next earnings > 4wk | +10 |
| Insider buying | +20 |

## Verdict Thresholds

| Score | Verdetto | Azione |
|------|----------|--------|
| 70-100 | Long-Term Investment | Entry DCA/singolo, PT 6-12m |
| 50-69 | Short-Term Spec (Bullish) | Entry tattico, PT 1-4wk |
| 30-49 | Short-Term Spec (Bearish/Neutral) | Solo setup perfetto |
| 0-29 | Avoid / Wait | Nessuna azione |

## Quick Execution Checklist

- [ ] Determinare is_crypto
- [ ] Caricare skill dipendenti
- [ ] Fase 1: Fetch data (market-data-fetch)
- [ ] Fase 2: Wyckoff Phase + Volume Profile
- [ ] Fase 3: VPA + Volman + Weis
- [ ] Fase 4: Sentiment
- [ ] Fase 5a/b: Fondamentali / Crypto Layer
- [ ] Aggregare con pesi
- [ ] Produrre verdetto
- [ ] Aggiungere rischi
