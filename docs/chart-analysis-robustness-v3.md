# Robustheitsprüfung der Chartanalyse v3

Prüftag: 26. Oktober 2026. Version `chapter-4.2-v3`. Die Änderung verbessert
konkrete Geometrie- und Zustandsfehler. Sie liefert weiterhin eine geometrische
Vorauswahl, keine allgemeine Erfolgswahrscheinlichkeit oder Renditeprognose.

## Behobene Fehler

- Ein symmetrischer Parabelfit und eine einzelne Tiefstkerze waren zu dominant.
  Eine kubische Kurve erlaubt unterschiedliche Seitenlängen, muss aber im mittleren
  Bereich erst fallen und dann steigen. Zusätzliche Kandidaten benötigen gegenüber
  zwei geraden V-Schenkeln einen mindestens 15 % niedrigeren Anpassungsfehler.
  Ansonsten bleiben die konservativen Quadratikregeln wirksam. Das neue einstellbare
  maximale Zeitverhältnis beträgt standardmäßig 3 und darf zwischen 1 und 5 liegen.
- Der rechte Cup-Rand muss ein Hoch gegenüber den vorangegangenen vier Sitzungen
  sein. Ein tieferer Tag im beginnenden Handle darf den Pivot nicht künstlich senken.
  Die eingezeichnete Randhöhe stammt jetzt tatsächlich von ihrer angegebenen Kerze;
  der Pivot berücksichtigt weiterhin das gesamte bis zur Erkennung bekannte Handle.
- Kleine Intraday-Überschreitungen des linken Randes bis 1,5 % sind möglich, solange
  die Schlusskurse des Handles unter dem linken Rand bleiben. Das ersetzt keine
  Tiefen- oder Mindestdauerregel.
- Eine Ausbruchskerze kann einen zuvor mindestens fünf Sitzungen langen gültigen
  Handle bestätigen. Die Ausbruchskerze fließt weder in den Handle-Pivot noch in
  dessen Volumenvergleich ein. `end_date` kann deshalb vor `detected_on` liegen.
- Vor dem Ausbruch gelten OHLC-Regeln weiter: Intraday-Unterschreiten des
  Basistiefs, mehr als die konfigurierte Handle-Tiefe oder Verlust der oberen
  Cup-Hälfte invalidiert das Muster. Eine spätere Erholung erzeugt keinen Ausbruch
  derselben ungültigen Geometrie. Grund und Datum erscheinen als Hinweis.
- Ein Handle kann nicht über seine eingestellte Höchstdauer hinaus auf einen
  Ausbruch warten. Ein unmittelbar anschließender Ausbruchstag ist zulässig.
- Die maximale Basisdauer endet mit der Formation. Eine folgende Bestätigung
  am Montag verlängert eine am Freitag fertiggestellte Basis nicht nachträglich.
- Bei konkurrierenden Double-Bottom-Paaren und Handle-Rändern gewinnt die
  früheste damals beobachtbare Variante. Später nachgewiesene Erholung oder
  Volumenabnahme kann deren historische Auswahl nicht verdrängen. Das gilt
  auch bei eingeschaltetem Volumen-Pflichtfilter.

Maximale Cup-Tiefe 50 %, Handle-Mindesttiefe 5 % und Handle-Höchstdauer 25 Sitzungen
bleiben unverändert. Bestehende gespeicherte Einstellungen werden erhalten;
das neue Zeitverhältnis ergänzt fehlende Altkonfigurationen mit dem Standard 3.
Die Versionsänderung macht den alten Universumscan erkennbar veraltet.

## Veröffentlichte Quellenfälle

Exakte Musterart, linker Rand und Beobachtungsfenster müssen zusammenpassen.
Eine kleinere Teilbasis oder ein Double Bottom zählt nicht als Cup-Treffer.
Alle Preisreihen sind eingefroren; die Auswertung enthält keine Kurse nach dem
historischen Stichtag.

| Prüfsatz | v2 | endgültige v3 | Einordnung |
|---|---:|---:|---|
| Ursprüngliche fünf Quellenfälle | 1/5 | 2/5 | Kalibrierung; ATI bleibt erkannt, Autodesk kommt hinzu |
| Vier zusätzlich vorab ausgewählte CwH-Fälle | 1/4 | 1/4 | MKTX bleibt erkannt; ADBE, EW, OLED fehlen weiterhin |
| Ganze ROKU-Basis mit 66 % Tiefe | ausgeschlossen | ausgeschlossen | Parametergrenze 50 %, keine allgemeine Präzisionsmessung |
| BLD-Basis | nicht auswertbar | nicht auswertbar | Historische Notierung nicht verfügbar; kein negativer Erfolg gezählt |

