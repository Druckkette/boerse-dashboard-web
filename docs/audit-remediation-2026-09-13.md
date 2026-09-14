# Datenqualitaet und Performance: Korrekturen vom 13.09.2026

## Umgesetzte Sicherungen

| Bereich | Aenderung |
| --- | --- |
| Verkaufsmonitor | OHLC, ATR und Einstand in derselben Waehrung. Kein fiktiver FX-Ersatz im Entscheidungsaufruf. Fehlende aktuelle FX-Daten blockieren die Berechnung. Bereits normalisierte Metrics werden im ATR-Monitor nicht doppelt umgerechnet. |
| Marktampel | Einheitliche Berechnung aus der gesamten gespeicherten Indexhistorie. 60/90/130/200 Tage begrenzen ausschliesslich den Chart. Overview verwendet die Warnzeichen der jeweiligen Index-Ampel. |
| Tagesschluss | Kursdatum und Abrufzeit werden getrennt gespeichert. Ein um 16 Uhr geholter Tageskurs wird nach Boersenschluss nicht automatisch zum bestaetigten Schlusskurs. Die Ampel verwendet nur bestaetigte Tageskerzen; vorlaeufige Kurse bleiben im Chart sichtbar. |
| Aktualitaet | Handelssitzungen statt einer pauschalen Fuenf-Tage-Toleranz. Preis-Coverage erfordert einen passenden Abrufzeitpunkt. Fundamentals, RS und erwartete 13F-Berichtsperiode werden getrennt ausgewiesen. Der Vollstaendigkeitsfilter schliesst alte Abhaengigkeiten aus. |
| Stopps | Gepflegte Stopps werden von bereits erreichten Stopps unterschieden. Das Dashboard bestaetigt keine Ausfuehrung eines Brokerauftrags. |
| Depotkurve | Kein stiller Wechsel vom fehlgeschlagenen TR-Verlauf zur Simulation heutiger Positionen. Historische Wechselkursreihen werden fuer Bestands- und Cashbewertung verwendet. Ersatzkurse, fehlende FX-Historie und fortgeschriebene Kurse werden als Einschraenkung angezeigt. |
| Fundamentals | Persistente Versuchs-/Wiederholungsdaten pro Ticker. Nicht faellige Wiederholungen blockieren keine anderen Titel. Reparaturen werden nicht mehr auf die ersten 80 unvollstaendigen Titel abgeschnitten; veraltete Titel werden ebenfalls beruecksichtigt. |
| 13F | Bis zu 10.000 Titel statt einer versteckten 5.000er-Grenze. Bedingte Archivabrufe und Wiederverwendung identischer Aggregationen. Fingerprint beruecksichtigt Archive, Zuordnungen, Universum, Konfiguration und Code. Erfolgreich ingestierte unveraenderte Ergebnisse werden nicht erneut geschrieben. |
| Seitenkopf | Kleiner Summary-Aufruf statt vollstaendiger Depotdiagnose bei jeder Sitzung. Eine Diagnose aelter als fuenf Minuten wird nicht als aktuelle Freigabe dargestellt. Die vollstaendige Diagnose wird im Settings-Bereich angefordert. |
| Screening | Postgres berechnet kompakte Abhaengigkeitsrevisionen. Bei identischen Revisionen entfallen OHLC-Historienabrufe. Nur geaenderte Snapshot-Zeilen werden geschrieben; Laufstatistik wird einmalig, atomar gespeichert. Regel- und Kalenderwechsel invalidieren die Wiederverwendung weiterhin. |

## Zeitplan und Ressourcen

- Die Hauptlaeufe bleiben werktags um **16:00 und 22:30 Uhr Europe/Berlin**. Kein Wechsel zu stuendlichen Vollscans.
- Bestehende Reparaturfenster und Worker-Concurrency 1 bleiben erhalten.
- Ein erfolgreicher Fundamental-Abruf wird nicht innerhalb von sechs Stunden erneut automatisch ausgefuehrt. Fehler werden mit wachsendem Abstand wiederholt (12 Stunden bis maximal sieben Tage). Der restliche faellige Bestand kann waehrenddessen weiterlaufen.
- Ein erfolgreicher Datenabruf ist nicht gleichbedeutend mit einer neuen Quartalsmeldung. Vorhandene SEC-Berichtsperioden werden nicht kuenstlich auf heute datiert.
- Earnings-Kalender-Freshness beruecksichtigt die werktags geplanten Abrufe und erzeugt nicht allein wegen des Wochenendes eine 26-Stunden-Warnung.
- Der Screening-Revisionsvergleich beschleunigt unveraenderte Wiederholungen; neue Kurs- oder Berichtsdaten muessen weiterhin berechnet werden. Eine konkrete NAS-Beschleunigung ist noch zu messen.

