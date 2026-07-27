# -*- coding: utf-8 -*-
"""Tests für übernommene Online-Bücher: Seitenbezeichnung und Blattnummern.

Aus der Online-Sammlung übernommene Bücher tragen Bandangaben („ج1 ص441").
Lokal ist eine Seite dagegen eine Ganzzahl, und der Leser setzt eine
lückenlose Reihe voraus. Deshalb zählt intern eine Blattnummer, und die echte
Druckseite kommt als eigene Bezeichnung mit.

Diese Tests sichern beides ab – vor allem aber, dass sich BESTEHENDE Bücher
kein bisschen anders verhalten als vorher.

Aufruf:  python3 engine/tests/test_shamela_pages.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine import connect, index_pages, search                # noqa: E402

# Lang genug, damit der Chunker die Seite nicht als Fragment verwirft.
RUMPF = ("هذا نص طويل بما يكفي كي لا يسقط المقطع من الفهرس، وفيه كلام معاد "
         "لبلوغ الطول المطلوب في كل صفحة من صفحات الكتاب. " * 3)


def test_bestehende_buecher_unveraendert():
    """Ein normal eingelesenes Buch trägt keine Bezeichnung – wie bisher.

    Bricht dieser Test, ist die Rückwärtsverträglichkeit verletzt: dann
    zeigte die App bei alten Büchern plötzlich etwas anderes an.
    """
    con = connect(":memory:")
    doc = index_pages(con, [(1, RUMPF + " كلمة زنجبيل"),
                            (2, RUMPF + " كلمة قرفة")], "Altes Buch", "Autor")
    zeilen = con.execute(
        "SELECT page_no, page_label, page_key FROM pages WHERE document_id=? "
        "ORDER BY page_no", (doc,)).fetchall()
    assert [z["page_no"] for z in zeilen] == [1, 2]
    assert all(z["page_label"] is None for z in zeilen), "Bezeichnung erfunden"
    assert all(z["page_key"] is None for z in zeilen)
    d = con.execute("SELECT reliability, source_key, embed_semantic "
                    "FROM documents WHERE id=?", (doc,)).fetchone()
    assert d["reliability"] == "sicher", d["reliability"]
    assert d["source_key"] is None
    assert d["embed_semantic"] == 1, "Bedeutungssuche darf nicht abgeschaltet sein"
    treffer = search(con, "زنجبيل")
    assert len(treffer) == 1 and treffer[0].page_from == 1
    print("ok  test_bestehende_buecher_unveraendert")


def test_migration_alter_bibliothek():
    """Eine Bibliothek im alten Schema wird ergänzt, ohne etwas zu verlieren."""
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "alt.db")
        # Bewusst das ALTE Schema von Hand anlegen – ohne die neuen Spalten.
        alt = sqlite3.connect(pfad)
        alt.executescript("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT,
                file_path TEXT, file_type TEXT, page_count INTEGER,
                needs_ocr INTEGER DEFAULT 0, status TEXT DEFAULT 'done',
                error TEXT, reliability TEXT DEFAULT 'sicher',
                engine TEXT DEFAULT '', created_at TEXT);
            CREATE TABLE pages (
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
                page_no INTEGER NOT NULL, text TEXT NOT NULL,
                UNIQUE(document_id, page_no));
            INSERT INTO documents (id, title, author, page_count)
                VALUES (1, 'Altes Buch', 'Autor', 1);
            INSERT INTO pages (document_id, page_no, text)
                VALUES (1, 7, 'نص قديم محفوظ');
        """)
        alt.commit()
        alt.close()

        con = connect(pfad)          # hier läuft die Migration
        spalten = {r[1] for r in con.execute("PRAGMA table_info(pages)")}
        assert {"page_label", "page_key"} <= spalten, spalten
        spalten = {r[1] for r in con.execute("PRAGMA table_info(documents)")}
        assert {"source_key", "embed_semantic"} <= spalten, spalten
        # Die vorhandene Zeile muss unangetastet sein.
        z = con.execute("SELECT page_no, text, page_label FROM pages").fetchone()
        assert z["page_no"] == 7 and z["text"] == "نص قديم محفوظ"
        assert z["page_label"] is None
        assert con.execute("SELECT title FROM documents").fetchone()[0] == \
            "Altes Buch"
        con.close()
    print("ok  test_migration_alter_bibliothek")


def test_migration_ist_wiederholbar():
    """Zweimal öffnen darf nicht scheitern (Spalte bereits vorhanden)."""
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "neu.db")
        connect(pfad).close()
        connect(pfad).close()
    print("ok  test_migration_ist_wiederholbar")


if __name__ == "__main__":
    test_bestehende_buecher_unveraendert()
    test_migration_alter_bibliothek()
    test_migration_ist_wiederholbar()
    print("\nAlle Tests bestanden.")
