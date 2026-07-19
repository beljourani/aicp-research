#!/bin/zsh
# AICP Research starten (Doppelklick)
cd "$(dirname "$0")"
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
# Fehlende Pakete automatisch nachinstallieren (schnell, wenn alles da ist)
"$PY" -m pip install -q -r requirements.txt 2>/dev/null
exec "$PY" app/main.py
