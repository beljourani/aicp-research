# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AICP Research (formerly "EchoArchive") is a local desktop app (macOS/Windows) for full-text search over
Arabic-heavy document libraries (PDF, DOCX, TXT). No server, no accounts, no ongoing costs — everything
runs and stays on the user's machine. Product-facing docs and setup guides are in German
(README.md, START_HIER.md, WINDOWS-ANLEITUNG.md, SETUP-GITHUB.md); code comments/docstrings are also
German. Keep new comments/docstrings in German to match the existing codebase.

## Commands

Run from the repo root.

```bash
# install deps (Python 3.11+ required — system Python on macOS is too old for pyobjc)
python3 -m pip install -r requirements.txt

# run the app
python3 app/main.py

# run all engine tests (plain scripts, not pytest — each has a __main__ block)
python3 engine/tests/test_engine.py
python3 engine/tests/test_boolean_search.py

# run a single test function: import and call it directly, e.g.
python3 -c "import sys; sys.path.insert(0,'engine'); sys.path.insert(0,'engine/tests'); from test_engine import test_stemming; test_stemming()"
```

Building distributable binaries (rarely needed for code changes — CI does this on tag push):
- Windows: `Build-Windows.bat` → PyInstaller (`build/echoarchive.spec`) + Inno Setup (`build/installer.iss`)
- macOS: `Build-DMG.command`
- Releases are built by `.github/workflows/build-windows.yml` / `build-macos.yml` on `v*` tags, which
  bundle the embedding model and Tesseract (`ara`+`deu` traineddata) into the installer.

## Architecture

**Two layers, cleanly separated:**

- `engine/echo_engine/` — the search engine. Pure Python, no UI/webview dependency, unit-tested in
  isolation (`engine/tests/`). This is the part that must stay correct and well-tested; treat it as a
  library.
- `app/` — the desktop shell. `app/main.py` runs a `ThreadingHTTPServer` bound to `127.0.0.1` only
  (never exposed externally) and points a `pywebview` window at it. `app/ui/index.html` is a single-file
  frontend (vanilla HTML/JS/CSS, no build step) that talks to the local server via `/api/*` routes
  defined in the `ROUTES` dict in `main.py`. This indirection through a real HTTP server (instead of
  pywebview's JS bridge) is deliberate — the bridge was found too fragile.

**Indexing pipeline** (`engine/echo_engine/`): `extract.py` → `chunker.py` → `normalize.py` → `db.py`/`indexer.py`.

- `extract.py`: file → `list[(page_no, text)]`. PDF via PyMuPDF (page-accurate); DOCX is converted to
  PDF via LibreOffice first so page numbers are real (DOCX itself has no page concept) — plain-text
  fallback exists but is marked unreliable; TXT gets synthetic ~2000-char pages. Scanned PDFs are
  detected (no text layer) and flagged `needs_ocr` for the Tesseract (`ara`) hook.
- `chunker.py`: splits page text into ~700–1100 char passages that never cross a page boundary, so
  every search hit has an exact page range. Fragments under `MIN_LETTERS` real letters are dropped.
- `normalize.py`: two-tier Arabic text handling — `normalize()` strips tashkil/tatweel and unifies
  alif/ya/ta-marbuta variants (used for the "exact" index and display mapping); `stem()` reduces words
  to their root via ISRI stemming (falls back to a light prefix/suffix stemmer if `nltk` is unavailable)
  so conjugations match (كتب finds يكتب، كتبت، يكتبون). Index and query must use identical
  normalize/stem logic or matching breaks.
- `db.py`: SQLite schema. `passages_fts` is an FTS5 table with two fields — `norm` (exact form,
  weighted higher) and `stems` (root form) — searched together for hybrid exact+root ranking (see
  `search.py`'s BM25 combination). Bookmarks intentionally have no FK cascade to `documents`/`passages`;
  they're re-matched by title+page+snippet after a document is re-indexed, since internal IDs can change.
- `indexer.STEM_VERSION`: bump this when normalize/stem logic changes — `ensure_index_version()` then
  transparently rebuilds `passages_fts` from stored passage text on next app start (no re-extraction of
  original files needed).
- `semantic.py`: optional local embedding search (fastembed, `paraphrase-multilingual-MiniLM-L12-v2`,
  384-dim), brute-force cosine over NumPy against BLOBs in `passage_vectors`. Lazy-loaded; the app stays
  usable via full-text search while the model loads/downloads on first run. `search.hybrid_search`
  combines this with the FTS ranking when available.
- `search.py`: query language — space = AND (root-based), `|`/`oder`/`or`/أو = OR between groups,
  leading `-` = exclude, `"..."` = exact phrase (no stemming). See its module docstring for details.

**App-layer conventions** (`app/main.py`):
- Multiple authors for one document are stored in a single `author` TEXT column, joined by `" ؛ "`
  (Arabic semicolon) — see `split_authors`/`join_authors`. Don't switch this to a separate table without
  also handling existing stored strings.
- If both a `.pdf` and `.docx` exist for the same book (same filename stem), the DOCX is skipped at
  import time (`_filter_duplicates`) — the PDF has the real printed page numbers.
- Background work (indexing, export, import, update download) runs on daemon threads and reports
  progress through the `_jobs`/`_order` dicts, polled by the frontend via `/api/status`.
- `data_dir()` auto-migrates an old `EchoArchive` data folder to `AICP Research` on first run after the
  rename — needed for users upgrading from before the rename.
- `.echolib` is the custom library export/import format (`echo_engine/library_io.py`) for moving a
  whole library or a selection between machines.

**Self-update**: `echo_engine/updater.py` checks GitHub Releases on the configured `update_repo`
(default `beljourani/aicp-research`), downloads the platform installer, and relaunches it, then exits
the app so the installer can replace it in place.
