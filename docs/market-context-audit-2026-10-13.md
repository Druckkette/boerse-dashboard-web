# Prüfung der Marktphase und Informationsscores

Stand: 13.10.2026. Geprüfter Ausgangsstand: `0e37d437897a1299f0388fc41426108aec4841db`. Korrigierte Scoreversion: `market_context_v2`; Trendampel unverändert `trend_ampel_v5`.

## Ergebnis

Der Ausgangsstand war nicht vollständig fehlerfrei. Die Trennung der fünf Informationsscores von der verbindlichen Trendampel funktioniert. Bei Datenfenstern, Gewichtung fehlender Beiträge, Equal-Weight-Bestätigung und Beschriftungen gab es jedoch konkrete Fehler bzw. fachliche Inkonsistenzen. Die nachstehenden Korrekturen verändern keine Ampelphase. Bestehende Detailblöcke behalten ihre bisherige Berechnung; strengere Equal-Weight-Fenster gelten gezielt für die neuen Kontextscores.

Die 91 Kriterien-IDs und die Anweisungen in Excel-Spalte F wurden mit dem Zuordnungsmanifest abgeglichen. Vier Texte unterschieden sich nur durch entfernte Leerzeichen am Rand; es fehlte keine Anweisung. Die Arbeitsmappe wurde nicht verändert.

## Festgestellte Probleme und Korrekturen

| Befund im Ausgangsstand | Auswirkung | Korrektur |
|---|---|---|
| Teilweise verfügbare Unterscores behielten ihr volles Gruppengewicht | Wenige vorhandene Kriterien konnten das Gewicht fehlender Kriterien übernehmen | Effektives Gruppengewicht = konfiguriertes Gewicht × verfügbarer Kriterienanteil |
| E04 gab für jeden stabilen Zustand 100 Punkte | Auch bestätigter Schutz erhielt einen positiven Bonus | Richtungsbezogene Bestätigung: Rückenwind100, Wachsam50, Schutz0; laufender Wechsel50 |
| Equal Weight prüfte nur die Länge der gesamten Historie | Bestätigungen konnten aus verkürzten 52W-Fenstern stammen | Jeder Bestätigungstag benötigt252 vollständige, aufeinanderfolgende Sitzungen; erste Bestätigung frühestens nach254 Sitzungen |
| Gemeinsame Equal-Weight-Tage übersprangen Datenlücken | Nicht aufeinanderfolgende Beobachtungen konnten eine Bestätigung bilden | Expliziter Sitzungskalender; Lücken und unvollständige OHLC-Daten machen das betroffene Fenster unbekannt |
| VXX wurde bereits nach21 Sitzungen als verfügbar gewertet | Vergleich der EMA21 mit fünf Sitzungen zuvor war noch nicht möglich | Mindestens26 Sitzungen; kombiniertes Regime verlangt zudem sechs aktuelle SPY-Beobachtungen |
| Fehlender Volatilitätspunkt bei gültigen Rohdatenflags erzeugte neutrale Einzelwerte | Unbekannte Daten erschienen als bewertete Neutralität | Fehlender Punkt und unbekannte Zustände sind nicht bewertbar |
| Powertrend war ohne vollständige SMA50-Vorbereitung bewertbar | Kurze Historie wurde als tatsächlicher Zustand „off“ bewertet | Mindestens54 vollständige Sitzungen für fünf gültige SMA50-Vergleiche |
| W01 verlangte nur zehn Kurse; W03 verlangte unnötig60 | W01 fehlte ein Vortagskurs; W03 blieb unnötig lange unbekannt | Beide verlangen elf Sitzungen für zehn Tagesvergleiche; W03 benötigt keine Volumen-SMA50 |
| B10 bezeichnete die zugrunde liegenden Hochs/Tiefs pauschal als20T | Summenfenster und Einzelaktien-Referenz wurden verwechselt | Explizite Trennung:20 Sitzungen Glättung; Hoch-/Tief-Referenz im Altbestand nicht gespeichert |
| W14 beschrieb „fünf Sitzungen seit Hoch“ | Die bestehende Formel zählt das Hoch mit | Korrekte Beschreibung: fünf Beobachtungen einschließlich Hoch; kontinuierlicher Erholungsscore |

## Gewichte und tatsächlicher Einfluss

