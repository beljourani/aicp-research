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
# Wort-/Wurzelsuche mit derselben Engine wie offline (ohne PyMuPDF/OCR).
import engine_light as el

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


# ---------------------------------------------- Wort-/Wurzelsuche (FTS) ------
FTS_DB = os.environ.get("FTS_DB", "/data/fts.db")
RRF_K = 60          # wie offline in echo_engine.search.hybrid_search


def _fts():
    """Verbindung zum Wort-/Wurzel-Index (nur lesend)."""
    con = sqlite3.connect(f"file:{FTS_DB}?mode=ro", uri=True, timeout=30,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _fts_verfuegbar() -> bool:
    return os.path.exists(FTS_DB)


def _fts_suche(con, q: str, limit: int, authors=None, book_ids=None):
    """Wort-/Wurzelsuche über den Server-Index – zweistufig.

    Die Engine-Abfrage verbindet passages_fts mit passages und documents,
    BEVOR sortiert wird. Lokal ist das egal (86.000 Passagen), hier nicht:
    ein häufiges Wort trifft Hunderttausende Abschnitte, deren Volltexte dann
    alle aus einer 30-GB-Datei gelesen werden (gemessen: 14–27 s).

    Deshalb wird erst IM FTS gerankt (dort steht nur der Index) und nur die
    besten Zeilen werden verbunden – gemessen 0,7–2,5 s. Geparst, gestemmt
    und bewertet wird mit derselben Engine-Logik wie offline, die Reihenfolge
    ist also dieselbe.
    """
    from echo_engine.search import (parse_query, _group_expr, _matched_words,
                                    _make_snippet, match_forms)
    groups = parse_query(q or "")
    exprs = [e for e in (_group_expr(g) for g in groups) if e]
    if not exprs:
        return []
    match_expr = " OR ".join(f"({e})" for e in exprs)
    # Dieselben Formen wie die Abfrage (inkl. Artikel-Form) – sonst bliebe
    # ein über die Artikel-Form gefundener Treffer unmarkiert und ohne Anker
    # im Ausschnitt.
    such_terme = [n for g in groups for n, _s in g.include]
    such_terme += [w for g in groups for p in g.phrases for w in p.split()]
    formen = match_forms(such_terme)

    # Filter auf Bücher zurückführen (documents ist klein, ~8.700 Zeilen).
    docs = None
    if book_ids:
        docs = [int(b) for b in book_ids]
    elif authors:
        namen = authors if isinstance(authors, (list, tuple)) else [authors]
        bed = " OR ".join("author LIKE ?" for _ in namen)
        docs = [r["id"] for r in con.execute(
            f"SELECT id FROM documents WHERE {bed}",
            [f"%{n}%" for n in namen]).fetchall()]
        if not docs:
            return []

    if docs is None:
        rohe = _fts_roh(con, match_expr, limit)
    else:
        # Buchfilter: NICHT global suchen und danach filtern. Ein häufiges
        # Wort trifft Millionen Abschnitte; die Prüfung gegen die Buchliste
        # läuft dann über alle (gemessen: über 150 s).
        # Stattdessen je Buch der rowid-Bereich seiner Abschnitte: FTS5 hält
        # seine Trefferlisten nach rowid sortiert und überspringt damit den
        # größten Teil des Index (gemessen: 0,6–1,0 s).
        rohe = []
        for bid in docs[:MAX_FILTER_BUECHER]:
            g = con.execute("SELECT MIN(id) lo, MAX(id) hi FROM passages "
                            "WHERE document_id=?", (bid,)).fetchone()
            if not g or g["lo"] is None:
                continue
            rohe += _fts_roh(con, match_expr, limit, bereich=(g["lo"], g["hi"]),
                             buch=bid)
        # bm25-Werte sind über die Bücher hinweg vergleichbar (gleiche
        # Anfrage, gleicher Index) – die Reihenfolge bleibt damit dieselbe.
        rohe.sort(key=lambda r: r["score"])
        rohe = rohe[:limit]

    if not rohe:
        return []
    ids = [r["rid"] for r in rohe]
    punkte = {r["rid"]: r["score"] for r in rohe}
    marks = ",".join("?" * len(ids))
    treffer = []
    zeilen = {r["id"]: r for r in con.execute(
        f"SELECT p.id, p.document_id, p.page_from, p.page_to, p.text, "
        f"d.title, d.author FROM passages p JOIN documents d ON d.id=p.document_id "
        f"WHERE p.id IN ({marks})", ids)}
    for pid in ids:                      # Reihenfolge aus der Bewertung halten
        row = zeilen.get(pid)
        if not row:
            continue
        matched = _matched_words(row["text"], formen)
        treffer.append({
            "passage_id": row["id"], "document_id": row["document_id"],
            "title": row["title"], "author": row["author"],
            "snippet": _make_snippet(row["text"], matched, formen=formen),
            "score": punkte[pid],
        })
    return treffer


MAX_FILTER_BUECHER = 25     # so viele Bücher je Suche einzeln abfragen


def _fts_roh(con, match_expr: str, limit: int, bereich=None, buch=None):
    """Bewertete Trefferliste aus dem Volltextindex (nur rowid + Punktzahl).

    `bereich` schränkt auf einen rowid-Abschnitt ein – das ist der einzige
    Weg, FTS5 dazu zu bringen, große Teile des Index zu überspringen.
    Da die Abschnitte eines Buches nicht lückenlos beieinanderliegen, wird
    anschließend noch auf das Buch selbst gefiltert.
    """
    sql = ("SELECT rowid AS rid, bm25(passages_fts,2.0,1.0) AS score "
           "FROM passages_fts WHERE passages_fts MATCH ?")
    params = [match_expr]
    if bereich:
        sql += " AND rowid BETWEEN ? AND ?"
        params += [bereich[0], bereich[1]]
    sql += " ORDER BY score LIMIT ?"
    params.append(limit * 4 if bereich else limit)
    rohe = [{"rid": r["rid"], "score": r["score"]}
            for r in con.execute(sql, params)]
    if buch is not None and rohe:
        marks = ",".join("?" * len(rohe))
        eigene = {r[0] for r in con.execute(
            f"SELECT id FROM passages WHERE document_id=? AND id IN ({marks})",
            [buch] + [r["rid"] for r in rohe])}
        rohe = [r for r in rohe if r["rid"] in eigene][:limit]
    return rohe


def _hit_aus_fts(con, h) -> dict:
    """Engine-Treffer in die Trefferform der App übersetzen. Die Form bleibt
    unverändert – Leser, Sortierung und Lesezeichen hängen daran."""
    m = con.execute("SELECT book_id, page_str, part, page_num FROM chunk_meta "
                    "WHERE passage_id=?", (h["passage_id"],)).fetchone()
    return {
        "score": h["score"],
        "book_id": (m["book_id"] if m else h["document_id"]),
        "page_id": None,
        "seq": None,                       # wird beim Öffnen aufgelöst
        "title": h["title"],
        "author": h["author"],
        "category": None,
        "page": (m["page_str"] if m else None),
        "page_num": (m["page_num"] if m else None),
        "part": (m["part"] if m else None),
        "source": "shamela",
        "snippet": h["snippet"],
    }


def _qdrant_filter(req: SearchReq):
    """Baut den Filter für die semantische Suche.

    Zweiter Rückgabewert sagt, ob die semantische Suche überhaupt sinnvoll
    ist: Buchkennungen sind aus Titel+Autor abgeleitet und stehen NICHT im
    Qdrant-Payload – lässt sich ein gewähltes Buch nicht zurückübersetzen,
    liefert die Vektorsuche nichts Sinnvolles. Die Wortsuche läuft trotzdem.
    """
    must = []
    if req.categories:
        must.append(qm.FieldCondition(key="category_name_ar",
                                      match=qm.MatchAny(any=req.categories)))
    if req.authors:
        must.append(qm.FieldCondition(key="author",
                                      match=qm.MatchAny(any=req.authors)))
    if req.source:
        must.append(qm.FieldCondition(key="source",
                                      match=qm.MatchValue(value=req.source)))
    if req.book_ids:
        rows = []
        con = _meta()
        mi.ensure_schema(con)
        rows = [r for r in (mi.book_row(con, b) for b in req.book_ids) if r]
        con.close()
        if not rows and _fts_verfuegbar():
            # Ersatzweise aus dem Wortindex auflösen (kennt alle Bücher).
            try:
                f = _fts()
                marks = ",".join("?" * len(req.book_ids))
                rows = [dict(r) for r in f.execute(
                    f"SELECT id AS book_id, title, author FROM documents "
                    f"WHERE id IN ({marks})", req.book_ids).fetchall()]
                f.close()
            except Exception:
                rows = []
        if not rows:
            return (qm.Filter(must=must) if must else None), False
        alts = []
        for r in rows:
            sub = [qm.FieldCondition(key="title",
                                     match=qm.MatchValue(value=r["title"]))]
            if r["author"]:
                sub.append(qm.FieldCondition(
                    key="author", match=qm.MatchValue(value=r["author"])))
            alts.append(qm.Filter(must=sub))
        must.append(qm.Filter(should=alts) if len(alts) > 1 else alts[0])
    return (qm.Filter(must=must) if must else None), True


def _vektor_rangliste(req: SearchReq, qfilter, anzahl: int):
    """Rangliste der semantischen Suche (unverändert wie bisher)."""
    res = _client.query_points(
        collection_name=COLLECTION, query=_embed(req.q), query_filter=qfilter,
        limit=anzahl, offset=0, with_payload=True,
        search_params=qm.SearchParams(
            quantization=qm.QuantizationSearchParams(rescore=True,
                                                     oversampling=2.0)),
    ).points
    return res


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
    # Semantik zusätzlich zur Wort-/Wurzelsuche (wie der Schalter offline).
    semantic: bool = True


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
    # Filter für die semantische Seite. Die Wortsuche filtert selbst über ihre
    # eigenen Tabellen und braucht dafür weder meta.db noch Qdrant.
    qfilter, semantik_moeglich = _qdrant_filter(req)

    spanne = req.offset + req.limit
    # Boolesche Anfragen (ODER / Ausschluss / Phrase) laufen rein über die
    # Wortsuche – genau wie offline; die Semantik kann Ausschlüsse nicht
    # berücksichtigen.
    nur_wort = (not req.semantic) or el.is_boolean_query(req.q or "")

    fts_hits, fts_con = [], None
    if _fts_verfuegbar() and (req.q or "").strip():
        try:
            fts_con = _fts()
            fts_hits = _fts_suche(fts_con, req.q, limit=spanne * 3,
                                  authors=req.authors or None,
                                  book_ids=req.book_ids or None)
        except Exception:
            fts_hits = []

    # Ohne Wortindex (oder ohne Treffer bei reiner Wortsuche) bleibt es bei
    # der bisherigen semantischen Suche – der Dienst fällt nie ganz aus.
    if fts_con is None and nur_wort and _fts_verfuegbar():
        nur_wort = False

    if nur_wort and fts_con is not None:
        gesamt = fts_hits
        hits = [_hit_aus_fts(fts_con, h) for h in gesamt[req.offset:spanne]]
        has_more = len(gesamt) > spanne
        fts_con.close()
        return {"hits": hits, "has_more": has_more,
                "offset": req.offset, "limit": req.limit}

    # --- Zusammenführung von Wort- und Vektorsuche (RRF, wie offline) -----
    vec = (_vektor_rangliste(req, qfilter, spanne * 3 + 1)
           if semantik_moeglich else [])
    punkte: dict = {}
    treffer: dict = {}

    for rang, h in enumerate(fts_hits):
        schluessel = ("p", h["passage_id"])
        punkte[schluessel] = punkte.get(schluessel, 0) + 1 / (RRF_K + rang)
        treffer[schluessel] = _hit_aus_fts(fts_con, h) if fts_con else None

    # Die Wort-Treffer sind die EINZIGE Ergebnismenge. Die semantische Liste
    # ändert nur ihre Reihenfolge – eine Stelle, die die gesuchten Wörter
    # nicht enthält, kommt NICHT hinzu. Sonst stünden begrifflose Treffer in
    # der Liste und „alle Begriffe" wäre nicht mehr verlässlich.
    con = _meta()
    mi.ensure_schema(con)
    for rang, p in enumerate(vec):
        pl = p.payload or {}
        title, author = pl.get("title"), pl.get("author")
        bid = mi.book_id(title, author)
        mi.remember_book(con, bid, title, author, pl.get("source"))
        if fts_con is None:
            continue
        # Zuordnung zur Wort-Trefferliste über (Buch, Seite, Abschnittsnummer).
        m = fts_con.execute(
            "SELECT passage_id FROM chunk_meta WHERE book_id=? AND "
            "page_str=? AND chunk_no=?",
            (bid, pl.get("page"), pl.get("chunk_no"))).fetchone()
        if not m:
            continue
        schluessel = ("p", m["passage_id"])
        if schluessel in treffer:          # nur echte Wort-Treffer umsortieren
            punkte[schluessel] = punkte.get(schluessel, 0) + 1 / (RRF_K + rang)
    con.commit()
    con.close()

    rang_liste = sorted((k for k in treffer if treffer[k] is not None),
                        key=lambda k: -punkte.get(k, 0))
    hits = []
    for k in rang_liste[req.offset:spanne]:
        h = treffer[k]
        h["score"] = punkte.get(k, 0)
        hits.append(h)
    has_more = len(rang_liste) > spanne
    if fts_con is not None:
        fts_con.close()
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
    book = mi.book_row(con, book_id)
    if book:
        # Aus dem Verzeichnis geöffnete Bücher zuerst vormerken, damit der
        # Seitenindex daran hängen kann.
        mi.remember_book(con, book_id, book["title"], book["author"], None)
        con.commit()
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
    """Kategorien gibt es in diesem Datensatz nicht – das Feld
    `category_name_ar` kommt darin schlicht nicht vor. Die leere Liste ist
    also korrekt; die App blendet den Filter daraufhin aus."""
    _auth(x_api_key, authorization)
    return []


@app.get("/authors")
def authors(q: str = "", limit: int = 50,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None)):
    """Autorenliste aus dem Verzeichnis; solange das noch nicht aufgebaut ist,
    direkt aus Qdrant erhoben (facet)."""
    _auth(x_api_key, authorization)
    con = _meta()
    mi.ensure_schema(con)
    rows = mi.find_authors(con, q=q, limit=limit)
    con.close()
    if rows:
        return [{"name": r["name"], "books": r["books"]} for r in rows]
    # Rückfallebene: Autoren direkt aus Qdrant (schnell, da Feld indiziert).
    try:
        res = _client.facet(collection_name=COLLECTION, key="author",
                            limit=max(limit, 200), exact=False)
        out = [{"name": h.value, "books": h.count} for h in res.hits
               if h.value and (not q or q in str(h.value))]
        return out[:limit]
    except Exception:
        return []


@app.get("/books")
def books(q: str = "", author: str | None = None, limit: int = 50,
          offset: int = 0,
          x_api_key: str | None = Header(None),
          authorization: str | None = Header(None)):
    """Bücherliste für den Buchfilter (durchsuchbar, seitenweise)."""
    _auth(x_api_key, authorization)
    limit = max(1, min(limit, 200))
    con = _meta()
    mi.ensure_schema(con)
    rows = mi.find_books(con, q=q, author=author, limit=limit + 1, offset=offset)
    ready = mi.catalog_ready(con)
    con.close()
    has_more = len(rows) > limit
    return {"books": rows[:limit], "has_more": has_more,
            "offset": offset, "limit": limit, "ready": ready}
