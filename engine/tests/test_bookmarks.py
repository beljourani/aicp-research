# -*- coding: utf-8 -*-
"""Tests für Lesezeichen mit zwei Quellen (lokal + Shamela online).

Geprüft wird vor allem die leichte Migration: eine Bibliothek, die noch die
alte bookmarks-Tabelle hat, muss die neuen Spalten bekommen, ohne dass
vorhandene Lesezeichen verloren gehen.

Aufruf:  python3 engine/tests/test_bookmarks.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from echo_engine import db                                       # noqa: E402

# So sah die Tabelle vor der Erweiterung aus.
ALT = """
CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER,
    passage_id INTEGER,
    doc_title TEXT NOT NULL,
    page_no INTEGER NOT NULL,
    snippet TEXT NOT NULL,
    note TEXT DEFAULT '',
    terms TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def test_neue_spalten_vorhanden():
    """Eine frische Bibliothek hat alle Spalten."""
    con = db.connect(":memory:")
    spalten = {r[1] for r in con.execute("PRAGMA table_info(bookmarks)")}
    for s in ("source", "book_key", "page_str", "page_label", "doc_author"):
        assert s in spalten, f"Spalte {s} fehlt"
    con.close()
    print("ok  test_neue_spalten_vorhanden")


def test_migration_alte_bibliothek():
    """Alte Bibliothek: Spalten kommen dazu, Lesezeichen bleiben erhalten."""
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "alt.db")
        con = sqlite3.connect(pfad)
        con.executescript(ALT)
        con.execute("INSERT INTO bookmarks (document_id,passage_id,doc_title,"
                    "page_no,snippet) VALUES (7,3,'Altes Buch',42,'Textstelle')")
        con.commit()
        con.close()

        # Öffnen über die App-Verbindung -> Migration läuft
        con = db.connect(pfad)
        spalten = {r[1] for r in con.execute("PRAGMA table_info(bookmarks)")}
        for s in ("source", "book_key", "page_str", "page_label", "doc_author"):
            assert s in spalten, f"Spalte {s} fehlt nach Migration"
        rows = con.execute("SELECT * FROM bookmarks").fetchall()
        assert len(rows) == 1, "Vorhandenes Lesezeichen ging verloren"
        assert rows[0]["doc_title"] == "Altes Buch"
        assert rows[0]["page_no"] == 42
        assert rows[0]["document_id"] == 7
        con.close()
    print("ok  test_migration_alte_bibliothek")


def test_migration_ist_wiederholbar():
    """Mehrfaches Öffnen darf nicht scheitern (Spalte doppelt anlegen)."""
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "x.db")
        for _ in range(3):
            con = db.connect(pfad)
            con.close()
    print("ok  test_migration_ist_wiederholbar")


def test_beide_quellen_nebeneinander():
    """Lokale und Online-Lesezeichen stören sich nicht."""
    con = db.connect(":memory:")
    con.execute("INSERT INTO bookmarks (document_id,passage_id,doc_title,"
                "page_no,snippet,source) VALUES (1,2,'Lokales Buch',5,'abc','local')")
    con.execute("INSERT INTO bookmarks (doc_title,page_no,snippet,source,"
                "book_key,page_str,page_label,doc_author) "
                "VALUES ('Online-Buch',479,'xyz','shamela',12345,'V23P005',"
                "'ج23 ص5','Autor')")
    con.commit()
    lokal = con.execute("SELECT * FROM bookmarks WHERE source='local'").fetchall()
    online = con.execute("SELECT * FROM bookmarks WHERE source='shamela'").fetchall()
    assert len(lokal) == 1 and len(online) == 1
    assert online[0]["document_id"] is None, "Online-Eintrag braucht keine document_id"
    assert online[0]["book_key"] == 12345
    assert online[0]["page_str"] == "V23P005"
    assert online[0]["page_label"] == "ج23 ص5"
    con.close()
    print("ok  test_beide_quellen_nebeneinander")


if __name__ == "__main__":
    test_neue_spalten_vorhanden()
    test_migration_alte_bibliothek()
    test_migration_ist_wiederholbar()
    test_beide_quellen_nebeneinander()
    print("\nAlle Tests bestanden.")
