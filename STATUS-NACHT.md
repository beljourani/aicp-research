# Shamela: Phase A (Leser) + Machbarkeitsprüfung Wortsuche — Stand 25.07.2026

Kein Versions-Tag gesetzt. Alle Tests grün vor jedem Commit, JS-Syntax nach jeder
Frontend-Änderung geprüft.

---

## A1 — Trefferliste im Leser nach Seite sortiert (erledigt, live verifiziert)

Die Treffer kamen online nach Ähnlichkeit (Qdrant-Score), offline nach Relevanz. Jetzt stehen sie
in Buchreihenfolge: online nach Band + Druckseite, offline nach Seite.

**Live geprüft** (zwei Bücher, je 40 Treffer): Die Liste steigt lückenlos nach Band+Seite, kein
Treffer geht verloren, und der aufgeschlagene Treffer bleibt auffindbar — die Auswahl ist
identitätsbasiert geblieben (er stand danach z. B. auf Index 37 statt 0 und war trotzdem korrekt
markiert). Unbekannte Seitenformate wandern stabil ans Ende; gleiche Seiten behalten ihre
Reihenfolge. Angezeigte Druckseiten unverändert.

## A2 — Leser virtualisieren: **gestoppt**, stattdessen die belegte Ursache behoben

**Ich habe die vermutete Ursache gemessen statt angenommen — sie trägt nicht.** Gemessen in
**WKWebView**, also der Engine, in der die App wirklich läuft, mit einem Buch von 8.765 Seiten:

| | Messwert |
|---|---|
| Aufbau aller 8.765 Blätter | **15 ms** (einmalig) |
| DOM-Knoten | 26.295 |
| Arbeit je Scroll-Schritt | **1,37 ms** — Budget für flüssige 60 Bilder/s sind 16,7 ms |

Die Knotenzahl allein verursacht in der echten Engine also **kein** Ruckeln. Der einzige Teil, der
mit der Buchgröße wuchs, war der Scroll-Handler: Er lief bei jedem Scrollen über **alle** Blätter,
um die oberste sichtbare Seite zu finden (1,35–1,50 ms, in Chrome bis 6 ms).

**Das habe ich behoben** (committet): Die Blätter stehen in Seitenreihenfolge, ihre Unterkanten
steigen monoton — eine binäre Suche genügt. Ergebnis: **1,35 ms → unter der Messgrenze**. Die neue
Funktion wurde direkt aus `index.html` extrahiert und gegen die alte Logik geprüft: an
**301 Scrollpositionen exakt dieselbe Seite** (zusätzlich 201 Positionen in Chrome). Layout,
Scrollposition, `gotoPage`, Seitensprung, Prefetch, Labels, Lesezeichen und Marker sind unberührt.

**Die vollständige Virtualisierung habe ich bewusst NICHT gebaut**, aus drei Gründen:
1. Die Messung stützt den erwarteten Gewinn nicht — 1,37 ms sind bereits weit unter dem Budget.
2. Platzhalter brauchen geschätzte Seitenhöhen. Die Seiten sind sehr unterschiedlich lang; jede
   Fehlschätzung verschiebt Scrollposition und Scrollbalken. Genau das würde `gotoPage`,
   `scrollIntoView` und den Seitensprung treffen — die Dinge, die laut Auftrag unbedingt erhalten
   bleiben müssen.
