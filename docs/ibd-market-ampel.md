# IBD Logik und Powertrend

Die Settings-Auswahl gilt global; S&P 500, Nasdaq Composite und Russell 2000 werden
jeweils aus ihrer eigenen Kurs-/Volumenhistorie berechnet. `current` bleibt der
Standard. Ein Wechsel benötigt weder Migration noch Worker-Neustart. Die
Berechnung verwendet für bestätigte Zustände nur abgeschlossene US-Handelstage;
Intraday-Vorschauen ändern diese Zustände nicht.

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
- FTD negiert: Tagestief unterschreitet das FTD-Tief, auch bei anschließendem
  Schluss darüber. Vor dem Aufwärtstrend geht es zurück zu Rot mit demselben
  Rally-Anker; nach bestätigtem Aufwärtstrend zunächst zu Trend unter Druck.
  Ein negierter FTD wird bei späterer Erholung nicht erneut als gültig behandelt.
- Rallyversuch beendet: Tagestief unterschreitet Rally-Day-1-Tief. Die bisherigen
  Risikoregeln können die Ampel schon vorher auf Rot zurückstufen, erhalten dann
  aber den intakten Rally-Anker für einen neuen Startschuss.

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
