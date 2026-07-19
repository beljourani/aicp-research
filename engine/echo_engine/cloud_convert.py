# -*- coding: utf-8 -*-
"""Word→PDF über Microsofts Cloud-Word-Engine (optional, exakt).

Noch nicht aktiviert – wird eingerichtet, wenn wir den Cloud-Weg gehen.
Solange keine Zugangsdaten hinterlegt sind, meldet cloud_ready() False und
die App nutzt die anderen Stufen (lokales Word / LibreOffice).
"""
from __future__ import annotations

from pathlib import Path


def cloud_ready() -> bool:
    """True, sobald ein Microsoft-Zugang eingerichtet ist."""
    return False


def convert_via_cloud(path: Path, out_dir: Path) -> Path | None:
    """Platzhalter – wird implementiert, wenn der Cloud-Weg aktiviert wird."""
    return None
