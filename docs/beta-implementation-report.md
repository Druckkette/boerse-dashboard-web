# Abschlussbericht: gemeinsame NAS-Beta

Stand: 8. Oktober 2026. Implementiert im lokalen Branch `feat/nas-beta-dashboard` des Repositorys
`Druckkette/boerse-dashboard-web`. Keine Änderungen, Deployments oder Neustarts auf einer laufenden
Synology; keine Secrets, Benutzerkonten, Datenbanken, Worker, Scheduler oder Hostingdienste ergänzt.
Der Code ist lokal zur Prüfung vorhanden; GitHub/GHCR wurden nicht veröffentlicht.

## 1. Umsetzung und geänderte Dateien

Die vollständige Dateiliste steht am Ende. Die Änderungen betreffen die gemeinsame Zugriffspolitik,
Frontend-Proxy und Authentifizierung, minimale Beta-Datenausgaben, Redis-Zulassung, vorhandene
Einzelaktienjobs, wiederverwendete UI, NAS-Compose/Update, Tests und Dokumentation. Die Bewertungs-
und Scoringmodelle werden weiterverwendet; es gibt keine globalen Modell-/Performanceänderungen.
Vorhandene unversionierte Arbeitsverzeichnisse `industry_group_analysis/` und `output/` bleiben erhalten.

## 2. Modus und Zugang

`APP_BETA_MODE=1` wird serverseitig zur Laufzeit gelesen; privat `0`. Beide Frontends benutzen denselben
Build und dasselbe Docker-Image. Ein Provider übergibt nur den Modus an Client Components. Die Beta
hat sechs Navigationsziele: Start, Markt, Sektoren, Industry Groups, Aktien und `/sell-check`.
Die separate Startseite liest Marktampel/Marktlage/Kennzahlen, vorbereitete Top-3-Aktien und führende
Gruppen. Sie nutzt die vorhandenen Darstellungskomponenten und die Schnellsuche im Header, ohne
private Home-/Portfolio-/Watchlist-Abfragen.

Standard ist Basic Auth mit technischer Kennung `beta` und einem gemeinsamen Passwort. Private
Authentifizierung bleibt unabhängig. Öffentlich ist die Beta nur mit `BETA_ACCESS_MODE=public` **und**
`BETA_PUBLIC_ENABLED=1`. Fehlende/falsche Konfiguration bleibt geschlossen, einschließlich fehlender
interner Proxy-Kennung. Es entstehen keine individuellen Konten, Profile oder Tracking-Daten.

## 3. Gezielter Aktienrefresh

Die Beta akzeptiert nur einen validierten, vorhandenen Instrument-Ticker und `mode=auto|manual`.
Der Backend-Service konstruiert den festen `refresh_stock_detail`-Payload, nutzt dieselbe Queue
`interactive` und denselben Worker. Kursdaten werden inkrementell aktualisiert; Fundamentals und
RS-Line für diese Aktie werden erneuert, anschließend die gespeicherte Bewertung über den bestehenden
Screener mit `only_tickers=[ticker]` berechnet. Andere gespeicherte Aktienbewertungen und globale
Screening-/Top-Daily-Veröffentlichungen werden dabei nicht neu aufgebaut.

Freshness verwendet die bestehende Bewertungs-/Abhängigkeitslogik. Bei aktuellen reparierbaren
Abhängigkeiten entsteht kein automatischer Job. Veraltete globale RS-Perzentile oder quartalsweise
13F-Daten bleiben Aufgabe des vorhandenen Schedulers; die Beta startet dafür keine Globaljobs.
Je Ansicht erfolgt höchstens ein Auto-Versuch, ergänzt durch eine globale tickerbezogene Sperre.

Redis-Zulassung und ein gemeinsam mit privaten Refreshes verwendeter Ticker-Mutex verhindern
mehrfache Beta-Dispatches. Ein passender laufender Aktienjob wird verfolgt. Die Beta erhält nur einen
zufälligen öffentlichen Handle samt kurzlebiger Berechtigung. Echte Job-IDs, Payload, interne Schritte,
Systemmeldungen, Ergebnisse und Logs werden nicht ausgegeben. Eine Statusabfrage fremder Jobs
ist ausgeschlossen. Die Beta prüft private Jobkapazität ausschließlich lesend; sie löst auch keine
allgemeine Bereinigung/Statusänderung veralteter fremder Jobs aus.

