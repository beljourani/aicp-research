# -*- coding: utf-8 -*-
"""Test: wurzelbewusste Markierung gegen den tatsächlichen Seitentext.

Behebt den Bug, dass beim Öffnen eines Treffers zwar die richtige Seite
angezeigt, die Wörter aber nicht markiert wurden. highlight_spans muss ALLE
Flexionen einer Wurzel auf einer Seite treffen – auch mit Tashkil.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine.search import highlight_spans, stems_of_terms


def test_spans_find_all_inflections():
    # Eine ganze "Seite" mit verschiedenen Konjugationen von كتب, dazwischen
    # unbeteiligte Wörter, plus eine Form mit Tashkil (كَتَبَ).
    page = ("كان الإمام يكتب الرسائل ثم كتبت المؤلفة وكان الرجال يكتبون "
            "بينما جلس الطبيب هنا وقد كَتَبَ العالم شرحا")
    spans = highlight_spans(page, ["كتب"])
    words = [page[s:e] for s, e in spans]
    print("    markiert:", words)

    # Alle vier Flexionen müssen markiert sein
    for form in ("يكتب", "كتبت", "يكتبون", "كَتَبَ"):
        assert any(form == w for w in words), f"{form} nicht markiert"
    # Unbeteiligte Wörter dürfen NICHT markiert sein
    for other in ("الطبيب", "جلس", "هنا"):
        assert other not in words, f"{other} fälschlich markiert"
    # Positionen müssen echte Teilstrings des Seitentexts sein
    for s, e in spans:
        assert 0 <= s < e <= len(page)
    print("OK  highlight_spans trifft alle Flexionen (inkl. Tashkil)")


def test_empty_terms_no_spans():
    assert highlight_spans("أي نص هنا", []) == []
    assert highlight_spans("أي نص هنا", None) == []
    assert stems_of_terms([]) == set()
    # Mehrwortiger Begriff wird tokenweise zu Wurzeln
    assert stems_of_terms(["دار الكتب"]) == {
        s for s in stems_of_terms(["دار", "الكتب"])}
    print("OK  leere/mehrwortige Begriffe korrekt behandelt")



def test_kurzes_wort_nur_ganzwoertig():
    """Kurze Wörter dürfen nicht INNERHALB längerer Wörter markiert werden.

    'لا' steckt als Zeichenfolge in 'الكلام' – der frühere wörtliche
    Vergleich im Browser markierte es dort mit. Die wurzelbewusste
    Markierung arbeitet auf ganzen Wörtern und tut das nicht.
    """
    text = "الكلام في الجهات الست لا يخلو من إشكال"
    spans = highlight_spans(text, ["لا"])
    markiert = [text[a:b] for a, b in spans]
    assert markiert == ["لا"], f"erwartet nur das eigene Wort, war {markiert}"
    # Gegenprobe: die Fundstelle liegt NICHT im Wort الكلام
    kl = text.index("الكلام")
    assert all(not (kl <= a < kl + len("الكلام")) for a, b in spans), \
        "لا wurde innerhalb von الكلام markiert"
    print("ok  test_kurzes_wort_nur_ganzwoertig")


def test_alle_begriffe_ganzwoertig():
    """Mehrere Begriffe: jeder nur als ganzes Wort bzw. Beugung."""
    text = "الجهات الست لا تخلو والجهة الواحدة كذلك"
    spans = highlight_spans(text, ["الجهات", "الست", "لا"])
    markiert = [text[a:b] for a, b in spans]
    assert "الجهات" in markiert and "الست" in markiert and "لا" in markiert, markiert
    # 'لا' darf nicht in 'تخلو' markiert sein
    tx = text.index("تخلو")
    assert all(not (tx <= a < tx + len("تخلو")) for a, b in spans), markiert
    print("ok  test_alle_begriffe_ganzwoertig")


if __name__ == "__main__":
    test_spans_find_all_inflections()
    test_empty_terms_no_spans()
    test_kurzes_wort_nur_ganzwoertig()
    test_alle_begriffe_ganzwoertig()
    print("\nAlle Highlight-Tests bestanden.")
