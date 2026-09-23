# Datenpflege: Betrieb und Grenzen

Stand: 15.09.2026.

## Implementierter Ablauf

- 16:00 und 22:30 Europe/Berlin bleiben die Haupttermine. Der Marktzyklus aktualisiert Kurse inkrementell, dann Breadth, RS und Bewertungen. Fundamentals und SEC-Archive sind keine Schritte dieses schnellen Zyklus mehr.
- Bestehende Reparaturtermine 18:45 und 01:15 sowie Depotmonitor und interaktiver Worker bleiben erhalten.
- Die Planung erfasst das gesamte gespeicherte Universum plus offene Positionen. Es gibt keine 250-Titel-Tagesgrenze fuer die neue Berichtspflege.
- Postgres `refresh_work_items` speichert Faelligkeit, Revision, Versuche, Fehler und Worker-Lease. Celery weckt die Verarbeitung jede Minute. Pro Paket maximal acht Eintraege und ein Zielbudget von 120 Sekunden zwischen Eintraegen. Ein einzelner Quellenabruf kann das Paketbudget ueberschreiten; ein SEC-Archiv ist noch kein kleinteilig fortsetzbarer Task.
- Fundamentals: Earnings der letzten 14 Tage, erkannte SEC-Berichte, fehlende Historien und Sicherheitscheck nach 14 Tagen. Beta getrennt alle sieben Tage. Die bestehende Kalenderpflege um 15:50 und 22:20 bleibt bestehen.
- SEC-Filing-Indizes werden alle zwoelf Stunden mit einem Rueckblick auf sieben Kalendertage geprueft. Das sind nachts veroeffentlichte Indizes, kein Echtzeitfeed. Laengere Ausfaelle werden durch den 14-Tage-Sicherheitscheck aufgefangen.
- Bei noch fehlenden Quelldaten: erneute Versuche nach 2, 8, 24, 48, 96 und maximal 168 Stunden. Neue Ereignisse ziehen den Auftrag wieder vor. Geltende Historie wird bei leeren Antworten nicht geloescht.
- FMP-Hintergrundabrufe respektieren gemeinsame Redis-Sperrzeiten fuer 429/401 und endpointbezogene 403. Geaenderte Schluessel verwenden einen neuen anonymen Fingerprint. Keine Schluessel in der Warteschlange. Dies ist noch kein globales Rate-Budget aller Anbieter/Worker.
- 13F-Archivpflege wird nachts zwischen 02:00 und 06:00 gestartet, danach fruehestens nach 24 Stunden. Unveraenderte Downloadinhalte behalten ihre Cache-Revision, auch bei HTTP 200. Neue Daten loesen Folgebewertungen aus. Der bisherige monatliche Sicherheitslauf bleibt erhalten.
- Nach geaenderten Statements/Beta werden nur betroffene Bewertungen neu geschrieben. Eine Aenderung der SPY-Preisrevision invalidiert auch abhaengige RS-Linien. Gesamt-RS wird weiterhin ueber das gesamte Vergleichsuniversum ermittelt.
- Smart-/Bestenlisten-Klicks verwenden einen bereits laufenden Markt-/Bewertungsjob. Bei anderer Schwerarbeit werden sie seriell eingereiht, nicht parallel ausgefuehrt. Diese Auftraege duerfen sechs Stunden warten. Hintergrundpflege nutzt weiterhin den Standardworker mit Concurrency 1.

## Sichtbarkeit

Unter Jobs und in der Bestenliste stehen jetzt die tatsaechlich faelligen Pruefungen und der naechste geplante Check getrennt von den Bestandszahlen je Datenbereich. Jede Bestandszahl zaehlt eine Pruefung pro Ticker und Datenbereich; sie ist keine Zahl offener Ticker. `current` bedeutet zuletzt erfolgreich geprueft und bis zum naechsten Termin nicht faellig. `waiting_source` bedeutet: der Abruf fand statt, aber die erforderliche Historie bzw. Berichtsperiode fehlt; ein weiterer Versuch ist terminiert. `queued` kann eine zukuenftige Erstpruefung sein. `error` ist ein fehlgeschlagener Abruf mit geplantem Wiederholungsversuch. Erst `due_count` zeigt an, wie viele Pruefungen jetzt faellig sind. Der Marktzyklus kann bereits fertig sein, waehrend Berichtsarbeit noch offen ist.

Bei fehlendem Anbieter-Beta berechnet der Report-Worker den Wert aus gespeicherten, splitbereinigten Aktien- und SPY-Tageskursen: bis zu 252 gemeinsame Tagesrenditen, mindestens 90, letzter gemeinsamer Kurs hoechstens 14 Tage alt. Reichen die Kurse nicht, bleibt der Yahoo-Abruf als Rueckfall erhalten. Fehlende Quartalsberichte und sehr kurze IPO-Kursreihen lassen sich damit nicht erfinden; sie bleiben mit rueckgestelltem Versuch sichtbar. Der NAS-Bestand vom 23.09.2026 hatte 0 faellige Pruefungen trotz 5.271 `assessment/current` und 65 `assessment/waiting_source`; 2.572 Statements und 939 Betas warteten auf Quelldaten. FMP antwortete bei einer Stichprobe mit HTTP 429; SEC und Yahoo sind bereits als weitere Statement-Quellen eingebunden. Diese Zahlen sind ein Zeitpunktbild, keine Ausfallgarantie.

API: `GET /api/v1/jobs/report-work`; kompakter Einzelfortschritt: `GET /api/v1/jobs/{id}?compact=true`. Die Warteschlange liefert bei Datenbankfehlern 503 statt eine falsche leere Erfolgsmeldung. Job-Schrittlaufzeiten werden fuer kuenftige NAS-Messungen gespeichert.

## Deployment

Migration `0015_refresh_work_items` vor Neustart der Worker ausfuehren. Backend, Worker, Interactive-Worker, Monitor und Scheduler verwenden dasselbe Backend-Image. Redis verwendet `noeviction` statt `allkeys-lru`, damit Broker-Schluessel nicht durch Speicherdruck geloescht werden. Speicherlimits bleiben bestehen. Nach Migration einmal Smart Refresh oder `plan_report_work()` ausfuehren, um den vorhandenen Bestand einzuplanen. Der Dispatcher setzt danach automatisch fort.

Die Umstellung migriert keine Secrets und loescht keine Kurse. Rueckkehr zum vorherigen Image ist moeglich; die zusaetzliche Tabelle kann bestehen bleiben. Kein `down -v` verwenden.

## Noch nicht als fertig betrachten

- Einzelne neue 13F-Einreichungen inklusive Amendments inkrementell statt ueber Bulkarchive verarbeiten.
- Universumsunabhaengige persistente CUSIP-Aggregate und echte Checkpoints innerhalb grosser SEC-Archive.
- Globale Provider-Rate-Budgets inklusive reservierter Monitor-Kapazitaet; derzeit nur FMP-Berichtspflege mit geteilter Sperrzeit.
- Intraday-SEC-Submissions-Pruefung und erweiterter, dauerhaft fortsetzbarer Indexabgleich nach langen Ausfaellen.
- Feinere feldbezogene Quellenwahl und durchgaengige Generationen mit Compare-and-Swap bei gleichzeitigen interaktiven Aktualisierungen.
- Ein kompletter gemessener neuer NAS-Marktzyklus ist erforderlich, bevor eine konkrete Beschleunigung zugesichert werden kann. Die erstmalige Reparatur des Fundamental-Rueckstands dauert weiterhin laenger als spaetere Ereignispflege.
