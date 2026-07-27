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


def test_bezeichnung_aus_kennung():
    """Alle Kennungsformen der Quelle ergeben eine zitierfähige Angabe."""
    from echo_engine.shamela_import import seiten_bezeichnung as b
    assert b(1, 441, "V01P441") == "ج1 ص441"
    assert b(None, 32, "P032") == "ص32"
    assert b(None, 5, "المقدمة_P005") == "ص5"
    assert b(43, 1, "43:1") == "ج43 ص1"          # Koran: Sure und Vers
    # Fehlt die Seitennummer, bleibt die Rohkennung – lieber das als nichts.
    assert b("", "", "V01P441") == "صV01P441"
    assert b(None, None, None) is None
    assert b(2, 0, "V02P000") == "ج2 ص0"         # Seite 0 ist eine Angabe
    print("ok  test_bezeichnung_aus_kennung")


def test_mehrbaendig_landet_richtig():
    """Zwei Bände mit denselben Druckseiten – genau die Falle.

    Ohne getrennte Blattnummer bräche hier UNIQUE(document_id, page_no),
    und die Druckseiten wären nicht mehr auseinanderzuhalten.
    """
    from echo_engine.shamela_import import blaetter_zu_seiten

    blaetter = [{"seq": i + 1, "part": band, "page_num": s,
                 "page_str": f"V0{band}P00{s}", "text": RUMPF + f" علامة {band}{s}"}
                for i, (band, s) in enumerate(
                    [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)])]
    seiten = blaetter_zu_seiten(blaetter)
    con = connect(":memory:")
    doc = index_pages(con, seiten, "Mehrbändiges Werk", "Autor",
                      file_type="shamela", reliability="shamela",
                      source_key="shamela:1", embed_semantic=False)

    zeilen = con.execute(
        "SELECT page_no, page_label, page_key FROM pages WHERE document_id=? "
        "ORDER BY page_no", (doc,)).fetchall()
    assert [z["page_no"] for z in zeilen] == [1, 2, 3, 4, 5, 6], \
        "Blattnummer muss lückenlos sein"
    assert [z["page_label"] for z in zeilen] == [
        "ج1 ص1", "ج1 ص2", "ج1 ص3", "ج2 ص1", "ج2 ص2", "ج2 ص3"]
    assert [z["page_key"] for z in zeilen][3] == "V02P001"
    d = con.execute("SELECT reliability, source_key, embed_semantic, file_type "
                    "FROM documents WHERE id=?", (doc,)).fetchone()
    assert d["reliability"] == "shamela" and d["source_key"] == "shamela:1"
    assert d["embed_semantic"] == 0 and d["file_type"] == "shamela"
    print("ok  test_mehrbaendig_landet_richtig")


def test_lueckenpruefung():
    """Eine Lücke in der Blattfolge des Servers muss auffallen."""
    from echo_engine.shamela_import import folge_ist_lueckenlos
    assert folge_ist_lueckenlos([{"seq": 1}, {"seq": 2}, {"seq": 3}])
    assert folge_ist_lueckenlos([{"seq": 41}, {"seq": 42}], versatz=40)
    assert not folge_ist_lueckenlos([{"seq": 1}, {"seq": 3}])
    assert not folge_ist_lueckenlos([{"seq": 2}, {"seq": 3}])
    assert not folge_ist_lueckenlos([{"seq": None}])
    print("ok  test_lueckenpruefung")


def test_blockweise_anhaengen():
    """Blockweise übernommen muss dasselbe ergeben wie alles auf einmal."""
    from echo_engine.indexer import append_pages
    from echo_engine.shamela_import import blaetter_zu_seiten

    blaetter = [{"seq": i, "part": 1, "page_num": i, "page_str": f"V01P{i:03d}",
                 "text": RUMPF + f" علامة {i}"} for i in range(1, 10)]

    ganz = connect(":memory:")
    d1 = index_pages(ganz, blaetter_zu_seiten(blaetter), "Buch", "Autor",
                     file_type="shamela", reliability="shamela")

    stueck = connect(":memory:")
    d2 = index_pages(stueck, blaetter_zu_seiten(blaetter[:3]), "Buch", "Autor",
                     file_type="shamela", reliability="shamela")
    append_pages(stueck, d2, blaetter_zu_seiten(blaetter[3:6], versatz=3))
    n = append_pages(stueck, d2, blaetter_zu_seiten(blaetter[6:], versatz=6))
    assert n == 9, n

    def bild(con, doc):
        s = con.execute("SELECT page_no, text, page_label, page_key FROM pages "
                        "WHERE document_id=? ORDER BY page_no", (doc,)).fetchall()
        p = con.execute("SELECT idx, page_from, page_to, text FROM passages "
                        "WHERE document_id=? ORDER BY idx", (doc,)).fetchall()
        return [tuple(r) for r in s], [tuple(r) for r in p]

    s1, p1 = bild(ganz, d1)
    s2, p2 = bild(stueck, d2)
    assert s1 == s2, "Seiten unterscheiden sich"
    assert p1 == p2, "Passagen unterscheiden sich (laufende Nummer?)"
    assert [r[0] for r in p2] == list(range(len(p2))), \
        "laufende Nummer der Passagen ist nicht lückenlos"
    assert len(search(stueck, "علامة")) == len(search(ganz, "علامة"))
    print("ok  test_blockweise_anhaengen")


def test_uebernommene_buecher_bleiben_wortwoertlich():
    """Die Absatz-Nachbesserung darf übernommene Bücher nicht anfassen."""
    from echo_engine.indexer import ensure_text_layout_version

    con = connect(":memory:")
    roh = "سطر أول\nسطر ثان   بمسافات   كثيرة\n\n\nسطر ثالث"
    lokal = index_pages(con, [(1, roh)], "Eigenes Buch")
    fremd = index_pages(con, [(1, roh, "ج1 ص1", "V01P001")], "Übernommen",
                        file_type="shamela", reliability="shamela")
    ensure_text_layout_version(con)
    t_fremd = con.execute("SELECT text FROM pages WHERE document_id=?",
                          (fremd,)).fetchone()[0]
    assert t_fremd == roh, "übernommenes Buch wurde nachbearbeitet"
    _ = lokal
    print("ok  test_uebernommene_buecher_bleiben_wortwoertlich")


if __name__ == "__main__":
    test_bestehende_buecher_unveraendert()
    test_migration_alter_bibliothek()
    test_migration_ist_wiederholbar()
    test_bezeichnung_aus_kennung()
    test_mehrbaendig_landet_richtig()
    test_lueckenpruefung()
    test_blockweise_anhaengen()
    test_uebernommene_buecher_bleiben_wortwoertlich()
    print("\nAlle Tests bestanden.")
