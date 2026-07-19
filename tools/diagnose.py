# -*- coding: utf-8 -*-
"""Word→PDF-Diagnose. Schreibt Klartext-Ergebnis (wird von Claude gelesen).

Für jede Word-Datei: konvertiert sie über die APP-PIPELINE und vergleicht
die Seitenzahl mit dem, was Word bzw. das PDF-Gegenstück sagt.
"""
from __future__ import annotations

import sys
import zipfile
import re
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import fitz
from echo_engine.extract import (convert_docx_to_pdf, convert_with_word,
                                 _word_installed)

BOOKS = Path.home() / "Downloads" / "AICP Research-Buecher"


def word_pages(docx: Path) -> int | None:
    """Was Word selbst in die Datei geschrieben hat (Metadaten)."""
    try:
        with zipfile.ZipFile(docx) as z:
            app = z.read("docProps/app.xml").decode("utf-8", "replace")
        m = re.search(r"<Pages>(\d+)</Pages>", app)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def main():
    print("AICP Research – Word→PDF Diagnose")
    print("Zeit:", time.strftime("%Y-%m-%d %H:%M"))
    print("=" * 68)

    docs = sorted(BOOKS.glob("*.docx"))
    if not docs:
        print("Keine Word-Dateien in", BOOKS)
        return

    print("Word installiert:", "JA" if _word_installed() else "NEIN")
    print()
    print(f"{'DATEI':30s}{'PDF':>6s}{'Word-Engine':>12s}{'LibreOffice':>13s}")
    print("-" * 68)
    import tempfile

    def count(fn, d):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = fn(d, Path(tmp))
                if out:
                    with fitz.open(out) as doc:
                        return len(doc)
        except Exception as e:
            return f"Fehler:{str(e)[:15]}"
        return None

    for d in docs:
        pdf_sibling = d.with_suffix(".pdf")
        pp = None
        if pdf_sibling.exists():
            with fitz.open(pdf_sibling) as doc:
                pp = len(doc)
        w = count(convert_with_word, d) if _word_installed() else "—"
        lo = count(lambda p, o: convert_docx_to_pdf(p, o,
                   progress=lambda s: None), d)
        print(f"{d.name[:28]:30s}{str(pp or '—'):>6s}"
              f"{str(w):>12s}{str(lo):>13s}")

    print("-" * 68)
    print("\nPDF = gedrucktes Gegenstück (Referenz)")
    print("Word-Engine = mit lokalem Word gewandelt (soll exakt sein)")
    print("LibreOffice = Notlösung (kann abweichen)")


if __name__ == "__main__":
    main()
