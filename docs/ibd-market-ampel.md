# IBD Logik und Powertrend

Die Settings-Auswahl gilt global; S&P 500, Nasdaq Composite und Russell 2000 werden
jeweils aus ihrer eigenen Kurs-/Volumenhistorie berechnet. `current` bleibt der
Standard. Ein Wechsel benötigt weder Migration noch Worker-Neustart. Die
Berechnung verwendet für bestätigte Zustände nur abgeschlossene US-Handelstage;
Intraday-Vorschauen ändern diese Zustände nicht.

Die Startseite verwendet dieselbe gewählte Trendberechnung wie die Marktseite.
Ihr kurzer Cache berücksichtigt die Variante; ein Settings-Wechsel benötigt
keinen neuen Worker-Snapshot. Die Snapshots speichern Variante, Regelversion,
FTD-Negation und den Powertrend-Zustand für spätere historische Auswertungen.

Für IBD-Bestätigungen müssen Open, High und Low tatsächlich vorliegen und zur
Tageskerze passen. Fehlende Werte werden nicht als belegte Tagestiefs behandelt.
Eine unvollständige Kerze unterbricht den Powertrend-Low-Streak und bestätigt
keine neue Ampelphase. Ein bereits formal aktiver Powertrend bleibt anhand der
bekannten Schlusskurs-Durchschnitte bestehen; die Datenlücke wird angezeigt.
Volumenlose Tage bestätigen keinen volumenabhängigen Startschuss.

Yahoo kann das Tagesvolumen nach dem ersten Abruf nach Börsenschluss noch
korrigieren. Deshalb lädt ein eigener Index-Refresh Dienstag bis Samstag um
01:05 Uhr (Europe/Berlin) die vier Indizes und ihre ETF-Proxys erneut, mit sieben
Kalendertagen Überlappung. Er läuft auch, wenn Smart Repair die Kurse bereits
als frisch einstuft, und übernimmt dabei spätere Volumenkorrekturen.

Die Journal-Rekonstruktion verwendet eine für denselben Handelstag gespeicherte
Variante, sofern sie belegt ist. Fehlt dieser Nachweis, wird die ausgewählte
heutige Variante auf historische Kurse angewandt und ausdrücklich als solche
Rekonstruktion gekennzeichnet. Die damalige Auswahl wird dabei nicht behauptet.
Bereits archivierte Kontexte bleiben unverändert. Varianten und Regelversionen
sind Teil des Rekonstruktions-Fingerprints.

## Regelabgleich

Die Variante `ibd` erhält die Buchkette Ankertag → Startschuss → Grün →
Aufwärtstrend. Sie ist keine vollständige Nachbildung von IBD Market Pulse.

- Korrekturbeginn: eigene Näherung, mindestens 8% Rückgang vom Hoch der letzten
  60 Sitzungen (einschließlich heute) oder Schluss unter 50-SMA bei mindestens
  3% Rückgang bzw. drei aktiven Distributionstagen. Diese Schwellen sind keine
  veröffentlichten universellen IBD-Grenzwerte und garantieren keine identische
  historische Market-Pulse-Einstufung.
- Rally Day 1: erster positiver Tag oder Schluss in der oberen Kerzenhälfte nach
  Korrekturerkennung. Bodenmarke ist dessen eigenes Tagestief.
- Startschuss: frühestens Rally Day 4 (Ankertag zählt als Tag 1), mindestens +1%,
  höheres Volumen als am Vortag, Rally-Day-1-Tief intakt. +1% und die zusätzliche
  Grün-/Aufwärtstrend-Bestätigung bleiben die vereinbarten Buchregeln.
- FTD negiert: **bestätigter Schlusskurs** strikt unter dem FTD-Tagestief.
  Eine Intraday-Unterschreitung mit Schluss auf/über der Marke ist ein separates
  Warnsignal (`ftd_intraday_undercut`), keine dauerhafte Negation.
  `gelb_startschuss` und `gruen` wechseln bei intaktem Rallytief zu
  `gelb_rally_unter_druck` (Gelb, „Rally unter Druck“). Erklärung:
  „Follow Through Day negiert. Der Rallyversuch bleibt aktiv, solange das
  maßgebliche Rallytief hält.“ Datum/Tief des negierten FTD bleiben sichtbar.
  Reine Erholung oder Zeitablauf reaktivieren diesen FTD nicht.
- Neuer FTD: im selben Rallyversuch ab Rallytag 4, mindestens +1% und Volumen
  über Vortag, bei intaktem Rallytief. Anker und Tageszählung bleiben erhalten;
  Datum/Tief des neuen FTD ersetzen die aktuellen Bestätigungsmarken. Die
  historischen Tagespunkte behalten die frühere Negation. Es folgt wieder
  `gelb_startschuss`, danach die bisherigen Grün-/Aufwärtstrend-Bestätigungen.
- Nach `aufwaertstrend` führt eine FTD-Negation zunächst zu
  `gelb_trend_unter_druck`; in einer bestehenden Trenddruckphase bleibt die
  Negation gespeichert. Die bisherige qualifizierte Erholung eines bereits
  bestätigten Trends bleibt möglich, ohne den alten FTD wieder gültig zu machen.
- Harte Rot-Regeln haben Vorrang vor Negation oder neuem FTD. In frühen aktiven
  Rallyphasen gelten Rallytiefbruch, bestätigte Abwärtsstruktur, 50-SMA-Bruch mit
  mindestens vier Distributionstagen, ein neuer Schlusskursbruch der 200-SMA
  von oben und mindestens 10% Rückgang vom Hoch seit dem FTD. Ein FTD unter
  200-SMA allein bleibt erlaubt. Im bestätigten Trend und dessen Druckphase
  bleiben die bisherigen Schwellen erhalten: Schluss unter 200-SMA, 10%
  Rückgang vom eigenen Trendhoch, 50-SMA-Bruch mit vier Distributionstagen
  oder bestätigte Abwärtsstruktur. Diese Rot-Schwellen sind Dashboard-Regeln.
