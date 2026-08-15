# -*- coding: utf-8 -*-
"""Ersatzweg zum Lesen von PDF-Dateien – ohne native Bibliothek.

Warum es das gibt: Der Hauptweg (PyMuPDF) ist eine kompilierte Bibliothek.
Lässt sie sich auf einem Gerät nicht laden – blockierte oder in Quarantäne
verschobene DLL, beschädigte Installation, ungewöhnliche Windows-Ausstattung –,
dann war bisher JEDE PDF-Datei unlesbar, während Word-Dateien weiter gingen.
Genau dieses Muster trat auf einem fremden Rechner auf.

`pypdf` ist reines Python und hat keinerlei native Anteile. Dieser Weg liefert
deshalb auf jedem Gerät ein Ergebnis. Er ist bewusst NUR die zweite Wahl:

* Seitenzahlen bleiben **exakt** – die Seitengrenzen stehen im PDF selbst,
  es wird nichts neu umbrochen. Das Zitierversprechen der App bleibt gültig.
* Die Textqualität ist geringer: es gibt keine Zeilengeometrie, also werden
  Absätze aus dem Zeilenumbruch geschätzt (`join_wrapped_lines`), und
  mehrspaltige Seiten können durcheinandergeraten. Darum wird das Ergebnis
  ausdrücklich als solches gekennzeichnet.
"""
from __future__ import annotations

from pathlib import Path

from .textlayout import clean_text, join_wrapped_lines


def verfuegbar() -> bool:
    """Ist der Ersatzweg auf diesem Gerät benutzbar?"""
    try:
        import pypdf  # noqa: F401
        return True
    except Exception:
        return False


def seiten_lesen(path: Path, progress=None) -> list[tuple[int, str]]:
    """Liest eine PDF-Datei seitenweise. Liefert [(seitenzahl, text)].

    Wirft nur, wenn die Datei gar nicht zu öffnen ist (kaputt, kein PDF,
    passwortgeschützt) – dann greift dieselbe Fehlerbehandlung wie sonst.
    Eine einzelne unlesbare Seite kostet nur diese Seite.
    """
    from pypdf import PdfReader

    leser = PdfReader(str(path))
    # Verschlüsselt, aber ohne echtes Benutzerpasswort: das kommt häufig vor
    # (nur Rechte-Beschränkung) und ist ganz normal lesbar.
    if getattr(leser, "is_encrypted", False):
        try:
            leser.decrypt("")
        except Exception:
            pass

    seiten: list[tuple[int, str]] = []
    gesamt = len(leser.pages)
    for i in range(gesamt):
        try:
            roh = leser.pages[i].extract_text() or ""
            text = clean_text(join_wrapped_lines(roh))
        except Exception:
            text = ""
        seiten.append((i + 1, text))
        if progress:
            progress("verarbeite", i + 1, gesamt, "verarbeite")
    return seiten
