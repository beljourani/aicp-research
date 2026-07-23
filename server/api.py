# -*- coding: utf-8 -*-
"""Shamela-Such-API (FastAPI).

Der Dienst bettet die Suchanfrage serverseitig ein (multilingual-e5-base),
sucht in Qdrant und liefert Treffer inkl. Metadaten. Für den Leser
rekonstruiert er ganze Seiten aus den gespeicherten Textabschnitten.

Die App muss KEIN Einbettungsmodell mitbringen – sie schickt nur den Suchtext.

Zugriff nur mit gültigem Token (Header `X-API-Key` oder `Authorization: Bearer`).
Der Token wird in der App einmalig hinterlegt und bleibt gespeichert.

Start (lokal):  API_TOKEN=... uvicorn api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import sqlite3
from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client import models as qm

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "shamela")
META_DB = os.environ.get("META_DB", "meta.db")
MODEL_NAME = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")
API_TOKEN = os.environ.get("API_TOKEN", "")     # Pflicht: nur mit Token nutzbar

app = FastAPI(title="Shamela Search API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_client = QdrantClient(url=QDRANT_URL, timeout=60)


@lru_cache(maxsize=1)
def _model():
    # Erst hier laden, damit der Prozess schnell startet.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def _embed(text: str) -> list:
    # e5 verlangt das Präfix "query: " für Suchanfragen.
    vec = _model().encode("query: " + text, normalize_embeddings=True)
    return vec.tolist()


def _meta():
    con = sqlite3.connect(META_DB)
    con.row_factory = sqlite3.Row
    return con


def _auth(x_api_key: str | None, authorization: str | None) -> None:
    if not API_TOKEN:
        raise HTTPException(500, "Server ohne API_TOKEN gestartet.")
    token = x_api_key
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if token != API_TOKEN:
        raise HTTPException(401, "Ungültiger oder fehlender Token.")


# ---------------------------------------------------------------- Modelle ----
class SearchReq(BaseModel):
    q: str
    limit: int = 30
    offset: int = 0
    categories: list[str] | None = None
    authors: list[str] | None = None
    book_ids: list[int] | None = None
    source: str | None = None            # "shamela" | "quran"


# ---------------------------------------------------------------- Routen -----
@app.get("/health")
def health():
    try:
        info = _client.get_collection(COLLECTION)
        return {"ok": True, "points": info.points_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/search")
def search(req: SearchReq,
           x_api_key: str | None = Header(None),
           authorization: str | None = Header(None)):
    _auth(x_api_key, authorization)
    must = []
    if req.categories:
        must.append(qm.FieldCondition(key="category_name_ar",
                                      match=qm.MatchAny(any=req.categories)))
    if req.authors:
        must.append(qm.FieldCondition(key="author",
                                      match=qm.MatchAny(any=req.authors)))
    if req.book_ids:
        must.append(qm.FieldCondition(key="book_id",
                                      match=qm.MatchAny(any=req.book_ids)))
    if req.source:
        must.append(qm.FieldCondition(key="source",
                                      match=qm.MatchValue(value=req.source)))
    qfilter = qm.Filter(must=must) if must else None

    # Ein Treffer mehr holen, um "es gibt weitere" zu erkennen.
    res = _client.query_points(
        collection_name=COLLECTION,
        query=_embed(req.q),
        query_filter=qfilter,
        limit=req.limit + 1,
        offset=req.offset,
        with_payload=True,
        search_params=qm.SearchParams(
            quantization=qm.QuantizationSearchParams(rescore=True, oversampling=2.0)),
    ).points

    has_more = len(res) > req.limit
    res = res[:req.limit]
    hits = []
    for p in res:
        pl = p.payload or {}
        hits.append({
            "score": p.score,
            "book_id": pl.get("book_id"),
            "page_id": pl.get("page_id"),
            "seq": pl.get("sequence_num"),      # zum Aufschlagen im Leser
            "title": pl.get("title"),
            "author": pl.get("author"),
            "category": pl.get("category_name_ar"),
            "page": pl.get("page"),
            "page_num": pl.get("page_num"),
            "part": pl.get("part"),
            "source": pl.get("source"),
            "snippet": pl.get("text"),
        })
    return {"hits": hits, "has_more": has_more,
            "offset": req.offset, "limit": req.limit}


@app.get("/page")
def page(book_id: int, seq: int = Query(..., description="sequence_num der Seite"),
         before: int = 0, after: int = 0,
         x_api_key: str | None = Header(None),
         authorization: str | None = Header(None)):
    """Liefert eine Seite (und optional Nachbarseiten) für den Leser.
    Der Seitentext wird aus den gespeicherten Abschnitten rekonstruiert."""
    _auth(x_api_key, authorization)
    con = _meta()
    book = con.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    if not book:
        con.close()
        raise HTTPException(404, "Buch nicht gefunden.")
    bounds = con.execute("SELECT MIN(sequence_num) lo, MAX(sequence_num) hi "
                         "FROM pages WHERE book_id=?", (book_id,)).fetchone()
    lo, hi = bounds["lo"], bounds["hi"]
    frm = max(lo, seq - before)
    to = min(hi, seq + after)
    rows = con.execute(
        "SELECT page_id, sequence_num, part, page_num, page_str FROM pages "
        "WHERE book_id=? AND sequence_num BETWEEN ? AND ? ORDER BY sequence_num",
        (book_id, frm, to)).fetchall()
    con.close()

    pages = []
    for r in rows:
        pages.append({
            "seq": r["sequence_num"], "page_id": r["page_id"],
            "part": r["part"], "page_num": r["page_num"], "page_str": r["page_str"],
            "text": _reconstruct_page(book_id, r["page_id"]),
        })
    return {"book_id": book_id, "title": book["title"], "author": book["author"],
            "first_seq": lo, "last_seq": hi, "page_count": book["page_count"],
            "pages": pages}


def _reconstruct_page(book_id: int, page_id: int) -> str:
    """Setzt den Seitentext aus den Abschnitten dieser Seite zusammen.
    Abschnitte überlappen leicht (50 Token) – anhand der Zeichen-Offsets
    (char_start/char_end innerhalb der Seite) wird sauber zusammengefügt."""
    flt = qm.Filter(must=[
        qm.FieldCondition(key="book_id", match=qm.MatchValue(value=book_id)),
        qm.FieldCondition(key="page_id", match=qm.MatchValue(value=page_id)),
    ])
    chunks, offset = [], None
    while True:
        res, offset = _client.scroll(
            collection_name=COLLECTION, scroll_filter=flt,
            with_payload=True, limit=64, offset=offset)
        chunks.extend(res)
        if offset is None:
            break
    parts = []
    for pt in chunks:
        pl = pt.payload or {}
        parts.append((pl.get("char_start") or 0, pl.get("char_end") or 0,
                      pl.get("text") or ""))
    parts.sort(key=lambda x: x[0])
    text, covered = "", 0
    for cs, ce, tx in parts:
        if ce <= covered:            # ganz innerhalb schon Bekanntem
            continue
        if cs >= covered:            # ohne Überlappung anhängen
            text += tx
        else:                        # Überlappung abschneiden
            text += tx[covered - cs:]
        covered = max(covered, ce)
    return text.strip()


@app.get("/categories")
def categories(x_api_key: str | None = Header(None),
               authorization: str | None = Header(None)):
    _auth(x_api_key, authorization)
    con = _meta()
    rows = con.execute(
        "SELECT category_name_ar name, COUNT(*) n FROM books "
        "WHERE category_name_ar IS NOT NULL AND category_name_ar<>'' "
        "GROUP BY category_name_ar ORDER BY name").fetchall()
    con.close()
    return [{"name": r["name"], "books": r["n"]} for r in rows]


@app.get("/authors")
def authors(q: str = "", limit: int = 50,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None)):
    _auth(x_api_key, authorization)
    con = _meta()
    if q:
        rows = con.execute(
            "SELECT author name, COUNT(*) n FROM books WHERE author LIKE ? "
            "GROUP BY author ORDER BY n DESC LIMIT ?", (f"%{q}%", limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT author name, COUNT(*) n FROM books WHERE author IS NOT NULL "
            "GROUP BY author ORDER BY n DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [{"name": r["name"], "books": r["n"]} for r in rows]