Die Gruppengewichte bleiben erhalten. Die folgenden effektiven Anteile gelten bei vollständigen Daten. Relative Einzelgewichte wirken innerhalb ihrer Gruppe; ein Gewicht0,25 in einer Gruppe mit nur einem Kriterium bedeutet daher nicht0,25% am Gesamtwert.

| Kennzahl | Gruppenanteile | Effektive Kriterienanteile |
|---|---|---|
| Index | Verkaufsdruck45%; Nachfrage35%; Trendbestätigung20% | W01 22,5%; W03/W04 je11,25%; W02 17,5%; W05/W11 je8,75%; A09/A11 je10% |
| Marktbreite | Teilnahme30%; Momentum20%; A/D15%; Hochs/Tiefs20%; Volumen5%; Schub5%; Erholung5% | B01/B02 je12%; B11 6%; D07 20%; B04 10%; D02 5%; B05 13,33%; B10 6,67%; D03/D04/W14 je5% |
| Powertrend | Status70%; Start/Erholung30% | P05 23,33%; P06 46,67%; der jeweils anwendbare Fortschritt P01 oder P03 30% |
| Equal Weight | Zustand80%; Bestätigung20% | E01 20%; E03 60%; E04 20%; E02 ist Anzeige ohne Zusatzgewicht |
| Volatilität | VIX40%; VXX40%; gemeinsames Regime20% | V01/V02/V04/V05 je20%; V07 10,91%; V06/V08 je3,64%; V09 1,82%; V03 ist Anzeige |

Bei fehlenden Beiträgen gilt jetzt: Unterscore = gewichteter Mittelwert vorhandener Kriterien. Sein effektives Gruppengewicht ist das konfigurierte Gruppengewicht multipliziert mit dem verfügbaren Anteil seiner relativen Einzelgewichte. Der Gesamtwert ist der damit gewichtete Mittelwert. Unter50% verfügbarer Gesamtgewichtung wird kein Gesamtwert ausgegeben.

Beispiel: Gruppe A hat60% Gewicht, aber nur25% ihrer Kriteriengewichte sind verfügbar. Sie erhält effektiv15%. Eine vollständig verfügbare Gruppe B mit40% behält40%. Der Gesamtwert verwendet15:40; vorher verwendete er60:40. Fehlende Daten werden dadurch weder als Null gewertet noch an einzelne Restkriterien übertragen.

## Fachliche Beurteilung

**Index:** Die Gewichtung eignet sich als Beschreibung der Kursqualität. W01 und W02 haben gemeinsam40% Einfluss und sind teilweise korreliert. Auch W03/W04/W11 teilen sich Volumendaten. Der Indexscore ist deshalb kein Bündel acht unabhängiger Beweise. A09 hat maximal fünf Punkte Zusatzwirkung gegenüber seinem neutralen Zustand50; A11 kann zehn Punkte abziehen. Das ist vertretbar, weil die Ampel selbst verbindlich bleibt. Die Warnungen sind überwiegend binär; bestätigtes Umschalten kann sichtbare Sprünge erzeugen.

**Marktbreite:** Teilnahme30% und Hochs/Tiefs20% bilden eine sinnvolle Hälfte des Scores. D02/D03/D04 bleiben mit je5% klein. McClellan20%, A/D15% und Deemer5% verwenden teilweise dieselben Advancer-/Decliner-Daten; gemeinsam sind das40%. Das ist eine bewusste Betonung des Breitenmomentums, keine statistische Unabhängigkeit. B05/B10 glätten dieselben NH/NL-Zählungen unterschiedlich und teilen sich daher eine20%-Familie. W14 misst die Erholung des ausgewählten Index; die Zuordnung zur Marktbreite folgt ausdrücklich der Excel und ist im Dashboard benannt.

**Powertrend:**70% formaler Zustand und30% Vorbereitung sind nachvollziehbar. Aktiv mit intakten Bedingungen ergibt76,67. Ein ausgeschalteter Powertrend mit vier vorbereiteten Bedingungen erreicht höchstens65; dies ist ein konstruktiver Vorbereitungsscore, keine Aktivierung des formalen Powertrends. Unter Druck liegt der mögliche Bereich bei11,67–41,67. Der ursprüngliche Status bleibt separat sichtbar.

