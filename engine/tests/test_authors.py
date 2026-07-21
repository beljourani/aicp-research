# -*- coding: utf-8 -*-
"""Test: Autoren als eigene Tabellen (wie Kategorien) inkl. Sync mit dem
documents.author-Cache. Spiegelt die SQL aus app/main.py (_sync_document_authors,
_recache_author_string, authors, author_rename/-delete) auf DB-Ebene."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine import connect, index_pages

AUTHOR_SEP = " ؛ "


def _split(value):
    if not value:
        return []
    parts = re.split(r"\s*[؛;]\s*", str(value))
    seen, out = set(), []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _join(names):
    clean = []
    for n in names or []:
        n = (n or "").strip()
        if n and n not in clean:
            clean.append(n)
    return AUTHOR_SEP.join(clean) if clean else None


def _sync(con, doc_id):
    """String -> Tabellen (wie _sync_document_authors)."""
    row = con.execute("SELECT author FROM documents WHERE id=?",
                      (doc_id,)).fetchone()
    con.execute("DELETE FROM document_authors WHERE document_id=?", (doc_id,))
    for n in _split(row["author"] if row else ""):
        con.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (n,))
        aid = con.execute("SELECT id FROM authors WHERE name=?", (n,)).fetchone()
        con.execute("INSERT OR IGNORE INTO document_authors "
                    "(document_id, author_id) VALUES (?,?)", (doc_id, aid["id"]))
    con.commit()


def _doc_authors(con, doc_id):
    return [r[0] for r in con.execute(
        "SELECT a.name FROM document_authors da JOIN authors a ON a.id=da.author_id "
        "WHERE da.document_id=? ORDER BY a.name", (doc_id,))]


def _recache(con, doc_id):
    """Tabellen -> String (wie _recache_author_string)."""
    con.execute("UPDATE documents SET author=? WHERE id=?",
                (_join(_doc_authors(con, doc_id)), doc_id))
    con.commit()


def _list_authors(con):
    """Wie CORE.authors: LEFT JOIN, auch leere Autoren, mit Zähler."""
    return {r["name"]: r["count"] for r in con.execute(
        "SELECT a.id, a.name, COUNT(da.document_id) AS count FROM authors a "
        "LEFT JOIN document_authors da ON da.author_id=a.id "
        "GROUP BY a.id ORDER BY a.name")}


def test_migration_and_counts():
    con = connect(":memory:")
    d1 = index_pages(con, [(1, "نص أول. " * 5)], title="ك1",
                     author="الخوارزمي" + AUTHOR_SEP + "سيبويه")
    d2 = index_pages(con, [(1, "نص ثانٍ. " * 5)], title="ك2", author="سيبويه")
    for d in (d1, d2):
        _sync(con, d)     # Migration je Buch
    counts = _list_authors(con)
    assert counts == {"الخوارزمي": 1, "سيبويه": 2}, counts
    # Idempotenz: erneutes Sync ändert nichts
    _sync(con, d1)
    assert _list_authors(con) == {"الخوارزمي": 1, "سيبويه": 2}
    print("OK  Migration aus documents.author + Zähler")


def test_standalone_empty_author():
    """Ein eigenständig angelegter Autor ohne Buch bleibt gelistet (count 0)."""
    con = connect(":memory:")
    con.execute("INSERT INTO authors (name) VALUES (?)", ("مؤلف بلا كتاب",))
    con.commit()
    assert _list_authors(con) == {"مؤلف بلا كتاب": 0}
    print("OK  Eigenständiger leerer Autor überlebt")


def test_rename_merge_recaches_string():
    con = connect(":memory:")
    d1 = index_pages(con, [(1, "نص. " * 5)], title="ك1",
                     author="أ" + AUTHOR_SEP + "ب")
    d2 = index_pages(con, [(1, "نص. " * 5)], title="ك2", author="أ")
    _sync(con, d1); _sync(con, d2)

    a = con.execute("SELECT id FROM authors WHERE name='أ'").fetchone()[0]
    b = con.execute("SELECT id FROM authors WHERE name='ب'").fetchone()[0]
    docs = {r[0] for r in con.execute(
        "SELECT document_id FROM document_authors WHERE author_id=?", (a,))}
    # Umbenennen "أ" -> "ب": zusammenführen (Namenskollision)
    con.execute("UPDATE OR IGNORE document_authors SET author_id=? "
                "WHERE author_id=?", (b, a))
    con.execute("DELETE FROM authors WHERE id=?", (a,))
    for d in docs:
        _recache(con, d)
    con.commit()

    assert _list_authors(con) == {"ب": 2}, _list_authors(con)
    # Cache-String der betroffenen Bücher wurde mitgezogen
    assert _split(con.execute("SELECT author FROM documents WHERE id=?",
                              (d1,)).fetchone()[0]) == ["ب"]
    assert _split(con.execute("SELECT author FROM documents WHERE id=?",
                              (d2,)).fetchone()[0]) == ["ب"]
    print("OK  Umbenennen-Zusammenführen zieht documents.author-Cache mit")


def test_delete_cascade_and_recache():
    con = connect(":memory:")
    d1 = index_pages(con, [(1, "نص. " * 5)], title="ك1",
                     author="أ" + AUTHOR_SEP + "ب")
    _sync(con, d1)
    a = con.execute("SELECT id FROM authors WHERE name='أ'").fetchone()[0]
    docs = {r[0] for r in con.execute(
        "SELECT document_id FROM document_authors WHERE author_id=?", (a,))}
    con.execute("DELETE FROM authors WHERE id=?", (a,))   # Kaskade
    for d in docs:
        _recache(con, d)
    con.commit()

    assert _list_authors(con) == {"ب": 1}, _list_authors(con)
    assert _split(con.execute("SELECT author FROM documents WHERE id=?",
                              (d1,)).fetchone()[0]) == ["ب"]
    assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    print("OK  Löschen entfernt Autor aus Cache, Buch bleibt")


if __name__ == "__main__":
    test_migration_and_counts()
    test_standalone_empty_author()
    test_rename_merge_recaches_string()
    test_delete_cascade_and_recache()
    print("\nAlle Autoren-Tests bestanden.")
