#!/bin/zsh
# AICP Research starten (Doppelklick)
cd "$(dirname "$0")"
# Projekteigenes Python-Environment (.venv) bevorzugen. Homebrew-Python ist
# "extern verwaltet" (PEP 668) und lässt kein direktes pip install zu – deshalb
# beim ersten Start ein .venv anlegen und die Pakete dorthin installieren.
if [ ! -x ".venv/bin/python" ]; then
  echo "==> Erstmalige Einrichtung: Python-Umgebung wird angelegt …"
  BOOT=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
  "$BOOT" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi
PY=".venv/bin/python"
# Fehlende Pakete automatisch nachinstallieren (schnell, wenn alles da ist)
"$PY" -m pip install -q -r requirements.txt
exec "$PY" app/main.py
