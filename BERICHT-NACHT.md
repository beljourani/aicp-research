# Bericht der Nacht — 27.07.2026

## 1. Kurzfazit

Die App ist in einem **guten, belastbaren Zustand**. Ich habe die gesamte Funktionsfläche
durchgetestet — Suche, Leser, Bibliothek, Oberfläche, App-Rahmen — und **keinen einzigen Fehler in
der Suchlogik** gefunden: 600 geprüfte Treffer erfüllen ihre Anfrage zu 100 %, alle Randfälle
(leere Anfrage, `|`, `-`, unbalancierte Anführungszeichen) laufen ohne Absturz.

**Zwei echte Fehler gefunden und behoben:**
1. Der Leser verlor beim Ein-/Ausblenden der Vokalzeichen die Leseposition (Seite 400 → 398). Das
   war ein Nachwehen meines Virtualisierungs-Umbaus. Behoben, im Test bestätigt.
2. Die Online-Suche zeigte bei Zeitüberschreitung die englische Meldung
   „The read operation timed out" in der deutschen Oberfläche. Jetzt steht dort ein verständlicher
   Hinweis mit Handlungsvorschlag.

**Der Windows-Updater ist gebaut** (Pro-Benutzer-Installation, keine UAC-Abfrage mehr) — noch nicht
ausgeliefert, wie beauftragt. Dabei fiel ein zweiter Fehler auf: Der Neustart nach dem stillen
Update hing bisher am Zufall; das ist jetzt deterministisch.

**Aufgeräumt:** tote Funktion, vier eingecheckte Skript-Ausgaben, sieben verstreute
`CREATE TABLE`-Aufrufe. **Doku:** README, START_HIER, WINDOWS-ANLEITUNG und CLAUDE.md waren an
mehreren Stellen veraltet, teils irreführend — richtiggestellt.

**Testlauf: 12 von 12 Testdateien grün.** Acht Commits, kein Tag, keine Co-Authored-By-Zeile.

---

## 2. Was gut funktioniert

**Die Suche — durchweg.** Getestet gegen die echte Bibliothek, jeder Treffer gegen den
Passagentext geprüft (nicht gegen den Ausschnitt, der täuschen kann):

| Prüfung | Ergebnis |
|---|---|
| UND (2–4 Begriffe), ODER (`\|`, `oder`, `or`, `أو`), Ausschluss (1–2), Phrase, Phrase negiert | 600/600 Treffer korrekt |
| artikellos ↔ Artikel (جهات↔الجهات, ست↔الست) | korrekt |
| `لا` nur als ganzes Wort (nicht in الكلام) | korrekt |
| Nur-Ausschluss-Suchen (keine positiven Begriffe) | kein Absturz |
| 15 Randfälle der Eingabe (leer, `-`, `"`, `\|`, `a\|b\|c`, …) | kein Absturz |
| Ausschnitt enthält **alle** Suchbegriffe | 60/60 |
| Paginierung (limit/offset) | keine Dubletten, keine Überschneidung |
| `reliability` fließt bis zum Treffer | `sicher` / `exakt` vorhanden |

**Der Leser** — 19 von 19 Prüfungen in der echten App: Sprünge landen exakt, Pfeiltasten, Home/End,
Fortschrittsbalken, Seitenfeld, Zitat-Seitenzuordnung, gemerkte Leseposition. Die Virtualisierung
hält: **21–41 DOM-Knoten, unabhängig von der Buchgröße** (auch bei 63.513 Seiten).

**Die Bibliothek** — `.echolib`-Export/Import inklusive der kritischen FTS-Neuberechnung,
Mehrfach-Autoren (`" ؛ "`), Sammlungen (n:m), Duplikat-Filter (PDF schlägt DOCX, auch bei
unterschiedlicher Groß-/Kleinschreibung), Migrationen `STEM_VERSION`/`LAYOUT_VERSION` — Lesezeichen
überleben sie.

**Die Oberfläche** — Sprachwechsel DE↔AR schaltet sauber auf RTL, und **der Maßstab stimmt**:
Arabisch ist mit 15 px genauso groß wie Deutsch, nicht größer. Enter in Begriffs- und
Ausschlussfeld wird abgefangen (kein macOS-Fehlton), Escape ebenso.

