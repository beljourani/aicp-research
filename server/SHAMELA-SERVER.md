# Shamela-Suchserver – Einrichtung & Betrieb

Dieser Server macht die ~8.600 Bücher der *Al-Maktaba Al-Shamela* über eine
**semantische Suche** durchsuchbar, ohne dass die App die Bücher lokal
speichern muss. Die App schickt nur den Suchtext; der Server bettet ihn ein,
durchsucht die Vektor-Datenbank und liefert Treffer samt ganzen Seiten für den
Leser zurück.

Der Zugriff ist durch einen geheimen **Token** geschützt. Diesen Token trägt
man in der App **einmalig** ein; danach bleibt die Verbindung bestehen.

---

## Was läuft auf dem Server?

Drei Dienste in Docker, per `docker compose` gestartet:

| Dienst   | Aufgabe                                                              |
|----------|---------------------------------------------------------------------|
| `qdrant` | Vektor-Datenbank – speichert die 11,5 Mio. eingebetteten Abschnitte |
| `api`    | Such-Dienst (FastAPI) – bettet Anfragen ein, sucht, baut Seiten     |
| `caddy`  | HTTPS-Endpunkt – besorgt automatisch ein Zertifikat                 |

Der einmalige **Import** läuft als separater Lauf (`importer`).

---

## Voraussetzungen

- **VPS** mit Ubuntu 22.04/24.04, root- oder sudo-Zugang.
- **Empfohlene Größe:** **16 GB RAM, ≥ 8 vCPU, ≥ 160 GB SSD**
  (z. B. Hetzner Cloud **CX43**, ~16 €/Monat; falls die CX-Reihe am Standort
  ausverkauft ist, tut es auch die ARM-Maschine **CAX31** – die Software läuft
  auf ARM). Der Import nutzt standardmäßig **binäre Quantisierung**: die Vektoren
  belegen dadurch nur ~1–2 GB RAM (Feinbewertung über die Originalvektoren auf
  der Platte, praktisch gleiche Trefferqualität). Auf einer 32-GB-Maschine kann
  man im `docker-compose.yml` beim `importer` `--quant binary` → `int8` setzen.
- **Plattenbedarf:** Der Download (~43 GB) und die Vektor-Datenbank (~50–60 GB)
  liegen zeitweise gleichzeitig vor – 160 GB reichen. Nach dem Import kann der
  Hugging-Face-Zwischenspeicher gelöscht werden (siehe unten).
- Eine **Domain** (z. B. `shamela.deine-domain.de`), deren DNS-A-Record auf die
  Server-IP zeigt. Für das HTTPS-Zertifikat müssen Port **80** und **443**
  von außen erreichbar sein.

---

## Schritt 1 – Server vorbereiten

Auf dem VPS einloggen und Docker installieren:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER      # danach einmal aus- und wieder einloggen
```

## Schritt 2 – Projekt auf den Server holen

Nur den `server`-Ordner brauchst du. Am einfachsten das Repo klonen:

```bash
git clone https://github.com/beljourani/aicp-research.git
cd aicp-research/server
```

## Schritt 3 – Domain & Token eintragen

```bash
cp .env.example .env
nano .env
```

Trage ein:

- `DOMAIN` – deine Domain, exakt wie im DNS (ohne `https://`).
- `API_TOKEN` – einen langen, zufälligen Geheimtext. Erzeugen mit:

  ```bash
  openssl rand -hex 32
  ```

  Diesen Wert brauchst du später in der App. **Gut aufbewahren, nicht teilen.**

## Schritt 4 – Import der Bücher (einmalig, dauert mehrere Stunden)

Lädt den fertig eingebetteten Datensatz (~43 GB) von Hugging Face und schreibt
ihn in die Vektor-Datenbank. Erst Qdrant starten, dann den Import:

```bash
docker compose up -d qdrant
docker compose run --rm importer
```

