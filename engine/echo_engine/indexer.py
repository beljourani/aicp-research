# -*- coding: utf-8 -*-
"""Indexierung: Datei -> Seiten -> Passagen -> Volltextindex."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .chunker import chunk_pages
from .extract import extract
from .normalize import to_index_forms
from .textlayout import join_wrapped_lines, letter_count

# Bei Änderungen an Normalisierung/Stemming hochzählen -> der Volltext-
# index wird beim nächsten App-Start automatisch neu aufgebaut (schnell,
# ohne die Dokumente neu einzulesen).
STEM_VERSION = 3        # 3: Tokenizer erkennt jede Schrift (Umlaute, Persisch,
#                            Kyrillisch, CJK) statt einer festen Zeichenliste

# Bei Änderungen an der Absatz-Aufbereitung hochzählen -> der gespeicherte
# Seitentext bereits eingelesener Bücher wird beim nächsten App-Start
# einmalig nachgebessert (ohne die Originaldateien erneut zu lesen, also
# insbesondere ohne erneutes OCR).
LAYOUT_VERSION = 1


def ensure_index_version(con: sqlite3.Connection) -> bool:
    """Baut den FTS-Index neu auf, wenn sich das Stemming geändert hat.
    Liefert True, wenn ein Neuaufbau stattgefunden hat."""
    row = con.execute(
        "SELECT value FROM meta WHERE key='stem_version'").fetchone()
    if row and row[0] == str(STEM_VERSION):
        return False
    rebuild_fts(con)
    con.execute("INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('stem_version', ?)", (str(STEM_VERSION),))
    con.commit()
    return True


def rebuild_fts(con: sqlite3.Connection) -> None:
    """Baut den Volltextindex vollständig aus den gespeicherten Passagen neu."""
    con.execute("INSERT INTO passages_fts (passages_fts) VALUES ('delete-all')")
    for pid, text in con.execute("SELECT id, text FROM passages"):
        norm, stems = to_index_forms(text)
        con.execute(
            "INSERT INTO passages_fts (rowid, norm, stems) VALUES (?,?,?)",
            (pid, norm, stems))


def delete_documents(con: sqlite3.Connection, doc_ids) -> int:
    """Löscht Dokumente – samt ihrer Spuren im Volltextindex.

    Der Volltextindex ist inhaltslos (`content=''`) und hat keinen Auslöser:
    ein `DELETE FROM documents` räumt über die Fremdschlüssel zwar `passages`
    ab, lässt die zugehörigen Indexzeilen aber stehen. Passagen-Nummern
    werden von SQLite wiederverwendet, das nächste eingelesene Buch erbt sie
    also – und mit ihnen die Wörter des gelöschten Buches. Ergebnis waren
    Treffer, deren angezeigter Text das gesuchte Wort gar nicht enthält
    (nachgestellt und bestätigt).

    Deshalb wird jede Passage vor dem Löschen ausdrücklich aus dem Index
    ausgetragen. Der Spezialbefehl 'delete' verlangt dieselben Werte, mit
    denen die Zeile eingefügt wurde – sie werden aus dem gespeicherten Text
    neu berechnet, was genau dieselben Formen ergibt (`ensure_index_version`
    baut den Index bei geänderter Stemming-Logik ohnehin aus derselben
    Quelle neu auf).
    """
    ids = [int(i) for i in doc_ids if i is not None]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    zeilen = con.execute(
        f"SELECT id, text FROM passages WHERE document_id IN ({marks})",
        ids).fetchall()
    try:
        for pid, text in zeilen:
            norm, stems = to_index_forms(text)
            con.execute(
                "INSERT INTO passages_fts (passages_fts, rowid, norm, stems) "
                "VALUES ('delete', ?, ?, ?)", (pid, norm, stems))
    except sqlite3.DatabaseError:
        # Sollten Index und Text wider Erwarten auseinanderliegen, ist ein
        # vollständiger Neuaufbau die sichere Rettung – lieber einmal
        # langsam als dauerhaft falsche Treffer.
        con.rollback()
        cur = con.execute(f"DELETE FROM documents WHERE id IN ({marks})", ids)
        rebuild_fts(con)
        con.commit()
        return cur.rowcount
    cur = con.execute(f"DELETE FROM documents WHERE id IN ({marks})", ids)
    con.commit()
    return cur.rowcount


def ensure_text_layout_version(con: sqlite3.Connection) -> int:
    """Bessert den gespeicherten Seitentext bereits eingelesener Bücher nach.

    Läuft einmalig (Zustand im meta-Schlüssel 'layout_version'). Es wird
    ausschließlich Weißraum verändert: überflüssige Leerzeichen und
    Leerzeilen verschwinden, umgebrochene Zeilen werden wieder zu Absätzen
    zusammengefügt. Seitenzahlen, Suchindex, Passagen und Lesezeichen
    bleiben unangetastet.

    Liefert die Zahl der geänderten Seiten.
    """
    row = con.execute(
        "SELECT value FROM meta WHERE key='layout_version'").fetchone()
    if row and row[0] == str(LAYOUT_VERSION):
        return 0
    geaendert = 0
    # Aus dem Netz übernommene Bücher bleiben wortwörtlich so, wie die Quelle
    # sie geliefert hat. Sonst wäre ihr Text nach einer solchen Nachbesserung
    # nicht mehr zeichengleich mit der Online-Ansicht, und dasselbe Zitat
    # sähe je nach Herkunft anders aus.
    for pid, alt in con.execute(
            "SELECT p.id, p.text FROM pages p "
            "JOIN documents d ON d.id = p.document_id "
            "WHERE COALESCE(d.reliability, 'sicher') != 'shamela'").fetchall():
        neu = join_wrapped_lines(alt or "")
        if neu == (alt or ""):
            continue
        # Sicherung: es darf kein Buchstabe verloren gehen oder hinzukommen
        if letter_count(neu) != letter_count(alt):
            continue
        con.execute("UPDATE pages SET text=? WHERE id=?", (neu, pid))
        geaendert += 1
    con.execute("INSERT OR REPLACE INTO meta (key, value) "
                "VALUES ('layout_version', ?)", (str(LAYOUT_VERSION),))
    con.commit()
    return geaendert


def index_document(con: sqlite3.Connection, path: str | Path,
                   title: str | None = None, author: str | None = None,
                   force_ocr: bool = False, progress=None,
                   warnungen: list | None = None) -> int:
    """Verarbeitet eine Datei vollständig. Liefert die Dokument-ID.

    `warnungen` (optional) wird mit den Hinweisen der Extraktion gefüllt –
    etwa „kaputte Textschicht erkannt" oder „Seitenzahlen können abweichen".
    Diese Hinweise wurden bisher erzeugt und danach weggeworfen; der Nutzer
    bekam ein Buch mit verdrehtem Text oder ungenauen Seitenzahlen kommentarlos
    als „fertig" gemeldet."""
    p = Path(path)
    res = extract(p, force_ocr=force_ocr, progress=progress)
    if warnungen is not None:
        warnungen.extend(getattr(res, "warnings", []) or [])
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


