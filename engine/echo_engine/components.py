# -*- coding: utf-8 -*-
"""Selbstladende Komponenten (z.B. LibreOffice für Word-Konvertierung).

Prinzip: Die App bringt alles Nötige mit oder lädt es beim ersten
Bedarf selbst herunter – der Nutzer muss nie etwas installieren.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

# Verhindert, dass mehrere gleichzeitige Jobs jeder für sich denselben
# Konverter herunterladen. Der Erste lädt, alle anderen warten und
# benutzen dann dieselbe Installation.
_install_lock = threading.Lock()

# Fallback-Version, falls die Live-Ermittlung scheitert. Die App fragt
# zuerst die aktuell gültige Version ab (siehe _lo_version), damit der
# Download nicht kaputtgeht, wenn eine Version aus dem Mirror fliegt.
_LO_FALLBACK = "25.8.3"
_LO_BASE = "https://download.documentfoundation.org/libreoffice/stable"


def _lo_version() -> str:
    """Aktuell im Mirror verfügbare LibreOffice-Version ermitteln."""
    try:
        with _urlopen(_LO_BASE + "/", timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
        import re
        vers = re.findall(r'href="(\d+\.\d+\.\d+)/"', html)
        if vers:
            # höchste Versionsnummer wählen
            return max(vers, key=lambda v: [int(x) for x in v.split(".")])
    except Exception:
        pass
    return _LO_FALLBACK


def _lo_urls() -> dict:
    v = _lo_version()
    return {
        "mac_arm": f"{_LO_BASE}/{v}/mac/aarch64/"
                   f"LibreOffice_{v}_MacOS_aarch64.dmg",
        "mac_x64": f"{_LO_BASE}/{v}/mac/x86_64/"
                   f"LibreOffice_{v}_MacOS_x86-64.dmg",
        "win_x64": f"{_LO_BASE}/{v}/win/x86_64/"
                   f"LibreOffice_{v}_Win_x86-64.msi",
    }


# --- Mitgelieferte Schriften -------------------------------------------
# Die App rendert Word-Dateien AUSSCHLIESSLICH mit diesen Schriften.
# Nur so entsteht auf jedem Gerät dasselbe PDF mit denselben Seitenzahlen –
# unabhängig davon, was auf dem Rechner installiert ist.
ARABIC_FONT = "Amiri"          # freie Naskh-Schrift (OFL)
LATIN_FONT = "Tinos"           # metrisch wie Times New Roman (Apache 2.0)

# Jede Schrift wird von mehreren Spiegeln probiert – so bricht nichts,
# wenn Google eine Schrift innerhalb des Repos verschiebt (z.B. Tinos von
# 'apache/' nach 'ofl/'). Reihenfolge: jsDelivr-CDN (stabil), dann GitHub.
def _mirror(rel: str) -> list[str]:
    return [f"https://cdn.jsdelivr.net/gh/google/fonts@main/{rel}",
            f"https://raw.githubusercontent.com/google/fonts/main/{rel}"]


_FONTS = {
    "Amiri-Regular.ttf": _mirror("ofl/amiri/Amiri-Regular.ttf"),
    "Amiri-Bold.ttf": _mirror("ofl/amiri/Amiri-Bold.ttf"),
    "Amiri-Italic.ttf": _mirror("ofl/amiri/Amiri-Italic.ttf"),
    "Amiri-BoldItalic.ttf": _mirror("ofl/amiri/Amiri-BoldItalic.ttf"),
    # Tinos: erst ofl/ (neuer Ort), dann apache/ (alter Ort) versuchen.
    "Tinos-Regular.ttf": _mirror("ofl/tinos/Tinos-Regular.ttf")
        + _mirror("apache/tinos/Tinos-Regular.ttf"),
    "Tinos-Bold.ttf": _mirror("ofl/tinos/Tinos-Bold.ttf")
        + _mirror("apache/tinos/Tinos-Bold.ttf"),
    "Tinos-Italic.ttf": _mirror("ofl/tinos/Tinos-Italic.ttf")
        + _mirror("apache/tinos/Tinos-Italic.ttf"),
    "Tinos-BoldItalic.ttf": _mirror("ofl/tinos/Tinos-BoldItalic.ttf")
        + _mirror("apache/tinos/Tinos-BoldItalic.ttf"),
}

# Merker: Schriften werden pro Sitzung nur EINMAL versucht – nie wieder
# der Wiederholungs-Spam bei jeder Umwandlung.
_fonts_tried = False


def fonts_dir() -> Path:
    d = components_dir() / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_fonts(progress=None) -> Path:
    """Lädt die mitgelieferten Notvorrat-Schriften – nur einmal pro Sitzung,
    aus mehreren Quellen, und immer geräuschlos (nie fatal)."""
    global _fonts_tried
    d = fonts_dir()
    missing = [(n, urls) for n, urls in _FONTS.items() if not (d / n).exists()]
    if not missing or _fonts_tried:
        return d
    with _install_lock:
        if _fonts_tried:
            return d
        _fonts_tried = True
        for name, urls in missing:
            if (d / name).exists():
                continue
            for url in urls:
                try:
                    _download(url, d / name, progress, "Schriften",
                              quiet=True)
                    if (d / name).exists():
                        break            # erfolgreich – nächste Schrift
                except Exception:
                    continue             # nächster Spiegel
    return d


def system_font_sources() -> list[Path]:
    """Ordner, in denen Schriften des Rechners liegen können – inklusive
    der privaten Ablagen von Microsoft Office. Word lädt Schriften wie
    'Traditional Arabic' als Cloud-Font in einen eigenen Ordner, den kein
    anderes Programm durchsucht. Genau diese Schriften brauchen wir, um
    ein Dokument so zu setzen, wie Word es tut."""
    home = Path.home()
    return [
        home / "Library" / "Group Containers" / "UBF8T346G9.Office"
        / "FontCache" / "4" / "CloudFonts",
        Path("/Library/Fonts/Microsoft"),
        Path("/Applications/Microsoft Word.app/Contents/Resources/Fonts"),
        Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts"),
        home / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path(r"C:\Windows\Fonts"),
    ]


def collect_document_fonts(progress=None) -> Path:
    """Sammelt die auf diesem Rechner vorhandenen Schriften (inkl. der
    Office-Cloud-Schriften) in einem Ordner der App. Diese Sammlung geht
    später auch mit der Bibliothek auf andere Geräte, damit dort exakt
    gleich gesetzt wird."""
    import shutil as _sh
    target = components_dir() / "docfonts"
    target.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in system_font_sources():
        if not src.exists():
            continue
        for f in src.rglob("*"):
            if f.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            dst = target / f.name
            if dst.exists():
                continue
            try:
                _sh.copy(f, dst)
                n += 1
            except Exception:
                pass
    if progress and n:
        progress(f"{n} Schriften des Rechners übernommen")
    return target


def install_fonts_into_converter(soffice: str, progress=None) -> bool:
    """Stattet den Konverter mit Schriften aus:
    1. den mitgelieferten (immer vorhanden, geräteunabhängig)
    2. den auf diesem Rechner gefundenen Original-Schriften – nur damit
       kann er ein Word-Dokument so umbrechen wie Word selbst.
    """
    p = Path(soffice)
    if sys.platform == "darwin":
        target = p.parent.parent / "Resources" / "fonts" / "truetype"
    else:
        target = p.parent.parent / "share" / "fonts" / "truetype"
    try:
        target.mkdir(parents=True, exist_ok=True)
        import shutil as _sh
        for src in (ensure_fonts(progress), collect_document_fonts(progress)):
            for f in src.iterdir():
                if f.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                    continue
                dst = target / f.name
                if not dst.exists():
                    _sh.copy(f, dst)
        return True
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def components_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    d = base / "AICP Research" / "components"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_soffice(auto_install: bool = False,
                 progress=None) -> str | None:
    """Findet den LibreOffice-Konverter. Reihenfolge:
    1. von der App selbst installierte Komponente
    2. systemweit installiertes LibreOffice
    3. bei auto_install=True: automatisch herunterladen
    progress: optionale Callback-Funktion (text) für Statusanzeigen.
    """
    own = _own_soffice_path()
    if own and own.exists():
        return str(own)

    import shutil
    p = shutil.which("soffice") or shutil.which("libreoffice")
    if p:
        return p
    for cand in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
                 r"C:\Program Files\LibreOffice\program\soffice.exe"):
        if Path(cand).exists():
            return cand

    if not auto_install:
        return None

    # Nur EIN Download gleichzeitig – die übrigen Jobs warten hier.
    if not _install_lock.acquire(blocking=False):
        if progress:
            progress("wartet auf den Word-Konverter …")
        with _install_lock:
            pass                      # warten, bis der Erste fertig ist
        own = _own_soffice_path()     # inzwischen installiert?
        return str(own) if own and own.exists() else None

    try:
        own = _own_soffice_path()     # doppelte Prüfung im Lock
        if own and own.exists():
            return str(own)
        return _install_libreoffice(progress or (lambda s: None))
    except Exception:
        import traceback
        traceback.print_exc()
        return None
    finally:
        _install_lock.release()


def _own_soffice_path() -> Path | None:
    d = components_dir()
    if sys.platform == "darwin":
        return d / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    if os.name == "nt":
        return d / "LibreOffice" / "program" / "soffice.exe"
    return None


def _ssl_context():
    """Eigener Zertifikatsspeicher.

    Das von python.org installierte Python kennt die System-Zertifikate
    von macOS nicht – ohne diesen Griff schlägt JEDER Download mit
    'CERTIFICATE_VERIFY_FAILED' fehl.
    """
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _urlopen(url: str, timeout: int = 60):
    return urllib.request.urlopen(url, timeout=timeout,
                                  context=_ssl_context())


def _download(url: str, dest: Path, progress=None, label: str = "Datei",
              quiet: bool = False):
    """Lädt eine Datei – notfalls über die Bordmittel des Systems.

    Python bringt je nach Installation keinen brauchbaren Zertifikatsspeicher
    mit ('CERTIFICATE_VERIFY_FAILED'). Deshalb: erst Python versuchen, sonst
    curl (macOS/Linux) bzw. PowerShell (Windows) – die kennen die
    System-Zertifikate immer. quiet=True unterdrückt jede Ausgabe (für
    Versuche über mehrere Spiegel, bei denen Fehlschläge normal sind).
    """
    if progress and not quiet:
        progress(f"{label} wird geladen …")
    try:
        with _urlopen(url, timeout=120) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total and not quiet:
                    progress(f"{label} wird geladen … {done * 100 // total} %")
        if dest.exists() and dest.stat().st_size > 0:
            return
    except Exception as e:
        if not quiet:
            print(f"Python-Download fehlgeschlagen ({e}) – "
                  "nutze Systemwerkzeug.", flush=True)

    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-Command",
               f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest}'"]
    else:
        cmd = ["curl", "-fsSL", "--retry", "2", "-o", str(dest), url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"Download fehlgeschlagen: {url} "
                           f"({r.stderr.strip()[:120]})")


def _install_libreoffice(progress) -> str | None:
    d = components_dir()
    urls = _lo_urls()
    if sys.platform == "darwin":
        import platform
        url = urls["mac_arm"] if platform.machine() == "arm64" \
            else urls["mac_x64"]
        with tempfile.TemporaryDirectory() as tmp:
            dmg = Path(tmp) / "lo.dmg"
            progress("Word-Konverter wird geladen …")
            _download(url, dmg, progress, "Word-Konverter")
            progress("Word-Konverter wird installiert …")
            mnt = Path(tmp) / "mnt"
            mnt.mkdir()
            subprocess.run(["hdiutil", "attach", str(dmg), "-mountpoint",
                            str(mnt), "-nobrowse", "-quiet"], check=True,
                           timeout=300)
            try:
                src = mnt / "LibreOffice.app"
                subprocess.run(["cp", "-R", str(src), str(d)], check=True,
                               timeout=600)
                # Quarantäne-Attribut entfernen, sonst blockt Gatekeeper
                subprocess.run(["xattr", "-dr", "com.apple.quarantine",
                                str(d / "LibreOffice.app")],
                               capture_output=True, timeout=120)
            finally:
                subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"],
                               capture_output=True, timeout=120)
        out = _own_soffice_path()
        return str(out) if out and out.exists() else None

    if os.name == "nt":
        with tempfile.TemporaryDirectory() as tmp:
            msi = Path(tmp) / "lo.msi"
            progress("Word-Konverter wird geladen …")
            _download(urls["win_x64"], msi, progress, "Word-Konverter")
            progress("Word-Konverter wird installiert …")
            target = d / "LibreOffice"
            # Administrative Installation = reines Entpacken, keine Adminrechte
            subprocess.run(["msiexec", "/a", str(msi), "/qn",
                            f"TARGETDIR={target}"], check=True, timeout=900)
        out = _own_soffice_path()
        return str(out) if out and out.exists() else None

    return None
