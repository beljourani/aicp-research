# -*- coding: utf-8 -*-
"""SQLite-Schema und Verbindung.

Tabellen:
  documents  – ein Eintrag pro Datei (Titel, Autor, Pfad, Status)
  pages      – Rohtext pro Seite (Grundlage für Seitenzahlen)
  passages   – Suchabschnitte (Chunks) mit Seitenbereich
  passages_fts – FTS5-Volltextindex über zwei Felder:
                 norm  = normalisierter Text  (exaktere Treffer, höher gewichtet)
                 stems = gestemmter Text      (findet Konjugationen/Wurzeln)
  categories / document_categories – Sammlungen (n:m)
  authors / document_authors       – Autoren (n:m)
  meta       – kleine Schlüssel/Wert-Einstellungen
  bookmarks  – Lesezeichen (lokal und online)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
-- Bei gleichzeitigen Schreibzugriffen bis zu 60s warten statt
-- sofort mit "database is locked" abzubrechen.
PRAGMA busy_timeout=60000;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    file_path TEXT,
    file_type TEXT,            -- pdf | docx | txt
    page_count INTEGER,
    needs_ocr INTEGER DEFAULT 0,
    status TEXT DEFAULT 'done',-- queued|processing|done|error
    error TEXT,
    reliability TEXT DEFAULT 'sicher',  -- sicher|exakt|ungefähr
    engine TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,   -- 1-basiert, wie im Dokument sichtbar
    text TEXT NOT NULL,
    UNIQUE(document_id, page_no)
);

CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,       -- Reihenfolge im Dokument
    page_from INTEGER NOT NULL,
    page_to INTEGER NOT NULL,
    text TEXT NOT NULL          -- Originaltext für die Anzeige
);

CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    norm,
    stems,
    content='',
    tokenize='unicode61'
);

-- Kategorien (frei benennbar, in den Einstellungen verwaltet). Ein Buch kann
-- mehreren Kategorien angehören -> Zuordnung über die Verknüpfungstabelle.
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS document_categories (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, category_id)
);

-- Autoren (frei benennbar, wie Kategorien in den Sammlungen verwaltbar). Ein
-- Buch kann mehrere Autoren haben -> Zuordnung über die Verknüpfungstabelle.
-- documents.author bleibt als synchron gehaltener Cache bestehen (Suche,
-- Reader-Kopf und der .echolib-Export/-Import lesen weiterhin aus der Spalte).
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS document_authors (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    author_id   INTEGER NOT NULL REFERENCES authors(id)   ON DELETE CASCADE,
    PRIMARY KEY (document_id, author_id)
);

-- Kleine Schlüssel/Wert-Einstellungen: Leseposition je Buch, Schriftgröße,
-- gesehene Version, zwischengespeicherte Release-Notizen, Shamela-Zugang.
-- Steht bewusst hier im zentralen Schema; früher legte fast jede Funktion
-- diese Tabelle selbst an (sieben Stellen mit demselben CREATE).
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Lesezeichen: bewusst OHNE Fremdschlüssel-Kaskade, damit sie ein
-- Neu-Einlesen des Buches überleben. Wiedergefunden wird die Stelle über
-- Titel + Seite + Textausschnitt, falls sich die internen IDs ändern.
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER,        -- bester bekannter Stand (nur lokale Bücher)
    passage_id INTEGER,         -- bester bekannter Stand (nur lokale Bücher)
    doc_title TEXT NOT NULL,    -- zum Wiederfinden nach Neu-Scan
    page_no INTEGER NOT NULL,
    snippet TEXT NOT NULL,      -- Textausschnitt der Fundstelle
    note TEXT DEFAULT '',       -- eigene Notiz
    terms TEXT DEFAULT '',      -- Suchbegriffe (JSON) für die Hervorhebung
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    -- Online-Bücher (Shamela): dort gibt es keine lokale document_id.
    source TEXT DEFAULT 'local',  -- 'local' | 'shamela'
    book_key INTEGER,             -- Buchkennung des Servers
    page_str TEXT,                -- Seitenkennung, z. B. "V01P441"
    page_label TEXT,              -- angezeigte Druckseite, z. B. "ج1 ص441"
    doc_author TEXT               -- Autor (Online-Treffer haben keine Dokumentzeile)
);
"""

# Spalten, die es in älteren Bibliotheken noch nicht gibt. CREATE TABLE IF NOT
# EXISTS lässt bestehende Tabellen unverändert, daher werden sie hier ergänzt.
_BOOKMARK_NEU = [
    ("source", "TEXT DEFAULT 'local'"),
    ("book_key", "INTEGER"),
    ("page_str", "TEXT"),
    ("page_label", "TEXT"),
    ("doc_author", "TEXT"),
]


def _migrate(con: sqlite3.Connection) -> None:
    """Fehlende Spalten nachrüsten – ohne Datenverlust, ohne Neuaufbau."""
    have = {r[1] for r in con.execute("PRAGMA table_info(bookmarks)")}
    for name, ddl in _BOOKMARK_NEU:
        if name not in have:
            con.execute(f"ALTER TABLE bookmarks ADD COLUMN {name} {ddl}")
    con.commit()


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=60)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con
