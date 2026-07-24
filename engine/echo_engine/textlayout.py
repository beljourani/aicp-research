# -*- coding: utf-8 -*-
"""Aufbereitung von Seitentext zu lesbaren Absätzen.

Das Modul kennt bewusst weder PyMuPDF noch OCR – es arbeitet nur auf Text
bzw. auf Zeilen mit Positionsangaben. Dadurch ist es vollständig testbar
(siehe engine/tests/test_textlayout.py).

Zwei Ebenen:

1. ``paragraphs_from_boxes()`` / ``paragraphs_from_groups()`` – der genaue
   Weg. Aus den Positionen der Zeilen (PDF-Textschicht, Apple Vision) bzw.
   aus den Absatzangaben der OCR-Engine (Tesseract) werden die Absätze des
   Originals rekonstruiert.
2. ``clean_text()`` + ``join_wrapped_lines()`` – der reine Textweg. Wird als
   Rückfall benutzt und für bereits eingelesene Bücher, bei denen nur noch
   der gespeicherte Text vorliegt.

Ergebnisformat in allen Fällen: ein Absatz ist EINE Zeile, Absätze sind
durch eine Leerzeile getrennt. Der Leser stellt das mit ``white-space:
pre-wrap`` genau so dar.

Wichtig: Es wird ausschließlich Weißraum verändert (plus NFKC-Normalisierung
der arabischen Präsentationsformen). Seitengrenzen bleiben unangetastet –
die Seitenzahlen des Originals dürfen sich nie verschieben.
"""
from __future__ import annotations

import re
import unicodedata

# Echte kombinierende Zeichen (Tashkil + Koran-Zeichen). Bewusst OHNE die
# arabisch-indischen Ziffern ٠-٩ (U+0660-0669) und ٪-ٯ (U+066A-066F): die
# stehen zwar im selben Unicode-Block, sind aber sichtbare Zeichen. Ein zu
# weiter Bereich hat früher das Leerzeichen vor Zahlen gefressen
# ("سورة الحشر ١٨" -> "سورة الحشر١٨"). Die Bereiche werden über explizite
# Codepoints gebildet – ein Literal aus kombinierenden Zeichen ist zu
# fragil (Reihenfolge/Kodierung), genau daran ist der alte Bug entstanden.
_MARK_RANGES = (
    (0x0610, 0x061A),   # arabische Zeichen über/unter dem Buchstaben
    (0x064B, 0x065F),   # Tashkil (Fatha, Kasra, Schadda ...)
    (0x0670, 0x0670),   # hochgestelltes Alif
    (0x06D6, 0x06DC),   # kleine Koran-Zeichen
    (0x06DF, 0x06E4),
    (0x06E7, 0x06E8),
    (0x06EA, 0x06ED),
)
_MARKS = "".join(f"{chr(a)}-{chr(b)}" for a, b in _MARK_RANGES)

# Leerraum (auch Zeilenumbruch) vor einem Vokalzeichen: kaputte Textschicht
_SPACE_BEFORE_MARK = re.compile(r"\s+(?=[" + _MARKS + r"])")

# Unsichtbarer Müll aus OCR/PDF: Zero-Width-Space (U+200B), Word-Joiner
# (U+2060), BOM/Zero-Width-No-Break-Space (U+FEFF). ZWNJ (U+200C) und
# LRM/RLM (U+200E/200F) bleiben erhalten – die sind bedeutungstragend.
_INVISIBLE = re.compile("[​⁠﻿]")

# Buchstaben (arabisch + lateinisch) – zum Messen von echtem Inhalt
_LETTERS = re.compile(r"[ء-يٮ-ۓA-Za-z]")

# Satzende – zusammen mit einer nicht voll ausgeschriebenen Zeile ein
# Hinweis auf das Ende eines Absatzes
_SENT_END = re.compile(r"[.!?؟:؛۔…»\"'\)\]]\s*$")

# Zeilenanfänge, die immer einen neuen Absatz beginnen: Aufzählungen,
# Nummerierungen, Gedankenstriche
_LIST_START = re.compile(
    r"^\s*(?:[-–—•*▪]|\(?[0-9٠-٩]{1,3}[.)\-]|\[[0-9٠-٩]+\])\s")

# Zeile ohne Buchstaben (Seitenzahl, Trennlinie, Kolumnentitel aus Ziffern)
_NO_LETTERS = re.compile(r"^[^ء-يٮ-ۓA-Za-z]*$")

# Latein-Trennstrich am Zeilenende (arabischer Satz trennt Wörter nicht)
_HYPHEN_END = re.compile(r"([A-Za-z])[-‐]$")


