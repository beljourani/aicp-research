# -*- coding: utf-8 -*-
"""Gegenprobe: Erzwungene eigene Schriften -> stimmen die Seitenzahlen?"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

BOOKS = Path.home() / "Downloads" / "AICP Research-Buecher"
DOCX = BOOKS / "شرح-الشيخ-جيل-لكتاب-عمدة-الراغب-النسخة-الرابعة.docx"
PDF = BOOKS / "شرح-الشيخ-جيل-لكتاب-عمدة-الراغب-النسخة-الرابعة.pdf"


def convert(src: Path, soffice: str, tmp: str) -> int | None:
    subprocess.run([soffice, "--headless", "--norestore", "--invisible",
                    "--convert-to", "pdf", "--outdir", tmp, str(src)],
                   capture_output=True, timeout=1200)
    out = Path(tmp) / (src.stem + ".pdf")
    if not out.exists():
        return None
    import fitz
    with fitz.open(out) as d:
        return len(d)


def main():
    import fitz
    from echo_engine.components import (ensure_fonts,
                                        install_fonts_into_converter,
                                        find_soffice)
    from echo_engine.extract import _force_own_fonts

    with fitz.open(PDF) as d:
        soll = len(d)
    print(f"Original-PDF (Referenz):        {soll} Seiten\n")

    print("Schriften bereitstellen …")
    fd = ensure_fonts(lambda s: print("  ", s))
    have = sorted(f.name for f in fd.glob("*.ttf"))
    print("  geladen:", have or "KEINE – Download fehlgeschlagen!")
    if not have:
        return

    soffice = find_soffice(auto_install=True, progress=lambda s: print("  ", s))
    print("Konverter:", soffice)
    if not soffice:
        return
    install_fonts_into_converter(soffice)
    print("  Schriften in den Konverter kopiert\n")

    with tempfile.TemporaryDirectory() as tmp:
        print("A) OHNE erzwungene Schriften (alter Weg) …")
        a = convert(DOCX, soffice, tmp)
        print(f"   → {a} Seiten  (Abweichung: {abs(a-soll) if a else '?'} )\n")

        print("B) MIT erzwungenen eigenen Schriften (neuer Weg) …")
        prepared = Path(tmp) / "forced.docx"
        _force_own_fonts(DOCX, prepared)
        b = convert(prepared, soffice, tmp)
        print(f"   → {b} Seiten  (Abweichung: {abs(b-soll) if b else '?'} )\n")

    print("=" * 58)
    print(f"Original-PDF:            {soll} Seiten")
    print(f"Alt (Systemschriften):   {a} Seiten")
    print(f"Neu (eigene Schriften):  {b} Seiten")
    print("=" * 58)
    print("\nWichtig: 'Neu' muss auf JEDEM Gerät dieselbe Zahl liefern –")
    print("das ist der Zweck. Ob sie exakt der Druckausgabe entspricht,")
    print("hängt davon ab, ob die Original-Schrift nachgebildet werden kann.")


if __name__ == "__main__":
    main()
