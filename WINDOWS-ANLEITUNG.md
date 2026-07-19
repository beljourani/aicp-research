# AICP Research auf Windows bauen

Der Build muss auf einem Windows-PC laufen (eine echte `.exe` lässt sich nicht auf dem Mac erzeugen).

## Einmalige Voraussetzung

**Python 3.12** installieren: https://www.python.org/downloads/
→ Im Installer unbedingt **„Add python.exe to PATH"** anhaken.

Inno Setup (für den Installer) holt sich die Build-Datei bei Bedarf selbst über winget.
Falls das nicht klappt, einmal manuell:
`winget install -e --id JRSoftware.InnoSetup`

## Bauen

1. Diesen Ordner (`echo-archive`) komplett auf den Windows-PC kopieren.
2. Doppelklick auf **`Build-Windows.bat`**.
3. Warten – das Skript erledigt alles automatisch (Abhängigkeiten, Modell,
   Tesseract-OCR, App bauen, Installer erzeugen). Erscheint eine
   Windows-Sicherheitsabfrage für Inno Setup, mit **„Ja"** bestätigen.

## Ergebnis

**`dist\AICP-Research-Setup.exe`** – der Installer.
Doppelklick installiert AICP Research nach *Programme* und legt Start- und
Desktop-Verknüpfung an. Deinstallieren wie üblich über „Apps & Features".

(Ohne Inno Setup als Notlösung: `dist\AICP-Research-Windows.zip` – entpacken und
`AICPResearch.exe` starten.)

## Hinweis

Die App braucht die **WebView2-Runtime** (auf Windows 11 und aktuellem Windows 10
bereits vorhanden). Falls das Fenster leer bleibt, hier nachinstallieren:
https://developer.microsoft.com/microsoft-edge/webview2/ („Evergreen Standalone").

Deine Bibliothek liegt in `%APPDATA%\AICP Research` und bleibt bei
Updates/Deinstallation erhalten.
