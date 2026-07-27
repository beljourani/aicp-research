# -*- coding: utf-8 -*-
"""Blätter einer Online-Quelle in Seiten der lokalen Bibliothek übersetzen.

Reine Umrechnung – ohne Netz, ohne Datenbank, ohne Oberfläche. Dadurch lässt
sich der einzige nicht triviale Teil des Übernehmens überall prüfen
(engine/tests/test_shamela_pages.py), auch dort, wo der Server nicht läuft.

Zwei Zahlenwelten treffen hier aufeinander:

* **Blattnummer** (`page_no`) – lückenlos 1..N in Lesereihenfolge. Der Leser
  setzt Lückenlosigkeit voraus (Höhenmodell, Seitensprung, Fensterlogik).
* **Druckseite** (`page_label`) – was tatsächlich im Buch steht, z. B.
  „ج1 ص441". Sie ist es, die angezeigt und zitiert wird.

Beide auseinanderzuhalten ist nötig, weil ein Viertel der Bücher mehrbändig
ist und jeder Band wieder bei Seite 1 beginnt – als Blattnummer wäre das
mehrdeutig, und die Eindeutigkeitsbedingung von `pages` bräche.
"""
from __future__ import annotations


def seiten_bezeichnung(part, page_num, page_key: str | None) -> str | None:
    """Die angezeigte Druckseite: „ج1 ص441", „ص441" – oder nichts.

    Spiegelt `shamelaPageLabel()` in app/ui/index.html. Die Beschriftung
    entsteht hier EINMAL und wird gespeichert; Leser, Trefferliste und Zitat
    geben sie nur noch aus und können deshalb nicht auseinanderlaufen.

    Fehlt die Seitennummer, wird auf die Rohkennung der Quelle
    zurückgegriffen – so bleibt auch bei ungewöhnlichen Formen (benannter
    Vorspann, Sure:Vers) etwas Zitierfähiges übrig.
    """
    num = page_num if page_num not in (None, "") else (page_key or "")
    if num in (None, ""):
        return None
    teil = str(part).strip() if part not in (None, "") else ""
    return f"ج{teil} ص{num}" if teil else f"ص{num}"


def blaetter_zu_seiten(blaetter, versatz: int = 0) -> list[tuple]:
    """Serverantwort -> [(page_no, text, page_label, page_key)].

    `versatz` ist die Zahl der bereits übernommenen Blätter; die Blattnummer
    bleibt dadurch über alle Blöcke hinweg lückenlos. Sie wird bewusst aus
    der Position abgeleitet und nicht aus der Blattnummer des Servers – so
    ist die lokale Reihe auch dann lückenlos, wenn der Server einmal etwas
    anderes liefert.
    """
    raus = []
    for i, b in enumerate(blaetter, start=versatz + 1):
        key = (b.get("page_str") or "") or None
        raus.append((i, b.get("text") or "",
                     seiten_bezeichnung(b.get("part"), b.get("page_num"), key),
                     key))
    return raus


def folge_ist_lueckenlos(blaetter, versatz: int = 0) -> bool:
    """Stimmt die Blattfolge des Servers mit der Erwartung überein?

    Wird beim Übernehmen geprüft: eine Lücke hiesse, dass Seiten fehlen,
    ohne dass es auffiele – das Buch wäre still unvollständig.
    """
    erwartet = list(range(versatz + 1, versatz + len(blaetter) + 1))
    return [b.get("seq") for b in blaetter] == erwartet
