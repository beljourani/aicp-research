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
   (LibreOffice fallback), `shamela` (taken over from the online collection: the page number comes
   from there unchanged and was never recomputed) — and the UI shows it. Keep it flowing end to end;
   it is how the user knows whether a page number is safe to cite.
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
python3 engine/tests/test_authors.py
python3 engine/tests/test_textlayout.py
python3 engine/tests/test_bookmarks.py
python3 engine/tests/test_hybrid.py
python3 engine/tests/test_library_io.py

# Shamela-Server: läuft ohne Qdrant/Netz (Attrappe statt Server)
python3 server/test_meta.py
python3 server/test_build_fts.py
python3 server/test_search_hybrid.py

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

**Indexing pipeline** (`engine/echo_engine/`): `extract.py` → `textlayout.py` → `chunker.py` →
`normalize.py` → `db.py`/`indexer.py`.

- `extract.py`: file → `list[(page_no, text)]`. PDF via PyMuPDF (page-accurate); DOCX via the
  Word → cloud → LibreOffice cascade described above (DOCX itself has no page concept), with a
  plain-text fallback that is marked unreliable; TXT gets synthetic ~2000-char pages. Scanned PDFs are
  detected (missing or broken text layer) and routed to OCR — Apple Vision on macOS, Tesseract (`ara`)
  otherwise.
- `textlayout.py`: turns extracted lines into readable paragraphs — the reader shows `pages.text`
  verbatim (`white-space: pre-wrap`), so *one paragraph = one line, paragraphs separated by a blank
  line* is a stored-format contract, not a display detail. `paragraphs_from_boxes()` reconstructs the
  original paragraphs from line geometry (PDF text layer, Apple Vision), `paragraphs_from_groups()`
  takes Tesseract's own `block_num`/`par_num` from its TSV output, `join_wrapped_lines()` is the
  text-only fallback used for already-stored pages. It may only ever change whitespace (plus NFKC) —
  `letter_count()` is the invariant that guards this. Careful with Arabic character ranges here: the
  old cleanup regex reached past the combining marks into the Arabic-Indic digits and ate the space
  before every page/verse number.
- `indexer.LAYOUT_VERSION`: bump this when the paragraph logic changes — `ensure_text_layout_version()`
  then re-runs the text-only cleanup over stored `pages.text` on next app start. It deliberately leaves
  `passages`, `passages_fts` and `bookmarks` alone, so search results and bookmarks stay put; only the
  reader display improves. Books re-read via "Neu einlesen" get the better geometry-based result.
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

## Shamela online search (`server/` + app integration)

Optional second search source: the ~8,600 books of *Al-Maktaba Al-Shamela*, searched on a small
self-hosted server without storing the books locally. The core app stays fully offline; Shamela is an
opt-in add-on the user connects once.

**Online search is word/root search, not semantic search.** The server carries its own FTS5 index
(`fts.db`, 11.5M chunks, `norm` weighted 2× / `stems` 1×, BM25) built through the same
`normalize.to_index_forms` as the local library, and imports the engine's own `_group_expr` — so
AND / OR groups / exclusions / phrases behave **exactly** as offline. Vectors only re-rank the output
page; they never add a hit. Do not describe this service as "semantic" — that wording was already
wrong once and led to the boolean filters being hidden in the UI for a release.

- **`server/`** is a standalone FastAPI service the user deploys on a VPS (~15–30 €/month). It imports
  the pre-embedded HF dataset `Maktabati/shamela-vectors` (11.5M chunks, `intfloat/multilingual-e5-base`,
  768-dim cosine) into **Qdrant** (int8 quantization) plus a small `meta.db` (books/pages index for
  paging & filter lists). `import_shamela.py` does the one-time load; `api.py` serves `/search`
  (embeds the query server-side with the `query:` prefix — the app ships no embedding model for this),
  `/page` (reconstructs a full page from its chunk payloads via char offsets, with neighbour pages for
  the reader), `/categories`, `/authors`, `/health`. `docker-compose.yml` runs Qdrant + API + Caddy
  (auto-HTTPS). Deploy guide: `server/SHAMELA-SERVER.md`. **This code cannot be tested in the sandbox**
  (no 43 GB data, no Qdrant, network-blocked) — verification happens on the user's VPS after deploy.
