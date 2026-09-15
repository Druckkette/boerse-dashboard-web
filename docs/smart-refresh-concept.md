# Konzept: Schnelle und nachvollziehbare Datenaktualisierung

Stand: 15.09.2026. Zielkonzept; den implementierten Umfang und verbleibende Ausbaustufen beschreibt [refresh-operations.md](refresh-operations.md). Nicht alle unten genannten Zielbausteine sind bereits implementiert.

## 1. Entscheidung

Den langen Smart-Refresh nicht durch mehr parallele Vollabrufe beschleunigen, sondern in einen schnellen Marktzyklus und ereignisgesteuerte Hintergrundpflege aufteilen.

Die zwei Haupttermine 16:00 und 22:30 Uhr Europe/Berlin bleiben bestehen. Jeder Termin prueft das gesamte konfigurierte Aktienuniversum. Nur faellige Quellen werden abgefragt und nur abhaengige, geaenderte Ergebnisse neu berechnet. Eine nachgelagerte Berichtspflege darf die Veroeffentlichung aktueller Kurse und Bewertungen nicht aufhalten.

Ein schneller Job darf nicht dadurch entstehen, dass offene Arbeit als erledigt markiert wird. Preisabdeckung, Berichtsaktualitaet, Quellenausfaelle und Restarbeiten bleiben getrennt sichtbar.

Keine Aenderung von EPS-/Umsatz-/Sell-/Marktampel-Bewertungsregeln. Geaendert werden Beschaffung, Ablaufsteuerung, Speicherung und Aktualitaetsausweis. Bestehende NAS-Daten und das alte Streamlit-Repository bleiben erhalten.

## 2. Ausgangslage

Gemessene abgeschlossene NAS-Laeufe aus der vorausgegangenen Pruefung, jeweils sechs bis sieben Laeufe:

| Lauf | Median | Spanne |
| --- | ---: | ---: |
| 16:00 | 67 Minuten | 62-119 Minuten |
| 22:30 | 58 Minuten | 56-95 Minuten |
| Reparatur 18:45 | 43 Minuten | 19-80 Minuten |
| Reparatur 01:15 | 17 Minuten | 17-26 Minuten |

Diese Zeiten enthalten teilweise abgeschlossene Laeufe. Sie sind keine Messung einzelner Verarbeitungsschritte. Der zuletzt beobachtete Hauptlauf bearbeitete nach 79 Minuten 13F-Daten. Die letzte automatische Universumsbewertung benoetigte separat etwa 9,5 Minuten.

Im beobachteten Fundamental-Schritt wurden 250 Titel geschrieben, 2012 uebersprungen und 3337 vertagt. Die bestehenden Grenzen von 250 Titeln und 45 Minuten schuetzen Ressourcen, ersetzen aber keine weiterlaufende Warteschlange.

Vorhandene Bausteine werden weiterverwendet:

- Celery, Redis, Postgres, eigene Monitor- und Interactive-Worker.
- Preis-Batches mit 50 Symbolen und inkrementellen Zeitfenstern.
- Earnings-Kalender mit FMP und Nasdaq-Fallback.
- Revisionsvergleich fuer Screening und Wiederverwendung unveraenderter SEC-Aggregationen.
- Persistente Wiederholungsdaten fuer Fundamentals.

Konkreter Aufwand im aktuellen Fundamental-Client: bis zu fuenf FMP-Statement-/Growth-Abrufe, zusaetzliche Ratios, Profil und Earnings; dazu Yahoo-Grunddaten, SEC-Companyfacts und bei Luecken Yahoo-Statements. Die Anzahl haengt vom Ergebnis und der Konfiguration ab. Heute ist dies kein gezielter Abruf nur des fehlenden Feldes.

## 3. Aktualisierungsvertrag pro Bereich

Alle folgenden Intervalle sind vorgeschlagene Defaults. Die zwei Haupttermine bleiben unveraendert; die Boersenbewertung folgt dem jeweiligen Handelskalender, nicht pauschal Montag bis Freitag. Auslandspositionen und FX erhalten eigene Kalender. Deutsche und US-Sommerzeit werden getrennt behandelt.

