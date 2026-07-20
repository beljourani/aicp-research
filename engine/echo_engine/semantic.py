# -*- coding: utf-8 -*-
"""Semantische Suche mit lokalem Embedding-Modell (kostenlos, offline).

Modell: paraphrase-multilingual-MiniLM-L12-v2 (384 Dim., ~220 MB),
läuft über ONNX auch auf schwachen Geräten. Wird beim ersten Start
einmalig heruntergeladen, danach vollständig offline.

Vektoren liegen als BLOBs in SQLite; die Suche ist Brute-Force-Cosinus
über NumPy – bei lokalem Maßstab (bis Hunderttausende Passagen) schnell
genug und ohne Zusatzdienste.
"""
from __future__ import annotations

import sqlite3

import numpy as np

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384

VECTOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS passage_vectors (
    passage_id INTEGER PRIMARY KEY REFERENCES passages(id) ON DELETE CASCADE,
    vec BLOB NOT NULL
);
"""


def model_cache_dir() -> "Path":
    """Modell-Speicherort. Gebündelte Modelle (aus dem Installer) werden
    beim ersten Start in den Datenordner kopiert – danach komplett offline,
    kein Download nötig."""
    import os
    import shutil as _shutil
    import sys
    from pathlib import Path

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".local" / "share"
    target = base / "AICP Research" / "models"

    bundled = Path(getattr(sys, "_MEIPASS", "")) / "models" \
        if getattr(sys, "frozen", False) else None
    if bundled and bundled.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copytree(bundled, target)
    target.mkdir(parents=True, exist_ok=True)
    return target


class Embedder:
    """Kapselt das Modell; lädt es erst bei Bedarf (lazy)."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model = None

    @property
    def available(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:
            return False

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(
                self.model_name, cache_dir=str(model_cache_dir()))
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        model = self._ensure()
        vecs = np.array(list(model.embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms


def ensure_vector_schema(con: sqlite3.Connection) -> None:
    con.executescript(VECTOR_SCHEMA)


def embed_passages(con: sqlite3.Connection, embedder: Embedder,
                   document_id: int | None = None,
                   batch_size: int = 64) -> int:
    """Berechnet Vektoren für alle Passagen ohne Vektor. Liefert Anzahl."""
    ensure_vector_schema(con)
    sql = ("SELECT p.id, p.text FROM passages p "
           "LEFT JOIN passage_vectors v ON v.passage_id = p.id "
           "WHERE v.passage_id IS NULL")
    params: list = []
    if document_id:
        sql += " AND p.document_id = ?"
        params.append(document_id)
    rows = con.execute(sql, params).fetchall()
    done = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        vecs = embedder.embed([r["text"] for r in batch])
        con.executemany(
            "INSERT OR REPLACE INTO passage_vectors (passage_id, vec) "
            "VALUES (?,?)",
            [(r["id"], v.tobytes()) for r, v in zip(batch, vecs)])
        con.commit()
        done += len(batch)
    return done


def vector_search(con: sqlite3.Connection, query_vec: np.ndarray,
                  limit: int = 50,
                  author: str | None = None,
                  document_id: int | None = None,
                  category=None,
                  min_similarity: float = 0.25) -> list[tuple[int, float]]:
    """Liefert [(passage_id, cosinus-ähnlichkeit)] absteigend sortiert."""
    from .search import _author_clause, _doc_clause, _category_clause
    ensure_vector_schema(con)
    sql = ("SELECT v.passage_id, v.vec FROM passage_vectors v "
           "JOIN passages p ON p.id = v.passage_id "
           "JOIN documents d ON d.id = p.document_id WHERE 1=1")
    params: list = []
    for clause, cparams in (_author_clause(author), _doc_clause(document_id),
                            _category_clause(category)):
        sql += clause; params += cparams
    rows = con.execute(sql, params).fetchall()
    if not rows:
        return []
    ids = np.array([r["passage_id"] for r in rows])
    mat = np.frombuffer(b"".join(r["vec"] for r in rows),
                        dtype=np.float32).reshape(len(rows), -1)
    sims = mat @ query_vec.astype(np.float32)
    order = np.argsort(-sims)[:limit]
    return [(int(ids[i]), float(sims[i])) for i in order
            if sims[i] >= min_similarity]
