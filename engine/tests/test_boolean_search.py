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


def test_artikel_unabhaengig():
    # Der bestimmte Artikel „ال" klebt im Arabischen am Wort. Ein artikelloses
    # Suchwort muss die ال-Form finden (ست -> الست), auch wenn der Stemmer bei
    # solchen kurzen Wörtern uneinheitlich stemmt.
    con = connect(":memory:")
    index_pages(con, [
        (1, "معنى قول الطحاوي لا تحويه الجهات الست كسائر المبتدعات وهذا الكلام"),
        (2, "قال المؤلف الله رب العالمين وله الحمد وهذا كلام في العقيدة"),
    ], title="Artikel")
    # Ohne Artikel eingegeben -> muss die Stelle mit Artikel finden
    assert 1 in [h.page_from for h in search(con, "جهات ست لا")]
    assert 1 in [h.page_from for h in search(con, "ست")]
    # Gefahr-Gegenprobe: „الله" (beginnt mit ال) darf NICHT jedes „له" treffen
    assert [h.page_from for h in search(con, "الله")] == [2]
    print("OK  Artikel-unabhängig: ست findet الست, الله trifft nicht له")


# --- Grundwahrheit: geprüft wird gegen den PASSAGENTEXT, nie gegen den
#     240-Zeichen-Ausschnitt. Der Ausschnitt ist nur ein Fenster und kann
#     täuschen – diese Falle hat hier mehrfach zu Fehldiagnosen geführt.

def _erfuellt(text, anfrage):
    """Enthält die Passage wirklich alles Geforderte? Bildet die FTS-Regel
    nach: Normalform ODER Artikel-Form ODER Stamm, jeweils als GANZES Wort."""
    from echo_engine.normalize import tokenize as tk, stem as st
    from echo_engine.search import _norm_variants
    toks = list(tk(text or ""))
    norms, stems = set(toks), {st(t) for t in toks}

    def da(n, s):
        return any(v in norms for v in _norm_variants(n)) or s in stems

    for g in parse_query(anfrage):
        if (all(da(n, s) for n, s in g.include)
                and all(" ".join(tk(text)).find(p) >= 0 for p in g.phrases)
                and not any(da(n, s) for n, s in g.exclude)):
            return True
    return False


def _bibliothek():
    con = connect(":memory:")
    index_pages(con, [
        (1, "الجهات الست لا تخلو من إشكال عند أهل النظر. " * 3),
        (2, "الجهات الست معروفة والكلام فيها طويل جدا. " * 3),
        (3, "الست خصال التي ذكرها المصنف في هذا الباب. " * 3),
        (4, "باب في الصبر والحلم من غير ذكر للجهات هنا. " * 3),
    ], title="Prüfbuch", author="Autor")
    con.commit()
    return con


def test_und_jeder_treffer_vollstaendig():
    """UND: JEDER Treffer enthält im Passagentext alle Begriffe."""
    con = _bibliothek()
    for q in ["جهات ست لا", "الجهات الست", "ست جهات", "لا جهات"]:
        hits = search(con, q, limit=50)
        assert hits, f"keine Treffer für {q}"
        schlecht = [h.passage_id for h in hits
                    if not _erfuellt(_text(con, h.passage_id), q)]
        assert not schlecht, f"{q}: Treffer ohne alle Begriffe: {schlecht}"
    print("OK  UND – jeder Treffer enthält alle Begriffe (Passagentext)")


def _text(con, pid):
    return con.execute("SELECT text FROM passages WHERE id=?", (pid,)).fetchone()[0]


def test_oder_jeder_treffer_erfuellt_eine_gruppe():
    """ODER: jeder Treffer erfüllt mindestens eine Gruppe."""
    con = _bibliothek()
    q = "جهات لا | صبر حلم"
    hits = search(con, q, limit=50)
    assert hits
    for h in hits:
        assert _erfuellt(_text(con, h.passage_id), q), h.passage_id
    print("OK  ODER – jeder Treffer erfüllt eine Gruppe")


def test_ausschluss_mit_real_vorkommendem_wort():
    """Ausschluss: genau die Treffer mit dem Wort fallen weg, der Rest bleibt."""
    con = _bibliothek()
    ohne = search(con, "الجهات الست", limit=50)
    assert len(ohne) >= 2, "Vorbedingung: mehrere Treffer"
    # „لا" kommt in EINEM Teil der Treffer vor – genau darum geht es.
    hatte = {h.passage_id for h in ohne if _erfuellt(_text(con, h.passage_id), "لا")}
    assert hatte, "Vorbedingung: das Ausschlusswort muss vorkommen"
    mit = search(con, "الجهات الست -لا", limit=50)
    ids = {h.passage_id for h in mit}
    assert not (hatte & ids), "Treffer mit dem Ausschlusswort blieben stehen"
    assert {h.passage_id for h in ohne} - hatte == ids, "übrige Treffer verloren"
    for h in mit:
        assert _erfuellt(_text(con, h.passage_id), "الجهات الست -لا")
    print("OK  Ausschluss – nur die passenden Treffer fallen weg")


def test_artikel_form_wird_markiert():
    """Ein über die Artikel-Form gefundener Treffer wird auch markiert."""
    from echo_engine.search import highlight_spans
    t = "الجهات الست لا تخلو"
    marks = [t[a:b] for a, b in highlight_spans(t, ["ست"])]
    assert "الست" in marks, f"Artikel-Form nicht markiert: {marks}"
    # Umgekehrt: Funktionswörter bekommen keine Artikel-Form
    marks2 = [t[a:b] for a, b in highlight_spans("له كتاب والله أعلم", ["له"])]
    assert "الله" not in marks2, f"Funktionswort zog die Artikel-Form: {marks2}"
    print("OK  Artikel-Form wird markiert, Funktionswörter nicht erweitert")


if __name__ == "__main__":
    test_parser()
    test_boolean_search_deutsch()
    test_boolean_search_arabisch()
    test_gemischt()
    test_artikel_unabhaengig()
    test_und_jeder_treffer_vollstaendig()
    test_oder_jeder_treffer_erfuellt_eine_gruppe()
    test_ausschluss_mit_real_vorkommendem_wort()
    test_artikel_form_wird_markiert()
    print("\nAlle Boolesche-Suche-Tests bestanden.")
