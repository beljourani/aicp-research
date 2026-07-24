# -*- coding: utf-8 -*-
"""Tests der Absatz-Aufbereitung (textlayout.py).

Deckt beide Wege ab: die Geometrie (Zeilen mit Position) und den reinen
Textweg, der für bereits eingelesene Bücher benutzt wird.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine.textlayout import (clean_text, join_wrapped_lines,
                                    letter_count, paragraphs_from_boxes,
                                    paragraphs_from_groups)


def test_clean_text():
    # Der alte Fehler: der Zeichenbereich reichte bis über die arabisch-
    # indischen Ziffern hinaus und hat das Leerzeichen davor gefressen.
    assert clean_text("سورة الحشر ١٨") == "سورة الحشر ١٨"
    assert clean_text("الآية ٢٥ من السورة") == "الآية ٢٥ من السورة"

    # Leerzeichen zwischen Buchstabe und Vokalzeichen gehört weg
    assert clean_text("كت َاب") == "كتَاب"
    # auch ein Umbruch an dieser Stelle
    assert clean_text("كت\nَاب") == "كتَاب"

    # NFKC löst arabische Präsentationsformen auf (hier: Ligatur Lam-Alif)
    assert clean_text("ﻻ") == "لا"

    # Leerzeichenketten und Leerzeilen zusammenfassen, Zeilen trimmen
    assert clean_text("a   b\n\n\n\nc  \n  d") == "a b\n\nc\nd"
    assert clean_text("  \n\n  ") == ""
    assert clean_text("") == ""

    # unsichtbarer Müll verschwindet, ZWNJ und RLM bleiben
    assert clean_text("a​b") == "ab"
    assert clean_text("a‌b") == "a‌b"
    assert clean_text("a‏ب") == "a‏ب"
    print("OK  clean_text: Ziffern, Vokalzeichen, Leerraum")


def test_join_wrapped_lines():
    # Volle Zeilen sind Umbrüche innerhalb eines Absatzes – auch wenn eine
    # davon mit einem Punkt endet. Erst die kurze Zeile beendet den Absatz.
    text = ("Dies ist eine ganze Zeile die bis zum Rand laeuft und dort\n"
            "umgebrochen wird weil der Satz noch weiter geht und geht.\n"
            "Kurzer Schluss.\n"
            "Hier faengt der zweite Absatz an und laeuft ebenfalls bis zum\n"
            "Rand der Seite und wird dann wieder ganz normal umgebrochen.\n"
            "Ende.")
    out = join_wrapped_lines(text)
    absaetze = out.split("\n\n")
    assert len(absaetze) == 2, absaetze
    assert absaetze[0].startswith("Dies ist eine ganze Zeile")
    assert absaetze[0].endswith("Kurzer Schluss.")
    assert "\n" not in absaetze[0]
    assert absaetze[1].startswith("Hier faengt der zweite Absatz")

    # Leerzeile trennt immer
    assert len(join_wrapped_lines("Erster Absatz.\n\nZweiter Absatz."
                                  ).split("\n\n")) == 2

    # Aufzählungen beginnen einen eigenen Absatz
    liste = ("Einleitungssatz der bis zum Rand der Zeile laeuft und dann\n"
             "- erster Punkt\n"
             "- zweiter Punkt")
    assert len(join_wrapped_lines(liste).split("\n\n")) == 3

    # Reine Ziffernzeilen (Seitenzahl, Kolumnentitel) bleiben eigenständig
    seite = ("Ein Textabsatz der bis zum Rand der Zeile laeuft und danach\n"
             "noch weitergeht bis er irgendwann einmal zu Ende ist hier.\n"
             "123")
    teile = join_wrapped_lines(seite).split("\n\n")
    assert teile[-1] == "123", teile

    # Lateinischer Trennstrich wird aufgeloest
    getrennt = ("Ein ziemlich langer Satz der hier mitten im Wort umge-\n"
                "brochen wird und danach normal weiterlaeuft bis zum Ende.")
    assert "umgebrochen" in join_wrapped_lines(getrennt)

    assert join_wrapped_lines("") == ""
    print("OK  join_wrapped_lines: Absätze aus reinem Text")


def test_join_wrapped_lines_laesst_absaetze_in_ruhe():
    """Steht je Zeile schon ein ganzer Absatz (Word-Notlösung, manche
    TXT-Dateien), darf nichts zusammengezogen werden."""
    text = ("Kurze Ueberschrift\n"
            "Ein sehr langer Absatz der in einer einzigen Zeile gespeichert "
            "ist und deshalb viel laenger ausfaellt als alle anderen Zeilen "
            "auf dieser Seite, was ihn klar als eigenen Absatz ausweist.\n"
            "Noch ein Satz.\n"
            "Und ein weiterer sehr langer Absatz der ebenfalls komplett in "
            "einer Zeile steht und daher nicht angetastet werden darf.")
    out = join_wrapped_lines(text)
    assert out.count("\n") == 3, out
    assert "\n\n" not in out
    assert out.startswith("Kurze Ueberschrift\n")
    print("OK  bereits absatzweiser Text bleibt unverändert")


def test_letter_count_invariant():
    """Die Aufbereitung darf nur Weißraum verändern – die Sicherung der
    einmaligen Nachbesserung verlässt sich darauf."""
    proben = [
        "الحمد لله رب العالمين\nوالصلاة والسلام على رسول الله\nصلى الله عليه",
        "سورة الحشر ١٨\n\nقال تعالى: يا أيها الذين آمنوا اتقوا الله",
        "Ein deutscher Text\nmit mehreren   Zeilen\n\nund einem Absatz.",
        "كت َاب",
        "",
    ]
    for p in proben:
        assert letter_count(join_wrapped_lines(p)) == letter_count(p), repr(p)
        assert letter_count(clean_text(p)) == letter_count(p), repr(p)
    print("OK  Buchstabenzahl bleibt erhalten")


def _zeile(text, x0, y0, x1, y1):
    return (text, float(x0), float(y0), float(x1), float(y1))


def test_paragraphs_from_boxes_rtl():
    # Arabische Seite, rechter Rand bei x=500, linker bei x=100.
    # Zeile 3 endet kurz (linke Kante bei 380) -> Absatzende.
    lines = [
        _zeile("الحمد لله رب العالمين وبه", 100, 100, 500, 120),
        _zeile("نستعين على أمور الدنيا", 100, 130, 500, 150),
        _zeile("والدين", 380, 160, 500, 180),
        _zeile("وصلى الله على نبينا محمد", 100, 190, 500, 210),
        _zeile("وعلى آله وصحبه أجمعين", 100, 220, 500, 240),
    ]
    out = paragraphs_from_boxes(lines)
    absaetze = out.split("\n\n")
    assert len(absaetze) == 2, absaetze
    assert absaetze[0].endswith("والدين"), absaetze[0]
    assert "\n" not in absaetze[0]
    assert absaetze[1].startswith("وصلى الله")
    print("OK  Geometrie: kurze Schlusszeile beendet den Absatz (RTL)")


def test_paragraphs_from_boxes_gap():
    # Alle Zeilen laufen bis zum Rand; nur der große vertikale Abstand
    # zwischen Zeile 2 und 3 trennt die Absätze.
    lines = [
        _zeile("الحمد لله رب العالمين وبه", 100, 100, 500, 120),
        _zeile("نستعين على أمور الدنيا كلها", 100, 130, 500, 150),
        _zeile("وصلى الله على نبينا محمد", 100, 260, 500, 280),
        _zeile("وعلى آله وصحبه أجمعين هنا", 100, 290, 500, 310),
    ]
    absaetze = paragraphs_from_boxes(lines).split("\n\n")
    assert len(absaetze) == 2, absaetze
    print("OK  Geometrie: großer Zeilenabstand trennt Absätze")


def test_paragraphs_from_boxes_columns():
    # Zwei Spalten: rechte Spalte (x 300-500) wird zuerst gelesen, sie darf
    # sich nicht mit der linken (x 50-250) verschachteln.
    lines = [
        _zeile("يمين واحد", 300, 100, 500, 120),
        _zeile("يسار واحد", 50, 100, 250, 120),
        _zeile("يمين اثنان", 300, 130, 500, 150),
        _zeile("يسار اثنان", 50, 130, 250, 150),
    ]
    out = paragraphs_from_boxes(lines)
    assert out.index("يمين واحد") < out.index("يمين اثنان")
    assert out.index("يمين اثنان") < out.index("يسار واحد"), out
    print("OK  Geometrie: Spalten laufen nicht ineinander")


def test_paragraphs_from_boxes_ltr():
    # Dieselbe Logik gespiegelt für lateinischen Text
    lines = [
        _zeile("This is a line that runs to the right margin here", 100, 100, 500, 120),
        _zeile("and continues on the following line until it ends", 100, 130, 500, 150),
        _zeile("short end.", 100, 160, 200, 180),
        _zeile("A second paragraph starts here and runs on again", 100, 190, 500, 210),
    ]
    absaetze = paragraphs_from_boxes(lines).split("\n\n")
    assert len(absaetze) == 2, absaetze
    assert absaetze[0].endswith("short end.")
    print("OK  Geometrie: gleiche Logik gespiegelt für Latein (LTR)")


def test_paragraphs_from_boxes_rand():
    assert paragraphs_from_boxes([]) == ""
    assert paragraphs_from_boxes([_zeile("  ", 0, 0, 1, 1)]) == ""
    assert paragraphs_from_boxes([_zeile("nur eine", 0, 0, 1, 1)]) == "nur eine"
    print("OK  Geometrie: leere und einzeilige Seiten")


def test_paragraphs_from_groups():
    # Tesseract liefert die Absätze selbst -> keine Heuristik nötig
    out = paragraphs_from_groups([
        ["الحمد لله رب", "العالمين"],
        ["وصلى الله على", "نبينا محمد"],
    ])
    assert out == "الحمد لله رب العالمين\n\nوصلى الله على نبينا محمد"
    assert paragraphs_from_groups([[], ["  "]]) == ""
    print("OK  Absätze aus den Gruppen der OCR-Engine")


def test_tesseract_tsv():
    """Die TSV-Ausgabe von Tesseract enthält die Absätze der OCR-Engine
    selbst (block_num/par_num) – der Parser muss sie sauber übernehmen."""
    from echo_engine.extract import _tesseract_tsv_to_text

    kopf = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext")
    zeilen = [kopf,
              "1\t1\t0\t0\t0\t0\t0\t0\t600\t800\t-1\t",       # Seiten-Ebene
              "5\t1\t1\t1\t1\t1\t10\t10\t40\t20\t96\tالحمد",
              "5\t1\t1\t1\t1\t2\t60\t10\t30\t20\t95\tلله",
              "5\t1\t1\t1\t2\t1\t10\t40\t50\t20\t93\tالعالمين",
              "5\t1\t1\t1\t2\t2\t70\t40\t30\t20\t-1\txx",     # conf<0 -> weg
              "5\t1\t1\t2\t1\t1\t10\t80\t40\t20\t97\tوصلى",
              "5\t1\t2\t1\t1\t1\t10\t120\t40\t20\t90\tالله"]
    out = _tesseract_tsv_to_text("\n".join(zeilen))
    assert out == "الحمد لله العالمين\n\nوصلى\n\nالله", repr(out)
    assert _tesseract_tsv_to_text(kopf) == ""
    assert _tesseract_tsv_to_text("") == ""
    print("OK  Tesseract-TSV: Absätze aus block_num/par_num")


if __name__ == "__main__":
    test_clean_text()
    test_join_wrapped_lines()
    test_join_wrapped_lines_laesst_absaetze_in_ruhe()
    test_letter_count_invariant()
    test_paragraphs_from_boxes_rtl()
    test_paragraphs_from_boxes_gap()
    test_paragraphs_from_boxes_columns()
    test_paragraphs_from_boxes_ltr()
    test_paragraphs_from_boxes_rand()
    test_paragraphs_from_groups()
    test_tesseract_tsv()
    print("\nAlle Textlayout-Tests bestanden.")
