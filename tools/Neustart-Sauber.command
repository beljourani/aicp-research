#!/bin/zsh
# Beendet laufende AICP Research-Instanzen, löscht die Datenbank
# (Bücher selbst bleiben natürlich erhalten) und startet neu.
cd "$(dirname "$0")/.."

echo "==> Laufende AICP Research-Instanzen beenden …"
pkill -f "AICP Research.app/Contents/MacOS/AICP Research" 2>/dev/null
pkill -f "app/main.py" 2>/dev/null
sleep 2

DB="$HOME/Library/Application Support/AICP Research/archive.db"
echo "==> Alte Datenbank entfernen …"
rm -f "$DB" "$DB-wal" "$DB-shm"
echo "    erledigt"

echo "==> AICP Research startet neu …"
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
exec "$PY" app/main.py
