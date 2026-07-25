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