## Migration und Inbetriebnahme

Migration **0014_price_fetch_time** muss vor Start des neuen Codes ausgefuehrt werden. Sie ergaenzt `price_bars.fetched_at`. Fuer alte Zeilen werden keine Abrufzeiten erfunden. Alte abgeleitete Sell-Rankings werden verworfen, damit die fruehere Waehrungsmischung nicht als Empfehlung bestehen bleibt. Positionen, Stopps, manuelle Einstellungen und Tagebucheintraege werden nicht geloescht.

`infra/update-nas.sh` fuehrt die Migration bereits vor dem Containerwechsel aus. Danach werden die aktuellen Kurszeilen beim naechsten Smart Refresh mit echten Abrufzeiten versehen und die Rankings neu erstellt. Bis dahin kann die Anzeige bewusst `nicht aktuell bestaetigt` melden.

Diese Aenderungen sind lokal implementiert. Ein NAS-Deployment oder eine Veroeffentlichung auf GitHub ist damit nicht automatisch erfolgt.

## Verifikation und verbleibende Grenzen

- Regressionstests decken Ampel-Zeitraumunabhaengigkeit, Intraday/Tagesschluss, FX-Normalisierung, wiederholte SEC-Artefakte, faire Wiederholungen und den guenstigen Header-Aufruf ab.
- Ein neuer CI-Job verwendet einen isolierten Postgres-16-Container: Alembic bis Head, Preisrevisionen, RS-Aenderungen am selben Datum und atomare Snapshot-Veroeffentlichung.
- Nach Installation von Docker am 14.09. wurde Postgres 16 lokal isoliert gestartet: Migration bis `0014_price_fetch_time` und der echte SQL-Integrationstest bestanden, einschliesslich Screening-Filter und Snapshot-Zusammenfassung. Die NAS-Datenbank wurde dabei nicht verwendet.
- Im Python-3.12-Backend-Image: 502 Tests bestanden, drei uebersprungen (zwei optionale externe Referenzdatei-Tests und der separat ausgefuehrte Postgres-Test). Der Referenzdatei-Pfad funktioniert nun auch im flachen Container-Dateisystem, ohne private CSV-Dateien ins Image zu kopieren.
- Frontend-Abhaengigkeiten wurden nach npm-Sicherheitspruefung aktualisiert: Next.js und eslint-config-next 16.3.5, PostCSS 8.5.28, sharp 0.35.4 sowie kompatible transitive Updates. `npm audit` meldet danach keine bekannten Schwachstellen. CI und Frontend-Dockerfile installieren reproduzierbar mit `npm ci`.
- Beide Docker-Images wurden lokal erfolgreich gebaut. Ruff, ESLint und Typecheck bestanden. Frontend-Container lieferte `/market`, `/stocks` und `/portfolio` mit HTTP 200; Health und Datenqualitaets-Summary funktionierten ueber den Next.js-Proxy zum Backend. Ohne Gesamtdiagnose meldet die isolierte Testinstallation korrekt `limited`, nicht eine erfundene Freigabe. Diese Start-/API-Tests ersetzen keinen vollstaendigen Browser- oder NAS-Lasttest.
- Fehlende historische Kurse delisteter oder falsch zugeordneter Instrumente werden durch diese Korrekturen nicht herbeigezaubert. Ein gezielter historischer Backfill fuer geschlossene Positionen bleibt erforderlich, um solche Depotkurven vollstaendig zu machen. Bis dahin bleibt die Einschraenkung sichtbar.
- ETF-/Provider-spezifische `nicht anwendbar`-Faelle und vollstaendige Fundamentalhistorien brauchen weiterhin eine fachliche Unterscheidung von temporaeren Fehlern. Die Wiederholungssteuerung verhindert Starvation, garantiert aber keine beim Provider nicht verfuegbaren Daten.
- Die 13F-Bulkquelle kann hinter einer bereits faelligen Berichtsperiode liegen. Dann wird die alte Periode als veraltet angezeigt, auch wenn der Quellencheck erfolgreich war. Eine alternative Einzelmeldungs-Pipeline ist hiermit nicht implementiert.
- Vorlaeufige Tageskurse duerfen weiter fuer Intraday-Anzeigen verwendet werden. Die ausdrueckliche Tagesschluss-Sperre betrifft die Marktampel; sie ist keine pauschale Umstellung aller Live-Aktiensignale auf Schlusskursalarme.
