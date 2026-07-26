# -*- coding: utf-8 -*-
"""Tests für den Export und Import einer Bibliothek (.echolib).

Die kritische Stelle ist der Suchindex: `passages_fts` ist eine contentless
FTS5-Tabelle – ihr Inhalt lässt sich nicht auslesen. Wer beim Import nur die
Zeilen kopiert, bekommt eine Bibliothek, die **nichts findet**, ohne dass
irgendetwas nach einem Fehler aussieht. Der Index muss deshalb aus dem
gespeicherten Passagentext neu berechnet werden. Genau das prüfen diese
Tests.

Aufruf:  python3 engine/tests/test_library_io.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from echo_engine import connect, search                          # noqa: E402
from echo_engine.indexer import index_pages                      # noqa: E402
from echo_engine.library_io import export_library, import_library  # noqa: E402


def _quelle(pfad: Path) -> tuple[int, int]:
    con = connect(str(pfad))
    a = index_pages(con, [(1, "الصبر عند البلاء جميل وهو من شيم الكرام. " * 4),
                          (2, "والحلم عند الغضب من صفات العقلاء الكرام. " * 4)],
                    title="Buch A", author="Autor Eins")
    b = index_pages(con, [(1, "الصلاة عماد الدين وهي اول ما يحاسب عليه. " * 4)],
                    title="Buch B", author="Autor Zwei ؛ Autor Drei")
    con.commit()
    con.close()
    return a, b


def test_rundlauf_findet_wieder():
    """Export -> Import: die importierte Bibliothek muss suchbar sein."""
    d = Path(tempfile.mkdtemp())
    try:
        quelle = d / "quelle.db"
        _quelle(quelle)
        paket = d / "export.echolib"
        export_library(quelle, paket)
        assert paket.exists() and paket.stat().st_size > 0, "Export ist leer"

        ziel = d / "ziel.db"
        connect(str(ziel)).close()
        dateien = d / "dateien"
        dateien.mkdir()
        import_library(ziel, paket, dateien)

        con = connect(str(ziel))
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
        # Der eigentliche Prüfpunkt: der Suchindex wurde neu berechnet.
        assert search(con, "الصبر", limit=10), "Wortsuche findet nichts"
        assert search(con, "صبر", limit=10), "Wurzelsuche findet nichts"
        assert search(con, "الصلاة", limit=10), "zweites Buch nicht auffindbar"
        con.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("ok  test_rundlauf_findet_wieder")


def test_mehrfach_autoren_bleiben():
    """Mehrere Autoren stehen in einer Spalte, getrennt durch „ ؛ "."""
    d = Path(tempfile.mkdtemp())
    try:
        quelle = d / "q.db"
        _quelle(quelle)
        paket = d / "p.echolib"
        export_library(quelle, paket)
        ziel = d / "z.db"
        connect(str(ziel)).close()
        dateien = d / "f"
        dateien.mkdir()
        import_library(ziel, paket, dateien)
        con = connect(str(ziel))
        autoren = [r[0] for r in con.execute("SELECT author FROM documents")]
        assert any("؛" in (a or "") for a in autoren), autoren
        # und der Autorenfilter greift auf den zweiten Namen
        assert search(con, "الصلاة", limit=5, author=["Autor Drei"]), \
            "Zweit-Autor nicht filterbar"
        con.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("ok  test_mehrfach_autoren_bleiben")


def test_import_in_gefuellte_bibliothek():
    """Ein Import darf vorhandene Bücher nicht verlieren."""
    d = Path(tempfile.mkdtemp())
    try:
        quelle = d / "q.db"
        _quelle(quelle)
        paket = d / "p.echolib"
        export_library(quelle, paket)

        ziel = d / "z.db"
        con = connect(str(ziel))
        index_pages(con, [(1, "كتاب موجود مسبقا في المكتبة المحلية هنا. " * 4)],
                    title="Vorher da", author="X")
        con.commit()
        con.close()

        dateien = d / "f"
        dateien.mkdir()
        import_library(ziel, paket, dateien)
        con = connect(str(ziel))
        titel = {r[0] for r in con.execute("SELECT title FROM documents")}
        assert "Vorher da" in titel, f"vorhandenes Buch verloren: {titel}"
        assert {"Buch A", "Buch B"} <= titel, f"Import unvollständig: {titel}"
        assert search(con, "موجود", limit=5), "altes Buch nicht mehr auffindbar"
        assert search(con, "الصبر", limit=5), "neues Buch nicht auffindbar"
        con.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("ok  test_import_in_gefuellte_bibliothek")


def test_auswahl_exportieren():
    """Nur ausgewählte Bücher exportieren."""
    d = Path(tempfile.mkdtemp())
    try:
        quelle = d / "q.db"
        a, _b = _quelle(quelle)
        paket = d / "p.echolib"
        export_library(quelle, paket, doc_ids=[a])
        ziel = d / "z.db"
        connect(str(ziel)).close()
        dateien = d / "f"
        dateien.mkdir()
        import_library(ziel, paket, dateien)
        con = connect(str(ziel))
        titel = {r[0] for r in con.execute("SELECT title FROM documents")}
        assert titel == {"Buch A"}, f"Auswahl nicht beachtet: {titel}"
        con.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("ok  test_auswahl_exportieren")


if __name__ == "__main__":
    test_rundlauf_findet_wieder()
    test_mehrfach_autoren_bleiben()
    test_import_in_gefuellte_bibliothek()
    test_auswahl_exportieren()
    print("\nAlle Tests bestanden.")
