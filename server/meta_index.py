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
    -- Verzeichnis aller Bücher/Autoren für die Filterlisten. Wird einmalig
    -- von build_catalog.py gefüllt (der Datensatz selbst bringt keine Listen mit).
    CREATE TABLE IF NOT EXISTS catalog (
        book_id INTEGER PRIMARY KEY, title TEXT, author TEXT,
        chunks INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_catalog_title ON catalog(title);
    CREATE INDEX IF NOT EXISTS idx_catalog_author ON catalog(author);
    CREATE TABLE IF NOT EXISTS author_index (
        name TEXT PRIMARY KEY, books INTEGER DEFAULT 0, chunks INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS build_state (key TEXT PRIMARY KEY, value TEXT);
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


# ------------------------------------------------------------- Verzeichnis ----
# Der Datensatz bringt keine Bücher-/Autorenlisten mit; sie werden einmalig
# aus Qdrant erhoben (build_catalog.py) und hier abgefragt.

def catalog_ready(con: sqlite3.Connection) -> bool:
    """Ob das Bücherverzeichnis fertig aufgebaut ist."""
    row = con.execute("SELECT value FROM build_state WHERE key='catalog'").fetchone()
    return bool(row and row["value"] == "fertig")


def set_catalog_state(con: sqlite3.Connection, value: str) -> None:
    con.execute("INSERT INTO build_state (key,value) VALUES ('catalog',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,))
    con.commit()


def add_books(con: sqlite3.Connection, rows: list[tuple]) -> None:
    """Trägt (title, author, chunks) ins Verzeichnis ein; Kennung wird abgeleitet."""
    con.executemany(
        "INSERT INTO catalog (book_id,title,author,chunks) VALUES (?,?,?,?) "
        "ON CONFLICT(book_id) DO UPDATE SET chunks=excluded.chunks",
        [(book_id(t, a), t, a, n) for t, a, n in rows])
    con.commit()


def book_row(con: sqlite3.Connection, bid: int) -> dict | None:
    """Titel/Autor zu einer Buchkennung – erst aus den bereits geöffneten
    Büchern, sonst aus dem Verzeichnis. So lässt sich auch ein Buch öffnen
    oder filtern, nach dem noch nie gesucht wurde."""
    row = con.execute("SELECT book_id, title, author FROM book_index "
                      "WHERE book_id=?", (bid,)).fetchone()
    if row:
        return dict(row)
    row = con.execute("SELECT book_id, title, author FROM catalog "
                      "WHERE book_id=?", (bid,)).fetchone()
    return dict(row) if row else None


def find_books(con: sqlite3.Connection, q: str = "", author: str | None = None,
               limit: int = 50, offset: int = 0) -> list[dict]:
    """Bücher im Verzeichnis suchen (Titelteil, optional nach Autor)."""
    where, args = [], []
    if q:
        where.append("title LIKE ?")
        args.append(f"%{q}%")
    if author:
        where.append("author = ?")
        args.append(author)
    sql = "SELECT book_id, title, author, chunks FROM catalog"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY chunks DESC, title LIMIT ? OFFSET ?"
    args += [limit, offset]
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def find_authors(con: sqlite3.Connection, q: str = "",
                 limit: int = 50) -> list[dict]:
    """Autorenliste aus dem Verzeichnis (nach Buchzahl absteigend)."""
    if q:
        rows = con.execute(
            "SELECT name, books, chunks FROM author_index WHERE name LIKE ? "
            "ORDER BY books DESC, name LIMIT ?", (f"%{q}%", limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT name, books, chunks FROM author_index "
            "ORDER BY books DESC, name LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
