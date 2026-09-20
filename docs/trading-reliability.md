# TR-Handelstagebuch, Stop-Alarme und Betriebsstatus

## Ursachen und Änderungen

Der bisherige TR-Import rekonstruierte Positionen nur aus der aktuellen CSV und
verknüpfte historische Ausführungen mit der aktuell offenen Tickerposition. Er erzeugte
keine Tagebucheinträge. Die Ersetzen-Option konnte außerdem Positionen anderer Broker
schließen. Der neue Import verarbeitet die gespeicherte Vereinigung aller TR-Ausführungen
chronologisch unter einer PostgreSQL-Transaktionssperre. Einzelne Ausführungen bleiben
unverändert; FIFO ordnet Teilverkäufe mehreren Käufen zu, inklusive Kauf-/Verkaufskosten.
Ein Wiedereinstieg erhält einen eigenen Positionszyklus. Tagebucheinträge sind über eine
unique source_transaction_id eindeutig; Notizen und ursprüngliche Snapshots bleiben
bei Wiederholungen erhalten. Notizänderungen überschreiben keine Brokerdaten oder
FIFO-Ergebnisse. Überträge erzeugen keine erfundenen Kaufbewertungen.

Anonyme CSV-Zeilen werden nach Ausführungsinhalt und Vorkommenszahl abgeglichen,
nicht nach ihrem veränderlichen globalen CSV-Zeilenindex. Explizite Broker-IDs haben
Vorrang. Ohne eindeutige Broker-ID bleiben tatsächlich identische Ausführungen in
unterschiedlichen Teilreports prinzipiell mehrdeutig. Bestehende Ausführungsdaten werden
bei widersprüchlichen späteren Reports nicht automatisch korrigiert. Ein Brokerkonto
wird wie bisher vorausgesetzt; unterschiedliche TR-Konten dürfen nicht vermischt werden.

Historische Verkäufe verwenden die bestehende Sell-Engine und deren heutige
Standardregeln ausschließlich auf gespeicherten Kursen **vor dem Verkaufstag**.
Mindestens 200 Kurs-/Benchmark-Tage und gegebenenfalls historische
FX-Daten sind erforderlich. Bei abweichenden Feiertagen wird ausschließlich der letzte
tatsächlich gespeicherte Kurs am oder vor dem Kurstag verwendet, höchstens vier
Kalendertage alt. Die betroffenen Kurstage und Ursprungsdaten sind in UI und PDF
ausgewiesen; zukünftige Kurse und größere Lücken sind ausgeschlossen. Fehlende Einstandsbasis, Corporate Actions mit unbekannter
Kostenbasis oder fehlende Kursdaten ergeben ausdrücklich keine Bewertung. Es werden
keine heutigen Kurse oder nicht gespeicherten damaligen manuellen Entscheidungen
unterstellt. Diese nachträgliche Bewertung ist als solche gekennzeichnet. Gebühren und
Steuern werden als Belastungen behandelt; separate Steuererstattungen sind keine
automatische Korrektur einer Verkaufszuordnung. Tagebuch-Ergebnisse werden in der
Originalwährung gespeichert; EUR-Ergebnisse nur bei tatsächlicher EUR-Ausführung.

Der bestehende Monitor prüfte ATR-Abstände und Trendlinien, aber nicht separat den
Positionsstop. stop_alerts vergleicht aktuelle Live-Kurse mit dem tatsächlichen Stop in
derselben Währung. Nur vorhandene aktuelle FX-Kurse werden verwendet. Der dauerhafte
Zustand ist positionsbezogen und wird nicht täglich zurückgesetzt: einmalige Meldung
bis zur Erholung um mehr als 0,5 % über den Stop; Stopänderungen aktivieren eine neue
Prüfung. Nur bestätigte Zustellung verriegelt den Alarm. Bei Fehlern gilt eine
15-Minuten-Wiederholungspause. Parallele Worker werden je Position gesperrt; ohne
Zustandsspeicher wird nicht gesendet. Langsame Zustellung verschiebt restliche Stops
auf den nächsten Monitorlauf. Ein externer Versand und ein DB-Commit können technisch
nicht atomar erfolgen; ein Prozessabbruch nach Versand oder eine verlorene
Providerbestätigung kann eine spätere Wiederholung verursachen.

