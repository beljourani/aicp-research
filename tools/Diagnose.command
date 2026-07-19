#!/bin/zsh
# Führt Word→PDF-Konvertierung für ALLE Testbücher durch und schreibt das
# Ergebnis in tools/diagnose_ergebnis.txt – dort liest Claude es direkt,
# ohne den Bildschirm fernsteuern zu müssen.
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
"$PY" -m pip install -q certifi 2>&1 | tail -1

# Falls eine LibreOffice-Instanz noch (unsichtbar) läuft: beenden.
pkill -f soffice 2>/dev/null
sleep 1
# Reste eines abgestürzten Profils entfernen (harmlos, wird neu erstellt).
rm -rf "$HOME/Library/Application Support/AICP Research/components/lo-profile" 2>/dev/null

echo "Diagnose läuft – jede Zeile erscheint sofort. Bitte warten …"
echo ""
# tee: live im Terminal UND in die Datei (die Claude liest)
"$PY" -u tools/diagnose.py 2>&1 | tee tools/diagnose_ergebnis.txt
echo ""
echo "FERTIG – Ergebnis auch in tools/diagnose_ergebnis.txt"
