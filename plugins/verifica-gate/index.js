// verifica-gate — Enforcement meccanico del blocco ## VERIFICA, Exit-Code Tracking e Task Output Pruning (API V2)
// Assicura che ogni subagent rispetti il contratto VERIFICA (router.md),
// ancora la confidenza agli exit code reali dei comandi shell (pytest/pylint/mypy) e compatta l'output dei task lunghi.
// Hook V2: ctx.tool.hook("execute.after") sui tool "subagent" (V1: task) e "shell" (V1: bash).
// Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { existsSync, mkdirSync, appendFileSync, statSync, openSync, readSync, closeSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const GATE_LOG_DIR = env.GATE_LOG_DIR || join(homedir(), ".config", "opencode", "stats");
const GATE_LOG_FILE = join(GATE_LOG_DIR, "gate_events.jsonl");

// ── Headroom token-saving tracking ──
// Log eventi condiviso scritto dal plugin auto-headroom e dal MCP (formato JSONL).
const HEADROOM_WORKSPACE_DIR = env.HEADROOM_WORKSPACE_DIR || join(homedir(), ".headroom");
const HEADROOM_STATS_FILE = join(HEADROOM_WORKSPACE_DIR, "session_stats.jsonl");

// Tracking incrementale: offset byte già consumato + cumulativi di sessione.
// Approssimazione accettata: task paralleli possono attribuire lo stesso delta.
const headroomState = {
  offsetBytes: 0,
  sessionTokensSaved: 0,
  compressions: 0,
  originalBytes: 0,
  injectedBytes: 0,
};

function initHeadroomOffset() {
  try {
    headroomState.offsetBytes = existsSync(HEADROOM_STATS_FILE) ? statSync(HEADROOM_STATS_FILE).size : 0;
  } catch (_e) {
    headroomState.offsetBytes = 0;
  }
}

// Legge i byte nuovi (offset→EOF), somma i `compress`, aggiorna offset/cumulativi.
// Edge: se il file è più corto dell'offset (pruned/truncated) → reset, delta 0 (mai negativi).
function readHeadroomDelta() {
  const delta = { tokensSaved: 0, compressions: 0, originalBytes: 0, injectedBytes: 0 };
  try {
    if (!existsSync(HEADROOM_STATS_FILE)) return delta;
    const size = statSync(HEADROOM_STATS_FILE).size;
    if (size < headroomState.offsetBytes) {
      headroomState.offsetBytes = size;
      return delta;
    }
    if (size === headroomState.offsetBytes) return delta;

    const length = size - headroomState.offsetBytes;
    const buf = Buffer.alloc(length);
    const fd = openSync(HEADROOM_STATS_FILE, "r");
    try {
      readSync(fd, buf, 0, length, headroomState.offsetBytes);
    } finally {
      closeSync(fd);
    }
    headroomState.offsetBytes = size;

    for (const raw of buf.toString("utf-8").split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      let evt;
      try {
        evt = JSON.parse(line);
      } catch (_e) {
        continue; // riga corrotta: ignora
      }
      if (evt && evt.type === "compress") {
        delta.tokensSaved += Number(evt.tokens_saved) || 0;
        delta.compressions += 1;
        delta.originalBytes += Number(evt.original_bytes) || 0;
        delta.injectedBytes += Number(evt.injected_bytes) || 0;
      }
    }
    headroomState.sessionTokensSaved += delta.tokensSaved;
    headroomState.compressions += delta.compressions;
    headroomState.originalBytes += delta.originalBytes;
    headroomState.injectedBytes += delta.injectedBytes;
  } catch (_e) {
    // best effort: non bloccare mai
  }
  return delta;
}

