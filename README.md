# AICP Research – Arabisches Dokumentarchiv mit Volltextsuche

Lokale Desktop-App (macOS/Windows) zum Durchsuchen von Büchern und
Dokumenten (PDF, Word, TXT) – arabisch-optimiert, kostenlos, offline.

## Stand

**Fertig: Such-Engine (`engine/`)** – das Herzstück, getestet:

- Arabische Normalisierung (Tashkil, Alif-Varianten, Ta Marbuta, Ziffern)
- Wurzel-Stemming (ISRI): Suche nach كتب findet يكتب، كتبت، يكتبون، كَتَبَ
- SQLite + FTS5-Volltextindex, zweistufig (exakt bevorzugt, Wurzel ergänzt)
- Seitengenaue Treffer: jede Passage kennt ihre exakte Seite
- Extraktion: PDF seitenweise (PyMuPDF), Scan-Erkennung + OCR-Hook
  (Tesseract ara), DOCX→PDF via LibreOffice für echte Seitenzahlen,
  TXT mit künstlichen Seiten
- Autorenfilter und Blättern ohne Suchbegriff

Tests: `python3 engine/tests/test_engine.py`

## Geplant (nächste Schritte)

1. Semantische Suche: lokales mehrsprachiges Embedding-Modell + Vektorindex
2. Desktop-UI (React) + App-Verpackung für macOS/Windows
3. Themen-/Tags-Verwaltung, Bibliotheks-Export/-Import
4. Installer inkl. Tesseract/LibreOffice-Erkennung

## Architektur-Entscheidungen

- Keine Server, keine Konten, keine laufenden Kosten
- Dateien bleiben, wo sie sind (auch Google-Drive-Ordner); die App
  speichert nur den Suchindex
- Word-Seitenzahlen: DOCX wird intern nach PDF konvertiert, weil DOCX
  selbst keine Seiten kennt – so stimmen die Seitenangaben exakt