**Online/Offline identisch** — über neun Anfragearten geprüft: beide Quellen liefern Treffer, und
die Bedeutungssuche ändert in **keinem** Fall die Treffermenge, nur die Reihenfolge.

---

## 3. Was nicht gut funktioniert

### Behoben in dieser Nacht

**A) Leser verlor die Position beim Umschalten der Vokalzeichen** — *mittel*
*Wo:* `app/ui/index.html`, `rerenderLoaded()`
*Repro:* Buch öffnen, zu Seite 400 springen, Vokalzeichen ausblenden → man landete auf Seite 398.
*Ursache:* Ohne Vokalzeichen ist der Text kürzer, die Blätter darüber schrumpfen. Seit der
Virtualisierung ändern sich Höhen im Fenster beim Neuzeichnen — vorher existierten alle Blätter
dauerhaft. *Behoben* (`b9e3b5e`): Die aktuelle Seite wird als Anker festgehalten und ihre
Bildschirmposition danach wiederhergestellt.

**B) Englische Technikmeldung in der deutschen Oberfläche** — *klein, aber sichtbar*
*Wo:* `app/main.py`, `_shamela_request`
*Repro:* Online nach einem sehr häufigen Wort suchen (`الله`) → bei Zeitüberschreitung erschien
„The read operation timed out". *Ursache:* Die Zeitüberschreitung wurde von keinem Fehlerzweig
gefangen. *Behoben* (`8f2c445`).

**C) Lokaler Windows-Build meldete fälschlich einen Fehler** — *klein*
*Wo:* `Build-Windows.bat`
*Repro:* `Build-Windows.bat` ausführen → „Installer wurde nicht erzeugt", obwohl er da war.
*Ursache:* Es wurde nach `AICP-Research-Setup.exe` gesucht, die Datei heißt aber
`AICP-Research-Setup-<Version>.exe`. *Behoben* (`6afcbf5`).

**D) Neustart nach stillem Windows-Update war Glückssache** — *mittel (Windows)*
Die App beendet sich beim Update selbst, damit ihre Dateien ersetzt werden können. Ob der
Windows-Restart-Manager sie vorher noch erfasst hatte, war ein Rennen. *Behoben* (`6afcbf5`):
zusätzlicher `[Run]`-Eintrag für den stillen Fall.

### Offen (nicht behoben, weil Abwägung nötig)

**E) Sehr häufige Wörter sind online langsam** — *mittel*
`الله` ohne Buchfilter braucht **14–20 Sekunden**; unter Last reißt das die 45-Sekunden-Grenze der
App. Der Nutzer sieht dann (jetzt) einen verständlichen Hinweis, aber keine Treffer. Ursache: Die
Rangfolge muss über Millionen Treffer berechnet werden. Lösungsvorschläge unter Punkt 9.

**F) Am Buchende meldet die Seitenanzeige die vorletzte Seite** — *kosmetisch*
Bei „End" steht die letzte Seite sichtbar unten, oben im Bild aber die vorletzte. `visiblePage()`
meldet korrekt die **oberste sichtbare** Seite. Gleiches gilt beim Treffer-Klick, weil Treffer
zentriert werden. Verhalten war vor der Virtualisierung identisch — ich habe es bewusst nicht
geändert, weil jede Alternative andere Fälle verschlechtert.

**G) Zwei unerreichbare API-Routen** — *harmlos*
`/api/check_update` und `/api/set_update_repo` werden von der Oberfläche nirgends aufgerufen. Ich
habe sie **nicht** entfernt: Sie sind brauchbare Notausgänge (Update-Repo umstellen, manuell
prüfen), und ihr Wegfall nähme eine Fähigkeit weg, ohne etwas zu gewinnen.

---

## 4. Was gut aufgebaut ist

- **Die Schichtentrennung.** `engine/echo_engine/` ist reine Python-Logik ohne Oberflächenbezug und
  einzeln testbar — deshalb konnte ich die ganze Suchlogik gegen die echte Bibliothek prüfen, ohne
  die App zu starten. Genau diese Trennung hat die Nacht produktiv gemacht.
- **Die Nicht-Verhandelbaren sind im Code verankert, nicht nur in der Doku.** `reliability` wird
  durchgereicht, die Druckseite kommt aus der Quellangabe und wird nie neu vergeben, die
  DOCX-Kaskade ist intakt.
