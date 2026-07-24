# -*- coding: utf-8 -*-
"""Tests für den Seitenindex des Shamela-Servers (ohne Qdrant/Netz).

Geprüft wird die Logik, die aus den vorhandenen Payload-Feldern
(title/author/page) eine Buchkennung und eine dichte Lesereihenfolge macht.

Aufruf:  python3 server/test_meta.py
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meta_index as mi


def _mem_con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    # WAL geht im Speicher nicht – daher ohne das PRAGMA anlegen.
    mi.ensure_schema(con, wal=False)
    return con


def test_parse_page():
    """Seitenkennungen werden in Band + Druckseite zerlegt."""
    assert mi.parse_page("V01P441") == (1, 441)
    assert mi.parse_page("V23P005") == (23, 5)
    assert mi.parse_page("P032") == (None, 32)
    assert mi.parse_page("43:1") == (43, 1)          # Koran: Sure:Vers
    assert mi.parse_page("المقدمة_P005") == (None, 5)
    assert mi.parse_page("") == (None, None)
    assert mi.parse_page(None) == (None, None)
    assert mi.parse_page("ohne Zahl") == (None, None)
    print("ok  test_parse_page")


def test_book_id_stabil():
    """Gleiche Angaben -> gleiche Kennung; andere -> andere. Immer JSON-sicher."""
    a = mi.book_id("المدونة", "مالك بن أنس")
    b = mi.book_id("المدونة", "مالك بن أنس")
    c = mi.book_id("المدونة", "غيره")
    d = mi.book_id("كتاب آخر", "مالك بن أنس")
    assert a == b, "Kennung muss stabil sein"
    assert a != c and a != d, "Verschiedene Bücher -> verschiedene Kennung"
    assert 0 < a < 2 ** 53, "Kennung muss als JSON-Zahl sicher sein"
    # Leere Angaben dürfen nicht krachen
    assert mi.book_id(None, None) > 0
    print("ok  test_book_id_stabil")


def test_sortierung_lesereihenfolge():
    """Bände werden vor Seiten sortiert; V2P9 kommt nach V1P100."""
    seiten = ["V02P009", "V01P100", "V01P009", "P007", "V10P001", "V02P100"]
    sortiert = sorted(seiten, key=mi.page_sort_key)
    assert sortiert == ["P007", "V01P009", "V01P100", "V02P009",
                        "V02P100", "V10P001"], sortiert
    print("ok  test_sortierung_lesereihenfolge")


def test_index_dicht_und_vollstaendig():
    """Aus den Seitenkennungen entsteht eine lückenlose Ordnung 1..N."""
    con = _mem_con()
    bid = mi.book_id("Buch", "Autor")
    mi.remember_book(con, bid, "Buch", "Autor", "shamela")
    con.commit()

    roh = ["V01P010", "V01P002", "V02P001"]
    n = mi.ensure_book_index(con, bid, fetch=lambda t, a: roh)
    assert n == 3, n
    rows = con.execute("SELECT seq, page_str, part, page_num FROM page_index "
                       "WHERE book_id=? ORDER BY seq", (bid,)).fetchall()
    assert [r["seq"] for r in rows] == [1, 2, 3], "Ordnung muss dicht sein"
    assert [r["page_str"] for r in rows] == ["V01P002", "V01P010", "V02P001"]
    # Die echten Druckseiten bleiben erhalten (Produktversprechen!)
    assert [(r["part"], r["page_num"]) for r in rows] == [(1, 2), (1, 10), (2, 1)]
    print("ok  test_index_dicht_und_vollstaendig")


def test_index_nur_einmal():
    """Ein zweiter Aufruf baut nicht neu (Zwischenspeicher greift)."""
    con = _mem_con()
    bid = mi.book_id("Buch", "Autor")
    mi.remember_book(con, bid, "Buch", "Autor", "shamela")
    con.commit()
    aufrufe = []

    def fetch(t, a):
        aufrufe.append(1)
        return ["V01P001", "V01P002"]

    assert mi.ensure_book_index(con, bid, fetch=fetch) == 2
    assert mi.ensure_book_index(con, bid, fetch=fetch) == 2
    assert len(aufrufe) == 1, f"fetch wurde {len(aufrufe)}x gerufen"
    print("ok  test_index_nur_einmal")


def test_seite_findet_blattnummer():
    """Aus der Seitenkennung wird die interne Blattnummer gefunden."""
    con = _mem_con()
    bid = mi.book_id("Buch", "Autor")
    mi.remember_book(con, bid, "Buch", "Autor", "shamela")
    con.commit()
    mi.ensure_book_index(con, bid, fetch=lambda t, a: [
        "V01P001", "V01P002", "V01P003"])
    row = con.execute("SELECT seq FROM page_index WHERE book_id=? AND page_str=?",
                      (bid, "V01P002")).fetchone()
    assert row["seq"] == 2, row["seq"]
    fehlt = con.execute("SELECT seq FROM page_index WHERE book_id=? AND "
                        "page_str=?", (bid, "V09P999")).fetchone()
    assert fehlt is None, "Unbekannte Seite darf nichts liefern"
    print("ok  test_seite_findet_blattnummer")


def test_unbekanntes_buch():
    """Ein nicht gemerktes Buch liefert 0 statt eines Absturzes."""
    con = _mem_con()
    assert mi.ensure_book_index(con, 12345, fetch=lambda t, a: ["V01P001"]) == 0
    print("ok  test_unbekanntes_buch")


def test_verzeichnis_suche():
    """Bücher lassen sich nach Titelteil und Autor filtern."""
    con = _mem_con()
    mi.add_books(con, [
        ("صحيح البخاري", "البخاري", 900),
        ("صحيح مسلم", "مسلم", 800),
        ("الأدب المفرد", "البخاري", 100),
    ])
    alle = mi.find_books(con)
    assert len(alle) == 3
    assert alle[0]["title"] == "صحيح البخاري", "nach Umfang sortiert"
    # Titelteil
    treffer = mi.find_books(con, q="صحيح")
    assert len(treffer) == 2, treffer
    # Autor
    bukhari = mi.find_books(con, author="البخاري")
    assert len(bukhari) == 2, bukhari
    # Kennung stimmt mit der zentralen Ableitung überein
    assert bukhari[0]["book_id"] == mi.book_id(bukhari[0]["title"], "البخاري")
    # Seitenweise
    assert len(mi.find_books(con, limit=2)) == 2
    assert len(mi.find_books(con, limit=2, offset=2)) == 1
    print("ok  test_verzeichnis_suche")


def test_verzeichnis_status():
    """Der Aufbauzustand des Verzeichnisses wird gemerkt."""
    con = _mem_con()
    assert mi.catalog_ready(con) is False
    mi.set_catalog_state(con, "laeuft")
    assert mi.catalog_ready(con) is False
    mi.set_catalog_state(con, "fertig")
    assert mi.catalog_ready(con) is True
    print("ok  test_verzeichnis_status")


def test_autorenliste():
    """Autoren werden nach Buchzahl sortiert und lassen sich filtern."""
    con = _mem_con()
    con.executemany("INSERT INTO author_index (name,books,chunks) VALUES (?,?,?)",
                    [("ابن كثير", 12, 500), ("البخاري", 3, 900),
                     ("ابن تيمية", 40, 700)])
    con.commit()
    alle = mi.find_authors(con)
    assert [a["name"] for a in alle][0] == "ابن تيمية", alle
    assert len(mi.find_authors(con, q="ابن")) == 2
    assert len(mi.find_authors(con, limit=1)) == 1
    print("ok  test_autorenliste")


if __name__ == "__main__":
    test_parse_page()
    test_book_id_stabil()
    test_sortierung_lesereihenfolge()
    test_index_dicht_und_vollstaendig()
    test_index_nur_einmal()
    test_seite_findet_blattnummer()
    test_unbekanntes_buch()
    test_verzeichnis_suche()
    test_verzeichnis_status()
    test_autorenliste()
    print("\nAlle Tests bestanden.")
