---
description: "Token saving report: aggregato headroom (compressioni, token salvati, retrieve, stima netta) e ripartizione per agente"
agent: build
---
Mostra il report aggregato del token saving di headroom: compressioni, token salvati,
bytes originali→iniettati, retrieve e **stima netta**, più la ripartizione per agente
(dagli eventi `token_saving` loggati dal verifica-gate).

**Esecuzione dello script:**
1. Script installato (symlink): `node ~/.config/opencode/scripts/token-stats.js`
2. Fallback dalla repo: `node ~/Progetti/Github/opencode-skills/scripts/token-stats.js`
3. Modalità programmatica: aggiungi `--json`.

**Fonti lette:**
- `~/.headroom/session_stats.jsonl` — eventi `compress` + `retrieve` (scritti da auto-headroom e dal MCP).
- `~/.config/opencode/stats/gate_events.jsonl` — eventi `token_saving` per agente (verifica-gate).
- `~/.config/opencode/context-store/<hash>.txt` — dimensioni file, per stimare i byte ri-recuperati.

**Interpretazione:**
- `STIMA NETTA = token_salvati − retrieved_bytes/4`: se > 0 → «headroom sta ottimizzando»; altrimenti warning.
- `PER AGENTE` deriva dagli eventi `token_saving` (un task = un evento).

Se i file non esistono, lo script mostra `MANCANTE` e termina senza errori (exit 0).
