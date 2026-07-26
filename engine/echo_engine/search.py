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


# Funktionswörter: Präpositionen, Pronomen, Partikeln. An sie hängt sich der
# bestimmte Artikel nie. Ohne diese Liste entstünden Scheintreffer, weil
# „ال" + Funktionswort zufällig ein ganz anderes Wort ergeben kann – der
# schwerste Fall ist له -> الله: gemessen kamen dadurch 3,7 Mio. Passagen in
# die Treffer, die „له" überhaupt nicht enthalten (48 % der Treffermenge).
# Die Formen stehen normalisiert (alif/hamza vereinheitlicht).
_OHNE_ARTIKEL = {
    # Präposition/Pronomen-Verbindungen
    "له", "لها", "لهم", "لهن", "لك", "لكم", "لكن", "لنا", "لي",
    "به", "بها", "بهم", "بك", "بكم", "بنا", "بي",
    "منه", "منها", "منهم", "عنه", "عنها", "عنهم",
    "فيه", "فيها", "فيهم", "اليه", "اليها", "عليه", "عليها", "عليهم",
    # Präpositionen
    "من", "في", "علي", "عن", "الي", "مع", "عند", "بين", "بعد", "قبل",
    # Partikeln
    "لا", "ما", "لم", "لن", "ان", "او", "ام", "لو", "قد", "ثم", "بل",
    "حتي", "اذا", "اذ", "كي", "هل", "نعم", "بلي",
    # Pronomen / Demonstrativa
    "هو", "هي", "هم", "هن", "انا", "انت", "نحن",
    "هذا", "هذه", "ذلك", "تلك", "هولاء", "الذي", "التي",
}


def _norm_variants(n: str) -> list[str]:
    """Artikel-Varianten für die norm-Suche.

    Der bestimmte Artikel „ال" klebt im Arabischen am Wort. Ein artikelloses
    Suchwort soll deshalb auch die ال-Form finden (ست -> الست), sonst findet
    man ein Substantiv nur, wenn man den Artikel exakt so eintippt wie im Text.
    Nötig, weil der Stemmer bei manchen (oft kurzen) Wörtern uneinheitlich ist:
    stem("الست")=="الس" != stem("ست"), sodass weder norm noch stems greifen.

    Nur diese Richtung (Artikel ergänzen). Das Abtrennen von „ال" bei einem
    Suchwort wäre gefährlich – „الله" würde zu „له" und träfe jedes „له".

    Funktionswörter bekommen keine Artikel-Form (siehe _OHNE_ARTIKEL).
    """
    if n.startswith("ال") or n in _OHNE_ARTIKEL:
        return [n]
    return [n, "ال" + n]


def _term_expr(n: str, s: str) -> str:
    """FTS5-Ausdruck für einen Einzelbegriff: norm (inkl. Artikel-Variante)
    ODER Stamm."""
    alts = " OR ".join(f'{{norm}} : {_esc(v)}' for v in _norm_variants(n))
    return f'({alts} OR {{stems}} : {_esc(s)})'


def _group_expr(g: QueryGroup) -> str | None:
    """Baut den FTS5-MATCH-Ausdruck für eine Gruppe."""
    positive = [_term_expr(n, s) for n, s in g.include]
    positive += [f'{{norm}} : {_esc(p)}' for p in g.phrases]
    if not positive:
        return None  # reine Ausschluss-Gruppe ist nicht sinnvoll
    expr = " AND ".join(positive)
    for n, s in g.exclude:
        expr = f'({expr}) NOT {_term_expr(n, s)}'
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
                      document_id: int | None = None,
                      category=None,
                      offset: int = 0) -> list[SearchHit]:
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
                          document_id=document_id, category=category,
                          offset=offset)


def search(con: sqlite3.Connection, query: str, limit: int = 20,
           author: str | None = None,
           document_id: int | None = None,
           category=None,
           offset: int = 0) -> list[SearchHit]:
    groups = parse_query(query or "")
    return _search_groups(con, groups, limit=limit, author=author,
                          document_id=document_id, category=category,
                          offset=offset)


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


def _doc_clause(document_id) -> tuple[str, list]:
    """Buchfilter: ein einzelnes ODER mehrere Dokumente (d.id IN (…))."""
    if not document_id:
        return "", []
    ids = document_id if isinstance(document_id, (list, tuple, set)) \
        else [document_id]
    ids = [int(i) for i in ids if i not in (None, "")]
    if not ids:
        return "", []
    marks = ",".join("?" for _ in ids)
    return f" AND d.id IN ({marks})", list(ids)


def _category_clause(category) -> tuple[str, list]:
    """Filter nach einer oder mehreren Kategorien. Ein Dokument passt, wenn
    ihm eine der gewählten Kategorien zugeordnet ist."""
    if not category:
        return "", []
    names = category if isinstance(category, (list, tuple, set)) else [category]
    names = [n for n in names if n]
    if not names:
        return "", []
    marks = ",".join("?" for _ in names)
    clause = (" AND EXISTS (SELECT 1 FROM document_categories dc "
              "JOIN categories c ON c.id = dc.category_id "
              f"WHERE dc.document_id = d.id AND c.name IN ({marks}))")
    return clause, list(names)


