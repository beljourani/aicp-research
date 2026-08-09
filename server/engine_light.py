# -*- coding: utf-8 -*-
"""Lädt aus der Such-Engine nur die Teile, die der Server braucht.

Warum nicht einfach `from echo_engine import ...`? Das Paket-`__init__`
zieht die komplette Indexierung nach – PyMuPDF, python-docx, OCR, fastembed.
Auf dem Server wird nichts extrahiert und nichts eingebettet; gebraucht
werden nur Normalisierung, Schema und Suche.

Deshalb wird das Paket hier von Hand angemeldet (mit `__path__`, damit die
relativen Importe der Untermodule weiter funktionieren) und `__init__.py`
übersprungen. Die Untermodule selbst bleiben unverändert – Anfrage und Index
benutzen also exakt dieselbe Logik wie die Offline-App.
"""
from __future__ import annotations

import os
import sys
import types

ENGINE = os.environ.get("ENGINE_PFAD", "/engine")


def _paket_anmelden() -> None:
    if "echo_engine" in sys.modules:
        return
    pfad = os.path.join(ENGINE, "echo_engine")
    if not os.path.isdir(pfad):
        # Entwicklungsrechner: Engine liegt neben dem Server-Verzeichnis
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "engine", "echo_engine")
    pkg = types.ModuleType("echo_engine")
    pkg.__path__ = [os.path.abspath(pfad)]
    sys.modules["echo_engine"] = pkg


_paket_anmelden()

from echo_engine.db import connect                       # noqa: E402
from echo_engine.normalize import (normalize, query_forms,  # noqa: E402
                                   stem, to_index_forms, tokenize)
from echo_engine.search import (SearchHit, groups_are_boolean,  # noqa: E402
                                groups_from_terms, highlight_spans,
                                is_boolean_query, parse_query, search)

__all__ = ["connect", "normalize", "query_forms", "stem", "to_index_forms",
           "tokenize", "SearchHit", "highlight_spans", "is_boolean_query",
           "groups_are_boolean", "groups_from_terms", "parse_query", "search"]
