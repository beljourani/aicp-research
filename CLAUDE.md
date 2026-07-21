# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AICP Research (formerly "EchoArchive") is a local desktop app (macOS/Windows) for full-text search over
Arabic-heavy document libraries (PDF, DOCX, TXT). No server, no accounts, no ongoing costs — everything
runs and stays on the user's machine. Product-facing docs and setup guides are in German
(README.md, START_HIER.md, WINDOWS-ANLEITUNG.md, SETUP-GITHUB.md); code comments/docstrings are also
German. Keep new comments/docstrings in German to match the existing codebase.

The user is a researcher, not a developer. He works in German, uses Windows as the main device and
macOS for development, and cares about the reading and citation experience far more than internals.

## Non-negotiables (read before changing anything)

These are product promises, not preferences. Breaking one silently is the worst failure mode here.

1. **Page numbers must match the original document exactly.** The point of the app is that a quote can
   be cited as "(Title, S. 123)" and someone holding the same PDF/Word file finds it on that page.
   Never re-flow, re-paginate or otherwise "improve" pagination.
2. **DOCX page numbers come from Microsoft Word when it is installed.** `extract.py` runs a cascade:
   local Word (AppleScript on macOS / COM on Windows) → cloud conversion (prepared but disabled) →
   LibreOffice as a last resort. Word is exact; LibreOffice drifts (measured: +13 pages on a
   530-page book). Do not collapse this cascade down to LibreOffice.
3. **Every hit carries a `reliability` value** — `sicher` (PDF), `exakt` (Word engine), `ungefähr`
   (LibreOffice fallback) — and the UI shows it. Keep it flowing end to end; it is how the user knows
   whether a page number is safe to cite.
4. **Fully offline, free, no accounts, no telemetry, no paid services.** The only network calls are the
   optional self-update check and one-time component downloads.
5. **Identical behaviour on Windows and macOS.** A feature that works on only one platform is not done.

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
python3 engine/tests/test_highlight.py
python3 engine/tests/test_categories.py

