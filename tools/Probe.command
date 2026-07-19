#!/bin/zsh
cd "$(dirname "$0")/.."
PY=$(command -v python3.14 || command -v python3.13 || command -v python3.12 || command -v python3)
"$PY" -m pip install -q certifi 2>&1 | tail -1
# macOS-Python kennt die System-Zertifikate nicht – certifi unterschieben
export SSL_CERT_FILE=$("$PY" -m certifi 2>/dev/null)
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
echo "SSL_CERT_FILE=$SSL_CERT_FILE"
"$PY" tools/probe.py
echo ""
echo "Fertig – Fenster kann geschlossen werden."
