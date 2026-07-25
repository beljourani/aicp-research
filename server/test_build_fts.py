# -*- coding: utf-8 -*-
"""Tests für den Aufbau des Wort-/Wurzel-Index (ohne Qdrant, ohne Netz).

Qdrant wird durch eine kleine Attrappe ersetzt. Geprüft werden die Dinge, die
bei einem vierstündigen Lauf teuer wären, wenn sie erst dort auffallen:
Schema, Wiederaufnahme nach Abbruch, Identität der Abschnitte und dass die
gefundenen Formen zur Offline-Engine passen.

Aufruf:  python3 server/test_build_fts.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import types

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
sys.path.insert(0, os.path.join(HIER, "..", "engine"))


# --- Qdrant-Attrappe, bevor build_fts importiert wird ----------------------
class _Treffer:
    def __init__(self, value, count):
        self.value, self.count = value, count


class _Facet:
    def __init__(self, hits):
        self.hits = hits


class _Punkt:
    def __init__(self, payload):
        self.payload = payload


class FakeClient:
    """Liefert feste Abschnitte; zählt, wie oft gelesen wurde."""
    DATEN: dict[str, list[dict]] = {}
    gelesen = 0

    def __init__(self, *a, **k):
        pass

    def facet(self, collection_name=None, key=None, limit=None, exact=None):
        return _Facet([_Treffer(a, len(v)) for a, v in self.DATEN.items()])

    def scroll(self, collection_name=None, scroll_filter=None, with_payload=None,
               with_vectors=None, limit=None, offset=None):
        autor = scroll_filter.must[0].match.value
        FakeClient.gelesen += 1
        return [_Punkt(p) for p in self.DATEN.get(autor, [])], None


fake_qc = types.ModuleType("qdrant_client")
fake_models = types.ModuleType("qdrant_client.models")


class _Match:
    def __init__(self, value=None):
        self.value = value


class _Cond:
    def __init__(self, key=None, match=None):
        self.key, self.match = key, match


class _Filter:
    def __init__(self, must=None, should=None, must_not=None):
        self.must, self.should, self.must_not = must, should, must_not


class _MatchAny:
    def __init__(self, any=None):
        self.any = any


class _SearchParams:
    def __init__(self, **k):
        self.k = k


fake_models.FieldCondition = _Cond
fake_models.MatchValue = _Match
fake_models.MatchAny = _MatchAny
fake_models.Filter = _Filter
fake_models.SearchParams = _SearchParams
fake_models.QuantizationSearchParams = _SearchParams
fake_qc.QdrantClient = FakeClient
fake_qc.models = fake_models
sys.modules["qdrant_client"] = fake_qc
sys.modules["qdrant_client.models"] = fake_models

import build_fts as bf                                              # noqa: E402
from echo_engine.normalize import to_index_forms                    # noqa: E402


def _abschnitt(titel, autor, seite, nr, text):
    return {"title": titel, "author": autor, "page": seite, "chunk_no": nr,
            "text": text, "char_start": 0, "char_end": len(text),
            "source": "shamela"}


DATEN = {
    "البخاري": [
        _abschnitt("صحيح البخاري", "البخاري", "V01P005", 0, "قَالَ الشَّافِعِيُّ رحمه الله"),
        _abschnitt("صحيح البخاري", "البخاري", "V01P006", 0, "والصبر عند البلاء"),
        _abschnitt("الأدب المفرد", "البخاري", "P012", 0, "يكتبون الحديث"),
    ],
    "مسلم": [
        _abschnitt("صحيح مسلم", "مسلم", "V02P100", 0, "الصلاة عماد الدين"),
    ],
}


def _baue(pfad, daten=None):
    FakeClient.DATEN = daten if daten is not None else DATEN
    sys.argv = ["build_fts.py", "--out", pfad, "--workers", "2"]
    bf.main()


def test_index_wird_gebaut():
    """Alle Abschnitte landen im Index, Bücher werden erkannt."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        _baue(p)
        import sqlite3
        con = sqlite3.connect(p)
        n_p = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        n_d = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_f = con.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
        n_m = con.execute("SELECT COUNT(*) FROM chunk_meta").fetchone()[0]
        assert n_p == 4, n_p
        assert n_d == 3, f"3 Bücher erwartet (2 von البخاري, 1 von مسلم), war {n_d}"
        assert n_f == 4, n_f
        assert n_m == 4, n_m
        con.close()
    print("ok  test_index_wird_gebaut")


