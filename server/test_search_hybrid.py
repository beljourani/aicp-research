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


class _P:
    def __init__(self, payload, score=0.9):
        self.payload, self.score = payload, score


def test_semantik_fuegt_nichts_hinzu():
    """Eine rein semantische Stelle OHNE die Suchwörter erscheint NICHT."""
    def pruef():
        # 'الصلاة' steht auf V02P100 – dort kommt 'الصبر' nicht vor.
        semantisch = [_P({"title": "صحيح مسلم", "author": "مسلم",
                          "page": "V02P100", "chunk_no": 0,
                          "text": "الصلاة عماد الدين والصلوات خمس",
                          "source": "shamela"})]
        nur_wort = _suche(q="الصبر", limit=10, semantic=False)
        echt = api._vektor_rangliste
        api._vektor_rangliste = lambda *a, **k: semantisch
        try:
            hy = _suche(q="الصبر", limit=10, semantic=True)
        finally:
            api._vektor_rangliste = echt
        seiten_wort = {h["page"] for h in nur_wort["hits"]}
        seiten_hy = {h["page"] for h in hy["hits"]}
        assert "V02P100" not in seiten_hy, \
            f"begriffloser Treffer wurde aufgenommen: {seiten_hy}"
        assert seiten_hy == seiten_wort, \
            f"Menge veraendert: {seiten_hy} != {seiten_wort}"
        print("ok  test_semantik_fuegt_nichts_hinzu")
    _mit_index(pruef)


def test_keine_doppelungen():
    """Eine Stelle in beiden Listen erscheint genau einmal."""
    def pruef():
        wort = _suche(q="الصبر", limit=10, semantic=False)["hits"]
        assert wort, "Vorbedingung: Wortsuche muss etwas finden"
        w = wort[0]
        semantisch = [_P({"title": w["title"], "author": w["author"],
                          "page": w["page"], "chunk_no": 0,
                          "text": w["snippet"], "source": "shamela"})]
        echt = api._vektor_rangliste
        api._vektor_rangliste = lambda *a, **k: semantisch
        try:
            hy = _suche(q="الصبر", limit=10, semantic=True)["hits"]
        finally:
            api._vektor_rangliste = echt
        schluessel = [(h["book_id"], h["page"]) for h in hy]
        assert len(schluessel) == len(set(schluessel)), f"Doppelung: {schluessel}"
        print("ok  test_keine_doppelungen")
    _mit_index(pruef)


def test_semantic_false_ist_reine_wortsuche():
    """Mit semantic=false wird die Vektorsuche gar nicht erst gefragt."""
    def pruef():
        gerufen = []
        echt = api._vektor_rangliste
        api._vektor_rangliste = lambda *a, **k: gerufen.append(1) or []
        try:
            r = _suche(q="الصبر", limit=10, semantic=False)
        finally:
            api._vektor_rangliste = echt
        assert not gerufen, "Semantik wurde trotz semantic=false benutzt"
        assert r["hits"], "keine Treffer"
        print("ok  test_semantic_false_ist_reine_wortsuche")
    _mit_index(pruef)


# --- Grundwahrheit: gegen den PASSAGENTEXT im Index, nie gegen den Ausschnitt.

def _erfuellt_online(text, anfrage):
    from echo_engine.normalize import tokenize as tk, stem as st
    from echo_engine.search import parse_query, _norm_variants
    toks = list(tk(text or ""))
    norms, stems = set(toks), {st(t) for t in toks}

    def da(n, s):
        return any(v in norms for v in _norm_variants(n)) or s in stems

    for g in parse_query(anfrage):
        if (all(da(n, s) for n, s in g.include)
                and not any(da(n, s) for n, s in g.exclude)):
            return True
    return False


def _passagentext(pfad, pid):
    import sqlite3
    con = sqlite3.connect(pfad)
    r = con.execute("SELECT text FROM passages WHERE id=?", (pid,)).fetchone()
    con.close()
    return r[0] if r else ""


def test_und_treffer_vollstaendig_online():
    """Jeder Online-Treffer enthält im Passagentext alle Begriffe."""
    def pruef():
        import sqlite3
        for q in ["الصبر البلاء", "صبر بلاء", "الصلاة الدين"]:
            r = _suche(q=q, limit=10, semantic=False)
            for h in r["hits"]:
                con = sqlite3.connect(api.FTS_DB)
                con.row_factory = sqlite3.Row
                # Passage über Buch+Seite finden (der Treffer trägt keine id)
                row = con.execute(
                    "SELECT p.text FROM passages p JOIN chunk_meta c "
                    "ON c.passage_id=p.id WHERE c.book_id=? AND c.page_str=?",
                    (h["book_id"], h["page"])).fetchone()
                con.close()
                assert row, f"Passage nicht gefunden: {h['page']}"
                assert _erfuellt_online(row["text"], q), \
                    f"{q}: Treffer {h['page']} erfuellt die Anfrage nicht"
        print("ok  test_und_treffer_vollstaendig_online")
    _mit_index(pruef)


def test_ausschluss_online_mit_echtem_wort():
    """Ausschluss mit einem Wort, das wirklich vorkommt."""
    def pruef():
        ohne = _suche(q="الصبر", limit=10, semantic=False)["hits"]
        assert ohne, "Vorbedingung: Treffer vorhanden"
        mit = _suche(q="الصبر -البلاء", limit=10, semantic=False)["hits"]
        seiten_ohne = {h["page"] for h in ohne}
        seiten_mit = {h["page"] for h in mit}
        # V01P006 enthaelt "والصبر عند البلاء" -> muss wegfallen
        assert "V01P006" in seiten_ohne, seiten_ohne
        assert "V01P006" not in seiten_mit, seiten_mit
        print("ok  test_ausschluss_online_mit_echtem_wort")
    _mit_index(pruef)


def test_artikel_form_online_markiert():
    """Ein über die Artikel-Form gefundener Treffer wird markiert."""
    from echo_engine.search import highlight_spans
    t = "الجهات الست لا تخلو"
    marks = [t[a:b] for a, b in highlight_spans(t, ["ست"])]
    assert "الست" in marks, marks
    print("ok  test_artikel_form_online_markiert")


if __name__ == "__main__":
    test_wurzelsuche_findet_beugung()
    test_vokalzeichen_egal()
    test_trefferform_unveraendert()
    test_buchfilter()
    test_autorenfilter()
    test_boolesche_anfrage_nur_wortsuche()
    test_semantik_fuegt_nichts_hinzu()
    test_keine_doppelungen()
    test_semantic_false_ist_reine_wortsuche()
    test_und_treffer_vollstaendig_online()
    test_ausschluss_online_mit_echtem_wort()
    test_artikel_form_online_markiert()
    print("\nAlle Tests bestanden.")
