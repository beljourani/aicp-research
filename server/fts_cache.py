# -*- coding: utf-8 -*-
"""Zwischenspeicher für die teure Stufe der Wort-/Wurzelsuche.

Reine Datenlogik – ohne FastAPI, ohne Qdrant, ohne SQLite. Wie meta_index.py
lässt sie sich damit überall testen (server/test_fts_cache.py), auch dort, wo
der Server selbst nicht laufen kann.

Warum es diesen Speicher gibt (auf dem Server gemessen):

  Anfrage   getroffene Abschnitte   Bewertung (bm25)   Verbinden+Ausschnitte
  الله      5.958.791               14,4 s             0,00 s
  الصلاة    1.097.504                2,7 s             0,00 s

SQLite FTS5 muss für JEDE Trefferzeile eine Punktzahl rechnen, um die besten
90 zu finden – einen vorzeitigen Abbruch gibt es nicht. Das ist reine
Rechenarbeit (warm genauso langsam wie kalt) und lässt sich nicht billiger
machen, ohne die Trefferreihenfolge zu verändern. Also wird sie gemerkt.

Zwischengelagert wird NUR die bewertete Kandidatenliste (Zeilennummer +
Punktzahl), nicht die fertige Antwort. Alles, was die Anzeige betrifft –
Verbinden, Ausschnitte, Markierung, die semantische Umsortierung – bleibt
live. Damit kann keine Anzeige veralten, und die Nebenwirkungen der Suche
(z. B. das Merken der Bücher für den Leser) laufen unverändert weiter.

Zweite Messung, die den Zuschnitt bestimmt: die Kosten hängen NICHT am Limit
(90 Zeilen 14,36 s, 1200 Zeilen 14,14 s). Deshalb wird immer großzügig
gerechnet und beim Lesen zugeschnitten – jedes Weiterblättern kommt dann aus
dem Speicher statt in einen neuen 14-Sekunden-Lauf.
"""
from __future__ import annotations

import threading
from array import array
from collections import OrderedDict

GROSS = 1200          # so viele Rangplätze werden immer gerechnet
MAX_EINTRAEGE = 500   # 500 × 1200 × 16 Byte ≈ 10 MB Nutzdaten
WARTE_MAX = 25.0      # Sekunden warten, bevor selbst gerechnet wird


class Eintrag:
    """Eine Kandidatenliste, speicherschonend als zwei Zahlenfelder.

    Eine Liste aus Wörterbüchern kostet rund 240 Byte je Zeile, zwei
    array-Objekte kosten 16. Bei 500 Einträgen ist das der Unterschied
    zwischen 145 MB und 10 MB – bei 23 GB Arbeitsspeicher, von denen Qdrant
    schon 13,6 GB hält, ist das kein Detail.
    """

    __slots__ = ("rids", "punkte", "bis")

    def __init__(self, rohe, bis: int):
        self.rids = array("q", [r["rid"] for r in rohe])
        self.punkte = array("d", [r["score"] for r in rohe])
        self.bis = bis          # mit diesem Limit wurde gerechnet

    def vollstaendig(self) -> bool:
        """Weniger Zeilen als gerechnet heißt: das sind ALLE Treffer."""
        return len(self.rids) < self.bis

    def deckt(self, limit: int) -> bool:
        """Reicht dieser Eintrag für die gewünschte Tiefe?

        Wichtig für `has_more` in der Suche: dort wird aus der Länge der
        gelieferten Liste geschlossen, ob es weitere Treffer gibt. Ein zu
        kurzer Eintrag würde also fälschlich „keine weiteren" melden.
        """
        return limit <= self.bis or self.vollstaendig()

    def liste(self, limit: int) -> list[dict]:
        n = min(limit, len(self.rids))
        return [{"rid": self.rids[i], "score": self.punkte[i]}
                for i in range(n)]


