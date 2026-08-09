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
import threading
import traceback
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client import models as qm

import meta_index as mi
# Wort-/Wurzelsuche mit derselben Engine wie offline (ohne PyMuPDF/OCR).
import engine_light as el
# Zwischenspeicher für die teure Bewertungsstufe (reine Logik, testbar).
import fts_cache as fc

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "shamela")
META_DB = os.environ.get("META_DB", "meta.db")
MODEL_NAME = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-base")
API_TOKEN = os.environ.get("API_TOKEN", "")     # Pflicht: nur mit Token nutzbar

def _vorladen() -> None:
    try:
        _model()
    except Exception:
        # Ohne Modell läuft die Wort-/Wurzelsuche unverändert weiter.
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app):
    """Einmalige Arbeit beim Start des Dienstes.

    Das Einbettungsmodell wird faul geladen (siehe `_model`). Der erste
    Aufruf nach einem Neustart kostete gemessen 19,7 s – zusammen mit einer
    langen Wortsuche (14 s) sind das 34 s und damit gefährlich nahe an der
    45-Sekunden-Grenze der App (app/main.py, `shamela_search`). Deshalb lädt
    ein Hintergrundfaden es sofort. Der Dienst ist trotzdem gleich
    erreichbar; /health meldet, ob das Modell schon steht.

    Bewusst hier und nicht beim Import: `test_search_hybrid.py` importiert
    api.py, und dort soll nicht sentence-transformers geladen werden.
    """
    threading.Thread(target=_vorladen, name="vorladen", daemon=True).start()
    yield


app = FastAPI(title="Shamela Search API", lifespan=lifespan)
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
# meta_index.py – ohne FastAPI/Qdrant, damit sie testbar bleibt. Hier steht,
# woher die Seitenkennungen kommen.
#
# (FTS_DB, _fts und _fts_verfuegbar stehen weiter unten beim Suchteil; hier
# werden sie nur zur Laufzeit gerufen.)

def _seiten_aus_qdrant(title: str, author: str | None) -> list[str]:
    """Seitenkennungen eines Buches aus Qdrant – die langsame Rückfallebene.

    Scrollt alle Abschnitte des Buches in Runden zu 1000. Bei grossen Büchern
    sind das über hundert Runden: gemessen 195 s für das grösste Buch, während
    die App nach 60 s abbricht. Deshalb ist das nicht mehr der Normalweg,
    sondern nur noch der Ausweg (siehe _seiten_kennungen).
    """
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


def _seiten_aus_wortindex(bid: int) -> list[str] | None:
    """Seitenkennungen eines Buches aus dem Wortindex (fts.db).

    `chunk_meta` trägt zu jedem Abschnitt Buch und Seitenkennung und hat
    darauf den abdeckenden Index idx_chunk_ident – die Liste kommt damit aus
    dem Index selbst, ohne eine einzige Datenzeile zu lesen. Auf dem Server
    gemessen: 2,1 s statt 195,2 s beim grössten Buch, im Schnitt 515-mal
    schneller; an 28 Büchern aller Grössen geprüft, die Listen sind identisch.

    Rückgabe `None` heisst „kann ich nicht beantworten" (Datei fehlt, Buch
    unbekannt, Fehler) – dann übernimmt Qdrant. Eine LEERE Liste gibt es hier
    bewusst nicht: `mi.ensure_book_index` würde die als „Buch hat keine
    Seiten" festschreiben und das Buch dauerhaft unöffenbar machen. Ein Buch
    ohne Abschnitte steht auch nicht in `documents`, die Unterscheidung kostet
    also nur eine Abfrage über den Schlüssel.
    """
    if not _fts_verfuegbar():
        return None
    con = None
    try:
        con = _fts()
        if not con.execute("SELECT 1 FROM documents WHERE id=?",
                           (bid,)).fetchone():
            return None
        # `page_str != ''` spiegelt das `if pg:` des Qdrant-Wegs. Ohne die
        # Bedingung käme ein leerer Eintrag dazu und verschöbe alle
        # Blattnummern des Buches um eins.
        zeilen = con.execute(
            "SELECT DISTINCT page_str FROM chunk_meta WHERE book_id=? "
            "AND page_str IS NOT NULL AND page_str != ''", (bid,)).fetchall()
    except Exception:
        # Ohne Ausgabe sähe ein Fehler hier aus wie „Buch unbekannt".
        traceback.print_exc()
        return None
    finally:
        if con is not None:
            con.close()
    return sorted({r["page_str"] for r in zeilen}, key=mi.page_sort_key)


