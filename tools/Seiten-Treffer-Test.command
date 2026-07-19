#!/bin/zsh
# Trifft die Wandlung Words 64 Seiten, wenn der Konverter die
# Original-Schrift (aus dem Office-Cache) bekommt?
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
F="$HOME/Downloads/AICP Research-Buecher/متن-الصراط-المستقيم.docx"

echo "Word zeigt für diese Datei: 64 Seiten"
echo ""

"$PY" - "$F" <<'PYEOF'
import sys, tempfile, subprocess, glob
from pathlib import Path
sys.path.insert(0, "engine")
import fitz
from echo_engine.components import (find_soffice, install_fonts_into_converter,
                                    collect_document_fonts, ensure_fonts)

F = sys.argv[1]

def log(s): print("  ", s, flush=True)

print("==> Konverter sicherstellen (lädt beim ersten Mal ~300 MB) …")
soffice = find_soffice(auto_install=True, progress=log)
print("   Konverter:", soffice)
if not soffice:
    print("   FEHLGESCHLAGEN"); raise SystemExit

def convert_and_count(src):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--norestore",
                        "--convert-to", "pdf", "--outdir", tmp, str(src)],
                       capture_output=True, timeout=1800)
        pdfs = glob.glob(tmp + "/*.pdf")
        if not pdfs: return None
        with fitz.open(pdfs[0]) as d:
            return len(d)

print("\n==> A) OHNE Original-Schrift:")
a = convert_and_count(F)
print(f"   ==> {a} Seiten   (Ziel: 64)")

print("\n==> B) Schriften sammeln (mitgeliefert + Office-Cache) …")
n = len(list(ensure_fonts(log).glob('*.ttf')))
docfonts = collect_document_fonts(log)
m = len(list(docfonts.glob('*')))
print(f"   mitgeliefert: {n}, vom Rechner gesammelt: {m}")
install_fonts_into_converter(soffice, log)

print("\n==> C) MIT Original-Schrift:")
c = convert_and_count(F)
print(f"   ==> {c} Seiten   (Ziel: 64)")

print("\n" + "="*50)
print(f"Word:                 64 Seiten")
print(f"ohne Schrift:         {a} Seiten")
print(f"mit Schrift:          {c} Seiten")
print("="*50)
PYEOF

echo ""
echo "Fertig – Fenster kann geschlossen werden."
