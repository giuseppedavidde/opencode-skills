#!/usr/bin/env python3
"""QuantMind paper extraction — preprocessing stage only (no API key needed).

Usage:
  python3 extract_paper.py arxiv 2401.12345
  python3 extract_paper.py url https://arxiv.org/pdf/2401.12345.pdf
  python3 extract_paper.py file /path/to/paper.pdf
  python3 extract_paper.py text "raw markdown content"

Output: writes markdown to /tmp/quantmind-extract/
  - /tmp/quantmind-extract/<id>.md          ← markdown grezzo
  - /tmp/quantmind-extract/<id>.meta.json   ← metadati (titolo, autori, fonte)
  - /tmp/quantmind-extract/<id>.prompt.txt  ← prompt per il subagent LLM
"""

import asyncio
import json
import sys
import os
from pathlib import Path

OUTPUT_DIR = Path("/tmp/quantmind-extract")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def extract_arxiv(arxiv_id: str) -> None:
    from quantmind.preprocess.fetch import fetch_arxiv
    from quantmind.preprocess.format import pdf_to_markdown

    print(f"📥 Fetching arXiv:{arxiv_id}...")
    raw = await fetch_arxiv(arxiv_id)
    print(f"   Title: {raw.title}")
    print(f"   Authors: {', '.join(list(raw.authors)[:5])}")

    print("📄 Converting PDF to markdown...")
    md = await pdf_to_markdown(raw.bytes)
    print(f"   → {len(md)} chars")

    # Salva markdown
    safe_id = arxiv_id.replace("/", "_").replace(".", "_")
    md_path = OUTPUT_DIR / f"{safe_id}.md"
    md_path.write_text(md)

    # Salva metadati
    meta = {
        "source": "arxiv",
        "arxiv_id": arxiv_id,
        "title": raw.title,
        "authors": list(raw.authors),
        "chars": len(md),
    }
    meta_path = OUTPUT_DIR / f"{safe_id}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # Crea prompt per subagent
    prompt = f"""Hai ricevuto il contenuto markdown di un paper accademico da arXiv.
Estrai le seguenti informazioni in formato JSON strutturato:

Paper: {raw.title}
Autori: {', '.join(list(raw.authors)[:5])}
Fonte: arXiv {arxiv_id}

Analizza il markdown e produci un JSON con:
1. Un riassunto (2-3 paragrafi) del paper
2. La metodologia principale
3. I key findings (lista di 3-5 punti)
4. Le limitazioni (se presenti)
5. Le asset classes menzionate
6. La struttura delle sezioni principali con per ciascuna: titolo e sommario

Il markdown è salvato in: {md_path}
Leggilo e produci il JSON.

Rispondi SOLO con il JSON, niente altro.
"""
    prompt_path = OUTPUT_DIR / f"{safe_id}.prompt.txt"
    prompt_path.write_text(prompt)

    print(f"\n✅ Salvato in: {OUTPUT_DIR}/")
    print(f"   📄 {safe_id}.md")
    print(f"   📋 {safe_id}.meta.json")
    print(f"   📝 {safe_id}.prompt.txt")

    return safe_id


async def extract_url(url: str) -> None:
    from quantmind.preprocess.fetch import fetch_url
    from quantmind.preprocess.format import html_to_markdown, pdf_to_markdown

    print(f"📥 Fetching URL: {url}...")
    raw = await fetch_url(url)
    ct = (raw.content_type or "").lower()

    print(f"   Content-Type: {ct}")
    print(f"   Bytes: {len(raw.bytes)}")

    if ct.startswith("application/pdf"):
        md = await pdf_to_markdown(raw.bytes)
    elif ct.startswith("text/html"):
        md = await html_to_markdown(raw.bytes.decode("utf-8", errors="replace"))
    else:
        md = raw.bytes.decode("utf-8", errors="replace")

    print(f"   → {len(md)} chars")

    safe_id = url.split("/")[-1].replace(".", "_") or "document"
    md_path = OUTPUT_DIR / f"{safe_id}.md"
    md_path.write_text(md)

    meta = {"source": "url", "url": url, "content_type": ct, "chars": len(md)}
    meta_path = OUTPUT_DIR / f"{safe_id}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    prompt = f"""Hai ricevuto il contenuto di un documento finanziario/accademico.
Estrai le seguenti informazioni in formato JSON strutturato.

Fonte: {url}
Content-Type: {ct}

Leggi il markdown in {md_path} e produci un JSON con:
1. Un riassunto (2-3 paragrafi)
2. Metodologia/key findings
3. Sezioni principali con titolo e sommario

Rispondi SOLO con il JSON.
"""
    prompt_path = OUTPUT_DIR / f"{safe_id}.prompt.txt"
    prompt_path.write_text(prompt)

    print(f"\n✅ Salvato in: {OUTPUT_DIR}/")
    return safe_id


async def extract_local(filepath: str) -> None:
    from quantmind.preprocess.fetch import read_local_file
    from quantmind.preprocess.format import pdf_to_markdown, html_to_markdown

    path = Path(filepath)
    print(f"📖 Reading local file: {path}...")

    raw = await read_local_file(path)
    ct = (raw.content_type or "").lower()

    if ct.startswith("application/pdf"):
        md = await pdf_to_markdown(raw.bytes)
    elif ct.startswith("text/html"):
        md = await html_to_markdown(raw.bytes.decode("utf-8", errors="replace"))
    else:
        md = raw.bytes.decode("utf-8", errors="replace")

    safe_id = path.stem
    md_path = OUTPUT_DIR / f"{safe_id}.md"
    md_path.write_text(md)

    meta = {"source": "local", "path": str(path), "content_type": ct, "chars": len(md)}
    meta_path = OUTPUT_DIR / f"{safe_id}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    prompt = f"""Hai ricevuto il contenuto di un documento finanziario/accademico.
Estrai le seguenti informazioni in formato JSON strutturato.

File: {path}
Content-Type: {ct}

Leggi il markdown in {md_path} e produci un JSON completo.

Rispondi SOLO con il JSON.
"""
    prompt_path = OUTPUT_DIR / f"{safe_id}.prompt.txt"
    prompt_path.write_text(prompt)

    print(f"\n✅ Salvato in: {OUTPUT_DIR}/")
    return safe_id


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    value = sys.argv[2]

    if mode == "arxiv":
        await extract_arxiv(value)
    elif mode == "url":
        await extract_url(value)
    elif mode == "file":
        await extract_local(value)
    elif mode == "text":
        # Raw text input, write directly
        safe_id = "inline"
        md_path = OUTPUT_DIR / f"{safe_id}.md"
        md_path.write_text(value)
        meta = {"source": "inline", "chars": len(value)}
        meta_path = OUTPUT_DIR / f"{safe_id}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"✅ Inline text salvato in: {md_path}")
    else:
        print(f"❌ Modalità sconosciuta: {mode}")
        print(__doc__)
        sys.exit(1)

    print("\n💡 Passa il prompt.txt al subagent opencode per l'estrazione LLM:")
    print(f"   Cerca il file .prompt.txt in {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
