# -*- coding: utf-8 -*-
"""End-to-End-Tests: Normalisierung, Konjugations-Suche, Seitenzahlen."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from echo_engine import connect, index_pages, search, normalize, stem


def test_normalize():
    # Tashkil entfernen, Alif-Varianten, Ta Marbuta
    assert normalize("كَتَبَ") == "كتب"
    assert normalize("أحمد") == "احمد"
    assert normalize("إسلام") == "اسلام"
    assert normalize("مكتبة") == "مكتبه"
    assert normalize("مصطفى") == "مصطفي"
    assert normalize("٥ صفحات") == "5 صفحات"
    print("OK  Normalisierung")


def test_stemming():
    # Alle Konjugationen von كتب müssen auf dieselbe Wurzel fallen
    forms = ["كتب", "يكتب", "كتبت", "يكتبون", "تكتبين", "المكتوب", "كاتب"]
    stems = {stem(normalize(f)) for f in forms}
    print("    Stämme:", stems)
    assert stem(normalize("يكتب")) == stem(normalize("كتب"))
    assert stem(normalize("كتبت")) == stem(normalize("كتب"))
    assert stem(normalize("يكتبون")) == stem(normalize("كتب"))
    print("OK  Stemming (Konjugationen -> gemeinsame Wurzel)")


def test_search_with_pages():
    con = connect(":memory:")

    # Buch 1: Verschiedene Konjugationen von كتب auf verschiedenen Seiten
    book1 = [
        (1, "في هذا الفصل نتحدث عن تاريخ العلم. " * 3),
        (2, "كان الإمام يكتب الرسائل كل يوم في الصباح الباكر. " * 2),
        (3, "وقد كتبت المؤلفة عدة مؤلفات في هذا الباب. " * 2),
        (4, "الرجال يكتبون والنساء يكتبن في المجالس العلمية. " * 2),
        (5, "هذه صفحة عن الطبخ والطعام لا علاقة لها بالموضوع. " * 3),
    ]
    index_pages(con, book1, title="تاريخ التأليف", author="ابن خلدون")

    # Buch 2: enthält das Wort nur einmal
    book2 = [
        (1, "مقدمة عامة عن الفقه والأصول. " * 4),
        (2, "ثم كَتَبَ العالمُ شرحاً مفصلاً على المتن. " * 2),
    ]
    index_pages(con, book2, title="شرح المتون", author="النووي")

    # Suche mit der Grundform كتب -> muss يكتب/كتبت/يكتبون/كَتَبَ finden
    hits = search(con, "كتب")
    assert hits, "Keine Treffer!"
    pages_found = {(h.title, h.page_from) for h in hits}
    print(f"    {len(hits)} Treffer:")
    for h in hits:
        loc = (f"S. {h.page_from}" if h.page_from == h.page_to
               else f"S. {h.page_from}-{h.page_to}")
        print(f"      [{h.title} / {h.author}, {loc}] "
              f"Wörter: {h.matched_words} :: {h.snippet[:60]}…")

    assert ("تاريخ التأليف", 2) in pages_found, "يكتب auf S.2 nicht gefunden"
    assert ("تاريخ التأليف", 3) in pages_found, "كتبت auf S.3 nicht gefunden"
    assert ("تاريخ التأليف", 4) in pages_found, "يكتبون auf S.4 nicht gefunden"
    assert ("شرح المتون", 2) in pages_found, "كَتَبَ (mit Tashkil) nicht gefunden"
    # Die Kochseite (S.5) darf NICHT auftauchen
    assert ("تاريخ التأليف", 5) not in pages_found, "Falscher Treffer S.5"
    print("OK  Suche: Konjugationen + Tashkil + korrekte Seitenzahlen")

    # Autorenfilter
    hits_nawawi = search(con, "كتب", author="النووي")
    assert all(h.author == "النووي" for h in hits_nawawi)
    print("OK  Autorenfilter")

    # Blättern ohne Suchbegriff
    browse = search(con, "", document_id=1)
    assert browse and browse[0].title == "تاريخ التأليف"
    print("OK  Blättern ohne Suchbegriff")


if __name__ == "__main__":
    test_normalize()
    test_stemming()
    test_search_with_pages()
    print("\nAlle Tests bestanden.")