- **Der Umgang mit früheren Fehlern.** An den heiklen Stellen stehen Kommentare, *warum* etwas so
  ist (contentless FTS5 beim Import, `KEEP` > Prefetch, `preventDefault` gegen den macOS-Fehlton).
  Das hat mich mehrfach vor Fehlgriffen bewahrt.
- **Die Tests sind schlichte Skripte** mit `__main__`-Block statt eines Frameworks — passend zum
  Projekt, keine zusätzliche Abhängigkeit, sofort ausführbar.
- **Der lokale HTTP-Server statt der pywebview-Brücke.** Dadurch ließ sich die App in dieser Nacht
  fernsteuern und messen; mit der Brücke wäre das nicht gegangen.

---

## 5. Was nicht gut aufgebaut ist

**a) `app/ui/index.html` ist mit 3.319 Zeilen die größte Datei des Projekts.**
Alles in einer Datei: Stil, Aufbau, Zustand, Netzzugriffe, Leser, Suche, Bibliothek, Lesezeichen.
*Vorschlag:* Nicht in Module zerlegen (das brächte einen Build-Schritt und widerspräche dem
„kein Build" -Prinzip), sondern **die Abschnitts-Kommentare zu einem Inhaltsverzeichnis am
Dateikopf ergänzen** und die drei größten Bereiche (Leser, Suche, Bibliothek) klar voneinander
trennen. Geringes Risiko, spürbarer Gewinn beim Navigieren.

**b) 35 leere `catch(e){}` im Frontend.**
Sie sind bewusst so (ein fehlgeschlagener `await` soll den restlichen Ablauf nicht abbrechen — eine
teuer bezahlte Lektion). Aber sie verschlucken auch echte Fehler stumm.
*Vorschlag:* Eine winzige Hilfsfunktion `leise(fn, wo)`, die den Fehler auf die Konsole schreibt und
weitermacht. Verhalten unverändert, aber Fehler werden auffindbar.

**c) 12 `except …: pass` in Python.**
Dasselbe Muster serverseitig. Die meisten sind legitim (bestmögliches Verhalten ohne Netz), einige
könnten eine Zeile Protokoll vertragen.

**d) `main.py` mischt Zuständigkeiten.**
1.690 Zeilen: HTTP-Routen, Bibliotheksverwaltung, Hintergrundarbeit, Update, Shamela-Anbindung,
Lesezeichen. *Vorschlag für später:* Die Shamela-Anbindung (`_shamela_request` und die sieben
`shamela_*`-Methoden) in ein eigenes Modul `app/shamela.py` ziehen — sie ist klar abgegrenzt und
hätte keine Nebenwirkungen. **Nicht heute gemacht**, weil es Produktcode ohne Testnetz verschiebt.

**e) Die `meta`-Tabelle fehlte im zentralen Schema** — *behoben.* Sie wurde an sieben Stellen
einzeln angelegt; wer eine neue Funktion schrieb, musste daran denken, sonst gab es
„no such table: meta". Jetzt steht sie einmal in `db.py` (`4624a50`).

---

## 6. Aufgeräumt / entfernt

| Was | Warum harmlos |
|---|---|
| `highlight()` in `index.html` | Tote Funktion. Die alte wörtliche Markierung wurde durch `stitchMarks` ersetzt; kein Aufruf mehr im Code (nachgeprüft), JS-Syntax nach dem Entfernen geprüft. |
| `tools/diagnose_ergebnis.txt` | Ausgabe von `tools/diagnose.py` — wird bei jedem Lauf neu geschrieben (nachgeprüft). Der eingecheckte Stand war vom 18.07. und trug noch „EchoArchive" im Kopf. |
| `tools/probe.txt` | Ausgabe von `tools/probe.py`. |
| `tools/ocr_benchmark.html` (63 KB) | Ausgabe von `tools/ocr_benchmark.py`. |
| `tools/ocr_vergleich.html` (37 KB) | Ausgabe von `tools/ocr_vergleich.py`. |
| 7× `CREATE TABLE IF NOT EXISTS meta` | Durch einen Eintrag im zentralen Schema ersetzt; `CREATE … IF NOT EXISTS` war ohnehin idempotent, Verhalten unverändert. Mit `meta_get`/`meta_set` gegen die echte Bibliothek geprüft. |