| Bereich | Pruefung | Teurer Abruf / Berechnung |
| --- | --- | --- |
| Index-, ETF-, Aktienkurse und Volumen | 16:00 und 22:30 fuer alle konfigurierten Titel | Aktuelle Sitzung und Daten seit dem letzten bestaetigten Stand; nur fehlende oder zu erneuernde Zeitfenster |
| Portfolio-/beobachtete Titel, Index-Benchmarks, benoetigte FX-Paare | Zuerst innerhalb jedes Marktzyklus | Priorisierter Preis-Batch vor dem Gesamtuniversum |
| ATR-/Warnsignalmonitor | Bestehende minuetliche Handels-/After-Hours-Fenster | Gemeinsame frische Intraday-Quotes fuer Depot; keine Fundamental-Vollabrufe |
| Geoeffnete Aktienseite | Ein priorisierter Kursauftrag je bewusstem Seitenaufruf, doppelte laufende Auftraege zusammenfassen | Keine Vollaktualisierung bei jedem Render, Tab-Fokus oder Query-Poll; danach manueller Kursbutton |
| Marktampel, Sektoren, Breadth | Sobald erforderliche Kursgruppen bereit sind | Nur bei geaenderten Eingangsrevisionen; Ampel weiterhin ausschliesslich mit bestaetigten Tageskerzen |
| Externes RS-Rating | Zweimal taeglich Quelle pruefen | CSV einmal zentral laden, bei gleicher Inhaltsrevision nicht neu importieren; Quellendatum sichtbar |
| Intern berechnetes RS-Rating | Nach relevantem Kursrefresh | Berechnung ueber das gesamte zulaessige Vergleichsuniversum; keine methodisch falsche Teilrangliste |
| RS-Linie und Durchschnitte | Nach Aenderung von Aktie oder Benchmark | Betroffene Reihen neu berechnen; SPY-Aenderung kann alle Reihen betreffen |
| Earnings-Kalender | 15:50 und 22:20; zentral | Rueckblick 7 Tage, Vorschau 14 Tage; weiterer Horizont bis 120 Tage einmal pro Woche, soweit Quelle verfuegbar |
| EPS, Umsatz, ROE, Marge | Neue Berichts-/Earnings-Ereignisse, fehlende Daten und Sicherheitskontrolle | Nur benoetigte Statement-Gruppen und Perioden laden; vorhandene Historie erhalten |
| Beta | Woechentlich verteilt; sofort bei fehlendem Wert fuer einen aktiven Titel oder relevanter Instrumentenaenderung | Profilabruf getrennt von Statements; vorhandene Beta-Methodik bleibt erhalten |
| 13F | Quellenmanifest zweimal taeglich pruefen | Nur neue/geaenderte Archive oder Einreichungen verarbeiten; neue Zuordnung nur fuer betroffene CUSIPs neu auswerten |
| Aktienuniversum / Symbolzuordnungen | Einmal taeglich | Aenderungen uebernehmen, neue Titel initialisieren; Fehlzuordnungen gesondert behandeln |
| FINRA Margin Debt / andere langsame Quellen | Taeglicher leichter Quellencheck | Nur neue Publikation einlesen; Berichtsmonat statt Tageskurs-Freshness verwenden |
| Portfolio-Snapshots, Sell-Ranking, Kaufstaerke | Nach Kurs-, FX-, Positions- oder Setup-Aenderung | Nur relevante Ableitungen; historische Tagebucheintraege nicht nachtraeglich veraendern |
| Bestenliste | Nach schnellem Kurs-/RS-Zyklus sowie nach neuen Berichtsrevisionen | Bei Kurszyklus ggf. viele Aktien; bei einzelnen Berichten nur betroffene Aktien |

Feiertag: kein vergeblicher Abruf fuer eine nicht existierende Sitzung. Nach Wiederanlauf der NAS: fehlende Zeitfenster zusammenfassen und nachholen statt alle verpassten Cron-Laeufe einzeln wiederzugeben.

