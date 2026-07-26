# STATUS-NACHT.md — Nachtauftrag (Nacht 27.07.2026)

Diese Datei ist der Auftrag für die **Mac-Claude-Code-Session**, die über Nacht autonom läuft.
Der Nutzer schläft und liest morgen früh nur den Abschlussbericht. Die Nacht ist lang — geh in
die Tiefe, arbeite gründlich, hetze nicht. **Am Ende muss `BERICHT-NACHT.md` im Repo liegen.**

---

## 0. Rahmen & Regeln (verbindlich)

- **Autonom auf `main`.** Keine Zweige. Committe in **kleinen, einzeln geprüften Schritten** mit
  klaren deutschen Commit-Messages. **Kein Versions-Tag, kein Release** (den Updater nur *bauen*,
  nicht ausliefern).
- **Keine `Co-Authored-By: Claude`-Zeile** in Commits.
- **Deutsch** für Kommentare, Docstrings, UI-Strings (`T.de`/`T.ar`), Berichte. **Keine Emojis**
  in UI oder generierten Dokumenten.
- **Nach jeder UI-Änderung**: JS-Syntax prüfen (größten `<script>`-Block aus
  `app/ui/index.html` extrahieren → `node --check`). **Nach jeder Engine-Änderung**: die
  Engine-Tests laufen lassen (siehe CLAUDE.md „Commands").
- **Nicht-Verhandelbare aus CLAUDE.md sind heilig** (Abschnitt „Non-negotiables"): Seitenzahlen
  müssen exakt der Druckseite entsprechen; DOCX-Kaskade (Word→Cloud→LibreOffice) nicht kollabieren;
  `reliability` (`sicher`/`exakt`/`ungefähr`) durchgängig halten; vollständig offline/kostenlos/
  kein Telemetrie; **identisches Verhalten Windows/macOS**. Nichts davon „vereinfachen".
- **Niemals die Nutzer-Bibliothek anfassen** (`~/Library/Application Support/AICP Research` bzw.
  `%APPDATA%\AICP Research`) — Originale + DB liegen dort und müssen überleben.
- **UI-Maßstab ist die deutsche Ansicht** (Merksatz des Nutzers): Arabisch gleich groß wie
  Deutsch, nur ggf. kräftiger; nichts aufblähen. Wenn du am UI etwas prüfst: **App starten und
  hinschauen** (Screenshots), nicht aus der Quelle raten.
- **Grenze autonom vs. berichten:** Erledige **selbstständig alles, was banal/Best-Practice/
  No-Brainer ist und die App klar verbessert** (tote Dateien weg, veraltete Doku richtigstellen,
  offensichtliche Bugs fixen, Fehlerbehandlung härten, toten Code entfernen, Tippfehler, fehlende
  Tests ergänzen). **Alles, was Produktverhalten ändert, riskant ist, eine Design-/Abwägungs-
  entscheidung braucht oder eine der Nicht-Verhandelbaren berührt → NICHT machen, sondern im
  Bericht als Empfehlung mit Trade-offs listen.**

Letzter Stand (nicht rückgängig machen): Leser-Virtualisierung, Schrift-/Ladehinweis-Arbeit,
UI wieder auf Deutsch-Größe (nur kräftiger). Letzte Commits: `4e5bab1`, `6aa4b79`, `d21e5f7`.

---

## Aufgabe 1 — Windows-Update still im Hintergrund (bauen, nicht ausliefern)

**Ziel:** Das automatische Windows-Update soll laufen **wie auf dem Mac** — ohne Installer-Fenster,
**ohne UAC-Nachfrage**, nur ein kleiner Fortschrittsbalken, danach startet die App automatisch neu.
Der Nutzer testet das morgen in Ruhe auf Windows; heute Nacht wird es **sauber gebaut und
dokumentiert**.

**Vereinbarter Ansatz — Pro-Benutzer-Installation (beseitigt die UAC-Nachfrage):**
- `build/installer.iss`: von Admin-/`Program Files`-Installation auf **Pro-Benutzer** umstellen —
  `PrivilegesRequired=lowest`, `DefaultDirName={autopf}` → nach `{localappdata}\AICP Research` (bzw.
  `{userpf}`), `CloseApplications=yes`, `RestartApplications=yes`, stabile `AppId` beibehalten.
  Ohne Admin-Rechte ⇒ **kein UAC-Dialog**, und `/SILENT` läuft wirklich unsichtbar.
- `engine/echo_engine/updater.py` (`launch_installer`): Installer weiterhin still starten
  (`/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /NORESTART`), Fortschritt/Balken beibehalten,
  automatischer Neustart. `_pick_asset`-Namen **nicht** ändern (Selbst-Update bricht sonst still).
- Prüfe, dass die **Fortschrittsanzeige** im UI sichtbar bleibt (analog Mac): Download → „wird
  installiert" → Neustart.

**Wichtige Caveats — im Bericht klar festhalten (der Nutzer entscheidet die Auslieferung):**
- **Wirkt nur vorwärts:** Erst das *nächste* Release nach dieser Änderung nutzt den neuen,
  UAC-freien Weg. Die aktuell installierte Version macht noch **ein** letztes Update mit UAC.
- **Einmaliger Umzug** von `Program Files` → Pro-Benutzer-Ordner. Dokumentiere den sauberen
  Umstiegsweg (z. B. einmalige manuelle Neuinstallation der Pro-Benutzer-Variante), damit nicht
  zwei Installationen nebeneinander liegen.
- **Auf dem Mac nicht voll testbar** (Inno Setup/WebView2 sind Windows). Implementiere die
  Code-/Konfig-Änderungen sorgfältig, prüfe sie durch Lesen/Logik, und lege einen **konkreten
  Windows-Testplan** in den Bericht (Schritt für Schritt, was der Nutzer morgen klickt/erwartet).
- **Kein Tag/Release.** Nur Code + Doku. Wenn du `installer.iss`-Assetnamen o. Ä. berührst,
  im selben Commit `_pick_asset` konsistent halten.

Wenn ein Detail des Ansatzes fachlich fragwürdig ist, **wähle die robusteste, offline-taugliche
Variante** und begründe sie im Bericht — nicht auf Rückfrage warten.

---

## Aufgabe 2 — Stresstest, Audit & Aufräumen (der Kern der Nacht)

Geh **bis ins kleinste Detail** durch alles, was die App kann. Ziel: Fehler finden, Qualität
bewerten, aufräumen. Nutze die Zeit — lieber eine Sache doppelt prüfen als oberflächlich.

### 2a. Funktions-Stresstest (was die App kann)
Decke die **gesamte Feature-Fläche** ab und notiere je Punkt „funktioniert / Fehler / Randfall":
- **Suche lokal**: strikt-UND, OR-Gruppen (`|`/`oder`/`or`/`أو`), Ausschluss (`-`), Phrase
  (`"..."`), Wortwurzel/Flexion, artikellos↔Artikel (جهات↔الجهات, ست↔الست), `لا` nur als ganzes
  Wort, **nur-Ausschluss-Suchen** (keine positiven Begriffe), Highlight-Spans, Snippet mit **allen**
  Begriffen, Dedup, Paginierung (`limit+1`).
- **Suche online (Shamela)**: funktional **identisch** zu lokal (soweit ohne Live-Server prüfbar).
  Kein Live-Server im Sandbox — `server/test_meta.py` laufen lassen, die Datenlogik/Seiten-Sortierung
  (`parse_page`/`page_sort_key`/`book_id`) prüfen, `api.py`/Merge-Logik per Code-Review bewerten.
- **Leser**: Virtualisierung (DOM-Knoten bleiben beschränkt, unabhängig von Buchgröße), weite
  Sprünge landen exakt, Prefetch/Prune, Pfeiltasten, Seiten-Sprungfeld, Fortschritt, Vokalzeichen
  an/aus (Position bleibt, kein hängendes „…"), Schrift-/Fett-Panel (persistiert), Zitat mit Quelle,
  Lesezeichen (lokal; Shamela-Lesezeichen bewusst noch nicht da), Treffer-Fokus/Active-State.
- **Bibliothek**: Upload/Indexierung (PDF page-genau, DOCX-Kaskade, TXT-Kunstseiten, Scan→OCR),
  Duplikat-Filter (PDF schlägt DOCX), Kategorien/Autoren (n:m, `" ؛ "`-Trennung), `.echolib`
  Export/Import (FTS muss neu berechnet werden!), Meta-Settings, Neu-Einlesen (Passage-IDs ändern →
  Lesezeichen-Fallback), `LAYOUT_VERSION`/`STEM_VERSION`-Migrationen.
- **App-Rahmen**: Single-Instance-Lock (Win/Mac), `data_dir()`-Migration alt→neu, Selbst-Update-
  Check, Statusanzeige/Jobs (`MAX_WORKERS=2`, WAL, busy_timeout).
- **Sprache/RTL**: DE↔AR, jeder Tastendruck mit `preventDefault`, Fokus-/Escape-Verhalten.

**Alle Engine-Tests laufen lassen** (test_engine, test_boolean_search, test_highlight,
test_categories, test_authors, test_textlayout, test_bookmarks) **+ server/test_meta.py**. Ergebnis
in den Bericht. Wo Tests fehlen für eine reale Bruchstelle, die du findest: **Test ergänzen**.
Besonderes Augenmerk auf die **Nicht-Verhandelbaren** (Seitenzahl-Genauigkeit, reliability-Fluss).

### 2b. Code-/Struktur-Audit
- **Was ist gut/schlecht aufgebaut?** Engine-Layer-Trennung, `main.py`-Routen, das eine große
  `index.html` (Länge, Wiederholungen, tote Zweige), Fehlerbehandlung in langen async-Flows.
- **Toter Code / ungenutzte Dateien / doppelte Dinge** im Repo (nicht in der Nutzer-Bibliothek!):
  verwaiste Skripte, Alt-Reste der Umbenennung EchoArchive→AICP Research, Build-Artefakte,
  auskommentierte Blöcke, ungenutzte Assets/Funktionen.
- **Veraltete Doku**: **CLAUDE.md ist teilweise veraltet** (ausdrücklich vom Nutzer genannt) —
  ebenso README/START_HIER/WINDOWS-ANLEITUNG prüfen. Bring die Doku auf den echten Stand
  (Umbenennung, Font-Bundling, Leser-Virtualisierung, Ladehinweise, UI-Maßstab-Regel, aktuelle
  Architektur). **Doku-Korrekturen sind No-Brainer → einfach machen.**

### 2c. Autonom erledigen vs. berichten
- **Einfach machen** (kein OK nötig): tote Dateien/Code entfernen, Doku richtigstellen, klare Bugs
  fixen, Fehlerbehandlung/Robustheit verbessern, Tests ergänzen, `.gitignore` pflegen, Tippfehler.
  Jede Änderung einzeln testen + committen.
- **Nur berichten** (OK nötig): Produktverhalten/UX-Änderungen, Refactorings mit Risiko, neue
  Abhängigkeiten, alles an den Nicht-Verhandelbaren, alles am Löschen von potenziellen Nutzerdaten,
  die tatsächliche Updater-Auslieferung/der Program-Files→Pro-Benutzer-Umzug.

---

## Bericht — `BERICHT-NACHT.md` (Pflicht, Deutsch, am Ende committen)

Struktur genau so, damit der Nutzer es morgen schnell durchliest:
1. **Kurzfazit** (5–10 Zeilen): Zustand der App, größte Funde, was du erledigt hast.
2. **Was gut funktioniert.**
3. **Was nicht gut funktioniert** (Bugs/Randfälle, je mit Repro + Schweregrad + wo).
4. **Was gut aufgebaut ist.**
5. **Was nicht gut aufgebaut ist** (mit konkretem Verbesserungsvorschlag).
6. **Aufgeräumt / entfernt** (Liste der gelöschten/bereinigten Dinge + warum harmlos).
7. **Unnütz herumliegend** (was noch weg könnte, aber Rückfrage braucht).
8. **Autonom erledigt** — nummerierte Liste mit Commit-Hashes, je 1 Zeile.
9. **Braucht deine Entscheidung** — offene Punkte mit Trade-offs (inkl. Updater-Auslieferung +
   Program-Files→Pro-Benutzer-Umzug + Windows-Testplan).
10. **Windows-Updater**: was gebaut wurde, wie getestet werden soll (Schritt für Schritt).
11. **Testlauf-Ergebnisse**: alle Engine-Tests + test_meta.py (grün/rot).

Halte den Bericht **ehrlich**: fehlgeschlagene Tests mit Output nennen, Ausgelassenes benennen.

---

## Nicht anfassen / Grenzen
- Nutzer-Bibliothek und DB. Die 5 Nicht-Verhandelbaren. Assetnamen des Selbst-Updates (außer im
  selben Commit konsistent). Kein Tag/Release. Keine Co-Authored-By-Zeile. Keine neuen schweren
  Abhängigkeiten ohne Bericht (Installer ist schon ~514 MB, alles muss offline bleiben).
- Shamela-**Live**-Server ist nicht testbar (keine Daten/kein Netz) — nur Code-Review + test_meta.py.

Viel Erfolg. Geh in die Tiefe — der Nutzer erwartet morgen früh einen Bericht, der ihm wirklich
zeigt, wo die App steht und was du schon besser gemacht hast.
