# -*- coding: utf-8 -*-
"""Baut den Wort-/Wurzel-Index (FTS5) über alle Shamela-Abschnitte.

Warum: Die Online-Suche war rein semantisch (Vektoren). Damit sie sich wie die
Offline-Suche verhält – Wort UND Wurzel, mit ODER/Ausschluss/Phrase – braucht
der Server denselben Volltextindex, den die App lokal baut.

Wiederverwendet wird die Offline-Engine unverändert (`engine/echo_engine`):
dasselbe Schema (documents/passages/passages_fts), dieselbe Normalisierung und
dieselbe Wurzelbildung. Nur so finden Anfrage und Index dieselben Formen.

WICHTIG: Das Feld `text_norm` aus dem Datensatz ist NICHT unsere
Normalisierung (Umbrüche, arabische Ziffern und Hamza werden dort anders
behandelt) – deshalb wird immer aus dem Rohtext `text` neu aufbereitet.

Es wird NICHTS neu eingebettet; die Vektoren in Qdrant bleiben unberührt und
dienen weiter der semantischen Suche.

Aufteilung nach Autor: Die Autoren-Facette deckt nachweislich alle Punkte ab
(3.179 Autoren = 11.488.400 Punkte). Jeder Autor ist eine Einheit, die in einer
eigenen Transaktion geschrieben wird – bricht der Lauf ab, ist kein halber
Autor im Index, und ein Neustart macht dort weiter, wo er aufgehört hat.

Aufruf auf dem Server:
    docker compose run --rm fts-builder
oder direkt:
    python3 build_fts.py --qdrant http://qdrant:6333 --out /data/fts.db
"""
from __future__ import annotations

import argparse
import os
import queue
import sqlite3
import sys
import threading
import time

from qdrant_client import QdrantClient
from qdrant_client import models as qm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/engine")                       # Engine im Container
import meta_index as mi                                            # noqa: E402
from echo_engine.db import connect as engine_connect                # noqa: E402
from echo_engine.normalize import to_index_forms                    # noqa: E402

COLLECTION = os.environ.get("QDRANT_COLLECTION", "shamela")
# Felder, die für Index und Trefferanzeige gebraucht werden.
FELDER = ["text", "title", "author", "page", "char_start", "char_end",
          "chunk_no", "source"]
BLOCK = 2000                    # Zeilen je Schreibvorgang
GROSS = 60000                   # ab so vielen Abschnitten: Autor einzeln streamen


def zusatz_schema(con: sqlite3.Connection) -> None:
    """Tabellen, die es nur auf dem Server gibt: Seitenkennung je Abschnitt
    (für die Trefferanzeige) und der Fortschritt des Aufbaus."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS chunk_meta (
            passage_id INTEGER PRIMARY KEY,
            book_id INTEGER, page_str TEXT,
            part INTEGER, page_num INTEGER, chunk_no INTEGER
        );
        -- Für die Zusammenführung mit der Vektorsuche: Qdrant liefert
        -- (Buch, Seite, Abschnittsnummer) – daraus muss die Passage findbar sein.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_ident
            ON chunk_meta(book_id, page_str, chunk_no);
        CREATE TABLE IF NOT EXISTS fts_state (
            autor TEXT PRIMARY KEY, chunks INTEGER, fertig INTEGER DEFAULT 0
        );
    """)
    con.commit()


def autoren(client: QdrantClient) -> list[tuple[str, int]]:
    """Alle Autoren mit ihrer Abschnittszahl (deckt alle Punkte ab)."""
    res = client.facet(collection_name=COLLECTION, key="author",
                       limit=100000, exact=True)
    return [(h.value, h.count) for h in res.hits if h.value is not None]


def lies_autor(client: QdrantClient, autor: str):
    """Liefert die Abschnitte eines Autors blockweise (aufbereitet)."""
    flt = qm.Filter(must=[qm.FieldCondition(key="author",
                                            match=qm.MatchValue(value=autor))])
    offset, block = None, []
    while True:
        res, offset = client.scroll(
            collection_name=COLLECTION, scroll_filter=flt,
            with_payload=FELDER, with_vectors=False, limit=1000, offset=offset)
        for pt in res:
            pl = pt.payload or {}
            text = pl.get("text") or ""
            if not text.strip():
                continue
            titel = pl.get("title") or ""
            page_str = str(pl.get("page") or "")
            part, page_num = mi.parse_page(page_str)
            norm, stems = to_index_forms(text)
            block.append({
                "book_id": mi.book_id(titel, pl.get("author")),
                "title": titel, "author": pl.get("author") or "",
                "page_str": page_str, "part": part, "page_num": page_num,
                "chunk_no": pl.get("chunk_no"), "text": text,
                "norm": norm, "stems": stems,
                "source": pl.get("source") or "shamela",
            })
            if len(block) >= BLOCK:
                yield block
                block = []
        if offset is None:
            break
    if block:
        yield block