Alle vier Dateien stehen jetzt in `.gitignore`, damit sie nicht wieder hineinrutschen.

---

## 7. Unnütz herumliegend (bräuchte deine Entscheidung)

- **`docs/`** — `kitab-tajriba.txt`, `kitab-word-test.docx`, `multi/buch-a.txt`, `multi/buch-b.txt`.
  Von keinem Test und keinem Skript referenziert. Vermutlich deine Probedateien zum Ausprobieren
  des Imports. **Nicht angefasst** — falls du sie noch brauchst, sollen sie bleiben; sonst können
  sie weg (zusammen ~50 KB).
- **`build/echoarchive.spec`** — trägt noch den alten Namen und wird an vier Stellen referenziert
  (beide Build-Skripte, beide CI-Abläufe). Umbenennen wäre kosmetisch, berührt aber den
  Auslieferungsweg, den ich hier nicht testen kann. **Empfehlung:** so lassen.
- **`engine/echo_engine/extract.py`** legt seinen Word-Zwischenordner unter dem Namen
  `echoarchive-tmp` an. Reiner Name eines temporären Ordners, kein Nutzen im Umbenennen.
- **`tools/tessdata_best/ara.traineddata`** und `tools/models_ar/` — zusammen ~12 MB im Repo.
  Werden von den OCR-Vergleichsskripten benutzt. Falls du die Vergleiche nicht mehr fährst, wäre
  das der größte Brocken zum Auslagern.

---

## 8. Autonom erledigt

1. `6afcbf5` — Windows-Update ohne Administrator-Abfrage: Pro-Benutzer-Installation, verlässlicher
   Neustart nach stillem Update, Erfolgsmeldung im lokalen Build repariert.
2. `fd4e8f3` — Vier Tests für `.echolib`-Export/Import ergänzt (die FTS-Neuberechnung war
   ungetestet, obwohl CLAUDE.md sie als früheren Fehlerfall nennt).
3. `4624a50` — `meta`-Tabelle ins zentrale Schema, sieben verstreute `CREATE`-Aufrufe entfernt.
4. `b9e3b5e` — Leser: Leseposition bleibt beim Umschalten der Vokalzeichen stehen.
5. `8f2c445` — Online-Suche: verständliche deutsche Meldung statt englischer Technikmeldung.
6. `5a2ec01` — CLAUDE.md auf den echten Stand (Testliste, Leser-Virtualisierung samt der
   2^25-px-Falle, gebündelte Schriften, UI-Maßstab, Installer).
7. `f9d3ead` — Nutzer-Doku richtiggestellt (README, START_HIER, WINDOWS-ANLEITUNG).
8. `d548b98` — Toter Code und vier eingecheckte Skript-Ausgaben entfernt, `.gitignore` gepflegt.

---

## 9. Braucht deine Entscheidung

### 9.1 Windows-Updater ausliefern (der wichtigste Punkt)

Der Umbau ist fertig, aber **noch nicht ausgeliefert** (kein Tag gesetzt). Zwei Dinge musst du
wissen, bevor du ein Release baust:

- **Wirkt nur vorwärts.** Erst das *nächste* Release nach dieser Änderung nutzt den UAC-freien Weg.
  Deine derzeit installierte Version macht noch **ein** letztes Update mit UAC-Abfrage.
