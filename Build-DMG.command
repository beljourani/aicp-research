#!/bin/zsh
# Baut die fertige macOS-App und verpackt sie als AICP Research.dmg
# (Doppelklick genügt. Dauert beim ersten Mal einige Minuten.)
set -e
cd "$(dirname "$0")"

# Bevorzugt Python 3.12 - genau die Version, mit der die veröffentlichten
# Installer gebaut werden (.github/workflows/build-macos.yml). Mit einer
# anderen Python-Version zieht pip andere Pakete; die lokal gebaute App wäre
# dann nicht dieselbe wie die ausgelieferte. Nur wenn 3.12 fehlt, wird der
# Reihe nach etwas Neueres genommen.
PY=$(command -v python3.12 || command -v python3.13 || command -v python3.14 || command -v python3)
echo "==> Python: $PY"
"$PY" --version

echo "==> Abhängigkeiten prüfen/installieren …"
"$PY" -m pip install -q -r requirements.txt pyinstaller

echo "==> Embedding-Modell für die Bündelung bereitstellen …"
"$PY" - <<'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, "engine")
from echo_engine.semantic import MODEL_NAME
from fastembed import TextEmbedding
cache = Path("build/models")
cache.mkdir(parents=True, exist_ok=True)
TextEmbedding(MODEL_NAME, cache_dir=str(cache))
print("Modell liegt in build/models")
PYEOF

echo "==> App bauen (PyInstaller) …"
rm -rf "dist/AICP Research" "dist/AICP Research.app"
# AICP_MAC_ARCH=universal2 würde eine App für Apple Silicon UND Intel bauen -
# das gelingt aber nur, wenn alle eingebundenen Bibliotheken universal2 sind
# (onnxruntime liefert seit 1.24 nur noch arm64). Siehe build/echoarchive.spec.
"$PY" -m PyInstaller --noconfirm --distpath dist --workpath build/pyi build/echoarchive.spec

echo "==> Bündel prüfen …"
APP="dist/AICP Research.app"
fehlt=""
[ -x "$APP/Contents/MacOS/AICPResearch" ] || fehlt="$fehlt Programmdatei"
for ordner in models ui; do
  [ -n "$(find "$APP/Contents" -maxdepth 4 -type d -name "$ordner" -print -quit 2>/dev/null)" ] \
    || fehlt="$fehlt $ordner"
done
# Reine Python-Pakete liegen im Archiv, nicht als Ordner - deshalb in den
# Inhaltsverzeichnissen von PyInstaller nachsehen.
TOC="$(cat build/pyi/*/*.toc 2>/dev/null || true)"
for modul in huggingface_hub pypdf fastembed onnxruntime docx fitz Vision; do
  printf '%s' "$TOC" | grep -q "$modul" || fehlt="$fehlt $modul"
done
if [ -n "$fehlt" ]; then
  echo "FEHLER: Im Bündel fehlt:$fehlt"
  echo "Kein DMG erzeugt - so ausgeliefert wäre die App an dieser Stelle stumm kaputt."
  exit 1
fi
echo "    Architektur: $(lipo -archs "$APP/Contents/MacOS/AICPResearch" 2>/dev/null || echo unbekannt)"

echo "==> DMG erzeugen …"
rm -f "dist/AICP-Research.dmg"
hdiutil create -volname "AICP Research" -srcfolder "dist/AICP Research.app" \
    -ov -format UDZO "dist/AICP-Research.dmg"

echo ""
echo "=========================================="
echo "FERTIG: dist/AICP-Research.dmg"
echo "=========================================="
open dist
