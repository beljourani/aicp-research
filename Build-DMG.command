#!/bin/zsh
# Baut die fertige macOS-App und verpackt sie als AICP Research.dmg
# (Doppelklick genügt. Dauert beim ersten Mal einige Minuten.)
set -e
cd "$(dirname "$0")"

PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
echo "==> Python: $PY"

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
"$PY" -m PyInstaller --noconfirm --distpath dist --workpath build/pyi build/echoarchive.spec

echo "==> DMG erzeugen …"
rm -f "dist/AICP-Research.dmg"
hdiutil create -volname "AICP Research" -srcfolder "dist/AICP Research.app" \
    -ov -format UDZO "dist/AICP-Research.dmg"

echo ""
echo "=========================================="
echo "FERTIG: dist/AICP-Research.dmg"
echo "=========================================="
open dist
