# Professioneller Arbeitsbereich · 22. Oktober 2026

Diese Erweiterung setzt die Verbesserungen des Beta-Berichts vom 22. Oktober um. Die bestehenden parallelen Scores, ihre Regeln und ihre Gewichtungen bleiben unverändert. Neue Funktionen verwenden vorhandene Bewertungen und gespeicherte Marktdaten.

## Ansichten und täglicher Ablauf

| Ansicht | Funktionen |
| --- | --- |
| Startseite | Unter „Weitere Prüfpunkte & Einstiegspläne“ priorisiert „Heute prüfen“ bis zu fünf Aufgaben aus bestätigten Depotwarnungen, fehlenden Stopps, offenen Alarmmeldungen, nahen Quartalszahlen und geplanten Einstiegen. Fehlende persönliche Daten werden kenntlich gemacht. |
| Aktie | „Beobachten“, „Vergleichen“ und „Einstieg planen“ stehen direkt oberhalb der Analyse. Kurs und Kurswährung werden in den Plan übernommen. Der Vergleich öffnet Aktie und SPY. Technische Pflege bleibt im zusätzlichen Aktionsbereich. |
| `/workspace` | Benannte Watchlists, Notizen, Kennzeichnungen, Suchfilter, Kandidatenstatus, Mehrfachauswahl sowie Kopieren und Verschieben zwischen Listen. Die Standardliste entspricht weiterhin der bisherigen Watchlist. |
| `/workspace#einstieg` | Kaufplan mit Einstieg, Stopp, optionalem Ziel, Gebührenreserve, Cashgrenze, Risikobudget und beobachtetem Wechselkurs. Speichern dokumentiert die geprüfte Vorschau mit damaligem Bewertungsstand. |
| `/alerts` | Kurs-, RS-, Stopp-, Earnings- und Datenqualitätsregeln anlegen, bearbeiten, pausieren oder entfernen. Meldungen mit Verlauf, Quittierung, Wiederholungsintervall und Berliner Ruhezeiten. Bestehende ATR-Zustellungen bleiben gesondert einsehbar. |
| `/calendar` | Gespeicherte Earnings aus Depot und allen Watchlists sowie eigene Unternehmens-, Dividenden-, Split-, Makro- und Prüftermine. Zeitraum und Zugehörigkeit sind filterbar. |
| `/portfolio/performance` | Zeitgewichtete Rendite, jährliche persönliche Rendite nach XIRR, Drawdown, Periodenergebnis und externe Cashflows. Wählbare Benchmarks SPY, QQQ, IWM, RSP und S&P-500-Index, umgerechnet in Depotwährung. |
| `/portfolio/accounts` | Zusätzliche, getrennte Depots mit Basiswährung, Broker/Strategie, Beständen und Cash. Konsolidierte EUR-Bewertung und CSV-Import mit Vorschau und Duplikatprüfung. |

Die Einstiegsplanung dokumentiert eine Entscheidung. Ein als gekauft markierter Plan erzeugt keine Order und keine Buchung. Tatsächliche Ausführungen werden weiterhin über die Depotverwaltung beziehungsweise einen Import erfasst. Der Plan führt zum bestehenden Journal oder zur Buchungsliste des zusätzlichen Depots.

Die initial vorgeschlagenen Stoppwerte sind bearbeitbare Annahmen. Die Stückzahl wird gleichzeitig durch Verlustbudget und verfügbares Cash begrenzt. Die Gebührenangabe ist die gesamte Kostenreserve für Einstieg und Ausstieg in Kurswährung. Unbekanntes Stopprisiko vorhandener Positionen bleibt unbekannt. Eine Vorschau wird beim Speichern erneut geprüft; geänderte Kurse, Bewertungen, Cash- oder FX-Werte erfordern eine neue Berechnung. Der erzeugte Antwortzeitstempel zählt dabei nicht als geänderte Finanzgrundlage.

## Bedienung und Darstellung

