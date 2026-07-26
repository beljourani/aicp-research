# Shamela: Online-Suche auf Wort/Wurzel umgestellt — Stand 25.07.2026

**Fertig und live verifiziert.** Die Online-Suche arbeitet jetzt wie die Offline-Suche: nach Wort
und Wurzel, mit ODER, Ausschluss und Phrase. Die semantische Suche bleibt als zuschaltbare
Ergänzung erhalten und ist standardmäßig an. Kein Versions-Tag gesetzt.

---

## Der Index

| | |
|---|---|
| Abschnitte | **11.488.400 von 11.488.400 (100 %)** |
| Bücher | 8.698 |
| Größe | 29,8 GB (Volltextindex + Textausschnitte für die Trefferanzeige) |
| Dauer | 409 min erster Lauf + 54 min Nachlauf |
| Freier Platz danach | 128 GB von 290 GB |
| Neu eingebettet | **nichts** – die Vektoren in Qdrant blieben unberührt |

Zwei Autoren fielen im ersten Lauf aus („Server disconnected", zusammen 55.254 Abschnitte). Der
zweite Lauf erkannte „3.177 Autoren bereits im Index, zu tun: 2" und holte genau diese nach —
ohne etwas doppelt zu schreiben. Der Index ist damit vollständig.

## Live verifiziert (durch die App, gegen den echten Server)

| Prüfung | Ergebnis |
|---|---|
| Wortsuche findet die Wurzel im Text | ✓ 3 Anfragen, je 5/5 Treffer enthalten die Wurzel |
| `semantic=false` → reine Wortsuche | ✓ 20 Treffer |
| `semantic=true` → Zusammenführung | ✓ 9 zusätzliche Stellen gegenüber reiner Wortsuche |
| Ausschluss (`-wort`) | ✓ wirkt nachweislich |
| ODER (`\|`) | ✓ liefert die Vereinigung |
| Phrasensuche (`"…"`) | ✓ 10 von 10 Treffern enthalten die Wortfolge **wörtlich** |
| Trefferform unverändert | ✓ alle Felder da, `seq` bleibt null |
| Buch öffnen | ✓ Druckseite passt zur Kennung (ج2 ص1034 ← V02P1034) |
| Autoren- und Buchfilter | ✓ beide wirken |
| Offline-Suche unberührt | ✓ unverändert nutzbar |

**Antwortzeiten:** 1,2 s (reine Wortsuche) bis 3,4 s (mit Semantik) für übliche Anfragen.

## Zwei Befunde, die den Plan korrigiert haben

**`nltk` fehlte im Server-Container.** Ohne den ISRI-Stemmer hätte der Server anders gestemmt als
deine App — gemessen 7 von 10 Wörtern (`يكتبون` → `يكتب` statt `كتب`). Der Index wäre unbrauchbar
gewesen. Aufgefallen *vor* dem Lauf, sonst wären 7 Stunden umsonst gewesen.

**Die Engine-Abfrage skaliert nicht auf 11,5 Mio. Abschnitte.** Sie verbindet den Volltextindex mit
den Passagen- und Buchtabellen, *bevor* sortiert wird. Lokal (86.000 Passagen) ist das folgenlos;
online werden dadurch Hunderttausende Volltexte aus einer 30-GB-Datei gelesen — gemessen 14 bis 27
Sekunden je Anfrage. Der Server rankt jetzt zuerst im Index und verbindet nur die besten Zeilen:
**14,0 s → 0,7 s** bzw. **27,4 s → 2,5 s**. Geparst, gestemmt, gefiltert und bewertet wird
weiterhin mit derselben Engine-Logik, die Reihenfolge bleibt also dieselbe. **Die gemeinsame Engine
wurde nicht angefasst** — die Offline-Suche ist unverändert.

## Morgens von dir zu prüfen (committet, Technik verifiziert)

1. **Der Semantik-Schalter ist im Online-Modus jetzt sichtbar** und standardmäßig an. Zu prüfen: Ob
   er dort sinnvoll platziert wirkt und ob sich das Umschalten spürbar auf die Treffer auswirkt.
2. **Trefferqualität im Alltag.** Die Wortsuche findet zuverlässig, wo ein Wort *wirklich steht* —
   für Zitate meist das Gewünschte. Ob die Mischung mit der Semantik für dich stimmt, lässt sich
   nur beim echten Arbeiten beurteilen.
3. **Buch- und Autorenfilter** in Verbindung mit der neuen Suche.

## Offen / Einschränkungen

- **Sehr häufige Wörter sind langsam.** `قال` braucht rund 18 Sekunden: Es trifft Millionen von
  Abschnitten, und die Rangfolge muss über alle berechnet werden. Übliche Anfragen liegen bei 1–3
  Sekunden. Falls dich das stört, ließe sich das entschärfen (z. B. Ergebnis-Zwischenspeicher oder
  eine Obergrenze für die Kandidatenmenge) — das ist ein eigener Schritt.
- **1.163 doppelte Abschnittskennungen** im ersten Lauf (0,01 %). Sie sind im Volltextindex
  enthalten und auffindbar; nur bei der Zusammenführung mit der semantischen Liste können sie nicht
  eindeutig zugeordnet werden. Im zweiten Lauf traten keine auf.
- **Die A2-Leser-Performance** (Ruckeln bei großen Büchern) läuft wie besprochen getrennt weiter —
  hier nicht angefasst.

---

## Nachtrag 26.07. — Buchgefilterte Suche war zu langsam (behoben, live gemessen)

**Problem:** Mit Buchfilter suchte die Wortsuche global im Volltextindex und prüfte erst danach
jeden Treffer gegen die Buchliste. Bei einem häufigen Wort trifft das Millionen Abschnitte.

**Behoben:** Je gewähltem Buch wird jetzt der `rowid`-Bereich seiner Abschnitte bestimmt und die
Suche darauf eingegrenzt. FTS5 hält seine Trefferlisten nach `rowid` sortiert und überspringt so
den größten Teil des Index. Da die Abschnitte eines Buches nicht lückenlos beieinanderliegen
(gemessen: Streuung bis 38-fach), wird anschließend auf das Buch selbst nachgefiltert.

| Anfrage (mit Buchfilter) | vorher | nachher |
|---|---|---|
| `الله` | **> 150 s (Timeout)** | **1,16 s** |
| `الفرق` | 14,8 s | **0,31 s** |
| `الصبر` | – | 0,13 s |
| Leser-Suche im Buch (limit 100, mit Semantik) | – | 0,62 s |
| drei Bücher gleichzeitig | – | 3,55 s |

Treffer und Reihenfolge sind **identisch** zur alten Abfrage (direkt gegeneinander geprüft:
0,09 s gegenüber 12,52 s, gleiche Trefferliste in gleicher Ordnung).

**Der im Auftrag vorgeschlagene Weg wurde gemessen und verworfen.** Von der Kandidatenmenge zu
treiben (per `JOIN` bzw. `CROSS JOIN`) macht es deutlich *langsamer*: `الله` im Buch brauchte damit
799 s (JOIN) bzw. 319 s (CROSS JOIN) gegenüber 150 s vorher. Grund: `bm25()` lässt sich nur im
Rahmen einer MATCH-Abfrage berechnen, weshalb SQLite die Volltextabfrage je Kandidatenzeile erneut
ausführt. Der Ausführungsplan bestätigte außerdem, dass der einfache `JOIN` die Reihenfolge gar
nicht umdreht.

**Der Index auf `passages(document_id)` existierte auf der Live-Datenbank bereits** (bei der
Optimierung am 25.07. angelegt). Er ist jetzt zusätzlich im Builder-Schema hinterlegt, damit ein
Neuaufbau ihn mitbringt.

**Noch offen (wie besprochen ein eigener Schritt):** Ein sehr häufiges Wort **ohne** Buchfilter
bleibt langsam (`الفرق` 2,3 s, `الله` ~18 s), weil die Rangfolge über alle Treffer berechnet wird.

**Am Rande gemessen:** Die erste semantische Suche nach einem Server-Neustart dauert rund 18
Sekunden – dann lädt der Dienst das Einbettungsmodell. Danach liegt dieselbe Anfrage bei unter
einer Sekunde. Das ist kein Fehler, aber gut zu wissen, falls dir die App direkt nach einem
Neustart einmal träge vorkommt.

---

## Nachtrag 26.07. (2) — Semantik sortiert nur noch um; Marker ganzwörtig

Beides galt für **online und offline gleichermaßen**, beides ist live verifiziert.

### Fix A — die Semantik fügt keine Treffer mehr hinzu

Bisher brachte die Bedeutungssuche eigene Stellen in die Liste. Dadurch standen dort Treffer, die
die gesuchten Wörter gar nicht enthalten, und dieselbe Stelle konnte doppelt erscheinen. Jetzt gilt:
**Die Wort-Treffer sind die einzige Ergebnismenge, die Semantik ändert nur deren Reihenfolge.**

- offline: `hybrid_search` nimmt Vektor-Treffer nicht mehr neu auf
- online: Vektor-Treffer werden über `chunk_meta` auf ihre Passage abgebildet und nur gewichtet,
  wenn sie schon Wort-Treffer sind

**Live geprüft** mit „الجهات الست لا" (Wurzeln `جهت`, `الس`, `لا`):

| | Ergebnis |
|---|---|
| offline: Passagen mit **allen** drei Wurzeln | **20 von 20** |
| online: Seiten mit **allen** drei Wurzeln | **6 von 6** |
| mit/ohne Semantik dieselbe TrefferMENGE | ✓ online und offline |
| Doppelungen | keine |

### Fix B — Markierung wurzelbewusst und ganzwörtig

Der Browser verglich die Ausschnitte wörtlich. Das markierte kurze Wörter auch **mitten in
anderen** („لا" in „الكلام") und verfehlte umgekehrt Beugungen und vokalisierte Formen. Die
Markierungen berechnet jetzt die App mit `highlight_spans` — dieselbe Logik wie im Leser, für beide
Quellen.

Live geprüft: online werden jetzt auch `الْجِهَاتِ`, `السِّتِّ` und `بالجهات` markiert; alle
Markierungen liegen an Wortgrenzen. Test ergänzt, dass „لا" nicht in „الكلام" markiert wird.

**Zusätzlich zum Auftrag:** Die Trefferliste **im Leser** hatte denselben Fehler und war nicht
genannt — sie ist jetzt ebenfalls umgestellt, sonst wären dort weiterhin falsche Marker erschienen.

### Antwortzeiten (unverändert)

| | ohne Semantik | mit Semantik |
|---|---|---|
| online, gesamt | 1,27 s | 2,22 s |
| online, im Buch | 0,92 s | 1,02 s |
| offline | 0,05 s | 0,25 s |

### Hinweis zur Messung

Eine erste Prüfung schien fehlzuschlagen („0 von 6 Treffern mit allen Begriffen"). Das war ein
Fehler meiner Prüfung, nicht des Produkts: Ich hatte den Text mit `split()` zerlegt, wodurch
Satzzeichen am Wort kleben (`الست،`) und anders gestemmt werden als im Index. Mit der Zerlegung der
Engine (`tokenize`) stimmt es vollständig.

