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

import meta_index as mi

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
    con = sqlite3.connect(META_DB, timeout=60)
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------- Bücher & Seitenordnung ----
# Die reine Datenlogik (Buchkennung, Seitenordnung, Zwischenspeicher) liegt in
# meta_index.py – ohne FastAPI/Qdrant, damit sie testbar bleibt. Hier bleibt
# nur, was Qdrant braucht.

def _fetch_page_strings(title: str, author: str | None) -> list[str]:
    """Holt alle vorkommenden Seitenkennungen eines Buches aus Qdrant."""
    must = [qm.FieldCondition(key="title", match=qm.MatchValue(value=title))]
    if author:
        must.append(qm.FieldCondition(key="author",
                                      match=qm.MatchValue(value=author)))
    flt = qm.Filter(must=must)
    seen, offset = set(), None
    while True:
        res, offset = _client.scroll(
            collection_name=COLLECTION, scroll_filter=flt,
            with_payload=["page"], with_vectors=False, limit=1000, offset=offset)
        for pt in res:
            pg = (pt.payload or {}).get("page")
            if pg:
                seen.add(str(pg))
        if offset is None:
            break
    return sorted(seen, key=mi.page_sort_key)


def _ensure_book_index(con, book_id: int) -> int:
    return mi.ensure_book_index(con, book_id, fetch=_fetch_page_strings)


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
        # Buchkennungen sind aus Titel+Autor abgeleitet und stehen NICHT im
        # Qdrant-Payload – daher über die gemerkte Zuordnung in Titel/Autor
        # zurückübersetzen (nötig u. a. für die Suche innerhalb eines Buches).
        con = _meta()
        mi.ensure_schema(con)
        marks = ",".join("?" * len(req.book_ids))
        rows = con.execute(f"SELECT title, author FROM book_index WHERE "
                           f"book_id IN ({marks})", req.book_ids).fetchall()
        con.close()
        if not rows:
            return {"hits": [], "has_more": False,
                    "offset": req.offset, "limit": req.limit}
        alts = []
        for r in rows:
            sub = [qm.FieldCondition(key="title",
                                     match=qm.MatchValue(value=r["title"]))]
            if r["author"]:
                sub.append(qm.FieldCondition(key="author",
                                             match=qm.MatchValue(value=r["author"])))
            alts.append(qm.Filter(must=sub))
        must.append(qm.Filter(should=alts) if len(alts) > 1 else alts[0])
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
    con = _meta()
    mi.ensure_schema(con)
    for p in res:
        pl = p.payload or {}
        title, author = pl.get("title"), pl.get("author")
        bid = mi.book_id(title, author)
        mi.remember_book(con, bid, title, author, pl.get("source"))
        page_str = pl.get("page")
        part, page_num = mi.parse_page(page_str)
        hits.append({
            "score": p.score,
            "book_id": bid,
            "page_id": pl.get("page_id"),
            # seq wird erst beim Öffnen bestimmt (Seitenindex des Buches);
            # aufgeschlagen wird über `page`.
            "seq": None,
            "title": title,
            "author": author,
            "category": pl.get("category_name_ar"),
            "page": page_str,
            "page_num": page_num,
            "part": part,
            "source": pl.get("source"),
            "snippet": pl.get("text"),
        })
    con.commit()
    con.close()
    return {"hits": hits, "has_more": has_more,
            "offset": req.offset, "limit": req.limit}


@app.get("/page")
def page(book_id: int,
         seq: int | None = Query(None, description="interne Blattnummer"),
         page: str | None = Query(None, description="Seitenkennung, z. B. V01P441"),
         before: int = 0, after: int = 0,
         title: str | None = None, author: str | None = None,
         x_api_key: str | None = Header(None),
         authorization: str | None = Header(None)):
    """Liefert eine Seite (und optional Nachbarseiten) für den Leser.

    Aufgeschlagen wird über `seq` (Blättern) oder `page` (erstes Öffnen aus
    der Trefferliste). Der Seitenindex des Buches entsteht beim ersten Zugriff.
    """
    _auth(x_api_key, authorization)
    con = _meta()
    mi.ensure_schema(con)
    book = con.execute("SELECT * FROM book_index WHERE book_id=?",
                       (book_id,)).fetchone()
    if not book and title:
        # Rückfallebene: Buch aus den mitgelieferten Angaben anlegen.
        if mi.book_id(title, author) != book_id:
            con.close()
            raise HTTPException(404, "Buchkennung passt nicht zu Titel/Autor.")
        mi.remember_book(con, book_id, title, author, None)
        con.commit()
        book = con.execute("SELECT * FROM book_index WHERE book_id=?",
                           (book_id,)).fetchone()
    if not book:
        con.close()
        raise HTTPException(404, "Buch nicht gefunden – bitte erneut suchen.")

    total = _ensure_book_index(con, book_id)
    if not total:
        con.close()
        raise HTTPException(404, "Zu diesem Buch sind keine Seiten auffindbar.")

    if seq is None:
        if not page:
            con.close()
            raise HTTPException(400, "Es fehlt seq oder page.")
        row = con.execute("SELECT seq FROM page_index WHERE book_id=? AND "
                          "page_str=?", (book_id, page)).fetchone()
        if not row:
            con.close()
            raise HTTPException(404, "Seite in diesem Buch nicht gefunden.")
        seq = row["seq"]

    lo, hi = 1, total
    frm, to = max(lo, seq - before), min(hi, seq + after)
    rows = con.execute(
        "SELECT seq, page_str, part, page_num FROM page_index "
        "WHERE book_id=? AND seq BETWEEN ? AND ? ORDER BY seq",
        (book_id, frm, to)).fetchall()
    btitle, bauthor = book["title"], book["author"]
    con.close()

    pages = []
    for r in rows:
        pages.append({
            "seq": r["seq"], "page_id": None,
            "part": r["part"], "page_num": r["page_num"], "page_str": r["page_str"],
            "text": _reconstruct_page(btitle, bauthor, r["page_str"]),
        })
    return {"book_id": book_id, "title": btitle, "author": bauthor,
            "first_seq": lo, "last_seq": hi, "page_count": total,
            "seq": seq, "pages": pages}


def _reconstruct_page(title: str, author: str | None, page_str: str) -> str:
    """Setzt den Seitentext aus den Abschnitten dieser Seite zusammen.
    Abschnitte überlappen leicht (50 Token) – anhand der Zeichen-Offsets
    (char_start/char_end innerhalb der Seite) wird sauber zusammengefügt."""
    must = [
        qm.FieldCondition(key="title", match=qm.MatchValue(value=title)),
        qm.FieldCondition(key="page", match=qm.MatchValue(value=page_str)),
    ]
    if author:
        must.append(qm.FieldCondition(key="author",
                                      match=qm.MatchValue(value=author)))
    flt = qm.Filter(must=must)
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
