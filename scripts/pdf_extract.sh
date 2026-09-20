#!/usr/bin/env bash
# pdf_extract.sh — estrazione testo da PDF (pdftotext) con fallback OCR (pdftoppm + tesseract).
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Uso: pdf_extract.sh <file.pdf> [--out FILE] [--pages A-B] [--ocr]

Estrae il testo di un PDF con pdftotext -layout (output su stdout di default).
Se il testo estratto e' insufficiente (< ~100 caratteri per pagina), esegue
automaticamente il fallback OCR con pdftoppm + tesseract (lingue deu+eng).

Opzioni:
  --out FILE     scrive l'output su FILE (default: stdout)
  --pages A-B    limita l'estrazione alle pagine da A a B
  --ocr          forza l'OCR anche se il testo e' sufficiente
  -h, --help     mostra questo messaggio

Dipendenze: poppler (pdftotext, pdftoppm, pdfinfo), tesseract (+ lingue deu/eng).
  sudo pacman -S poppler tesseract tesseract-data-deu tesseract-data-eng
  sudo apt install poppler-utils tesseract-ocr tesseract-ocr-deu
EOF
}

PDF=""
OUT=""
PAGES=""
A=""
B=""
FORCE_OCR=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --out)
      [ "$#" -ge 2 ] || { echo "[pdf_extract] errore: --out richiede un FILE" >&2; exit 1; }
      OUT="$2"; shift 2 ;;
    --pages)
      [ "$#" -ge 2 ] || { echo "[pdf_extract] errore: --pages richiede A-B" >&2; exit 1; }
      PAGES="$2"; shift 2 ;;
    --ocr)
      FORCE_OCR=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    -*)
      echo "[pdf_extract] errore: opzione sconosciuta: $1" >&2; usage; exit 1 ;;
    *)
      if [ -n "$PDF" ]; then
        echo "[pdf_extract] errore: argomento inatteso: $1" >&2; exit 1
      fi
      PDF="$1"; shift ;;
  esac
done

if [ -z "$PDF" ]; then
  usage
  exit 1
fi

if [ ! -f "$PDF" ]; then
  echo "[pdf_extract] errore: file non trovato: $PDF" >&2
  exit 1
fi

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "[pdf_extract] errore: 'pdftotext' non trovato." >&2
  echo "  Installa poppler:  sudo pacman -S poppler   |   sudo apt install poppler-utils" >&2
  exit 1
fi

TMPD="$(mktemp -d "${TMPDIR:-/tmp}/pdf_extract.XXXXXX")"
trap 'rm -rf "$TMPD"' EXIT

PT_ARGS=(-layout)
if [ -n "$PAGES" ]; then
  A="${PAGES%%-*}"
  B="${PAGES##*-}"
  case "$A" in ''|*[!0-9]*) echo "[pdf_extract] errore: --pages non valido: $PAGES" >&2; exit 1 ;; esac
  case "$B" in ''|*[!0-9]*) echo "[pdf_extract] errore: --pages non valido: $PAGES" >&2; exit 1 ;; esac
  PT_ARGS+=(-f "$A" -l "$B")
fi

TEXT="$TMPD/text.txt"
pdftotext "${PT_ARGS[@]}" "$PDF" "$TEXT"

CHARS="$(tr -d '[:space:]' < "$TEXT" | wc -m)"

NP=""
if [ -n "$PAGES" ]; then
  NP=$((B - A + 1))
elif command -v pdfinfo >/dev/null 2>&1; then
  NP="$(pdfinfo "$PDF" 2>/dev/null | awk '/^Pages:/{print $2; exit}' || true)"
fi
THRESH=200
case "$NP" in
  ''|*[!0-9]*) : ;;
  *) if [ "$NP" -gt 0 ]; then THRESH=$((NP * 100)); fi ;;
esac

emit() {
  if [ -n "$OUT" ]; then
    cat > "$OUT"
    echo "[pdf_extract] output scritto in $OUT (${CHARS} caratteri non-bianchi estratti)" >&2
  else
    cat
  fi
}

if [ "$FORCE_OCR" -eq 1 ] || [ "$CHARS" -lt "$THRESH" ]; then
  echo "[pdf_extract] testo insufficiente, fallback OCR" >&2
  if ! command -v pdftoppm >/dev/null 2>&1 || ! command -v tesseract >/dev/null 2>&1; then
    echo "[pdf_extract] errore: 'pdftoppm' o 'tesseract' non trovati." >&2
    echo "  Installa: sudo pacman -S poppler tesseract tesseract-data-deu tesseract-data-eng" >&2
    exit 1
  fi
  OCR_DIR="$TMPD/ocr"
  mkdir -p "$OCR_DIR"
  PP_ARGS=(-r 300 -png)
  if [ -n "$PAGES" ]; then PP_ARGS+=(-f "$A" -l "$B"); fi
  pdftoppm "${PP_ARGS[@]}" "$PDF" "$OCR_DIR/pg"
  {
    for f in "$OCR_DIR"/pg-*.png; do
      if [ ! -e "$f" ]; then
        echo "[pdf_extract] errore: nessuna pagina rasterizzata per l'OCR" >&2
        exit 1
      fi
      num="${f##*/pg-}"
      num="${num%.png}"
      printf -- '--- page %s ---\n' "$((10#$num))"
      tesseract "$f" stdout -l deu+eng 2>/dev/null || true
    done
  } | emit
elif [ -n "$PAGES" ]; then
  {
    for (( p = A; p <= B; p++ )); do
      printf -- '--- page %s ---\n' "$p"
      pdftotext -f "$p" -l "$p" -layout "$PDF" -
    done
  } | emit
else
  emit < "$TEXT"
fi