**Equal Weight:** Nach Korrektur ergeben stabile Zustände70/50/10 für Rückenwind/Wachsam/Schutz. Bestätigung erhöht einen negativen Zustand nicht mehr. Die Bestätigung ist weiterhin aus denselben Kursen abgeleitet und deshalb kein unabhängiges Signal. Während eines noch unbestätigten Wechsels bleibt der bisherige Zustand bestehen und der Bestätigungsbeitrag neutral.

**Volatilität:**40/40/20 begrenzt den zusätzlichen Einfluss des abgeleiteten Regimes. VIX und VXX sowie das gemeinsame Regime sind korreliert; die Zahl der Kriterien ist nicht die Zahl unabhängiger Risikofaktoren. Inaktive Zustandskriterien stehen auf50. Dadurch ergibt ein vollständig ruhiges Risk-On-Szenario70,91 und ein beidseitig bestätigtes Stressszenario24,55. Ein Score0 oder100 ist hier regulär nicht erreichbar. Die Skala ist eine Einordnung, keine Wahrscheinlichkeit und keine marktübergreifend einheitliche Intensitätsmessung.

**Schwellen:** Unter40 schwach,40 bis unter65 gemischt, ab65 konstruktiv. Diese Bänder ordnen die genannten typischen Zustände konsistent ein. Sie sind nicht durch eine unabhängige Optimierung belegt. Insbesondere Unterschiede von wenigen Punkten zwischen verschiedenen Kennzahlen dürfen nicht wie vergleichbare Renditeaussichten interpretiert werden.

## Datenprüfung und verbleibende Grenzen

- Die McClellan-Basis im Repository ist ratio-adjustiert: `(Advancer−Decliner)/(Advancer+Decliner)×1000`, darauf EMA19 minus EMA39. Die verwendeten Schwellen werden damit auf einer von der Anzahl der Aktien normierten Skala angewendet. Die ursprüngliche Entwicklerdokumentation beschreibt diese Normierung: [McClellan Financial](https://www.mcoscillator.com/download/docs/UnderstandingOscillators.pdf).
- VIX beschreibt die vom Optionsmarkt erwartete30-Tage-Volatilität; die hiesigen Scorestufen sind eine eigene Einordnung. Quelle: [Cboe](https://www.cboe.com/tradable-products/volatility-trading/).
- Der NH/NL-Altbestand speichert seine tatsächliche Hoch-/Tief-Referenz pro Tag nicht. Die vorhandene Datenproduktion bestimmt das maximale Referenzfenster aus der Länge des geladenen Datensatzes und erlaubt Titel bereits ab20 Vorwerten. Deshalb ist ein rückwirkender, vollständig reproduzierbarer52W-Nachweis aus diesen aggregierten Cache-Zeilen allein nicht möglich. Das Score-Label behauptet ihn nicht mehr. Eine vollständige Bereinigung braucht eine versionierte Neuberechnung aus Einzeltitelhistorien.
- Derselbe Zeitstempel allein garantiert nicht, dass ein Aktienuniversum historisch ohne Auswahlverzerrung rekonstruiert wurde. Die aktuelle Prüfung belegt Rechen- und Integrationsverhalten; sie ist kein neuer Renditebacktest und ersetzt keine Prüfung auf einem unberührten historischen Zeitraum.
- Die vorherige PDF dokumentiert `market_context_v1`. Die hier aufgeführten Korrekturen und das aktualisierte Regeldokument beschreiben `market_context_v2`.

## Überprüfung

Gezielte Regressionstests prüfen die gefundenen Grenzfälle mit unabhängigen Erwartungswerten, darunter15:40 bei Teilverfügbarkeit,70/50/10 bei Equal Weight,254 Sitzungen bis zur ersten vollständigen EW-Bestätigung und fehlende VXX-/Benchmark-Beobachtungen. Hinzu kommen die vollständigen bestehenden Backend- und Frontend-Prüfungen sowie die Browserprüfung für Ampelvorrang und mobile Anzeige.

Ein Abgleich mit dem eingefrorenen NAS-Datenstand09.10.2026 liefert beim Nasdaq unverändert Aufwärtstrend, Index66,25, Marktbreite30,43, Powertrend76,67 und Volatilität70,91. Equal Weight sinkt durch die korrekte neutrale Bestätigung von60 auf50. Beim Russell steigt der nur teilweise verfügbare Indexscore von50 auf60, weil fehlendes Volumen nun seine ursprünglichen Gewichte behält, statt die übrigen Gruppenmitglieder hochzugewichten. Die verfügbare Gesamtgewichtung beträgt68,75%.