Nach Erfolg invalidiert das Frontend alle betroffenen Kurs-/RS-/Fundamental-/Bewertungs-/Ranking-/
Screening-/Vergleichsqueries; der Backend-Beta-Cache erhält eine neue Generation. Fortschritt wird
alle sechs Sekunden nur für den laufenden Job abgefragt, auch wenn zwischen Aktientabs gewechselt
wird. Providerfehler werden bereinigt und bestehende Bewertungen nicht durch unvollständige
Erfolgsmeldungen als aktuell dargestellt.

## 4. Unabhängige freie Verkaufsprüfung

Die neue Seite verwendet die bestehende `ManualSellPreview`-Komponente. Die Beta greift ausschließlich
auf den eigenen `POST beta/sell/preview` zu. Die komplette Aufrufkette der bestehenden
`preview_manual_sell_decision` wurde geprüft: eigene Formulareingaben, synthetische Stückzahl 1,
Marktdaten, ausdrückliche manuelle Marktdaten-Defaults, leere Tranche-Historie/neuer Empfehlungszustand
und `persist_state=False`. Kein Rückgriff auf Positionen, gespeicherte Einstiegspreise, Stopps oder
Sell-Zustände. Globale Bewertungsregeln bleiben dieselben wie privat.

Die bereits berechneten Metrics werden innerhalb dieses Aufrufs wiederverwendet, anstatt sie dreimal
zu berechnen. Die Beta projiziert ausschließlich die benötigten Anzeige- und Signalwerte; Stückzahl,
private Konfiguration und Zustandsobjekte werden nicht ausgeliefert. Acht Währungen werden serverseitig
validiert; Preis muss positiv/endlicher Wert sein, Datum gültig und nicht zukünftig, Zusatzfelder verboten.
Formularwerte und Ergebnisse werden weder gespeichert noch gecacht. Zwei echte PostgreSQL-Tests
mit/ohne private NVDA-Position vergleichen sämtliche öffentlichen Datenbanktabellen vor/nach Vorschau:
keine Veränderungen und kein privater Einstieg/Stop/Stückzahl im Ergebnis.

## 5. Erlaubte und gesperrte Endpunkte

Die 30 expliziten Regeln stehen in [api-policy.json](../frontend/src/lib/beta/api-policy.json).
Sie werden unverändert ins Backend-Image übernommen. Freigegeben sind die einzeln aufgeführten
GETs für Marktübersicht/Ampel/Breite/Frühwarn-/Volatilitätsanalysen/Sektoren, Aktien-Suche/Rankings/
Screening/Vergleich/Kurse/RS/Bewertungen/Änderungen/Fundamentals/13F sowie Gruppen-Rankings/
Mitglieder/Drilldown. Ergänzt: Beta-Home und tickerbezogene Freshness.

Die drei technisch begrenzten Ausnahmen lauten:

| Methode | Pfad unter `/api/v1/` | Grenze |
| --- | --- | --- |
| POST | `beta/stocks/{ticker}/refresh` | Fester Einzelaktienjob, nur Modus auswählbar |
| GET | `beta/stock-refresh/{beta_handle}/status` | Capability, minimale sichere Statusprojektion |
| POST | `beta/sell/preview` | Zustandslose, validierte und begrenzte Berechnung |

Alle anderen Schreibendpunkte und unbekannten Routen bleiben gesperrt. Insbesondere normale Jobs,
Jobabbruch, privates Home, Portfolio, Workspace, Journal, Sell-Monitor, normaler Sell-Preview,
Settings, Setup, API-Schlüssel, Mappings, Exporte/PDFs und Administrative Aktionen. Die interne
statische Industry-Group-Diagnoseroute ist trotz ähnlichem dynamischem Gruppenpfad ausdrücklich
ausgeschlossen. Ein Test gleicht alle statischen Backend-Routen mit der expliziten Freigabeliste ab.

