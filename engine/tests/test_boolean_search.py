# -*- coding: utf-8 -*-
"""Tests für die boolesche Suche: UND / ODER / Ausschluss / Wortgruppen.

Nachgebaut: Bilals Beispielszenario mit deutschen und arabischen Begriffen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine import connect, index_pages, search
from echo_engine.search import parse_query, is_boolean_query


def test_parser():
    g = parse_query('schreiben stehen -kochen | "دار الكتب" -بيت')
    assert len(g) == 2
    assert len(g[0].include) == 2 and len(g[0].exclude) == 1
    assert g[1].phrases == ["دار الكتب"] and len(g[1].exclude) == 1
    assert is_boolean_query("a -b") and is_boolean_query("a | b")
    assert not is_boolean_query("nur normale wörter")
    # ODER auch über Wörter: oder / or / أو
    assert len(parse_query("haus oder topf")) == 2
    assert len(parse_query("بيت أو قدر")) == 2
    print("OK  Parser")


def test_boolean_search_deutsch():
    con = connect(":memory:")
    index_pages(con, [
        (1, "Hier geht es um Schreiben und um das Haus. "),
        (2, "Hier geht es um Schreiben und um das Kochen im Topf. "),
        (3, "Hier geht es um Schreiben und um ein Buch. "),
        (4, "Hier geht es nur um den Garten. "),
        (5, "Hier geht es um Schreiben und um einen Text. "),
    ], title="Testbuch DE")

    # UND: schreiben + haus -> nur Seite 1
    hits = search(con, "schreiben haus")
    assert [h.page_from for h in hits] == [1], [h.page_from for h in hits]

    # Ausschluss: schreiben, aber nicht kochen und nicht buch -> 1 und 5
    hits = search(con, "schreiben -kochen -buch")
    assert sorted(h.page_from for h in hits) == [1, 5]

    # ODER-Gruppen: (schreiben buch) | (schreiben text) -> 3 und 5
    hits = search(con, "schreiben buch | schreiben text")
    assert sorted(h.page_from for h in hits) == [3, 5]
    print("OK  Deutsch: UND, Ausschluss, ODER-Gruppen")


def test_boolean_search_arabisch():
    con = connect(":memory:")
    index_pages(con, [
        (1, "كان الإمام يكتب في بيته الكبير كل صباح. "),          # schreiben + haus
        (2, "كان الإمام يكتب ويطبخ الطعام في القدر. "),           # schreiben + kochen
        (3, "كتبت المؤلفة كتاباً عن تاريخ الأندلس. "),            # schreiben + buch
        (4, "الحديقة جميلة في فصل الربيع. "),                     # nichts davon
        (5, "كتب العالم نصاً طويلاً عن النحو. "),                 # schreiben + text
    ], title="كتاب الاختبار", author="مؤلف")

    # Wurzel-UND: كتب + بيت -> nur Seite 1 (findet يكتب + بيته!)
    hits = search(con, "كتب بيت")
    assert [h.page_from for h in hits] == [1], [h.page_from for h in hits]

    # Ausschluss über Wurzel: كتب, aber ohne طبخ -> 1, 3, 5 (nicht 2!)
    hits = search(con, "كتب -طبخ")
    pages = sorted(h.page_from for h in hits)
    assert 2 not in pages and 1 in pages and 5 in pages, pages

    # ODER-Gruppen: (كتب قدر) | (كتب نص) -> 2 und 5
    hits = search(con, "كتب قدر | كتب نص")
    assert sorted(h.page_from for h in hits) == [2, 5]

    # Exakte Wortgruppe: "فصل الربيع" -> nur Seite 4
    hits = search(con, '"فصل الربيع"')
    assert [h.page_from for h in hits] == [4]
    print("OK  Arabisch: Wurzel-UND, Wurzel-Ausschluss, ODER, Wortgruppe")


def test_gemischt():
    con = connect(":memory:")
    index_pages(con, [
        (1, "Der Schüler lernt Grammatik. كان يكتب الدرس في دفتره. "),
        (2, "Der Schüler kocht heute nur. كان يطبخ الطعام. "),
    ], title="Gemischt")
    # Deutsch + Arabisch in einer Anfrage
    hits = search(con, "schüler كتب")
    assert [h.page_from for h in hits] == [1]
    print("OK  Gemischt Deutsch+Arabisch in einer Anfrage")


if __name__ == "__main__":
    test_parser()
    test_boolean_search_deutsch()
    test_boolean_search_arabisch()
    test_gemischt()
    print("\nAlle Boolesche-Suche-Tests bestanden.")
