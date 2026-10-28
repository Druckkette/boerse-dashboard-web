# Unternehmensnachrichten mit Marketaux

Die Aktien-Detailansicht lädt beim Öffnen `GET /api/v1/stocks/{ticker}/news`. Der Backend-Endpunkt
verwendet ausschließlich [Marketaux Financial News](https://www.marketaux.com/documentation).
Es gibt weder Hintergrundscans noch einen zusätzlichen Produktionsdienst, eine neue Abhängigkeit
oder eine Datenbankmigration. Die persistente Speicherung nutzt die bestehende PostgreSQL-Tabelle
`app_settings`. Container-Neustarts setzen Cache und Abrufkontingent nicht zurück.

## Konfiguration

Den dauerhaften Schlüssel als serverseitige Variable `MARKETAUX_API_KEY` im Backend setzen, auf
Synology beispielsweise in der nicht versionierten `infra/.env.nas`. Keinen `NEXT_PUBLIC_`-Namen
verwenden und den Schlüssel weder in Browserformulare noch in Git, Testausgaben oder Logs kopieren.
Die Frontend-Container benötigen den Schlüssel nicht; bei gemeinsamem `env_file` muss ihr
`MARKETAUX_API_KEY` ausdrücklich leer überschrieben werden. Anschließend nur nach bewusster
Produktionsfreigabe die geänderte Backend-Umgebung übernehmen. Der Implementierungstest hinterlegt
keinen temporären Schlüssel auf dem NAS.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `MARKETAUX_API_KEY` | leer | Backend-Schlüssel; ohne Schlüssel erscheint ein sicherer Hinweis. |
| `MARKETAUX_LANGUAGES` | `de,en` | Sprachfilter; eine leere Variable deaktiviert den Filter. |
| `MARKETAUX_DAILY_LIMIT` | `90` | Schutzbudget, konfigurierbar von 1 bis 90 Versuchen in rollierenden 24 Stunden. |
| `MARKETAUX_CACHE_TTL_SECONDS` | `3600` | Gültigkeit erfolgreicher nichtleerer Nachrichtenlisten. |
| `MARKETAUX_EMPTY_TTL_SECONDS` | `600` | Kürzere Gültigkeit gültiger leerer Antworten. |
| `MARKETAUX_FAILURE_BACKOFF_SECONDS` | `300` | Mindestwartefrist nach fehlgeschlagenen Abrufen. |
| `MARKETAUX_REQUEST_TIMEOUT_SECONDS` | `8` | Lese-Timeout; Verbindungsaufbau höchstens 3,05 Sekunden. |
| `MARKETAUX_MIN_MATCH_SCORE` | `10` | Relevanzfilter für beiläufige Unternehmenszuordnungen. |

## Cache, Zusammenfassung und Kontingent

Der Cache berücksichtigt das aufgelöste Anbietersymbol, Sprache, Unternehmenszuordnung und
Relevanzkonfiguration. Eine frische Liste wird ohne externe Anfrage geliefert. Leere gültige
Antworten werden ebenfalls gespeichert. Mehrere gleichzeitige Anfragen derselben Variante werden
über eine PostgreSQL-Advisory-Sperre zusammengefasst; der wartende Aufruf liest anschließend den
gespeicherten Stand. Die Sperre bleibt auf derselben physischen Verbindung über Transaktionsgrenzen
erhalten. Es wird unter der Sperre keine zweite Pool-Verbindung für Kontingent oder Cache benötigt.

Jeder externe Versuch wird unter einer kurzen globalen Datenbanksperre **vor** dem HTTP-Aufruf
dauerhaft reserviert. Auch fehlerhafte Antworten und ein Absturz nach Reservierung zählen. Das
Budget gilt gemeinsam für alle Ticker, Frontends und Backendprozesse. Das rollierende 24-Stunden-
Fenster ist konservativer als ein einzelner täglicher Reset und vermeidet Annahmen über die
Reset-Zeitzone des Anbieters. Die Standardgrenze 90 lässt Abstand zum kostenlosen Tageskontingent
von 100. Außerhalb dieser Anwendung genutzte Aufrufe desselben Schlüssels sind nicht messbar.

Bei erreichtem Budget werden vorhandene Artikel mit ihrem tatsächlichen letzten Aktualisierungs-
zeitpunkt als veraltet zurückgegeben. Fehler verändern diesen Zeitpunkt nicht. Bei HTTP 429 wird
`Retry-After` berücksichtigt; ohne brauchbaren Header gilt eine Wartefrist von 24 Stunden.
Ungültige Schlüssel verursachen eine einstündige Wartefrist, andere Providerfehler mindestens fünf
Minuten. Diese Providerwartefrist gilt auch tickerübergreifend. Ein Schlüsselwechsel hebt nur die
Fehlerwartefrist auf, niemals bereits verbrauchte Reservierungen. Es gibt keine automatischen
HTTP-Wiederholungen oder Redirects. Ohne verlässlichen persistenten Cache/Zähler werden keine
Marketaux-Anfragen gestellt.

## Zuordnung und Datenqualität

Nur bekannte Instrumente werden abgefragt. Die Symbolwahl verwendet zuerst eine ausdrückliche
`marketaux_symbol`-Instrumentmetadatenzuordnung, danach die gespeicherte aktive Symbolzuordnung,
dann `yahoo_symbol` und zuletzt den vorhandenen Ticker. Ausländische Suffixe werden erhalten;
beispielsweise wird `RHM.DE` nicht blind auf das möglicherweise andere Unternehmen `RHM` verkürzt.
Bei bekannten US-Listings werden Klassenaktien wie `BRK-B` auf `BRK.B` normalisiert. Ein fehlendes
oder vom Anbieter nicht unterstütztes Listing kann deshalb korrekt zu null Meldungen führen.

Die Anfrage setzt `symbols`, `filter_entities=true`, `must_have_entities=true`, `group_similar=true`,
`limit=3`, `sort=published_at` und optional `language`. Der Schlüssel wird nur serverseitig an den
festen HTTPS-Endpunkt übergeben. Der Client projiziert keine rohen Providerfehler; auch aktivierte
urllib3-Debugpfade redigieren `api_token`-Querywerte.

Artikel benötigen eine passende Unternehmensentität, gültige Original-URL und einen tatsächlichen,
parsebaren Veröffentlichungszeitpunkt. Match-Scores sind die Providerwerte, keine Prozentsätze oder
Werte von 0 bis 1. Werte unter dem konfigurierten Minimum werden verworfen, außer eine passende
Entität wurde im Titel erkannt oder die Überschrift nennt das zugeordnete Unternehmen ausdrücklich.
Fehlende Scores werden nicht erfunden. Gleiche UUIDs, kanonische URLs und nahezu gleiche Titel
werden zusammengefasst. Verbleibende Artikel werden nach UTC-Veröffentlichungszeit absteigend
sortiert und auf drei begrenzt. Überschriften und Beschreibungen stammen vom Anbieter; es werden
keine KI-Zusammenfassungen oder fehlende Nachrichten ergänzt.

## Tests

Mocktests decken Providerparameter, Datenprojektion, Symbolzuordnung, Reihenfolge, Deduplizierung,
leere Listen, Sprachfilter, Cacheablauf, Parallelzugriffe, Kontingent, Fehlerwartefristen und
Credential-Redaktion ab. Ein separater Integrationstest nutzt ausschließlich eine Datenbank namens
`audit_tests`: Er prüft echte PostgreSQL-Sperren, gemeinsame Kontingentreservierung, Erhalt nach
Verbindungsneustart und das Verhalten eines auf zwei Verbindungen begrenzten Pools.

```sh
cd backend
python -m pytest tests/services/test_stock_news.py tests/data_sources/test_marketaux.py tests/api/test_stock_news_api.py -q
TEST_POSTGRES_URL=postgresql+psycopg://test:test@127.0.0.1:18432/audit_tests python -m pytest tests/integration/test_stock_news_persistence.py -q
```

Echte API-Tests werden ausdrücklich separat und mit wenigen Aufrufen durchgeführt. Ein Schlüssel
darf dabei ausschließlich aus einer nicht versionierten Umgebungsdatei oder der Secret-Verwaltung
gelesen werden. Kein `curl`-Befehl mit Schlüssel in der URL oder Shell-History.
