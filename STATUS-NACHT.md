# Nachtarbeit Shamela — Stand 25.07.2026

Kurzfassung: **Phase 1 ist erledigt und live verifiziert — Bücher lassen sich wieder öffnen.**
Phase 2 und 3 sind umgesetzt, getestet und ausgerollt; was nur mit Blick in die App prüfbar ist,
steht unten unter „Morgens zu prüfen".

---

## Wichtigster Punkt: Die Ursache war eine andere als vermutet

Der Plan ging davon aus, dass nur `sequence_num` fehlt. Die Diagnose gegen den Live-Server hat
etwas Grundlegenderes gezeigt — deshalb habe ich, wie im Entscheidungstor vorgesehen, gestoppt
und den Plan angepasst statt ihn blind umzusetzen.

| Angenommen | Tatsächlich gemessen |
|---|---|
| `book_id`/`page_id` vorhanden, nur `seq` fehlt | `book_id`, `page_id`, `sequence_num`, `part`, `page_num`, `category_name_ar` **existieren im Datensatz überhaupt nicht** |
| `meta.db` gefüllt, Ordnung lückenhaft | `meta.db` war **komplett leer**: 0 Bücher, 0 Seiten |

Der Importer überspringt jede Zeile ohne `book_id` (`import_shamela.py`, „`if bid is None: continue`") —
das traf auf **alle 11,5 Mio.** zu. Vorhanden sind real nur: `title`, `author`, `page` („V01P441"),
`char_start`, `char_end`, `chunk_no`, `source`, `death_year`, `text`.

**Angepasste Lösung:** Buchkennung wird stabil aus Titel+Autor abgeleitet, die Lesereihenfolge aus
der Seitenkennung. Der Seitenindex eines Buches entsteht beim ersten Öffnen (ein gefilterter
Qdrant-Zugriff, ~3 s) und wird gemerkt. **Kein Neu-Import, keine Neu-Einbettung** — die 43 GB
blieben unangetastet.

**Seitenzahlen:** Angezeigt werden weiterhin die echten Druckseiten (`V23P005` → „ج23 ص5"). Sie
werden nur aus der Quellangabe dekodiert, **nie neu vergeben**. `seq` ist eine rein interne
Blattnummer zum Blättern.

---

## Erledigt und LIVE verifiziert

**Phase 1 — Bücher öffnen**

| Prüfung | Ergebnis |
|---|---|
| `/health` | ok, 11.488.400 Punkte |
| Token-Prüfung ohne Token | 401 (greift) |
| `/search` liefert `book_id` | ja (vorher `null`) |
| Buch öffnen über Seitenkennung | ja — 553 Seiten, Text korrekt |
| Druckseiten-Label | „ج23 ص5" — echte Seite |
| Zweites Öffnen (gemerkt) | 0,28 s |
| Blättern per `seq` | ja |
| Suche innerhalb eines Buches | ja, nur dieses Buch |
| Zweites Seitenformat (`P032`, `مقدمة_P001`) | ja |
| Ganze Kette **durch die App** (`/api/shamela_*`) | ja |
| Absturz-Sicherung bei fehlenden Angaben | verständliche Meldung statt Absturz |

**Phase 2 — Filterlisten** (dieselbe Wurzel: `/authors` und `/categories` lasen die leere Tabelle)

- Bücherverzeichnis einmalig erhoben: **8.697 Bücher, 3.178 Autoren in 68 Sekunden**
  (per Facet-Abfrage statt Vollscan; ein Vollscan hätte ~3,5 Stunden gedauert).
- `/books` (neu, durchsuchbar/seitenweise), `/authors` (echte Liste mit Buchzahlen) — live geprüft.
- Ein Buch, nach dem noch nie gesucht wurde, lässt sich filtern **und** öffnen — live geprüft.
- `/categories` liefert bewusst `[]`: **Kategorien gibt es in diesem Datensatz nicht.**

**Phase 3 — Lesezeichen für Online-Bücher**

- Lesezeichen setzen → Liste → wieder entfernen: Rundlauf **durch die App** geprüft; die Liste zeigt
  die echte Druckseite „ج23 ص5".
- Migration der bestehenden Bibliothek lief sauber: 152 Dokumente, 86.497 Passagen unverändert,
  `integrity_check: ok`.

**Tests:** alle grün — 7 Engine-Testdateien (inkl. neuer `test_bookmarks.py`) plus
`server/test_meta.py` (11 Tests). Vor jedem Commit ausgeführt.

---

## Morgens von dir zu prüfen (committet, aber nur am Bildschirm beurteilbar)

Die Technik dahinter ist geprüft; wie es sich **anfühlt und aussieht**, habe ich bewusst nicht
bewertet:

1. **Buchfilter im Online-Modus** — er wird jetzt eingeblendet und schlägt beim Tippen Bücher vom
   Server vor. Zu prüfen: Fühlt sich das Tippen flüssig an, sind die Vorschläge sinnvoll?
2. **Kategoriefilter** — verschwindet im Online-Modus (es gibt dort keine Kategorien). Zu prüfen:
   Wirkt das stimmig oder fehlt dir ein Hinweis?
3. **Lesezeichen im Online-Leser** — der Knopf ist wieder da. Zu prüfen: Setzen, Liste öffnen,
   Eintrag anklicken → schlägt das Buch an der richtigen Stelle auf?
4. **Autorenfilter online** — die Liste kommt jetzt echt vom Server (vorher leer).

---

## Offen / bewusst nicht gemacht

- **Kategorien für Shamela sind nicht herstellbar.** Das Feld existiert im Datensatz nicht; das
  ließe sich nur über eine zusätzliche externe Kategorienliste nachrüsten. Entscheidung dazu bei dir.
- **Buchidentität = Titel + Autor.** Zwei wirklich verschiedene Bücher mit identischem Titel *und*
  identischem Autor würden zusammenfallen. In den Stichproben kein solcher Fall; sauberer wäre eine
  echte Buch-ID, die der Datensatz aber nicht liefert.
- **`import_shamela.py` schreibt weiterhin keine `meta.db`-Zeilen.** Für den laufenden Betrieb
  belanglos (die Daten kommen jetzt aus Qdrant), aber bei einem Neu-Import fiele es wieder auf.
  Bewusst nicht angefasst, um am laufenden Import nichts zu riskieren.
- **Nicht gepusht:** meine früheren Änderungen an `EchoArchive.command` / `tools/Neustart*.command`
  (die `.venv`-Einrichtung für diesen Mac) liegen unverändert im Arbeitsverzeichnis — sie gehören
  nicht zu diesem Auftrag und warten auf deine Entscheidung.

---

## Was ich am Server geändert habe

- `title` als Payload-Index in Qdrant angelegt (additiv, nötig für Buchsuche/Verzeichnis).
- `meta.db` um `book_index`, `page_index`, `catalog`, `author_index`, `build_state` ergänzt.
  Die alten, leeren Tabellen `books`/`pages` blieben unangetastet.
- API-Container neu gebaut und gestartet; `build_catalog.py` einmalig gelaufen (Log: `/root/catalog.log`).