function formatTokens(n) {
  return n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function formatKB(bytes) {
  return (bytes / 1024).toFixed(1);
}

function buildTokenSavingLine(delta) {
  if (!delta || delta.tokensSaved === 0) {
    return `📊 Token saving: 0 token salvati durante questo task (nessuna compressione) | sessione: ${formatTokens(headroomState.sessionTokensSaved)} token`;
  }
  return `📊 Token saving: ~${formatTokens(delta.tokensSaved)} token salvati durante questo task (${delta.compressions} compressioni, ${formatKB(delta.originalBytes)} KB → ${formatKB(delta.injectedBytes)} KB iniettati) | sessione: ${formatTokens(headroomState.sessionTokensSaved)} token`;
}

// Inserisce la riga come ULTIMA riga della sezione ## VERIFICA (o in coda se assente).
function appendTokenLine(text, tokenLine) {
  if (!text) return tokenLine;
  return text.includes("## VERIFICA") ? `${text}\n${tokenLine}` : `${text}\n\n${tokenLine}`;
}

// Session-level tracking for verification command outcomes (exit status != 0).
// Solo i fallimenti REALI ancorano la confidenza; quelli infrastrutturali no.
let lastFailedVerification = null;
let lastIndeterminateVerification = null;

function ensureLogDir() {
  if (!existsSync(GATE_LOG_DIR)) {
    try {
      mkdirSync(GATE_LOG_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

// Testo del result V2 (content stringa o array di parti text), con fallback su output.
function extractText(result) {
  if (typeof result === "string") return { text: result, kind: "direct" };
  if (!result || typeof result !== "object") return { text: String(result), kind: "string" };
  const c = result.content;
  if (typeof c === "string") return { text: c, kind: "content-string" };
  if (Array.isArray(c)) {
    const texts = c.filter(p => p && p.type === "text" && typeof p.text === "string").map(p => p.text);
    if (texts.length > 0) return { text: texts.join("\n"), kind: "content-array" };
  }
  if (typeof result.output === "string") return { text: result.output, kind: "output" };
  if (result.output && typeof result.output === "object" && typeof result.output.output === "string") {
    return { text: result.output.output, kind: "output.output" };
  }
  return { text: JSON.stringify(result), kind: "stringify" };
}

// Ritorna un NUOVO result con il testo sostituito (execute.after muta event.result).
function replaceResultText(result, kind, originalText, newText) {
  if (kind === "direct") return newText;
  let updated = result;
  if (kind === "content-string") updated = { ...result, content: newText };
  else if (kind === "content-array") updated = { ...result, content: [{ type: "text", text: newText }] };
  else if (kind === "output") updated = { ...result, output: newText };
  else if (kind === "output.output") updated = { ...result, output: { ...result.output, output: newText } };
  else return newText;
  if (updated && typeof updated === "object" && updated.output && typeof updated.output === "object"
      && updated.output.output === originalText) {
    updated = { ...updated, output: { ...updated.output, output: newText } };
  }
  return updated;
}

function extractPromptSnippet(input) {
  const prompt = (input && typeof input.prompt === "string") ? input.prompt : "";
  return prompt.slice(0, 80);
}

function extractSubagentType(input) {
  if (input && typeof input === "object") {
    if (typeof input.agent === "string") return input.agent;
    if (typeof input.subagent_type === "string") return input.subagent_type;
  }
  const argsStr = JSON.stringify(input || {});
  const match = argsStr.match(/"(?:agent|subagent_type)"\s*:\s*"([\w-]+)"/);
  return match ? match[1] : null;
}

function parseVerifica(outputText) {
  if (!outputText || typeof outputText !== "string") return { present: false, confidenza: null, mechanicalError: false };

  const sectionMatch = outputText.match(/## VERIFICA\b/i);
  const present = !!sectionMatch;

  const confMatch = outputText.match(/confidenza\s*[:：]\s*(\d{1,3})/i);
  const confidenza = confMatch ? parseInt(confMatch[1], 10) : null;

  // Mechanical error detection (tests failed, tracebacks, syntax errors)
  const hasErrorPattern = /\b(FAILED|SyntaxError|AssertionError|Traceback \(most recent call last\))\b/i.test(outputText);

  return { present, confidenza, mechanicalError: hasErrorPattern };
}

function logEvent(subagentType, caseType, confidenza, promptSnippet, extra) {
  ensureLogDir();
  const event = {
    ts: new Date().toISOString(),
    subagent_type: subagentType || "unknown",
    case: caseType,
    confidenza: confidenza,
    prompt_snippet: promptSnippet,
    ...(extra || {}),
  };
  try {
    appendFileSync(GATE_LOG_FILE, JSON.stringify(event) + "\n", "utf-8");
  } catch (_err) {
    // best effort — non crashare mai
  }
}

function pruneTaskOutput(text) {
  // Prune long subagent outputs (>1500 chars) to prevent nested context explosion
  if (!text || text.length <= 1500) return text;

  const head = text.slice(0, 650);
  const tailIndex = text.lastIndexOf("## VERIFICA");
  const tail = tailIndex !== -1 ? text.slice(tailIndex) : text.slice(-650);

  return `${head}\n\n... [Output intermedio di task compresso dal verifica-gate per risparmio token (${text.length - 1300} caratteri omessi)] ...\n\n${tail}`;
}

// Estrae l'exit code dal result V2 (metadata.exit oppure output.exit).
function extractExitCode(result) {
  if (!result || typeof result !== "object") return null;
  if (result.metadata && typeof result.metadata.exit === "number") return result.metadata.exit;
  if (result.output && typeof result.output === "object" && typeof result.output.exit === "number") {
    return result.output.exit;
  }
  return null;
}

// ── Classificazione dei comandi di verifica ──
// Distingue un VERO fallimento di verifica da un fallimento infrastrutturale
// (venv assente, comando malformato/vuoto, errori di shell). Solo i veri
// fallimenti ancorano la confidenza; gli altri NON producono falsi positivi.

const VERIFICATION_TOOL_RE = /\b(pytest|pylint|mypy|python3|python|unittest|npm\s+test|jest|vitest|tsc)\b/i;

// Errori a livello di shell/ambiente: il comando non è stato realmente eseguito.
const INFRA_ERROR_RES = [
  /command not found/i,
  /:\s*not found\b/i,
  /no such file or directory/i,
  /cannot source/i,
  /cannot execute/i,
  /permission denied/i,
  /syntax error near/i,
  /unbound variable/i,
  /is a directory/i,
  /not a valid/i,
  /\bENOENT\b/,
  /failed to activate/i,
];

// Segnali di un fallimento reale di test/lint/type-check.
const REAL_FAILURE_RES = [
  /\bFAILED\b/,
  /\b\d+\s+failed\b/i,
  /\bAssertionError\b/,
  /\bSyntaxError\b/,
  /Traceback \(most recent call last\)/,
  /\bExit code:\s*[1-9]/i,
  /\b[1-9]\d*\s+errors?\b/i,
  /rated at (?!10\.00)(?:-inf|-?\d+(?:\.\d+)?)\/10/i,
  /\berror:\s/i,
];

function matchesAny(regexes, text) {
  return regexes.some(re => re.test(text || ""));
}

// Estrae i target di `source X` / `. X`, tollerando quoting e chain `;`/`&&`/`|`.
function extractSourceTargets(cmd) {
  const out = [];
  const re = /(?:^|[;&|]\s*)(?:source|\.)\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))/g;
  let m;
  while ((m = re.exec(cmd)) !== null) {
    const target = m[1] || m[2] || m[3];
    if (target) out.push(target);
  }
  return out;
}

function expandTilde(p) {
  if (typeof p !== "string") return p;
  if (p === "~") return homedir();
  if (p.startsWith("~/")) return join(homedir(), p.slice(2));
  return p;
}

// Individua il pattern fragile `source .../activate` (o `. .../activate`).
function fragileActivationTargets(cmd) {
  return extractSourceTargets(cmd)
    .map(expandTilde)
    .filter(t => /(^|\/)activate$/.test(t) || /bin\/activate$/.test(t));
}

// Individua l'uso ROBUSTO del binario del venv (/path/venv/bin/python|pytest|...).
function hasDirectVenvBinary(cmd) {
  return /(?:^|\s)(?:[\w.~/-]*\/)?bin\/(?:python|python3|pytest|pylint|mypy)\b/.test(cmd);
}

function isVerificationCommand(cmd) {
  return VERIFICATION_TOOL_RE.test(cmd || "");
}

/**
 * Classifica l'esito di un comando shell candidato alla verifica.
 * @returns {{applicable:boolean, realFailure:boolean, reason:string,
 *            exitCode:(number|null), envMode:string}}
 */
function classifyVerificationOutcome(cmd, exitCode, status, text) {
  const command = (cmd || "").trim();
  const exit = (typeof exitCode === "number") ? exitCode : null;

  if (!command) {
    return { applicable: false, realFailure: false, reason: "comando vuoto", exitCode: exit, envMode: "system" };
  }
  if (!isVerificationCommand(command)) {
    return { applicable: false, realFailure: false, reason: "nessun comando di verifica riconosciuto", exitCode: exit, envMode: "system" };
  }

  const activations = fragileActivationTargets(command);
  const envMode = hasDirectVenvBinary(command)
    ? "direct-binary"
    : (activations.length > 0 ? "source-activate" : "system");

  if (status !== "error" && (exit === null || exit === 0)) {
    return { applicable: true, realFailure: false, reason: "esito ok", exitCode: exit, envMode };
  }

  // 1) Errore infrastrutturale nel testo (shell/ambiente) → non eseguibile.
  if (matchesAny(INFRA_ERROR_RES, text)) {
    return { applicable: false, realFailure: false, reason: "errore infrastrutturale (shell/ambiente)", exitCode: exit, envMode };
  }

  // 2) Attivazione venv fragile con path inesistente → non eseguibile.
  const missing = activations.filter(t => !existsSync(t));
  if (missing.length > 0) {
    return { applicable: false, realFailure: false, reason: `venv/activate assente: ${missing.join(", ")}`, exitCode: exit, envMode };
  }

  // 3) Fallimento reale con evidenza di test/lint.
  if (matchesAny(REAL_FAILURE_RES, text)) {
    return { applicable: true, realFailure: true, reason: "fallimento reale di verifica", exitCode: exit, envMode };
  }

  // 4) Exit != 0 senza evidenza chiara né causa infrastrutturale → indeterminato.
  //    Nessun ancoraggio automatico: si segnala la non conclusività.
  return { applicable: true, realFailure: false, reason: "exit != 0 senza evidenza di fallimento reale", exitCode: exit, envMode };
}

export { classifyVerificationOutcome, isVerificationCommand, fragileActivationTargets, hasDirectVenvBinary };

export default {
  id: "verifica-gate",
  async setup(ctx) {
    ensureLogDir();
    initHeadroomOffset();

    await ctx.tool.hook("execute.after", (event) => {
      try {
        const toolName = typeof event.tool === "string" ? event.tool : "";

        // Traccia gli exit code dei comandi shell di verifica (pytest/pylint/mypy/python...).
        // Il comando NON viene rieseguito dal gate: si osserva l'esecuzione reale e la
        // si classifica (fallimento reale vs infrastrutturale) prima di ancorare.
        if (toolName === "shell" || toolName === "bash") {
          const args = (event.input && typeof event.input === "object") ? event.input : {};
          const cmd = (args.command || "").toString();
          if (!isVerificationCommand(cmd)) return; // non è una verifica: ignora

          const { text } = extractText(event.result);
          const exitCode = extractExitCode(event.result);
          const outcome = classifyVerificationOutcome(cmd, exitCode, event.status, text);

          logEvent(null, "shell_verification", null, cmd.slice(0, 80), {
            command: cmd.slice(0, 200),
            exit_code: outcome.exitCode,
            applicable: outcome.applicable,
            real_failure: outcome.realFailure,
            env_mode: outcome.envMode,
            reason: outcome.reason,
          });

          if (outcome.realFailure) {
            lastFailedVerification = {
              cmd: cmd.slice(0, 80),
              exitCode: outcome.exitCode,
              reason: outcome.reason,
              ts: new Date().toISOString(),
            };
            lastIndeterminateVerification = null;
          } else if (outcome.applicable && exitCode !== null && exitCode !== 0) {
            lastIndeterminateVerification = {
              cmd: cmd.slice(0, 80),
              exitCode: outcome.exitCode,
              reason: outcome.reason,
              ts: new Date().toISOString(),
            };
          }
          return;
        }

        if (toolName !== "subagent" && toolName !== "task") return;

        const { text, kind } = extractText(event.result);
        const verifica = parseVerifica(text);
        const subagentType = extractSubagentType(event.input);
        const promptSnippet = extractPromptSnippet(event.input);

        let warning = "";

        // Ancoraggio SOLO su fallimenti reali; gli esiti infrastrutturali/indeterminati
        // producono un avviso informativo senza ancorare la confidenza.
        const hasRealFailure = !!lastFailedVerification;
        if (lastFailedVerification) {
          warning += `\n\n⚠️ [verifica-gate] EXIT CODE FAILURE: il comando di verifica \`${lastFailedVerification.cmd}\` ha restituito exit-code ${lastFailedVerification.exitCode} (${lastFailedVerification.reason}). Confidenza ancorata a <= 35.`;
          logEvent(subagentType, "exit_code_failure", 35, promptSnippet, {
            command: lastFailedVerification.cmd,
            exit_code: lastFailedVerification.exitCode,
            reason: lastFailedVerification.reason,
            anchored: true,
          });
          lastFailedVerification = null; // reset
        } else if (lastIndeterminateVerification) {
          warning += `\n\n⚠️ [verifica-gate] VERIFICA NON CONCLUSA: il comando \`${lastIndeterminateVerification.cmd}\` ha restituito exit-code ${lastIndeterminateVerification.exitCode} senza evidenza di fallimento reale (${lastIndeterminateVerification.reason}). Nessun ancoraggio automatico: ricontrollare l'esito.`;
          logEvent(subagentType, "indeterminate_verification", null, promptSnippet, {
            command: lastIndeterminateVerification.cmd,
            exit_code: lastIndeterminateVerification.exitCode,
            reason: lastIndeterminateVerification.reason,
            anchored: false,
          });
          lastIndeterminateVerification = null; // reset
        }

        if (!verifica.present) {
          warning += "\n\n⚠️ [verifica-gate] Il subagent NON ha compilato il blocco ## VERIFICA. Non riassumere come verificato: ri-delega UNA volta chiedendo di compilare il blocco, oppure segnala all'utente che il risultato non e' verificato.";
          logEvent(subagentType, "missing_verifica", null, promptSnippet);
        } else if ((verifica.confidenza !== null && verifica.confidenza < 40) || hasRealFailure) {
          if (!hasRealFailure) {
            warning += "\n\n⚠️ [verifica-gate] Confidenza < 40: ri-delega a @coder per un'analisi approfondita o segnala l'incompiutezza all'utente.";
            logEvent(subagentType, "low_confidence", verifica.confidenza, promptSnippet);
          }
        }

        if (verifica.mechanicalError && (verifica.confidenza === null || verifica.confidenza >= 70) && !hasRealFailure) {
          warning += "\n\n⚠️ [verifica-gate] Rilevati errori meccanici o fallimenti nei test/traceback nell'output. Verificare attentamente l'esito.";
          logEvent(subagentType, "mechanical_error", verifica.confidenza, promptSnippet);
        }

        // Token saving del task (headroom): delta incrementale dal log eventi condiviso
        const tokenDelta = readHeadroomDelta();
        const tokenLine = buildTokenSavingLine(tokenDelta);
        logEvent(subagentType, "token_saving", null, promptSnippet, {
          tokens_saved: tokenDelta.tokensSaved,
          compressions: tokenDelta.compressions,
          original_bytes: tokenDelta.originalBytes,
          injected_bytes: tokenDelta.injectedBytes,
          session_tokens_saved: headroomState.sessionTokensSaved,
        });

        // Prune + warning, poi inietta la riga token come ULTIMA riga (del ## VERIFICA o in coda)
        const prunedText = pruneTaskOutput(text) + warning;
        const finalText = appendTokenLine(prunedText, tokenLine);
        event.result = replaceResultText(event.result, kind, text, finalText);

      } catch (_err) {
        // Non crashare mai il tool execution
      }
    });
  },
};
