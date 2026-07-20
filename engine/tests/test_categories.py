# -*- coding: utf-8 -*-
"""Test: Kategorie-Filter und Buchfilter (mehrere Bücher) in der Suche."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine import connect, index_pages, search


def _assign(con, doc_id, *names):
    for n in names:
        con.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (n,))
        cid = con.execute("SELECT id FROM categories WHERE name=?",
                          (n,)).fetchone()[0]
        con.execute("INSERT OR IGNORE INTO document_categories "
                    "(document_id, category_id) VALUES (?,?)", (doc_id, cid))
    con.commit()


def test_category_and_book_filter():
    con = connect(":memory:")
    d1 = index_pages(con, [(1, "الرياضيات علم النسب والمقادير. " * 3)],
                     title="كتاب الجبر", author="الخوارزمي")
    d2 = index_pages(con, [(1, "اللغة والنحو أساس الأدب العربي. " * 3)],
                     title="كتاب النحو", author="سيبويه")
    d3 = index_pages(con, [(1, "الهندسة فرع من الرياضيات. " * 3)],
                     title="كتاب الهندسة", author="إقليدس")

    _assign(con, d1, "رياضيات")
    _assign(con, d2, "لغة")
    _assign(con, d3, "رياضيات", "هندسة")   # in ZWEI Kategorien

    # Kategoriefilter: nur die zwei Mathe-Bücher
    hits = search(con, "", category="رياضيات")
    got = {h.document_id for h in hits}
    assert got == {d1, d3}, f"Kategoriefilter falsch: {got}"

    # Buch d3 taucht auch unter der Kategorie 'هندسة' auf (Mehrfachzuordnung)
    hits = search(con, "", category="هندسة")
    assert {h.document_id for h in hits} == {d3}

    # Mehrere Kategorien (ODER): لغة + هندسة -> d2 und d3
    hits = search(con, "", category=["لغة", "هندسة"])
    assert {h.document_id for h in hits} == {d2, d3}

    # Buchfilter mit Liste (mehrere Bücher)
    hits = search(con, "", document_id=[d1, d2])
    assert {h.document_id for h in hits} == {d1, d2}

    # Kombination Kategorie + Volltext
    hits = search(con, "الرياضيات", category="رياضيات")
    assert {h.document_id for h in hits} <= {d1, d3} and hits

    print("OK  Kategorie- und Buchfilter (inkl. Mehrfachzuordnung/ODER)")


def _cat_id(con, name):
    return con.execute("SELECT id FROM categories WHERE name=?",
                       (name,)).fetchone()[0]


def _cats_of(con, doc_id):
    return {r[0] for r in con.execute(
        "SELECT c.name FROM document_categories dc "
        "JOIN categories c ON c.id=dc.category_id "
        "WHERE dc.document_id=?", (doc_id,))}


def test_rename_merge_and_delete_cascade():
    """Spiegelt die SQL aus category_rename/category_delete: Umbenennen auf
    einen vorhandenen Namen führt beide Kategorien zusammen; Löschen entfernt
    die Zuordnung (Kaskade), lässt die Bücher aber bestehen."""
    con = connect(":memory:")
    d1 = index_pages(con, [(1, "نص أول. " * 5)], title="ك1")
    d2 = index_pages(con, [(1, "نص ثانٍ. " * 5)], title="ك2")
    _assign(con, d1, "أ", "ب")     # d1 -> {أ, ب}
    _assign(con, d2, "أ")          # d2 -> {أ}

    a, b = _cat_id(con, "أ"), _cat_id(con, "ب")
    # Umbenennen "أ" -> "ب": zusammenführen (wie category_rename bei Namenskollision)
    con.execute("UPDATE OR IGNORE document_categories SET category_id=? "
                "WHERE category_id=?", (b, a))
    con.execute("DELETE FROM categories WHERE id=?", (a,))   # Kaskade räumt Reste
    con.commit()

    assert _cats_of(con, d1) == {"ب"}, _cats_of(con, d1)
    assert _cats_of(con, d2) == {"ب"}, _cats_of(con, d2)
    assert con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1

    # Löschen der letzten Kategorie: Zuordnungen weg, Bücher bleiben
    con.execute("DELETE FROM categories WHERE id=?", (b,))
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM document_categories").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
    print("OK  Umbenennen-Zusammenführen + Löschen-Kaskade")


if __name__ == "__main__":
    test_category_and_book_filter()
    test_rename_merge_and_delete_cascade()
    print("\nAlle Kategorie-Tests bestanden.")
