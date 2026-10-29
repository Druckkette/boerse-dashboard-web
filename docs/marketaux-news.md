# Unternehmensnachrichten mit Marketaux

Die Aktien-Detailansicht lädt beim Öffnen `GET /api/v1/stocks/{ticker}/news`. Der Backend-Endpunkt
verwendet ausschließlich [Marketaux Financial News](https://www.marketaux.com/documentation).
Es gibt weder Hintergrundscans noch einen zusätzlichen Produktionsdienst, eine neue Abhängigkeit
oder eine Datenbankmigration. Die persistente Speicherung nutzt die bestehende PostgreSQL-Tabelle
`app_settings`. Container-Neustarts setzen Cache und Abrufkontingent nicht zurück.

## Konfiguration

Den dauerhaften Schlüssel im **privaten Dashboard unter Setup → API-Zugänge im Setup pflegen →
API & Datenquellen → Marketaux API Key** eintragen und oben „Speichern“ wählen. Das vorhandene
Setup-Formular zeigt den neuen Zugang automatisch aus der Backend-Konfiguration an. Alternativ bleibt
**Einstellungen → Daten & System → Aktiennachrichten · Marketaux** verfügbar. Das geschützte Formular sendet ihn an die eigene
Backend-API, die ihn dauerhaft in PostgreSQL speichert. Antworten enthalten anschließend nur den
Konfigurationsstatus und eine vollständige konstante Maskierung, niemals Präfix oder Endzeichen.
Jeder Nachrichtenabruf liest den aktuellen gespeicherten Wert; ein Schlüsselwechsel benötigt keinen
Container-Neustart und setzt weder Cache noch Abrufbudget zurück. Die Beta hat keinen Zugriff auf
die Secret-Einstellungen. Nachrichten erscheinen dagegen im Bereich **Aktien → Aktie öffnen** sowohl
im normalen Dashboard als auch in der Beta, unabhängig vom gewählten Analyse-Unterreiter.

Alternativ bleibt die serverseitige Variable `MARKETAUX_API_KEY` im Backend möglich, auf Synology
beispielsweise in der nicht versionierten `infra/.env.nas`. Ein im Dashboard gespeicherter Wert hat
Vorrang. „Entfernen“ löscht diesen Datenbankwert; eine weiterhin gesetzte Umgebungsvariable wird
danach wieder als Quelle verwendet. Ohne beide Quellen werden keine neuen Provideranfragen
gestellt; vorhandene Cache-Artikel bleiben verfügbar. Der Konfigurationstest prüft nur das Format
lokal und benötigt keine API-Anfrage. Die tatsächliche Gültigkeit zeigt sich beim nächsten regulären,
budgetgeschützten Nachrichtenabruf.

Der Marketaux-Schlüssel wird ausdrücklich **nicht** in die zwischen Backend und privatem Frontend
geteilte Runtime-Env-Datei gespiegelt. Die Frontend-Container benötigen ihn nicht; bei gemeinsamem
Compose-`env_file` wird ihr `MARKETAUX_API_KEY` ausdrücklich leer überschrieben. Keinen
`NEXT_PUBLIC_`-Namen verwenden und den Schlüssel nicht in Git, Testausgaben oder Logs kopieren.
Eine Produktionsbereitstellung erfolgt nur nach bewusster Freigabe. Der Implementierungstest
hinterlegt keinen temporären Schlüssel auf dem NAS.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `MARKETAUX_API_KEY` | leer | Optionaler Backend-Fallback; der über Einstellungen gespeicherte Schlüssel hat Vorrang. |
| `MARKETAUX_LANGUAGES` | `de,en` | Sprachfilter; eine leere Variable deaktiviert den Filter. |
| `MARKETAUX_DAILY_LIMIT` | `90` | Schutzbudget, konfigurierbar von 1 bis 90 Versuchen in rollierenden 24 Stunden. |
| `MARKETAUX_CACHE_TTL_SECONDS` | `3600` | Gültigkeit erfolgreicher nichtleerer Nachrichtenlisten. |
| `MARKETAUX_EMPTY_TTL_SECONDS` | `600` | Kürzere Gültigkeit gültiger leerer Antworten. |
| `MARKETAUX_FAILURE_BACKOFF_SECONDS` | `300` | Mindestwartefrist nach fehlgeschlagenen Abrufen. |
| `MARKETAUX_REQUEST_TIMEOUT_SECONDS` | `15` | Lese-Timeout; Verbindungsaufbau höchstens 3,05 Sekunden. |
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
Explizit widersprechende Börsenländer werden verworfen: `NA` an der NASDAQ wird beispielsweise
nicht mit `NA` an der kanadischen TSX gleichgesetzt. Fehlt die Länderangabe, werden nur eindeutig
widersprechende bekannte Börsenplätze ausgeschlossen. Unbekannte Metadaten bleiben zulässig.
Eine ausdrücklich auf `9988.HK` aufgelöste US-Ausgangsaktie wird als Hongkong-Listing behandelt.

Die Anfrage setzt `symbols`, `filter_entities=true`, `must_have_entities=true`, `group_similar=true`,
`limit=3`, `sort=published_at` und optional `language`. Der Schlüssel wird nur serverseitig an den
festen HTTPS-Endpunkt übergeben. Der Client projiziert keine rohen Providerfehler; auch aktivierte
urllib3-Debugpfade redigieren `api_token`-Querywerte.

Artikel benötigen eine passende Unternehmensentität, gültige Original-URL und einen tatsächlichen,
parsebaren Veröffentlichungszeitpunkt. Zusätzlich muss das Unternehmen oder sein Ticker direkt in
Überschrift oder Anbieter-Kurzbeschreibung vorkommen, oder der Anbieter muss eine passende Entität
ausdrücklich im Titel erkannt haben. Eine hohe Zuordnungszahl zu einer beiläufigen Erwähnung im
Artikeltext genügt nicht. Dadurch können beispielsweise fremde Unternehmens-Pressemitteilungen aus
der Liste entfernt werden, auch wenn sie NVIDIA im Haupttext erwähnen. Es werden dann entsprechend
weniger Nachrichten angezeigt. Ganze Wörter und vollständige Namen bei generischen Namensanfängen
verhindern Verwechslungen wie Apple/Appleton oder „Trade“/„The Trade Desk“.

Match-Scores sind die Providerwerte, keine Prozentsätze oder Werte von 0 bis 1. Werte unter dem
konfigurierten Minimum werden zusätzlich verworfen, außer eine passende Entität wurde im Titel
erkannt oder die Überschrift nennt das zugeordnete Unternehmen ausdrücklich. Fehlende Scores werden
nicht erfunden. Die Qualitätsversion `company-intro-v3` und der Börsenplatz sind Teil des Cache-Schlüssels; bereits unter
der schwächeren Prüfung gespeicherte Listen werden nicht wiederverwendet.
Gleiche UUIDs, kanonische URLs und nahezu gleiche Titel
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
