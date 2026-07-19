# -*- coding: utf-8 -*-
"""Indexierung: Datei -> Seiten -> Passagen -> Volltextindex."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .chunker import chunk_pages
from .extract import extract
from .normalize import to_index_forms

# Bei Änderungen an Normalisierung/Stemming hochzählen -> der Volltext-
# index wird beim nächsten App-Start automatisch neu aufgebaut (schnell,
# ohne die Dokumente neu einzulesen).
STEM_VERSION = 2


def ensure_index_version(con: sqlite3.Connection) -> bool:
    """Baut den FTS-Index neu auf, wenn sich das Stemming geändert hat.
    Liefert True, wenn ein Neuaufbau stattgefunden hat."""
    con.execute("CREATE TABLE IF NOT EXISTS meta "
                "(key TEXT PRIMARY KEY, value TEXT)")
    row = con.execute(
        "SELECT value FROM meta WHERE key='stem_version'").fetchone()
    if row and row[0] == str(STEM_VERSION):
        return False
    # Spezialbefehl: contentless FTS5-Tabellen komplett leeren
    con.execute("INSERT INTO passages_fts (passages_fts) VALUES ('delete-all')")
    for pid, text in con.execute("SELECT id, text FROM passages"):
        norm, stems = to_index_forms(text)
        con.execute(
            "INSERT INTO passages_fts (rowid, norm, stems) VALUES (?,?,?)",
            (pid, norm, stems))
    con.execute("INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('stem_version', ?)", (str(STEM_VERSION),))
    con.commit()
    return True


def index_document(con: sqlite3.Connection, path: str | Path,
                   title: str | None = None, author: str | None = None,
                   force_ocr: bool = False, progress=None) -> int:
    """Verarbeitet eine Datei vollständig. Liefert die Dokument-ID."""
    p = Path(path)
    res = extract(p, force_ocr=force_ocr, progress=progress)
    cur = con.execute(
        "INSERT INTO documents (title, author, file_path, file_type, "
        "page_count, needs_ocr, status, reliability, engine) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (title or p.stem, author, str(p), p.suffix.lstrip("."),
         len(res.pages), int(res.needs_ocr), "done",
         getattr(res, "reliability", "sicher"), getattr(res, "engine", "")),
    )
    doc_id = cur.lastrowid
    _index_pages(con, doc_id, res.pages)
    con.commit()
    return doc_id


def index_pages(con: sqlite3.Connection, pages: list[tuple[int, str]],
                title: str, author: str | None = None) -> int:
    """Indexiert bereits extrahierte Seiten (z.B. für Tests)."""
    cur = con.execute(
        "INSERT INTO documents (title, author, file_type, page_count) "
        "VALUES (?,?,?,?)", (title, author, "raw", len(pages)))
    doc_id = cur.lastrowid
    _index_pages(con, doc_id, pages)
    con.commit()
    return doc_id


def _index_pages(con: sqlite3.Connection, doc_id: int,
                 pages: list[tuple[int, str]]) -> None:
    con.executemany(
        "INSERT INTO pages (document_id, page_no, text) VALUES (?,?,?)",
        [(doc_id, no, text) for no, text in pages])
    for passage in chunk_pages(pages):
        norm, stems = to_index_forms(passage.text)
        cur = con.execute(
            "INSERT INTO passages (document_id, idx, page_from, page_to, text) "
            "VALUES (?,?,?,?,?)",
            (doc_id, passage.idx, passage.page_from, passage.page_to,
             passage.text))
        con.execute(
            "INSERT INTO passages_fts (rowid, norm, stems) VALUES (?,?,?)",
            (cur.lastrowid, norm, stems))