Proxy und Route Handler kontrollieren beide serverseitig. Kein Vertrauen in Browser-Rollen-/Beta-
Header. Backend-Middleware begrenzt zusätzlich die serverseitige Beta-Kennung. Private Page-URLs,
RSC, Dateiendungen und Server Actions können die Beta-Grenze nicht umgehen. Browser verwenden
immer die gemeinsame Frontend-API-Route, keine Build-Time-Backend-URL. POST benötigt dieselbe
Origin, vorzugsweise die konfigurierte externe HTTPS-Origin.

## 6. Sicherheit und Last

Konservativer Standard: 1 neuer Beta-Aktienjob aktiv/wartend, 300 Sekunden Ticker-Cooldown,
6 Stunden automatische Wiederholungssperre, 12 Refresh-Anfragen/min, 10 Vorschauen/min und
1 Vorschau gleichzeitig. Höchstens 2 nicht gecachte GET-Berechnungen gleichzeitig, 240 API-Aufrufe/min
insgesamt. Alle Werte sind begrenzt konfigurierbar und global für den anonymen Testerkreis.

Private Arbeit hat Zulassungsvorrang; standardmäßig pausiert die Beta bei privaten aktiven Jobs.
Niedrigere Celery-Priorität gilt zusätzlich für wartende Beta-Jobs. Laufende Jobs sind nicht präemptiv.
Provider-Rate-Limits und Worker-Concurrency bleiben erhalten. Kein weiterer Worker oder Queue.

Öffentliche GET-Daten werden 30 Sekunden in Redis geteilt. Formularwerte bleiben ungecacht.
Keine automatische Markt-/Ranking-Dauerabfrage oder Focus-Refetch in der Beta. API-Anfragen
mehrerer Panels desselben Browsers werden nacheinander ausgeführt (höchstens 32 wartend), um
nicht schon mit einer Ansicht die globalen Berechnungsslots zu überlaufen. Bodies maximal
4096 Bytes, Query-Schlüssel explizit begrenzt, unbekannte Parameter blockiert. Allgemeine Fehler,
Quell-Metadaten und echte Job-IDs werden aus öffentlichen Antworten entfernt. Redis-Ausfall/
Speichermangel führt zu geschlossener Beta-Zulassung. Technische Statusberechtigungen verfallen
nach 2 Stunden, Counter nach 65 Sekunden, Rechen-Leases nach 120 Sekunden. Aktive Zuordnungen
bleiben bis zu einem bestätigten Abschluss, um Überlast durch abgelaufene Reservierungen zu verhindern.
Die NAS-Anleitung beschreibt Speicherung, Kontrolle und Betriebsgrenzen ausführlich.

## 7. Qualitätssicherung

Alle folgenden Prüfungen wurden lokal ausgeführt; CI ist entsprechend erweitert, noch nicht auf GitHub ausgeführt.

| Prüfung | Ergebnis |
| --- | --- |
| Backend Ruff (`app`, `tests`) | Bestanden |
| Gesamte Backend-Pytest-Suite | 1.109 bestanden, 22 PostgreSQL-Tests separat ausgeführt |
| Beta-API mit echtem isoliertem Redis 7 | 75 bestanden |
| PostgreSQL 16: alle Alembic-Migrationen + Integration | 22 bestanden |
| Frontend ESLint / TypeScript | Bestanden |
| Frontend Node-Tests | 38 bestanden |
| Playwright gegen denselben Standalone-Produktionsbuild in drei Modi | 6 bestanden |
| Next.js-Produktionsbuild | Bestanden |
| Backend- und Frontend-Dockerbuild | Bestanden |
| Docker-Smoke: ein identisches Frontend-Image für private/Beta-Container | Authentifizierung und private Page-/API-Sperren bestanden |
| Backend-Image: kanonische Policy enthalten und ausführbar | Bestanden |
| Compose-Struktur und Update-/Entrypoint-Regression | 4 automatisierte Tests bestanden |
| `git diff --check` / Shell-Syntax | Bestanden |
| `npm audit --omit=dev` | 0 bekannte Meldungen |