def index_pages(con: sqlite3.Connection, pages: list[tuple],
                title: str, author: str | None = None, *,
                file_type: str = "raw", reliability: str = "sicher",
                source_key: str | None = None,
                embed_semantic: bool = True) -> int:
    """Indexiert bereits vorliegende Seiten (Tests, Übernahme aus dem Netz).

    `pages` ist entweder `[(page_no, text)]` wie bisher oder
    `[(page_no, text, page_label, page_key)]` – dann wird die angezeigte
    Druckseite mitgespeichert (siehe shamela_import.py).
    """
    cur = con.execute(
        "INSERT INTO documents (title, author, file_type, page_count, "
        "reliability, source_key, embed_semantic) VALUES (?,?,?,?,?,?,?)",
        (title, author, file_type, len(pages), reliability, source_key,
         1 if embed_semantic else 0))
    doc_id = cur.lastrowid
    _index_pages(con, doc_id, pages)
    con.commit()
    return doc_id


def append_pages(con: sqlite3.Connection, doc_id: int,
                 pages: list[tuple]) -> int:
    """Hängt weitere Seiten an ein bestehendes Dokument an.

    Für das blockweise Übernehmen aus dem Netz: jeder Block wird sofort
    weggeschrieben, damit weder Speicher noch Schreibprotokoll anwachsen.
    Liefert die Zahl der Seiten des Dokuments nach dem Anhängen.
    """
    _index_pages(con, doc_id, pages)
    con.commit()
    return con.execute("SELECT COUNT(*) FROM pages WHERE document_id=?",
                       (doc_id,)).fetchone()[0]


def _index_pages(con: sqlite3.Connection, doc_id: int,
                 pages: list[tuple]) -> None:
    # Zwei- und Vierertupel zusammenführen: ohne Bezeichnung bleiben die
    # beiden neuen Spalten leer, und das Dokument verhält sich wie bisher.
    voll = []
    for p in pages:
        voll.append((p[0], p[1], None, None) if len(p) == 2 else tuple(p[:4]))
    con.executemany(
        "INSERT INTO pages (document_id, page_no, text, page_label, page_key) "
        "VALUES (?,?,?,?,?)",
        [(doc_id, no, text, lbl, key) for no, text, lbl, key in voll])
    # Die Passagen kennen weiterhin nur Blattnummern; der Chunker bleibt
    # unangetastet. Der Versatz sorgt dafür, dass die laufende Nummer über
    # mehrere Blöcke hinweg weiterzählt statt je Block wieder bei 0 zu
    # beginnen.
    versatz = con.execute(
        "SELECT COALESCE(MAX(idx) + 1, 0) FROM passages WHERE document_id=?",
        (doc_id,)).fetchone()[0]
    for passage in chunk_pages([(no, text) for no, text, _l, _k in voll]):
        norm, stems = to_index_forms(passage.text)
        cur = con.execute(
            "INSERT INTO passages (document_id, idx, page_from, page_to, text) "
            "VALUES (?,?,?,?,?)",
            (doc_id, versatz + passage.idx, passage.page_from, passage.page_to,
             passage.text))
        con.execute(
            "INSERT INTO passages_fts (rowid, norm, stems) VALUES (?,?,?)",
            (cur.lastrowid, norm, stems))
