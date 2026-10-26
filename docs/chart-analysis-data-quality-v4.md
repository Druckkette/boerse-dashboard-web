# Chartanalyse: Kursqualität und sichere Teilabschnitte (v4)

Der Scan verwirft eine Aktie nicht mehr vollständig, wenn eine einzelne Stelle
in ihrer bis zu 850 Kalendertage langen Historie auffällig ist. Jeder saubere,
zusammenhängende Abschnitt mit mindestens 25 abgeschlossenen Handelstagen wird
mit den unveränderten Musterregeln aus Kapitel 4.2 geprüft.

## Grenzen der Auswertung

- Ungültige OHLC-Werte, ungültiges Volumen und sämtliche Einträge eines doppelt
  belegten Datums unterbrechen die Auswertung. Fehlerhafte Kerzen erscheinen im
  Chart als leere Stellen; Preise werden weder geschätzt noch passend gemacht.
- Eine Lücke über zehn Kalendertage und eine Schlusskursänderung über 60 Prozent
  trennen Abschnitte. Beide gültigen Kurse bleiben erhalten. Ein großer Sprung
  allein beweist keinen Datenfehler. Exakt 60 Prozent lösen keine Grenze aus.
- Muster einschließlich ihrer Volumenbasis und ihres späteren Status werden nur
  innerhalb eines Abschnitts bestimmt. Kein Muster überspannt eine Unterbrechung.
  Endet ein Abschnitt vor der letzten Kursbeobachtung, tragen seine Treffer eine
  sichtbare historische Kennzeichnung und eine Warnung über den begrenzten Status.
- Alle Gründe werden erhoben. Zusammengefasste Scanhinweise zählen betroffene
  Aktien je Grund; eine Aktie kann in mehreren Kategorien erscheinen.
- `analysed_count` enthält vollständig und teilweise auswertbare Aktien.
  `partial_count` ist eine Teilmenge davon. `skipped_count` umfasst nur Aktien ohne
  ausreichend langen sauberen Abschnitt. Alte Scans bleiben bis zum erfolgreichen
  Abschluss eines neuen Scans erhalten und werden als veraltet markiert.

## Begrenztes Nachladen im Worker

Ein über die Oberfläche gestarteter Scan prüft zuerst die Kursqualität und lädt
gezielt auffällige Historien neu. Bekannte OHLC-Fehler haben Vorrang vor fehlenden
Kursen. Standardmäßig sind höchstens 100 Ticker und 300 Sekunden für diese Phase
vorgesehen. Ein Providerabruf hat zehn Sekunden Request-Timeout; ein laufender
Abruf kann die Phasengrenze geringfügig überschreiten. Rate-Limits stoppen weitere
Versuche im selben Lauf. Aufgeschobene Ticker kommen bei späteren Scans dran.

Der Auftrag `scan_chart_patterns` kann für einen gezielten Wartungslauf
`repair_limit` (serverseitig maximal 2.500) und `repair_seconds` (maximal 1.800)
angeben. `repair_prices=false` führt eine reine Cacheauswertung durch. Direkte
Serviceaufrufe sind standardmäßig ebenfalls netzwerkfrei. Der Worker hat ein
Gesamtlimit von zwei Stunden, Fortschritt und Abbruchprüfung bleiben aktiv.

Ein neuer Abruf darf die bestehende Preisbasis nur ersetzen, wenn mindestens 25
gültige Tageskerzen vorliegen, alle bereits gecachten Tage des Prüfzeitraums
enthalten sind und die Reihe ausreichend dicht und aktuell ist. Bei leeren,
verkürzten, widersprüchlichen oder nicht erreichbaren Quellen bleibt der Cache
unverändert. Neuabrufe berücksichtigen die gesamte gemeinsame Historie statt
einer einseitigen Änderung von Kursen rund um einen Split.

Yahoo-OHLC werden niemals erneut mit `split_adjustment_factor` multipliziert.
Gespeicherte Splitereignisse in zeitlicher Nähe eines Sprungs werden als Evidenz
angezeigt; sie rechtfertigen keine automatische Preisumrechnung. Bleibt ein Sprung
im vollständigen Neuabruf bestehen, bleibt er eine Abschnittsgrenze mit dem
Hinweis auf die erneute Quellenbeobachtung. Seine Ursache ist damit nicht bewiesen.

Versuche werden vor dem Abruf gespeichert. Fehler erhalten mindestens einen Tag
Wartezeit, gespeicherte vollständige Neuabrufe mit weiterhin auffälligen Daten
sieben Tage. Ein abgebrochener Scan veröffentlicht keine halbfertige Trefferliste;
bereits abgeschlossene, geprüfte Kursreparaturen bleiben jedoch im Cache erhalten.
Deshalb vor dem ersten produktiven Wartungslauf die Datenbank sichern.

## Prüfung

Gezielte Tests prüfen gültige Cups vor und nach Fehlerstellen, unterbrochene Cups,
fehlende Kurse, alle OHLC-Fehlerarten, doppelte Daten, Volumen, Lücken, exakte
Grenzwerte, unveränderte historische Geometrie, Split-Evidenz ohne Zukunftsdaten,
unvollständige Neuabrufe, unveränderte Preise, Cooldowns, Budget, Rate-Limits und
atomare Veröffentlichung. Browserfälle prüfen die filterbare Diagnose mit
50 Einträgen je Seite und weiterhin sichtbare Muster in teilweise nutzbaren Charts.

Die eingefrorenen Internetbeispiele behalten ihre bisherigen Ergebnisse:
2/5 ursprüngliche und 1/4 zusätzliche positive Quellenfälle; der 66 Prozent tiefe
ROKU-Gegenfall bleibt ausgeschlossen. Diese Änderung verbessert Datenabdeckung
und Fehlerbehandlung, liefert keine neue Schätzung der allgemeinen Musterpräzision.
