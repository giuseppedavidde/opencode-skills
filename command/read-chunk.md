---
description: "Selective Retrieval: legge chunk o righe da un contenuto compresso in context-store per hash"
agent: build
---
Legge porzioni specifiche (chunk o intervallo righe) da un file memorizzato in `context-store` tramite il suo hash SHA-256.

**Esecuzione dello script:**
```bash
#!/usr/bin/env bash
PYTHON=""
for c in "/tmp/opencode/.venv/bin/python" "python3" "python"; do
    if command -v "$c" &>/dev/null; then PYTHON="$c"; break; fi
done

SCRIPT=""
for d in "$HOME/.config/opencode/scripts" "$HOME/Progetti/Github/opencode-skills/scripts" "$HOME/opencode-skills/scripts"; do
    if [ -n "$d" ] && [ -f "$d/context_store_reader.py" ]; then SCRIPT="$d/context_store_reader.py"; break; fi
done

if [ -z "$SCRIPT" ]; then
    echo "ERRORE: context_store_reader.py non trovato."
    exit 1
fi

exec "$PYTHON" "$SCRIPT" $ARGUMENTS
```

**Uso tipico:**
- `/read-chunk <hash> --info` — mostra metadati, numero di chunk e lista delle intestazioni
- `/read-chunk <hash> --chunk 0` — legge il chunk 0 (righe 1-50) con numeri di riga
- `/read-chunk <hash> --lines 100 160` — legge l'intervallo di righe 100-160
- `/read-chunk <hash> --search "pattern"` — cerca un pattern o parola chiave nel file compresso