3. Ich kann Scrollverhalten hier nicht sehen, nur messen. Ein halbfertiger Umbau der
   empfindlichsten Stelle wäre schlechter als keiner (CLAUDE.md: „run the app and look").

**Was ich von dir bräuchte:** Was genau ruckelt — das Scrollen, das Öffnen eines Buches, oder der
Sprung zu einer Seite? Und bei welchem Buch? Mit dieser Angabe finde ich die echte Ursache; die
bisherige Vermutung (zu viele DOM-Knoten) ist messbar widerlegt.

---

# B0 — Machbarkeit: Online-Suche auf Wort/Wurzel umstellen

**Nichts gebaut, nichts gestartet.** Nur gemessen. Alle Zahlen vom laufenden VPS.

## Ausgangslage auf dem Server

| | |
|---|---|
| Freier Speicher | **172 GB** von 290 GB (41 % belegt) |
| Arbeitsspeicher | 23 GB gesamt, 15 GB von Qdrant belegt, ~8 GB frei |
| Kerne | 8 |
| Abschnitte (Punkte) | **11.488.400** |

## Wichtigster Befund: `text_norm` ist vorhanden — aber **nicht unsere Normalisierung**

Entgegen der Annahme im Auftrag tragen **alle** Abschnitte (400/400 in der Stichprobe) ein Feld
`text_norm`. Es ist aber **eine andere Normalisierung als unsere**:

| | unsere `normalize()` | deren `text_norm` |
|---|---|---|
| Zeilenumbrüche | bleiben erhalten | zu Leerzeichen |
| arabische Ziffern | `١` → `1` | bleiben `١` |
| Hamza-Formen | `ئ` → `ي` | bleibt `ئ` |

Da Index und Anfrage **identisch** normalisieren müssen (sonst findet die Suche nichts — CLAUDE.md),
ist `text_norm` **nicht direkt verwendbar**. Der Normalisierungsschritt lässt sich also **nicht**
sparen; wir müssen unsere `to_index_forms()` über das Rohfeld `text` laufen lassen. Das ist kein
Hindernis, nur kein Zeitgewinn.

## Aufwand (gemessen, nicht geschätzt)

An **50.000 echten, verschiedenen** Abschnitten vom Server gemessen und hochgerechnet:

| Schritt | Wert |
|---|---|
| Lesen aus Qdrant | 982 Abschnitte/s → **3,2 h** einkernig (der Löwenanteil; durch Aufteilen parallelisierbar) |
| Aufbereiten (`to_index_forms`) | 4.035/s → 0,8 h einkernig, **0,1 h auf 8 Kernen** |
| FTS5 schreiben | 12.330/s → **0,3 h** |
| **Gesamt realistisch** | **~3,5–4 h** am Stück, mit Aufteilung auf mehrere Leser ~1,5 h |
| **Indexgröße** | **~10,7 GB** (932 Byte/Abschnitt; der Wert sinkt mit dem Umfang weiter, ist also eine Obergrenze) |
| Suchgeschwindigkeit | 0,5–3,6 ms je Anfrage im 50.000er-Testindex |

Speicher ist damit **kein Problem**: 10,7 GB von 172 GB freien.

## Empfehlung

**Machbar, und ich würde es empfehlen** — mit einer wichtigen Einschränkung, die eine
Produktentscheidung ist, keine technische.

Dafür spricht: Der Aufwand ist überschaubar (eine Nacht, kein Neu-Einbetten, keine 43 GB erneut),
der Platzbedarf unkritisch, die Suche wird spürbar schneller als die heutige Vektorsuche, und die
Online-Suche verhielte sich endlich wie die Offline-Suche — Wort und Wurzel, mit Boolean, Ausschluss
und Phrasensuche, die es online heute gar nicht gibt.

**Die Einschränkung:** Eine reine Wortsuche findet **anderes** als die heutige semantische Suche.
Heute findet „الصبر على البلاء" auch Stellen, die den Gedanken *sinngemäß* ausdrücken, ohne die
Wörter zu enthalten. Nach der Umstellung fielen solche Treffer weg. Umgekehrt findet die Wortsuche
zuverlässig jede Stelle, wo das Wort (oder seine Wurzel) *wirklich steht* — was für Zitate und
Belege meist das ist, was man will.

**Mein Vorschlag:** beides behalten, wie es die Offline-Suche schon tut (`hybrid_search` verbindet
dort FTS und Semantik). Der Vektorindex bleibt ohnehin liegen — man verliert nichts, und du könntest
je Suche entscheiden. Das kostet keinen zusätzlichen Aufbau, nur etwas mehr Arbeit an `/search`.

## Bitte um Freigabe

Ich habe **nichts gestartet**. Für B1 bräuchte ich von dir:

1. **Freigabe** für den ~4-stündigen Indexaufbau auf dem VPS.
2. Entscheidung: **Wortsuche ersetzt** die semantische Suche — oder **beide nebeneinander**
   (meine Empfehlung).

## Offen / bewusst nicht gemacht

- Volle Virtualisierung des Lesers — siehe A2 oben, wartet auf deine Angabe, was genau ruckelt.
- B1 (der eigentliche Umbau) — nicht begonnen, wartet auf Freigabe.
