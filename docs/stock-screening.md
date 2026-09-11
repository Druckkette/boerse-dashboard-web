# Universumsbewertung

Unter **Aktien > Aktienbewertung Ranking** startet **Universum bewerten** die
Bewertung aller aktiven Mitglieder des gespeicherten Aktienuniversums
`us_common_stocks`. Es gibt keine Vorauswahl nach RS und keine Begrenzung auf
120 oder 500 Kandidaten.

Die Bestenliste verwendet dieselben Scores, Gewichtungen und Kriterien wie die
Aktien-Detailbewertung. Fehlende Fundamental-Daten werden sichtbar als fehlend
markiert; der bestehende Gesamtscore behaelt seine fachliche Berechnung bei.
Mit Mindest-Scores, Mindest-RS, maximaler Warnungsanzahl und frei waehlbaren
Pflichtkriterien laesst sich die Liste eingrenzen. Alle Pflichtkriterien muessen
erfuellt sein. Einzelne fehlende Kriterien bestehen den Filter nicht.

**Bestenliste exportieren** liefert alle Treffer der aktuellen Filterung als
UTF-8-CSV mit Semikolon, Teilscores, Kursstand, Datenabdeckung und Checkliste.
Die Seitenauswahl begrenzt den Export nicht. Der Ticker verlinkt zur Detailanalyse.

## Ausfuehrung und Ressourcen

- Bestehender Job `refresh_stock_assessments`, normale Worker-Queue,
  Concurrency 1. Der Schutz vor parallelen globalen Schwerjobs bleibt aktiv.
- Pakete von 40 Aktien. SQL-Abfragen lesen je Paket die Kurse und nur die jeweils
  neuesten RS-, Fundamental- und 13F-Snapshots sowie Earnings-Termine.
- Keine Yahoo-, FMP- oder SEC-Downloads waehrend der Bewertung. Datenbeschaffung
  bleibt Aufgabe des Smart Refresh. Nicht bewertbare Aktien werden gezaehlt.
- Ein SHA-256-Fingerprint beruecksichtigt die vollstaendigen verwendeten
  Eingangsdaten, den Bewertungs-Code und das Kalenderdatum. Unveraenderte
  Bewertungen werden bei Wiederholung am selben Tag wiederverwendet.
  Intraday-Kursaenderungen, neue Fundamentals, RS oder 13F loesen Neuberechnung aus.
  Der Kalender ist relevant fuer den Abstand zum naechsten Earnings-Termin.
- Kursgeschichte bleibt erhalten, insbesondere fuer Allzeithoch- und
  Wochenkriterien. Es wird keine Historie erneut heruntergeladen.
- Fortschritt und Abbruchpruefung erfolgen nach jedem Paket.
- Die bisherige Bestenliste bleibt lesbar, bis der neue Lauf atomar publiziert
  wird. Datenbankfehler, Abbruch oder ein komplett leeres Ergebnis ersetzen sie
  nicht. Entfernte Universumsmitglieder verschwinden bei der neuen Publikation.
- Lesen, Filtern und Sortieren erfolgen in Postgres. Pro Seite werden hoechstens
  50 Bewertungen an den Browser geschickt; der explizite CSV-Export umfasst
  alle gefilterten Treffer.
- Der Job ist Teil des bestehenden Smart Refresh um 16:00 und 22:30 Uhr.
  Eine veraltete Tagesauswertung wird beim Smart Refresh auch ohne neue
  Providerdaten erneuert.
- Das Limit fuer einen separaten Bewertungslauf liegt bei 60 Minuten plus
  60 Sekunden fuer den harten Abbruch. Es gibt keine neuen Container und keine
  zusaetzlichen Secrets oder Datenbankmigrationen.

## API

- `POST /api/v1/jobs`: `{"type":"refresh_stock_assessments","payload":{}}`
- `GET /api/v1/jobs/{job_id}`: Fortschritt, Ergebnisse und fehlende Ticker.
- `POST /api/v1/jobs/{job_id}/cancel`: Abbruch.
- `GET /api/v1/stocks/screening`: Zusammenfassung, Kriterienkatalog und 50 Treffer.
- `GET /api/v1/stocks/screening/export`: CSV aller Treffer.

Beide Lese-Endpunkte akzeptieren `min_score`, `min_rs`, `min_fundamental`,
`max_warnings`, `complete_only`, `search`, wiederholtes `required` und `sort`.
`page` ist nullbasiert und gilt nur fuer die JSON-Liste.

Persistenz verwendet die bestehende Tabelle `stock_assessment_snapshots`.
`item_json._input_fingerprint` und `item_json._screening` sind interne
Metadaten und werden nicht als Zeilenfelder an die API ausgegeben.

## Messung

Lokaler synthetischer Test: 100 Bewertungen mit 260 Tageskursen benoetigten
rund 2,3 Sekunden CPU-Zeit; 100 Fingerprint-Pruefungen rund 0,12 Sekunden.
Diese Werte sind keine NAS-Laufzeitgarantie: Kurshistorien, Datenbankort und
NAS-Auslastung beeinflussen die Gesamtdauer. Jeder Job speichert seine tatsaechliche
Dauer sowie die Anzahl berechneter, wiederverwendeter und fehlender Bewertungen.
