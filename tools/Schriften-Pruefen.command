#!/bin/zsh
# Prüft, ob die von den Word-Dateien verlangten Schriften vorhanden sind,
# und misst, wie sich das auf die Seitenzahlen auswirkt.
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
"$PY" tools/schriften_check.py
echo ""
echo "Fertig – Fenster kann geschlossen werden."
