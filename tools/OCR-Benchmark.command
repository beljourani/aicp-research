#!/bin/zsh
# Vergleicht Windows-taugliche OCR-Engines mit Apple Vision als Referenz.
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
echo "==> Python: $PY"

"$PY" -m pip install -q certifi pillow 2>&1 | tail -1
# macOS-Python kennt die System-Zertifikate nicht – certifi unterschieben,
# sonst schlagen alle Modell-Downloads fehl.
export SSL_CERT_FILE=$("$PY" -m certifi 2>/dev/null)
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
export CURL_CA_BUNDLE="$SSL_CERT_FILE"
echo "==> Zertifikate: $SSL_CERT_FILE"

echo "==> Kandidaten installieren (einmalig, dauert) …"
"$PY" -m pip install -q surya-ocr 2>&1 | tail -1 || echo "   (Surya übersprungen)"
"$PY" -m pip install -q easyocr 2>&1 | tail -1 || echo "   (EasyOCR übersprungen)"

echo "==> tessdata_best (arabisch) …"
mkdir -p tools/tessdata_best
[ -f tools/tessdata_best/ara.traineddata ] || curl -sL -o tools/tessdata_best/ara.traineddata \
  https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata

echo ""
echo "==> Benchmark läuft – Surya lädt beim ersten Mal ~1 GB Modelle."
echo "    Das kann 10+ Minuten dauern. Bitte Fenster offen lassen."
echo ""
"$PY" tools/ocr_benchmark.py 2>&1 | grep -vE "^(Loading|Detecting|Recognizing|  0%|100%)"

open tools/ocr_benchmark.html
