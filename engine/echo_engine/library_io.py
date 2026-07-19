# -*- coding: utf-8 -*-
"""Bibliothek exportieren und importieren.

Eine exportierte Bibliothek ist EINE Datei (*.echolib – im Kern ein ZIP):
  archive.db        – die komplette Datenbank (Texte, Seiten, Vektoren)
  files/<id>.<ext>  – die Originaldateien (für Original-Ansicht & Neu-Einlesen)
  manifest.json     – Version + Inhaltsübersicht

Der Empfänger importiert die Datei und hat sofort die fertige, durchsuchbare
Bibliothek – ohne Word, ohne OCR, ohne Neuverarbeitung. Die Seitenzahlen
(inkl. der von Word exakt berechneten) kommen 1:1 mit.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from .db import connect
from .normalize import to_index_forms
from .semantic import ensure_vector_schema

FORMAT_VERSION = 1


def export_library(db_path: Path, out_file: Path,
                   doc_ids: list[int] | None = None,
                   progress=None) -> dict:
    """Packt die Bibliothek (oder nur ausgewählte Bücher) in eine Datei.

    doc_ids=None  -> gesamte Bibliothek
    doc_ids=[...] -> nur diese Dokumente
    """
    con = connect(db_path)
    ensure_vector_schema(con)
    if doc_ids:
        marks = ",".join("?" for _ in doc_ids)
        docs = con.execute(
            "SELECT id, title, file_path, file_type FROM documents "
            f"WHERE id IN ({marks}) ORDER BY id", doc_ids).fetchall()
    else:
        docs = con.execute("SELECT id, title, file_path, file_type "
                           "FROM documents ORDER BY id").fetchall()
    keep = {d["id"] for d in docs}
    con.close()

    out_file = Path(out_file)
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        # 1. Datenbank kopieren (WAL zusammenführen)
        db_copy = tmpd / "archive.db"
        _copy_sqlite(db_path, db_copy)

        # 1b. Bei Auswahl: nicht gewählte Bücher aus der Kopie entfernen.
        if doc_ids:
            c = connect(db_copy)
            marks = ",".join("?" for _ in keep)
            c.execute(f"DELETE FROM documents WHERE id NOT IN ({marks})",
                      list(keep))              # FK-Kaskade räumt Seiten/Passagen
            c.execute("INSERT INTO passages_fts (passages_fts) "
                      "VALUES ('delete-all')")  # verwaiste Index-Reste weg
            c.commit()
            c.close()

        # 2. Originaldateien einsammeln
        files_dir = tmpd / "files"
        files_dir.mkdir()
        included, missing = 0, 0
        file_map = {}
        for i, d in enumerate(docs):
            src = Path(d["file_path"]) if d["file_path"] else None
            if progress:
                progress(f"Bücher werden gepackt … {i + 1}/{len(docs)}")
            if src and src.exists():
                ext = src.suffix or ("." + (d["file_type"] or "bin"))
                name = f"{d['id']}{ext}"
                shutil.copy(src, files_dir / name)
                file_map[str(d["id"])] = name
                included += 1
            else:
                missing += 1

        manifest = {
            "format": FORMAT_VERSION,
            "documents": len(docs),
            "files_included": included,
            "files_missing": missing,
            "file_map": file_map,
        }
        (tmpd / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1))

        # 3. Alles in eine ZIP-Datei
        if progress:
            progress("Datei wird geschrieben …")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_copy, "archive.db")
            z.write(tmpd / "manifest.json", "manifest.json")
            for f in files_dir.iterdir():
                z.write(f, f"files/{f.name}")

    return {"documents": len(docs), "files_included": included,
            "files_missing": missing, "path": str(out_file)}


def import_library(db_path: Path, in_file: Path, files_target: Path,
                   progress=None) -> dict:
    """Fügt die Bücher aus einer exportierten Datei zur aktuellen
    Bibliothek hinzu (bestehende bleiben erhalten)."""
    in_file = Path(in_file)
    files_target = Path(files_target)
    files_target.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        with zipfile.ZipFile(in_file) as z:
            z.extractall(tmpd)

        manifest = json.loads((tmpd / "manifest.json").read_text())
        if manifest.get("format") != FORMAT_VERSION:
            raise ValueError("Nicht unterstütztes Bibliotheks-Format.")

        src = connect(tmpd / "archive.db")
        ensure_vector_schema(src)
        dst = connect(db_path)
        ensure_vector_schema(dst)

        file_map = manifest.get("file_map", {})
        added, skipped = 0, 0
        docs = src.execute("SELECT * FROM documents ORDER BY id").fetchall()
        cols = [c[0] for c in src.execute(
            "SELECT * FROM documents LIMIT 1").description]

        for i, d in enumerate(docs):
            if progress:
                progress(f"Bücher werden importiert … {i + 1}/{len(docs)}")
            old_id = d["id"]

            # Doppelte vermeiden: gleicher Titel + Seitenzahl schon da?
            dup = dst.execute(
                "SELECT 1 FROM documents WHERE title=? AND page_count=?",
                (d["title"], d["page_count"])).fetchone()
            if dup:
                skipped += 1
                continue

            # Originaldatei an den Zielort kopieren
            new_path = None
            fname = file_map.get(str(old_id))
            if fname and (tmpd / "files" / fname).exists():
                dest = files_target / fname
                if dest.exists():
                    dest = files_target / f"imp-{old_id}-{fname}"
                shutil.copy(tmpd / "files" / fname, dest)
                new_path = str(dest)

            # Dokument-Zeile übernehmen (ohne id, mit neuem Pfad)
            data = {k: d[k] for k in cols if k != "id"}
            if new_path:
                data["file_path"] = new_path
            keys = ", ".join(data.keys())
            qs = ", ".join("?" for _ in data)
            cur = dst.execute(
                f"INSERT INTO documents ({keys}) VALUES ({qs})",
                list(data.values()))
            new_id = cur.lastrowid

            # Seiten übernehmen
            for pg in src.execute(
                    "SELECT page_no, text FROM pages WHERE document_id=?",
                    (old_id,)):
                dst.execute("INSERT INTO pages (document_id, page_no, text) "
                            "VALUES (?,?,?)", (new_id, pg["page_no"],
                                               pg["text"]))

            # Passagen + Volltextindex + Vektoren übernehmen
            for ps in src.execute(
                    "SELECT * FROM passages WHERE document_id=?", (old_id,)):
                cur2 = dst.execute(
                    "INSERT INTO passages (document_id, idx, page_from, "
                    "page_to, text) VALUES (?,?,?,?,?)",
                    (new_id, ps["idx"], ps["page_from"], ps["page_to"],
                     ps["text"]))
                new_pid = cur2.lastrowid
                # Volltextindex aus dem Text NEU berechnen. (Aus der
                # contentless FTS5-Tabelle lässt er sich nicht zurücklesen.)
                norm, stems = to_index_forms(ps["text"])
                dst.execute("INSERT INTO passages_fts (rowid, norm, stems)"
                            " VALUES (?,?,?)", (new_pid, norm, stems))
                vec = src.execute(
                    "SELECT vec FROM passage_vectors WHERE passage_id=?",
                    (ps["id"],)).fetchone()
                if vec:
                    dst.execute("INSERT INTO passage_vectors (passage_id, vec)"
                                " VALUES (?,?)", (new_pid, vec["vec"]))
            added += 1

        dst.commit()
        dst.close()
        src.close()

    return {"added": added, "skipped": skipped,
            "files_missing": manifest.get("files_missing", 0)}


def _copy_sqlite(src: Path, dst: Path) -> None:
    """Sichere Kopie einer SQLite-Datei (inkl. offener WAL-Änderungen)."""
    con = sqlite3.connect(str(src))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    con.close()
    # Über die SQLite-Backup-API kopieren – konsistent auch bei Zugriff.
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    s.close()
    d.close()
