# -*- coding: utf-8 -*-
"""Zerlegt seitenweisen Text in Suchabschnitte (Passagen).

Wichtig: Jede Passage kennt ihren Seitenbereich (page_from/page_to),
damit Suchtreffer exakte Seitenangaben liefern.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Satzenden: arabische und lateinische Interpunktion
_SENT_END = re.compile(r"(?<=[.!?؟۔۔])\s+|\n{2,}")

# Buchstaben (arabisch + lateinisch) zum Messen von echtem Inhalt
_LETTERS = re.compile(r"[ء-يA-Za-z]")

TARGET_CHARS = 700    # Zielgröße einer Passage
MAX_CHARS = 1100      # harte Obergrenze
MIN_LETTERS = 20      # Passagen mit weniger echten Buchstaben verwerfen


@dataclass
class Passage:
    idx: int
    page_from: int
    page_to: int
    text: str


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_END.split(text)]
    return [p for p in parts if p]


def chunk_pages(pages: list[tuple[int, str]]) -> list[Passage]:
    """pages: Liste von (seitenzahl, seitentext). Liefert Passagen.

    Passagen überschreiten nie eine Seitengrenze – damit ist jede
    Seitenangabe in den Suchergebnissen exakt.
    """
    passages: list[Passage] = []

    for page_no, text in pages:
        buf: list[str] = []
        size = 0

        def flush() -> None:
            nonlocal buf, size
            if buf:
                text = " ".join(buf).strip()
                # Leere/inhaltsarme Schnipsel (Seitenzahlen, Trennlinien,
                # kaputte Extraktionsreste) nicht indexieren
                if len(_LETTERS.findall(text)) >= MIN_LETTERS:
                    passages.append(Passage(
                        idx=len(passages),
                        page_from=page_no,
                        page_to=page_no,
                        text=text,
                    ))
            buf, size = [], 0

        for sentence in _sentences(text):
            # Überlange Einzelsätze hart teilen
            while len(sentence) > MAX_CHARS:
                head, sentence = sentence[:MAX_CHARS], sentence[MAX_CHARS:]
                buf.append(head)
                flush()
            if size + len(sentence) > TARGET_CHARS and buf:
                flush()
            buf.append(sentence)
            size += len(sentence) + 1

        flush()

    return passages
