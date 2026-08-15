@echo off
REM ============================================================
REM   AICP Research - Windows-Installer bauen (Ein-Klick)
REM   Voraussetzung: Python 3.12 (mit "Add to PATH" installiert)
REM   Optional fuer echten Installer: Inno Setup 6
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo.
echo ==========================================================
echo    AICP Research - Windows-Build
echo ==========================================================
echo.

REM --- 1. Python suchen ---------------------------------------
REM Bevorzugt Python 3.12 - genau die Version, mit der die veroeffentlichten
REM Installer gebaut werden (.github/workflows/build-windows.yml). Mit einer
REM anderen Python-Version zieht pip andere Rad-Dateien; der lokal gebaute
REM Installer waere dann nicht derselbe wie der ausgelieferte.
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD ( where py >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( where python >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD (
  echo [FEHLER] Python wurde nicht gefunden.
  echo   Bitte Python 3.12 installieren:  https://www.python.org/downloads/
  echo   WICHTIG: im Installer "Add python.exe to PATH" anhaken.
  echo.
  pause
  exit /b 1
)
echo [1/8] Python gefunden:
%PYCMD% --version

REM --- 2. Virtuelle Umgebung ---------------------------------
REM Hinweis: Die Umgebung wird nur einmal angelegt. Wenn hier spaeter eine
REM andere Python-Version stehen soll, den Ordner .venv loeschen.
if not exist ".venv\Scripts\python.exe" (
  echo [2/8] Erstelle virtuelle Umgebung ...
  %PYCMD% -m venv .venv || ( echo [FEHLER] venv konnte nicht erstellt werden. & pause & exit /b 1 )
) else (
  echo [2/8] Virtuelle Umgebung vorhanden.
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" --version

REM --- 3. Abhaengigkeiten ------------------------------------
echo [3/8] Installiere Abhaengigkeiten ^(kann einige Minuten dauern^) ...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt pyinstaller || ( echo [FEHLER] pip-Installation fehlgeschlagen. & pause & exit /b 1 )

REM --- 4. Embedding-Modell buendeln --------------------------
if not exist "build\models" (
  echo [4/8] Lade Embedding-Modell ^(einmalig, ca. 150 MB^) ...
  "%VPY%" -c "import sys; sys.path.insert(0,'engine'); from echo_engine.semantic import MODEL_NAME; from fastembed import TextEmbedding; TextEmbedding(MODEL_NAME, cache_dir='build/models')" || ( echo [FEHLER] Modell-Download fehlgeschlagen. & pause & exit /b 1 )
) else (
  echo [4/8] Embedding-Modell bereits vorhanden.
)

REM --- 5. Tesseract-OCR (optional, fuer Scans) ---------------
REM Sprachdateien aus tessdata_BEST - dieselbe Quelle wie in der CI
REM (.github/workflows/build-windows.yml). Frueher stand hier tessdata_fast:
REM die Modelle sind kleiner, erkennen arabische Scans aber deutlich
REM schlechter. Ein lokal gebauter Installer las damit anderen Text als der
REM ausgelieferte - genau das soll nicht sein.
REM osd.traineddata erkennt das Schriftsystem der ersten Seite. Fehlt es,
REM nimmt extract.py stumm seinen Rueckfall "ara" an und liest deutsche Scans
REM mit dem arabischen Modell.
if not exist "build\tesseract\tesseract.exe" (
  echo [5/8] Lade Tesseract-OCR ^(fuer eingescannte Dokumente^) ...
  set "TSETUP=%TEMP%\echo-tess-setup.exe"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest 'https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe' -OutFile '!TSETUP!' -UseBasicParsing } catch { exit 1 }"
  if exist "!TSETUP!" (
    "!TSETUP!" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="%CD%\build\tesseract"
  ) else (
    echo    [Hinweis] Tesseract konnte nicht geladen werden - OCR fuer Scans laesst sich spaeter nachruesten.
  )
) else (
  echo [5/8] Tesseract-OCR bereits vorhanden.
)
REM Die Merkdatei liegt bewusst ausserhalb von build\tesseract, denn dieser
REM Ordner wandert vollstaendig in die App - dort soll kein Beiwerk landen.
if exist "build\tesseract\tessdata" (
  if not exist "build\tessdata-best.ok" (
    for %%L in (ara deu eng osd) do (
      echo    Lade Sprachdatei %%L ^(tessdata_best^) ...
      powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest 'https://github.com/tesseract-ocr/tessdata_best/raw/main/%%L.traineddata' -OutFile 'build\tesseract\tessdata\%%L.traineddata' -UseBasicParsing } catch { Write-Host '   [Hinweis] %%L konnte nicht geladen werden.' }"
    )
    if exist "build\tesseract\tessdata\ara.traineddata" (
      powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Content -Path 'build\tessdata-best.ok' -Value 'Sprachdateien stammen aus tessdata_best' -Encoding ascii"
    )
  )
)

REM --- 6. WebView2-Bootstrapper besorgen ---------------------
REM Das App-Fenster ist ein Browser-Fenster (pywebview). Fehlt die
REM WebView2-Laufzeit, faellt pywebview auf die Internet-Explorer-Engine
REM zurueck und der Nutzer sieht ein WEISSES FENSTER ohne Meldung. Der
REM Bootstrapper wird in den Installer gepackt und dort nur gestartet, wenn
REM die Laufzeit wirklich fehlt (build\installer.iss).
if not exist "build\MicrosoftEdgeWebview2Setup.exe" (
  echo [6/8] Lade den WebView2-Bootstrapper ^(ca. 2 MB^) ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile 'build\MicrosoftEdgeWebview2Setup.exe' -UseBasicParsing; if ((Get-Item 'build\MicrosoftEdgeWebview2Setup.exe').Length -lt 500000) { Remove-Item 'build\MicrosoftEdgeWebview2Setup.exe' -Force; exit 1 } } catch { exit 1 }"
  if not exist "build\MicrosoftEdgeWebview2Setup.exe" (
    echo    [Hinweis] Bootstrapper konnte nicht geladen werden - der Installer
    echo    wird ohne ihn gebaut ^(auf Rechnern ohne WebView2 bleibt das
    echo    Fenster dann weiss^).
  )
) else (
  echo [6/8] WebView2-Bootstrapper bereits vorhanden.
)

