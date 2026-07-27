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
  **Entschieden: gelöscht.** Nachgeprüft ergab sich, dass sie aus dem allerersten Commit (`42ce43c`)
  stammen, seitdem nie angefasst wurden und von nichts referenziert werden; die Engine-Tests legen
  ihre Prüfdaten selbst an (`connect(":memory:")`, `tempfile.TemporaryDirectory()`). Über die
  Git-Historie bleiben sie wiederherstellbar. Für eine Prüfung der Word-Kaskade ist ohnehin ein
  echtes Buch mit bekannten Seitenzahlen aussagekräftiger als eine Kunstdatei.
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

**Entschieden (27.07.):** Der Umzug bleibt **manuell**. Ein automatischer Umzug wäre technisch
möglich — der Installer kann die Altinstallation über `HKLM\…\Uninstall\{AppId}_is1` finden —,
aber ihr Entfernen braucht Administratorrechte und damit **eine** UAC-Abfrage; wegzaubern lässt die
sich nicht. Für einen einzelnen Rechner und einen einmaligen Vorgang von zwei Minuten steht das in
keinem Verhältnis zum Risiko, Pascal-Code in die `.iss` zu schreiben, der hier nicht kompiliert
werden kann und im Fehlerfall den Installer-Bau **jedes** Releases bräche. Falls die App später
weitergegeben werden soll, wäre der automatische Umzug erneut zu erwägen.

### 9.2 Häufige Wörter online beschleunigen — erledigt

**Entschieden und umgesetzt: Zwischenspeicher.** Die beiden anderen Wege wurden verworfen — eine
Obergrenze für Kandidaten hätte die Trefferqualität angetastet, ein höheres Zeitlimit hätte nur
das Symptom behandelt.

**Ursache, vorher vermessen statt vermutet.** Die Zeit steckt vollständig in einer einzigen Stelle:
`الله` trifft 5.958.791 Abschnitte, und SQLite FTS5 muss für jeden davon eine bm25-Punktzahl
rechnen, um die besten 90 zu finden — einen vorzeitigen Abbruch gibt es nicht. Das sind 14,4 s
reine Rechenarbeit (warm genauso langsam wie kalt). Das anschließende Verbinden und die
Ausschnittbildung kosten 0,00 s. Ohne die Trefferreihenfolge zu verändern lässt sich das nicht
billiger machen — deshalb wird die Bewertung gemerkt statt beschnitten.

Zwei weitere Messungen bestimmten den Entwurf: Die Bewertung kostet **unabhängig vom Limit**
gleich viel (90 Zeilen 14,36 s, 1200 Zeilen 14,14 s) — einmal großzügig rechnen ist also gratis.
Und das Einbettungsmodell wurde erst beim ersten Gebrauch geladen: **19,7 s**, die bisher eine
echte Nutzeranfrage bezahlte. Zusammen mit einer langen Wortsuche waren das 34 s bei 45 s
Zeitgrenze — das war die eigentliche Ursache der Abbrüche.

**Was gebaut wurde** (`server/fts_cache.py`, eingehängt in `server/api.py`):

- Gemerkt wird nur die Kandidatenliste (Zeilennummer + Punktzahl), nicht die fertige Antwort.
  Ausschnitte, Markierung, semantische Umsortierung und das Merken der Bücher für den Leser laufen
  unverändert bei jeder Anfrage — es kann also keine Anzeige veralten.
- Es wird immer großzügig gerechnet (1200 Rangplätze) und für jeden Blätterschritt zugeschnitten.
  Damit kommt auch „Weitere Treffer laden" aus dem Speicher statt in einen neuen 14-Sekunden-Lauf.
- Gleichzeitige gleiche Anfragen rechnen nur einmal; die übrigen warten auf das Ergebnis.
- Das Einbettungsmodell wird beim Start vorgeladen.
- `/health` meldet jetzt Modell- und Speicherstand — sonst würde ein Zwischenspeicher still
  verdecken, wenn die Suche insgesamt langsamer geworden wäre.

**Zweiter Schritt: auch die erste Suche wurde beschleunigt.** Der Speicher hilft erst ab dem
zweiten Mal — die erste Suche kostete weiter 14 s, weil ein einziger Kern rechnete, während sieben
brachlagen. Der Index wird jetzt in Zeilennummern-Streifen geteilt, die gleichzeitig bewertet
werden. Die Reihenfolge bleibt erhalten, weil bm25 mit den Kennzahlen des **ganzen** Index rechnet
und nicht mit denen des Streifens — genau darauf beruht der Buchfilter schon heute. Ein Halbmesser
begrenzt die gleichzeitigen Durchläufe über alle Suchen hinweg; über `STREIFEN=1` lässt sich das
Ganze ohne Codeänderung abschalten.

