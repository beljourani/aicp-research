# AICP Research – Arabisches Dokumentarchiv mit Volltextsuche

Lokale Desktop-App (macOS/Windows) zum Durchsuchen von Büchern und
Dokumenten (PDF, Word, TXT) – arabisch-optimiert, kostenlos, offline.
Kein Server, keine Konten, keine laufenden Kosten: Alles läuft und bleibt
auf dem eigenen Rechner.

## Was die App kann

**Suche**

- Arabische Normalisierung (Tashkil, Alif-Varianten, Ta Marbuta, Ziffern)
- Wurzel-Suche (ISRI-Stemming): كتب findet يكتب، كتبت، يكتبون، كَتَبَ
- Artikelloses Wort findet auch die ال-Form (ست findet الست)
- Suchfelder statt Syntax: eine UND-Gruppe je Feld, ODER-Gruppen per Knopf,
  ein eigenes rot umrandetes Feld für Ausschlüsse, Wortgruppen in
  Anführungszeichen
- Optional zusätzlich sinnverwandte Treffer (Bedeutungssuche); sie ändert
  nur die Reihenfolge, nie die Treffermenge
- Der Ausschnitt eines Treffers zeigt zu jedem Suchbegriff eine Fundstelle

**Lesen und Zitieren**

- Leser mit durchgehendem Lesefluss, Seitensprung und Treffer-Navigation
- Seitenangaben entsprechen exakt der Druckseite des Originals
- Jeder Treffer trägt eine Verlässlichkeitsangabe (`sicher` / `exakt` /
  `ungefähr`), damit klar ist, ob eine Seitenzahl zitierfähig ist
- Vokalzeichen ein-/ausblendbar, Schriftart und -größe einstellbar
- Zitat mit Quellenangabe, Lesezeichen mit eigenen Notizen

**Bibliothek**

- PDF seitengenau (PyMuPDF), gescannte PDFs per OCR (Apple Vision auf dem
  Mac, sonst Tesseract)
- Word-Dateien über eine Kaskade: lokales Word → Cloud-Umwandlung →
  LibreOffice. Word liefert exakte Seitenzahlen; LibreOffice weicht ab
  (gemessen: +13 Seiten bei einem 530-Seiten-Buch) und wird deshalb als
  „ungefähr" gekennzeichnet
- TXT mit künstlichen Seiten
- Sammlungen (Kategorien) und Autoren, jeweils mehrere je Buch möglich
- Bibliothek als `.echolib` exportieren und auf einem anderen Rechner
  importieren

**Optional: Shamela online**

Zusätzliche Quelle mit den rund 8.600 Büchern der Maktaba Shamela, die auf
einem selbst betriebenen kleinen Server durchsucht werden. Die Kern-App
bleibt vollständig offline; die Online-Suche ist eine Erweiterung, die
einmalig eingerichtet wird (siehe `server/SHAMELA-SERVER.md`).

## Loslegen

- **macOS:** siehe `START_HIER.md`
- **Windows:** siehe `WINDOWS-ANLEITUNG.md`

## Tests

Die Such-Engine ist unabhängig von der Oberfläche testbar:

```bash
python3 engine/tests/test_engine.py
python3 engine/tests/test_boolean_search.py
python3 engine/tests/test_highlight.py
python3 engine/tests/test_categories.py
python3 engine/tests/test_authors.py
python3 engine/tests/test_textlayout.py
python3 engine/tests/test_bookmarks.py
python3 engine/tests/test_hybrid.py
python3 engine/tests/test_library_io.py
```

## Architektur-Entscheidungen

- **Zwei Schichten:** `engine/echo_engine/` ist die Such-Engine (reines
  Python, ohne Oberfläche, einzeln getestet). `app/` ist die Desktop-Hülle:
  ein lokaler HTTP-Server auf `127.0.0.1` und ein Fenster darauf.
- **Keine Server, keine Konten, keine laufenden Kosten.** Die einzigen
  Netzzugriffe sind die freiwillige Update-Prüfung und einmalige Downloads
  von Komponenten.
- **Dateien bleiben, wo sie sind** (auch in Cloud-Ordnern); die App legt
  nur ihren Suchindex an.
- **Word-Seitenzahlen kommen von Word**, nicht von einem Ersatzprogramm –
  nur so stimmen die Seitenangaben mit dem Original überein.
- **Schriften sind mitgeliefert** (`app/ui/fonts/`), nichts wird von einem
  CDN nachgeladen.
