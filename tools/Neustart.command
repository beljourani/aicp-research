#!/bin/zsh
# Startet AICP Research neu, OHNE die Bibliothek zu löschen.
# (Zum Übernehmen von Code-Änderungen – deine Bücher bleiben erhalten.)
cd "$(dirname "$0")/.."

echo "==> Laufende AICP Research-Instanzen beenden …"
pkill -f "app/main.py" 2>/dev/null
pkill -f soffice 2>/dev/null
sleep 2

echo "==> AICP Research startet neu (Bibliothek bleibt erhalten) …"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
fi
exec "$PY" app/main.py
