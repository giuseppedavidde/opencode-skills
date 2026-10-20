import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  classifyVerificationOutcome,
  isVerificationCommand,
  fragileActivationTargets,
  hasDirectVenvBinary,
  isExploratoryCommand,
  normalizeCommand,
  createVerificationState,
  resetVerificationState,
  applyVerificationEvent,
  finalVerdict,
  evaluateVerificationState,
} from "./index.js";

test("isVerificationCommand: riconosce i tool di verifica", () => {
  assert.equal(isVerificationCommand("python3 -m pytest -q"), true);
  assert.equal(isVerificationCommand("/tmp/.venv/bin/pylint src"), true);
  assert.equal(isVerificationCommand("npm test"), true);
  assert.equal(isVerificationCommand("ls -la"), false);
});

test("comando ok (exit 0) -> applicable, nessun ancoraggio", () => {
  const r = classifyVerificationOutcome("python3 -m pytest -q", 0, "success", "5 passed");
  assert.equal(r.applicable, true);
  assert.equal(r.realFailure, false);
  assert.equal(r.reason, "esito ok");
});

test("fallimento reale pytest (exit 1, FAILED) -> realFailure", () => {
  const r = classifyVerificationOutcome("python3 -m pytest -q", 1, "error", "FAILED tests/test_x.py::test_a");
  assert.equal(r.realFailure, true);
  assert.equal(r.applicable, true);
});

test("fallimento reale pylint con rating negativo -> realFailure", () => {
  const text = "Your code has been rated at 4.00/10";
  const r = classifyVerificationOutcome("python3 -m pylint src", 16, "error", text);
  assert.equal(r.realFailure, true);
});

test("pylint pulito 10.00/10 non e' fallimento reale", () => {
  const r = classifyVerificationOutcome("python3 -m pylint src", 0, "success", "Your code has been rated at 10.00/10");
  assert.equal(r.realFailure, false);
  assert.equal(r.applicable, true);
});

test("comando sorgente attivazione venv inesistente -> infrastrutturale (no ancoraggio)", () => {
  const cmd = "source /nonexistent/venv-xyz/bin/activate; cd /home/giuseppe/Progetti/Github/opencode-skills; python3 -m pytest";
  const r = classifyVerificationOutcome(cmd, 1, "error", "pytest: command not found");
  assert.equal(r.applicable, false);
  assert.equal(r.realFailure, false);
  assert.match(r.reason, /infrastrutturale|assente/);
});

test("'source: command not found' (shell non supporta source) -> infrastrutturale", () => {
  const cmd = "source ~/.local/share/opencode/trading-mcp-venv/bin/activate; python3 -m pytest";
  const r = classifyVerificationOutcome(cmd, 127, "error", "/bin/sh: 1: source: not found");
  assert.equal(r.applicable, false);
  assert.equal(r.realFailure, false);
});

test("syntax error nel comando malformato -> infrastrutturale", () => {
  const r = classifyVerificationOutcome("python3 -m pytest ...", 2, "error", "sh: 1: Syntax error near unexpected token");
  assert.equal(r.applicable, false);
  assert.equal(r.realFailure, false);
});

test("comando vuoto -> non applicabile", () => {
  const r = classifyVerificationOutcome("   ", 1, "error", "");
  assert.equal(r.applicable, false);
  assert.match(r.reason, /vuoto/);
});

test("comando non di verifica -> non applicabile", () => {
  const r = classifyVerificationOutcome("echo hello", 1, "error", "boom");
  assert.equal(r.applicable, false);
  assert.equal(r.realFailure, false);
});

test("exit != 0 senza evidenza -> indeterminato (no ancoraggio automatico)", () => {
  const r = classifyVerificationOutcome("python3 -m mypy src", 2, "error", "oops generic failure");
  assert.equal(r.applicable, true);
  assert.equal(r.realFailure, false);
  assert.match(r.reason, /evidenza/);
});

