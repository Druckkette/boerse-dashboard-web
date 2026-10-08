# Beta auf der Synology DS220+

Die Beta verwendet dieselbe Anwendung, dieselben Bewertungsmodelle und denselben Datenbestand
wie das private Dashboard. Nur `frontend-beta` kommt hinzu. Beide Frontends verwenden genau
`ghcr.io/${GHCR_OWNER}/boerse-dashboard-web-frontend:${IMAGE_TAG}`. Backend, PostgreSQL, Redis,
interaktiver Worker, übrige Worker und Scheduler bleiben gemeinsam. Es gibt keine Beta-Migration,
Benutzerverwaltung, persönliche Watchlist oder weitere Datenvolumes.

Diese Anleitung beschreibt die spätere Bereitstellung. Die Implementierung verändert keine laufende NAS.
Die allgemeine Anleitung einschließlich Backup steht in [nas-deployment.md](nas-deployment.md).

## Aktivierung mit gemeinsamem Passwort

Im NAS-Checkout zunächst die neue Version und die dazugehörigen GHCR-Images bereitstellen.
In `infra/.env.nas` lokal folgende Werte ergänzen:

```dotenv
COMPOSE_PROFILES=beta
BETA_ACCESS_MODE=password
BETA_PUBLIC_ENABLED=0
BETA_AUTH_PASSWORD=<eigenes langes zufälliges Passwort, mindestens 12 Zeichen>
BETA_PROXY_SECRET=<separates zufälliges Geheimnis, mindestens 32 Zeichen>
BETA_PUBLIC_ORIGIN=https://beta.example.org
BETA_BIND=127.0.0.1
BETA_PORT=3001
```

Die Platzhalter müssen ersetzt werden; keine echten Secrets committen. Zwei getrennte Zufallswerte
lassen sich lokal jeweils mit `openssl rand -hex 32` erzeugen. Das Proxy-Geheimnis gilt nur für die
interne Verbindung zwischen Beta-Frontend und Backend; das Testerpasswort ist ein anderer Wert.
Die technische Basic-Auth-Kennung lautet immer `beta`. Private Zugangsdaten funktionieren damit
nicht. Der Beta-Container erhält eine explizite Auswahl von Umgebungsvariablen; weder das private
Env-File noch das Runtime-Secrets-Volume oder der Docker-Socket werden eingebunden.

```sh
cd /volume1/docker/boerse-dashboard-web/infra
./backup-postgres.sh
./update-nas.sh
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta ps frontend frontend-beta
```

`APP_BETA_MODE=1` wird im Beta-Service serverseitig gesetzt; privat gilt `0`. Die Einstellung wird
zur Laufzeit gelesen und als Boolean an Client-Komponenten weitergereicht. Ein gemeinsamer Build
reicht aus. Bei fehlendem Passwort, fehlendem Proxy-Geheimnis oder ungültigem Zugangsmodus liefert
die Beta einen Fehler (503), ohne einen öffentlichen Zugang zu öffnen.

Für ein zunächst lokales Testen ohne DNS kann `BETA_PUBLIC_ORIGIN` leer bleiben. Zugriff vom eigenen
Rechner dann beispielsweise über `ssh -L 3001:127.0.0.1:3001 NAS-BENUTZER@NAS-HOST`, anschließend
`http://127.0.0.1:3001`. Für die externe Freigabe HTTPS und die tatsächliche externe Origin konfigurieren.

## Synology-HTTPS-Reverse-Proxy

Eine eigene Beta-Domain auf die NAS zeigen lassen. Eine separate Reverse-Proxy-Regel anlegen:
Quelle `HTTPS`, Host `beta.example.org`, Port `443`; Ziel `HTTP`, Host `127.0.0.1`, Port `3001`.
Ein gültiges Zertifikat dieser Domain zuordnen, nur den benötigten HTTPS-Port extern veröffentlichen.
`BETA_PUBLIC_ORIGIN` muss genau der Browser-Origin entsprechen, ohne abschließenden Slash; bei
abweichendem Port gehört dieser dazu. Das schützt die beiden POST-Funktionen vor fremden Origins.
Die Basic-Auth-Challenge des Beta-Frontends und den Authorization-Header durchreichen. Für HTML,
RSC und API keine Reverse-Proxy-Caches aktivieren. Backend-Port 8000, PostgreSQL, Redis und private
Setup-/Admin-Routen bleiben intern. Der Backend-Port muss auf `127.0.0.1` gebunden bleiben.

