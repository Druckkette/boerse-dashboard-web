# Vergleich mit veröffentlichten Cup-Beispielen

Prüftag: 26. Oktober 2026. Die Chartanalyse wurde zuerst über PR #65 auf GitHub
und dem NAS aktiviert. Danach wurden fünf vorab festgelegte Veröffentlichungen
mit dem laufenden Backend verglichen. Die Kursdaten enthalten ausschließlich
Tage bis zum jeweils festgelegten historischen Prüfzeitpunkt. Es wurden keine
Testkurse in die produktive Datenbank geschrieben.

## Ergebnis mit unveränderten Standardparametern

**Ein Treffer in fünf Quellenfällen.** Das ist eine Übereinstimmung der
Musterklasse und Basis im festgelegten Zeitfenster, keine Präzisionsquote für das
Aktienuniversum. Andere Muster oder Teilbasen zählen nicht als Treffer. Der erste
Test der veröffentlichten Version `chapter-4.2-v1` und die korrigierte Version
`chapter-4.2-v2` ergeben denselben Wert. Die fünf Fälle wurden bei der folgenden
Fehleranalyse verwendet und sind anschließend kein unabhängiger Prüfsatz mehr.

| Quelle und Aktie | Quellenmuster | Standardergebnis in v2 | Einordnung |
|---|---|---|---|
| [IBD: ATI 2005](https://finance.yahoo.com/news/cup-patterns-without-handles-still-182000010.html), veröffentlicht 3.10.2013 | Cup ohne Handle; Ausbruch in der Woche bis 25.11.2005 | **Erkannt am 15.11.2005**, Ausbruch 21.11.2005; Tiefe 16,76 %, Pivot 31,38 | Der Quellenkaufpunkt 31,48 enthält den dort verwendeten Aufschlag von 0,10. Das Modul zeichnet den Widerstand selbst. |
| [IBD: Sea 2019](https://shop.investors.com/images/promotional/shop/assets/pdf/TopStocks-2019.pdf), Druckseite 86 / PDF-Seite 87 | Cup ohne Handle; Ausbruch 20.11.2019 | **Übersehen** | Der späte Tiefpunkt am 21.10.2019 und die unruhige Form erfüllen die technischen Symmetrie- und Formgrenzen nicht. Für den Abschnitt bis 19.11. liegt der Tiefpunkt bei 73,8 % der Cup-Länge; zugelassen sind 30–70 %. |
| [IBD: Apple 2004](https://finance.yahoo.com/news/chart-pattern-star-power-simple-212700404.html), veröffentlicht 11.9.2015 | Cup mit Handle Oktober 2003 bis Februar 2004; Ausbruch Anfang März | **Übersehen**; andere Teilmuster werden nicht als Erfolg gezählt | Beim linken Peak 15.10. und rechten Peak 13.1. liegt der tiefste Kurs bei 77 % der Cup-Länge. Der Abschnitt vom rechten Peak bis vor den Ausbruch umfasst 34 Folgesitzungen, mehr als die eingestellten 25. |
| [StockCharts: Autodesk 2009](https://articles.stockcharts.com/article/articles-dont_ignore_this_chart-2009-09-identifying-the-cup-with-handle-formation/), veröffentlicht 8.9.2009 | Cup mit Handle Juni–August 2009 | **Übersehen** | Nach korrigierter Peak-Suche wird die Basis untersucht, der spitze Boden bleibt aber am V-Filter hängen. Im Abschnitt 5.6.–23.7. beträgt der Fehler der beiden geraden Schenkel 0,051 bei einem Bodenanteil von 0,281; die Ausschlussgrenzen sind 0,06 und 0,30. |
| [StockCharts: Cisco 2023](https://articles.stockcharts.com/article/articles-arthurhill-2023-07-cisco-takes-the-lead-with-a-cl-153/), veröffentlicht 24.7.2023 | Cup mit Handle April–Juli 2023 | **Abweichend als Cup ohne Handle** am 15.6.; kein Treffer für die Quellenklasse | Der spätere Handle ist etwa 4,48 % tief und unterschreitet die Standard-Mindesttiefe von 5 %. |

Die Berechnungen verwenden splitbereinigte Yahoo-OHLC-Tageskurse ohne zusätzliche
Dividendenbereinigung. Insbesondere Apples historische Kurswerte sind deshalb
kleiner als die damaligen Nominalkurse. Verlagsabbildungen wurden nicht kopiert.
Die vollständigen Messwerte und erkannten Alternativen stehen in
[chart-analysis-internet-results.json](chart-analysis-internet-results.json).

## Separater Parametertest

Mit **Handle-Mindesttiefe 4 %** und ansonsten unveränderten Einstellungen wird
Ciscos Cup mit Handle am **29.6.2023** erkannt, der Ausbruch am **19.7.2023**.
Auch die Wiederholung nur mit den bis 29.6. verfügbaren Kursen liefert dieselben
Eckpunkte und denselben Pivot. Dies zeigt die Wirkung der Parametereinstellung;
es verbessert nicht rückwirkend das Ergebnis des ursprünglichen Standardtests.
Die zentralen NAS-Standardparameter bleiben unverändert.

## Korrekturen aus der Prüfung

- Der linke Peak darf in der ersten negativen Woche selbst liegen. Auch eine
  enge positive Woche zwischen Peak und erster negativer Woche darf den Peak
  nicht verschwinden lassen. Autodesk liefert dafür einen realen Regressionstest.
- Bei einem Double Bottom müssen beide Tiefs und der Mittelgipfel getrennte
  Wendepunkte bilden. V1 konnte in Cisco die Kerze vom 12.4.2023 gleichzeitig
  als erstes Tief und als Mittelgipfel verwenden. V2 verhindert solche W-Geometrien.
- Die Algorithmusversion wurde auf `chapter-4.2-v2` erhöht. Der Parameterhash
  ändert sich dadurch auch ohne Änderung der Zahlenwerte; alte Scans werden veraltet.

Die Regeln für U-Form, Symmetrie und Standard-Handle-Tiefe wurden für den
Vergleich nicht gelockert. Gerade bei der Abdeckung veröffentlichter Muster
bestehen deutliche Grenzen. Die aktive Funktion ist eine geometrische Vorauswahl
mit visueller Nachprüfung, kein fachlich umfassend validierter Musterdetektor.

## Wiederholung

```bash
cd backend
.venv/bin/python -m scripts.evaluate_published_chart_examples
.venv/bin/pytest tests/domain/test_chart_patterns_published.py -q
```

Die fünf eingefrorenen Kursreihen und die vorab festgelegten Quellenfenster liegen
in `backend/tests/fixtures/chart_patterns/published/`. Der Bericht enthält den
SHA-256-Hash jeder Kursreihe, den Modulhash, Parameter, Version und sämtliche
gefundenen Alternativen. Für erkannte Quellenfälle werden die Eckpunkte mit
einem Kurspräfix bis zum Erkennungstag erneut geprüft.