- Rallyversuch beendet: Tagestief unterschreitet Rally-Day-1-Tief. Nach einem
  bestätigten Aufwärtstrend beendet auch eine harte Rückstufung auf Rot den
  bisherigen Zyklus. Der nächste qualifizierte Ankertag beginnt einen neuen
  Rallyversuch; die Wartezeit bis Rally Day 4 startet erneut. Eine bloße
  Druckphase oder ein negierter früher FTD erhält dagegen den intakten Anker.
  Die IBD-Anzeige verwendet nur die Marken des aktuellen Zyklus und übernimmt
  kein FTD-Tief aus einer abgeschlossenen Rally. Regelversion: `trend_ampel_v4`.

## Powertrend als Zusatzstatus

Websters vier Startbedingungen müssen gleichzeitig vorliegen:

1. Tagestief strikt über 21-EMA für mindestens zehn aufeinanderfolgende Sitzungen.
2. 21-EMA strikt über 50-SMA für mindestens fünf aufeinanderfolgende Sitzungen.
3. Heutige 50-SMA höher als am vorherigen Handelstag.
4. Schlusskurs mindestens so hoch wie am Vortag.

Der Zustand bleibt anschließend gespeichert, bis 21-EMA strikt unter 50-SMA
liegt. Gleichheit beendet ihn nicht. Später entfallende Startbedingungen ändern
weder das Startdatum noch automatisch den formalen Aktivstatus. Die Anzeige
zeigt deshalb „formal aktiv“, auch wenn die Buchampel noch keinen Aufwärtstrend
bestätigt hat. Der Powertrend überspringt keine Buchphase.

`under_pressure` ist eine zusätzliche Dashboard-Risikokennzeichnung, keine fünfte
IBD-Startbedingung: Rot/Trend unter Druck, drei Schlusskurse unter 21-EMA oder
Schluss mehr als 0,5 ATR21 unter 50-SMA. Ein solcher Zustand bleibt formal aktiv,
kann sich wieder erholen und sollte nicht mit dem Ende des Powertrends verwechselt
werden. Es wird nicht das vollständige Market-School-Expositionsmodell oder jede
historische Sonder-/Circuit-Breaker-Regel implementiert.

## Quellen und Grenzen der Prüfung

Abgeglichen mit dem Chat „Powertrend integrieren“ im Projekt BoB Marketing und
„Powertrend Konzept erklären“ im Buchprojekt. Im Buchprojekt sind unter anderem
`MarketSchool.pdf` und `WRO 1-44.txt` hinterlegt. Die PDF-Vorschau/der Download
waren bei dieser Prüfung nicht verfügbar. Für den Originalabgleich wurde die
lokal vorhandene Transkriptsammlung `WRO1-21 zusammen.txt`, darin Websters
„WRO #18 Power Trend, Webby Rambles On (Slight Return)“, verwendet. Sie bestätigt
die vier Bedingungen, den Vortagsvergleich der SMA50 und das grundsätzliche Ende
bei negativer Kreuzung; Webster erwähnt darin auch nicht vollständig erläuterte
Ausnahmen. Es wird daher keine vollständige Prüfung der unzugänglichen PDF behauptet.

Zusätzliche öffentliche Primärquelle zum formalen Ende:
[IBD/MarketSurge Stock Guide, Mid-Year 2024, S. 17](https://marketsurge-files.investors.com/2024/07/StockGuide-Mid-year-2024.pdf).

Regressionstests decken Intraday-Bruch, Rally-Erhalt, erneuten FTD, Erholung nach
Negation, echte OHLCV-Indikatorberechnung und fortbestehenden Powertrend bei
entfallenen Startbedingungen ab. Fehlende Daten erzeugen keine Aktivierung.

## Quellenabgleich FTD und Regelversion 4

Die lokal vorhandene automatische Transkription `WRO1-21 zusammen.txt`,
**WRO #10 „Follow Through Day Part 1“**, unterscheidet ausdrücklich:
Rally-Day-1-Tief intraday unterschritten → Rallyversuch gescheitert
(Zeilen 3630–3678); FTD-Tief intraday unterschritten → Signal noch intakt,
Schluss darunter → FTD-Signal negiert, häufig neuer FTD erforderlich
(Zeilen 4045–4070; ergänzend 6554–6574). Dies ist eine paraphrasierte
Auswertung der Primärtranskription, keine Behauptung vollständiger offizieller
IBD-Market-Pulse-Regeln. Die gelben Farben und die getrennten frühen/stabilen
Druckphasen sind ausdrücklich unsere Dashboard-Interpretation.

Historische Kursreihen werden mit `trend_ampel_v4` neu berechnet. Ursprüngliche
Snapshots und archivierte Journal-Kontexte bleiben mit ihrer damaligen
Regelversion erhalten; Rekonstruktionen verwenden einen neuen versionierten
Fingerprint. Ein alter IBD-Snapshot wird ohne verfügbare Kursrekonstruktion
nicht als aktuelle Version ausgegeben. Der Startseiten-Cache enthält die
Regelversion. `current` und `powertrend_v2` behalten ihre Berechnungsregeln.
Nur abgeschlossene Handelstage und echte vollständige OHLC-Kerzen bestätigen
Negationen; fehlendes aktuelles oder vorheriges Volumen erlaubt keinen neuen
FTD. Intraday-Kurse ändern keine bestätigte Phase.