Der geteilte interne Docker-Netzwerkbereich ist eine Vertrauensgrenze: der bestehende private
Backend-Zugang setzt ein internes Netzwerk voraus. Der Beta-Zugang ist zusätzlich im Backend
beschränkt. Dies ersetzt keine Isolation gegen einen kompromittierten Container oder NAS-Administrator.

## Zugang nur über Link ausdrücklich einschalten

Für einen begrenzten Testerkreis ist der Passwortmodus vorgesehen. Ein öffentlicher Link benötigt
**beide** folgenden Werte, zusätzlich zum gültigen `BETA_PROXY_SECRET`:

```dotenv
BETA_ACCESS_MODE=public
BETA_PUBLIC_ENABLED=1
```

Danach den Beta-Service neu erstellen. Alle anderen Kombinationen bleiben gesperrt. Im öffentlichen
Modus ist die URL selbst kein Geheimnis; jeder Besucher kann die freigegebenen Analysen und die
global begrenzten Berechnungen verwenden. Es werden keine Namen, E-Mail-Adressen, Konten, Profile,
Cookies für Tracking oder persönliche Präferenzen gespeichert. Backend-Request-Logging unterdrückt
Beta-Anfragen. Etwaige Zugriffsprotokolle des Synology-Reverse-Proxys separat deaktivieren oder auf
unbedingt notwendige kurze Aufbewahrung begrenzen; dessen Konfiguration wird durch den Code nicht geändert.

## Aktivieren, deaktivieren und Konfiguration übernehmen

Mit `COMPOSE_PROFILES=beta` wird die Beta auch beim bestehenden `start-nas.sh` und nach Updates
wieder gestartet. Ein einmaliger Start ist alternativ möglich:

```sh
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta up -d frontend-beta
```

Nach Änderungen an Beta-Secrets, Limits oder Origin Backend und Beta-Frontend neu erstellen:

```sh
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta up -d --force-recreate backend frontend-beta
```

Zum dauerhaften Deaktivieren zuerst `beta` aus `COMPOSE_PROFILES` entfernen, danach:

```sh
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta stop frontend-beta
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta rm -f frontend-beta
```

Keine Volumes entfernen. Bereits laufende Aktienjobs beenden ihre gezielte Marktdatenaktualisierung
im gemeinsamen Worker. Andere Dienste bleiben aktiv. Der private Setup-Button „Dienste neu starten“
berücksichtigt den Beta-Container, wenn vorhanden. Ein bloßer Neustart übernimmt keine geänderte
Compose-Umgebung; dafür ist das obige `up --force-recreate` erforderlich.

## Gemeinsame Updates und Rollback

Der vorhandene Git-/GHCR-Prozess bleibt unverändert der Einstieg:

```sh
git -C /volume1/docker/boerse-dashboard-web pull --ff-only
cd /volume1/docker/boerse-dashboard-web/infra
./update-nas.sh
```

Das Skript aktiviert das Beta-Profil auch dann, wenn `frontend-beta` bereits läuft. Es zieht beide
Frontends mit demselben `IMAGE_TAG`, führt genau einen normalen Alembic-Migrationslauf aus und
behält die vorhandenen Journal-Backfills bei. Es startet keine zweite Initialisierung, Worker oder
Scheduler. `--remove-orphans` wird nicht verwendet, damit eine aktive Beta nicht verloren geht.
Für reproduzierbare Updates einen gemeinsamen Commit-SHA-Tag statt eines veränderlichen `latest`
verwenden. Vor einem Rollback Backup und bisher verwendeten Image-Tag aufbewahren.

Rollback: `IMAGE_TAG=<bisheriger kompatibler Commit-SHA>` in `.env.nas` setzen, anschließend:

```sh
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta pull
docker compose --env-file .env.nas -f docker-compose.nas.yml --profile beta up -d
```

 Beide Frontends wechseln zusammen. Diese Änderung hat keine Datenbankmigration;
bei anderen, inkompatiblen Versionssprüngen bleibt eine Datenbankwiederherstellung erforderlich.
Beim Rollback auf eine Version ohne Beta-Gate die Beta zuvor stoppen und entfernen.

## Grenzen und NAS-Last

Alle Limits sind global für den anonymen Testerkreis, ohne IP-/Benutzerprofile. Konfiguration in
`.env.nas`, Anwendung im gemeinsamen Backend:

