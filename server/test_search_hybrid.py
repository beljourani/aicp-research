# -*- coding: utf-8 -*-
"""Tests für die umgestellte Online-Suche (Wort/Wurzel + Semantik).

Qdrant wird durch eine Attrappe ersetzt; der Wortindex ist ein echter, klein
gebauter FTS5-Index. Geprüft wird, dass die Online-Suche dieselben Formen
findet wie offline, dass die Trefferform unverändert bleibt (davon hängen
Leser, Sortierung und Lesezeichen ab) und dass die Zusammenführung mit der
semantischen Liste funktioniert.

Aufruf:  python3 server/test_search_hybrid.py
"""
from __future__ import annotations

import os
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

# Qdrant-Attrappe aus dem Builder-Test wiederverwenden (setzt sys.modules).
import test_build_fts as tbf                                        # noqa: E402

import build_fts as bf                                              # noqa: E402
import api                                                          # noqa: E402


DATEN = {
    "البخاري": [
        tbf._abschnitt("صحيح البخاري", "البخاري", "V01P005", 0,
                       "قَالَ الشَّافِعِيُّ وهو يكتبون الحديث في المسجد"),
        tbf._abschnitt("صحيح البخاري", "البخاري", "V01P006", 0,
                       "والصبر عند البلاء جميل"),
    ],
    "مسلم": [
        tbf._abschnitt("صحيح مسلم", "مسلم", "V02P100", 0,
                       "الصلاة عماد الدين والصلوات خمس"),
        tbf._abschnitt("صحيح مسلم", "مسلم", "V02P101", 0,
                       "من صبر ظفر وهذا من الصبر"),
    ],
}


def _index(pfad):
    tbf.FakeClient.DATEN = DATEN
    sys.argv = ["build_fts.py", "--out", pfad, "--workers", "2"]
    bf.main()
    api.FTS_DB = pfad


def _suche(**kw):
    req = api.SearchReq(**kw)
    return api.search(req, x_api_key="T", authorization=None)


def _mit_index(fn):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        api.API_TOKEN = "T"
        api.META_DB = os.path.join(d, "meta.db")
        _index(p)
        fn()


def test_wurzelsuche_findet_beugung():
    """Wie offline: 'كتب' findet 'يكتبون'."""
    def pruef():
        r = _suche(q="كتب", limit=10, semantic=False)
        texte = [h["snippet"] for h in r["hits"]]
        assert any("يكتبون" in t for t in texte), texte
        print("ok  test_wurzelsuche_findet_beugung")
    _mit_index(pruef)


def test_vokalzeichen_egal():
    """Vokalisiertes قَالَ wird über die unvokalisierte Anfrage gefunden."""
    def pruef():
        r = _suche(q="قال", limit=10, semantic=False)
        assert r["hits"], "kein Treffer für قال"
        assert any("قَالَ" in h["snippet"] for h in r["hits"])
        print("ok  test_vokalzeichen_egal")
    _mit_index(pruef)


def test_trefferform_unveraendert():
    """Die Felder, an denen Leser/Lesezeichen hängen, sind alle da."""
    def pruef():
        r = _suche(q="الصبر", limit=5, semantic=False)
        assert r["hits"], "keine Treffer"
        h = r["hits"][0]
        for feld in ("score", "book_id", "seq", "title", "author", "page",
                     "page_num", "part", "source", "snippet"):
            assert feld in h, f"Feld {feld} fehlt"
        assert h["seq"] is None, "seq muss null bleiben (wird beim Öffnen gelöst)"
        assert isinstance(h["book_id"], int) and h["book_id"] > 0
        # Druckseite unverändert aus der Seitenkennung
        assert h["page"] and h["page"].startswith("V")
        assert h["part"] == int(h["page"][1:3])
        print("ok  test_trefferform_unveraendert")
    _mit_index(pruef)


def test_buchfilter():
    """book_ids schränkt auf ein Buch ein."""
    def pruef():
        import meta_index as mi
        bid = mi.book_id("صحيح مسلم", "مسلم")
        r = _suche(q="الصبر", limit=10, semantic=False, book_ids=[bid])
        assert r["hits"], "kein Treffer im gefilterten Buch"
        assert all(h["book_id"] == bid for h in r["hits"]), \
            [h["title"] for h in r["hits"]]
        print("ok  test_buchfilter")
    _mit_index(pruef)


def test_autorenfilter():
    """authors schränkt auf einen Autor ein."""
    def pruef():
        r = _suche(q="الصبر", limit=10, semantic=False, authors=["مسلم"])
        assert r["hits"], "kein Treffer beim gefilterten Autor"
        assert all(h["author"] == "مسلم" for h in r["hits"])
        print("ok  test_autorenfilter")
    _mit_index(pruef)


def test_boolesche_anfrage_nur_wortsuche():
    """Ausschluss/ODER laufen rein über die Wortsuche – auch mit semantic=True."""
    gerufen = []

    def pruef():
        echt = api._vektor_rangliste
        api._vektor_rangliste = lambda *a, **k: gerufen.append(1) or []
        try:
            r = _suche(q="الصبر -البلاء", limit=10, semantic=True)
            assert not gerufen, "Semantik wurde bei boolescher Anfrage benutzt"
            texte = [h["snippet"] for h in r["hits"]]
            assert all("البلاء" not in t for t in texte), texte
        finally:
            api._vektor_rangliste = echt
        print("ok  test_boolesche_anfrage_nur_wortsuche")
    _mit_index(pruef)


def test_zusammenfuehrung_mit_semantik():
    """Mit semantic=True fließen beide Listen ein (RRF)."""
    def pruef():
        class P:
            def __init__(self, payload, score):
                self.payload, self.score = payload, score
        # Die Semantik liefert eine Stelle, die die Wortsuche NICHT findet.
        semantisch = [P({"title": "صحيح مسلم", "author": "مسلم",
                         "page": "V02P100", "chunk_no": 0,
                         "text": "الصلاة عماد الدين والصلوات خمس",
                         "source": "shamela"}, 0.9)]
        echt = api._vektor_rangliste
        api._vektor_rangliste = lambda *a, **k: semantisch
        try:
            r = _suche(q="الصبر", limit=10, semantic=True)
            seiten = {h["page"] for h in r["hits"]}
            assert "V02P101" in seiten, f"Worttreffer fehlt: {seiten}"
            assert "V02P100" in seiten, f"semantischer Treffer fehlt: {seiten}"
        finally:
            api._vektor_rangliste = echt
        print("ok  test_zusammenfuehrung_mit_semantik")
    _mit_index(pruef)


if __name__ == "__main__":
    test_wurzelsuche_findet_beugung()
    test_vokalzeichen_egal()
    test_trefferform_unveraendert()
    test_buchfilter()
    test_autorenfilter()
    test_boolesche_anfrage_nur_wortsuche()
    test_zusammenfuehrung_mit_semantik()
    print("\nAlle Tests bestanden.")