**Gemessen am laufenden Dienst, so wie die App ihn ruft** (limit=40):

| Anfrage | Semantik | vorher | erstmals | nochmal | weiterblättern |
|---|---|---|---|---|---|
| `الله` | an | ~16 s | **7,5 s** | **0,55 s** | **0,99 s** |
| `العلم` | an | ~11 s | **5,3 s** | **0,65 s** | **1,5 s** |
| `الصلاة` | an | 4,1 s | **1,9 s** | **0,75 s** | **0,73 s** |
| `الرحمن` | aus | 4,6 s | **1,9 s** | **0,41 s** | **0,66 s** |
| `الميراث` | aus | 1,1 s | **0,68 s** | **0,33 s** | **0,52 s** |

Fünf gleichzeitige **gleiche** Anfragen brauchten zusammen 14,6 s statt fünfmal 14,6 s. Vier
gleichzeitige **verschiedene** teure Anfragen liefen in 12,8 s alle durch, ohne Fehler und mit
8 GB freiem Arbeitsspeicher.

**Nachgewiesen, dass sich nichts verändert hat** — das war der wichtigere Teil der Arbeit:

1. Für 12 Anfragen liefert der Speicher zeichengleich dieselben Treffer, Ausschnitte und
   `has_more`-Angaben wie die frische Rechnung, mit und ohne Semantik.
2. Seitenweise Blättern ergibt dieselbe Folge wie ein Abruf am Stück.
3. Dabei kam eine echte Falle zum Vorschein: bm25 erzeugt **massenhaft Gleichstände** (bis zu 467
   von 1200 Zeilen). Ohne festen Zweitschlüssel darf SQLite bei `LIMIT 90` anders sortieren als
   bei `LIMIT 1200` — dann wäre der Zuschnitt einer großen Liste auf eine kleine nicht mehr
   dasselbe Ergebnis. Behoben mit `ORDER BY score, rowid`; gemessen kostet das nichts (14,57 s
   statt 14,70 s) und liefert bei 12 geprüften Anfragen exakt dieselbe Liste wie bisher. Es legt
   nur eine bislang zufällige Reihenfolge innerhalb eines Gleichstands fest.
4. Für die Streifen eigens: bei 12 Anfragen liefert die gestreifte Bewertung zeichengleich
   dieselbe Liste wie die einfache, bei 6 Anfragen auch die vollständige Suchantwort, und beim
   Blättern (offset 40 und 80) ebenfalls. Null Abweichungen.
5. Elf Tests für die Speicherlogik (`server/test_fts_cache.py`, laufen ohne Server und ohne Daten)
   und acht neue Integrationstests in `server/test_search_hybrid.py`, darunter einer, der
   sicherstellt, dass nach einem neu gebauten Index nichts aus dem alten durchschlägt, und einer,
   der die lückenlose Streifeneinteilung prüft — der hat prompt einen Fehler bei kleinen Indizes
   gefunden (leere Streifen), bevor er ausgeliefert war.

**Was bewusst nicht gemacht wurde:**

- Der Buchfilter geht weiter am Speicher vorbei — dort ist die Suche mit 0,6–1,0 s bereits schnell.
- **Der Speicher überlebt keinen Neustart.** Das wäre möglich gewesen, ist aber verworfen worden:
  Der große Neustart-Schaden waren die 19,7 s Modellladen, und die sind durch das Vorladen weg.
  Übrig bliebe einmal wenige Sekunden je häufigem Wort. Dafür bräuchte es einen Schreibzugriff auf
  die Indexplatte und einen Fingerabdruck, der einen neu gebauten Index sicher erkennt — erkennt er
  ihn nicht, lieferte die Suche **fremde Textstellen** statt nur veralteter. Das Verhältnis stimmt
  nicht. Der Speicher füllt sich nach einem Neustart beim Suchen von selbst wieder.

### 9.2b Die größten Bücher ließen sich gar nicht öffnen — behoben

Auf die Frage, ob aus dem Server noch mehr herauszuholen sei, habe ich ihn systematisch
vermessen. Dabei kam ein Fehler zum Vorschein, der weit schwerer wog als alles, wonach ich
gesucht hatte.

**Der Fund.** Beim ersten Öffnen eines Buches baute der Server dessen Seitenverzeichnis, indem
er *alle* Abschnitte des Buches aus Qdrant scrollte. Gemessen:

| Buch | Abschnitte | vorher | nachher |
|---|---|---|---|
| فتاوى الشبكة الإسلامية | 135.241 | **195,2 s** | **0,83 s** |
| خزانة التراث | 124.383 | **130,8 s** | **0,84 s** |
| مجلة الرسالة | 100.221 | **78,6 s** | **0,53 s** |

