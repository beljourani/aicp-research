# -*- coding: utf-8 -*-
"""Suche: kombiniert exakte (normalisierte) Treffer mit Wurzel-Treffern.

Suchsyntax (funktioniert für Arabisch, Deutsch, Englisch, …):
    wort1 wort2        beide müssen vorkommen (UND), wurzelbasiert
    a b | a c          ODER-Verknüpfung von Gruppen
    -wort              Ausschluss: Passagen mit diesem Wort (oder seiner
                       Wurzel) fliegen raus
    "genauer ausdruck" exakte Wortgruppe (ohne Wurzel-Aufweichung)

Ranking: BM25 über beide FTS-Felder, wobei exakte Treffer (norm) doppelt
so stark gewichtet werden wie Wurzel-Treffer (stems). Ergebnisse enthalten
Dokumenttitel, Autor und den Seitenbereich der Passage.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .normalize import normalize, query_forms, stem, tokenize


@dataclass
class QueryGroup:
    """Eine UND-Gruppe: alle include-Begriffe müssen vorkommen,
    kein exclude-Begriff darf vorkommen."""
    include: list[tuple[str, str]] = field(default_factory=list)  # (norm, stamm)
    exclude: list[tuple[str, str]] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)              # normalisiert
    neg_phrases: list[str] = field(default_factory=list)


# ODER-Trenner: senkrechter Strich oder die Wörter oder/or/أو zwischen Leerzeichen
_OR_SPLIT = re.compile(r"\s*\|\s*|\s+(?:oder|or|أو)\s+", re.IGNORECASE)
_PHRASE = re.compile(r"(-?)\"([^\"]+)\"")


def parse_query(q: str) -> list[QueryGroup]:
    """Zerlegt die Anfrage in ODER-Gruppen mit UND-Begriffen/Ausschlüssen."""
    groups: list[QueryGroup] = []
    for raw in _OR_SPLIT.split(q.strip()):
        if not raw.strip():
            continue
        g = QueryGroup()
        # Wortgruppen in Anführungszeichen zuerst herausziehen
        def _take_phrase(m):
            tokens = tokenize(m.group(2))
            if tokens:
                phrase = " ".join(tokens)
                if m.group(1):
                    g.neg_phrases.append(phrase)
                else:
                    g.phrases.append(phrase)
            return " "
        rest = _PHRASE.sub(_take_phrase, raw)
        for word in rest.split():
            neg = word.startswith("-") or word.startswith("−")
            word = word.lstrip("-−")
            tokens = tokenize(word)
            if not tokens:
                continue
            pair = (tokens[0], stem(tokens[0]))
            (g.exclude if neg else g.include).append(pair)
        if g.include or g.phrases or g.exclude or g.neg_phrases:
            groups.append(g)
    return groups


def _esc(t: str) -> str:
    return '"' + t.replace('"', '""') + '"'


def _group_expr(g: QueryGroup) -> str | None:
    """Baut den FTS5-MATCH-Ausdruck für eine Gruppe."""
    positive = [f'({{norm}} : {_esc(n)} OR {{stems}} : {_esc(s)})'
                for n, s in g.include]
    positive += [f'{{norm}} : {_esc(p)}' for p in g.phrases]
    if not positive:
        return None  # reine Ausschluss-Gruppe ist nicht sinnvoll
    expr = " AND ".join(positive)
    for n, s in g.exclude:
        expr = f'({expr}) NOT ({{norm}} : {_esc(n)} OR {{stems}} : {_esc(s)})'
    for p in g.neg_phrases:
        expr = f'({expr}) NOT {{norm}} : {_esc(p)}'
    return expr


def is_boolean_query(q: str) -> bool:
    """Nutzt die Anfrage ODER/Ausschluss/Phrasen? Dann keine semantische
    Beimischung (die kann Ausschlüsse nicht respektieren)."""
    groups = parse_query(q)
    if len(groups) > 1:
        return True
    return any(g.exclude or g.phrases or g.neg_phrases for g in groups)


@dataclass
class SearchHit:
    passage_id: int
    document_id: int
    title: str
    author: str | None
    page_from: int
    page_to: int
    snippet: str
    score: float
    matched_words: list[str]
    reliability: str = "sicher"    # sicher | exakt | ungefähr


def structured_search(con: sqlite3.Connection,
                      and_groups: list[list[str]],
                      exclude: list[str] | None = None,
                      limit: int = 20, author: str | None = None,
                      document_id: int | None = None) -> list[SearchHit]:
    """Begriffssuche aus der Oberfläche: Gruppen von UND-Begriffen
    (ODER-verknüpft) plus globale Ausschlussliste – ohne Syntax-Parsing."""
    groups: list[QueryGroup] = []
    exc_pairs = []
    for word in (exclude or []):
        tokens = tokenize(word)
        if tokens:
            exc_pairs.append((tokens[0], stem(tokens[0])))
    for raw_terms in and_groups:
        g = QueryGroup(exclude=list(exc_pairs))
        for term in raw_terms:
            tokens = tokenize(term)
            if not tokens:
                continue
            if len(tokens) > 1:  # mehrwortiger Begriff = exakte Wortgruppe
                g.phrases.append(" ".join(tokens))
            else:
                g.include.append((tokens[0], stem(tokens[0])))
        if g.include or g.phrases:
            groups.append(g)
    return _search_groups(con, groups, limit=limit, author=author,
                          document_id=document_id)


def search(con: sqlite3.Connection, query: str, limit: int = 20,
           author: str | None = None,
           document_id: int | None = None) -> list[SearchHit]:
    groups = parse_query(query or "")
    return _search_groups(con, groups, limit=limit, author=author,
                          document_id=document_id)


def _author_clause(author) -> tuple[str, list]:
    """Filter nach einem ODER mehreren Autoren. Ein Dokument passt, wenn
    einer der gewählten Autoren in seiner (mehrfachen) Autorenliste steht."""
    if not author:
        return "", []
    names = author if isinstance(author, (list, tuple)) else [author]
    names = [n for n in names if n]
    if not names:
        return "", []
    clause = " AND (" + " OR ".join("d.author LIKE ?" for _ in names) + ")"
    return clause, [f"%{n}%" for n in names]


def _search_groups(con: sqlite3.Connection, groups: list[QueryGroup],
                   limit: int, author,
                   document_id: int | None) -> list[SearchHit]:
    exprs = [e for e in (_group_expr(g) for g in groups) if e]
    if not exprs:
        return _browse(con, limit=limit, author=author,
                       document_id=document_id)
    match_expr = " OR ".join(f"({e})" for e in exprs)

    # Für Hervorhebung/Snippets: alle positiven Begriffe aller Gruppen
    stem_tokens = [s for g in groups for _, s in g.include]
    stem_tokens += [stem(w) for g in groups for p in g.phrases
                    for w in p.split()]

    sql = """
        SELECT p.id, p.document_id, p.page_from, p.page_to, p.text,
               d.title, d.author, d.reliability,
               bm25(passages_fts, 2.0, 1.0) AS score
        FROM passages_fts f
        JOIN passages p ON p.id = f.rowid
        JOIN documents d ON d.id = p.document_id
        WHERE passages_fts MATCH ?
    """
    params: list = [match_expr]
    ac, ap = _author_clause(author)
    sql += ac; params += ap
    if document_id:
        sql += " AND d.id = ?"
        params.append(document_id)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    hits: list[SearchHit] = []
    for row in con.execute(sql, params):
        matched = _matched_words(row["text"], set(stem_tokens))
        hits.append(SearchHit(
            passage_id=row["id"], document_id=row["document_id"],
            title=row["title"], author=row["author"],
            page_from=row["page_from"], page_to=row["page_to"],
            snippet=_make_snippet(row["text"], matched),
            score=row["score"], matched_words=matched,
            reliability=row["reliability"] or "sicher"))
    return hits


def hybrid_search(con: sqlite3.Connection, query: str, embedder=None,
                  limit: int = 20, author: str | None = None,
                  document_id: int | None = None,
                  k: int = 60) -> list[SearchHit]:
    """Kombiniert Volltext- und semantische Suche per Reciprocal Rank Fusion.

    RRF ist robust gegen unterschiedliche Score-Skalen: score = Σ 1/(k+rang).
    Ohne Embedder (oder ohne Suchbegriff) fällt es auf die FTS-Suche zurück.
    """
    fts_hits = search(con, query, limit=limit * 3, author=author,
                      document_id=document_id)
    # Boolesche Anfragen (ODER/Ausschluss/Phrase) laufen rein über FTS –
    # die semantische Suche kann Ausschlüsse nicht respektieren.
    if embedder is None or not query.strip() or is_boolean_query(query):
        return fts_hits[:limit]

    from .semantic import vector_search
    try:
        qvec = embedder.embed([query])[0]
    except Exception:
        return fts_hits[:limit]
    vec_hits = vector_search(con, qvec, limit=limit * 3, author=author,
                             document_id=document_id)

    scores: dict[int, float] = {}
    by_id: dict[int, SearchHit] = {}
    for rank, hit in enumerate(fts_hits):
        scores[hit.passage_id] = scores.get(hit.passage_id, 0) + 1 / (k + rank)
        by_id[hit.passage_id] = hit
    for rank, (pid, _sim) in enumerate(vec_hits):
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank)
        if pid not in by_id:
            row = con.execute(
                "SELECT p.id, p.document_id, p.page_from, p.page_to, p.text, "
                "d.title, d.author, d.reliability FROM passages p "
                "JOIN documents d ON d.id = p.document_id WHERE p.id = ?",
                (pid,)).fetchone()
            if row:
                _, stem_tokens = query_forms(query)
                matched = _matched_words(row["text"], set(stem_tokens))
                by_id[pid] = SearchHit(
                    row["id"], row["document_id"], row["title"],
                    row["author"], row["page_from"], row["page_to"],
                    _make_snippet(row["text"], matched), 0.0, matched,
                    reliability=row["reliability"] or "sicher")

    ranked = sorted(by_id.values(),
                    key=lambda h: -scores.get(h.passage_id, 0))
    for h in ranked:
        h.score = scores.get(h.passage_id, 0)
    return ranked[:limit]


def _browse(con: sqlite3.Connection, limit: int, author,
            document_id: int | None) -> list[SearchHit]:
    """Ohne Suchbegriff: Passagen in Dokumentreihenfolge (Blättern)."""
    sql = ("SELECT p.id, p.document_id, p.page_from, p.page_to, p.text, "
           "d.title, d.author, d.reliability FROM passages p "
           "JOIN documents d ON d.id = p.document_id WHERE 1=1")
    params: list = []
    ac, ap = _author_clause(author)
    sql += ac; params += ap
    if document_id:
        sql += " AND d.id = ?"
        params.append(document_id)
    sql += " ORDER BY p.document_id, p.idx LIMIT ?"
    params.append(limit)
    return [SearchHit(row["id"], row["document_id"], row["title"],
                      row["author"], row["page_from"], row["page_to"],
                      row["text"][:200], 0.0, [],
                      reliability=row["reliability"] or "sicher")
            for row in con.execute(sql, params)]


import re as _re

_WORD = _re.compile(r"[ء-يٮ-ۓؐ-ٰA-Za-z0-9ً-ٟ]+")


def _match_spans(original_text: str,
                 query_stems: set[str]) -> list[tuple[int, int, str]]:
    """Findet (start, ende, wort) aller Wörter im ORIGINALTEXT, deren
    normalisierter Stamm zur Anfrage passt. Positionen beziehen sich auf
    den Originaltext (inkl. Tashkil) und stimmen daher für die Anzeige."""
    from .normalize import normalize as _norm
    spans = []
    for m in _WORD.finditer(original_text):
        if stem(_norm(m.group())) in query_stems:
            spans.append((m.start(), m.end(), m.group()))
    return spans


def _matched_words(original_text: str, query_stems: set[str]) -> list[str]:
    seen, out = set(), []
    for _, _, word in _match_spans(original_text, query_stems):
        if word not in seen:
            seen.add(word)
            out.append(word)
    return out


def _make_snippet(text: str, matched: list[str], width: int = 240) -> str:
    """Schneidet einen Ausschnitt um den ersten Treffer im Original aus."""
    if not matched:
        return text[:width] + ("…" if len(text) > width else "")
    first = text.find(matched[0])
    pos = first if first >= 0 else 0
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix
