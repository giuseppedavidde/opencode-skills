import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const sandbox = mkdtempSync(join(tmpdir(), "auto-headroom-test-"));
process.env.CONTEXT_STORE_DIR = join(sandbox, "context-store");
process.env.HEADROOM_WORKSPACE_DIR = join(sandbox, "headroom");

const plugin = await import("./index.js");
const { isPassthrough } = plugin;

async function hookFor() {
  const hooks = {};
  await plugin.default.setup({ tool: { hook: (name, fn) => { hooks[name] = fn; } } });
  return hooks["execute.after"];
}

const LONG_JSON = JSON.stringify({ ticker: "AAPL", rows: Array.from({ length: 200 }, (_, i) => ({ strike: 100 + i, delta: 0.5 })) });
const LONG_TEXT = Array.from({ length: 80 }, (_, i) => `line ${i} ${"x".repeat(40)}`).join("\n");

test.after(() => rmSync(sandbox, { recursive: true, force: true }));

test("isPassthrough: trading tools and store reads pass through", () => {
  assert.equal(isPassthrough("trading_analyze_stock", {}), true);
  assert.equal(isPassthrough("bash", { command: "python3 ~/.config/opencode/scripts/context_store_reader.py abc --lines 1 5" }), true);
  assert.equal(isPassthrough("bash", { command: "ls -la" }), false);
  assert.equal(isPassthrough("read", { filePath: "/tmp/x.txt" }), false);
  assert.equal(isPassthrough("headroom_stats", {}), false);
});

test("hook: a trading result reaches the model unchanged", async () => {
  const hook = await hookFor();
  const result = { content: [{ type: "text", text: LONG_JSON }] };
  const event = { status: "completed", tool: "trading_fetch_options_chain", input: { ticker: "AAPL" }, result };
  hook(event);
  assert.equal(event.result, result);
  assert.equal(event.result.content[0].text.length, LONG_JSON.length);
});

test("hook: other long results are still compressed", async () => {
  const hook = await hookFor();
  const event = { status: "completed", tool: "bash", input: { command: "cat big.log" }, result: { output: LONG_TEXT } };
  hook(event);
  assert.match(event.result.output, /AUTO-HEADROOM COMPRESSED/);
  assert.ok(event.result.output.length < LONG_TEXT.length);
});
