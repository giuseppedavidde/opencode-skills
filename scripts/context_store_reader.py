#!/usr/bin/env python3
"""
context_store_reader.py — Helper CLI per il Selective Retrieval dai file compressi in context-store.
Uso:
  python3 scripts/context_store_reader.py <hash> --info
  python3 scripts/context_store_reader.py <hash> --chunk <chunk_index>
  python3 scripts/context_store_reader.py <hash> --lines <start_line> <end_line>
  python3 scripts/context_store_reader.py <hash> --search <pattern>
"""

import sys
import json
import os
from pathlib import Path

STORE_DIR = os.environ.get("CONTEXT_STORE_DIR", os.path.expanduser("~/.config/opencode/context-store"))

def get_paths(content_hash):
    # Rimuovi estensione se passata
    clean_hash = content_hash.replace(".txt", "").replace("_index.json", "")
    txt_path = Path(STORE_DIR) / f"{clean_hash}.txt"
    index_path = Path(STORE_DIR) / f"{clean_hash}_index.json"
    return clean_hash, txt_path, index_path

def show_info(clean_hash, txt_path, index_path):
    if not index_path.exists():
        print(f"❌ Errore: Indice non trovato per hash '{clean_hash}' in {STORE_DIR}")
        sys.exit(1)
    
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"📊 Context Store Info per hash: {clean_hash}")
    print(f"  - Totale righe : {data.get('total_lines')}")
    print(f"  - Totale byte  : {data.get('total_bytes')} bytes")
    print(f"  - Dim. chunk   : {data.get('chunk_size')} righe")
    print(f"  - Totale chunk : {data.get('total_chunks')}")
    print("\n📌 Indice dei Chunk ed Intestazioni:")
    for chunk in data.get("chunks", []):
        headings_str = " | ".join(chunk.get("headings", [])) if chunk.get("headings") else ""
        h_info = f" -> [{headings_str}]" if headings_str else ""
        print(f"  Chunk {chunk['chunk_index']:2d} (Righe {chunk['start_line']:4d}-{chunk['end_line']:4d}): {chunk['preview'][:60]}{h_info}")

def read_chunk(clean_hash, txt_path, index_path, chunk_idx):
    if not txt_path.exists():
        print(f"❌ Errore: File contenuto non trovato per hash '{clean_hash}' in {STORE_DIR}")
        sys.exit(1)
    
    chunk_size = 50
    start_line = (chunk_idx * chunk_size) + 1
    end_line = start_line + chunk_size - 1
    read_lines(txt_path, start_line, end_line)

def read_lines(txt_path, start_line, end_line):
    if not txt_path.exists():
        print(f"❌ Errore: File non trovato: {txt_path}")
        sys.exit(1)
    
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    total = len(lines)
    start_idx = max(0, start_line - 1)
    end_idx = min(total, end_line)
    
    print(f"📖 Lettura {txt_path.name} (Righe {start_idx + 1}-{end_idx} di {total}):")
    print("-" * 60)
    for idx in range(start_idx, end_idx):
        print(f"{idx + 1:5d} | {lines[idx]}", end="")
    print("-" * 60)

def search_pattern(txt_path, pattern):
    if not txt_path.exists():
        print(f"❌ Errore: File non trovato: {txt_path}")
        sys.exit(1)
    
    import re
    regex = re.compile(pattern, re.IGNORECASE)
    matches = []
    
    with open(txt_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            if regex.search(line):
                matches.append((idx, line.strip()))
    
    print(f"🔍 Risultati ricerca '{pattern}' in {txt_path.name} ({len(matches)} corrispondenze):")
    print("-" * 60)
    for line_num, content in matches[:30]:
        print(f"Riga {line_num:5d}: {content[:100]}")
    if len(matches) > 30:
        print(f"... ed altre {len(matches) - 30} corrispondenze omosse.")
    print("-" * 60)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        sys.exit(0)
    
    content_hash = sys.argv[1]
    clean_hash, txt_path, index_path = get_paths(content_hash)
    
    if len(sys.argv) == 2 or sys.argv[2] == "--info":
        show_info(clean_hash, txt_path, index_path)
    elif sys.argv[2] == "--chunk" and len(sys.argv) > 3:
        read_chunk(clean_hash, txt_path, index_path, int(sys.argv[3]))
    elif sys.argv[2] == "--lines" and len(sys.argv) > 4:
        read_lines(txt_path, int(sys.argv[3]), int(sys.argv[4]))
    elif sys.argv[2] == "--search" and len(sys.argv) > 3:
        search_pattern(txt_path, sys.argv[3])
    else:
        print(f"Opzione non riconosciuta: {' '.join(sys.argv[2:])}")
        print(__doc__)

if __name__ == "__main__":
    main()
