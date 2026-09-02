---


name: quant-mind-skill
description: >
  Integrazione con QuantMind — knowledge extraction e retrieval per
  finanza quantitativa. Preprocessa paper arXiv, news, PDF in markdown
  (senza API key) e delega l'estrazione strutturata a un subagent
  OpenCode che usa i modelli opencode-go.

metadata:
  argument-hint: "[arxiv_id, URL, "extract paper", "batch papers"]"
---

# QuantMind Skill

QuantMind trasforma contenuti finanziari non strutturati (paper, news,
report, PDF) in markdown strutturato, pronto per l'estrazione LLM
tramite i modelli **opencode-go** (nessuna API key esterna richiesta).

## Architettura

```
┌─ Request ────────────────────────────────────────┐
│ "estrai paper 2401.12345"                       │
└─────────────────────────┬────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────┐
│           Router / @task                         │
│                                                  │
│  Step 1 — QuantMind (no API key)                 │
│    extract_paper.py arxiv 2401.12345             │
│    → /tmp/quantmind-extract/<id>.md              │
│    → /tmp/quantmind-extract/<id>.prompt.txt      │
│                                                  │
│  Step 2 — Subagent (opencode-go)                 │
│    task(subagent_type="general")                 │
│    Legge .md + .prompt.txt                       │
│    Estrae Paper strutturato in JSON              │
│    Usa deepseek-v4-flash / glm-5.3               │
└──────────────────────────────────────────────────┘
```

## Perché questo design

QuantMind usa l'OpenAI Agents SDK internamente e richiederebbe una
`OPENAI_API_KEY`. Invece di configurarne una, **scolliamo i due passi**:

| Passo | Cosa | API Key | Modello |
|-------|------|---------|---------|
| **Preprocessing** | fetch arXiv/URL + PDF→markdown | ❌ Nessuna | — |
| **Estrazione LLM** | markdown → Paper strutturato | ✅ opencode-go | deepseek-v4-flash / glm-5.3 |

## Utilizzo

### Step 1 — Preprocessa un paper (senza API key)

```bash
source /tmp/opencode/.venv-quantmind/bin/activate

# Da arXiv
python3 ~/.config/opencode/skills/quant-mind-skill/extract_paper.py arxiv 2401.12345

# Da URL
python3 ~/.config/opencode/skills/quant-mind-skill/extract_paper.py url https://arxiv.org/pdf/2401.12345.pdf

# Da file locale
python3 ~/.config/opencode/skills/quant-mind-skill/extract_paper.py file /path/to/paper.pdf
```

Output in `/tmp/quantmind-extract/`:
```
<id>.md           ← markdown del paper
<id>.meta.json    ← metadati (titolo, autori, fonte)
<id>.prompt.txt   ← prompt pronto per subagent
```

### Step 2 — Estrai struttura con subagent opencode-go

Dopo il preprocessing, il prompt.txt contiene le istruzioni per un
subagent. Puoi delegare l'estrazione LLM con:

```
Leggi /tmp/quantmind-extract/<id>.prompt.txt
Leggi /tmp/quantmind-extract/<id>.md
Estrai il JSON strutturato del paper
```

Il subagent usa il modello opencode-go che preferisci (default:
deepseek-v4-flash, oppure glm-5.3 per maggiore profondità).

### Workflow completo (in una richiesta)

Puoi chiedere direttamente al router di fare entrambi i passi:

> "Preprocessa arXiv 2401.12345 con QuantMind, poi estrai la struttura
> con deepseek-v4-pro e salvami il JSON in /tmp/paper-output.json"

Il router eseguirà:
1. `extract_paper.py arxiv 2401.12345` (bash)
2. Task subagent con prompt per estrarre JSON dal markdown
3. Salva il risultato

### Batch di paper

```bash
source /tmp/opencode/.venv-quantmind/bin/activate
for id in 2401.12345 2401.12346 2401.12347; do
  python3 ~/.config/opencode/skills/quant-mind-skill/extract_paper.py arxiv "$id"
done
```

Poi processa ogni `.prompt.txt` con un subagent.

## Bridge con altri skill

### → Trading MCP

Dopo aver estratto un paper su una strategia (es. momentum factor):

```
1. Leggi il paper JSON estratto → identifica strategia/fattore
2. analyze_stock("SPY") → analisi mercato attuale
3. Applica la logica del paper ai dati attuali
```

### → Graphify

Il JSON del paper può essere caricato in Graphify:

```bash
# Il JSON prodotto dal subagent può essere inserito in graphify-out/
cp /tmp/paper-output.json /path/to/graphify-out/
```

## Script helper

`~/.config/opencode/skills/quant-mind-skill/extract_paper.py`:
- `arxiv <id>` → fetch arXiv PDF, converti in markdown
- `url <url>` → fetch URL, converti in markdown
- `file <path>` → leggi file locale, converti in markdown

Tutti producono in `/tmp/quantmind-extract/`: `.md`, `.meta.json`, `.prompt.txt`.

## Output atteso dal subagent

Il subagent deve produrre un JSON con questa struttura:

```json
{
  "title": "Titolo del paper",
  "authors": ["Autore 1", "Autore 2"],
  "source": "arxiv:2401.12345",
  "summary": "Riassunto di 2-3 paragrafi...",
  "methodology": "Descrizione metodologia...",
  "key_findings": ["Finding 1", "Finding 2"],
  "limitations": ["Limite 1"],
  "asset_classes": ["equity", "futures"],
  "sections": [
    {"title": "Introduzione", "summary": "..."},
    {"title": "Metodologia", "summary": "..."}
  ]
}
```

## Limitazioni

- ❌ `mind/memory/` (PR6) — nessuna persistenza filesystem
- ❌ `mind/store/` (PR7) — nessun db vettoriale
- ❌ `DoiIdentifier` — non implementato (serve unpaywall)
- ⚠️  Subagent singolo per paper (non batch LLM)
- ⚠️  `pyproject.toml` ha patch locale pillow (riapplicata da skill_updater)

## Aggiornamento

Delega a `@skill_updater`:
> "aggiorna quant-mind"

Oppure manualmente:
```bash
cd ~/Progetti/Github/opencode-skills
git submodule update --remote skills/quant-mind-src
cd skills/quant-mind-src
sed -i 's/pillow>=10.1.0,<11.0.0/pillow>=10.1.0/' pyproject.toml
source /tmp/opencode/.venv-quantmind/bin/activate
pip install --quiet -e .
```
