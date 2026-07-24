# -*- coding: utf-8 -*-
"""Baut das Bücher- und Autorenverzeichnis für die Filterlisten auf.

Warum nötig: Der Datensatz `Maktabati/shamela-vectors` bringt keine Bücher-
oder Kategorienliste mit (siehe CLAUDE.md). Titel und Autor stehen nur an
jedem einzelnen Abschnitt. Dieses Skript erhebt daraus einmalig die Liste
aller Bücher (Titel+Autor) und Autoren und legt sie in `meta.db` ab.

Es nutzt Qdrants Facet-Abfrage statt eines Vollscans: erst alle Autoren,
dann je Autor dessen Titel. Das dauert Minuten statt Stunden und rührt die
Vektoren nicht an – es wird nichts neu eingebettet oder importiert.

Aufruf auf dem Server:
    docker exec -i server-api-1 python3 /app/build_catalog.py
oder im Container-Verzeichnis:
    python3 build_catalog.py --qdrant http://qdrant:6333 --meta /app/data/meta.db
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

from qdrant_client import QdrantClient
from qdrant_client import models as qm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta_index as mi                                        # noqa: E402

COLLECTION = os.environ.get("QDRANT_COLLECTION", "shamela")


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=os.environ.get("QDRANT_URL",
                                                       "http://qdrant:6333"))
    ap.add_argument("--meta", default=os.environ.get("META_DB", "/app/data/meta.db"))
    args = ap.parse_args()

    client = QdrantClient(url=args.qdrant, timeout=600)
    con = _con(args.meta)
    mi.ensure_schema(con)
    mi.set_catalog_state(con, "laeuft")

    # 1) Alle Autoren erheben (exakt, damit keiner fehlt).
    t0 = time.time()
    res = client.facet(collection_name=COLLECTION, key="author",
                       limit=100000, exact=True)
    autoren = [(h.value, h.count) for h in res.hits if h.value]
    print(f"{len(autoren)} Autoren in {time.time() - t0:.1f}s", flush=True)

    # 2) Je Autor die Titel erheben -> ergibt die Bücher.
    gesamt = 0
    for i, (name, chunks) in enumerate(autoren, 1):
        try:
            flt = qm.Filter(must=[qm.FieldCondition(
                key="author", match=qm.MatchValue(value=name))])
            tres = client.facet(collection_name=COLLECTION, key="title",
                                facet_filter=flt, limit=100000, exact=True)
            titel = [(h.value, h.count) for h in tres.hits if h.value]
        except Exception as e:                       # einzelner Autor darf nicht alles kippen
            print(f"  Autor übersprungen ({name!r}): {e}", flush=True)
            continue
        mi.add_books(con, [(t, name, n) for t, n in titel])
        con.execute("INSERT INTO author_index (name,books,chunks) VALUES (?,?,?) "
                    "ON CONFLICT(name) DO UPDATE SET books=excluded.books, "
                    "chunks=excluded.chunks", (name, len(titel), chunks))
        con.commit()
        gesamt += len(titel)
        if i % 100 == 0 or i == len(autoren):
            print(f"[{i}/{len(autoren)}] {gesamt:,} Bücher – "
                  f"{time.time() - t0:.0f}s", flush=True)

    mi.set_catalog_state(con, "fertig")
    n_b = con.execute("SELECT COUNT(*) c FROM catalog").fetchone()["c"]
    n_a = con.execute("SELECT COUNT(*) c FROM author_index").fetchone()["c"]
    con.close()
    print(f"Fertig: {n_b:,} Bücher, {n_a:,} Autoren in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