## 4. Schneller Marktzyklus

```text
16:00 / 22:30 / Button
  -> kurzer Plan aus vorhandenen Aktualitaetsdaten
  -> aktuelle Index-, Portfolio-, ETF- und FX-Kurse zuerst
  -> Markt-/Portfolio-Ansichten gruppenweise veroeffentlichen
  -> restliche faellige Universumskurse in Batches
  -> Breadth, RS, technische Bewertungen, Bestenliste
  -> Marktzyklus abgeschlossen / eingeschraenkt abgeschlossen

Parallel geplant, aber NICHT mehrere schwere Ausfuehrungen:
  -> Earnings-/Filing-Pruefung
  -> Fundamental- und 13F-Arbeit in persistenter Hintergrundwarteschlange
  -> nur betroffene Bewertungen nachziehen
```

Der Planer beendet sich schnell; seine Laufzeit ist nicht die Aktualisierungsdauer. Die UI zeigt den gesamten Marktzyklus bis zur veroeffentlichten Bestenliste weiter als laufend.

### Preis-Beschaffung

- Unterschiedliche Abrufstaende in kompatible Batches gruppieren. Ein neu hinzugekommener Titel darf nicht fuer 49 aktuelle Titel zwei Jahre Historie erzwingen.
- Intraday dieselbe Tageskerze erneut abrufen, abends nach Handelsschluss bestaetigen. Kleine Ueberlappung von einer Handelssitzung statt pauschal sieben Tagen.
- Provider-Abrufzeit und tatsaechlichen Quote-/Sitzungszeitpunkt getrennt speichern. Heute abgerufen bedeutet nicht automatisch heutiger Kurs.
- Fehlversuche einzelner Symbole aus dem normalen schnellen Batch in eine Reparaturliste verschieben. Keine unendliche Retry-Schleife pro Symbol.
- Splits, Dividendenadjustierungen und Providerkorrekturen koennen aeltere Werte aendern: gezielter historischer Backfill fuer betroffene Titel plus rotierende Stichproben. Nicht ungeprueft annehmen, dass nur neue Zeilen veraendert sind.
- Yahoo-Batches bleiben bei zunaechst 25-50 Symbolen; gleichzeitige Providerverbindungen begrenzen und messen. Ein yfinance-Batch ist nicht automatisch ein einziger HTTP-Aufruf an Yahoo.

### Veroeffentlichung ohne verfaelschte Frische

Indexansicht, Portfolio, Breadth und Gesamtranking haben eigene Abhaengigkeitsgruppen. Fehlende CHF-/JPY-Kurse duerfen nicht den unabhaengigen S&P-Chart blockieren; fuer betroffene Fremdwaehrungspositionen bleibt die Warnung bestehen.

Pro Gruppe kurze atomare Veroeffentlichung einer Generation. Bis dahin bleibt die letzte gueltige Generation sichtbar. Nach Budgetende darf eine eingeschraenkte Generation mit explizit markierten alten/fehlenden Titeln erscheinen, niemals ein pauschal frisches Gesamtranking. Bestehende Abdeckungsgrenzen werden nicht zur Beschleunigung abgesenkt.

## 5. Fundamentals: Aenderungen erkennen statt blind neu laden

### Ausloeser

1. Neues Earnings-Ereignis beziehungsweise erwarteter Berichtszeitpunkt.
2. Neue relevante SEC-Einreichung oder Korrektur, zum Beispiel 10-Q/10-K und deren Amendments. Relevante 8-K/6-K sowie 20-F/40-F koennen ebenfalls eine Pruefung ausloesen, sind aber kein Beweis, dass bereits alle benoetigten Zahlen vorliegen.
3. Noch fehlende Historie, neues Instrument oder manuell angeforderte Reparatur.
4. Kein verlaesslicher Aenderungsnachweis innerhalb der maximalen Sicherheitsfrist.

FMP stellt einen zentralen Kalender mit Terminen und teils Ist-Werten bereit. Er ersetzt weder Jahresabschluesse noch vollstaendige Abdeckung aller Instrumente. Keine Annahme kostenloser/unbegrenzter API-Rechte. [FMP Earnings Calendar](https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar)