- Screener, RS-Ranking und Vergleich verwenden wieder die bisherigen Tabellen, auch mobil. Breite Tabellen scrollen innerhalb ihres Bereichs. Alle Teilbewertungen und Vergleichskennzahlen bleiben zugänglich.
- Desktoptabellen behalten die optionale Spaltenauswahl und kompakte Zeilen. Fixierte Spalten entfallen zugunsten der vorherigen Darstellung. Darstellungspräferenzen werden lokal im Browser gespeichert.
- Das RS-Ranking heißt ausdrücklich „Top 120 nach RS“. Lokales Sortieren betrifft diese Auswahl; der vollständige Screener bleibt separat verfügbar.
- Schriftgrößen entsprechen wieder dem Stand vor dem Funktionsupdate. Datenstand, Quelle und Einschränkungen stehen an den betroffenen Informationen.
- Der Wechsel zwischen klassischer und neuer Ansicht liegt wieder direkt im Header sowie in den Einstellungen. Der Schutz offener Entwürfe bleibt erhalten.
- Die Depotkurve zeigt ihre gleitenden Durchschnitte nur auf Wunsch.
- Gemeinsame Charts unterstützen eigene horizontale Marken, benannte Vorlagen, eine logarithmische Skala bei positiven Werten sowie SVG- und PNG-Export. Marken und Vorlagen liegen im jeweiligen Browser, nicht im serverseitigen Entscheidungsarchiv.

## Historische Nachvollziehbarkeit und Performance

Ein Plan speichert die unveränderte Eingangsvorschau, Depotwert und Cashgrundlage, FX-Stichtag, bestehende Scorefelder und V2-Bewertungen, Datenqualität, Regelversion und Konfigurationshash, Kriterien, Warnungen und Nutzerbegründung. Spätere Prüfschritte werden angehängt. Sie ersetzen die damaligen Daten nicht durch heutige Bewertungen.

Die Performance des bestehenden Depots baut auf der vorhandenen TR-Ausführungshistorie und deren cashflowbereinigtem Renditeindex auf. Eine Simulation des heutigen Bestands wird nicht als historische Performance ausgewiesen. Die neue XIRR-Berechnung verwendet dieselben erfassten externen TR-Cashflows; separate manuelle Cashflows werden nicht zusätzlich gezählt. Bei Wertpapierüberträgen ohne bewerteten externen Vermögensfluss wird keine persönliche Rendite behauptet.

Zusätzliche Depots werden aus ihrer eigenen CSV-Buchungshistorie bewertet. Ein- und Auszahlungen gelten am Tagesende. Historische Stückzahlen werden mit der damaligen Kursbasis kombiniert; gespeicherte Yahoo-Splitfaktoren werden dafür zurückgerechnet. Bei einer gebuchten Kapitalmaßnahme mit unklarer alter Kursbasis muss die Historie aktualisiert werden. Die Bewertung folgt US-Handelstagen; für einen lokalen Börsenfeiertag darf der letzte beobachtete Kurs höchstens vier Kalendertage alt sein. An offenen Börsentagen fehlen fehlende Kurse weiterhin. Cashumrechnungen benötigen beobachtete historische FX-Werte.

TWR und Drawdown benötigen einen vollständig belegten historischen Index. XIRR wird nur mit eindeutiger berechenbarer Lösung angezeigt und ist ausdrücklich annualisiert. Unvollständige Reihen zeigen Lücken. Der Benchmark ist eine Kursrendite in derselben Basiswährung; er wird nicht als Gesamtrendite einschließlich Ausschüttungen bezeichnet. Nicht importierte Buchungen, fehlende Splitbuchungen und fehlende Daten können keine vollständige Auswertung ergeben.

## CSV für zusätzliche Depots

Für das bestehende Depot bleibt der bisherige Trade-Republic-Import zuständig. Zusätzliche Brokerexporte werden an die herunterladbare, gemeinsame Vorlage angepasst; es gibt keine automatische Verbindung zu weiteren Brokerkonten.

```csv
date,type,ticker,shares,price,currency,fees,tax,amount,external_id
2026-01-02,deposit,,,,USD,0,0,10000,cash-1
2026-01-05,buy,NVDA,5,100,USD,1,0,,buy-1
2026-01-06,dividend,NVDA,,,USD,0,1,5,dividend-1
2026-01-07,sell,NVDA,2,110,USD,1,0,,sell-1
```

Pflichtspalten sind `date`, `type` und `currency`. Käufe und Verkäufe benötigen zusätzlich Ticker, positive Stückzahl und Preis. Cashbuchungen verwenden positive Beträge in `amount`; `withdrawal` und `fee` erhalten ihr negatives Vorzeichen durch den Buchungstyp. Gebühren und Steuern werden zusätzlich abgezogen. `split` setzt `shares` auf den neuen Gesamtbestand und benötigt einen vorhandenen Bestand; maßgeblich ist das wirksame Datum der Kapitalmaßnahme. Buchungen desselben Tages werden in Importreihenfolge verarbeitet.