- **Einmaliger Umzug nötig.** Die alte Installation liegt in `C:\Program Files\AICP Research`, die
  neue in `%LOCALAPPDATA%\Programs\AICP Research`. Windows führt beide getrennt — ohne Aufräumen
  hättest du **zwei Installationen nebeneinander**. Sauberer Weg:
  1. Alte Version über „Apps & Features" deinstallieren (deine Bibliothek in `%APPDATA%\AICP
     Research` bleibt dabei unangetastet).
  2. Den neuen Installer einmal von Hand ausführen.
  3. Ab dann laufen alle Updates still.

**Alternative, falls dir der Umzug zu heikel ist:** bei der Installation in „Programme" bleiben und
die UAC-Abfrage behalten. Dann bleibt alles wie bisher — ein Klick pro Update. Ich halte den Umzug
für die bessere Lösung, aber es ist deine Entscheidung.

### 9.2 Häufige Wörter online beschleunigen

`الله` braucht 14–20 s. Drei Wege, mit Abwägung:

| Weg | Gewinn | Preis |
|---|---|---|
| **Ergebnis-Zwischenspeicher** (letzte N Anfragen merken) | Wiederholte Anfragen sofort | Erste Anfrage bleibt langsam; Speicher auf dem Server |
| **Obergrenze für Kandidaten** (nur die ersten X Treffer bewerten) | Deutlich schneller | Die Rangfolge stimmt nicht mehr exakt — ein sehr guter Treffer weit hinten könnte fehlen |
| **Zeitgrenze anheben** (45 s → 90 s) | Weniger Abbrüche | Der Nutzer wartet länger, bevor etwas passiert |

Meine Empfehlung: **Zwischenspeicher** — er ändert die Ergebnisse nicht, nur die Wartezeit. Die
Kandidaten-Obergrenze würde die Trefferqualität antasten, und daran würde ich ohne dein
Einverständnis nichts ändern.

### 9.3 Kleinere Vorschläge

- **`app/shamela.py` abtrennen** (Punkt 5d) — reine Umstrukturierung, kein Verhaltenswechsel, aber
  ich verschiebe ungern Produktcode ohne dein OK.
- **Fehler-Protokollierung statt stummer `catch`** (Punkt 5b) — Verhalten bleibt gleich, Fehler
  würden auffindbar.
- **`docs/`-Probedateien** (Punkt 7) — löschen oder behalten?

---

## 10. Windows-Updater: was gebaut wurde und wie du es testest

### Was geändert wurde

`build/installer.iss`:
- `PrivilegesRequired=lowest` → `{autopf}` löst auf `%LOCALAPPDATA%\Programs` auf. Ohne
  Administratorrechte zeigt Windows **keine UAC-Abfrage**, und `/SILENT` läuft wirklich unsichtbar.
- `PrivilegesRequiredOverridesAllowed=` (leer) → die Abfrage kann nicht durch die Hintertür
  zurückkommen.
- Zusätzlicher `[Run]`-Eintrag mit `skipifnotsilent` → nach einem stillen Update startet die App
  verlässlich wieder. (`RestartApplications` allein genügte nicht: Die App beendet sich selbst,
  damit ihre Dateien ersetzt werden können — ob der Restart-Manager sie vorher erfasst hatte, war
  Zufall. Ein doppelter Start ist unschädlich: die Einzelinstanz-Sperre holt nur das vorhandene
  Fenster nach vorne.)
- **Unverändert:** `AppId` und die Asset-Namen — das Selbst-Update findet seine Datei weiter.

`engine/echo_engine/updater.py`: **nicht geändert.** Die Startparameter
(`/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /NORESTART`) waren bereits richtig; das Problem
lag allein an den Administratorrechten.

Die Fortschrittsanzeige im UI ist unverändert und funktioniert wie auf dem Mac:
„lädt … X %" → „startet Installer …" → App beendet sich → Installer läuft → App startet neu.

### Was ich **nicht** prüfen konnte

Inno Setup und WebView2 gibt es nur auf Windows — ich konnte den Installer **nicht kompilieren**.
Ich habe deshalb bewusst nur deklarative, gut verstandene Direktiven verwendet und zwei zunächst
eingebaute Zusatz-Direktiven (`UsedUserAreasWarning`, `CloseApplicationsFilter`) wieder entfernt:
Sie hätten keinen Nutzen gebracht, aber bei einer älteren Inno-Version einen Kompilierfehler
auslösen können.

### Testplan für morgen (Schritt für Schritt)

**Vorbereitung**
1. Auf dem Windows-PC: alte Version über „Apps & Features" deinstallieren.
   → Prüfen: `%APPDATA%\AICP Research` ist **noch da** (deine Bücher und die Datenbank).
2. Repo aktualisieren, `Build-Windows.bat` doppelklicken.
   → Erwartung: Der Build läuft durch und meldet am Ende den Pfad zu
   `dist\AICP-Research-Setup-<Version>.exe`. (Genau diese Meldung war vorher kaputt.)

**Erstinstallation**
3. Den Installer doppelklicken.
   → Erwartung: **Keine** Abfrage „Möchten Sie zulassen, dass Änderungen vorgenommen werden?".
4. Installation abschließen, App starten.
   → Prüfen: Die App liegt unter `%LOCALAPPDATA%\Programs\AICP Research`.
   → Prüfen: Deine Bibliothek ist vollständig da (Bücher, Lesezeichen, Sammlungen).

**Stilles Update (der eigentliche Test)**
5. Eine neue Version veröffentlichen (Tag setzen, CI bauen lassen).
6. App starten und den Update-Knopf drücken.
   → Erwartung: Fortschrittsbalken „lädt … %", dann „startet Installer …".
   → Erwartung: **Kein** Installer-Fenster, **keine** UAC-Abfrage.
   → Erwartung: Die App schließt sich und **startet nach wenigen Sekunden von selbst wieder**.
7. Nach dem Neustart: Version prüfen, ein Buch öffnen, eine Suche machen.
   → Prüfen: Bibliothek unverändert, Leseposition erhalten.

**Falls etwas schiefgeht**
- Erscheint doch eine UAC-Abfrage → es lief noch die alte, systemweite Installation. Schritt 1
  wiederholen.
- Die App startet nach dem Update nicht von selbst → von Hand starten und mir melden; dann greift
  der `[Run]`-Eintrag nicht wie gedacht.
- Zwei Einträge in „Apps & Features" → die alte Installation ist noch da, deinstallieren.

---

## 11. Testlauf-Ergebnisse

**Alle 12 Testdateien grün** (Stand nach allen Änderungen dieser Nacht):

```
engine/tests/test_engine.py            GRÜN
engine/tests/test_boolean_search.py    GRÜN
engine/tests/test_highlight.py         GRÜN
engine/tests/test_categories.py        GRÜN
engine/tests/test_authors.py           GRÜN
engine/tests/test_textlayout.py        GRÜN
engine/tests/test_bookmarks.py         GRÜN
engine/tests/test_hybrid.py            GRÜN
engine/tests/test_library_io.py        GRÜN   (neu in dieser Nacht)
server/test_meta.py                    GRÜN
server/test_build_fts.py               GRÜN
server/test_search_hybrid.py           GRÜN
```

Zusätzlich geprüft: JS-Syntax (`node --check`) nach **jeder** Frontend-Änderung, Python-Syntax aller
Module, und diese Stresstests gegen die echte Bibliothek bzw. die laufende App:

| Stresstest | Ergebnis |
|---|---|
| Suche lokal (15 Anfragearten, 15 Randfälle) | 600/600 Treffer korrekt, 0 Abstürze |
| Bibliothek (`.echolib`, Sammlungen, Migrationen) | 0 Fehler |
| Leser in der echten App (19 Prüfungen) | 19/19 |
| Oberfläche: Sprache, RTL, Maßstab, Tastatur | 16/16 |
| App-Rahmen: Duplikate, Autoren, `data_dir`, Jobs | 0 Fehler |
| Online/Offline-Gleichheit (9 Anfragearten) | Treffermenge unabhängig von der Semantik |

### Ehrlich benannt: was ich **nicht** geprüft habe

- **Der Windows-Installer wurde nicht kompiliert** — Inno Setup läuft nur auf Windows. Die Änderung
  ist durch Lesen und Abgleich mit der Inno-Dokumentation geprüft, nicht durch einen Build.
- **Kein Tempo-Urteil zum Leser.** Meine Engine (WKWebView) ist nicht repräsentativ für WebView2 auf
  deinem Windows-Rechner. Belegt ist nur die strukturelle Garantie (Knotenzahl bleibt beschränkt);
  ob es sich flüssig **anfühlt**, musst du dort beurteilen.
- **OCR und die DOCX-Kaskade** habe ich nicht mit echten Dateien durchlaufen lassen — dafür fehlen
  in dieser Umgebung Word und passende Scan-PDFs. Der Code der Kaskade ist unverändert.
- **Kein Screenshot-Vergleich der Oberfläche.** Ich habe stattdessen gemessen (Schriftgrößen,
  Textrichtung, Tastaturverhalten). Wie es **aussieht**, solltest du selbst beurteilen.