test("attivazione venv ESISTENTE + fallimento reale -> realFailure", () => {
  const dir = mkdtempSync(join(tmpdir(), "vg-venv-"));
  try {
    const binDir = join(dir, "bin");
    mkdirSync(binDir, { recursive: true });
    const activate = join(binDir, "activate");
    writeFileSync(activate, "# fake activate\n");
    const cmd = `source ${activate}; pytest -q`;
    const r = classifyVerificationOutcome(cmd, 1, "error", "1 failed, 2 passed");
    assert.equal(r.realFailure, true);
    assert.equal(r.envMode, "source-activate");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("binario venv diretto -> envMode direct-binary", () => {
  const r = classifyVerificationOutcome("/tmp/.venv/bin/python -m pytest", 0, "success", "ok");
  assert.equal(r.envMode, "direct-binary");
  assert.equal(hasDirectVenvBinary("/tmp/.venv/bin/pytest -q"), true);
});

test("fragileActivationTargets estrae il path con tilde espanso", () => {
  const targets = fragileActivationTargets("source ~/venv/bin/activate && pytest");
  assert.equal(targets.length, 1);
  assert.ok(targets[0].endsWith("/venv/bin/activate"));
  assert.equal(targets[0].startsWith("~"), false);
});

// ── Reducer "ultimo esito vince" ──

const FAIL_CMD = "cd /tmp/opencode && python3 stx_greeks.py";

test("normalizeCommand: trim + collapse whitespace", () => {
  assert.equal(normalizeCommand("  cd  /tmp/opencode &&\n python3  x.py "), "cd /tmp/opencode && python3 x.py");
  assert.equal(normalizeCommand(undefined), "");
});

test("isExploratoryCommand: python -c e heredoc non ancorabili, test runner si'", () => {
  assert.equal(isExploratoryCommand('python3 -c "print(1)"'), true);
  assert.equal(isExploratoryCommand("python3 - <<'EOF'\nprint(1)\nEOF"), true);
  assert.equal(isExploratoryCommand("python3 -m pytest -q"), false);
  assert.equal(isExploratoryCommand("pytest -q"), false);
  assert.equal(isExploratoryCommand("python3 script.py"), false);
});

test("fallimento poi successo dello STESSO comando -> nessun ancoraggio", () => {
  const v = evaluateVerificationState([
    { command: FAIL_CMD, exitCode: 1, status: "error", text: "Traceback (most recent call last): boom" },
    { command: FAIL_CMD, exitCode: 0, status: "success", text: "ok" },
  ]);
  assert.equal(v.anchored, false);
  assert.equal(v.failure, null);
  assert.equal(v.indeterminate, null);
});

test("fallimento poi fallimento -> ancoraggio si'", () => {
  const v = evaluateVerificationState([
    { command: FAIL_CMD, exitCode: 1, status: "error", text: "Traceback (most recent call last): boom" },
    { command: FAIL_CMD, exitCode: 2, status: "error", text: "1 failed" },
  ]);
  assert.equal(v.anchored, true);
  assert.equal(v.failure.exitCode, 2);
});

test("solo successi -> nessun ancoraggio", () => {
  const v = evaluateVerificationState([
    { command: "python3 -m pytest -q", exitCode: 0, status: "success", text: "5 passed" },
    { command: "python3 -m pylint src", exitCode: 0, status: "success", text: "rated at 10.00/10" },
  ]);
  assert.equal(v.anchored, false);
  assert.equal(v.indeterminate, null);
});

test("comando esplorativo python -c fallito -> non ancorabile", () => {
  const v = evaluateVerificationState([
    { command: 'python3 -c "import json; print(json.load(open(\'x.json\')))"', exitCode: 1, status: "error", text: "Traceback (most recent call last): FileNotFoundError" },
  ]);
  assert.equal(v.anchored, false);
  assert.equal(v.failure, null);
});

test("heredoc esplorativo fallito -> non ancorabile", () => {
  const v = evaluateVerificationState([
    { command: "python3 - <<'EOF'\nprint(open('ctx.txt').read())\nEOF", exitCode: 1, status: "error", text: "FileNotFoundError: ctx.txt" },
  ]);
  assert.equal(v.anchored, false);
});

test("due task consecutivi: il fallimento del primo non trapela nel secondo", () => {
  const state = createVerificationState();
  applyVerificationEvent(state, { command: FAIL_CMD, exitCode: 1, status: "error", text: "Traceback (most recent call last): boom" });
  assert.equal(finalVerdict(state).anchored, true);
  resetVerificationState(state);
  applyVerificationEvent(state, { command: "python3 -m pytest -q", exitCode: 0, status: "success", text: "3 passed" });
  const v = finalVerdict(state);
  assert.equal(v.anchored, false);
  assert.equal(v.failure, null);
});

test("ordine invertito: successo poi fallimento -> ancoraggio si'", () => {
  const v = evaluateVerificationState([
    { command: FAIL_CMD, exitCode: 0, status: "success", text: "ok" },
    { command: FAIL_CMD, exitCode: 1, status: "error", text: "AssertionError: nope" },
  ]);
  assert.equal(v.anchored, true);
  assert.equal(v.failure.exitCode, 1);
});

test("fallimento reale + exit != 0 senza evidenza su comandi diversi -> ancora il reale", () => {
  const state = createVerificationState();
  applyVerificationEvent(state, { command: "python3 -m pytest -q", exitCode: 1, status: "error", text: "FAILED tests/test_a.py" });
  applyVerificationEvent(state, { command: "python3 -m mypy src", exitCode: 2, status: "error", text: "oops generic failure" });
  const v = finalVerdict(state);
  assert.equal(v.anchored, true);
  assert.match(v.failure.cmd, /pytest/);
});

