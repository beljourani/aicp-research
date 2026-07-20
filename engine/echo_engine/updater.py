# -*- coding: utf-8 -*-
"""Selbst-Update über GitHub Releases.

Ablauf:
  1. Die App kennt ihre eigene Version (Datei VERSION, von der Cloud beim
     Bauen aus dem Git-Tag geschrieben).
  2. check() fragt das neueste GitHub-Release ab und vergleicht die Version.
  3. Ist eine neuere da, liefert check() Version + Download-Link des passenden
     Installers (Windows: .exe, macOS: .dmg).
  4. download_installer() lädt die Datei, launch_installer() startet sie –
     danach beendet sich die App, damit der Installer sie ersetzen kann.

Alles läuft nur auf ausdrücklichen Wunsch des Nutzers (Klick im Fenster) und
gegen das EIGENE Repository. Ohne Internet passiert einfach nichts.
"""
from __future__ import annotations

import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return Path(__file__).resolve().parents[2]


def current_version() -> str:
    """Liest die mitgelieferte VERSION-Datei (Fallback 0.0.0)."""
    for p in (_base_dir() / "VERSION",
              Path(__file__).resolve().parents[2] / "VERSION"):
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except Exception:
            pass
    return "0.0.0"


def _to_tuple(v: str) -> tuple:
    v = (v or "").strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest: str, current: str) -> bool:
    return _to_tuple(latest) > _to_tuple(current)


def _asset_suffix() -> str:
    return ".dmg" if sys.platform == "darwin" else ".exe"


def _pick_asset(assets: list) -> tuple:
    """Wählt die passende Release-Datei für das aktuelle System.

    Windows: der Setup-Installer (.exe).
    macOS:   bevorzugt das App-ZIP (automatisches Ersetzen), sonst das DMG
             (manuelle Installation).
    """
    pairs = [(a.get("name", ""), a.get("browser_download_url"))
             for a in (assets or []) if a.get("browser_download_url")]
    if sys.platform == "darwin":
        for n, u in pairs:
            nl = n.lower()
            if nl.endswith(".zip") and "macos" in nl:
                return u, n
        for n, u in pairs:
            if n.lower().endswith(".dmg"):
                return u, n
    else:
        for n, u in pairs:
            if n.lower().endswith(".exe"):
                return u, n
    return None, None


def check(repo: str, timeout: int = 8) -> dict:
    """Prüft das neueste Release. Liefert immer ein dict mit 'ok'.

    repo: "benutzer/repository"
    Ergebnis bei Erfolg:
      {ok, update_available, current, latest, url, name, notes}
    """
    cur = current_version()
    if not repo or "/" not in repo:
        return {"ok": False, "error": "kein Repo konfiguriert",
                "current": cur, "update_available": False}
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(api, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "AICP-Research-Updater",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e), "current": cur,
                "update_available": False}

    latest = (data.get("tag_name") or data.get("name") or "").strip()
    url, name = _pick_asset(data.get("assets", []))
    avail = bool(latest) and is_newer(latest, cur) and bool(url)
    return {"ok": True, "current": cur, "latest": latest,
            "update_available": avail, "url": url, "name": name,
            "notes": (data.get("body") or "")[:2000],
            "has_asset": bool(url)}


def release_notes(repo: str, version: str, timeout: int = 8) -> str:
    """Holt den Beschreibungstext des Releases zu einer Version."""
    if not repo or "/" not in repo or not version:
        return ""
    for tag in (f"v{version}", version):
        api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        req = urllib.request.Request(api, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AICP-Research-Updater",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                data = json.loads(r.read().decode("utf-8"))
            body = (data.get("body") or "").strip()
            if body:
                return body
        except Exception:
            continue
    return ""


def download_installer(url: str, name: str | None = None, progress=None) -> Path:
    """Lädt den Installer in einen temporären Ordner und liefert den Pfad."""
    dest_dir = Path(tempfile.gettempdir()) / "aicp-research-update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = name or os.path.basename(url) or ("installer" + _asset_suffix())
    dest = dest_dir / fname
    req = urllib.request.Request(url, headers={"User-Agent": "AICP-Research-Updater"})
    with urllib.request.urlopen(req, timeout=60, context=_SSL) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(int(done * 100 / total))
    return dest


def _mac_app_bundle() -> "Path | None":
    """Pfad zum eigenen .app-Bundle (nur in der gepackten App unter macOS)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    p = Path(sys.executable).resolve()
    for anc in [p] + list(p.parents):
        if anc.suffix == ".app":
            return anc
    return None


def install_mac_zip(zip_path: Path) -> bool:
    """Ersetzt die laufende .app automatisch durch die neue Version aus dem
    ZIP – ohne Zutun des Nutzers. Ein kleines Hintergrundskript wartet, bis
    diese App beendet ist, tauscht das Bundle aus und startet es neu.
    Liefert True, wenn der Austausch angestoßen wurde."""
    app = _mac_app_bundle()
    if app is None:
        return False
    tmp = Path(tempfile.gettempdir()) / "aicp-research-update"
    tmp.mkdir(parents=True, exist_ok=True)
    script = tmp / "apply-update.sh"
    script.write_text(
        "#!/bin/bash\n"
        f'ZIP="{zip_path}"\n'
        f'APP="{app}"\n'
        f'PID="{os.getpid()}"\n'
        f'EXTRACT="{tmp}/extract"\n'
        'while kill -0 "$PID" 2>/dev/null; do sleep 0.4; done\n'
        'sleep 1\n'
        'rm -rf "$EXTRACT"; mkdir -p "$EXTRACT"\n'
        'ditto -x -k "$ZIP" "$EXTRACT" 2>/dev/null || '
        '/usr/bin/unzip -oq "$ZIP" -d "$EXTRACT"\n'
        'NEWAPP=$(/usr/bin/find "$EXTRACT" -maxdepth 2 -name "*.app" | head -1)\n'
        '[ -z "$NEWAPP" ] && exit 1\n'
        'rm -rf "$APP"\n'
        'mv "$NEWAPP" "$APP"\n'
        '/usr/bin/xattr -dr com.apple.quarantine "$APP" 2>/dev/null\n'
        'open "$APP"\n'
    )
    subprocess.Popen(["/bin/bash", str(script)], start_new_session=True)
    return True


def launch_installer(path: Path) -> bool:
    """Startet die passende Installation.

    Windows: Inno-Setup läuft still, schließt die App und startet sie neu.
    macOS:   .zip -> vollautomatischer Austausch; .dmg -> Fenster öffnen
             (manuelle Installation als Rückfall).
    Liefert True, wenn ein vollautomatischer Weg angestoßen wurde."""
    path = Path(path)
    if sys.platform == "darwin":
        if path.suffix.lower() == ".zip" and install_mac_zip(path):
            return True
        subprocess.Popen(["open", str(path)])   # DMG-Rückfall (manuell)
        return False
    elif os.name == "nt":
        try:
            subprocess.Popen(
                [str(path), "/SILENT", "/CLOSEAPPLICATIONS",
                 "/RESTARTAPPLICATIONS", "/NORESTART"],
                close_fds=True)
        except Exception:
            os.startfile(str(path))  # type: ignore[attr-defined]
        return True
    else:
        subprocess.Popen(["xdg-open", str(path)])
        return False
