# Aktienempfehlungen und Verkaufsstrategien prüfen

Der Offline-Lauf verändert keine Depotpositionen, Verkaufszustände oder Rankings. Er verwendet einen expliziten Export aus dem NAS. Historische Empfehlungen werden aus `daily_stock_opportunities` gelesen; aktuelle Fundamentaldaten werden nicht nachträglich zu historischen Kaufentscheidungen erklärt.

## Reproduktion

Im Backend mit derselben Python-Umgebung:

```sh
python -m app.research.export_stock_backtest > backtest-input.json
python -m app.research.stock_backtest backtest-input.json backtests --workers 4
```

Der Export enthält ausschließlich Börsendaten, aktives Universum, gespeicherte Top-20-Ranglisten und die globalen Verkaufsregeln. Persönliche Depotbestände und Zugangsdaten werden nicht exportiert. Er endet beim letzten abgeschlossenen US-Handelstag. Kurszeilen werden je Datum anhand des letzten Abrufs entdoppelt; unvollständige OHLC-Kerzen werden ausgeschlossen. Der Ergebnisbericht speichert die SHA-256-Prüfsumme des tatsächlichen Inputs.

## Tagesauswahl

Für jede tatsächlich gespeicherte Top-3-Empfehlung wird der erste spätere reguläre Börsenstart verwendet, der sowohl nach dem Bewertungsdatum als auch nach dem tatsächlichen Erstellungszeitpunkt liegt. Das verhindert auch bei nachträglich berechneten Ständen einen rückwirkenden Einstieg. Gemessen werden 1, 5, 10, 20 und 63 Handelssitzungen ab Einstieg, soweit abgeschlossen. Vergleich: SPY über denselben Zeitraum, jeweils Eröffnung zu Schluss. Offene Zeiträume bleiben offen. Jede Empfehlung ist eine eigenständige gleich gewichtete Beobachtung; wiederkehrende Aktien und überlappende Zeiträume sind nicht unabhängig.

Die gespeicherte Historie beginnt am 22.09.2026. Aus längeren Kursreihen allein lässt sich keine historische Top-3-Auswahl mit damals bekannten Fundamentals und RS-Ratings rekonstruieren. Deshalb wird kein langjähriger Backtest der Aktienauswahl vorgetäuscht.

## Verkaufsstrategien

Alle acht vorhandenen Strategien einschließlich des aktuell konfigurierten benutzerdefinierten Baukastens werden mit denselben Einstiegen verglichen. Der aktuelle Baukasten kann ausschließlich den Nothalt enthalten; dies wird aus dem exportierten Setup übernommen, ohne ihn nachträglich zu optimieren.

Zusätzlich zu den echten Top-3-Einstiegen werden 40 Titel deterministisch anhand des SHA-256-Schlüssels `sell-backtest-2026-10-15:<ticker>` aus dem aktiven Universum gezogen. Die Stichprobe wird vor Betrachtung ihrer Renditen festgelegt. Einstiege: erste vorhandene Sitzung im Januar und Juli, jeweils mindestens 200 vorherige Kurskerzen und 126 vollständige Haltedauersitzungen. Lücken gegenüber dem SPY-Sitzungskalender schließen diese Zusatzkohorte aus. Dies ist ein Vergleich der Ausstiegsregeln bei identischen Einstiegen, kein Backtest der Aktienauswahl. Die Verwendung des heutigen Universums verursacht Survivorship-Bias und wird ausdrücklich ausgewiesen.

Der Lauf verwendet die bestehenden Produktionsfunktionen zur Merkmals-, Strategie- und Bestätigungsberechnung. Die gemeinsamen Merkmale werden pro Tag nur einmal berechnet. Die beschleunigte Zielberechnung wird gegen die vollständige Engine geprüft, einschließlich bereits verkaufter Tranchen und Bestätigungszustand.

Signale entstehen frühestens nach dem jeweiligen Tagesschluss; ihre Tranchen werden zum nächsten vorhandenen Eröffnungskurs ausgeführt. Der Nothalt bleibt in diesem Tagesmodell ebenfalls ein Schlusskurssignal mit Ausführung am nächsten Börsenstart; es wird kein garantierter Intraday-Stopkurs angenommen. Verkaufte Anteile bleiben unverzinst als Cash. Restbestände werden am gemeinsamen Vergleichsende zum Schlusskurs bewertet und für den Kostenvergleich rechnerisch liquidiert. Prozenttranchen beziehen sich auf die ursprüngliche Position und können zusammen nie mehr als 100 % verkaufen.

## Kosten und Ergebnisgrenzen

Die Sensitivitäten 0, 10 und 25 Basispunkte je Kauf und Verkauf werden proportional zum ausgeführten Wert berechnet. Das Modell enthält keine Dividenden, Steuern, Wechselkurse, Broker-Mindestgebühren, Intraday-Daten oder Marktbeeinflussung. Verglichen werden Preisrenditen. Maximaler Rückgang wird aus dem täglichen Bruttowert einer einzelnen Kohorte einschließlich ihres Cash-Anteils gemessen.

Die Ergebnisse berichten Kohortenmittel, Median, Gewinnquote und Rückgang. Sie werden weder zu einer handelbaren Gesamtportfolio-Rendite aufaddiert noch bei kurzen Horizonten als Jahresrendite ausgegeben. Die zwei halbjährlichen Einstiegsgruppen können sich kalenderbedingt überlappen. Es gibt keine nachträgliche Parameteroptimierung. Eine Rangfolge dieser Stichprobe ist kein Nachweis einer allgemeinen künftigen Überrendite.

## Offene 13F-Kennungen fortsetzen

Der optionale Kennungsabgleich nutzt die bereits konfigurierte FMP-Verbindung und den gemeinsamen Provider-Backoff. Er ändert keine Depotpositionen oder manuellen CUSIP-Zuordnungen. Erfolgreiche Profile werden 30 Tage aus dem Instrument-Cache gelesen; nach einem Providerlimit wird beim nächsten Lauf deshalb nicht erneut das erste Symbolpaket abgerufen. Nur exakt zurückgemeldete Symbole und CUSIPs mit gültiger Prüfsumme dürfen eine neue Kennung erzeugen. Konflikte bleiben sichtbar.

```sh
python -m app.research.repair_sec13f_identifiers identity-request.json identity-results.json
```

Anschließend verwendet ein regulärer vollständiger 13F-Lauf die gespeicherten Kennungen, um die echten SEC-Holdings zuzuordnen. FMP liefert hier ausschließlich Wertpapierkennungen und Stammdaten; die institutionellen Bestände stammen weiterhin aus den SEC-Dateien.