def _search_groups(con: sqlite3.Connection, groups: list[QueryGroup],
                   limit: int, author,
                   document_id: int | None, category=None,
                   offset: int = 0) -> list[SearchHit]:
    exprs = [e for e in (_group_expr(g) for g in groups) if e]
    if not exprs:
        return _browse(con, limit=limit, author=author,
                       document_id=document_id, category=category,
                       offset=offset)
    match_expr = " OR ".join(f"({e})" for e in exprs)

    # Für Hervorhebung/Snippets: alle positiven Begriffe aller Gruppen –
    # mit denselben Formen, mit denen auch gesucht wird (inkl. Artikel-Form).
    such_terme = [n for g in groups for n, _s in g.include]
    such_terme += [w for g in groups for p in g.phrases for w in p.split()]
    formen = match_forms(such_terme)

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
    dc, dp = _doc_clause(document_id)
    sql += dc; params += dp
    cc, cp = _category_clause(category)
    sql += cc; params += cp
    sql += " ORDER BY score LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    hits: list[SearchHit] = []
    for row in con.execute(sql, params):
        matched = _matched_words(row["text"], formen)
        hits.append(SearchHit(
            passage_id=row["id"], document_id=row["document_id"],
            title=row["title"], author=row["author"],
            page_from=row["page_from"], page_to=row["page_to"],
            snippet=_make_snippet(row["text"], matched, formen=formen),
            score=row["score"], matched_words=matched,
            reliability=row["reliability"] or "sicher"))
    return hits


def hybrid_search(con: sqlite3.Connection, query: str, embedder=None,
                  limit: int = 20, author: str | None = None,
                  document_id: int | None = None,
                  category=None,
                  k: int = 60, offset: int = 0) -> list[SearchHit]:
    """Kombiniert Volltext- und semantische Suche per Reciprocal Rank Fusion.

    RRF ist robust gegen unterschiedliche Score-Skalen: score = Σ 1/(k+rang).
    Ohne Embedder (oder ohne Suchbegriff) fällt es auf die FTS-Suche zurück.
    """
    span = offset + limit          # so viele Treffer werden insgesamt gebraucht
    fts_hits = search(con, query, limit=span * 3, author=author,
                      document_id=document_id, category=category)
    # Boolesche Anfragen (ODER/Ausschluss/Phrase) laufen rein über FTS –
    # die semantische Suche kann Ausschlüsse nicht respektieren.
    if embedder is None or not query.strip() or is_boolean_query(query):
        return fts_hits[offset:span]

    from .semantic import vector_search
    try:
        qvec = embedder.embed([query])[0]
    except Exception:
        return fts_hits[offset:span]
    vec_hits = vector_search(con, qvec, limit=span * 3, author=author,
                             document_id=document_id, category=category)

    # Umsortiert wird NUR die tatsächlich ausgegebene Trefferseite. Würde man
    # über einen größeren Kandidatenvorrat umsortieren, könnten Treffer von
    # weiter hinten nach vorn rutschen – die TrefferMENGE hinge dann davon ab,
    # ob die Semantik an ist. Sie soll aber nur die Reihenfolge ändern.
    seite = fts_hits[offset:span]
    scores: dict[int, float] = {}
    by_id: dict[int, SearchHit] = {}
    for rank, hit in enumerate(seite):
        scores[hit.passage_id] = 1 / (k + rank)
        by_id[hit.passage_id] = hit
    # Die Wort-Treffer sind die EINZIGE Ergebnismenge. Die semantische Suche
    # ändert nur ihre Reihenfolge – sie nimmt keine Stelle neu auf. Sonst
    # stünden in der Liste Treffer, die die gesuchten Wörter gar nicht
    # enthalten; „alle Begriffe" wäre dann nicht mehr verlässlich.
    for rank, (pid, _sim) in enumerate(vec_hits):
        if pid in by_id:
            scores[pid] = scores.get(pid, 0) + 1 / (k + rank)

    ranked = sorted(by_id.values(),
                    key=lambda h: -scores.get(h.passage_id, 0))
    for h in ranked:
        h.score = scores.get(h.passage_id, 0)
    return ranked


def _browse(con: sqlite3.Connection, limit: int, author,
            document_id: int | None, category=None,
            offset: int = 0) -> list[SearchHit]:
    """Ohne Suchbegriff: Passagen in Dokumentreihenfolge (Blättern)."""
    sql = ("SELECT p.id, p.document_id, p.page_from, p.page_to, p.text, "
           "d.title, d.author, d.reliability FROM passages p "
           "JOIN documents d ON d.id = p.document_id WHERE 1=1")
    params: list = []
    ac, ap = _author_clause(author)
    sql += ac; params += ap
    dc, dp = _doc_clause(document_id)
    sql += dc; params += dp
    cc, cp = _category_clause(category)
    sql += cc; params += cp
    sql += " ORDER BY p.document_id, p.idx LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
    return [SearchHit(row["id"], row["document_id"], row["title"],
                      row["author"], row["page_from"], row["page_to"],
                      row["text"][:200], 0.0, [],
                      reliability=row["reliability"] or "sicher")
            for row in con.execute(sql, params)]