Die Tests decken aktuelle/veraltete Aktien, Auto-/Manuell-Refresh, sechs konkurrierende identische
Anfragen, bestehende private Aktienjobs, belegte Worker-Kapazität, Providerfehler, Fortschritt,
Bewertungsreload, Payload-Injection, Job-Flooding, Statusberechtigungen, TTLs, Cache, Redis-Ausfall,
private Routen, HTML/RSC/Exports/Server Actions, Auth-Fail-Closed und Origin-Prüfung ab. Verkaufs-
prüfungen werden für Aktien mit/ohne private Position, acht Währungen und ungültige Eingaben geprüft.
Der Browser bestätigt alle sechs Navigationsbereiche und die Darstellung der drei Signalgruppen.
Die bisherige Backend-Suite deckt weiterhin Portfolio, Sell Engine, Journal, Jobs, Setup, Scheduler,
Marktdaten und Importfunktionen ab. Testcontainers wurden ausschließlich lokal und ohne NAS-Daten verwendet.

## 8. Synology-Start

Vollständige Anleitung: [nas-beta.md](nas-beta.md). Lokal auf der NAS ein eigenes gemeinsames
Testerpasswort und separates Proxy-Geheimnis setzen, `COMPOSE_PROFILES=beta` ergänzen und nach
Bereitstellung dieser Version `infra/update-nas.sh` ausführen. Standardport ist `127.0.0.1:3001`;
extern ausschließlich über die eigene Synology-HTTPS-Reverse-Proxy-Regel veröffentlichen.
Ohne Secrets bleibt die Beta geschlossen. Ein passwortloser Link erfordert die beiden ausdrücklichen
Public-Schalter. Zum Deaktivieren Profil entfernen, nur `frontend-beta` stoppen/entfernen.

## 9. Weitere Updates

Gemeinsamer Git-/GHCR-Prozess und gemeinsamer `IMAGE_TAG`. Das Update-Skript erhält eine bereits
aktive Beta, zieht beide Frontends mit demselben Tag, migriert einmal und belässt die vorhandenen
Backfills. Keine zweite Initialisierung, Scheduler oder Worker; kein `--remove-orphans`.
Der private Setup-Neustart berücksichtigt eine vorhandene Beta. Rollback bleibt über einen gemeinsamen
kompatiblen Commit-SHA-Tag möglich. Diese Änderung fügt keine Schema-Migration hinzu.

## 10. Risiken und verbleibende Betriebsprüfungen

- Synology-HTTPS, Zertifikat, Proxy-Header, tatsächlicher RAM-Verbrauch und OOM-Verhalten müssen
  bei der späteren Bereitstellung auf der DS220+ geprüft werden. Die zusätzliche Frontend-Grenze ist
  384 MiB; lokal erfolgreiche Tests sind keine Messung auf der NAS.
- Live-Provider, echter langlaufender Celery-Betrieb und private Setup-Neustarts wurden nicht auf der
  NAS ausgeführt. Browser-/Worker-Tests verwenden deterministische Marktdaten/Provider-Antworten;
  Redis und PostgreSQL wurden zusätzlich echt geprüft. GitHub-CI und GHCR-Veröffentlichung stehen aus.
- Redis ist die vorhandene gemeinsame Sicherheits-/Broker-Infrastruktur. Bei Störungen sperrt die
  Beta; unklare aktive Reservierungen erst nach Jobprüfung durch den Betreiber behandeln.
- Bestehende globale RS-/13F-Daten können veraltet sein und werden durch den Einzelaktienjob nicht
  global erneuert. Die Ansicht zeigt deren Freshness; der bestehende Scheduler liefert diese Daten.
- Alle Beta-Tester teilen globale Limits und das Passwort. Ein missbräuchlicher Tester kann die
  begrenzte Beta-Kapazität belegen; es gibt absichtlich keine individuellen Konten oder Nutzerprofile.
- Der gemeinsame interne Backend-/Docker-Netzwerkbereich bleibt eine Vertrauensgrenze. Keine
  Abwehr eines kompromittierten Containers oder NAS-Administrators wird behauptet.
