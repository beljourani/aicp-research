# Shamela-Online-Leser: vier gemeldete Fehler — Stand 25.07.2026

Alle vier Punkte sind behoben, einzeln getestet, live gegen den echten Server geprüft und
committet. **Kein Shamela-Server-Neustart war nötig** — alles läuft in der App bzw. nutzt die
vorhandene `/page`-Antwort. Kein Versions-Tag gesetzt.

---

## Eine Abweichung vom Auftrag: Reihenfolge getauscht

Punkt 3 wurde **vor** Punkt 2 umgesetzt. Grund: Punkt 2 lässt `openShamelaReader` am Ende
`selectHit` rufen — und `selectHit` sprang ohne den Fix aus Punkt 3 auf Seite 1, weil
Online-Treffer keine Blattnummer tragen. Punkt 2 zuerst hätte also den Fehler aus Punkt 3 genau
in den Weg eingebaut, der heute funktioniert (das Öffnen aus der Haupt-Trefferliste). Getrennte
Commits wie gefordert, nur in der Reihenfolge, die `main` nie kaputt lässt.

---

## Punkt 1 — Lesezeichen-Knopf in den Online-Treffern (erledigt, live verifiziert)

Die Online-Trefferliste hatte als einzige keinen Lesezeichen-Knopf.

- `shamelaHitEl` bekommt denselben Knopf wie die lokale Liste.
- Gemerkt werden Buch- und Seitenkennung, Titel/Autor und die echte Druckseite („ج23 ص5").
- Knopf in Liste und Leser zeigen denselben Zustand: beide tragen ihren Schlüssel als
  `data-bmkey`, `toggleBookmark` zieht den jeweils anderen mit.

**Live geprüft:** Setzen meldet `saved=true`, Eintrag steht in der Liste mit unveränderter
Druckseite, zweiter Klick entfernt ihn, Liste ist wieder wie zuvor.

## Punkt 3 — Weiterklicken sprang auf Seite 1 (erledigt, live verifiziert)

Treffer in der Leser-Liste trugen keine Blattnummer (`seq:null`); daraus wurde über `n|0`
stillschweigend `0` und damit Seite 1.

- Die Seitenkennung (`page`) wird jetzt mitgeführt.
- `selectHit` löst online eine fehlende Blattnummer über `/page` auf und merkt sie sich.
- `gotoPage` bricht bei ungültiger Blattnummer ab, statt auf Seite 1 zu klemmen.

**Live geprüft:** Alle 8 Treffer eines Buches lösen sich auf gültige Blätter auf, **keiner** landet
auf Blatt 1. Zwei Treffer auf derselben Druckseite ergeben korrekt dasselbe Blatt, verschiedene
Seiten verschiedene Blätter. Rückweg stimmt: Blatt 479 → `V23P005` → „ج23 ص5".

## Punkt 2 — „Active"-Zustand in der Leser-Trefferliste (erledigt, live verifiziert)

`openShamelaReader` rief nie `selectHit`, anders als lokal.

- Der geöffnete Treffer wird über die Seitenkennung gesucht (ersatzweise über die Blattnummer)
  und mit `selectHit` markiert und angesteuert.

**Live geprüft:** Über drei Bücher und Seitenformate (`V23P005`, `P032`, `V01P488`) wird der
geöffnete Treffer zuverlässig gefunden und zeigt auf dieselbe Druckseite.

## Punkt 4 — Marker fehlten auf Online-Seiten (erledigt, live verifiziert)

Online-Seiten wurden ohne Marker gerendert; im Browser griff nur ein wörtlicher Vergleich.

- `shamela_page` nimmt `terms` an und liefert je Seite `spans`, berechnet mit dem vorhandenen,
  wurzelbewussten `highlight_spans` — derselbe Weg wie bei lokalen Büchern.
- Beide Leser-Aufrufe geben `readerTerms()` mit; `fillSheet` nutzt die gelieferten `spans`.

**Live geprüft:** Die Marker sind Zeichen für Zeichen **identisch** mit dem, was ein lokales Buch
bekäme (vier Bücher). Auf einer Seite mit 107 Vokalzeichen werden auch `وَسَلِّمُوا`, `ويسلموا`,
`وسلامه`, `والصلاة` erkannt.

Zwei Beobachtungen aus der Prüfung, beide **kein Fehler**:
- Es gibt Seiten mit *weniger* Markern als vorher. Der wörtliche Vergleich markierte `الصبر` auch
  *innerhalb* von `والصبر` — also halbe Wörter. Jetzt wird das ganze Wort markiert.
- `قال` markiert `قاله` nicht (der Stemmer bildet andere Wurzeln für manche Vorsilben-Formen).
  Das ist eine bestehende Eigenart der Engine und **betrifft die Offline-Suche genauso** — Online
  verhält sich damit wie gefordert exakt wie Offline.

---

## Nur am Bildschirm zu beurteilen (committet, Technik geprüft)

Die Abläufe sind end-to-end gegen den echten Server geprüft; das **Aussehen** habe ich bewusst
nicht bewertet:

1. Ob der Lesezeichen-Knopf in der Online-Trefferliste an der richtigen Stelle sitzt und sich
   anfühlt wie der lokale.
2. Ob die Hervorhebung des aktiven Treffers in der Leser-Liste sichtbar genug ist.
3. Ob die Marker im Lesetext optisch sitzen (Position wurde rechnerisch geprüft, nicht gerendert).

## Regression geprüft

- Offline-Suche unverändert: Treffer, `document_id`, Seite, Verlässlichkeit („sicher"), Seiten
  laden weiter mit Markern (24 Marker auf der Stichprobenseite).
- Autorenfilter und Buchfilter online funktionieren weiter.
- Alle Tests grün: 7 Engine-Testdateien + `server/test_meta.py`, vor jedem Commit ausgeführt.
  JS-Syntax der Oberfläche nach jeder Änderung mit `node --check` geprüft.

## Offen / bewusst nicht gemacht

- **Snippet-Hervorhebung in der Trefferliste** (im Auftrag als „optional, niedrige Priorität"
  markiert) nutzt weiter den wörtlichen Vergleich. Für dieselbe Normalisierung müssten die Marker
  je Ausschnitt berechnet werden — machbar, aber ein eigener Schritt.
- **Der schlanke Server-Endpunkt `/resolve`** (optionale Variante bei Punkt 3) wurde nicht gebaut.
  Die Auflösung über `/page` reicht: sie passiert einmal pro Fundstelle und wird gemerkt. Damit
  war kein Redeploy nötig.
