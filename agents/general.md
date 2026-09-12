---
description: Deprecated general subagent. Direct GLM-5.3 execution is disabled. All code and scripting tasks are routed to @coder (deepseek-v4.1-flash + coder_planner).
mode: subagent
model: opencode-go/deepseek-v4.1-flash
hidden: true
permission:
  bash: allow
  read: allow
  task: allow
steps: 10
---

ATTENZIONE: L'esecuzione diretta su **glm-5.3** è stata disabilitata per minimizzare il consumo di token.

Se hai ricevuto una richiesta di calcolo complesso, modifica o esecuzione di codice:
1. Delega il task all'agente `@coder` (`subagent_type="coder"`).
2. `@coder` utilizzerà `coder_planner` (`glm-5.3`) per la sola pianificazione delle azioni atomiche ed eseguirà i calcoli via script con `deepseek-v4.1-flash`.

```
task(
  description="Calcolo/Script via coder",
  subagent_type="coder",
  prompt=<richiesta_originale>
)
```

## VERIFICA

```
## VERIFICA
- confidenza: 100
- evidenza: Reindirizzato a @coder per esecuzione a basso consumo di token.
- non_verificato: nessuna
- escalation_consigliata: no
```
