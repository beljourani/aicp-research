#!/bin/zsh
# Lädt die frei angebotenen Bücher von shaykhgillessadek.com
# nach ~/Downloads/AICP Research-Buecher (Doppelklick genügt).
set -u
D=~/Downloads/AICP Research-Buecher
mkdir -p "$D"
PAGE="https://shaykhgillessadek.com/%D8%A7%D9%84%D9%85%D9%83%D8%AA%D8%A8%D8%A9-%D8%A7%D9%84%D8%B3%D9%86%D9%8A%D8%A9/%D9%83%D8%AA%D8%A8-%D9%84%D9%84%D8%AA%D8%AD%D9%85%D9%8A%D9%84/"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

echo "==> Seite auslesen …"
curl -fsSL -A "$UA" "$PAGE" -o /tmp/echo_books.html || { echo "Seite nicht erreichbar"; exit 1; }

grep -oE 'https://shaykhgillessadek\.com/download/[^"'"'"']+' /tmp/echo_books.html \
  | sed 's/&amp;/\&/g' | sort -u > /tmp/echo_urls.txt
N=$(wc -l < /tmp/echo_urls.txt | tr -d ' ')
echo "==> $N Dateien gefunden"
echo ""

i=0
while IFS= read -r u; do
  i=$((i+1))
  printf "[%2d/%s] " "$i" "$N"
  if curl -fsSL -OJ -A "$UA" --output-dir "$D" "$u"; then
    echo "ok"
  else
    echo "FEHLER"
  fi
done < /tmp/echo_urls.txt

echo ""
echo "=========================================="
echo "Fertig. Dateien in: $D"
ls -1sh "$D"
echo "=========================================="
open "$D"