Fuer SEC-Titel werden taegliche Filing-Indizes inkrementell anhand CIK und Accession ausgewertet. Diese Indizes entstehen nachts; sie sind kein Intraday-Pushdienst. Fuer Portfolio-Titel und erwartete Earnings werden zusaetzlich gezielte Submissions-Pruefungen genutzt. Ein woechentlicher Indexabgleich beruecksichtigt spaetere Korrekturen. [SEC: Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

Companyfacts werden nur fuer betroffene Unternehmen geladen. Die SEC-APIs liefern aktualisierte Einreichungs- und Finanzdaten; ein pauschaler taeglicher Download aller Companyfacts-ZIPs ist fuer diesen NAS-Inkrementalbetrieb nicht vorgesehen. [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

### Sicherheitsnetz

- Gesamter Bestand: zweimal taeglich kostenguenstige lokale Faelligkeitspruefung; kein Einzel-HTTP-Aufruf je Aktie dafuer.
- Je Unternehmen spaetestens nach 14 Kalendertagen ein tatsaechlicher verteilter Provider-/Periodencheck, sofern dieser nicht bereits durch ein Ereignis erfolgte. Bei 5593 Titeln sind das grob 400 Pruefungen pro Tag, nicht zwingend 400 Vollabrufe.
- Portfolio, beobachtete Titel und fehlende/unklare Kalenderdaten priorisieren; im Umfeld erwarteter Earnings taeglich pruefen. Ein unbekannter Termin ist niemals ein Beleg fuer unveraenderte Fundamentals.
- Globale Kalenderantworten setzen nicht blind den individuellen Aktualitaetsnachweis aller Titel auf heute.

### Feldbezogene Beschaffung

Statement-Daten, Profil/Beta und Kalender voneinander entkoppeln. Ein neuer Earnings-Termin erfordert keinen erneuten Beta-Abruf; ein Beta-Abruf keine EPS-Historie.

Pro Ticker/Datengruppe die zuletzt brauchbare Quelle bevorzugen. FMP/SEC/Yahoo-Fallbacks nur fuer fehlende, widerspruechliche oder noch alte Felder aufrufen. Ein allgemeines FMP-401/429 darf nicht tausendfach pro Ticker erneut getestet werden. Vorhandene Rohdaten zusammen mit Herkunft und Version wiederverwenden.

YoY-Wachstum aus den bereits normalisierten absoluten Werten berechnen. Zusaetzliche Growth-Endpunkte sind nur ein explizit benoetigter Fallback, keine Standard-Doppelabfrage. Perioden-/Einheitenvergleich und Golden Tests muessen Gleichwertigkeit zur bisherigen Bewertung sichern.

Initiale Reparatur sichert mindestens die letzten drei Quartale samt ihren Vorjahresvergleichsquartalen, vier Jahre fuer drei jaehrliche Wachstumsraten, vier zusammenhaengende Quartale fuer EPS-TTM sowie die fuer ROE-Bonuspunkte benoetigten Jahre. Kuenftige Abrufe ergaenzen neue Perioden und gezielte Revisionen. Fiscal Year/Quarter, Berichtszeitraum, Waehrung und diluted/basic EPS werden nicht vermischt. Q4-Ableitungen sind nur bei fachlich kompatiblen Ausgangsdaten erlaubt; EPS nicht unbesehen aus Jahreswert minus drei Quartalen ableiten.

Provider koennen auch bei einem Einzelupdate komplette Historien liefern. Dann wird auf Quellenebene gecacht und auf Datenbankebene differenziert; ein echtes Netzwerk-Delta ist nicht bei jedem Endpoint moeglich.

### Wann ist der Auftrag wirklich erledigt?

HTTP 200 oder ein gespeicherter Snapshot allein reichen nicht. Erwartete Berichtsperiode und erforderliche Felder muessen vorliegen. Alte Zahlen nach neuem Earnings-Termin lassen den Auftrag im Zustand `waiting_source`. Noch gueltige Daten werden bei leerer/fehlerhafter Antwort nicht geloescht.

Erster Versuch nach erkannter Veroeffentlichung beziehungsweise im naechsten passenden Hauptfenster. Ist die neue Periode noch nicht verfuegbar: vorgeschlagene Wiederholungen nach 2, 8 und 24 Stunden, anschliessend taeglich bis sieben Tage; danach deutlich sichtbare Luecke mit geringerem Prueftakt. Neue Filing-Ereignisse koennen die Wartezeit verkuerzen. Aeltere Historienluecken laufen gesondert weiter, nicht als angeblich ausstehende aktuelle Earnings.

## 6. 13F als eigener Datenstrom

Ein zweimaliger Manifestcheck pro Tag ist billig; identische Archive zweimal taeglich zu aggregieren ist es nicht. Die offizielle Bulkquelle ist quartalsweise und kann aktuellen Einzeleinreichungen hinterherlaufen. Hauefigeres Herunterladen derselben Datei behebt dies nicht. [SEC Form 13F Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)

Zweistufiges Ziel:

1. Kurzfristig: Archive anhand Inhaltsrevision/ETag/Last-Modified pruefen, soweit angeboten; auf unveraenderten Download auch nach erneutem HTTP 200 per Inhalts-Hash reagieren. Einmal in normalisierte Tabellen importieren; CUSIP-Aggregate unabhaengig vom aktuell ausgewaehlten Aktienuniversum speichern. Neue Titel oder Zuordnungen duerfen keinen vollstaendigen ZIP-Neuimport ausloesen.
2. Fuer zeitnaehere 13F-Abdeckung: neue 13F-HR/13F-HR-A-Einreichungen nach Accession inkrementell verarbeiten und regelmaessig gegen Bulk abgleichen. Das ist ein eigener Implementierungsschritt; blosses Caching reicht fuer diese Aktualitaet nicht.

Versionierung je Manager, Berichtsperiode und Einreichung verhindert Doppelzaehlung von Amendments. Aggregation in begrenzten Teilen, kein DataFrame aller Holdings dauerhaft im RAM. Fruehe unvollstaendige Quartalsmeldungen nicht als Rueckgang der Halterzahl verkaufen: Vergleichbarkeit, Meldestand und Abdeckung ausweisen. Die Verarbeitung erfolgt nachrangig beziehungsweise nachts und haelt den schnellen Marktzyklus nicht offen.

## 7. Warteschlange und NAS-Ressourcen

Postgres wird die verbindliche Aufgabenliste; Celery transportiert kurze Ausfuehrungsauftraege. Keine zweite Datenbank, kein Kubernetes, kein neues Worker-Framework.

### Prioritaet und Fortsetzung

1. Bestehender eigener Monitor fuer zeitkritische Depotwarnungen.
2. Interaktiver, begrenzter Kursabruf sowie Kernmarkt-/Portfolio-Batch.
3. Kurse des Gesamtuniversums, RS und aktuelle Bestenliste.
4. Neue Berichte betroffener Portfolio-/Earnings-Titel.
5. Faellige Berichte anderer Titel, Sicherheitspruefungen und Reparaturen.
6. Historischer Backfill und grosse SEC-Aggregationen.

Nur ein schwerer Rechenauftrag gleichzeitig. Leichte Netzwerkaufgaben erhalten wenige begrenzte Verbindungen und ein gemeinsames Rate-Budget je Provider, auch ueber Monitor/Interactive/Standard-Worker hinweg. Reservierte Kapazitaet fuer den Monitor verhindert, dass ein Universumsabruf alle Provider-Tokens verbraucht.

Arbeitspakete geben die Ausfuehrung nach zunaechst 1-2 Minuten Zielbudget oder einem kleineren fachlichen Teil frei; Provider-Timeouts bleiben begrenzt. Pausen gelten an sicheren Speicherpunkten, nicht mitten in einer Transaktion. 13F muss dafuer erst in echte Teilaufgaben zerlegt werden. Fuer lange/kurze Aufgaben und Speicherbegrenzung empfiehlt auch Celery getrenntes Routing und begrenzte Reservierung; die vorhandene Concurrency 1 bleibt der Ausgangspunkt. [Celery Optimizing](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)

Der Dispatcher waehlt alle 30-60 Sekunden und nach Taskabschluss erneut faellige Arbeit. Kein Worker wartet schlafend auf ein mehrstuendiges Providerlimit. Mindestens ein Anteil der freien Hintergrundkapazitaet wird fuer die aelteste Aufgabe reserviert; Prioritaet nimmt mit Wartezeit zu. Der 250er-Wert ist hoechstens eine Planungstranche, keine Tagesgrenze. Neue Markttermine verdraengen keinen bereits gespeicherten Fortschritt.

### Zuverlaessigkeit

- Idempotenter Schluessel aus Instrument/Quelle/Datengruppe/Zielrevision, statt mehrfacher Auftraege durch wiederholte Klicks.
- Aufgabenstatus und Dispatch-Eintrag in derselben Postgres-Transaktion; Dispatcher darf erneut senden, Worker beansprucht Auftrag mit Lease und Revision.
- Bei Worker-/NAS-Neustart abgelaufene Leases pruefen und genau offene Pakete erneut ausfuehren. Niemals automatisch den gesamten Bootstrap neu starten.
- Bei Rate Limit `Retry-After` beachten, begrenzte Wiederholungen mit Jitter. Auth-/Tariffehler bis Konfigurationsaenderung oder kontrolliertem Probeabruf pausieren; fehlende Symbole zur Zuordnungspruefung.
- Altere Resultate duerfen neuere Revisionen weder ueberschreiben noch eine inzwischen erneut geaenderte Aktie als fertig markieren.
- Genuegend RAM fuer DSM, Postgres, Frontend und Monitor reservieren. Konkrete Containerlimits nach Messung der vorhandenen NAS-RAM-Ausstattung; keine pauschale Erhoehung der Workerzahl. Bei Speicherdruck weniger Hintergrundarbeit statt OOM-Schleifen.

Zusaetzlicher Infrastrukturpunkt: `docker-compose.nas.yml` verwendet aktuell Redis `allkeys-lru` auch fuer den Broker. Diese Policy kann Schluessel bei Speicherdruck entfernen. Vorschlag: Broker auf begrenztes `noeviction` umstellen, Fehler beim Einreihen abfangen und Auftraege in Postgres belassen; reine Cache-Daten separat beziehungsweise mit strengem eigenen Budget halten. Verschiedene Redis-DB-Nummern trennen die Speicherpolicy nicht. [Redis Eviction](https://redis.io/docs/latest/develop/reference/eviction/)

## 8. Datenmodell und Berechnungsrevisionen

Bestehende Jobs und Snapshots erweitern, neue Detailtabellen schrittweise via Alembic ergaenzen:

| Struktur | Wesentliche Felder |
| --- | --- |
| `data_refresh_state` | instrument_id, data_group, provider, report_period, latest_detected_revision, applied_revision, checked_at, successful_fetch_at, value_changed_at, next_check_at, completeness, freshness_state, missing_fields, reason |
| `refresh_work_items` | run_id, deduplication_key, target_revision, priority, due_at, status, attempts, lease_owner, lease_until, checkpoint, last_error, created_at, finished_at |
| `source_artifacts` | provider, resource_key, etag, last_modified, content_hash, parser_version, fetched_at, local_path, imported_at |
| `jobs` / Job-Schritte | parent/run_id, stage, started_at, heartbeat_at, finished_at, expected_count, processed_count, reused_count, failed_count, deferred_count, duration_ms |
| Bewertungs-Snapshots | generation_id, Preis-/Fundamental-/RS-/13F-/FX-Revisionen nach Bedarf, rule_version, evaluated_at, effective_date, Quality-Status |

`checked_at` veraendert keine Inhaltsrevision. Nur geaenderte Eingangsdaten machen die abhaengige Berechnung faellig. Auch Regelversion, Benchmark, Universum und zeitabhaengige Bedingungen wie Earnings-Abstand muessen als Abhaengigkeit beruecksichtigt werden.

Aktienratings koennen bei geaenderten Gesamtuniversumsdaten alle betroffen sein; einzelne Fundamentalupdates dagegen nicht. Batches von Aenderungsereignissen sammeln, damit nicht fuer jeden geschriebenen Kurs sofort ein Screening entsteht. Periodische Sicherheitsabgleiche finden verlorene Invalidierungen.

Alle UI-Ansichten und CSV-Exporte lesen dieselben veroeffentlichten Generationen und dieselben Qualitaetsregeln. Vollstaendigkeitsfilter schliessen unbekannte oder veraltete Abhaengigkeiten aus. Rohdaten bei Ausfall weiter sichtbar, aber keine erfundene positive Freigabe und keine falsche Entwarnung in Push-Nachrichten.

## 9. Bedienung und Status

Ein Hauptbutton: **Smart aktualisieren**. Er fordert eine Faelligkeitspruefung an, priorisiert offene Arbeit und verknuepft mit einem bestehenden Lauf, statt die Meldung zur gesperrten parallelen Schwerarbeit zu zeigen. Er erzwingt keinen Vollabruf. Eine gesonderte Reparaturaktion bleibt in den erweiterten Einstellungen.

Vier getrennte Fortschrittsanzeigen:

- Markt/Kurse: aktueller Zyklus, tatsaechlich aktuelle Titel, alte und fehlende Titel.
- Bestenliste: Stand der veroeffentlichten Generation, neu berechnet, wiederverwendet, noch offen; laufender Smart-Refresh und Einzeljob gleichermassen erkennbar.
- Fundamentals: erwartete Berichte, Quellen noch nicht bereit, Historienluecken und Sicherheitschecks getrennt.
- 13F: Berichtsperiode, Quellencheck, Einreichungsabdeckung, Aggregation laeuft oder unveraendert.

Datensatzstatus: `current`, `provisional`, `update_expected`, `waiting_source`, `missing`, `error`, `not_applicable`. Jobstatus wie queued/running/done bleibt davon getrennt. `not_applicable` erfordert eine begruendete Instrumentklassifikation, nicht nur eine leere Providerantwort. Nicht auf Aktien anwendbare Daten duerfen fuer ETFs nicht endlos als Pflichtluecke laufen.

Zeitwerte: Kurszeit, Abrufzeit, letzte Pruefung und Auswertung nicht miteinander verwechseln. Quartalsdaten ohne neueren Bericht koennen weiterhin aktuell sein; eine ueberfaellige neue Berichtsperiode darf nicht durch blossen Abruf ein neues Frischesiegel bekommen.

Poll nur kompakte Statusendpoints alle 5-10 Sekunden waehrend Arbeit, ansonsten deutlich seltener; grosse Job-Resultate nur bei explizitem Aufklappen. Fortschritt in Stueckzahlen je Schritt, Restzeit aus dessen gemessenem Durchsatz als Spanne. Bei unbekanntem Durchsatz keine scheinexakte ETA.

## 10. Ziele und Grenzen

Vorlaeufige Abnahmeziele fuer Normalbetrieb nach initialem Historienaufbau, bei funktionierenden Quellen und ausreichendem NAS-RAM:

| Messgroesse | Ziel fuer den ersten Benchmark |
| --- | --- |
| Einreihen / vorhandenen Lauf finden | API-Antwort unter 1 Sekunde, ohne Datenabruf im Request |
| Kernmarkt-/Portfolio-Preise nach Start | unter 5 Minuten |
| Schneller Gesamtmarktzyklus inklusive Bestenliste | Median unter 30 Minuten; 95. Perzentil unter 45 Minuten |
| Geaenderte Einzel-Fundamentals bis neue Bewertung | innerhalb von 5 Minuten nach erfolgreicher Datenuebernahme bei freier Kapazitaet |
| Unveraenderte 13F-Quelle | keine erneute Vollaggregation |
| Wiederholung ohne Inhaltsaenderung | keine unnoetige Neuberechnung, Fortschritts-/Pruefzeit trotzdem korrekt |
| Hintergrundwarteschlange | aelteste faellige Aufgabe und Netto-Abbau taeglich sichtbar; kein dauerhaftes Wachstum ohne Warnung |

Das sind Zielwerte, keine bereits gemessenen Zusagen. Der schnelle Gesamtzyklus benoetigt weiterhin echte Arbeit fuer rund 5600 Titel. Ein historischer Erstimport, neue SEC-Grossarchive oder eine Providerstoerung koennen laenger dauern und erhalten eigene Budgets/Status.

Ende-zu-Ende-Latenz = Erkennung der Veroeffentlichung + Provider-Verzoegerung + Warteschlange + Abruf/Berechnung. Ein Earnings-Event macht Zahlen nicht sofort abrufbar. Bei knappen Tarifen ist ein kompletter rueckstandsfreier Universumsdienst eventuell nicht innerhalb dieser Ziele moeglich. Dann werden Limit und Wartezeit offen angezeigt; keine automatische kostenpflichtige Buchung.

Mindestens zehn Handelstage Laufzeiten, CPU/RAM, Datenbankzeit, HTTP-Zahl, Providerwartezeit, Wiederverwendungsquote und Rueckstandsabbau erfassen. Tageskapazitaet muss groesser sein als neue Ereignisse plus faellige Sicherheitspruefungen; sonst muss die Beschaffung/Bulkstrategie oder das Ressourcenbudget angepasst werden. Neon allein beseitigt weder API-Limits noch NAS-Berechnungen und ist kein vorgesehener Beschleunigungsschritt.

## 11. Umsetzung und Tests

1. Messung je Schritt, ehrliche Status-/Restarbeitsanzeige, Bestenliste mit Parent-Smart-Refresh verknuepfen. Redis-Broker-Speicherschutz vorbereiten.
2. Marktzyklus von Berichtspflege trennen; Kernsymbole priorisieren, gruppenweise Qualitaet und atomare Ranking-Veroeffentlichung sichern.
3. Persistente Arbeitsliste, Leases, Deduplizierung, Providerbudgets und kurze fortsetzbare Tasks einfuehren. Bestehende Zeitplaene auf Dispatcher umstellen, keine doppelten Hauptlaeufe.
4. Fundamental-Gruppen trennen, Earnings-/Filing-Ausloeser und Sicherheitschecks implementieren; Bestand einmalig inventarisieren und kontrolliert reparieren.
5. Feld-/Revisionen-basierte Folgeauswertungen und 13F-Normalisierung. Danach bei benoetigter juengerer Abdeckung die inkrementelle Einzelmeldungs-Pipeline.
6. Lokale Docker-/Postgres-Tests, dann kontrollierter NAS-Rollout mit Backup, Feature-Flag und SHA-Rollback. Keine parallelen alten/neuen Scheduler gegen dieselben Daten.

Pflichttests: gleiche Inputs erzeugen gleiche Scores; alte Daten nach Earnings bleiben offen; Amendments werden verarbeitet; fehlende Kalenderdaten werden per Sicherheitscheck erfasst; keine Loeschung guter Historien bei Fehler; Split-/FX-/Zeitzonen-/Feiertagsfaelle; Neustart setzt nur offene Arbeit fort; wiederholter Buttonklick erzeugt keine Doppelarbeit; veralteter Worker darf keine neuere Generation ueberschreiben; globale RS- und SPY-Abhaengigkeiten werden korrekt invalidiert; Provider-429 pausiert nur betroffene Quelle; Redis-Speicherdruck verliert keine persistierten Auftraege; API und Monitor bleiben unter gemessener Hintergrundlast reaktionsfaehig.

Dieses Dokument aendert noch keine Ausfuehrung, Zeitplaene oder NAS-Einstellungen. Die Implementierung sollte mit den Punkten 1 und 2 beginnen: Sie machen die aktuelle Bewertung schneller verfuegbar und liefern belastbare Messwerte fuer die weiteren Optimierungen.
