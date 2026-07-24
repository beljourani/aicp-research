# -*- coding: utf-8 -*-
"""Buchkennung und Seitenordnung für die Shamela-Suche.

Reine Datenlogik – ohne FastAPI, ohne Qdrant, ohne Netz. Dadurch lässt sie
sich überall testen (`server/test_meta.py`), auch dort, wo der Server selbst
nicht laufen kann.

Hintergrund: Der Datensatz `Maktabati/shamela-vectors` liefert je Abschnitt
nur `title`, `author` und `page` – es gibt darin KEINE `book_id`, `page_id`
oder `sequence_num`. Die Buchkennung wird deshalb stabil aus Titel+Autor
abgeleitet, die Lesereihenfolge aus der Seitenkennung ("V01P441" =
Band 1, Seite 441).

WICHTIG: `seq` ist eine rein INTERNE Blattnummer zum Blättern. Angezeigt wird
immer die echte Druckseite (part/page_num) – die wird hier nur aus der
Quellangabe dekodiert, niemals neu vergeben.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading

SCHEMA = """
    CREATE TABLE IF NOT EXISTS book_index (
        book_id INTEGER PRIMARY KEY,
        title TEXT, author TEXT, source TEXT,
        page_count INTEGER DEFAULT 0,
        indexed INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS page_index (
        book_id INTEGER, seq INTEGER, page_str TEXT,
        part INTEGER, page_num INTEGER,
        PRIMARY KEY (book_id, seq)
    );
    CREATE INDEX IF NOT EXISTS idx_page_str ON page_index(book_id, page_str);
"""


def book_id(title: str | None, author: str | None) -> int:
    """Stabile, positive Buchkennung aus Titel+Autor (48 Bit, JSON-sicher)."""
    key = f"{(title or '').strip()}\x00{(author or '').strip()}"
    return int.from_bytes(
        hashlib.blake2b(key.encode("utf-8"), digest_size=6).digest(), "big")


def parse_page(page_str: str | None) -> tuple[int | None, int | None]:
    """Zerlegt eine Seitenkennung in (Band, Druckseite).

    Bekannte Formen: "V01P441" (Band+Seite), "P032" (nur Seite),
    "43:1" (Koran: Sure:Vers), "المقدمة_P005" (benannter Vorspann + Seite).
    Unbekanntes ergibt (None, None) – die Seite behält dann ihr Rohlabel.
    """
    s = (page_str or "").strip()
    if not s:
        return None, None
    m = re.fullmatch(r"[Vv](\d+)[Pp](\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"[Pp](\d+)", s)
    if m:
        return None, int(m.group(1))
    m = re.fullmatch(r"(\d+):(\d+)", s)          # Koran: Sure:Vers
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"[Pp](\d+)\s*$", s)           # z. B. "المقدمة_P005"
    if m:
        return None, int(m.group(1))
    return None, None


def page_sort_key(page_str: str) -> tuple:
    """Sortierschlüssel für die Lesereihenfolge innerhalb eines Buches."""
    part, num = parse_page(page_str)
    # Seiten ohne erkennbare Zahl hinten anstellen, aber stabil (nach Rohtext).
    return (part or 0, 0 if num is None else 1, num or 0, page_str or "")


def ensure_schema(con: sqlite3.Connection, wal: bool = True) -> None:
    """Legt die Tabellen für den Seitenindex an. Eigene Tabellennamen, damit
    die ungenutzten Alt-Tabellen aus dem Import unangetastet bleiben."""
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.commit()


def remember_book(con: sqlite3.Connection, bid: int, title: str | None,
                  author: str | None, source: str | None) -> None:
    """Merkt sich Titel/Autor zu einer Buchkennung – nötig, um aus der Kennung
    später wieder den Qdrant-Filter bauen zu können."""
    con.execute("INSERT OR IGNORE INTO book_index (book_id,title,author,source) "
                "VALUES (?,?,?,?)", (bid, title, author, source))


_lock = threading.Lock()


def ensure_book_index(con: sqlite3.Connection, bid: int, fetch) -> int:
    """Baut den Seitenindex eines Buches beim ersten Öffnen auf (einmalig).

    `fetch(title, author)` liefert alle Seitenkennungen des Buches. Ergebnis
    ist eine dichte Blattnummerierung 1..N in Lesereihenfolge. Rückgabe ist die
    Seitenzahl; 0 bedeutet „Buch unbekannt oder ohne Seiten".
    """
    row = con.execute("SELECT title, author, indexed, page_count FROM book_index "
                      "WHERE book_id=?", (bid,)).fetchone()
    if not row:
        return 0
    if row["indexed"]:
        return row["page_count"] or 0
    with _lock:
        # Nach dem Warten erneut prüfen – ein paralleler Aufruf war evtl. schneller.
        row = con.execute("SELECT title, author, indexed, page_count FROM "
                          "book_index WHERE book_id=?", (bid,)).fetchone()
        if row["indexed"]:
            return row["page_count"] or 0
        pages = sorted({str(p) for p in fetch(row["title"], row["author"]) if p},
                       key=page_sort_key)
        rows = []
        for seq, pg in enumerate(pages, start=1):
            part, num = parse_page(pg)
            rows.append((bid, seq, pg, part, num))
        con.execute("DELETE FROM page_index WHERE book_id=?", (bid,))
        con.executemany("INSERT INTO page_index (book_id,seq,page_str,part,"
                        "page_num) VALUES (?,?,?,?,?)", rows)
        con.execute("UPDATE book_index SET indexed=1, page_count=? WHERE book_id=?",
                    (len(rows), bid))
        con.commit()
        return len(rows)


def seq_for_page(con: sqlite3.Connection, bid: int, page_str: str) -> int | None:
    """Interne Blattnummer zu einer Seitenkennung (None, wenn unbekannt)."""
    row = con.execute("SELECT seq FROM page_index WHERE book_id=? AND page_str=?",
                      (bid, page_str)).fetchone()
    return row["seq"] if row else None