Im Projekt existiert **Pushover**, kein separater „Pushify“-Client. Deshalb wird die
bestehende Pushover-Konfiguration genutzt. Die Tests versenden keine echten Nachrichten.
Positionsmonitor und Pushover müssen in den Einstellungen aktiviert sein.

Die Marktübersicht rief zuvor die vollständige Marktampel auf; deren Bestätigung
historischer Tageskerzen berechnete für jede Kerze erneut den Börsenkalender.
Die Übersicht berechnet jetzt nur ihre benötigten Trenddaten. Die Ampel bestimmt die
letzte abgeschlossene Sitzung einmal pro Anfrage, ohne ihre Historie oder Zyklusregeln
zu verkürzen. Ein lokaler Vergleich mit 1.800 Kerzen ergab für diesen Teilschritt
ca. 0,824 s vorher / 0,001 s nachher (keine End-to-End-Garantie für das NAS).
Vor der Änderung wurden am NAS rund 17 s für die Ampel und 26 s für die Diagnose
gemessen. Volatilität, Intermarket und Sektorrotation werden isoliert geladen;
Ausfälle werden als Teilverfügbarkeit samt component_errors kenntlich gemacht.
Bei fehlgeschlagener Hintergrundaktualisierung bleiben vorhandene Frontenddaten
sichtbar, mit Fehlerhinweis. Es wurden keine Timeouts verlängert.

Der Header las zuvor ausschließlich eine beim Öffnen der Settings gespeicherte
Gesamtdiagnose. Nach fünf Minuten oder ohne Diagnose fiel er pauschal auf
„Eingeschränkt“ zurück. Jetzt ermittelt system_quality den aktuellen Zustand direkt:
- Pflichtquellen fehlen / Datenbank nicht erreichbar: Fehler (blocked).
- Pflichtquellen veraltet: Eingeschränkt (limited).
- Pflichtquellen aktuell: OK (trusted).

Pflichtquellen sind Kurse offener Positionen, der Marktindex (^GSPC, ersatzweise SPY),
Marktsnapshot und Marktbreite. Positionskurse folgen der vorhandenen Intraday-
Freshness; tägliche Marktprodukte benötigen die letzte abgeschlossene Börsensitzung,
auch an Wochenenden/Feiertagen. Quartalsfundamentals, 13F und persönliche Stops bleiben
in der ausführlichen Diagnose, verursachen aber keinen globalen Betriebsausfall.
Die API liefert sources/reasons mit Datenstand; der Header aktualisiert minütlich.
Ein fehlgeschlagener Statusabruf wird ausdrücklich als nicht verfügbar angezeigt.
Der Status beschreibt Datenverfügbarkeit, keine Empfehlung zum Handeln.

Bereits in USD gespeicherte Altpositionen behalten ihre Währung, ihren Stop und die
in ihrem bisherigen Einstand enthaltene Umrechnungsbasis. Weitere Käufe aktualisieren
den gewichteten Einstand im Verhältnis zur nativen Broker-Kostenbasis. Die exakten
Ausführungsergebnisse im Journal bleiben davon unabhängig in Originalwährung.

## PDF und Datenmodell

Die A4-ReportLab-Lösung ist in [pdf-reports.md](pdf-reports.md) beschrieben.
Die neuen Ausführungs-/Bewertungsfelder werden in Aktien- und Trade-Reports
aufgenommen. Ein Trade-Report umfasst nur den verknüpften Positionszyklus.
Interne Datenbank-IDs werden nicht gedruckt; fehlende Bewertungen werden nicht ersetzt.
Gebühren, Steuern, Einstand, Nettoerlös und FIFO-Ergebnis sind deutsch beschriftet.

## Dateien

- backend/alembic/versions/0016_trade_journal_import_links.py und app/db/models.py:
  optionale Verknüpfungen, native Währung, Ergebnisse, Bewertungs-Snapshot.
- backend/app/domain/portfolio/trade_ledger.py, repositories/tr_import.py,
  repositories/portfolio.py, services/portfolio.py: Import und Positionsprojektion.
- backend/app/services/historical_sell.py, trade_journal.py, schemas.py und
  frontend/src/features/trade-journal/trade-journal-page.tsx: Bewertung und Anzeige.
- backend/app/services/stop_alerts.py, domain/sell/service.py,
  workers/tasks/position_atr_monitor.py: Stop-Zustand und Zustellung.
- backend/app/services/market.py, market_calendar.py und frontend/src/features/market:
  Kalenderberechnung, Fehlerisolation, Aktualisierungszustand.
