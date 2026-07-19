# Auto-Update einrichten (einmalig)

Das Repository ist bereits angelegt und in der App hinterlegt:
**`beljourani/aicp-research`** (öffentlich).

Sobald der Code dort liegt, baut die Cloud bei jedem Versions-Tag automatisch
Windows-Installer **und** Mac-DMG und veröffentlicht sie. Die App prüft beim
Start selbst auf Updates und aktualisiert sich auf Klick.

---

## 1. Zugriffs-Token erstellen (einmalig, ~1 Minute)

Zum Hochladen braucht Git ein Passwort in Form eines Tokens.

1. Im Browser öffnen: https://github.com/settings/tokens/new
2. **Note:** z. B. `aicp-upload`. **Expiration:** nach Wunsch (z. B. 90 Tage).
3. Haken setzen bei **`repo`** und bei **`workflow`**
   (der `workflow`-Haken ist nötig, damit die Bau-Anweisungen mit hochgehen).
4. Ganz unten **Generate token** → den angezeigten Token **kopieren**
   (er wird nur einmal gezeigt).

---

## 2. Code hochladen (Terminal)

Terminal öffnen und diese Zeilen nacheinander einfügen:

```
cd ~/Projekte/echo-archive
rm -f .git/*.lock
git add -A
git commit -m "AICP Research"
git remote add origin https://github.com/beljourani/aicp-research.git
git push -u origin main
```

Beim `git push` fragt Git nach Anmeldedaten:
- **Username:** `beljourani`
- **Password:** den eben kopierten **Token** einfügen (nicht dein GitHub-Passwort).

Danach ist der Code online. `git commit` meldet evtl. „nothing to commit" –
das ist in Ordnung, dann ist schon alles erfasst.

---

## 3. Eine Version veröffentlichen (= Update auslösen)

Jedes Mal, wenn du ein Update herausgeben willst, im Terminal:

```
cd ~/Projekte/echo-archive
git tag v1.0.1
git push origin v1.0.1
```

(Versionsnummer immer erhöhen: v1.0.1, v1.0.2, …)

Das startet die beiden Cloud-Builds automatisch. Nach ein paar Minuten hängen
**Setup.exe** und **DMG** unter „Releases". Die installierten Apps melden dann
beim nächsten Start **„Update verfügbar"**.

> Die Versionsnummer kommt allein aus dem Tag – sonst musst du nichts ändern.

---

## Wichtig: die erste Version

Auto-Update greift ab der ersten Version, die den Updater schon enthält. Setze
also einmal `v1.0.0` (oder starte den Windows-/Mac-Workflow manuell unter
**Actions**), installiere diese eine Version normal – ab dann läuft jedes
weitere Update per Knopf in der App.

Fortschritt der Builds siehst du jederzeit im Reiter **Actions** deines Repos.