Autodesk: linker Rand **2.6.2009**, rechter Rand **28.7.2009**, Handle-Tief
**5.8.2009**. Erkennung und volumenbestätigter Ausbruch **7.8.2009**, Pivot
**22,950001**; der Handle endet am **6.8.2009**. Auch mit ausschließlich bis zum
Erkennungstag verfügbaren Kursen entstehen dieselben Punkte und derselbe Pivot.
Quelle: [Tom Bowley / StockCharts](https://articles.stockcharts.com/article/articles-dont_ignore_this_chart-2009-09-identifying-the-cup-with-handle-formation/).

SE und AAPL bleiben im ursprünglichen Quellenfenster unerkannt; Cisco braucht
weiterhin eine ausdrücklich reduzierte Handle-Mindesttiefe (4 statt 5 %).
Die Grenzen werden nicht stillschweigend übergangen, um Quellenlabels zu treffen.
Die zusätzlichen Fälle stammen aus der offiziellen
[IBD-/MarketSmith-Publikation 2019](https://shop.investors.com/images/promotional/shop/assets/pdf/TopStocks-2019.pdf).
Seiten und Datumsfenster stehen im Manifest unter
`backend/tests/fixtures/chart_patterns/holdout_v3/`.

### Erstprüfung und anschließende Kalibrierung offenhalten

Das zusätzliche Manifest wurde **vor dem ersten Detektorlauf** eingefroren
(SHA-256 `0a8a45e0dd1508c7a929e435dd4a8c094fbc2ccdff3e1c7c2783f038ff43dc35`).
Der erste v3-Entwurf erkannte **0/4**, gegenüber **1/4** in v2. Die breite,
ungleich verteilte MKTX-Bodenzone führte zu einer zu frühen Lage beim Median der
Bodensitzungen. Die Lageprüfung wurde auf das Minimum der angepassten Kurve
umgestellt; MKTX wird wieder erkannt. Der zusätzliche Satz ist dadurch jetzt
**Kalibrierung und Regression**, kein unabhängiger Beleg für die finale Version.
Auch die Grenzen der ersten flexibleren Formprüfung wurden im V-Stresstest
sichtbar und führten zur konservativen Rückfallregel. Es wird kein nachträglich
verbesserter Wert als unvoreingenommener Holdout-Wert ausgegeben.

Maschinenlesbare Belege:

- [v2: zusätzliche Quellenfälle](chart-analysis-holdout-v2-results.json)
- [v3: erste zusätzliche Auswertung](chart-analysis-holdout-v3-first-results.json)
- [v3: endgültige zusätzliche Auswertung](chart-analysis-holdout-v3-results.json)
- [v3: ursprüngliche Quellenfälle](chart-analysis-internet-v3-results.json)

Die Berichte enthalten Modul-, Manifest- und Preishashes, Parameter, sämtliche
Alternativen und den kausalen Präfixvergleich für passende Quellenfälle.

## Gegenproben und Wiederholbarkeit

Ein fest reproduzierbarer Stresstest erzeugt **420 spitze V-Verläufe**: 65
Sitzungen, 35 % Tiefe, sechs unterschiedliche Tiefpunktlagen, sieben
Rauschstärken, jeweils zehn Zufallsseeds. Jeder Cup-Treffer zählt als Fehlklassifikation.

| Rausch-Standardabweichung (Preiseinheiten) | v2 Fehlklassifikationen / 60 | v3 Fehlklassifikationen / 60 |
|---|---:|---:|
| 0 | 0 | 0 |
| 0,2 | 0 | 0 |
| 1 | 0 | 0 |
| 2 | 0 | 0 |
| 3 | 2 | 2 |
| 4 | 12 | 8 |
| 5 | 21 | 15 |
| Summe | **35/420** | **25/420** |

Die stärksten Rauschstufen bleiben problematisch. Ein Hinweis kennzeichnet
unruhige Schlusskursverläufe; er macht eine Fehlklassifikation nicht nachträglich
richtig. Der konstruierte und bei der Entwicklung verwendete Stresstest ist
kein zufälliger Marktprüfsatz und erlaubt keine allgemeine Präzisionsangabe.
Details: [v2](chart-analysis-stress-v2-results.json), [v3](chart-analysis-stress-v3-results.json).

Alle acht eingefrorenen Buch-/Referenzfälle bleiben erkannt. Bei 36 ausgegebenen
Geometrien aus den Buch- und Quellenreihen wurde jede Erkennung ausschließlich
mit dem bis dahin verfügbaren Kurspräfix wiederholt: keine Abweichung bei ID,
Punkten und Pivot. Zusätzliche Regressionen prüfen flache Reihen mit einzelner
Tiefstkerze, asymmetrische verrauschte Vs, Intraday-Verletzungen, Handle-Verfall,
korrekte Randkerzen, konkurrierende W-Tiefs und Handles in beiden Volumenmodi
sowie Speichern und Neuladen des neuen Parameters. Weitere deterministische
Zufallsreihen wurden am jeweiligen historischen Erkennungstag erneut abgespielt:
112 Geometrien im Standardmodus und 41 mit verpflichtendem Volumenfilter,
ohne Abweichung bei ID, Punkten oder Pivot.

Lokale Prüfung: **1.550 Backendtests bestanden**, 55 ohne Integrationsdienste
übersprungen; Postgres-Persistenztest separat bestanden. **53 Frontendtests**,
Lint, Typprüfung, Produktionsbuild und **9 Chartanalyse-Browsertests** erfolgreich.
Die zusätzliche Kurvenprüfung bleibt auf den eingefrorenen realen Reihen im
Millisekundenbereich; der NAS-Universumscan wird nach Auslieferung neu erstellt.

```bash
cd backend
.venv/bin/pytest tests/domain/test_chart_patterns*.py -q
.venv/bin/python -m scripts.evaluate_published_chart_examples
.venv/bin/python -m scripts.evaluate_chart_holdout_v3
.venv/bin/python -m scripts.evaluate_chart_shape_stress --output /tmp/chart-stress.json
```
