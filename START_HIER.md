# AICP Research – So startest du die App

## 0. Voraussetzung: aktuelles Python (einmalig)

Die App braucht Python 3.11 oder neuer. **Wichtig:** Das auf dem Mac
vorinstallierte Apple-Python (3.9) ist zu alt — damit schlägt die
Installation von `pyobjc` fehl.

Installer von https://www.python.org/downloads/ laden und per
Doppelklick installieren (kostenlos, kein Account nötig).

## 1. Sofort ausprobieren (auf deinem Mac)

Terminal öffnen und einmalig:

```bash
cd ~/Projekte/echo-archive
python3.13 -m pip install -r requirements.txt
```

Dann bei jedem Start:

```bash
cd ~/Projekte/echo-archive
python3.13 app/main.py
```

(Versionsnummer ggf. anpassen, z.B. `python3.12`.)

Beim allerersten Start lädt die App einmalig das Embedding-Modell für die
semantische Suche (~220 MB). Danach läuft alles komplett offline.
Die Volltextsuche funktioniert sofort, auch während das Modell noch lädt.

## 2. Optionale Helfer (kostenlos)

- **LibreOffice** (für Word-Dateien mit exakten Seitenzahlen):
  https://de.libreoffice.org – einfach installieren, die App findet es selbst.
  Ohne LibreOffice werden Word-Texte trotzdem indexiert, Seitenzahlen sind
  dann Schätzwerte (wird in der App angezeigt).
- **Tesseract** (für eingescannte PDFs, arabische Texterkennung):
  macOS:  `brew install tesseract tesseract-lang`
  Windows: Installer von https://github.com/UB-Mannheim/tesseract/wiki
  (bei der Installation "Arabic" anhaken)

## 3. Fertige App bauen (Doppelklick-Programm, für die Weitergabe)

```bash
pip3 install pyinstaller
pyinstaller build/echoarchive.spec
```

Ergebnis: `dist/AICP Research.app` (macOS) bzw. `dist/AICP Research/` mit
`AICP Research.exe` (Windows). Wichtig: Der Windows-Build muss auf einem
Windows-Rechner laufen, der Mac-Build auf einem Mac.

## Wo liegen meine Daten?

- Deine Dokumente bleiben, wo sie sind (auch Google-Drive-Ordner sind ok).
- Der Suchindex liegt unter:
  - macOS: `~/Library/Application Support/AICP Research/archive.db`
  - Windows: `%APPDATA%\AICP Research\archive.db`
- Nichts verlässt jemals deinen Rechner. Keine Konten, keine Kosten.