Unterstützt werden Komma, Semikolon oder Tab als Trennzeichen sowie ISO-Daten und Dezimalzahlen. Datum in der Zukunft, fehlende Pflichtwerte, nicht endliche Zahlen, doppelte Spalten und Verkäufe über den gebuchten Bestand werden abgelehnt. Der Import ist auf 2 MB beziehungsweise 5.000 Zeilen beschränkt, ein zusätzliches Depot auf 20.000 Buchungen.

Eine `external_id` identifiziert die Buchung innerhalb des Depots. Dieselbe ID mit gleichem Inhalt ist ein Duplikat, dieselbe ID mit anderem Inhalt ein Fehler. Ohne ID dient der Fingerabdruck der normalisierten Buchungsdaten als Identität. Für zwei tatsächlich identische Ausführungen müssen unterschiedliche externe IDs vergeben werden. Die Vorschau nennt neue und bereits vorhandene Buchungen und zeigt Gebühren, Steuern und IDs. Übernommen wird ausschließlich die bestätigte Vorschau.

## Speicherung, Daten und Betrieb

Die Erweiterung verwendet die bestehende PostgreSQL-Tabelle für Anwendungseinstellungen (`professional_workspace_v1`). Eine zusätzliche Schema-Migration ist nicht erforderlich. Die Standard-Watchlist und ihre bisherigen Notizen beziehungsweise zuletzt angesehenen Ticker bleiben kompatibel. Gemeinsame Transaktionssperren und eine Revisionsprüfung verhindern das unbemerkte Überschreiben konkurrierender Änderungen. Ein fehlgeschlagenes Speichern wird nicht als Erfolg ausgegeben.

Die Grenzen des privaten Arbeitsbereichs liegen bei 30 Listen mit je 100 Aktien, 100 dokumentierten Plänen mit je 100 Prüfschritten, 100 Alarmregeln, 500 Meldungen im Verlauf, 500 eigenen Terminen und 20 zusätzlichen Depots. Die Daten gehören zum vorhandenen privaten Dashboard-Arbeitsbereich; dies ist keine neue Benutzerkontenverwaltung.

Neue Leseansichten und Alarmprüfungen laden keine Marktdaten von Anbietern. Sie verwenden die vorhandenen Kurse, FX-, RS- und Earnings-Daten. Neue oder bislang nicht abgedeckte Ticker und historische Zeiträume müssen über die bestehende Datenverwaltung aktualisiert werden. Zusätzliche Watchlists werden bei der Fundamental-Aktualisierung berücksichtigt. Unternehmens- und Makrotermine außerhalb vorhandener Earnings-Quellen werden selbst gepflegt; ein zusätzlicher externer Kalenderfeed ist nicht enthalten.

Celery Beat prüft aktive Alarmregeln alle fünf Minuten über `check_workspace_alerts`. Für den Betrieb müssen Backend, Frontend, Worker und Beat auf denselben Stand gebracht werden. Pushover erfordert die ausdrückliche Aktivierung an der jeweiligen Regel sowie die vorhandene globale Aktivierung und Zugangsdaten; Dry-Run bleibt wirksam. Pro Durchlauf werden höchstens fünf Zustellungen beansprucht. Nach einem unklaren Versandbeginn wird nicht blind erneut gesendet. Ruhezeiten gelten in `Europe/Berlin`; gleiche Anfangs- und Endzeit deaktiviert sie. Die vorhandenen ATR-/Intraday-Alarme bleiben unabhängig.

Die neuen Seiten und `/api/v1/desk/*` bleiben privat. Die öffentliche Beta erhält weder persönliche Pläne und Depots noch neue Schreibrechte.

## Prüfung

Automatisierte Prüfungen decken Währungsrichtung, Cash- und Gebührenbegrenzung, veraltete Vorschauen, unveränderliche Entscheidungsstände, CSV-Validierung und Duplikate, Kapitalmaßnahmen, Cashflowrenditen, fehlende Kurse, Ruhezeiten, Push-Freigaben und konkurrierende PostgreSQL-Zugriffe ab. Browsertests prüfen den gesamten Planungsablauf auf Desktop und Mobilgeräten, bearbeitbare Alarmregeln, Kalenderfilter, CSV-Import, FX-Fehler, Chartwerkzeuge und die private Abgrenzung der neuen Routen.

Die Prüfungen verwenden isolierte Beispieldaten und eine wegwerfbare lokale PostgreSQL-Datenbank. Produktive Depotdaten, echte Pushover-Zustellungen und eine Veröffentlichung auf NAS oder Hosting gehören nicht zu diesen Tests.
