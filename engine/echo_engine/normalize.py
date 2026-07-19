# -*- coding: utf-8 -*-
"""Arabische Textnormalisierung und Stemming für die Suche.

Zwei Ebenen:
1. normalize(): entfernt Tashkil/Tatweel, vereinheitlicht Alif/Ya/Ta-Marbuta.
   -> Wird für den "exakten" Index und die Anzeige-Zuordnung benutzt.
2. stem(): reduziert Wörter auf ihre Wurzel (ISRI-Algorithmus), damit
   Konjugationen gefunden werden (كتب findet يكتب، كتبت، يكتبون ...).
"""
from __future__ import annotations

import re

try:
    from nltk.stem.isri import ISRIStemmer
    _ISRI = ISRIStemmer()
except ImportError:  # Fallback: leichter Präfix/Suffix-Stemmer
    _ISRI = None

# Diakritika (Tashkil) + Koran-Zeichen + Tatweel
_TASHKIL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")

_ALIF = re.compile(r"[آأإٱ]")   # آ أ إ ٱ -> ا
_YA = re.compile(r"ى")                          # ى -> ي
_TA_MARBUTA = re.compile(r"ة")                  # ة -> ه
_HAMZA_WAW = re.compile(r"ؤ")                   # ؤ -> و
_HAMZA_YA = re.compile(r"ئ")                    # ئ -> ي

# Arabisch-indische Ziffern -> westliche Ziffern
_DIGIT_MAP = {ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")})

# Wort-Tokenizer: arabische Buchstaben, lateinische Buchstaben, Ziffern
_TOKEN = re.compile(r"[ء-يٮ-ۓA-Za-z0-9]+")

_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل", "س")
_SUFFIXES = ("كما", "هما", "تما", "تان", "ات", "ان", "ون", "ين", "ها", "هم", "هن",
             "كم", "كن", "نا", "وا", "ية", "ه", "ة", "ي", "ك", "ت", "ا", "ن")


def normalize(text: str) -> str:
    """Orthografische Normalisierung, erhält Wortgrenzen und Lesbarkeit."""
    text = _TASHKIL.sub("", text)
    text = _ALIF.sub("ا", text)
    text = _YA.sub("ي", text)
    text = _TA_MARBUTA.sub("ه", text)
    text = _HAMZA_WAW.sub("و", text)
    text = _HAMZA_YA.sub("ي", text)
    text = text.translate(_DIGIT_MAP)
    return text


def _light_stem(word: str) -> str:
    """Fallback-Stemmer, falls NLTK fehlt (Präfix/Suffix-Kürzung)."""
    for p in _PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 3:
            word = word[len(p):]
            break
    for s in _SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            word = word[: -len(s)]
            break
    return word


def stem(word: str) -> str:
    """Reduziert ein (bereits normalisiertes) Wort auf seinen Stamm/Wurzel."""
    if not word:
        return word
    # Nicht-arabische Tokens (Zahlen, lateinische Wörter) unverändert lassen
    if not re.search(r"[ء-ي]", word):
        return word.lower()
    out = _ISRI.stem(word) if _ISRI is not None else _light_stem(word)
    # Akkusativ-/End-Alif konsistent kappen (نصا -> نص). Wichtig ist nur,
    # dass Index und Anfrage identisch behandelt werden.
    if len(out) >= 3 and out.endswith("ا"):
        out = out[:-1]
    return out


def tokenize(text: str) -> list[str]:
    """Zerlegt Text in normalisierte Tokens."""
    return _TOKEN.findall(normalize(text))


def to_index_forms(text: str) -> tuple[str, str]:
    """Liefert (normalisierter Text, gestemmter Text) für die Indexierung.

    Beide sind tokenweise ausgerichtet (gleiche Wortanzahl), damit Treffer
    im gestemmten Index auf Wörter im normalisierten Text abgebildet
    werden können.
    """
    tokens = tokenize(text)
    stems = [stem(t) for t in tokens]
    return " ".join(tokens), " ".join(stems)


def query_forms(query: str) -> tuple[list[str], list[str]]:
    """Liefert (normalisierte Tokens, gestemmte Tokens) einer Suchanfrage."""
    tokens = tokenize(query)
    return tokens, [stem(t) for t in tokens]