- **What the dataset actually contains** (measured on the live server, 2026-07-25): each chunk payload
  has only `title`, `author`, `death_year`, `page`, `char_start`, `char_end`, `chunk_no`, `source`,
  `text`, `text_norm`. There is **no `book_id`, `page_id`, `sequence_num`, `part`, `page_num` or
  `category_name_ar`** — `import_shamela.py`'s `PAYLOAD_FIELDS` list those, but they never exist, so
  `upsert_meta` skipped every row (`if bid is None: continue`) and left `meta.db` empty. Consequently:
  - Book identity is derived, not given: `meta_index.book_id(title, author)` — a stable 48-bit hash.
    Two genuinely different books sharing title *and* author would merge; no such case seen so far.
  - Reading order comes from the `page` string (`V01P441` = part 1, page 441; also `P032`, `43:1`
    for Quran, `المقدمة_P005`). `meta_index.parse_page()` decodes it; `page_sort_key()` orders it.
  - `seq` is an **internal** sheet number (dense 1..N per book) built lazily on first open and cached
    in `meta.db` (`book_index`/`page_index`). The page list comes from `chunk_meta` in `fts.db`
    (`_seiten_aus_wortindex`), **not** from Qdrant: scrolling Qdrant took 45–195 s for the large books
    and blew the app's 60 s limit, so they could not be opened at all. Qdrant remains as a fallback
    (`_seiten_aus_qdrant`), and `_seiten_aus_wortindex` returns `None` — never `[]` — when it cannot
    answer, because an empty list would be written as "book has no pages" and make the book
    permanently unopenable. `/health` counts how often the fallback fired (`rueckfall_qdrant`).
    After rebuilding `fts.db`, reset `page_index`/`book_index.indexed` (see `SHAMELA-SERVER.md`).
    The **displayed** page label stays the real printed page (`part`/`page_num`) — decoded from the
    source, never re-numbered. `/search` therefore returns `seq: null`; the reader opens via `page`.
  - `meta_index.py` holds this logic free of FastAPI/Qdrant so `server/test_meta.py` can run anywhere.
  - Still broken by the same root cause: `/categories` returns nothing (no category field in the data
    at all) and `/authors` reads the empty `books` table.
- **Token & URL are secrets** — they live only in the app's `meta` table (keys `shamela_url`,
  `shamela_token`), entered once in Settings (gear next to the source toggle) and persisted. They are
  **never** baked into the repo and **never** returned to the browser JS: the app talks to the server
  **server-side** in `main.py` (`_shamela_request` via stdlib `urllib`), so the token stays in the
  Python process. `/api/shamela_status` reports only `configured` + `url`, never the token.
- **App endpoints** (`main.py`): `shamela_status` / `shamela_save` (saves + tests `/health`) /
  `shamela_clear` / `shamela_search` / `shamela_page` / `shamela_categories` / `shamela_authors`.
- **The search chips go to the server structurally, never as a text query.** `shamela_search` sends
  `and_groups` + `excludes` (the same shape the local `/api/search` takes in `mode:"terms"`); the
  server turns them into query groups with `search.groups_from_terms()` — literally the same function
  `structured_search` uses offline. `q` is still sent alongside (built by `search.query_from_terms`)
  purely as a fallback for a server that predates the structured fields; without it such a server
  would silently drop the exclusions. Never go back to serializing chips into query syntax as the
  primary path: a chip that reads `أو`/`oder`/`or`, starts with `-`, or contains `|` has its own
  meaning in that syntax and would be misread.