- Das vollständige npm-Audit meldet noch 5 hohe Entwicklungsabhängigkeits-Meldungen über
  `braces`/`micromatch`/`fast-glob` im ESLint-Werkzeugbaum. Produktionsabhängigkeiten sind meldungsfrei;
  kein inkompatibles `npm audit fix --force` durchgeführt. Vor Veröffentlichung erneut prüfen.
- Bestehende Deprecation-Warnungen von Starlette/httpx und Pandas bleiben sichtbar; keine Testfehler.
  Synology-Zugriffsprotokolle außerhalb der App separat datensparsam konfigurieren.

Next.js und die zugehörige ESLint-Konfiguration wurden auf 16.3.8 und Sharp auf 0.35.5 aktualisiert.
Die Sicherheitskorrekturen sind in den [Next.js-Advisories](https://github.com/advisories/GHSA-3w37-wq28-93x7)
und im [Sharp-Advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w) dokumentiert.

## Vollständige geänderte/neue Dateiliste

- [.github/workflows/ci.yml](../.github/workflows/ci.yml)
- [.gitignore](../.gitignore)
- [backend/app/api/v1/beta.py](../backend/app/api/v1/beta.py)
- [backend/app/api/v1/router.py](../backend/app/api/v1/router.py)
- [backend/app/beta_policy.py](../backend/app/beta_policy.py)
- [backend/app/core_config.py](../backend/app/core_config.py)
- [backend/app/domain/sell/service.py](../backend/app/domain/sell/service.py)
- [backend/app/main.py](../backend/app/main.py)
- [backend/app/middleware/beta_access.py](../backend/app/middleware/beta_access.py)
- [backend/app/middleware/request_context.py](../backend/app/middleware/request_context.py)
- [backend/app/repositories/jobs.py](../backend/app/repositories/jobs.py)
- [backend/app/services/beta.py](../backend/app/services/beta.py)
- [backend/app/services/jobs.py](../backend/app/services/jobs.py)
- [backend/app/workers/tasks/refresh_stock_detail.py](../backend/app/workers/tasks/refresh_stock_detail.py)
- [backend/pyproject.toml](../backend/pyproject.toml)
- [backend/tests/api/test_beta_api.py](../backend/tests/api/test_beta_api.py)
- [backend/tests/integration/test_beta_preview_readonly.py](../backend/tests/integration/test_beta_preview_readonly.py)
- [backend/tests/test_beta_deployment.py](../backend/tests/test_beta_deployment.py)
- [docs/beta-implementation-report.md](../docs/beta-implementation-report.md)
- [docs/nas-beta.md](../docs/nas-beta.md)
- [docs/nas-deployment.md](../docs/nas-deployment.md)
- [frontend/docker-entrypoint.sh](../frontend/docker-entrypoint.sh)
- [frontend/next-env.d.ts](../frontend/next-env.d.ts)
- [frontend/package-lock.json](../frontend/package-lock.json)
- [frontend/package.json](../frontend/package.json)
- [frontend/playwright.config.ts](../frontend/playwright.config.ts)
- [frontend/src/app/api/v1/[...path]/route.ts](../frontend/src/app/api/v1/[...path]/route.ts)
- [frontend/src/app/layout.tsx](../frontend/src/app/layout.tsx)
- [frontend/src/app/page.tsx](../frontend/src/app/page.tsx)
- [frontend/src/app/sell-check/page.tsx](../frontend/src/app/sell-check/page.tsx)
- [frontend/src/app/stocks/[ticker]/page.tsx](../frontend/src/app/stocks/[ticker]/page.tsx)
- [frontend/src/components/beta-mode-provider.tsx](../frontend/src/components/beta-mode-provider.tsx)
- [frontend/src/components/query-provider.tsx](../frontend/src/components/query-provider.tsx)
- [frontend/src/components/ui/app-shell.tsx](../frontend/src/components/ui/app-shell.tsx)
- [frontend/src/components/ui/header-tools.tsx](../frontend/src/components/ui/header-tools.tsx)
- [frontend/src/features/home/beta-home-dashboard.tsx](../frontend/src/features/home/beta-home-dashboard.tsx)
- [frontend/src/features/home/home-dashboard.tsx](../frontend/src/features/home/home-dashboard.tsx)
- [frontend/src/features/market/breadth-chart-panel.tsx](../frontend/src/features/market/breadth-chart-panel.tsx)
- [frontend/src/features/market/deep-analysis-panel.tsx](../frontend/src/features/market/deep-analysis-panel.tsx)
- [frontend/src/features/market/market-ampel-panel.tsx](../frontend/src/features/market/market-ampel-panel.tsx)
- [frontend/src/features/market/market-breadth-overview-panel.tsx](../frontend/src/features/market/market-breadth-overview-panel.tsx)
- [frontend/src/features/market/market-diagnostics-panel.tsx](../frontend/src/features/market/market-diagnostics-panel.tsx)
- [frontend/src/features/market/market-overview-panel.tsx](../frontend/src/features/market/market-overview-panel.tsx)
- [frontend/src/features/market/market-risk-sections-panel.tsx](../frontend/src/features/market/market-risk-sections-panel.tsx)
- [frontend/src/features/market/query-timing.ts](../frontend/src/features/market/query-timing.ts)
- [frontend/src/features/market/volatility-panel.tsx](../frontend/src/features/market/volatility-panel.tsx)
- [frontend/src/features/sell/manual-sell-preview.tsx](../frontend/src/features/sell/manual-sell-preview.tsx)
- [frontend/src/features/stocks/beta-stock-detail-actions.tsx](../frontend/src/features/stocks/beta-stock-detail-actions.tsx)
- [frontend/src/features/stocks/institutional-13f-panel.tsx](../frontend/src/features/stocks/institutional-13f-panel.tsx)
- [frontend/src/features/stocks/rs-ranking-panel.tsx](../frontend/src/features/stocks/rs-ranking-panel.tsx)
- [frontend/src/features/stocks/stock-assessment-panel.tsx](../frontend/src/features/stocks/stock-assessment-panel.tsx)
- [frontend/src/features/stocks/stock-assessment-ranking-panel.tsx](../frontend/src/features/stocks/stock-assessment-ranking-panel.tsx)
- [frontend/src/features/stocks/stock-compare-panel.tsx](../frontend/src/features/stocks/stock-compare-panel.tsx)
- [frontend/src/features/stocks/stock-detail-actions.tsx](../frontend/src/features/stocks/stock-detail-actions.tsx)
- [frontend/src/features/stocks/stock-detail-tabs.tsx](../frontend/src/features/stocks/stock-detail-tabs.tsx)
- [frontend/src/features/stocks/stock-fundamentals-panel.tsx](../frontend/src/features/stocks/stock-fundamentals-panel.tsx)
- [frontend/src/features/stocks/top-daily-stocks-panel.tsx](../frontend/src/features/stocks/top-daily-stocks-panel.tsx)
- [frontend/src/lib/api/client.ts](../frontend/src/lib/api/client.ts)
- [frontend/src/lib/beta/api-policy.json](../frontend/src/lib/beta/api-policy.json)
- [frontend/src/lib/beta/auth.ts](../frontend/src/lib/beta/auth.ts)
- [frontend/src/lib/beta/policy.ts](../frontend/src/lib/beta/policy.ts)
- [frontend/src/lib/beta/refresh-state.ts](../frontend/src/lib/beta/refresh-state.ts)
- [frontend/src/lib/beta/request-limiter.ts](../frontend/src/lib/beta/request-limiter.ts)
- [frontend/src/proxy.ts](../frontend/src/proxy.ts)
- [frontend/tests/beta-security.test.mjs](../frontend/tests/beta-security.test.mjs)
- [frontend/tests/e2e/beta.spec.ts](../frontend/tests/e2e/beta.spec.ts)
- [frontend/tests/e2e/fixture_backend.py](../frontend/tests/e2e/fixture_backend.py)
- [frontend/tests/e2e/start-frontend.mjs](../frontend/tests/e2e/start-frontend.mjs)
- [infra/.env.nas.example](../infra/.env.nas.example)
- [infra/Dockerfile.backend](../infra/Dockerfile.backend)
- [infra/docker-compose.nas.yml](../infra/docker-compose.nas.yml)
- [infra/update-nas.sh](../infra/update-nas.sh)