class Kandidatenspeicher:
    """Speicher mit Verdrängung nach Alter und Einzelrechner-Sperre.

    Die Sperre schützt NUR das Wörterbuch (Mikrosekunden). Die 14 Sekunden
    teure Berechnung läuft ohne Sperre – sonst stünde der ganze Dienst
    währenddessen still.

    Damit trotzdem nicht mehrere Fäden dieselbe Anfrage gleichzeitig rechnen
    (uvicorn läuft mit einem Prozess, bedient aber bis zu 40 Anfragen in
    einem Fadenbündel), trägt der erste Faden eine Ankündigung ein und die
    übrigen warten darauf. Wartende hängen nie endlos: nach `warte_max`
    rechnen sie selbst, und ein gescheiterter Rechner weckt sie im
    finally-Zweig.
    """

    def __init__(self, gross: int = GROSS, max_eintraege: int = MAX_EINTRAEGE,
                 warte_max: float = WARTE_MAX):
        self._sperre = threading.Lock()
        self._eintraege: "OrderedDict[str, Eintrag]" = OrderedDict()
        self._laeuft: dict[str, threading.Event] = {}
        self.gross = gross
        self.max_eintraege = max_eintraege
        self.warte_max = warte_max
        self.treffer = 0
        self.fehltreffer = 0

    # ---------------------------------------------------------- Zustand ----
    def leeren(self) -> None:
        """Alles vergessen. Nur für Tests und einen Indexwechsel gedacht."""
        with self._sperre:
            self._eintraege.clear()

    def stand(self) -> dict:
        """Kennzahlen für /health – sonst ließe sich auf dem Server nicht
        prüfen, ob der Speicher überhaupt greift."""
        with self._sperre:
            return {
                "eintraege": len(self._eintraege),
                "zeilen": sum(len(e.rids) for e in self._eintraege.values()),
                "treffer": self.treffer,
                "fehltreffer": self.fehltreffer,
            }

    # ------------------------------------------------------------ intern ---
    def _lesen(self, schluessel: str, limit: int):
        with self._sperre:
            e = self._eintraege.get(schluessel)
            if e is None or not e.deckt(limit):
                return None
            self._eintraege.move_to_end(schluessel)      # zuletzt benutzt
            self.treffer += 1
            return e.liste(limit)

    def _schreiben(self, schluessel: str, rohe, bis: int) -> None:
        with self._sperre:
            alt = self._eintraege.get(schluessel)
            # Einen tieferen Eintrag nie durch einen flacheren ersetzen –
            # sonst könnte der Notweg unten eine bereits erarbeitete lange
            # Blätterliste gegen eine kurze tauschen.
            if alt is None or bis >= alt.bis or alt.vollstaendig():
                self._eintraege[schluessel] = Eintrag(rohe, bis)
            self._eintraege.move_to_end(schluessel)
            while len(self._eintraege) > self.max_eintraege:
                self._eintraege.popitem(last=False)      # ältester fliegt
    # ----------------------------------------------------------- Zugriff ---

    def hole(self, schluessel: str, limit: int, rechne) -> list[dict]:
        """Kandidatenliste zum Schlüssel.

        `rechne(n)` liefert die besten n Zeilen als [{"rid":…, "score":…}]
        und wird nur gerufen, wenn der Speicher nicht ausreicht.
        """
        fertig = self._lesen(schluessel, limit)
        if fertig is not None:
            return fertig

        with self._sperre:
            self.fehltreffer += 1
            laeuft = self._laeuft.get(schluessel)
            ich_rechne = laeuft is None
            if ich_rechne:
                laeuft = self._laeuft[schluessel] = threading.Event()

        if not ich_rechne:
            # Ein anderer Faden rechnet dasselbe gerade. Warten ist billiger
            # als ein zweiter 14-Sekunden-Lauf.
            laeuft.wait(self.warte_max)
            fertig = self._lesen(schluessel, limit)
            if fertig is not None:
                return fertig
            # Notweg: der andere ist gescheitert oder hat zu flach gerechnet.

        gerechnet = max(limit, self.gross)
        try:
            rohe = rechne(gerechnet)
        finally:
            if ich_rechne:
                with self._sperre:
                    if self._laeuft.get(schluessel) is laeuft:
                        del self._laeuft[schluessel]
                # Wartende IMMER wecken, auch wenn die Rechnung scheitert –
                # sonst hängen sie bis zur Wartegrenze.
                laeuft.set()
        self._schreiben(schluessel, rohe, gerechnet)
        return rohe[:limit]
