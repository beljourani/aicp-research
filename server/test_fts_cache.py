# -*- coding: utf-8 -*-
"""Tests für den Kandidatenspeicher (server/fts_cache.py).

Läuft überall – das Modul braucht weder SQLite noch Qdrant noch Netz. Die
teure Rangfunktion wird durch eine Attrappe ersetzt, die mitzählt und auf
Wunsch bummelt.

Aufruf:  python3 server/test_fts_cache.py
"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts_cache import Kandidatenspeicher


class Rechner:
    """Attrappe der teuren Bewertung.

    Liefert absteigende, NEGATIVE Punktzahlen – genau wie bm25(): kleiner ist
    besser, und `ORDER BY score` aufsteigend heißt „bestes zuerst". Ein Test
    mit positiven Werten würde die Sortierrichtung falsch absichern.
    """

    def __init__(self, gesamt: int = 5000, dauer: float = 0.0):
        self.gesamt = gesamt        # so viele Treffer gäbe es insgesamt
        self.dauer = dauer
        self.aufrufe = 0
        self.limits: list[int] = []

    def __call__(self, n: int):
        self.aufrufe += 1
        self.limits.append(n)
        if self.dauer:
            time.sleep(self.dauer)
        return [{"rid": 1000 + i, "score": -20.0 + i * 0.001}
                for i in range(min(n, self.gesamt))]


def test_zweiter_aufruf_rechnet_nicht():
    sp, r = Kandidatenspeicher(), Rechner()
    a = sp.hole("k", 90, r)
    b = sp.hole("k", 90, r)
    assert r.aufrufe == 1, r.aufrufe
    assert a == b
    assert sp.stand()["treffer"] == 1
    print("ok: zweiter Aufruf rechnet nicht")


def test_praefix_ist_stabil():
    """Zuschneiden muss dasselbe liefern wie eine kleine Abfrage."""
    sp, r = Kandidatenspeicher(gross=1200), Rechner()
    voll = sp.hole("k", 1200, r)
    for limit in (1, 30, 90, 400):
        teil = sp.hole("k", limit, r)
        assert teil == voll[:limit], limit
        # Punktzahlen müssen den array-Umweg bitgleich überstehen.
        assert all(t["score"] == v["score"] for t, v in zip(teil, voll))
    assert r.aufrufe == 1
    print("ok: Präfix ist stabil und bitgleich")


def test_grosszuegig_rechnen():
    """Auch bei kleinem Limit wird gleich die große Liste geholt."""
    sp, r = Kandidatenspeicher(gross=1200), Rechner()
    sp.hole("k", 30, r)
    assert r.limits == [1200], r.limits
    sp.hole("k", 900, r)            # tieferes Blättern: schon gedeckt
    assert r.aufrufe == 1
    print("ok: es wird einmal großzügig gerechnet")


def test_vollstaendige_liste_deckt_jedes_limit():
    """Weniger Treffer als gerechnet heißt: das sind alle.

    Genau daraus schließt die Suche auf `has_more`. Ein erneutes Rechnen
    wäre hier reine Verschwendung.
    """
    sp, r = Kandidatenspeicher(gross=1200), Rechner(gesamt=40)
    sp.hole("k", 30, r)
    ergebnis = sp.hole("k", 5000, r)
    assert r.aufrufe == 1, r.aufrufe
    assert len(ergebnis) == 40
    print("ok: vollständige Liste deckt jedes Limit")


def test_zu_flache_liste_wird_nachgerechnet():
    """Volle Liste und mehr gefragt -> neu rechnen, sonst wäre has_more falsch."""
    sp, r = Kandidatenspeicher(gross=1200), Rechner(gesamt=99999)
    sp.hole("k", 30, r)
    tief = sp.hole("k", 3000, r)
    assert r.aufrufe == 2, r.aufrufe
    assert r.limits == [1200, 3000], r.limits
    assert len(tief) == 3000
    # Der tiefere Eintrag darf nicht wieder gegen den flachen getauscht werden.
    sp.hole("k", 3000, r)
    assert r.aufrufe == 2, r.aufrufe
    print("ok: zu flache Liste wird nachgerechnet und bleibt tief")


def test_verdraengung():
    sp = Kandidatenspeicher(max_eintraege=3)
    for name in ("a", "b", "c"):
        sp.hole(name, 10, Rechner())
    sp.hole("a", 10, Rechner())      # a wieder anfassen -> b ist der älteste
    sp.hole("d", 10, Rechner())
    assert sp.stand()["eintraege"] == 3
    zaehler = Rechner()
    sp.hole("a", 10, zaehler)
    assert zaehler.aufrufe == 0, "a wurde verdrängt, obwohl zuletzt benutzt"
    zaehler = Rechner()
    sp.hole("b", 10, zaehler)
    assert zaehler.aufrufe == 1, "b hätte verdrängt sein müssen"
    print("ok: ältester Eintrag wird verdrängt, benutzte bleiben")


def test_nur_einer_rechnet():
    """Zwölf gleichzeitige Anfragen dürfen nicht zwölfmal 14 s kosten."""
    sp, r = Kandidatenspeicher(), Rechner(dauer=0.25)
    ergebnisse, fehler = [], []

    def lauf():
        try:
            ergebnisse.append(sp.hole("k", 90, r))
        except Exception as e:                       # pragma: no cover
            fehler.append(e)

    faeden = [threading.Thread(target=lauf) for _ in range(12)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(10)
    assert not fehler, fehler
    assert r.aufrufe == 1, r.aufrufe
    assert len(ergebnisse) == 12
    assert all(e == ergebnisse[0] for e in ergebnisse)
    print("ok: bei gleichzeitigen Anfragen rechnet nur einer")


def test_ausnahme_haengt_niemanden_auf():
    """Scheitert die Rechnung, dürfen Wartende nicht bis zur Grenze hängen."""
    sp = Kandidatenspeicher(warte_max=30)
    los = threading.Event()

    def kaputt(n):
        los.set()
        time.sleep(0.05)
        raise RuntimeError("Indexfehler")

    fehler = []

    def erster():
        try:
            sp.hole("k", 90, kaputt)
        except Exception as e:
            fehler.append(e)

    f = threading.Thread(target=erster)
    f.start()
    los.wait(5)
    begonnen = time.time()
    zweiter = Rechner()
    ergebnis = sp.hole("k", 90, zweiter)             # darf nicht 30 s warten
    dauer = time.time() - begonnen
    f.join(5)
    assert len(fehler) == 1, fehler
    assert dauer < 5, f"Wartender hing {dauer:.1f}s"
    assert zweiter.aufrufe == 1, "der Wartende hätte selbst rechnen müssen"
    assert len(ergebnis) == 90
    # Der Schlüssel darf nicht als „läuft gerade" zurückbleiben.
    nochmal = Rechner()
    sp.hole("k", 90, nochmal)
    assert nochmal.aufrufe == 0
    print("ok: eine Ausnahme hängt niemanden auf")


def test_wartegrenze():
    """Wer zu lange wartet, rechnet selbst – kein Verklemmen."""
    sp = Kandidatenspeicher(warte_max=0.05)
    los = threading.Event()

    def langsam(n):
        los.set()
        time.sleep(1.0)
        return [{"rid": i, "score": -1.0 * i} for i in range(n)]

    f = threading.Thread(target=lambda: sp.hole("k", 90, langsam))
    f.start()
    los.wait(5)
    eigener = Rechner()
    begonnen = time.time()
    ergebnis = sp.hole("k", 90, eigener)
    assert time.time() - begonnen < 0.9
    assert eigener.aufrufe == 1
    assert len(ergebnis) == 90
    f.join(5)
    print("ok: nach der Wartegrenze wird selbst gerechnet")


def test_grosse_zahlen_und_negative_punkte():
    """Zeilennummern und bm25-Werte müssen unverändert zurückkommen."""
    sp = Kandidatenspeicher()
    rohe = [{"rid": 11_488_400 - i, "score": -18.3456789 - i * 0.5}
            for i in range(1000)]
    ergebnis = sp.hole("k", 1000, lambda n: rohe[:n])
    assert ergebnis == rohe, "Speicherform verändert die Werte"
    print("ok: große Zeilennummern und negative Punktzahlen bleiben exakt")


def test_leeren():
    sp, r = Kandidatenspeicher(), Rechner()
    sp.hole("k", 90, r)
    sp.leeren()
    sp.hole("k", 90, r)
    assert r.aufrufe == 2
    print("ok: leeren vergisst alles")


if __name__ == "__main__":
    test_zweiter_aufruf_rechnet_nicht()
    test_praefix_ist_stabil()
    test_grosszuegig_rechnen()
    test_vollstaendige_liste_deckt_jedes_limit()
    test_zu_flache_liste_wird_nachgerechnet()
    test_verdraengung()
    test_nur_einer_rechnet()
    test_ausnahme_haengt_niemanden_auf()
    test_wartegrenze()
    test_grosse_zahlen_und_negative_punkte()
    test_leeren()
    print("\nAlle Tests bestanden.")