def test_druckseite_bleibt_erhalten():
    """Die Seitenkennung wird unverändert gespeichert und zerlegt."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        _baue(p)
        import sqlite3
        con = sqlite3.connect(p)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM chunk_meta WHERE page_str='V01P005'").fetchone()
        assert r["part"] == 1 and r["page_num"] == 5, dict(r)
        r2 = con.execute("SELECT * FROM chunk_meta WHERE page_str='P012'").fetchone()
        assert r2["part"] is None and r2["page_num"] == 12, dict(r2)
        con.close()
    print("ok  test_druckseite_bleibt_erhalten")


def test_formen_wie_offline():
    """Der Index enthält genau die Formen, die die Offline-Engine erzeugt."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        _baue(p)
        import sqlite3
        con = sqlite3.connect(p)
        # Wurzelsuche muss die gebeugte Form finden (يكتبون -> كتب)
        stems = to_index_forms("يكتبون الحديث")[1]
        treffer = con.execute(
            "SELECT COUNT(*) FROM passages_fts WHERE passages_fts MATCH ?",
            (f'stems:"{stems.split()[0]}"',)).fetchone()[0]
        assert treffer >= 1, "gestemmte Form nicht gefunden"
        # Vokalisiertes قَالَ muss über die normalisierte Form auffindbar sein
        norm = to_index_forms("قال")[0]
        t2 = con.execute("SELECT COUNT(*) FROM passages_fts WHERE passages_fts "
                         "MATCH ?", (f'norm:"{norm}"',)).fetchone()[0]
        assert t2 >= 1, "vokalisierte Form nicht über norm gefunden"
        con.close()
    print("ok  test_formen_wie_offline")


def test_wiederaufnahme():
    """Ein zweiter Lauf liest nichts neu und verdoppelt nichts."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        _baue(p)
        import sqlite3
        con = sqlite3.connect(p)
        vorher = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        con.close()
        FakeClient.gelesen = 0
        _baue(p)                       # zweiter Lauf
        con = sqlite3.connect(p)
        nachher = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        con.close()
        assert nachher == vorher, f"verdoppelt: {vorher} -> {nachher}"
        assert FakeClient.gelesen == 0, \
            f"trotz fertigem Index wurde {FakeClient.gelesen}x gelesen"
    print("ok  test_wiederaufnahme")


def test_abbruch_hinterlaesst_keinen_halben_autor():
    """Bricht ein Autor ab, ist er gar nicht im Index (Transaktion)."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fts.db")
        import sqlite3
        from echo_engine.db import connect as ec
        con = ec(p)
        bf.zusatz_schema(con)
        s = bf.Schreiber(con)

        def kaputt():
            yield [{"book_id": 1, "title": "T", "author": "A",
                    "page_str": "P001", "part": None, "page_num": 1,
                    "chunk_no": 0, "text": "x", "norm": "x", "stems": "x",
                    "source": "shamela"}]
            raise RuntimeError("Abbruch mitten im Autor")

        try:
            s.schreibe("A", kaputt())
        except RuntimeError:
            pass
        n = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        offen = con.execute("SELECT COUNT(*) FROM fts_state").fetchone()[0]
        con.close()
        assert n == 0, f"halber Autor im Index: {n} Abschnitte"
        assert offen == 0, "Autor faelschlich als fertig vermerkt"
    print("ok  test_abbruch_hinterlaesst_keinen_halben_autor")


if __name__ == "__main__":
    test_index_wird_gebaut()
    test_druckseite_bleibt_erhalten()
    test_formen_wie_offline()
    test_wiederaufnahme()
    test_abbruch_hinterlaesst_keinen_halben_autor()
    print("\nAlle Tests bestanden.")