| Variable | Standard | Wirkung |
| --- | ---: | --- |
| `BETA_REFRESH_MAX_ACTIVE` | 1 | Neue Beta-Aktienjobs, laufend oder wartend, zusammen |
| `BETA_REFRESH_COOLDOWN_SECONDS` | 300 | Wiederholungssperre je Ticker, auch manuell |
| `BETA_AUTO_COOLDOWN_SECONDS` | 21600 | Automatische Wiederholung je Ticker frühestens nach 6 Stunden |
| `BETA_REFRESH_REQUESTS_PER_MINUTE` | 12 | Globale Refresh-Aufrufe einschließlich Zusammenführung |
| `BETA_STATUS_TTL_SECONDS` | 7200 | Gültigkeit eines kurzlebigen Status-Handles und seiner Berechtigung |
| `BETA_PAUSE_WHEN_PRIVATE_BUSY` | true | Neue Beta-Jobs pausieren bei privaten aktiven Jobs |
| `BETA_PREVIEW_REQUESTS_PER_MINUTE` | 10 | Globale freie Verkaufsprüfungen |
| `BETA_PREVIEW_MAX_ACTIVE` | 1 | Gleichzeitige Verkaufsberechnungen |
| `BETA_READ_REQUESTS_PER_MINUTE` | 240 | Globale API-Aufrufe einschließlich Status und POST |
| `BETA_READ_MAX_ACTIVE` | 2 | Gleichzeitig berechnete, noch nicht gecachte GET-Antworten |
| `BETA_MEMORY_LIMIT` | 384m | Speichergrenze ausschließlich für den zusätzlichen Frontend-Container |

Vorbereitete öffentliche GET-Antworten werden 30 Sekunden in Redis geteilt. Cache-Treffer benötigen
keinen Berechnungsslot. Berechnungsslots haben eine 120-Sekunden-Lease; Rate-Counter verfallen nach
65 Sekunden. Formularwerte und Vorschauergebnisse werden nicht gespeichert oder gecacht. Laufende
Jobzuordnungen bleiben bis zum bestätigten Abschluss erhalten, damit ein ausgefallener Worker die
Warteschlangenbegrenzung nicht durch abgelaufene Reservierungen umgehen kann. Sie enthalten nur
technische Ticker-/Jobzuordnungen. Abgeschlossene Statusberechtigungen verfallen nach zwei Stunden.

Die Beta hat kein permanentes Markt-Polling und kein Focus-Refetch. Anfragen mehrerer Panels
eines Browsers laufen nacheinander, mit maximal 32 wartenden Client-Anfragen. Nur ein aktiv verfolgter
Aktienjob wird alle sechs Sekunden abgefragt; nach Abschluss oder Statusfehler endet das Polling.
Aktuelle Kurs-/Fundamental-/RS-Line-Daten starten keinen automatischen Job. Je Ansicht gibt es nur
einen Auto-Versuch. Ein laufender geeigneter Einzelaktienjob wird gemeinsam verfolgt. Nach Abschluss
werden Kursdaten, Fundamentals, RS, technische/fundamentale Bewertung, Änderungen, Screening und
Vergleiche neu abgefragt; der gemeinsame Beta-Cache wird invalidiert.

Manuelles „Aktie aktualisieren“ verwendet immer das feste Profil für genau einen bekannten Ticker:
incrementelle Preise, Fundamentals, Einzelaktien-RS-Line und gespeicherte Bewertung. Keine globale
RS-Perzentilberechnung, keine 13F-Komplettimporte, kein Universums-/Portfoliojob. Gemeinsame
Provider-Limits und Worker gelten weiter. Beta-Jobs erhalten niedrigere Queue-Priorität; laufende
Arbeit wird nicht unterbrochen. Falls ein privater Einzelaktienjob bereits läuft, darf die Beta dessen
bereinigten Status verfolgen, erhält jedoch keine echten Job-IDs, Payloads, Schritte oder Logs.

RAM und Redis regelmäßig kontrollieren:

```sh
docker stats --no-stream
docker compose --env-file .env.nas -f docker-compose.nas.yml exec redis redis-cli INFO memory
docker compose --env-file .env.nas -f docker-compose.nas.yml logs --tail=100 interactive-worker
```

Den tatsächlichen zusätzlichen Speicherbedarf unter dem vorgesehenen Testerkreis messen; 384 MiB
ist eine Containergrenze, keine Messung des Verbrauchs auf einer DS220+. Bei Neustarts wegen
Speichermangel zuerst Last und OOM-Zustand prüfen. Redis verwendet `noeviction`; bei Ausfall oder
Speichermangel werden Beta-Anfragen geschlossen abgewiesen. Limits dann nicht ohne Ursachenprüfung
anheben. Im privaten Dashboard Jobs mit `requested_by=beta` beziehungsweise Payload-Quelle `beta`
prüfen. Redis-Schutzschlüssel bei laufenden oder unklaren Jobs niemals blind löschen.

## Freie Verkaufsprüfung

