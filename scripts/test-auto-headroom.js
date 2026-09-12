// test-auto-headroom.js — Verification test for Auto-Headroom Plugin and Chunk Retrieval
// ERMETICO di default: se CONTEXT_STORE_DIR / HEADROOM_WORKSPACE_DIR non sono impostati,
// usa directory temporanee, così il run standard non tocca lo store reale né collide con
// file stale. Il plugin è importato DINAMICAMENTE dopo aver impostato l'env (STORE_DIR del
// plugin è una costante di modulo, quindi va decisa prima dell'import).
// Flag --seed-legacy: inietta un file in formato legacy a hash noto per testare il self-heal.
import { existsSync, readFileSync, writeFileSync, mkdtempSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import { createHash } from "crypto";

const EXPLICIT_STORE = process.env.CONTEXT_STORE_DIR;
const STORE_DIR = EXPLICIT_STORE || mkdtempSync(join(tmpdir(), "hr-test-store-"));
if (!EXPLICIT_STORE) process.env.CONTEXT_STORE_DIR = STORE_DIR;
const EXPLICIT_WS = process.env.HEADROOM_WORKSPACE_DIR;
const WORKSPACE_DIR = EXPLICIT_WS || mkdtempSync(join(tmpdir(), "hr-test-ws-"));
if (!EXPLICIT_WS) process.env.HEADROOM_WORKSPACE_DIR = WORKSPACE_DIR;
const SHARED_STATS_FILE = join(WORKSPACE_DIR, "session_stats.jsonl");
const SEED_LEGACY = process.argv.includes("--seed-legacy");

function sha256(text) {
  return createHash("sha256").update(text, "utf-8").digest("hex").slice(0, 16);
}

// Conta le righe "reali" in modo coerente con readlines()/read tool: nessuna riga fantasma finale.
function countRealLines(text) {
  const parts = text.split("\n");
  if (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
  return parts.length;
}

// Fixture 100 righe usata sia dal seed legacy sia dal Test 2 (stesso hash deterministico).
function buildLargeContent() {
  const lines = [];
  for (let i = 1; i <= 100; i++) {
    lines.push(`Line ${i}: This is sample log or code line content for testing auto-headroom compression.`);
  }
  lines[50] = "Line 51: ERROR AssertionError: Test failed in module calculation";
  return lines.join("\n");
}

async function runTests() {
  console.log("🚀 Running Auto-Headroom Plugin Verification Tests...\n");
  console.log(`   STORE_DIR=${STORE_DIR}`);
  console.log(`   WORKSPACE_DIR=${WORKSPACE_DIR}\n`);

  const { AutoHeadroomPlugin } = await import("../plugins/auto-headroom.js");
  const plugin = await AutoHeadroomPlugin({ directory: process.cwd() });
  const hook = plugin["tool.execute.after"];

  if (SEED_LEGACY) {
    const content = buildLargeContent();
    const hash = sha256(content);
    const legacyRaw = `# [selective-retrieval] Index available at ${hash}_index.json | Total lines: ${countRealLines(content)} | Use start_line/end_line to read specific chunks!\n` + content;
    writeFileSync(join(STORE_DIR, `${hash}.txt`), legacyRaw, "utf-8");
    writeFileSync(join(STORE_DIR, `${hash}_index.json`),
      JSON.stringify({ hash, total_lines: countRealLines(content), total_bytes: Buffer.byteLength(content),
        chunk_size: 50, total_chunks: 2, chunks: [] }, null, 2), "utf-8");
    console.log(`🧪 [seed-legacy] iniettato file legacy ${hash}.txt (header + ${countRealLines(content)} righe) in ${STORE_DIR}\n`);
  }

  let passed = 0;
  let failed = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(`  ✅ PASSED: ${message}`);
      passed++;
    } else {
      console.error(`  ❌ FAILED: ${message}`);
      failed++;
    }
  }

  // TEST 1: Output < 800 chars should NOT be compressed
  {
    console.log("Test 1: Output sotto i 800 caratteri");
    const input = { tool: "bash", args: { command: "echo hello" } };
    const output = { output: "Short output string" };
    const result = await hook(input, output);
    assert(result === undefined, "L'output sotto i 800 char è lasciato inalterato");
  }

  // TEST 2: Output >= 800 chars SHOULD be compressed
  let generatedHash = null;
  {
    console.log("\nTest 2: Output largo (>= 800 caratteri)");
    const largeContent = buildLargeContent();

    const input = { tool: "bash", args: { command: "python3 test_runner.py" } };
    const output = { output: largeContent };
    const result = await hook(input, output);

    assert(result && typeof result.output === "string", "Restituita la versione compressa dell'output");
    assert(result.output.includes("AUTO-HEADROOM COMPRESSED"), "Contiene l'intestazione AUTO-HEADROOM COMPRESSED");
    assert(result.output.includes("EVIDENZE / ERRORI RILEVATI"), "Rileva correttamente le righe di errore");

    const match = result.output.match(/hash=([a-f0-9]{16})/);
    assert(match !== null, "Estratto hash SHA-256 a 16 caratteri");
    if (match) {
      generatedHash = match[1];

      // Controlla la presenza dei file in context-store
      const txtFile = join(STORE_DIR, `${generatedHash}.txt`);
      const indexFile = join(STORE_DIR, `${generatedHash}_index.json`);

      assert(existsSync(txtFile), `File memorizzato su disk: ${txtFile}`);
      assert(existsSync(indexFile), `Indice chunk memorizzato su disk: ${indexFile}`);

      if (existsSync(indexFile)) {
        const indexJson = JSON.parse(readFileSync(indexFile, "utf-8"));
        assert(indexJson.format_version === 2, "Index nel formato corrente (format_version=2)");
        assert(indexJson.total_lines === 100, "Conteggio totale righe corretto nell'indice");
        assert(indexJson.total_chunks === 2, "Numero di chunk da 50 righe corretto (2 chunks per 100 righe)");

        // Coerenza index <-> file: nessun header nel .txt (fix off-by-one)
        const fileContent = readFileSync(txtFile, "utf-8");
        const realLines = countRealLines(fileContent);
        assert(!fileContent.startsWith("# [selective-retrieval]"), "Nessun header legacy nel .txt");
        assert(fileContent === largeContent, "Il file .txt contiene il contenuto originale verbatim");
        assert(indexJson.total_lines === realLines,
          `index.total_lines (${indexJson.total_lines}) == righe reali file (${realLines})`);
        const readBack = fileContent.split("\n").slice(0, indexJson.total_lines).join("\n");
        assert(readBack === largeContent,
          "Leggendo 1..total_lines si ottiene esattamente il contenuto originale");
      }

      // Evento auto-compressione registrato nel file stats condiviso di headroom
      assert(existsSync(SHARED_STATS_FILE), `Evento stats scritto: ${SHARED_STATS_FILE}`);
      if (existsSync(SHARED_STATS_FILE)) {
        const evtLines = readFileSync(SHARED_STATS_FILE, "utf-8").trim().split("\n");
        const last = JSON.parse(evtLines[evtLines.length - 1]);
        assert(last.source === "opencode-plugin", "L'evento stats ha source=opencode-plugin");
        assert(last.original_bytes === Buffer.byteLength(largeContent, "utf-8"),
          "L'evento registra original_bytes corretti");
        assert(typeof last.tokens_saved === "number" && last.tokens_saved >= 0,
          "L'evento registra tokens_saved stimato");
      }
    }
  }

  // TEST 3: Selective retrieval (read tool on context-store with start_line) should pass through
  {
    console.log("\nTest 3: Selective Retrieval (read con start_line su context-store)");
    const input = {
      tool: "read",
      args: {
        path: `${STORE_DIR}/${generatedHash}.txt`,
        start_line: 1,
        end_line: 50,
      },
    };
    const output = { text: "Sample chunk lines 1 to 50..." };
    const result = await hook(input, output);
    assert(result === undefined, "Il selective retrieval mirato non viene ricompresso");
  }

  console.log(`\n📊 Risultati Test: ${passed} passati, ${failed} falliti.`);
  if (failed > 0) {
    process.exit(1);
  }
}

runTests().catch(err => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