REM --- 7. App bauen ------------------------------------------
echo [7/8] Baue die App mit PyInstaller ...
REM Laufende Instanz beenden und alten Build entfernen
REM (sonst "Zugriff verweigert", weil die EXE ihre Dateien sperrt).
taskkill /F /IM AICPResearch.exe >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "dist\AICPResearch" rmdir /S /Q "dist\AICPResearch" >nul 2>&1
if exist "dist\AICPResearch" (
  echo [FEHLER] "dist\AICPResearch" laesst sich nicht loeschen.
  echo   Bitte die AICP-Research-App und alle Explorer-Fenster in diesem Ordner
  echo   schliessen und die Datei erneut ausfuehren.
  pause & exit /b 1
)
"%VPY%" -m PyInstaller --noconfirm --distpath dist --workpath build\pyi build\echoarchive.spec || ( echo [FEHLER] PyInstaller-Build fehlgeschlagen. & pause & exit /b 1 )

REM --- 8. Installer bauen ------------------------------------
echo [8/8] Erzeuge den Installer ...

call :FIND_ISCC

REM Nicht gefunden? Inno Setup per winget installieren (Windows-Paketverwaltung).
if not defined ISCC (
  where winget >nul 2>&1
  if not errorlevel 1 (
    echo    Inno Setup nicht gefunden - installiere es einmalig ueber winget ...
    echo    ^(evtl. erscheint eine Windows-Sicherheitsabfrage - bitte mit "Ja" bestaetigen^)
    winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --disable-interactivity
    call :FIND_ISCC
  ) else (
    echo    [Hinweis] winget ist nicht verfuegbar.
  )
)

REM Immer noch nicht da? Direkter Download als letzter Versuch.
if not defined ISCC (
  echo    Versuche Inno Setup direkt herunterzuladen ...
  set "ISSETUP=%TEMP%\echo-innosetup.exe"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest 'https://jrsoftware.org/download.php/is.exe' -OutFile '%TEMP%\echo-innosetup.exe' -UseBasicParsing } catch { exit 1 }"
  if exist "%TEMP%\echo-innosetup.exe" (
    "%TEMP%\echo-innosetup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    call :FIND_ISCC
  )
)

REM Installer bauen (oder ZIP als Notloesung)
if defined ISCC (
  echo    Verwende Inno Setup: "!ISCC!"
  "!ISCC!" build\installer.iss || ( echo [FEHLER] Inno Setup fehlgeschlagen. & pause & exit /b 1 )
  echo.
  REM Der Dateiname enthaelt die Version (AICP-Research-Setup-1.0.0.exe),
  REM deshalb mit Platzhalter suchen - sonst meldet der Build faelschlich
  REM einen Fehler, obwohl der Installer erzeugt wurde.
  set "SETUPEXE="
  for %%F in ("dist\AICP-Research-Setup-*.exe") do set "SETUPEXE=%%~fF"
  if defined SETUPEXE (
    echo ==========================================================
    echo   FERTIG.  Der Installer liegt hier:
    echo       !SETUPEXE!
    echo   Doppelklick darauf installiert AICP Research in Ihr
    echo   Benutzerprofil ^(ohne Administrator-Abfrage^) und legt eine
    echo   Start- und Desktop-Verknuepfung an.
    echo ==========================================================
  ) else (
    echo [FEHLER] Installer wurde nicht erzeugt. Bitte Ausgabe oben pruefen.
  )
) else (
  echo    [WARNUNG] Inno Setup konnte nicht eingerichtet werden.
  echo    Erstelle als Notloesung ein ZIP ^(nur eine portable App, KEIN Installer^).
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\AICPResearch\*' -DestinationPath 'dist\AICP-Research-Windows.zip' -Force"
  echo.
  echo ==========================================================
  echo   Portable App:  dist\AICP-Research-Windows.zip
  echo   Fuer einen echten Installer bitte Inno Setup installieren:
  echo       winget install -e --id JRSoftware.InnoSetup
  echo   und diese Datei danach erneut ausfuehren.
  echo ==========================================================
)
echo.
pause
exit /b 0

REM ==== Unterprogramm: sucht ISCC.exe an allen ueblichen Orten ====
:FIND_ISCC
set "ISCC="
for %%D in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "build\innosetup\ISCC.exe"
) do (
  if not defined ISCC if exist "%%~D" set "ISCC=%%~D"
)
goto :eof