class Schreiber:
    """Schreibt die Abschnitte eines Autors in einer Transaktion."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.buecher: set[int] = set()
        row = con.execute("SELECT COALESCE(MAX(id),0) FROM passages").fetchone()
        self.naechste_id = row[0] + 1
        for r in con.execute("SELECT id FROM documents"):
            self.buecher.add(r[0])
        self.doppelt = 0

    def schreibe(self, autor: str, bloecke) -> int:
        con = self.con
        n = 0
        con.execute("BEGIN")
        try:
            for block in bloecke:
                docs, pas, fts, meta = [], [], [], []
                for r in block:
                    bid = r["book_id"]
                    if bid not in self.buecher:
                        docs.append((bid, r["title"], r["author"], "shamela",
                                     "online"))
                        self.buecher.add(bid)
                    pid = self.naechste_id
                    self.naechste_id += 1
                    # page_from/page_to tragen die ECHTE Druckseite (oder 0) –
                    # sie werden nie angezeigt, die Anzeige nutzt page_str.
                    seite = r["page_num"] or 0
                    pas.append((pid, bid, r["chunk_no"] or 0, seite, seite,
                                r["text"]))
                    fts.append((pid, r["norm"], r["stems"]))
                    meta.append((pid, bid, r["page_str"], r["part"],
                                 r["page_num"], r["chunk_no"]))
                if docs:
                    con.executemany(
                        "INSERT OR IGNORE INTO documents (id,title,author,"
                        "file_type,engine) VALUES (?,?,?,?,?)", docs)
                con.executemany(
                    "INSERT INTO passages (id,document_id,idx,page_from,"
                    "page_to,text) VALUES (?,?,?,?,?,?)", pas)
                con.executemany(
                    "INSERT INTO passages_fts (rowid,norm,stems) VALUES (?,?,?)",
                    fts)
                # Doppelte Kennungen dürfen den Lauf nicht abbrechen.
                for m in meta:
                    try:
                        con.execute("INSERT INTO chunk_meta (passage_id,book_id,"
                                    "page_str,part,page_num,chunk_no) "
                                    "VALUES (?,?,?,?,?,?)", m)
                    except sqlite3.IntegrityError:
                        self.doppelt += 1
                n += len(block)
            con.execute("INSERT OR REPLACE INTO fts_state (autor,chunks,fertig) "
                        "VALUES (?,?,1)", (autor, n))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=os.environ.get("QDRANT_URL",
                                                       "http://qdrant:6333"))
    ap.add_argument("--out", default=os.environ.get("FTS_DB", "/data/fts.db"))
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    client = QdrantClient(url=args.qdrant, timeout=1200)
    con = engine_connect(args.out)
    zusatz_schema(con)
    schreiber = Schreiber(con)

    alle = autoren(client)
    fertig = {r[0] for r in con.execute(
        "SELECT autor FROM fts_state WHERE fertig=1")}
    offen = [(a, n) for a, n in alle if a not in fertig]
    schon = sum(n for a, n in alle if a in fertig)
    gesamt = sum(n for _, n in alle)
    print(f"{len(alle):,} Autoren, {gesamt:,} Abschnitte", flush=True)
    if fertig:
        print(f"Wiederaufnahme: {len(fertig):,} Autoren / {schon:,} Abschnitte "
              f"bereits im Index", flush=True)

    # Kleine Autoren parallel vorbereiten, große einzeln streamen (Speicher).
    klein = [(a, n) for a, n in offen if n <= GROSS]
    gross = [(a, n) for a, n in offen if n > GROSS]
    print(f"zu tun: {len(klein):,} kleine + {len(gross):,} große Autoren",
          flush=True)

    t0 = time.time()
    erledigt = schon

    def fortschritt():
        dauer = time.time() - t0
        anteil = erledigt / gesamt if gesamt else 0
        tempo = (erledigt - schon) / dauer if dauer > 0 else 0
        rest = (gesamt - erledigt) / tempo / 60 if tempo > 0 else 0
        print(f"  {erledigt:,}/{gesamt:,} ({anteil*100:.1f}%) – "
              f"{tempo:,.0f}/s – noch ~{rest:.0f} min", flush=True)

    # --- kleine Autoren: mehrere Leser, ein Schreiber --------------------
    aufgaben = queue.Queue()
    for a, n in klein:
        aufgaben.put(a)
    ergebnisse = queue.Queue(maxsize=args.workers * 2)
    stopp = threading.Event()

    def arbeiter():
        eigener = QdrantClient(url=args.qdrant, timeout=1200)
        while not stopp.is_set():
            try:
                a = aufgaben.get_nowait()
            except queue.Empty:
                return
            try:
                bloecke = list(lies_autor(eigener, a))
                ergebnisse.put((a, bloecke))
            except Exception as e:                       # einer darf scheitern
                ergebnisse.put((a, None, str(e)))

    threads = [threading.Thread(target=arbeiter, daemon=True)
               for _ in range(args.workers)]
    for t in threads:
        t.start()

    offen_klein = len(klein)
    fehler = 0
    while offen_klein > 0:
        eintrag = ergebnisse.get()
        if len(eintrag) == 3:
            print(f"  Autor übersprungen ({eintrag[0]!r}): {eintrag[2]}",
                  flush=True)
            fehler += 1
            offen_klein -= 1
            continue
        a, bloecke = eintrag
        erledigt += schreiber.schreibe(a, bloecke)
        offen_klein -= 1
        if offen_klein % 100 == 0 or offen_klein == 0:
            fortschritt()

    # --- große Autoren: einzeln streamen --------------------------------
    for a, n in gross:
        print(f"  großer Autor: {a!r} ({n:,} Abschnitte)", flush=True)
        try:
            erledigt += schreiber.schreibe(a, lies_autor(client, a))
        except Exception as e:
            print(f"    fehlgeschlagen: {e}", flush=True)
            fehler += 1
        fortschritt()

    print("Index verdichten …", flush=True)
    con.execute("INSERT INTO passages_fts(passages_fts) VALUES('optimize')")
    con.commit()
    n_p = con.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
    n_d = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    con.close()
    groesse = os.path.getsize(args.out) / 1e9
    print(f"Fertig: {n_p:,} Abschnitte, {n_d:,} Bücher, {groesse:.1f} GB, "
          f"{(time.time()-t0)/60:.0f} min, {fehler} Fehler, "
          f"{schreiber.doppelt:,} doppelte Kennungen")


if __name__ == "__main__":
    main()