- **Frontend**: a source toggle (`searchSource` = `local` | `shamela`) at the top of the search view.
  Both sources show the same controls — AND fields, OR groups, the red exclusion field, book filter
  and semantic checkbox. Only the category filter is hidden online (`shHasCats`), because the dataset
  has no categories at all. Author/book filters are populated from the server.
  Results open a **remote reader** that reuses the whole reader
  shell: `rRemote`/`rBook` branch only the data source (`ensurePages` → `shamela_page`) and the page
  label (Shamela sheets are keyed by the internal `seq` described above; the sheet label shows the real
  `ج<part> ص<page>`). The first open passes `page` (the source's page string) instead of `seq`, since
  `seq` only exists once the server has built that book's page index.
  Everything else (continuous scroll, prune/prefetch, arrow keys, page jump, progress, font, tashkil,
  in-book search, cite-with-source) works unchanged because it operates on abstract sheet numbers.
- **Taking a book over into the local library** (`/book_info` + `/book` on the server,
  `shamela_download` in the app): a whole book can be downloaded once and then lives in the offline
  library like any other. The server reconstructs pages **blockwise** (500 sheets, hard cap
  server-side) — the largest book has 231 MB of text and 90,751 sheets, so a single response is not
  deliverable. `_reconstruct_pages` is the **only** place that stitches chunks; `/page` calls it too,
  so the taken-over text cannot drift from what the online reader shows.
  - **`pages.page_no` now has two meanings**: for PDF/Word/TXT it is the printed page; for a
    taken-over book it is a dense, gapless sheet number, because a quarter of the Shamela books are
    multi-volume and each volume restarts at page 1 (`UNIQUE(document_id, page_no)` would break).
    The real printed page lives in `pages.page_label` (`ج1 ص441`). **Anything that displays or cites
    a page number must check `page_label` first** — otherwise it prints a wrong page, which is
    exactly what non-negotiable 1 forbids. Books without a label behave exactly as before.
  - The reconversion helpers are in `echo_engine/shamela_import.py` (pure, no net, no DB, tested).
  - Semantic vectors are **off by default** for taken-over books (`documents.embed_semantic`):
    `semantic.vector_search` loads *all* vectors of the whole library on every query, so one large
    book would slow down semantic search over the user's own books. `embed_passages` honours the
    column, including the backfill at app start — without that the switch would be pointless.

## Frontend conventions (`app/ui/index.html`)

One file, no build step, no framework. It is long — use the section comments to navigate.

- **German UI, Arabic as second language.** Every user-facing string goes into the `T.de` / `T.ar`
  dictionaries and is applied in `applyLang()`. Arabic switches the whole layout to RTL.
- **No emojis** anywhere in the UI or in generated documents.
- **Arabic is set at the same size as German**, only heavier if needed — the German view is the
  yardstick. Do not inflate the RTL layout.
- **Fonts are bundled** in `app/ui/fonts/` (Noto Sans Arabic for the UI, Amiri / Scheherazade New /
  Noto Naskh for the reader, each with its OFL licence file). They are loaded via `@font-face` from
  the local server — nothing is fetched from a CDN, which is what keeps the app fully offline.
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
- **The reader is virtualised.** Only a window of ~41 real `.pageSheet` nodes exists at any time
  (`HALF=20` around the current page); above and below sits one `.pageSpacer` div whose height stands
  in for the pages that are not rendered. It used to create one node per book page — 63,513 nodes for
  a big Shamela book — which was unusable on weaker machines. Text is still loaded lazily in ranges
  (`BEHIND`/`AHEAD`); `KEEP` only bounds the *text cache* now, not the DOM.
  - Height model: `rHeights[p]` per measured page, unmeasured ones estimated from the running average;
    `offsetOf()`/`pageAtOffset()` work on prefix sums.
  - **Browsers cap an element's height at 2^25 px** (33,554,432). A 63,513-page book would need ~70 M px,
    the spacers got truncated and every far jump landed wrong (target 63000 → 30139). The scroll height
    is therefore compressed (`MAXH`); inside the window real heights still apply.
  - `visiblePage()` reads the page off the DOM inside the window (~41 nodes) and only estimates from
    the model outside it. Anything that shifts heights (window slide, refill, tashkil toggle) must
    re-anchor the scroll position on a page via `sheetY()` — otherwise the reading position drifts.
  - `sheetOf(p)` returns `null` for pages outside the window. Every caller must cope with that.
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
  **Per-user install** (`PrivilegesRequired=lowest`, so `{autopf}` resolves to
  `%LOCALAPPDATA%\Programs`): installing into `Program Files` needs admin rights, and Windows then
  shows the UAC prompt on *every* update — even with `/SILENT`. Without admin rights the silent
  update really is silent, like on macOS. A second `[Run]` entry (`skipifnotsilent`) restarts the app
  after a silent update; relying on `RestartApplications` alone was racy because the app exits itself
  so its files can be replaced. A double start is harmless — the single-instance lock just focuses
  the existing window.
  Note: this only takes effect for releases built *after* the change; the currently installed
  version still performs one last update the old way, and the move from `Program Files` to the
  per-user folder needs one manual reinstall (otherwise two installations sit side by side).
- `AICP-Research-macOS-<ver>.zip` — the `.app` bundle, used for **automatic** macOS updates. A detached
  shell script waits for the app to quit, swaps the bundle in place, strips the quarantine attribute
  and relaunches.
- `AICP-Research-<ver>.dmg` — first-time macOS install only (built with `create-dmg`, shows the
  drag-to-Applications window). The updater must not prefer it.

Renaming these breaks self-update silently. If you change them, update `_pick_asset` in the same commit.

Other things worth knowing:
- **The "Was ist neu" text is the GitHub Release *body*** (`updater.release_notes` → release `body`,
  shown by `openNews` via `/api/whats_new`, cached in `meta`). CI does **not** set it — the workflows use
  `softprops/action-gh-release` without a `body`, so the body is empty unless you set it. After tagging,
  set it explicitly: `gh release edit vX.Y.Z --notes-file NOTES.md` (softprops preserves an existing body
  when it later attaches the installers — but re-verify body + assets once the builds finish).
- **Release notes must be bilingual (German + Arabic)** — the app runs in either language and users read
  these. Format the body as: German section, then a line `<!--ar-->`, then the Arabic section. The HTML
  comment is invisible on the GitHub release page; in the app, `notesForLang(body, lang)` shows only the
  active language (falls back to the other; a body with no marker shows as-is). This is the same
  DE+AR rule as UI strings (`T.de`/`T.ar`) — nothing user-facing ships in only one language.
- A change to the *update mechanism itself* only takes effect for updates **after** the version that
  introduces it; the installed older version still runs its own updater code. (So the language-aware
  notes above are live from the **first release built after** they were added, not retroactively.)
- Builds are unsigned. macOS shows "unidentified developer" on first manual launch (right-click → Open);
  the auto-update path avoids this by removing the quarantine attribute.

## Diagnosis on the user's machine

There is no console on Windows: `build/echoarchive.spec` packs with `console=False`, so in the running
app `sys.stdout`/`sys.stderr` are `None` and every `print()` and traceback is silently dropped. Without
a file there is *no* way to learn why something failed on the user's laptop — the UI's friendly
sentence ("Die Datei konnte nicht eingelesen werden.") is all he can see.

- `data_dir()/protokoll.txt` is that file. `protokolliere()` appends timestamped lines and rotates once
  at ~1 MB (`protokoll-alt.txt`). `protokoll_einrichten()` re-points `sys.stdout`/`sys.stderr` into it
  when they are `None`, so existing `print()`/`traceback.print_exc()` calls are captured too.
- `fehler_melden(kontext, exc)` writes the **full traceback** to the log and returns the short technical
  reason for the UI. Every failing job carries it as `error_detail` next to the friendly `error` text.
  `technischer_grund()` appends the code location (`extract.py:159 in extract_pdf`) — the message alone
  ("DLL load failed") does not say whether it broke while opening the PDF or during OCR.
- "Kein Text gefunden" is a **second, exception-free** way an import fails. `_leer_grund()` reports
  pages/characters/engine for it, which is what distinguishes "file could not be opened at all"
  (`Seiten=0`) from "scan whose OCR produced nothing" (`Seiten=248 · Zeichen=0`).
- Reachable from the UI: every error row has *Fehlerbericht kopieren* / *Protokoll anzeigen*, plus a
  permanent *Protokoll anzeigen* entry in the sidebar (`/api/protokoll`, `/api/open_protokoll`).
- The technical detail is Latin text and must stay `direction: ltr; text-align: left` — the Arabic
  RTL layout otherwise reverses it into something unreadable.

## Pitfalls already paid for

- **Job rows are only ever built by `refreshStatus()`, and polling stops when nothing is running.**
  Anything that must change with the language has to trigger a re-render explicitly; `applyLang()`
  alone left a finished error row standing in German inside an otherwise Arabic UI.
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
