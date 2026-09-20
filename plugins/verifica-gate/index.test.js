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
