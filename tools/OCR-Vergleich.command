#!/bin/zsh
# Führt den OCR-Vergleich durch und öffnet das Ergebnis im Browser.
set -e
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)

echo "==> Kandidaten-Erkenner installieren (einmalig) …"
"$PY" -m pip install -q rapidocr-onnxruntime pillow 2>&1 | tail -1 || true

echo "==> Tesseract prüfen …"
if ! command -v tesseract >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "    Tesseract wird per Homebrew installiert (dauert etwas) …"
    brew install tesseract tesseract-lang 2>&1 | tail -2 || true
  else
    echo "    Kein Homebrew – Tesseract-Spalte bleibt leer."
  fi
fi

echo "==> Vergleich läuft …"
"$PY" tools/ocr_vergleich.py

open tools/ocr_vergleich.html