Die App bricht nach 60 s ab. **Die größten Bücher der Sammlung waren damit unerreichbar** — sie
liefen jedes Mal in die Zeitüberschreitung. Betroffen waren die 240 Bücher mit über 10.000
Abschnitten (2,8 % der Sammlung), also gerade die großen Nachschlagewerke. Die Projektdoku
vermerkte „~3 s je Buch"; das galt nur für ein durchschnittliches Buch (246 Abschnitte).

**Die Lösung lag schon bereit.** Dieselbe Angabe steht in `chunk_meta` im Wortindex und kommt
dort über einen abdeckenden Index in unter einer Sekunde. Qdrant bleibt als Rückfallebene; der
Wortindex antwortet mit „weiß nicht" statt mit einer leeren Liste, denn eine leere Liste würde
als „Buch hat keine Seiten" festgeschrieben und das Buch dauerhaft unöffenbar machen.

**Nachgewiesen, dass sich nichts verändert hat:**

1. Die **54 bereits gebauten Verzeichnisse** stammen noch aus dem Qdrant-Weg. Sie passen Blatt
   für Blatt zur neuen Quelle — null Abweichungen. Ohne diese Prüfung hinge die Blattnummer
   davon ab, wann ein Buch zum ersten Mal geöffnet wurde.
2. Zusätzlich 48 Bücher aller Größenklassen (von 8 bis 135.241 Abschnitten) aus beiden Quellen
   verglichen: **null Abweichungen**.
3. Die 1.163 Zeilen, die `chunk_meta` gegenüber Qdrant fehlen, sind restlos erklärt: das
   Bauprotokoll meldet exakt `1.163 doppelte Kennungen`. Doppelte tragen per Definition dieselbe
   Seitenkennung wie eine vorhandene Zeile — eine Seite kann dadurch nicht verlorengehen. Damit
   ist das Restrisiko null, nicht bloß klein.
4. Fünf neue Tests, darunter einer, der Qdrant beim Aufbau **verbietet** (er schlägt fehl, sobald
   jemand den langsamen Weg wieder zum Normalfall macht), und einer in `test_meta.py`, der die
   Zusage festhält, auf der die Rückfallebene beruht: ein gescheiterter Aufbau darf nicht
   festgeschrieben werden.
5. Ein großes, nie geöffnetes Buch (فتح الباري, 59.109 Abschnitte) über den echten Weg
   aufgeschlagen: **9,6 s** einschließlich Schreiben der Blattnummern, danach 0,3 s.
   `rueckfall_qdrant` steht auf 0.

**Was ich geprüft und verworfen habe** — damit es niemand erneut versucht:

- **Mehr Kerne für die Suche.** 6 Streifen bringen 2,6× — 8 Streifen 2,4×, 16 Streifen 1,7×,
  64 Streifen 0,8× (langsamer als ohne). Die Arbeiter sind zu 90 % ausgelastet, die Streifen also
  gut ausbalanciert; aber die Gesamtarbeit wächst mit jedem Streifen. 6 ist bereits das Optimum.
- **Mehr Arbeitsspeicher.** Eine Suche liest **0 MB** von der Platte; die Trefferlisten liegen
  längst im Zwischenspeicher des Betriebssystems. Die Suche ist reine Rechenarbeit.
- **Den Seitentext ebenfalls aus dem Wortindex holen.** Geht nicht: die Abschnitte einer Seite
  überlappen sich (12 von 12 geprüften Seiten), und die dafür nötigen Zeichenpositionen stehen
  nur in Qdrant. Bloßes Aneinanderhängen ergäbe doppelten Text.
- **Qdrant nachstellen.** Bereits sauber eingestellt: Originalvektoren und Nutzdaten auf Platte,
  quantisierte Vektoren im Arbeitsspeicher, Status grün.

**Nebenbei auf dem Weg zur App:** Die Antworten kamen unkomprimiert, obwohl der Server es längst
kann — eine Trefferliste mit 40 Einträgen war 28,5 KB statt 8,1 KB. Und beim Umschalten auf
„Online" wurden jedes Mal die Kategorien abgefragt, die es in den Shamela-Daten gar nicht gibt.
Beides behoben. Nicht gemacht: Verbindungen wiederverwenden — das spart rund 60 ms je Anfrage,
verlangt aber Zustandshaltung über Fäden hinweg; das Verhältnis stimmt nicht.

### 9.2c Online-Bücher in die Offline-Bibliothek übernehmen — gebaut

