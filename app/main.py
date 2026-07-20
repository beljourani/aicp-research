# -*- coding: utf-8 -*-
"""AICP Research Desktop-App.

Architektur: Ein interner HTTP-Server (nur 127.0.0.1, kein Netzzugriff von
außen) liefert die Oberfläche und die API. pywebview zeigt sie nur als
Fenster an. Das umgeht die fragile JS-Brücke von pywebview komplett.

Start:  python3 app/main.py   (oder Doppelklick auf AICP Research.command)
Datenbank: ~/Library/Application Support/AICP Research/archive.db (macOS)
           %APPDATA%/AICP Research/archive.db (Windows)
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import socket
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

# Mehrere Autoren werden in EINER Spalte als getrennte Liste gespeichert.
# Trennzeichen: arabisches Semikolon mit Leerzeichen (kollidiert nicht mit Namen).
AUTHOR_SEP = " ؛ "

# Standard-Repository für Selbst-Updates (Cloud-Builds liegen als GitHub-
# Release dort). Kann in der App überschrieben werden (Einstellung
# 'update_repo' in der meta-Tabelle). Format: "benutzer/repository".
UPDATE_REPO = "beljourani/aicp-research"


def split_authors(value) -> list[str]:
    """Zerlegt einen gespeicherten Autoren-String in einzelne Namen."""
    if not value:
        return []
    parts = re.split(r"\s*[؛;]\s*", str(value))
    return [p.strip() for p in parts if p.strip()]


def join_authors(names) -> str | None:
    """Fügt eine Liste von Autoren zu einem Speicher-String zusammen."""
    if isinstance(names, str):
        names = split_authors(names)
    clean = []
    for n in (names or []):
        n = (n or "").strip()
        if n and n not in clean:
            clean.append(n)
    return AUTHOR_SEP.join(clean) if clean else None

from echo_engine import connect, index_document, hybrid_search  # noqa: E402
from echo_engine.indexer import ensure_index_version  # noqa: E402
from echo_engine.semantic import Embedder, embed_passages, ensure_vector_schema  # noqa: E402

def _resource_base() -> Path:
    """Basisordner für mitgelieferte Dateien – funktioniert im
    Entwicklungsmodus UND in der gepackten App (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return Path(__file__).parent


UI_FILE = _resource_base() / "ui" / "index.html"


def data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    d = base / "AICP Research"
    # Bestehende Bibliothek aus der frueheren Version (EchoArchive) uebernehmen,
    # damit vorhandene Buecher nach der Umbenennung erhalten bleiben.
    if not d.exists():
        old = base / "EchoArchive"
        if old.exists():
            try:
                old.rename(d)
            except Exception:
                d.mkdir(parents=True, exist_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


# Wie viele Dokumente gleichzeitig verarbeitet werden. Mehr bringt
# nichts – die Arbeit ist rechenlastig und die Datenbank hat nur einen
# Schreiber. Zu viele Threads machen alles langsamer.
MAX_WORKERS = 2


class Core:
    """Anwendungslogik, vom HTTP-Handler aufgerufen."""

    def __init__(self):
        self.db_path = data_dir() / "archive.db"
        self.window = None
        self._embedder: Embedder | None = None
        self._embedder_state = "lädt"
        self._update: dict = {"ok": False, "update_available": False}
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []          # Reihenfolge für die Anzeige
        self._queue: queue.Queue = queue.Queue()
        for _ in range(MAX_WORKERS):
            threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._startup, daemon=True).start()

    # --- Warteschlange ---------------------------------------------------
    def _enqueue(self, path: str, job_id: str, **opts):
        if job_id not in self._jobs:
            self._order.append(job_id)
        self._jobs[job_id] = {"file": job_id, "state": "wartet"}
        self._queue.put((path, job_id, opts))

    def _skip(self, job_id: str, grund: str):
        """Datei bewusst nicht einlesen (z.B. Word-Dublette zu einem PDF)."""
        if job_id not in self._jobs:
            self._order.append(job_id)
        self._jobs[job_id] = {"file": job_id, "state": "übersprungen",
                              "error": grund}

    def _filter_duplicates(self, paths: list[str]) -> list[str]:
        """Liegt dasselbe Buch als PDF UND als Word-Datei vor, wird nur das
        PDF eingelesen: dort sind die Seitenzahlen die der gedruckten
        Ausgabe. Die Word-Fassung wäre nur eine Dublette mit anderem Satz."""
        stems = {}
        for p in paths:
            stem, ext = os.path.splitext(os.path.basename(p))
            stems.setdefault(stem.lower(), set()).add(ext.lower())
        # Bereits vorhandene PDFs in der Bibliothek berücksichtigen
        con = self._con()
        known = {os.path.splitext(os.path.basename(r[0] or ""))[0].lower()
                 for r in con.execute(
                     "SELECT file_path FROM documents WHERE file_type='pdf'")}
        con.close()

        keep = []
        for p in paths:
            stem, ext = os.path.splitext(os.path.basename(p))
            if ext.lower() == ".docx" and (
                    ".pdf" in stems.get(stem.lower(), set())
                    or stem.lower() in known):
                self._skip(os.path.basename(p),
                           "PDF-Fassung vorhanden – diese wird verwendet "
                           "(gedruckte Seitenzahlen)")
                continue
            keep.append(p)
        return keep

    def _worker(self):
        while True:
            path, job_id, opts = self._queue.get()
            try:
                self._index_one(path, job_id, **opts)
            except Exception:
                traceback.print_exc()
            finally:
                self._queue.task_done()

    def _startup(self):
        # Suchindex bei Bedarf an neue Stemming-Version anpassen
        try:
            con = self._con()
            if ensure_index_version(con):
                print("Suchindex an neue Version angepasst.", flush=True)
            con.close()
        except Exception:
            traceback.print_exc()
        # Im Hintergrund nach einem Update sehen (scheitert leise ohne Netz)
        try:
            from echo_engine import updater
            self._update = updater.check(self.update_repo())
        except Exception:
            pass
        self._init_embedder()

    def _con(self):
        con = connect(self.db_path)
        ensure_vector_schema(con)
        return con

    def _init_embedder(self):
        try:
            emb = Embedder()
            emb.embed(["تجربة"])
            self._embedder = emb
            self._embedder_state = "bereit"
            con = self._con()
            embed_passages(con, emb)
            con.close()
        except Exception:
            traceback.print_exc()
            self._embedder_state = "fehler"

    # --- API-Methoden -----------------------------------------------------
    def status(self, _body=None):
        # Erst die Verarbeitungs-Jobs in Reihenfolge, dann alle übrigen
        # (z.B. Export/Import), damit die Oberfläche sie ebenfalls sieht.
        snapshot = dict(self._jobs)          # gegen gleichzeitige Änderung
        seen, jobs = set(), []
        for j in list(self._order):
            if j in snapshot:
                jobs.append(snapshot[j]); seen.add(j)
        for k, v in snapshot.items():
            if k not in seen:
                jobs.append(v)
        up = self._update if isinstance(self._update, dict) else {}
        return {"semantik": self._embedder_state, "jobs": jobs,
                "update": {"available": bool(up.get("update_available")),
                           "latest": up.get("latest"),
                           "current": up.get("current")}}

    def clear_jobs(self, _body=None):
        """Entfernt abgeschlossene Einträge (fertig/fehler/übersprungen) aus
        der Liste. Laufende oder wartende Jobs bleiben erhalten."""
        done = {"fertig", "fehler", "übersprungen"}
        for jid in list(self._jobs.keys()):
            if (self._jobs[jid].get("state") or "") in done:
                self._jobs.pop(jid, None)
                if jid in self._order:
                    self._order.remove(jid)
        return {"ok": True, "remaining": len(self._jobs)}

    def get_settings(self, _body=None):
        con = self._con()
        con.execute("CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        row = con.execute(
            "SELECT value FROM meta WHERE key='lang'").fetchone()
        con.close()
        return {"lang": row[0] if row else "de"}

    def set_settings(self, body):
        con = self._con()
        con.execute("CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT OR REPLACE INTO meta (key, value) "
                    "VALUES ('lang', ?)", (body.get("lang", "de"),))
        con.commit()
        con.close()
        return {"ok": True}

    # --- Selbst-Update -----------------------------------------------------
    def _meta_get(self, key: str, default: str = "") -> str:
        try:
            con = self._con()
            con.execute("CREATE TABLE IF NOT EXISTS meta "
                        "(key TEXT PRIMARY KEY, value TEXT)")
            row = con.execute(
                "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            con.close()
            return row[0] if row and row[0] else default
        except Exception:
            return default

    def update_repo(self) -> str:
        return self._meta_get("update_repo", UPDATE_REPO)

    def version(self, _body=None):
        from echo_engine import updater
        return {"version": updater.current_version(),
                "repo": self.update_repo(),
                "configured": "/" in self.update_repo()
                and not self.update_repo().startswith("DEIN-")}

    def set_update_repo(self, body):
        repo = (body or {}).get("repo", "").strip()
        con = self._con()
        con.execute("CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT OR REPLACE INTO meta (key, value) "
                    "VALUES ('update_repo', ?)", (repo,))
        con.commit()
        con.close()
        return {"ok": True, "repo": repo}

    def check_update(self, _body=None):
        from echo_engine import updater
        res = updater.check(self.update_repo())
        self._update = res
        return res

    def apply_update(self, body=None):
        """Lädt den passenden Installer und startet ihn. Danach beendet sich
        die App, damit der Installer sie ersetzen kann."""
        from echo_engine import updater
        info = getattr(self, "_update", None) or updater.check(self.update_repo())
        if not info.get("ok") or not info.get("url"):
            return {"error": "Kein Update verfügbar oder kein Installer im "
                             "Release gefunden."}
        self._jobs["__update__"] = {"file": "Update", "state": "lädt …"}

        def work():
            try:
                path = updater.download_installer(
                    info["url"], info.get("name"),
                    progress=lambda p: self._jobs["__update__"].update(
                        state=f"lädt … {p}%"))
                self._jobs["__update__"] = {"file": "Update",
                                            "state": "startet Installer …"}
                updater.launch_installer(path)
                # kurz warten, dann App beenden (Installer übernimmt)
                threading.Timer(1.5, lambda: os._exit(0)).start()
            except Exception as e:
                traceback.print_exc()
                self._jobs["__update__"] = {"file": "Update",
                                            "state": "fehler", "error": str(e)}
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def documents(self, _body=None):
        con = self._con()
        rows = con.execute(
            "SELECT d.*, COUNT(p.id) AS passage_count FROM documents d "
            "LEFT JOIN passages p ON p.document_id = d.id "
            "GROUP BY d.id ORDER BY d.created_at DESC").fetchall()
        con.close()
        return [dict(r) for r in rows]

    def upload(self, filename: str, data: bytes):
        """Per Drag&Drop übertragene Datei speichern und indexieren."""
        safe = os.path.basename(filename) or "datei"
        updir = data_dir() / "uploads"
        updir.mkdir(parents=True, exist_ok=True)
        dest = updir / safe
        # Namenskollision: nummerieren statt überschreiben
        stem, suffix = os.path.splitext(safe)
        n = 1
        while dest.exists():
            n += 1
            dest = updir / f"{stem}-{n}{suffix}"
        dest.write_bytes(data)
        self._enqueue(str(dest), dest.name)
        return {"started": 1}

    def pick(self, _body=None):
        try:
            fd = getattr(webview, "FileDialog", None)
            dialog_type = fd.OPEN if fd else webview.OPEN_DIALOG
            paths = self.window.create_file_dialog(
                dialog_type, allow_multiple=True,
                file_types=("Dokumente (*.pdf;*.docx;*.txt)",))
        except Exception as e:
            traceback.print_exc()
            return {"started": 0, "error": f"Dateidialog: {e}"}
        if not paths:
            return {"started": 0}
        paths = self._filter_duplicates(list(paths))
        for p in paths:
            self._enqueue(p, os.path.basename(p))
        return {"started": len(paths)}

    # --- Bibliothek exportieren / importieren ----------------------------
    def export_library(self, body=None):
        from echo_engine.library_io import export_library
        body = body or {}
        ids = body.get("ids") or None      # None = ganze Bibliothek
        default_name = ("Auswahl.echolib" if ids else "Bibliothek.echolib")
        try:
            fd = getattr(webview, "FileDialog", None)
            dtype = fd.SAVE if fd else webview.SAVE_DIALOG
            dest = self.window.create_file_dialog(
                dtype, save_filename=default_name)
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Speichern-Dialog: {e}"}
        if not dest:
            return {"cancelled": True}
        path = dest if isinstance(dest, str) else dest[0]
        if not path.lower().endswith(".echolib"):
            path += ".echolib"
        self._jobs["__export__"] = {"file": "Export",
                                    "state": "wird exportiert …"}

        def work():
            try:
                res = export_library(
                    self.db_path, Path(path), doc_ids=ids,
                    progress=lambda s: self._jobs["__export__"].update(
                        state=s))
                self._jobs["__export__"] = {
                    "file": "Export", "state": "fertig",
                    "result": f"{res['documents']} Bücher exportiert"}
            except Exception as e:
                traceback.print_exc()
                self._jobs["__export__"] = {"file": "Export",
                                            "state": "fehler", "error": str(e)}
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "path": path}

    def import_library(self, _body=None):
        from echo_engine.library_io import import_library
        try:
            fd = getattr(webview, "FileDialog", None)
            dtype = fd.OPEN if fd else webview.OPEN_DIALOG
            src = self.window.create_file_dialog(
                dtype, allow_multiple=False,
                file_types=("AICP Research Bibliothek (*.echolib)",
                            "Alle Dateien (*.*)"))
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Öffnen-Dialog: {e}"}
        if not src:
            return {"cancelled": True}
        path = src if isinstance(src, str) else src[0]
        self._jobs["__import__"] = {"file": "Import",
                                    "state": "wird importiert …"}

        def work():
            try:
                target = data_dir() / "uploads"
                res = import_library(
                    self.db_path, Path(path), target,
                    progress=lambda s: self._jobs["__import__"].update(
                        state=s))
                self._jobs["__import__"] = {
                    "file": "Import", "state": "fertig",
                    "result": f"{res['added']} Bücher importiert"
                              + (f", {res['skipped']} bereits vorhanden"
                                 if res['skipped'] else "")}
                # Fehlende Vektoren (falls Modell erst später bereit) nachziehen
                if self._embedder is not None:
                    con = self._con()
                    embed_passages(con, self._embedder)
                    con.close()
            except Exception as e:
                traceback.print_exc()
                self._jobs["__import__"] = {"file": "Import",
                                            "state": "fehler", "error": str(e)}
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def _index_one(self, path: str, job_id: str, force_ocr: bool = False,
                   replace_id: int | None = None, title: str | None = None,
                   author: str | None = None):
        self._jobs[job_id] = {"file": job_id, "state":
                              "OCR läuft …" if force_ocr else "verarbeite"}

        def progress(text: str):
            self._jobs[job_id]["state"] = text

        try:
            con = self._con()
            if replace_id is not None:
                con.execute("DELETE FROM documents WHERE id=?", (replace_id,))
                con.commit()
            doc_id = index_document(con, path, title=title, author=author,
                                    force_ocr=force_ocr, progress=progress)
            if self._embedder is not None:
                self._jobs[job_id]["state"] = "vektorisiere"
                embed_passages(con, self._embedder, document_id=doc_id)
            con.close()
            self._jobs[job_id]["state"] = "fertig"
        except Exception as e:
            traceback.print_exc()
            self._jobs[job_id] = {"file": job_id, "state": "fehler",
                                  "error": str(e)}

    def reindex(self, body):
        """Liest ein Dokument aus seiner Originaldatei neu ein
        (nach Verbesserungen an der Extraktion)."""
        con = self._con()
        row = con.execute("SELECT * FROM documents WHERE id=?",
                          (body["id"],)).fetchone()
        con.close()
        if not row:
            return {"error": "Dokument nicht gefunden"}
        path = row["file_path"]
        if not path or not os.path.exists(path):
            return {"error": f"Originaldatei nicht mehr auffindbar: {path}"}
        self._enqueue(path, os.path.basename(path),
                      force_ocr=bool(body.get("ocr")),
                      replace_id=body["id"],
                      title=row["title"], author=row["author"])
        return {"ok": True}

    def passage(self, body):
        """Liefert die Kontextdaten zu einem Suchtreffer (für den Leser)."""
        con = self._con()
        row = con.execute(
            "SELECT p.id, p.document_id, p.page_from, p.page_to, p.text, "
            "d.title, d.author, d.file_type, d.file_path "
            "FROM passages p JOIN documents d ON d.id = p.document_id "
            "WHERE p.id = ?", (body["id"],)).fetchone()
        con.close()
        if not row:
            return {"error": "Passage nicht gefunden"}
        return dict(row)

    def page(self, body):
        """Liefert den Volltext einer Seite plus Navigationsinfos."""
        doc_id, page_no = body["document_id"], body["page_no"]
        con = self._con()
        doc = con.execute("SELECT title, author, file_type, file_path "
                          "FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            con.close()
            return {"error": "Dokument nicht gefunden"}
        row = con.execute(
            "SELECT text FROM pages WHERE document_id=? AND page_no=?",
            (doc_id, page_no)).fetchone()
        lo, hi = con.execute(
            "SELECT MIN(page_no), MAX(page_no) FROM pages WHERE document_id=?",
            (doc_id,)).fetchone()
        con.close()
        has_image = bool(doc["file_type"] == "pdf" and doc["file_path"]
                         and os.path.exists(doc["file_path"]))
        return {"title": doc["title"], "author": doc["author"],
                "page_no": page_no, "first_page": lo, "last_page": hi,
                "text": row["text"] if row else "",
                "has_image": has_image}

    def pages(self, body):
        """Liefert einen Bereich von Seiten auf einmal (für den Lesefluss).
        Wird beim Scrollen nachgeladen, damit auch dicke Bücher flüssig sind."""
        doc_id = body["document_id"]
        try:
            frm = max(1, int(body.get("from") or 1))
            to = int(body.get("to") or frm)
        except Exception:
            return {"error": "ungültiger Bereich"}
        if to < frm:
            to = frm
        to = min(to, frm + 40)          # Sicherheitsgrenze pro Anfrage
        con = self._con()
        rows = con.execute(
            "SELECT page_no, text FROM pages WHERE document_id=? "
            "AND page_no BETWEEN ? AND ? ORDER BY page_no",
            (doc_id, frm, to)).fetchall()
        lo, hi = con.execute(
            "SELECT MIN(page_no), MAX(page_no) FROM pages WHERE document_id=?",
            (doc_id,)).fetchone()
        con.close()
        return {"pages": [{"page_no": r["page_no"], "text": r["text"]}
                          for r in rows],
                "first_page": lo, "last_page": hi}

    # --- Merker (Leseposition, Schriftgröße) ------------------------------
    def meta_get(self, body):
        return {"value": self._meta_get((body or {}).get("key", ""), "")}

    def meta_set(self, body):
        body = body or {}
        key = (body.get("key") or "").strip()
        if not key:
            return {"error": "kein Schlüssel"}
        con = self._con()
        con.execute("CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                    (key, str(body.get("value", ""))))
        con.commit()
        con.close()
        return {"ok": True}

    # --- Lesezeichen ------------------------------------------------------
    def bookmark_add(self, body):
        body = body or {}
        con = self._con()
        doc = con.execute("SELECT id, title FROM documents WHERE id=?",
                          (body.get("document_id"),)).fetchone()
        if not doc:
            con.close()
            return {"error": "Dokument nicht gefunden"}
        con.execute(
            "INSERT INTO bookmarks (document_id, passage_id, doc_title, "
            "page_no, snippet, note, terms) VALUES (?,?,?,?,?,?,?)",
            (doc["id"], body.get("passage_id"), doc["title"],
             int(body.get("page_no") or 1), (body.get("snippet") or "")[:400],
             (body.get("note") or "")[:2000],
             json.dumps(body.get("terms") or [], ensure_ascii=False)))
        con.commit()
        con.close()
        return {"ok": True}

    def bookmark_toggle(self, body):
        """Setzt ein Lesezeichen – oder entfernt es, wenn dieselbe Stelle
        bereits gemerkt ist. Liefert saved=True/False."""
        body = body or {}
        doc_id = body.get("document_id")
        pid = body.get("passage_id")
        try:
            page = int(body.get("page_no") or 1)
        except Exception:
            page = 1
        con = self._con()
        if pid:
            row = con.execute("SELECT id FROM bookmarks WHERE document_id=? "
                              "AND passage_id=?", (doc_id, pid)).fetchone()
        else:
            row = con.execute("SELECT id FROM bookmarks WHERE document_id=? "
                              "AND page_no=? AND passage_id IS NULL",
                              (doc_id, page)).fetchone()
        if row:
            con.execute("DELETE FROM bookmarks WHERE id=?", (row["id"],))
            con.commit()
            con.close()
            return {"ok": True, "saved": False}
        con.close()
        res = self.bookmark_add(body)
        if res.get("error"):
            return res
        return {"ok": True, "saved": True}

    def bookmarks(self, _body=None):
        """Liste aller Lesezeichen. Verlorene Verknüpfungen (z.B. nach einem
        Neu-Scan) werden über Titel + Seite + Ausschnitt repariert."""
        con = self._con()
        out = []
        for b in con.execute("SELECT * FROM bookmarks ORDER BY id DESC"):
            doc = con.execute("SELECT id, title FROM documents WHERE id=?",
                              (b["document_id"],)).fetchone()
            if not doc:      # Buch wurde neu eingelesen -> über Titel suchen
                doc = con.execute("SELECT id, title FROM documents "
                                  "WHERE title=?", (b["doc_title"],)).fetchone()
            pid, did = b["passage_id"], (doc["id"] if doc else None)
            if did:
                ok = con.execute("SELECT 1 FROM passages WHERE id=? AND "
                                 "document_id=?", (pid, did)).fetchone()
                if not ok:   # Passage neu -> auf der Seite per Ausschnitt finden
                    cand = con.execute(
                        "SELECT id, text FROM passages WHERE document_id=? AND "
                        "? BETWEEN page_from AND page_to", (did, b["page_no"])
                    ).fetchall()
                    frag = (b["snippet"] or "")[:40]
                    pid = None
                    for c in cand:
                        if frag and frag in (c["text"] or ""):
                            pid = c["id"]
                            break
                    if pid is None and cand:
                        pid = cand[0]["id"]
                    if pid:
                        con.execute("UPDATE bookmarks SET document_id=?, "
                                    "passage_id=? WHERE id=?", (did, pid, b["id"]))
            try:
                terms = json.loads(b["terms"] or "[]")
            except Exception:
                terms = []
            out.append({"id": b["id"], "document_id": did,
                        "passage_id": pid, "doc_title": b["doc_title"],
                        "title": (doc["title"] if doc else b["doc_title"]),
                        "page_no": b["page_no"], "snippet": b["snippet"],
                        "note": b["note"] or "", "terms": terms,
                        "missing": did is None})
        con.commit()
        con.close()
        return out

    def bookmark_delete(self, body):
        con = self._con()
        con.execute("DELETE FROM bookmarks WHERE id=?", ((body or {}).get("id"),))
        con.commit()
        con.close()
        return {"ok": True}

    def bookmark_note(self, body):
        body = body or {}
        con = self._con()
        con.execute("UPDATE bookmarks SET note=? WHERE id=?",
                    ((body.get("note") or "")[:2000], body.get("id")))
        con.commit()
        con.close()
        return {"ok": True}

    def update(self, body):
        # Mehrere Autoren: als Liste (bevorzugt) oder Einzelfeld entgegennehmen.
        authors = body.get("authors")
        if authors is None:
            authors = [body.get("author")] if body.get("author") else []
        author = join_authors(authors)
        con = self._con()
        con.execute("UPDATE documents SET title=?, author=? WHERE id=?",
                    (body["title"], author, body["id"]))
        con.commit()
        con.close()
        return {"ok": True}

    def download_document(self, body):
        """Speichert die Originaldatei eines Dokuments an einen selbst
        gewählten Ort (Speichern-Dialog)."""
        con = self._con()
        row = con.execute(
            "SELECT title, file_path FROM documents WHERE id=?",
            (body["id"],)).fetchone()
        con.close()
        if not row or not row["file_path"]:
            return {"error": "Keine Originaldatei vorhanden."}
        src = Path(row["file_path"])
        if not src.exists():
            return {"error": "Originaldatei nicht gefunden."}
        ext = src.suffix or ""
        base = (row["title"] or src.stem).strip() or "Dokument"
        # ungültige Zeichen für Dateinamen entfernen
        base = re.sub(r'[\\/:*?"<>|]', "_", base)
        default_name = f"{base}{ext}"
        try:
            fd = getattr(webview, "FileDialog", None)
            dtype = fd.SAVE if fd else webview.SAVE_DIALOG
            dest = self.window.create_file_dialog(
                dtype, save_filename=default_name)
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Speichern-Dialog: {e}"}
        if not dest:
            return {"cancelled": True}
        path = dest if isinstance(dest, str) else dest[0]
        if ext and not path.lower().endswith(ext.lower()):
            path += ext
        try:
            shutil.copy(src, path)
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
        return {"ok": True, "path": path}

    def document(self, body):
        """Einzelnes Dokument mit Metadaten (für den Leser-Kopf)."""
        con = self._con()
        row = con.execute(
            "SELECT d.*, COUNT(p.id) AS passage_count FROM documents d "
            "LEFT JOIN passages p ON p.document_id = d.id "
            "WHERE d.id = ? GROUP BY d.id", (body["id"],)).fetchone()
        con.close()
        return dict(row) if row else {"error": "nicht gefunden"}

    def delete(self, body):
        con = self._con()
        con.execute("DELETE FROM documents WHERE id=?", (body["id"],))
        con.commit()
        con.close()
        return {"ok": True}

    def delete_documents(self, body):
        """Löscht mehrere ausgewählte Dokumente auf einmal."""
        ids = [int(i) for i in (body or {}).get("ids", []) if i is not None]
        if not ids:
            return {"ok": True, "deleted": 0}
        con = self._con()
        marks = ",".join("?" for _ in ids)
        cur = con.execute(
            f"DELETE FROM documents WHERE id IN ({marks})", ids)
        con.commit()
        deleted = cur.rowcount
        con.close()
        return {"ok": True, "deleted": deleted}

    def search(self, body):
        from dataclasses import asdict
        body = body or {}
        # Autorenfilter: Liste (mehrere) oder Einzelwert.
        author_filter = body.get("authors")
        if not author_filter:
            author_filter = body.get("author") or None
        elif isinstance(author_filter, list):
            author_filter = [a for a in author_filter if a] or None
        # Seitenweises Nachladen: limit + offset. Wir holen ein Ergebnis mehr
        # als angefragt, um zu erkennen, ob es noch weitere gibt.
        try:
            limit = max(1, min(int(body.get("limit") or 40), 200))
        except Exception:
            limit = 40
        try:
            offset = max(0, int(body.get("offset") or 0))
        except Exception:
            offset = 0
        con = self._con()
        if body.get("mode") == "terms":
            # Begriffssuche aus der Oberfläche (Gruppen + Ausschluss)
            from echo_engine.search import structured_search
            hits = structured_search(
                con, body.get("groups") or [],
                exclude=body.get("exclude") or [],
                limit=limit + 1, offset=offset, author=author_filter,
                document_id=body.get("document_id") or None)
        else:
            emb = self._embedder if body.get("semantic", True) else None
            hits = hybrid_search(
                con, body.get("q") or "", embedder=emb,
                limit=limit + 1, offset=offset, author=author_filter,
                document_id=body.get("document_id") or None)
        has_more = len(hits) > limit
        hits = hits[:limit]
        seen = {}
        for r in con.execute(
                "SELECT DISTINCT author FROM documents "
                "WHERE author IS NOT NULL AND author != ''"):
            for name in split_authors(r[0]):
                seen[name] = True
        authors = sorted(seen.keys())
        con.close()
        return {"hits": [asdict(h) for h in hits], "authors": authors,
                "offset": offset, "limit": limit, "has_more": has_more}


CORE = Core()

ROUTES = {
    ("GET", "/api/status"): CORE.status,
    ("POST", "/api/clear_jobs"): CORE.clear_jobs,
    ("GET", "/api/version"): CORE.version,
    ("POST", "/api/check_update"): CORE.check_update,
    ("POST", "/api/apply_update"): CORE.apply_update,
    ("POST", "/api/set_update_repo"): CORE.set_update_repo,
    ("GET", "/api/settings"): CORE.get_settings,
    ("POST", "/api/settings"): CORE.set_settings,
    ("GET", "/api/documents"): CORE.documents,
    ("POST", "/api/pick"): CORE.pick,
    ("POST", "/api/update"): CORE.update,
    ("POST", "/api/download_document"): CORE.download_document,
    ("POST", "/api/reindex"): CORE.reindex,
    ("POST", "/api/export_library"): CORE.export_library,
    ("POST", "/api/import_library"): CORE.import_library,
    ("POST", "/api/delete"): CORE.delete,
    ("POST", "/api/delete_documents"): CORE.delete_documents,
    ("POST", "/api/search"): CORE.search,
    ("POST", "/api/passage"): CORE.passage,
    ("POST", "/api/page"): CORE.page,
    ("POST", "/api/pages"): CORE.pages,
    ("POST", "/api/meta_get"): CORE.meta_get,
    ("POST", "/api/meta_set"): CORE.meta_set,
    ("GET", "/api/bookmarks"): CORE.bookmarks,
    ("POST", "/api/bookmark_add"): CORE.bookmark_add,
    ("POST", "/api/bookmark_toggle"): CORE.bookmark_toggle,
    ("POST", "/api/bookmark_delete"): CORE.bookmark_delete,
    ("POST", "/api/bookmark_note"): CORE.bookmark_note,
    ("POST", "/api/document"): CORE.document,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keine Request-Logs im Terminal
        pass

    def _send(self, code: int, payload: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/page_image"):
            self._page_image()
            return
        fn = ROUTES.get(("GET", self.path))
        if fn:
            try:
                self._json(fn())
            except Exception as e:
                traceback.print_exc()
                self._json({"error": str(e)}, 500)
        else:
            self._json({"error": "not found"}, 404)

    def _page_image(self):
        """Rendert eine PDF-Seite als Bild (Originalansicht im Leser)."""
        import urllib.parse
        try:
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1])
            doc_id = int(qs["doc"][0])
            page_no = int(qs["page"][0])
            con = CORE._con()
            row = con.execute("SELECT file_path, file_type FROM documents "
                              "WHERE id=?", (doc_id,)).fetchone()
            con.close()
            if not row or row["file_type"] != "pdf" or \
                    not row["file_path"] or not os.path.exists(row["file_path"]):
                self._json({"error": "kein Originalbild verfügbar"}, 404)
                return
            import fitz
            with fitz.open(row["file_path"]) as doc:
                page = doc[page_no - 1]
                png = page.get_pixmap(dpi=150).tobytes("png")
            self._send(200, png, "image/png")
        except Exception as e:
            traceback.print_exc()
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        if self.path == "/api/upload":
            # Rohdaten-Upload (Drag&Drop): Dateiname im Header
            try:
                import urllib.parse
                name = urllib.parse.unquote(
                    self.headers.get("X-Filename") or "datei")
                length = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(length)
                self._json(CORE.upload(name, data))
            except Exception as e:
                traceback.print_exc()
                self._json({"error": str(e)}, 500)
            return
        fn = ROUTES.get(("POST", self.path))
        if not fn:
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        try:
            self._json(fn(body))
        except Exception as e:
            traceback.print_exc()
            self._json({"error": str(e)}, 500)


def main():
    # Freien Port auf localhost finden
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    CORE.window = webview.create_window(
        "AICP Research", f"http://127.0.0.1:{port}/",
        width=1200, height=800, min_size=(900, 600))
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    main()