_rueckfall_qdrant = 0       # wie oft der langsame Weg nötig war (siehe /health)


def _seiten_kennungen(bid: int, title: str, author: str | None) -> list[str]:
    """Alle Seitenkennungen eines Buches – erst der Wortindex, sonst Qdrant.

    Beide Wege sortieren mit `mi.page_sort_key` und lassen Leeres weg; die
    Listen sind nachweislich gleich. Ein leeres Ergebnis kann damit nur noch
    von Qdrant kommen und ist dann eine echte Antwort statt eines
    verschluckten Fehlers.
    """
    global _rueckfall_qdrant
    seiten = _seiten_aus_wortindex(bid)
    if seiten is not None:
        return seiten
    _rueckfall_qdrant += 1
    return _seiten_aus_qdrant(title, author)


def _ensure_book_index(con, book_id: int) -> int:
    # Die Buchkennung wird hier gebunden statt durchgereicht: so behält
    # `fetch` die Form (Titel, Autor) und meta_index.py bleibt frei von
    # Wissen über den Wortindex.
    return mi.ensure_book_index(
        con, book_id, fetch=lambda t, a: _seiten_kennungen(book_id, t, a))


# ---------------------------------------------- Wort-/Wurzelsuche (FTS) ------
FTS_DB = os.environ.get("FTS_DB", "/data/fts.db")
RRF_K = 60          # wie offline in echo_engine.search.hybrid_search

# Die Bewertung eines häufigen Wortes ist reine Rechenarbeit auf einem Kern,
# während die übrigen sieben brachliegen. STREIFEN teilt den Index in
# Zeilennummern-Abschnitte, die gleichzeitig bewertet werden. 1 schaltet das
# ab, ohne dass am Code etwas geändert werden muss.
STREIFEN = max(1, int(os.environ.get("STREIFEN", "6")))
# Obergrenze über ALLE gleichzeitigen Suchen. Ohne sie könnten mehrere Nutzer
# zusammen ein Vielfaches an Durchläufen über die 30-GB-Datei auslösen. Wer
# keinen Platz bekommt, wartet kurz statt zu scheitern – die Suche wird dann
# höchstens so langsam wie vorher, nie langsamer.
_streifen_platz = threading.BoundedSemaphore(STREIFEN)