Der Lauf ist **wiederaufnehmbar**: bricht er ab (z. B. Verbindung getrennt),
einfach den `docker compose run --rm importer`-Befehl erneut starten – schon
importierte Abschnitte werden übersprungen bzw. überschrieben.

> Tipp: In einer `tmux`- oder `screen`-Sitzung starten, damit der Import beim
> Trennen der SSH-Verbindung weiterläuft:
> ```bash
> sudo apt install -y tmux && tmux
> # ... Import starten ...   Loslösen: Strg-b, dann d.   Zurück: tmux attach
> ```

Am Ende steht `data/meta.db` bereit (Bücher-/Seitenindex) und die Vektoren
liegen in Qdrant.

## Schritt 5 – Server starten

```bash
docker compose up -d
```

Caddy holt jetzt automatisch das HTTPS-Zertifikat für deine Domain (dafür muss
der DNS-Eintrag stehen und Port 80/443 offen sein).

## Schritt 6 – Funktionstest

```bash
# Erreichbarkeit + Anzahl Punkte (sollte in die Millionen gehen):
curl -s https://DEINE-DOMAIN/health

# Eine echte Suche (Token einsetzen):
curl -s -X POST https://DEINE-DOMAIN/search \
  -H "X-API-Key: DEIN-TOKEN" -H "Content-Type: application/json" \
  -d '{"q":"الصبر على البلاء","limit":5}'
```

Kommen bei `/health` Punkte zurück und liefert `/search` Treffer mit Titel,
Autor und Seitenzahl, läuft der Server. Danach in der App unter
**Einstellungen → Shamela-Server** die Domain (`https://DEINE-DOMAIN`) und den
Token eintragen – einmalig.

---

## Betrieb & Wartung

- **Logs ansehen:** `docker compose logs -f api`
- **Neustart:** `docker compose restart`
- **Stoppen:** `docker compose down` (Daten bleiben in den Volumes erhalten)
- **Aktualisieren** (nach `git pull` im `server`-Ordner):
  `docker compose build api && docker compose up -d`
- **Token wechseln:** in `.env` ändern, dann `docker compose up -d api`
  (danach den neuen Token in der App eintragen).

## Endpunkte (Kurzreferenz)

| Methode & Pfad | Zweck                                                     |
|----------------|-----------------------------------------------------------|
| `GET /health`  | Erreichbarkeit + Punktzahl (ohne Token)                   |
| `POST /search` | Semantische Suche; Body: `q`, `limit`, `offset`, Filter   |
| `GET /page`    | Ganze Seite + Nachbarseiten für den Leser                 |
| `GET /categories` | Liste der Kategorien mit Buchzahl                      |
| `GET /authors` | Autoren (optional gefiltert mit `?q=`)                    |

Alle außer `/health` erfordern den Token im Header
`X-API-Key: …` (oder `Authorization: Bearer …`).

## Häufige Stolpersteine

- **Zertifikat kommt nicht:** DNS-A-Record prüfen (`dig DEINE-DOMAIN`), Port 80
  muss offen sein. Caddy-Logs: `docker compose logs caddy`.
- **`/health` meldet `ok: false`:** Qdrant noch am Indizieren oder Import nicht
  gelaufen. `docker compose logs qdrant` prüfen.
- **Wenig RAM / Absturz beim Start:** Der Import nutzt bereits `--quant binary`
  (sparsam). Falls du auf `int8` umgestellt hattest und es zu eng wird, im
  `docker-compose.yml` beim `importer` wieder auf `binary` zurückstellen.
- **Platte voll während des Imports:** Nach erfolgreichem Import den
  Hugging-Face-Zwischenspeicher freigeben: `docker volume rm server_hf_cache`
  (bzw. `docker compose down` und dann das `hf_cache`-Volume entfernen).
- **Suche langsam beim ersten Aufruf:** Das Einbettungsmodell wird beim ersten
  Request in den Speicher geladen; danach ist es schnell.
