#!/usr/bin/env python3
"""stress-headroom-mcp.py — Stress test del MCP headroom v2 via JSON-RPC (subprocess).

Spawna `headroom mcp serve` in un processo fresco (NON il server della sessione opencode) e
verifica: compress (integrità/savings), retrieve (local/fallback plugin/reale), stats, latenze,
error path, e E2E plugin->MCP.

Uso:
    ~/.local/share/opencode/headroom-venv/bin/python scripts/stress-headroom-mcp.py

Non tocca lo store reale in scrittura (solo lettura per l'hash reale). Termina SEMPRE con exit 0.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
HR_BIN = HOME / ".local" / "share" / "opencode" / "headroom-venv" / "bin" / "headroom"
REPO = Path(__file__).resolve().parent.parent
HELPER_JS = REPO / "scripts" / "stress-headroom.js"
SCRATCH = Path(os.environ.get("HR_STRESS_DIR", "/tmp/opencode/headroom-stress"))
B_STORE = SCRATCH / "b_store"
B_WS = SCRATCH / "b_ws"
B_WS2 = SCRATCH / "b_ws_real"
REAL_STORE = HOME / ".config" / "opencode" / "context-store"
REAL_HASH = "1c767c321fe2d0bd"

PASS = 0
FAIL = 0
LAT: dict[str, list[float]] = {"compress": [], "retrieve": [], "stats": []}


def check(cond: bool, label: str) -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")
    return cond


class MCP:
    """Minimal JSON-RPC client over stdio for `headroom mcp serve`."""

    def __init__(self, env: dict[str, str]) -> None:
        self.proc = subprocess.Popen(
            [str(HR_BIN), "mcp", "serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        self._id = 0
        self._init()

    def _read_msg(self, timeout: float) -> dict | None:
        assert self.proc.stdout is not None
        rlist, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not rlist:
            return None
        line = self.proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line.startswith("{"):
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _wait(self, target: int, timeout: float) -> dict | None:
        end = time.time() + timeout
        while time.time() < end:
            msg = self._read_msg(max(0.1, end - time.time()))
            if msg and msg.get("id") == target:
                return msg
        return None

    def _send(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _init(self) -> None:
        self._send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "stress", "version": "1"}}})
        self._wait(1, 30)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call(self, name: str, args: dict, timeout: float = 180) -> tuple[dict | None, float]:
        self._id += 1
        rid = self._id
        t0 = time.perf_counter()
        self._send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                    "params": {"name": name, "arguments": args}})
        msg = self._wait(rid, timeout)
        dt = time.perf_counter() - t0
        if not msg:
            return None, dt
        text = ""
        try:
            text = msg["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None, dt
        try:
            return json.loads(text), dt
        except json.JSONDecodeError:
            return {"_raw": text}, dt

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:  # noqa: BLE001
                pass


def make_payload(nbytes: int, seed: int) -> str:
    unit = f"line {seed} service=api request_id=%d status=%s latency_ms=%d"
    out: list[str] = []
    n = 0
    i = 0
    while n < nbytes:
        i += 1
        line = unit % (i, "ERROR" if i % 500 == 0 else "ok", i % 300)
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for d in (B_STORE, B_WS, B_WS2):
        if d.exists():
            for p in sorted(d.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
        d.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["HEADROOM_WORKSPACE_DIR"] = str(B_WS)
    env["OPENCODE_CONTEXT_STORE_DIR"] = str(B_STORE)

    # E2E setup: il plugin scrive 20 payload in B_STORE + eventi in B_WS
    out_json = SCRATCH / "b_plugin_payloads.json"
    r = subprocess.run(["node", str(HELPER_JS), "--emit-for-mcp", str(B_STORE), str(B_WS), str(out_json)],
                       cwd=str(REPO), capture_output=True, text=True)
    plugin_payloads = json.loads(out_json.read_text()) if out_json.exists() else []
    print(f"E2E setup: node exit={r.returncode}, plugin payloads={len(plugin_payloads)}")
    check(len(plugin_payloads) == 20, "plugin helper ha emesso 20 payload")

    mcp = MCP(env)
    print("MCP b-server: initialized")

    # ── B1: compress 20 (alternato 100KB / 1MB) ──
    hashes: list[tuple[str, str]] = []  # (hash, kind)
    accum_saved = 0
    for i in range(20):
        nbytes = 102400 if i % 2 == 0 else 1048576
        payload = make_payload(nbytes, i)
        res, dt = mcp.call("headroom_compress", {"content": payload})
        LAT["compress"].append(dt)
        ok = res is not None and "hash" in res
        check(ok, f"B1 compress #{i} risposta integra")
        if not ok:
            continue
        o = res.get("original_tokens", 0)
        c = res.get("compressed_tokens", 0)
        saved = res.get("tokens_saved", 0)
        sp = res.get("savings_percent", 0.0)
        expected = round((o - c) / o * 100, 1) if o > 0 else 0.0
        check(abs(sp - expected) < 0.2, f"B1 #{i} savings% coerente ({sp} vs {expected})")
        check(not (saved == 0 and sp > 0.0), f"B1 #{i} no 100% spurio con saved=0")
        check(sp <= 100.0, f"B1 #{i} savings<=100")
        accum_saved += saved
        hashes.append((res["hash"], "compress"))
    print(f"B1: 20 compress fatte (hash={len(hashes)})")

    # ── B2a: retrieve hashes da compress (local) ──
    for h, kind in hashes[:20]:
        res, dt = mcp.call("headroom_retrieve", {"hash": h})
        LAT["retrieve"].append(dt)
        ok = res is not None and res.get("source") == "local" and res.get("original_content")
        check(ok, f"B2a retrieve local {h[:8]}")

    # ── B2b + D: retrieve hashes plugin (fallback) + byte-equal E2E ──
    e2e_ok = 0
    for item in plugin_payloads:
        res, dt = mcp.call("headroom_retrieve", {"hash": item["hash"]})
        LAT["retrieve"].append(dt)
        ok = res is not None and res.get("source") == "opencode-context-store"
        check(ok, f"B2b/D source fallback per {item['hash'][:8]}")
        if ok:
            got = res.get("original_content", "").encode("utf-8")
            want = Path(item["orig"]).read_bytes()
            if got == want:
                e2e_ok += 1
            else:
                check(False, f"D byte-equal {item['hash'][:8]} (got {len(got)} vs want {len(want)})")
    check(e2e_ok == len(plugin_payloads), f"D E2E byte-equal {e2e_ok}/{len(plugin_payloads)}")
    print(f"B2b/D: {e2e_ok}/{len(plugin_payloads)} byte-equal via fallback")

    # ── B2c: hash reale (lettura) via secondo server con store reale ──
    env2 = dict(os.environ)
    env2["HEADROOM_WORKSPACE_DIR"] = str(B_WS2)
    env2["OPENCODE_CONTEXT_STORE_DIR"] = str(REAL_STORE)
    mcp2 = MCP(env2)
    real_ok = 0
    for _ in range(10):
        res, dt = mcp2.call("headroom_retrieve", {"hash": REAL_HASH})
        LAT["retrieve"].append(dt)
        if res and res.get("source") == "opencode-context-store":
            got = res.get("original_content", "").encode("utf-8")
            want = (REAL_STORE / f"{REAL_HASH}.txt").read_bytes()
            if got == want:
                real_ok += 1
    check(real_ok == 10, f"B2c hash reale byte-equal {real_ok}/10")
    print(f"B2c: hash reale {REAL_HASH} -> {real_ok}/10 byte-equal")

    # ── B5: error path + sessione viva ──
    res, dt = mcp.call("headroom_retrieve", {"hash": "ffffffffffffffff"})
    check(res is not None and "error" in res, "B5 hash inesistente -> errore pulito")
    stats_after, dt2 = mcp.call("headroom_stats", {})
    LAT["stats"].append(dt2)
    check(stats_after is not None, "B5 sessione ancora viva dopo errore")

    # ── B3: stats finali (b-server) ──
    stats, _ = mcp.call("headroom_stats", {})
    ok = stats is not None
    check(ok, "B3 stats call")
    if ok:
        comp = stats.get("compressions", 0)
        retr = stats.get("retrievals", 0)
        tsaved = stats.get("total_tokens_saved", 0)
        check(comp >= 20, f"B3 compressions>=20 (got {comp})")
        check(retr >= 40, f"B3 retrievals>=40 (got {retr})")
        check(isinstance(tsaved, int) and tsaved == accum_saved,
              f"B3 total_tokens_saved coerente col calcolo ({tsaved} vs {accum_saved})")
        check(len(stats.get("recent_events", [])) > 0, "B3 recent_events non vuoto")
        ah = stats.get("auto_headroom", {})
        check(ah.get("compressions", 0) >= 20, f"B3 auto_headroom popolato (got {ah})")
        check(ah.get("tokens_saved", 0) > 0, "B3 auto_headroom tokens_saved>0")
        comb = stats.get("combined", {})
        check(comb.get("total_tokens_saved", -1) == tsaved + ah.get("tokens_saved", 0),
              f"B3 combined include auto ({comb.get('total_tokens_saved')} vs {tsaved + ah.get('tokens_saved', 0)})")
        for key in ("compressions", "retrievals", "total_tokens_saved", "recent_events"):
            check(key in stats, f"B3 chiave presente: {key}")
        print(f"B3 stats: compressions={comp} retrievals={retr} tokens_saved={tsaved} auto_headroom={ah}")
    mcp.close()
    mcp2.close()

    # ── B4: latenze ──
    print("B4 latenze (s):")
    lat_summary = {}
    for k, vals in LAT.items():
        if vals:
            lat_summary[k] = {"n": len(vals), "avg": round(sum(vals) / len(vals), 4), "max": round(max(vals), 4)}
            print(f"  {k:<9} n={len(vals):>3} avg={lat_summary[k]['avg']} max={lat_summary[k]['max']}")

    result = {
        "pass": PASS, "fail": FAIL, "latencies": lat_summary,
        "compress_hashes": [h for h, _ in hashes], "e2e_ok": e2e_ok,
        "plugin_payloads": len(plugin_payloads), "real_ok": real_ok,
    }
    (SCRATCH / "B-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSUMMARY B: PASS={PASS} FAIL={FAIL}")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as err:  # noqa: BLE001
        print(f"FATAL B: {err}")
        rc = 0
    sys.exit(0)