def clean_text(text: str) -> str:
    """Repariert Zeichen- und Leerraum-Artefakte einer Seite.

    - NFKC: arabische Präsentationsformen (Ligaturen) -> normale Buchstaben
    - Leerraum, der zwischen Buchstabe und Vokalzeichen geraten ist, entfernen
    - unsichtbare Steuerzeichen entfernen
    - Leerzeichen-/Tabketten auf eines reduzieren, Zeilen trimmen
    - höchstens eine Leerzeile am Stück
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_BEFORE_MARK.sub("", text)
    lines = [re.sub(r"[^\S\n]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if not ln and out and not out[-1]:
            continue        # mehrere Leerzeilen zu einer zusammenfassen
        out.append(ln)
    return "\n".join(out).strip()


def letter_count(text: str) -> int:
    """Zahl der echten Buchstaben – Sicherung für die Nachbesserung.

    Die Aufbereitung darf nur Weißraum verändern; die Buchstabenzahl (nach
    NFKC, weil dabei Ligaturen wie ﻻ zu zwei Buchstaben werden) muss vorher
    und nachher identisch sein.
    """
    return len(_LETTERS.findall(unicodedata.normalize("NFKC", text or "")))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def _quantil(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return float(s[min(len(s) - 1, int(q * (len(s) - 1)))])


def _join_lines(lines: list[str]) -> str:
    """Zeilen eines Absatzes zusammensetzen.

    Normalerweise mit einem Leerzeichen; endet eine Zeile mit einem
    lateinischen Trennstrich, wird das Wort ohne Leerzeichen zusammengefügt.
    """
    out = ""
    for ln in lines:
        ln = (ln or "").strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif _HYPHEN_END.search(out):
            out = _HYPHEN_END.sub(r"\1", out) + ln
        else:
            out += " " + ln
    return out


def join_wrapped_lines(text: str) -> str:
    """Fügt umgebrochene Zeilen zu Absätzen zusammen (reiner Textweg).

    Ohne Positionsangaben ist die Zeilenlänge das beste Indiz: eine Zeile,
    die bis zum Rand läuft, ist ein Umbruch mitten im Absatz – auch wenn
    dort ein Punkt steht. Erst eine erkennbar kürzere Zeile beendet einen
    Absatz. Zusätzlich beginnen Aufzählungen, Zeilen ohne Buchstaben
    (Seitenzahlen, Trennlinien) und Leerzeilen immer einen neuen Absatz.

    Steht in jeder Zeile bereits ein ganzer Absatz (Word-Notlösung, manche
    TXT-Dateien), sind die Zeilenlängen sehr unterschiedlich. Dann wird
    nichts zusammengefügt – geraten wäre hier schlimmer als nichts zu tun.
    """
    text = clean_text(text)
    if not text:
        return ""
    raw = text.split("\n")
    lengths = [len(ln) for ln in raw if ln]
    if not lengths:
        return ""
    med = _median(lengths)
    if med > 0 and _quantil(lengths, 0.9) > med * 1.5:
        return text     # keine gleichmäßig umbrochenen Zeilen
    voll = med * 0.92       # so lang -> die Zeile war ein Umbruch
    kurz = med * 0.75       # so kurz -> Schlusszeile / Überschrift

    paras: list[list[str]] = []
    for ln in raw:
        if not ln:
            if paras and paras[-1]:
                paras.append([])
            continue
        vorher = paras[-1][-1] if paras and paras[-1] else None
        if vorher is None:
            neu = True
        elif _LIST_START.match(ln) or _NO_LETTERS.match(ln) \
                or _NO_LETTERS.match(vorher):
            neu = True
        elif len(vorher) >= voll:
            neu = False     # volle Zeile: der Absatz läuft weiter
        else:
            neu = bool(_SENT_END.search(vorher)) or len(vorher) < kurz
        if neu or not paras:
            paras.append([ln])
        else:
            paras[-1].append(ln)

    return "\n\n".join(_join_lines(p) for p in paras if p)


def _is_rtl(lines: list[tuple]) -> bool:
    """Grobe Leserichtung: überwiegt Arabisch, wird von rechts gelesen."""
    text = " ".join((l[0] or "") for l in lines)
    ar = len(re.findall(r"[ء-يٮ-ۓ]", text))
    la = len(re.findall(r"[A-Za-z]", text))
    return ar >= la


def _columns(lines: list[tuple], rtl: bool) -> list[list[tuple]]:
    """Gruppiert Zeilen über ihre x-Überlappung zu Spalten.

    Zeilen, die sich horizontal überlappen, gehören zur selben Spalte; die
    Spalten werden in Leserichtung sortiert (arabisch: rechte zuerst). Eine
    seitenbreite Zeile (Überschrift) verbindet die Spalten – dann bleibt es
    bei einer einzigen Spalte in reiner y-Reihenfolge, also beim bisherigen
    Verhalten.
    """
    cols: list[dict] = []
    for ln in sorted(lines, key=lambda l: l[1]):        # nach x0
        x0, x1 = ln[1], ln[3]
        for c in cols:
            # Überlappung von mindestens der Hälfte der schmaleren Zeile
            ueber = min(x1, c["x1"]) - max(x0, c["x0"])
            breite = min(x1 - x0, c["x1"] - c["x0"])
            if breite <= 0 or ueber >= breite * 0.5:
                c["lines"].append(ln)
                c["x0"] = min(c["x0"], x0)
                c["x1"] = max(c["x1"], x1)
                break
        else:
            cols.append({"x0": x0, "x1": x1, "lines": [ln]})
    cols.sort(key=lambda c: c["x0"], reverse=rtl)
    return [sorted(c["lines"], key=lambda l: l[2]) for c in cols]   # nach y0


def paragraphs_from_boxes(lines: list[tuple]) -> str:
    """Baut den Seitentext aus Zeilen mit Position auf.

    lines: Liste von (text, x0, y0, x1, y1) in Seitenkoordinaten mit
    Ursprung oben links (y wächst nach unten).

    Ein Absatzwechsel wird angenommen, wenn eines zutrifft:
      - der vertikale Abstand ist deutlich größer als der übliche
      - die vorige Zeile endet "kurz" (bei RTL: ihre linke Kante liegt weit
        rechts vom Spaltenrand) – das ist die Schlusszeile eines Absatzes
      - die aktuelle Zeile ist gegenüber dem üblichen Anfangsrand eingerückt
      - Aufzählungszeichen oder Zeile ohne Buchstaben
    """
    lines = [l for l in lines if (l[0] or "").strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return clean_text(lines[0][0])

    rtl = _is_rtl(lines)
    teile: list[str] = []

    for spalte in _columns(lines, rtl):
        if not spalte:
            continue
        hoehen = [l[4] - l[2] for l in spalte if l[4] > l[2]]
        zeilenhoehe = _median(hoehen) or 1.0
        abstaende = [spalte[i][2] - spalte[i - 1][4]
                     for i in range(1, len(spalte))]
        # Negativer Median (überlappende Boxen) darf die Schwelle nicht kippen
        abstand_max = max(_median(abstaende), 0.0) + zeilenhoehe * 0.6

        breite = max(l[3] for l in spalte) - min(l[1] for l in spalte)
        # Kante, an der eine Zeile endet: bei RTL links, bei LTR rechts
        enden = [l[1] for l in spalte] if rtl else [l[3] for l in spalte]
        anfaenge = [l[3] for l in spalte] if rtl else [l[1] for l in spalte]
        rand_ende = _median(enden)
        rand_anfang = _median(anfaenge)
        toleranz = max(breite * 0.10, zeilenhoehe * 0.8)

        paras: list[list[str]] = []
        for i, ln in enumerate(spalte):
            txt = (ln[0] or "").strip()
            if i == 0:
                paras.append([txt])
                continue
            vor = spalte[i - 1]
            vortext = (vor[0] or "").strip()

            luecke = ln[2] - vor[4] > abstand_max
            if rtl:
                kurz_geendet = vor[1] - rand_ende > toleranz
                eingerueckt = rand_anfang - ln[3] > toleranz
            else:
                kurz_geendet = rand_ende - vor[3] > toleranz
                eingerueckt = ln[1] - rand_anfang > toleranz

            if (luecke or kurz_geendet or eingerueckt
                    or _LIST_START.match(txt)
                    or _NO_LETTERS.match(txt)
                    or _NO_LETTERS.match(vortext)):
                paras.append([txt])
            else:
                paras[-1].append(txt)
        teile.extend(_join_lines(p) for p in paras if p)

    return clean_text("\n\n".join(t for t in teile if t.strip()))


def paragraphs_from_groups(groups: list[list[str]]) -> str:
    """Baut den Seitentext aus fertig gruppierten Absätzen auf.

    Für OCR-Engines, die die Absätze selbst erkennen (Tesseract liefert in
    der TSV-Ausgabe block_num/par_num). Jede innere Liste ist ein Absatz,
    ihre Einträge sind die Zeilen.
    """
    paras = [_join_lines(g) for g in groups]
    return clean_text("\n\n".join(p for p in paras if p.strip()))