import re as _re

_WORD = _re.compile(r"[ء-يٮ-ۓؐ-ٰA-Za-z0-9ً-ٟ]+")


def match_forms(terms) -> tuple[set[str], set[str]]:
    """(Normalformen, Stämme) einer Anfrage – exakt die Formen, mit denen die
    Suche ihre Treffer findet.

    Enthält auch die Artikel-Varianten aus `_norm_variants`. Ohne sie würde
    ein über „الست" gefundener Treffer nicht markiert und der Ausschnitt fände
    keinen Anker – es sähe aus, als fehlte der Begriff, obwohl er da ist.
    """
    norms: set[str] = set()
    stems: set[str] = set()
    for term in (terms or []):
        for tok in tokenize(term or ""):
            stems.add(stem(tok))
            norms.update(_norm_variants(tok))
    norms.discard("")
    stems.discard("")
    return norms, stems


def _als_formen(query_forms_or_stems) -> tuple[set[str], set[str]]:
    """Nimmt (norms, stems) entgegen – oder nur eine Stamm-Menge (alt)."""
    if isinstance(query_forms_or_stems, tuple):
        return query_forms_or_stems
    return set(), set(query_forms_or_stems or ())


def _match_spans(original_text: str, formen) -> list[tuple[int, int, str]]:
    """Findet (start, ende, wort) aller Wörter im ORIGINALTEXT, die zur
    Anfrage passen – über Normalform (inkl. Artikel-Form) ODER Stamm.
    Positionen beziehen sich auf den Originaltext (inkl. Tashkil) und stimmen
    daher für die Anzeige."""
    from .normalize import normalize as _norm
    norms, stems = _als_formen(formen)
    spans = []
    for m in _WORD.finditer(original_text):
        n = _norm(m.group())
        if n in norms or stem(n) in stems:
            spans.append((m.start(), m.end(), m.group()))
    return spans


def _matched_words(original_text: str, formen) -> list[str]:
    seen, out = set(), []
    for _, _, word in _match_spans(original_text, formen):
        if word not in seen:
            seen.add(word)
            out.append(word)
    return out


def stems_of_terms(terms) -> set[str]:
    """Wandelt eine Liste von Suchbegriffen (einzelne Wörter ODER mehrwortige
    Ausdrücke) in die Menge ihrer Wurzeln um – identisch zu der Menge, die
    die Suche zum Finden der Treffer benutzt. Damit stimmen Markierungen und
    Trefferauswahl überein."""
    out: set[str] = set()
    for term in (terms or []):
        for tok in tokenize(term or ""):
            out.add(stem(tok))
    out.discard("")
    return out


def highlight_spans(text: str, terms) -> list[tuple[int, int]]:
    """Liefert (start, ende)-Positionen aller Wörter in ``text``, deren Wurzel
    zu einem der ``terms`` passt. Die Berechnung läuft wurzelbewusst gegen den
    TATSÄCHLICH angezeigten Text – so werden alle Flexionen und Diakritika-
    Varianten markiert (behebt den Markierungs-Bug im Leser)."""
    formen = match_forms(terms)
    if not formen[0] and not formen[1]:
        return []
    return [(s, e) for s, e, _ in _match_spans(text, formen)]


def _make_snippet(text: str, matched: list[str], width: int = 240,
                  formen=None) -> str:
    """Schneidet einen Ausschnitt aus, in dem möglichst VIELE der gesuchten
    Begriffe stehen.

    Früher wurde nur um den ersten Treffer geschnitten. Bei mehreren Begriffen
    zeigte der Ausschnitt dann oft nur einen davon – es sah aus, als fehlten
    die anderen, obwohl die Passage sie enthält.
    """
    if not text:
        return ""
    if formen is not None:
        stellen = _match_spans(text, formen)
    elif matched:
        stellen = []
        for w in matched:
            i = text.find(w)
            if i >= 0:
                stellen.append((i, i + len(w), w))
        stellen.sort()
    else:
        stellen = []
    if not stellen:
        return text[:width] + ("…" if len(text) > width else "")

    # Fenster so legen, dass es möglichst viele VERSCHIEDENE Wortformen deckt.
    from .normalize import normalize as _norm
    bestes, beste_zahl = stellen[0][0], -1
    for a, _b, _w in stellen:
        start = max(0, a - width // 6)
        ende = start + width
        abgedeckt = {_norm(w) for s, e, w in stellen if s >= start and e <= ende}
        if len(abgedeckt) > beste_zahl:
            beste_zahl, bestes = len(abgedeckt), a
    start = max(0, bestes - width // 6)
    end = min(len(text), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix
