# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Konfiguration: erzeugt eine vollständig eigenständige App.
#   macOS:   dist/AICP Research.app   (per Build-DMG.command -> AICP-Research.dmg)
#   Windows: dist/AICPResearch/      (per GitHub Actions -> Setup-EXE)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent

datas = [
    (str(root / "app" / "ui"), "ui"),
]
binaries = []
hiddenimports = ["echo_engine", "nltk", "nltk.stem.isri"]

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

for pkg in ("fastembed", "onnxruntime", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

if sys.platform == "darwin":
    hiddenimports += ["Vision", "Quartz", "Foundation", "objc"]

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
            "NSAppleEventsUsageDescription":
                "AICP Research nutzt Automation als Reserve-Weg für "
                "Word-Dokumente.",
        },
    )
