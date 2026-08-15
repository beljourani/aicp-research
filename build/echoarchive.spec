# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Konfiguration: erzeugt eine vollständig eigenständige App.
#   macOS:   dist/AICP Research.app   (per Build-DMG.command -> AICP-Research.dmg)
#   Windows: dist/AICPResearch/      (per GitHub Actions -> Setup-EXE)
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent

datas = [
    (str(root / "app" / "ui"), "ui"),
]
binaries = []
# "docx" ist der Modulname von python-docx, "pypdf" der reine Python-Rückfall
# fürs PDF-Lesen. Beide werden erst zur Laufzeit importiert (in extract.py, je
# nach Dateityp), deshalb findet PyInstaller sie nicht von allein.
hiddenimports = ["echo_engine", "nltk", "nltk.stem.isri", "docx", "pypdf"]

# Versionsdatei mitliefern (die App liest daraus ihre eigene Version fürs Update)
_vfile = root / "VERSION"
APP_VERSION = "1.0.0"
if _vfile.exists():
    datas.append((str(_vfile), "."))
    try:
        APP_VERSION = _vfile.read_text(encoding="utf-8").strip() or APP_VERSION
    except Exception:
        pass

if sys.platform == "win32":
    # Word-COM-Automation braucht diese Module explizit
    hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

# Gebündeltes Embedding-Modell (vom Build-Skript nach build/models gelegt)
models = root / "build" / "models"
if models.exists():
    datas.append((str(models), "models"))

# Gebündelte Tesseract-OCR (nur Windows-Build, von CI nach build/tesseract)
tess = root / "build" / "tesseract"
if tess.exists():
    datas.append((str(tess), "tesseract"))

# huggingface_hub muss ausdrücklich mit eingesammelt werden: das Paket lädt
# seine Untermodule verzögert (lazy) über eine Namenstabelle, nicht über
# normale import-Zeilen. PyInstaller kann solchen Importen nicht folgen und
# packt dann nur die Teile ein, die zufällig direkt importiert werden. Fehlt
# ein Teil davon, scheitert schon "import fastembed" im ausgelieferten Build -
# und weil die semantische Suche das Modell nur bei Bedarf lädt, sieht der
# Nutzer keinen Fehler: die semantische Suche liefert einfach nie Treffer.
for pkg in ("fastembed", "onnxruntime", "tokenizers", "huggingface_hub"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

if sys.platform == "darwin":
    hiddenimports += ["Vision", "Quartz", "Foundation", "objc"]

# macOS-Architektur des fertigen Programms.
#
# Gebaut wird sonst genau für die Architektur des Build-Rechners. Die
# GitHub-Runner sind Apple Silicon, das Ergebnis ist also arm64 und startet auf
# einem Intel-Mac gar nicht (Rosetta übersetzt nur in die andere Richtung).
#
# Ein "universal2"-Programm (arm64 + Intel in einer Datei) verlangt, dass JEDE
# eingebundene Bibliothek selbst universal2 ist. Das ist heute nicht erfüllt:
# onnxruntime liefert seit Version 1.24 ausschliesslich arm64-Räder für macOS
# (bis 1.22.1 gab es universal2), numpy, PyMuPDF, tokenizers und Pillow liefern
# getrennte arm64- und Intel-Räder. PyInstaller bricht den Build mit
# "is not a fat binary" ab, sobald target_arch="universal2" gesetzt ist -
# es gäbe dann gar kein macOS-Release mehr statt nur keines für Intel.
#
# Deshalb: standardmässig wie bisher (Architektur des Build-Rechners), und über
# die Umgebungsvariable AICP_MAC_ARCH bewusst umschaltbar, sobald die
# Abhängigkeiten es hergeben:
#     AICP_MAC_ARCH=universal2 python -m PyInstaller ... build/echoarchive.spec
# Echte Intel-Unterstützung braucht ansonsten einen zweiten Build-Lauf auf
# einem Intel-Runner (macos-13) - dort fehlt allerdings onnxruntime, die
# semantische Suche wäre auf Intel-Macs also ohnehin nicht dabei.
MAC_ARCH = os.environ.get("AICP_MAC_ARCH") or None
if sys.platform != "darwin":
    MAC_ARCH = None

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root / "engine")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

icon_ico = str(root / "build" / "icon.ico")
icon_icns = str(root / "build" / "icon.icns")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AICPResearch",
    console=False,
    icon=icon_ico,
    target_arch=MAC_ARCH,   # wird nur auf macOS ausgewertet, sonst None
)
coll = COLLECT(exe, a.binaries, a.datas, name="AICPResearch")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AICP Research.app",
        icon=icon_icns,
        bundle_identifier="com.aicp.research",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": "AICP Research",
            "CFBundleShortVersionString": APP_VERSION,
            # Ältestes unterstütztes macOS. Ohne diesen Eintrag nennt macOS
            # gar keine Mindestversion, und auf einem zu alten System startet
            # die App mit einer nichtssagenden Fehlermeldung statt mit dem
            # klaren Hinweis, dass das System zu alt ist.
            # 11.0 ist der Stand der eingebundenen Bibliotheken (PyMuPDF,
            # tokenizers). Nur onnxruntime ist gegen macOS 14 gebaut - die
            # semantische Suche braucht daher wirklich macOS 14; alles andere
            # (Volltextsuche, Lesen, Einlesen) läuft ab 11.0.
            "LSMinimumSystemVersion": "11.0",
            "NSAppleEventsUsageDescription":
                "AICP Research nutzt Automation als Reserve-Weg für "
                "Word-Dokumente.",
        },
    )
