# -*- coding: utf-8 -*-
"""Tests für die Zusammenführung von Wort- und semantischer Suche (offline).

Kernregel: Die Wort-Treffer sind die EINZIGE Ergebnismenge. Die semantische
Suche darf ihre Reihenfolge ändern, aber niemals eine Stelle hinzufügen –
sonst stünden Treffer in der Liste, die die gesuchten Wörter gar nicht
enthalten.

Aufruf:  python3 engine/tests/test_hybrid.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from echo_engine import connect                                    # noqa: E402
from echo_engine.indexer import index_pages                        # noqa: E402
from echo_engine.search import hybrid_search, search               # noqa: E402
import echo_engine.search as such                                  # noqa: E402


class FakeEmbedder:
    """Tut so, als gäbe es ein Modell – der Vektor selbst ist egal."""

    def embed(self, texte):
        return [[0.0, 0.0, 0.0]]


def _bibliothek():
    """Buch A enthält das Suchwort, Buch B ist nur thematisch verwandt –
    genau das darf die Semantik nicht hereinholen."""
    con = connect(":memory:")
    a = index_pages(con, [(1, "الصبر عند البلاء جميل وهو من شيم الكرام. " * 4)],
                    title="Buch A", author="Autor")
    b = index_pages(con, [(1, "الحلم والأناة من صفات العقلاء في المجالس. " * 4)],
                    title="Buch B", author="Autor")
    con.commit()
    return con, a, b


def _vec_ersatz(paare):
    """Ersetzt die Vektorsuche durch eine feste Rangliste."""
    def fake(con, qvec, limit=50, author=None, document_id=None,
             category=None, min_similarity=0.25):
        return paare
    return fake


def test_semantik_fuegt_nichts_hinzu():
    """Ein rein semantischer Treffer ohne die Suchwörter erscheint NICHT."""
    con, a, b = _bibliothek()
    wort = search(con, "الصبر", limit=20)
    ids_wort = {h.passage_id for h in wort}
    assert ids_wort, "Vorbedingung: die Wortsuche muss etwas finden"
    fremd = con.execute("SELECT id FROM passages WHERE document_id=?", (b,)).fetchone()[0]
    assert fremd not in ids_wort, "Vorbedingung: Buch B ist kein Wort-Treffer"

    import echo_engine.semantic as sem
    echt = sem.vector_search
    sem.vector_search = _vec_ersatz([(fremd, 0.99)])   # Semantik ganz vorn
    try:
        hy = hybrid_search(con, "الصبر", embedder=FakeEmbedder(), limit=20)
    finally:
        sem.vector_search = echt
    ids = [h.passage_id for h in hy]
    assert fremd not in ids, "begriffloser Treffer wurde aufgenommen"
    assert set(ids) == ids_wort, f"Menge veraendert: {set(ids)} != {ids_wort}"
    print("ok  test_semantik_fuegt_nichts_hinzu")


def test_keine_doppelungen():
    """Eine Stelle in beiden Listen erscheint genau einmal."""
    con, a, b = _bibliothek()
    wort = search(con, "الصبر", limit=20)
    pid = wort[0].passage_id
    import echo_engine.semantic as sem
    echt = sem.vector_search
    sem.vector_search = _vec_ersatz([(pid, 0.99)])
    try:
        hy = hybrid_search(con, "الصبر", embedder=FakeEmbedder(), limit=20)
    finally:
        sem.vector_search = echt
    ids = [h.passage_id for h in hy]
    assert len(ids) == len(set(ids)), f"Doppelung: {ids}"
    print("ok  test_keine_doppelungen")


def test_semantik_sortiert_um():
    """Die Semantik darf die Reihenfolge ändern – aber nur innerhalb der
    Wort-Treffer."""
    con = connect(":memory:")
    index_pages(con, [(1, "الصبر أول وهذا كلام في الباب الأول منه. " * 4),
                      (2, "الصبر ثان وهذا كلام في الباب الثاني منه. " * 4),
                      (3, "الصبر ثالث وهذا كلام في الباب الثالث منه. " * 4)],
                title="A", author="X")
    con.commit()
    wort = [h.passage_id for h in search(con, "الصبر", limit=20)]
    assert len(wort) >= 3, wort
    import echo_engine.semantic as sem
    echt = sem.vector_search
    # letzten Wort-Treffer semantisch nach ganz vorn holen
    sem.vector_search = _vec_ersatz([(wort[-1], 0.99)])
    try:
        hy = [h.passage_id for h in hybrid_search(con, "الصبر",
                                                  embedder=FakeEmbedder(), limit=20)]
    finally:
        sem.vector_search = echt
    assert set(hy) == set(wort), "Menge darf sich nicht ändern"
    assert hy[0] == wort[-1], f"Umsortierung wirkte nicht: {hy} vs {wort}"
    print("ok  test_semantik_sortiert_um")


def test_ohne_embedder_reine_wortsuche():
    """Ohne Embedder bleibt es exakt bei der Wortsuche."""
    con, _, _ = _bibliothek()
    x = [h.passage_id for h in search(con, "الصبر", limit=20)]
    y = [h.passage_id for h in hybrid_search(con, "الصبر", embedder=None, limit=20)]
    assert x == y, f"{x} != {y}"
    print("ok  test_ohne_embedder_reine_wortsuche")


def test_boolesche_anfrage_bleibt_wortsuche():
    """Ausschluss/ODER laufen rein über die Wortsuche, auch mit Embedder."""
    con, a, b = _bibliothek()
    fremd = con.execute("SELECT id FROM passages WHERE document_id=?", (b,)).fetchone()[0]
    import echo_engine.semantic as sem
    echt = sem.vector_search
    gerufen = []

    def fake(*a, **k):
        gerufen.append(1)
        return [(fremd, 0.99)]

    sem.vector_search = fake
    try:
        hy = hybrid_search(con, "الصبر -البلاء", embedder=FakeEmbedder(), limit=20)
    finally:
        sem.vector_search = echt
    assert not gerufen, "Semantik wurde bei boolescher Anfrage benutzt"
    assert fremd not in [h.passage_id for h in hy]
    print("ok  test_boolesche_anfrage_bleibt_wortsuche")


def test_abgewaehlte_buecher_werden_nicht_vektorisiert():
    """Der Schalter muss auch beim Nachholen ohne Buchangabe greifen.

    Beim App-Start wird embed_passages OHNE document_id gerufen. Ohne die
    Bedingung waere der Schalter wirkungslos: ein grosses uebernommenes
    Buch wuerde am naechsten Morgen doch vektorisiert vorliegen und jede
    semantische Suche verlangsamen.
    """
    from echo_engine import connect
    from echo_engine.indexer import index_pages
    from echo_engine.semantic import embed_passages, ensure_vector_schema

    rumpf = "هذا نص طويل بما يكفي كي لا يسقط المقطع من الفهرس. " * 4
    con = connect(":memory:")
    ensure_vector_schema(con)
    mit = index_pages(con, [(1, rumpf + " كلمة زنجبيل")], "Mit Semantik")
    ohne = index_pages(con, [(1, rumpf + " كلمة قرفة")], "Ohne Semantik",
                       file_type="shamela", reliability="shamela",
                       embed_semantic=False)

    class Attrappe:
        def embed(self, texte):
            import numpy as np
            return np.zeros((len(texte), 4), dtype=np.float32)

    embed_passages(con, Attrappe())          # wie beim App-Start: ohne Filter
    hat = {r[0] for r in con.execute(
        "SELECT DISTINCT p.document_id FROM passages p "
        "JOIN passage_vectors v ON v.passage_id = p.id")}
    assert mit in hat, "Buch mit Semantik wurde nicht vektorisiert"
    assert ohne not in hat, "abgewaehltes Buch wurde doch vektorisiert"
    print("ok  test_abgewaehlte_buecher_werden_nicht_vektorisiert")


if __name__ == "__main__":
    test_semantik_fuegt_nichts_hinzu()
    test_keine_doppelungen()
    test_semantik_sortiert_um()
    test_ohne_embedder_reine_wortsuche()
    test_boolesche_anfrage_bleibt_wortsuche()
    test_abgewaehlte_buecher_werden_nicht_vektorisiert()
    print("\nAlle Tests bestanden.")