def _fts():
    """Verbindung zum Wort-/Wurzel-Index (nur lesend)."""
    con = sqlite3.connect(f"file:{FTS_DB}?mode=ro", uri=True, timeout=30,
                          check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _fts_verfuegbar() -> bool:
    return os.path.exists(FTS_DB)


def _fts_suche(con, groups, limit: int, authors=None, book_ids=None):
    """Wort-/Wurzelsuche über den Server-Index – zweistufig.

    `groups` sind fertige Suchgruppen der Engine (siehe `_gruppen`) – entweder
    aus den Pillen der Oberfläche oder aus einer Anfrage in Textform.

    Die Engine-Abfrage verbindet passages_fts mit passages und documents,
    BEVOR sortiert wird. Lokal ist das egal (86.000 Passagen), hier nicht:
    ein häufiges Wort trifft Hunderttausende Abschnitte, deren Volltexte dann
    alle aus einer 30-GB-Datei gelesen werden (gemessen: 14–27 s).

    Deshalb wird erst IM FTS gerankt (dort steht nur der Index) und nur die
    besten Zeilen werden verbunden – gemessen 0,7–2,5 s. Geparst, gestemmt
    und bewertet wird mit derselben Engine-Logik wie offline, die Reihenfolge
    ist also dieselbe.
    """
    from echo_engine.search import (_group_expr, _matched_words,
                                    _make_snippet, match_forms,
                                    match_forms_je_begriff)
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
    je_begriff = match_forms_je_begriff(such_terme)

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
        rohe = _kandidaten(match_expr, limit)
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
        # Zweitschlüssel wie in _fts_roh, damit Gleichstände auch hier eine
        # feste Reihenfolge haben.
        rohe.sort(key=lambda r: (r["score"], r["rid"]))
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
            "snippet": _make_snippet(row["text"], matched, formen=formen,
                                     je_begriff=je_begriff),
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
    # Zweitschlüssel `rowid`: bm25 erzeugt sehr viele Gleichstände (gemessen
    # bis zu 467 von 1200 Zeilen). Ohne festen Zweitschlüssel darf SQLite bei
    # LIMIT 90 anders sortieren als bei LIMIT 1200 – dann wäre der Zuschnitt
    # einer großen Liste auf eine kleine nicht mehr dasselbe Ergebnis, worauf
    # der Zwischenspeicher aber baut. Gemessen kostet der Zusatz nichts
    # (14,57 s statt 14,70 s) und liefert dieselbe Liste wie bisher; er legt
    # nur eine bislang zufällige Reihenfolge innerhalb eines Gleichstands fest.
    sql += " ORDER BY score, rowid LIMIT ?"
    # Das Vierfache holt nur der Buchfilter: von den Zeilen eines
    # rowid-Bereichs gehören nicht alle zum gesuchten Buch, und nach dem
    # Aussieben unten sollen noch `limit` übrig bleiben. Beim Streifenlauf
    # wird nichts ausgesiebt – dort wäre das Vierfache verschenkte Arbeit.
    params.append(limit * 4 if buch is not None else limit)
    rohe = [{"rid": r["rid"], "score": r["score"]}
            for r in con.execute(sql, params)]
    if buch is not None and rohe:
        marks = ",".join("?" * len(rohe))
        eigene = {r[0] for r in con.execute(
            f"SELECT id FROM passages WHERE document_id=? AND id IN ({marks})",
            [buch] + [r["rid"] for r in rohe])}
        rohe = [r for r in rohe if r["rid"] in eigene][:limit]
    return rohe


def _streifen_grenzen(hoechste: int, anzahl: int):
    """Zeilennummern-Bereiche, die zusammen lückenlos alles abdecken.

    Eine Lücke hieße: Treffer fehlen, ohne dass es auffällt. Leere Bereiche
    entstehen bewusst keine – sonst würden Fäden gestartet, die nichts zu
    tun haben (bei kleinen Indizes wäre das die Mehrzahl).
    """
    if anzahl < 2 or hoechste < anzahl:
        return [(0, hoechste)]
    breite = hoechste // anzahl + 1
    grenzen, lo = [], 0
    while lo <= hoechste:
        grenzen.append((lo, min(lo + breite - 1, hoechste)))
        lo += breite
    return grenzen


@lru_cache(maxsize=4)
def _hoechste_zeile(kennung: str) -> int:
    """Größte Zeilennummer des Index – Grundlage der Streifeneinteilung.

    Der Fingerabdruck steht nur im Schlüssel, damit der Wert nach einem
    Indexwechsel neu geholt wird; benutzt wird er hier nicht.
    """
    con = _fts()
    try:
        return con.execute("SELECT MAX(rowid) FROM passages_fts").fetchone()[0] or 0
    finally:
        con.close()


def _fts_roh_gestreift(match_expr: str, limit: int):
    """Dieselbe Bewertung, nur auf mehrere Kerne verteilt.

    Warum die Reihenfolge erhalten bleibt: bm25 rechnet mit den Kennzahlen
    des GANZEN Index, nicht des Streifens. Die Punktzahl einer Zeile hängt
    also nicht davon ab, in welchem Streifen sie berechnet wurde – genau
    darauf beruht der Buchfilter oben schon (siehe _fts_suche). Und eine
    Zeile, die global unter die besten `limit` gehört, gehört erst recht in
    ihrem eigenen Streifen dazu; die Vereinigung der Streifen-Bestenlisten
    enthält die globale Bestenliste deshalb vollständig.

    Gemessen mit 6 Streifen: „الله" 14,0 s -> 4,7 s, Liste zeichengleich.

    Jeder Streifen braucht eine eigene Verbindung – SQLite-Verbindungen
    lassen sich nicht gleichzeitig benutzen. Währenddessen gibt sqlite3 die
    GIL frei, die Streifen rechnen also wirklich nebeneinander.
    """
    grenzen = _streifen_grenzen(_hoechste_zeile(_index_kennung()), STREIFEN)
    if len(grenzen) < 2:
        con = _fts()
        try:
            return _fts_roh(con, match_expr, limit)
        finally:
            con.close()

    ergebnis, fehler, sperre = [], [], threading.Lock()

    def teil(lo, hi):
        try:
            with _streifen_platz:
                con = _fts()
                try:
                    r = _fts_roh(con, match_expr, limit, bereich=(lo, hi))
                finally:
                    con.close()
            with sperre:
                ergebnis.extend(r)
        except Exception as e:                       # pragma: no cover
            with sperre:
                fehler.append(e)

    faeden = [threading.Thread(target=teil, args=g, name="streifen")
              for g in grenzen]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    if fehler:
        # Eine Teilliste wäre schlimmer als ein Fehler: sie sähe aus wie ein
        # vollständiges Ergebnis, hätte aber Treffer verloren.
        raise fehler[0]
    ergebnis.sort(key=lambda r: (r["score"], r["rid"]))
    return ergebnis[:limit]


# Zwischenspeicher für die Bewertung. Gemerkt wird nur die Kandidatenliste
# (Zeilennummer + Punktzahl); Verbinden, Ausschnitte und die semantische
# Umsortierung laufen weiter bei jeder Anfrage. Begründung und Messwerte:
# siehe fts_cache.py.
_speicher = fc.Kandidatenspeicher()


def _index_kennung() -> str:
    """Fingerabdruck der Indexdatei – Teil jedes Schlüssels.

    Ein neu gebauter Index vergibt ANDERE Zeilennummern: build_fts.py
    schreibt die Autoren in der Reihenfolge, in der die Lesefäden fertig
    werden, und die liegt nicht fest. Ein alter Eintrag zeigte danach auf
    fremde Abschnitte – also falsche Treffer, nicht bloß veraltete. Für ein
    Zitierwerkzeug ist das der schlimmste denkbare Fehler, deshalb steht die
    Kennung im Schlüssel und nicht bloß in einer Prüfung beim Start.
    Größe und Änderungszeit ändern sich bei jedem Neubau; der Aufruf kostet
    Mikrosekunden.
    """
    try:
        s = os.stat(FTS_DB)
        return f"{s.st_size}:{s.st_mtime_ns}"
    except OSError:
        return "?"


def _kandidaten(match_expr: str, limit: int):
    """Bewertete Kandidatenliste – aus dem Speicher, sonst frisch gerechnet.

    Schlüssel ist der MATCH-Ausdruck, nicht die eingetippte Anfrage: er ist
    die bereits normalisierte Form (Vokalzeichen, Leerraum und Artikel sind
    darin aufgelöst) und zugleich das Einzige, wovon `_fts_roh` überhaupt
    abhängt. Damit teilen sich „الله", " الله " und „اللّه" einen Eintrag.
    Ändert sich die Engine-Logik, ändert sich der Ausdruck automatisch mit –
    ein Deploy kann also keine inhaltlich veralteten Einträge erben.

    Nur der ungefilterte Zweig geht über den Speicher. Mit Buchfilter ist die
    Suche bereits schnell (gemessen 0,6–1,0 s), weil sie über rowid-Bereiche
    läuft; dort lohnt der Aufwand nicht.

    Gerechnet wird gestreift, also über mehrere Kerne. Das wirkt – anders als
    der Speicher – auch beim allerersten Mal. Eine Verbindung wird hier
    deshalb nicht durchgereicht: jeder Streifen öffnet seine eigene.
    """
    schluessel = f"{_index_kennung()}\x00{match_expr}"
    return _speicher.hole(schluessel, limit,
                          lambda n: _fts_roh_gestreift(match_expr, n))


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
    # Die Pillen der Oberfläche, unverändert: jede innere Liste ist eine
    # UND-Gruppe, die Gruppen sind ODER-verknüpft; `excludes` gilt global.
    # Sind sie gesetzt, haben sie Vorrang vor `q` – dann entsteht die Suche
    # aus derselben Engine-Funktion wie offline, ohne Umweg über Textsyntax.
    # `q` wird trotzdem mitgeschickt: ein Server ohne diese Felder versteht
    # zumindest die Textform, statt still die Ausschlüsse zu verlieren.
    and_groups: list[list[str]] | None = None
    excludes: list[str] | None = None


def _gruppen(req: SearchReq):
    """Suchgruppen der Anfrage – strukturiert, sonst aus der Textform.

    Beides läuft über die Engine, `groups_from_terms` ist dieselbe Funktion,
    die auch die Offline-Suche benutzt (`structured_search`).
    """
    if req.and_groups is not None:
        return el.groups_from_terms(req.and_groups, req.excludes or [])
    return el.parse_query(req.q or "")


# ---------------------------------------------------------------- Routen -----
@app.get("/health")
def health():
    try:
        info = _client.get_collection(COLLECTION)
        # Modell- und Speicherstand mitmelden: nur so lässt sich auf dem
        # Server ohne Debugger prüfen, ob Vorladen und Zwischenspeicher
        # greifen. Ein Zwischenspeicher verdeckt sonst still, wenn die Suche
        # insgesamt langsamer geworden ist.
        return {"ok": True, "points": info.points_count,
                "modell_geladen": _model.cache_info().currsize > 0,
                "streifen": STREIFEN,
                # Bleibt der Zähler auf 0, kam jedes Seitenverzeichnis aus dem
                # Wortindex. Feuert er, ist der langsame Qdrant-Weg nötig
                # gewesen - dann gehört die Ursache angesehen.
                "rueckfall_qdrant": _rueckfall_qdrant,
                "speicher": _speicher.stand()}
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
    gruppen = _gruppen(req)
    # Boolesche Anfragen (ODER / Ausschluss / Phrase) laufen rein über die
    # Wortsuche – genau wie offline; die Semantik kann Ausschlüsse nicht
    # berücksichtigen.
    nur_wort = (not req.semantic) or el.groups_are_boolean(gruppen)

    fts_hits, fts_con = [], None
    if _fts_verfuegbar() and gruppen:
        try:
            fts_con = _fts()
            fts_hits = _fts_suche(fts_con, gruppen, limit=spanne * 3,
                                  authors=req.authors or None,
                                  book_ids=req.book_ids or None)
        except Exception:
            # Ohne Ausgabe sähe ein Fehler hier wie „keine Treffer" aus –
            # die Suche wirkte kaputt, ohne dass im Protokoll etwas stünde.
            traceback.print_exc()
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
    # Die Semantik braucht eine Anfrage in Textform. Kommen die Pillen
    # strukturiert und ist `q` leer, gibt es nichts einzubetten – ein leerer
    # Vektor würde sonst eine beliebige Reihenfolge erzwingen.
    vec = (_vektor_rangliste(req, qfilter, spanne * 3 + 1)
           if (semantik_moeglich and (req.q or "").strip()) else [])
    punkte: dict = {}
    treffer: dict = {}

    # Umsortiert wird NUR die ausgegebene Trefferseite – sonst hinge die
    # TrefferMENGE davon ab, ob die Semantik an ist (Treffer von weiter hinten
    # könnten nach vorn rutschen). Sie soll nur die Reihenfolge ändern.
    seite = fts_hits[req.offset:spanne]
    for rang, h in enumerate(seite):
        schluessel = ("p", h["passage_id"])
        punkte[schluessel] = 1 / (RRF_K + rang)
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
    for k in rang_liste:
        h = treffer[k]
        h["score"] = punkte.get(k, 0)
        hits.append(h)
    has_more = len(fts_hits) > spanne
    if fts_con is not None:
        fts_con.close()
    return {"hits": hits, "has_more": has_more,
            "offset": req.offset, "limit": req.limit}


def _buch_aufloesen(con, book_id: int, title: str | None, author: str | None):
    """Buchzeile zur Kennung – oder aus Titel/Autor angelegt.

    Schliesst die Verbindung und wirft 404, wenn das Buch nicht zu ermitteln
    ist. Gemeinsam genutzt von /page, /book und /book_info, damit alle drei
    dieselbe Rückfallebene und dieselben Meldungen haben.
    """
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
    return book


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
    book = _buch_aufloesen(con, book_id, title, author)

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

    # Alle angeforderten Blätter in EINEM Durchlauf zusammensetzen statt in
    # einem je Blatt. Beim Vorausladen des Lesers sind das bis zu 14 Blätter,
    # also 14 Runden weniger.
    texte = _reconstruct_pages(btitle, bauthor, [r["page_str"] for r in rows])
    pages = []
    for r in rows:
        pages.append({
            "seq": r["seq"], "page_id": None,
            "part": r["part"], "page_num": r["page_num"], "page_str": r["page_str"],
            "text": texte.get(r["page_str"], ""),
        })
    return {"book_id": book_id, "title": btitle, "author": bauthor,
            "first_seq": lo, "last_seq": hi, "page_count": total,
            "seq": seq, "pages": pages}


# Ein Buch wird blockweise übernommen, nicht am Stück. Gründe: das grösste
# Buch hat 231 MB Text und 90.751 Blätter – eine einzige Antwort dafür wäre
# in keiner Zeitgrenze zustellbar und läge auf Server wie App mehrfach im
# Speicher. Ein Block ist dagegen wiederholbar: bricht einer ab, wird genau
# er nachgeholt. Je Block genügt EIN Qdrant-Durchlauf (~1 s), der gemessene
# Vorteil gegenüber dem seitenweisen Abruf bleibt also erhalten.
BLOCK_BLAETTER = 500


@app.get("/book_info")
def book_info(book_id: int, title: str | None = None, author: str | None = None,
              x_api_key: str | None = Header(None),
              authorization: str | None = Header(None)):
    """Umfang eines Buches – für die Rückfrage vor dem Übernehmen.

    Kostet nur das Seitenverzeichnis (unter einer Sekunde, siehe
    `_seiten_aus_wortindex`), lädt also keinen Text.
    """
    _auth(x_api_key, authorization)
    con = _meta()
    mi.ensure_schema(con)
    book = _buch_aufloesen(con, book_id, title, author)
    total = _ensure_book_index(con, book_id)
    btitle, bauthor = book["title"], book["author"]
    con.close()
    abschnitte = None
    if _fts_verfuegbar():
        try:
            f = _fts()
            try:
                r = f.execute("SELECT COUNT(*) FROM chunk_meta WHERE book_id=?",
                              (book_id,)).fetchone()
                abschnitte = r[0] if r else None
            finally:
                f.close()
        except Exception:
            traceback.print_exc()
    return {"book_id": book_id, "title": btitle, "author": bauthor,
            "page_count": total, "chunks": abschnitte,
            "block": BLOCK_BLAETTER}


@app.get("/book")
def book(book_id: int, offset: int = 0, limit: int = BLOCK_BLAETTER,
         title: str | None = None, author: str | None = None,
         x_api_key: str | None = Header(None),
         authorization: str | None = Header(None)):
    """Ein Block Blätter eines Buches, Text bereits zusammengesetzt.

    Geliefert werden die Blätter `offset+1` bis `offset+limit` in
    Lesereihenfolge. Der Text ist zeichengleich mit dem, was /page für
    dasselbe Blatt liefert – beide gehen durch `_reconstruct_pages`.

    Die Obergrenze wird hier erzwungen, nicht nur in der App: sonst könnte
    eine einzige Anfrage den Server in den Speicher treiben.
    """
    _auth(x_api_key, authorization)
    limit = max(1, min(int(limit), BLOCK_BLAETTER))
    offset = max(0, int(offset))
    con = _meta()
    mi.ensure_schema(con)
    book_row = _buch_aufloesen(con, book_id, title, author)
    total = _ensure_book_index(con, book_id)
    if not total:
        con.close()
        raise HTTPException(404, "Zu diesem Buch sind keine Seiten auffindbar.")
    rows = con.execute(
        "SELECT seq, page_str, part, page_num FROM page_index "
        "WHERE book_id=? AND seq BETWEEN ? AND ? ORDER BY seq",
        (book_id, offset + 1, offset + limit)).fetchall()
    btitle, bauthor = book_row["title"], book_row["author"]
    con.close()
    texte = _reconstruct_pages(btitle, bauthor, [r["page_str"] for r in rows])
    pages = [{"seq": r["seq"], "part": r["part"], "page_num": r["page_num"],
              "page_str": r["page_str"], "text": texte.get(r["page_str"], "")}
             for r in rows]
    return {"book_id": book_id, "title": btitle, "author": bauthor,
            "page_count": total, "offset": offset, "limit": limit,
            "has_more": (offset + len(pages)) < total, "pages": pages}


def _fuegen(parts: list) -> str:
    """Fügt die Abschnitte EINER Seite zum Seitentext zusammen.

    Abschnitte überlappen leicht (50 Token); anhand der Zeichen-Offsets
    innerhalb der Seite wird die Überlappung abgeschnitten.
    """
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


def _reconstruct_pages(title: str, author: str | None,
                       page_strs: list) -> dict:
    """Setzt MEHRERE Seiten in einem Durchlauf zusammen.

    Ein einziger Qdrant-Filter über alle gewünschten Seitenkennungen statt
    einer Runde je Seite. Für den Leser (bis zu 14 Blätter) und erst recht
    für das Übernehmen ganzer Bücher ist das der Unterschied zwischen
    Sekunden und Minuten: seitenweise kostete ein mittleres Buch gemessen
    87 s, ein grosses 1.171 s.

    Es gibt bewusst nur DIESE eine Zusammensetzung. Die Zusage „der
    übernommene Text ist derselbe wie in der Online-Ansicht" liesse sich
    mit zwei Fassungen nicht halten – sie würden getrennt altern, und der
    Unterschied fiele erst auf, wenn jemand ein Zitat vergleicht.
    """
    if not page_strs:
        return {}
    must = [qm.FieldCondition(key="title", match=qm.MatchValue(value=title)),
            qm.FieldCondition(key="page",
                              match=qm.MatchAny(any=list(page_strs)))]
    if author:
        must.append(qm.FieldCondition(key="author",
                                      match=qm.MatchValue(value=author)))
    flt = qm.Filter(must=must)
    teile: dict = {}
    offset = None
    while True:
        res, offset = _client.scroll(
            collection_name=COLLECTION, scroll_filter=flt,
            with_payload=["page", "char_start", "char_end", "text"],
            with_vectors=False, limit=1000, offset=offset)
        for pt in res:
            pl = pt.payload or {}
            teile.setdefault(str(pl.get("page") or ""), []).append(
                (pl.get("char_start") or 0, pl.get("char_end") or 0,
                 pl.get("text") or ""))
        if offset is None:
            break
    return {pg: _fuegen(parts) for pg, parts in teile.items()}


def _reconstruct_page(title: str, author: str | None, page_str: str) -> str:
    """Eine einzelne Seite – über denselben Weg wie beim Übernehmen."""
    return _reconstruct_pages(title, author, [page_str]).get(page_str, "")


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
