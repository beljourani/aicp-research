# -*- coding: utf-8 -*-
"""Import der Shamela-Vektordatenbank nach Qdrant + Aufbau eines Meta-Index.

Einmalig auf dem Server auszuführen. Lädt den fertig eingebetteten Datensatz
`Maktabati/shamela-vectors` (11,5 Mio. Abschnitte, 8.589 Bücher + Koran) und
schreibt ihn in eine Qdrant-Sammlung. Parallel entsteht eine kleine SQLite-Datei
(`meta.db`) mit Büchern/Seiten/Kategorien/Autoren – die brauchen wir zum
Blättern und für die Filterlisten, ohne dafür Qdrant zu durchsuchen.

Die 768-dim-Vektoren werden quantisiert gespeichert (int8), damit der
Arbeitsspeicherbedarf beherrschbar bleibt; die Originalvektoren liegen auf der
Platte und dienen dem Nachbewerten (Rescoring).

Aufruf (Beispiel):
    python import_shamela.py --qdrant http://localhost:6333 \
        --data ./shamela-vectors            # Ordner mit .parquet-Dateien
        # oder ohne --data: lädt automatisch von Hugging Face herunter

Wichtig: Der Download ist ~43 GB, der Import dauert je nach Maschine Stunden.
Das Skript ist wiederaufnehmbar – bereits importierte Punkte werden von Qdrant
anhand ihrer ID überschrieben, ein erneuter Lauf schadet also nicht.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pyarrow.parquet as pq
from qdrant_client import QdrantClient
from qdrant_client import models as qm

COLLECTION = "shamela"
VECTOR_SIZE = 768                      # multilingual-e5-base
BATCH = 512                            # Punkte pro Upsert

# Payload-Felder aus dem Datensatz (siehe Dataset-Card). Nur diese werden
# als Payload gespeichert – der Vektor kommt separat.
PAYLOAD_FIELDS = [
    "text", "text_norm", "author", "title", "death_year", "page",
    "char_start", "char_end", "chunk_no", "source", "book_id", "page_id",
    "page_num", "part", "category_id", "category_name_ar", "sequence_num",
    "book_type_label", "surah_num", "surah_name", "ayah_num", "global_id",
]


def make_collection(client: QdrantClient, quant: str) -> None:
    if client.collection_exists(COLLECTION):
        print(f"Sammlung '{COLLECTION}' existiert bereits – wird weiterbefüllt.")
        return
    if quant == "binary":
        quant_cfg = qm.BinaryQuantization(
            binary=qm.BinaryQuantizationConfig(always_ram=True))
    else:                              # int8 (Standard, bessere Trefferqualität)
        quant_cfg = qm.ScalarQuantization(
            scalar=qm.ScalarQuantizationConfig(
                type=qm.ScalarType.INT8, always_ram=True))
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(
            size=VECTOR_SIZE, distance=qm.Distance.COSINE, on_disk=True),
        quantization_config=quant_cfg,
        hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=100, on_disk=False),
        optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=0),
        on_disk_payload=True,
    )
    # Nutzlast-Indizes für schnelle Filter (Kategorie/Autor/Buch/Quelle/Seite)
    for field, schema in [
        ("book_id", qm.PayloadSchemaType.INTEGER),
        ("page_id", qm.PayloadSchemaType.INTEGER),
        ("category_name_ar", qm.PayloadSchemaType.KEYWORD),
        ("author", qm.PayloadSchemaType.KEYWORD),
        ("source", qm.PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(COLLECTION, field_name=field,
                                    field_schema=schema)
    print(f"Sammlung '{COLLECTION}' angelegt (Quantisierung: {quant}).")


def init_meta(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS books (
            book_id INTEGER PRIMARY KEY,
            title TEXT, author TEXT, category_id INTEGER,
            category_name_ar TEXT, death_year INTEGER, source TEXT,
            book_type_label TEXT, page_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS pages (
            book_id INTEGER, page_id INTEGER, sequence_num INTEGER,
            part TEXT, page_num INTEGER, page_str TEXT,
            PRIMARY KEY (book_id, page_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pages_seq ON pages(book_id, sequence_num);
    """)
    con.commit()
    return con


def upsert_meta(con: sqlite3.Connection, rows: list[dict]) -> None:
    books, pages = {}, {}
    for r in rows:
        bid = r.get("book_id")
        if bid is None:
            continue
        books[bid] = (bid, r.get("title"), r.get("author"), r.get("category_id"),
                      r.get("category_name_ar"), r.get("death_year"),
                      r.get("source"), r.get("book_type_label"))
        pid = r.get("page_id")
        if pid is not None:
            pages[(bid, pid)] = (bid, pid, r.get("sequence_num"), str(r.get("part") or ""),
                                 r.get("page_num"), r.get("page"))
    con.executemany(
        "INSERT OR IGNORE INTO books (book_id,title,author,category_id,"
        "category_name_ar,death_year,source,book_type_label) "
        "VALUES (?,?,?,?,?,?,?,?)", list(books.values()))
    con.executemany(
        "INSERT OR IGNORE INTO pages (book_id,page_id,sequence_num,part,"
        "page_num,page_str) VALUES (?,?,?,?,?,?)", list(pages.values()))
    con.commit()


def resolve_data_dir(data: str | None) -> Path:
    if data:
        return Path(data)
    print("Kein --data angegeben – lade Datensatz von Hugging Face …")
    from huggingface_hub import snapshot_download
    path = snapshot_download(repo_id="Maktabati/shamela-vectors",
                             repo_type="dataset", allow_patterns=["*.parquet"])
    return Path(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--data", default=None, help="Ordner mit .parquet-Dateien")
    ap.add_argument("--meta", default="meta.db", help="Pfad der Meta-SQLite-Datei")
    ap.add_argument("--quant", choices=["int8", "binary"], default="int8")
    args = ap.parse_args()

    data_dir = resolve_data_dir(args.data)
    files = sorted(data_dir.glob("*.parquet"))
    if not files:
        sys.exit(f"Keine .parquet-Dateien in {data_dir}")
    print(f"{len(files)} Parquet-Dateien gefunden.")

    client = QdrantClient(url=args.qdrant, timeout=120)
    make_collection(client, args.quant)
    con = init_meta(Path(args.meta))

    total = 0
    for fi, path in enumerate(files, 1):
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=BATCH):
            rows = batch.to_pylist()
            points = [
                qm.PointStruct(
                    id=r["id"],
                    vector=r["vector"],
                    payload={k: r.get(k) for k in PAYLOAD_FIELDS if r.get(k) is not None},
                )
                for r in rows
            ]
            client.upsert(COLLECTION, points=points, wait=False)
            upsert_meta(con, rows)
            total += len(points)
            if total % (BATCH * 40) == 0:
                print(f"[{fi}/{len(files)}] {total:,} Punkte …", flush=True)
    print(f"Alle Punkte importiert: {total:,}")

    # Seitenzahl je Buch nachtragen (für 'Seite X von N')
    con.execute("UPDATE books SET page_count = "
                "(SELECT COUNT(*) FROM pages WHERE pages.book_id = books.book_id)")
    con.commit()
    con.close()

    print("HNSW-Indizierung aktivieren …")
    client.update_collection(
        COLLECTION,
        optimizers_config=qm.OptimizersConfigDiff(
            indexing_threshold=20000, max_optimization_threads=4))
    print("Fertig. Warte, bis Qdrant die Indizierung abgeschlossen hat "
          "(indexed_vectors_count == points_count).")


if __name__ == "__main__":
    main()
