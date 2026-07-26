# AICP Research – So startest du die App

## 0. Voraussetzung: aktuelles Python (einmalig)

Die App braucht Python 3.11 oder neuer. **Wichtig:** Das auf dem Mac
vorinstallierte Apple-Python (3.9) ist zu alt — damit schlägt die
Installation von `pyobjc` fehl.

Installer von https://www.python.org/downloads/ laden und per
Doppelklick installieren (kostenlos, kein Account nötig).

## 1. Starten (der einfache Weg)

**Doppelklick auf `EchoArchive.command`** im Projektordner. Beim ersten Mal
richtet das Skript alles selbst ein (eine eigene Python-Umgebung im
Unterordner `.venv` und die benötigten Pakete) und startet danach die App.

Weitere Doppelklick-Helfer liegen in `tools/`:

- `Neustart.command` – App neu starten, Bibliothek bleibt erhalten
- `Neustart-Sauber.command` – Neustart mit frischer, leerer Datenbank
- `Diagnose.command` – prüft die Installation und zeigt, was fehlt

### Falls du lieber das Terminal benutzt

```bash
cd ~/aicp-research
python3 -m venv .venv                     # einmalig
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app/main.py              # bei jedem Start
```

Die eigene Umgebung (`.venv`) ist nötig, weil aktuelle macOS- und
Homebrew-Installationen keine Pakete mehr direkt in das System-Python
schreiben lassen. Ein `pip install` ohne `.venv` bricht dort mit einer
Meldung über eine „extern verwaltete Umgebung" ab.

Beim allerersten Start lädt die App einmalig das Embedding-Modell für die
semantische Suche (~220 MB). Danach läuft alles komplett offline.
Die Volltextsuche funktioniert sofort, auch während das Modell noch lädt.

## 2. Optionale Helfer (kostenlos)

- **Microsoft Word** (falls vorhanden) liefert die **exakten** Seitenzahlen
  für `.docx`-Dateien. Die App benutzt es automatisch, wenn es installiert
  ist – nichts einzurichten.
- **LibreOffice** (https://de.libreoffice.org) ist der kostenlose Ersatz,
  wenn kein Word vorhanden ist. Seine Seitenumbrüche weichen leicht ab
  (gemessen: +13 Seiten bei einem 530-Seiten-Buch), deshalb kennzeichnet die
  App solche Treffer als **„ungefähr"**. Für Zitate mit Seitenangabe sind
  nur Treffer mit „sicher" (PDF) oder „exakt" (Word) verlässlich.
- **Tesseract** (für eingescannte PDFs, arabische Texterkennung):
  macOS:  `brew install tesseract tesseract-lang`
  Windows: Installer von https://github.com/UB-Mannheim/tesseract/wiki
  (bei der Installation "Arabic" anhaken)

## 3. Fertige App bauen (Doppelklick-Programm, für die Weitergabe)

Auf dem Mac genügt ein Doppelklick auf **`Build-DMG.command`**.
Von Hand:

```bash
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m PyInstaller build/echoarchive.spec
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