`/sell-check` verwendet dieselbe `ManualSellPreview`-Komponente und Sell Engine. Die Beta sendet
nur an `POST /api/v1/beta/sell/preview`. Ticker, positiver endlicher Einstiegspreis, Einstiegsdatum
bis einschließlich heute sowie eine unterstützte Währung werden serverseitig geprüft; zusätzliche
Felder werden abgewiesen. Unterstützt: USD, EUR, GBP, CHF, JPY, CAD, AUD, HKD.
Die Währungsumrechnung benötigt die vorhandenen Marktdaten; fehlende Kurse/Wechselkurse führen zu
einer verständlichen Fehlermeldung. Es werden keine Provider-Downloads durch die Vorschau gestartet.

Der vollständige Aufruf übergibt die Eingaben ausdrücklich, erzeugt eine synthetische Position mit
einer Stückzahl von 1 sowie leere Tranche-/Empfehlungszustände und nutzt `persist_state=False`.
Private Positionen, Einstiegspreise, manuelle Stopps und gespeicherte Sell-Zustände werden nicht
abgerufen. Die Antwort projiziert ausschließlich Kurs, Formular-Einstieg, Performance, Empfehlung,
Signalgruppen und Schwellenwerte. Auch ein Ticker im echten Depot ist unabhängig. Der normale
Verkaufsmonitor und alle übrigen Sell-Endpunkte sind in der Beta gesperrt.

## Freigabeliste und Sicherheitsprüfung

Die kanonische Liste liegt in `frontend/src/lib/beta/api-policy.json` und wird in das Backend-Image
kopiert. Es gibt keine pauschale Freigabe ganzer API-Bereiche. Neben den dort einzeln aufgeführten
Markt-/Aktien-/Industry-Group-GETs sind ausschließlich folgende Ausnahmen erlaubt:

- `POST /api/v1/beta/stocks/{ticker}/refresh`: Body nur `mode: auto|manual`, Jobtyp/Payload serverseitig.
- `GET /api/v1/beta/stock-refresh/{beta_handle}/status`: zusätzlicher kurzlebiger Capability-Header,
  nur bereinigter Status des durch tickerbezogene Beta-Zulassung bekannten Jobs.
- `POST /api/v1/beta/sell/preview`: reine, begrenzte Vorschau.

`GET beta/home` und `GET beta/stocks/{ticker}/freshness` sind ebenfalls ausdrücklich freigegeben.
Private Home-/Portfolio-/Workspace-/Journal-/Sell-/Settings-/Setup-/Job-/Export-APIs, unbekannte
Endpunkte und alle übrigen Schreibmethoden sind gesperrt. Das gilt auch für HTML, RSC, direkte URLs,
Dateiendungen, Server Actions und manipulierte Rollenheader. Ein eigener Backend-Check begrenzt die
serverseitige Beta-Proxy-Kennung. Browser dürfen diese Kennung weder setzen noch erfahren.
Request-Bodies sind auf 4096 Bytes begrenzt, Query-Parameter explizit freigegeben und begrenzt.
Fehlerantworten enthalten keine Provider-Logs oder Systemdetails.

Vor externer Freigabe auf der eigenen NAS prüfen:

1. Passwortlose Anfrage erhält 401; ohne vollständige Konfiguration 503. Private Credentials öffnen
   die Beta nicht. Öffentlicher Modus funktioniert nur nach beiden ausdrücklichen Schaltern.
2. `/portfolio`, `/sell-monitor`, `/settings`, `/setup`, `/jobs` und `/api/v1/home` liefern in der
   Beta 403, auch als RSC-Anfrage. Direkte Backend-/DB-/Redis-Ports sind extern unerreichbar.
3. Alle sechs Analysebereiche anzeigen, Datenstände prüfen. Bekannte aktuelle Aktie öffnen;
   veraltete Aktie und manuellen Refresh testen. Zwei Browser teilen den laufenden Job.
4. Eigenen Formulareinstieg eines Depot-Tickers prüfen; keine Stückzahl/privaten Stops sichtbar.
   Portfolio und privater Verkaufsmonitor bleiben unverändert.
5. NAS-RAM, OOM-Zustand und Worker-/Provider-Last unter mehreren Testern kontrollieren. Privates
   Dashboard, private Jobs, Setup-Neustart und gemeinsames Update mit beiden Frontends testen.
6. HTTPS-Zertifikat, korrekte Origin, Basic-Auth-Weitergabe und Reverse-Proxy-Protokollierung prüfen.

Automatisierte Tests und ihre Grenzen stehen in [beta-implementation-report.md](beta-implementation-report.md).