- backend/app/services/system_quality.py, settings.py sowie
  frontend/src/components/ui/header-tools.tsx: aktueller Betriebsstatus.
- backend/app/reports/collect.py, pdf.py: erweiterter Bericht.
- backend/app/services/backfill_trade_journal.py, infra/update-nas.sh: Bestandsnachtrag.

## Prüfung und NAS-Update

Geprüft mit Python 3.12 und separatem PostgreSQL 16: FIFO, Bruchteile, Teil-/Vollverkauf,
Wiedereinstieg, Gebühren, fehlende Historie, anonyme IDs, parallele/wiederholte Imports,
nachgereichte ältere Käufe, Überträge, Erhalt manueller Notizen und konkurrierende
Stop-Zustellungen. Weitere Tests prüfen vorhandene Sell-Engine, historische SQL-Grenze,
JSON-Serialisierung, Wiederanlauf/Erholung, Freshness, Kalenderaufwand und optionale
Marktfehler. Bestehende PDF-Tests prüfen A4, Vollständigkeit, mehrseitige Tabellen,
Nullwerte und reproduzierbare Bytes bei identischem Reportmodell. Ein PDF aus den
Testausführungen wurde gerendert und visuell kontrolliert.

Der NAS-Updater führt nach den Migrationen den idempotenten Bestandsnachtrag aus:
`python -m app.services.backfill_trade_journal`. Er liest nur bereits gespeicherte
TR-Ausführungen; keine neue CSV ist erforderlich. Eine Wiederholung legt keine
zusätzlichen Ausführungen oder eindeutig verknüpften Tagebucheinträge an.
Vorhandene manuelle Tagebucheinträge werden nur bei genau einem exakten Treffer
übernommen, sonst erhalten die Broker-Ausführungen eigene Einträge.

Migration 0016 wurde auf der isolierten Testdatenbank vor-/zurück-/vorwärts getestet.
Das Downgrade entfernt die neuen Verknüpfungs-/Bewertungsfelder und ist kein
Produktions-Rollback ohne Datensicherung. Der normale Updatepfad ist ausschließlich
vorwärts. Der NAS-SSH-Zugang wurde abgelehnt; das lokale Testresultat bestätigt
keine erfolgte NAS-Bereitstellung.


## Nachprüfung am 20.09.2026

Die NAS-Bereitstellung 271d691 war erfolgreich; Migration, Postgres/Redis und PDF
wurden über die API geprüft. Historische EUR-Verkäufe scheiterten aber an der strikt
identischen Kalenderdatums-Zuordnung von Aktien- und FX-Kursen. Beispiel MRVL:
Aktienkurs am 21.04.2025, letzter gespeicherter EUR/USD-Kurs am 17.04.2025.
Die nun begrenzte historische As-of-Zuordnung behebt diese Kalenderlücke ohne neue
Kurswerte zu erfinden. Versionierte Bewertungen werden beim nächsten NAS-Update
neu berechnet; weiterhin fehlende Bewertungen werden bei späteren Nachträgen erneut
versucht. Fehler unterscheiden fehlende Daten und tatsächliche Engine-Exceptions.
Der Nachtrag gibt zusätzlich Bewertungszahlen und verbleibende Gründe aus.

Bei erneuter Messung im warmen NAS-Prozess lagen Ampel und Diagnose bei rund
0,55 Sekunden statt 13–19 Sekunden unmittelbar nach Bereitstellung. Ein lokaler
paralleler Kaltstart reproduzierte vier Kalenderkonstruktionen bei vier Anfragen:
functools.lru_cache verhindert konkurrierende Erstberechnungen nicht. Eine Sperre
serialisiert jetzt den ersten Kalenderaufbau; der FastAPI-Lifespan lädt ihn vor
Annahme von Anfragen. Datenabhängige Ampelregeln, Timeouts und Freshness bleiben
unverändert. Tests prüfen parallele Erstzugriffe sowie die Startup-Reihenfolge.

Neue Regressionstests decken Osterfeiertagslücke, Ausschluss zukünftiger oder zu
alter FX-Werte, ungültige Kurse und die einmalige Neuberechnung älterer
Bewertungsversionen ab. Pushover wurde lesend geprüft: aktiviert, Schlüssel
konfiguriert, Dry-Run aus, vorhandene bestätigte Zustellungen. Es wurde kein
künstlicher Stop gesetzt und keine Testnachricht verschickt.
