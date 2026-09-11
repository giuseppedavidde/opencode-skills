---
description: "Routing telemetry: mostra statistiche delle delegazioni ai subagent, blocchi VERIFICA, confidenza e escalation"
agent: build
---
Mostra le statistiche di telemetria del routing caricando il file degli eventi
registrati dal plugin `routing-stats`.

**Risoluzione Python e script:**
1. Prova `/tmp/opencode/.venv/bin/python` (venv condiviso opencode)
2. Fallback a `python3`
3. Lo script `stats_report.py` si trova in `routing-eval`, incluso in
   `opencode-skills` e installato come symlink in `~/.config/opencode/routing-eval`.
   Risoluzione (in ordine): `$ROUTING_EVAL_DIR` → `~/.config/opencode/routing-eval`
   → `~/Progetti/Github/opencode-skills/routing-eval` → `~/opencode-skills/routing-eval`.

Esegui il comando equivalente a questo script bash:
```bash
#!/usr/bin/env bash
PYTHON=""
for c in "/tmp/opencode/.venv/bin/python" "python3" "python"; do
    if command -v "$c" &>/dev/null; then PYTHON="$c"; break; fi
done
if [ -z "$PYTHON" ]; then
    echo "ERRORE: Python non trovato. Crea il venv: python3 -m venv /tmp/opencode/.venv"
    exit 1
fi
SCRIPT=""
for d in "${ROUTING_EVAL_DIR:-}" "$HOME/.config/opencode/routing-eval" "$HOME/Progetti/Github/opencode-skills/routing-eval" "$HOME/opencode-skills/routing-eval"; do
    if [ -n "$d" ] && [ -f "$d/stats_report.py" ]; then SCRIPT="$d/stats_report.py"; break; fi
done
if [ -z "$SCRIPT" ]; then
    echo "ERRORE: routing-eval non trovato. Rilancia python3 install.py dalla repo."
    exit 1
fi
exec "$PYTHON" "$SCRIPT" $ARGUMENTS
```

**Uso tipico:**
- `/routing-stats` — riepilogo globale di tutte le delegazioni
- `/routing-stats --day 2026-08-09` — report per un giorno specifico
- `/routing-stats --json` — output JSON (utile per pipe/post-processing)

**Metriche mostrate:**
- Conteggio delegazioni per subagent (trade, coder, skill_updater, graphify_helper, book-to-skill-agent)
- % con blocco `## VERIFICA`
- Confidenza media, conteggio `escalation_consigliata=sì`, conteggio `confidenza < 40`
- Costi stimati se disponibili dal DB sessioni

Se il file `~/.config/opencode/stats/routing_events.jsonl` non esiste, viene mostrato
un messaggio che indica plugin non attivo o nessuna delegazione.

**Prerequisito portabile:** `routing-eval` è incluso nel repo `opencode-skills` e
installato come symlink in `~/.config/opencode/routing-eval`. Dopo un `git pull`
non serve reinstallare. Se non viene trovato, esegui dalla repo:
```bash
python3 install.py
pip install -r routing-eval/requirements.txt
```