# run a single test function: import and call it directly, e.g.
python3 -c "import sys; sys.path.insert(0,'engine'); sys.path.insert(0,'engine/tests'); from test_engine import test_stemming; test_stemming()"
```

Double-clickable helper scripts for the user (macOS): `EchoArchive.command` (start),
`tools/Neustart.command` (restart, keeps library), `tools/Neustart-Sauber.command` (restart with a
fresh database), `tools/Diagnose.command`. If you bulk-edit these files with a tool that rewrites
them, re-apply `chmod +x` — losing the executable bit makes macOS refuse to open them ("no
permission") — and quote every path containing a space (`AICP Research`). Both have broken the app before.

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

- `extract.py`: file → `list[(page_no, text)]`. PDF via PyMuPDF (page-accurate); DOCX via the
  Word → cloud → LibreOffice cascade described above (DOCX itself has no page concept), with a
  plain-text fallback that is marked unreliable; TXT gets synthetic ~2000-char pages. Scanned PDFs are
  detected (missing or broken text layer) and routed to OCR — Apple Vision on macOS, Tesseract (`ara`)
  otherwise.
- `chunker.py`: splits page text into ~700–1100 char passages that never cross a page boundary, so
  every search hit has an exact page range. Fragments under `MIN_LETTERS` real letters are dropped.
- `normalize.py`: two-tier Arabic text handling — `normalize()` strips tashkil/tatweel and unifies
  alif/ya/ta-marbuta variants (used for the "exact" index and display mapping); `stem()` reduces words
  to their root via ISRI stemming (falls back to a light prefix/suffix stemmer if `nltk` is unavailable)
  so conjugations match (كتب finds يكتب، كتبت، يكتبون). Index and query must use identical
  normalize/stem logic or matching breaks.
- `db.py`: SQLite schema. `passages_fts` is an FTS5 table with two fields — `norm` (exact form,
  weighted higher) and `stems` (root form) — searched together for hybrid exact+root ranking (see
  `search.py`'s BM25 combination). `categories` / `document_categories` give books an n:m category
  assignment. Bookmarks intentionally have no FK cascade to `documents`/`passages`; they're re-matched
  by title+page+snippet after a document is re-indexed, since internal IDs can change.
- `indexer.STEM_VERSION`: bump this when normalize/stem logic changes — `ensure_index_version()` then
  transparently rebuilds `passages_fts` from stored passage text on next app start (no re-extraction of
  original files needed).
- `semantic.py`: optional local embedding search (fastembed, `paraphrase-multilingual-MiniLM-L12-v2`,
  384-dim), brute-force cosine over NumPy against BLOBs in `passage_vectors`. Lazy-loaded; the app stays
  usable via full-text search while the model loads/downloads on first run. `search.hybrid_search`
  combines this with the FTS ranking when available.
- `search.py`: query language — space = AND (root-based), `|`/`oder`/`or`/أو = OR between groups,
  leading `-` = exclude, `"..."` = exact phrase (no stemming). See its module docstring for details.
  `highlight_spans(text, terms)` returns root-aware highlight ranges against the real page text, so
  inflected and tashkil-bearing forms get marked too. Search takes `limit`/`offset`; callers request
  `limit + 1` to detect whether more results exist.

**App-layer conventions** (`app/main.py`):
- Multiple authors for one document are stored in a single `author` TEXT column, joined by `" ؛ "`
  (Arabic semicolon) — see `split_authors`/`join_authors`. Don't switch this to a separate table without
  also handling existing stored strings.
- If both a `.pdf` and `.docx` exist for the same book (same filename stem), the DOCX is skipped at
  import time (`_filter_duplicates`) — the PDF has the real printed page numbers.
- Background work (indexing, export, import, update download) runs on daemon threads and reports
  progress through the `_jobs`/`_order` dicts, polled by the frontend via `/api/status`.
  `MAX_WORKERS = 2` is deliberate — more threads made indexing slower and caused SQLite lock errors,
  since there is only one writer. The DB uses WAL and `busy_timeout=60000`.
- `data_dir()` auto-migrates an old `EchoArchive` data folder to `AICP Research` on first run after the
  rename — needed for users upgrading from before the rename.
- `.echolib` is the custom library export/import format (`echo_engine/library_io.py`) for moving a
  whole library or a selection between machines. Import must recompute the FTS index via
  `to_index_forms()` — a contentless FTS5 table cannot be read back out, so copying rows alone silently
  produces a library that finds nothing.
- Small key/value settings (reading position per book, font scale, seen version, cached release notes)
  live in the `meta` table via `/api/meta_get` / `/api/meta_set`.

## Frontend conventions (`app/ui/index.html`)

One file, no build step, no framework. It is long — use the section comments to navigate.

- **German UI, Arabic as second language.** Every user-facing string goes into the `T.de` / `T.ar`
  dictionaries and is applied in `applyLang()`. Arabic switches the whole layout to RTL.
- **No emojis** anywhere in the UI or in generated documents.
- Design language: minimal and calm (Notion/Linear feel), teal accent (`--accent`), generous
  whitespace, no decorative noise. New UI should look like it was always there.
- **The search UI is field- and chip-based.** The engine has a query syntax, but the user must never
  have to type operators: one field per AND-group, a separate red-framed field for exclusions, buttons
  to add an OR-group. The red styling of the exclusion field is meaningful — it signals "these words
  are filtered out".
- The primary action (`Suchen`) is the **last step at the bottom**, full width, below all fields and
  filters. Secondary actions sit above it.
- Actions that apply to a selection (export/delete) stay hidden until something is selected.
- **Every key you handle must call `e.preventDefault()`.** On macOS an unhandled key produces the
  system error beep, which makes working keys feel broken. Applies to Enter in every input, Escape
  everywhere, and Backspace when it removes a chip.
- The reader renders one `.pageSheet` per page and lazily loads text in ranges via `/api/pages`, keeping
  a prefetch window (`BEHIND`/`AHEAD`) and discarding pages further than `KEEP` away. `KEEP` must stay
  larger than the prefetch window, otherwise pages are dropped and re-fetched in a loop.
- Long async flows (e.g. `openReader`) must wrap each risky step in its own `try/catch`. A single
  failing `await` used to abort the rest of the function and leave the UI half-initialised.

## Release & self-update

The version number lives **only in the git tag**. CI writes it into `VERSION`, the app reads it from
there, and the macOS bundle and Windows installer inherit it.

To publish a version: bump `VERSION` and commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
Both workflows then build and attach the installers to a GitHub Release automatically.

Assets and why their names matter (`echo_engine/updater.py` → `_pick_asset`):
- `AICP-Research-Setup-<ver>.exe` — Windows installer. Auto-update runs it silently
  (`/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`); `installer.iss` sets `CloseApplications=yes`.
- `AICP-Research-macOS-<ver>.zip` — the `.app` bundle, used for **automatic** macOS updates. A detached
  shell script waits for the app to quit, swaps the bundle in place, strips the quarantine attribute
  and relaunches.
- `AICP-Research-<ver>.dmg` — first-time macOS install only (built with `create-dmg`, shows the
  drag-to-Applications window). The updater must not prefer it.

Renaming these breaks self-update silently. If you change them, update `_pick_asset` in the same commit.

Other things worth knowing:
- **The commit message becomes the release body**, which the app shows in its "Was ist neu" dialog after
  an update (`/api/whats_new`, cached in `meta`). Write release commits as a short title plus `-` bullet
  points, in German — end users read them.
- A change to the *update mechanism itself* only takes effect for updates **after** the version that
  introduces it; the installed older version still runs its own updater code.
- Builds are unsigned. macOS shows "unidentified developer" on first manual launch (right-click → Open);
  the auto-update path avoids this by removing the quarantine attribute.

## Pitfalls already paid for

- **A search can consist of exclusions only**, with no positive terms. Then there are no matched words
  to highlight and no terms to re-run inside the reader. Code that assumes "there are always search
  terms" fails in ways that look like an unrelated bug. Pass the full query (groups *and* exclusions),
  not just the terms.
- Re-indexing a document deletes and recreates its rows, so **passage IDs change**. Anything storing a
  passage reference (bookmarks) needs a fallback path.
- Fonts change pagination. Bundling and forcing our own fonts for DOCX conversion made page numbers
  *worse*; the document's original fonts plus real Word is what makes them exact.
- `hdiutil` / `ditto` / `rm` on paths containing `AICP Research` need quotes; an unquoted path once made
  the "clean restart" script delete nothing while reporting success.
- PyInstaller fails with "access denied" if the app is still running — terminate it before rebuilding.
- When debugging UI behaviour, **run the app and look**. Reasoning about this frontend from source alone
  produced three wrong fixes in a row once; a single screenshot found the real cause immediately.

## Working style

- For anything larger than a bugfix, **discuss the approach first** and offer options with trade-offs.
  The user likes to decide on the design before code is written.
- Explain what changed in plain German, focused on what he can now do differently — not a diff summary.
  Keep it short.
- Prefer verifying over asserting: run the engine tests, run the app, check a real Arabic book with
  known page numbers.
- Be conservative with new dependencies. The Windows installer is already ~514 MB and everything must
  keep working offline.
- Never delete or overwrite the user's library (`~/Library/Application Support/AICP Research` or
  `%APPDATA%\AICP Research`). Uploaded originals and the database live there and must survive updates,
  re-installs and renames.