Ein Buch aus der Shamela-Sammlung lässt sich jetzt **einmal übernehmen** und liegt danach dauerhaft
in der eigenen Bibliothek: durchsuchbar ohne Netz, lesbar, mit Lesezeichen und Zitat wie jedes
andere Buch. Kein Umschalten der Quelle mehr.

**Am schwierigsten war nicht das Herunterladen, sondern die Seitenzahl.** Lokal ist eine Seite eine
Ganzzahl; bei Shamela ist sie „Band 1, Seite 441". **25,5 % der 8.698 Bücher sind mehrbändig**, bei
22,7 % kommt dieselbe Seitenzahl mehrfach vor — die Eindeutigkeit der lokalen Seitentabelle wäre
gebrochen, und der Leser setzt zusätzlich eine lückenlose Zahlenreihe voraus, die Shamela-Seiten
nicht haben. Gelöst: intern zählt eine lückenlose Blattnummer, die echte Druckseite kommt als
eigene Bezeichnung mit und wird angezeigt und zitiert. Übernommene Bücher tragen die vierte
Verlässlichkeitsangabe „Shamela".

**Live geprüft** (Buch *الموسوعة الفقهية*, 1.352 Seiten, in die echte Bibliothek übernommen):

- Übernahme in wenigen Sekunden, danach in der Bibliotheksliste.
- Die **Offline**-Suche findet es und zeigt `ج3 ص7` statt einer Blattnummer.
- Der Leser zeigt Blatt 800 als `ج2 ص302`, Blatt 1200 als `ج3 ص211` — Bände bleiben unterscheidbar.
- Ein vorhandenes lokales Buch daneben ist unverändert (`Seite 79`, `exakt`).
- Nach einem Neustart der App ist das Buch noch da, und der Semantik-Schalter hält:
  2.216 Abschnitte, **0 vektorisiert** — obwohl der Start sonst alles nachholt.

**Dabei gefunden: ein Fehler, der schon vorher wirkte.** Ein Buch löschen und danach ein anderes
einlesen liess die Suche Treffer liefern, **deren angezeigter Text das gesuchte Wort gar nicht
enthält**: der Volltextindex wurde beim Löschen nicht mitaufgeräumt, und SQLite vergibt die
Passagen-Nummern neu. Reproduziert, behoben, zwei Tests dagegen. Das wirkt unabhängig von diesem
Vorhaben.

**Zwei Entscheidungen mit Begründung:**

- **Blockweise herunterladen** (500 Blätter je Anfrage, serverseitig gedeckelt). Das grösste Buch
  hat 231 MB Text und 90.751 Blätter — eine einzige Antwort wäre in keiner Zeitgrenze zustellbar.
  Je Block genügt ein Qdrant-Durchlauf; seitenweise hätte ein grosses Buch 1.171 s gebraucht.
- **Bedeutungssuche standardmässig aus** für übernommene Bücher. Grund: `vector_search` lädt bei
  **jeder** Anfrage alle Vektoren der ganzen Bibliothek. Ein einziges grosses Buch (≈322 MB je
  Suche) hätte die Bedeutungssuche über die eigenen Bücher dauerhaft verlangsamt — ein Schaden am
  Bestehenden. Abwählbar im Vorschaudialog.

**Nebenwirkung zum Guten:** Weil Seiten jetzt in einem Durchlauf zusammengesetzt werden, kostet das
Vorausladen des Online-Lesers eine Serverrunde statt vierzehn.

**Absicherungen:** Die Bibliothek enthält nie ein halbes Buch, das aussieht wie ein ganzes — die
Buchzeile gilt bis zum Schluss als „in Arbeit", die Liste zeigt nur fertige Bücher, ein Fehler
löscht die angefangene Zeile, und ein Abbruch wird beim nächsten Start weggeräumt. Die Blattfolge
jedes Blocks wird auf Lücken geprüft. Und die Druckseiten überleben den `.echolib`-Rundlauf —
sonst hätte ein übernommenes Buch auf einem anderen Rechner lautlos seine Zitierfähigkeit verloren.

### 9.3 Kleinere Vorschläge

- **`app/shamela.py` abtrennen** (Punkt 5d) — reine Umstrukturierung, kein Verhaltenswechsel, aber
  ich verschiebe ungern Produktcode ohne dein OK.
- ~~**Fehler-Protokollierung statt stummer `catch`** (Punkt 5b)~~ — erledigt für die Online-Suche:
  ein Fehler in der Wortsuche sah bisher aus wie „keine Treffer" und stand nirgends im Protokoll.
- ~~**`docs/`-Probedateien** (Punkt 7)~~ — entschieden und erledigt: gelöscht (siehe Punkt 7).
- ~~**Auch die erste Suche beschleunigen**~~ — entschieden und erledigt, siehe 9.2.

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
