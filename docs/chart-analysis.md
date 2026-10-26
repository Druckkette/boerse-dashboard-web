# Chartanalyse nach Kapitel 4.2

## Stand und Freigabe

Seit **26. Oktober 2026 auf ausdrücklichen Nutzerwunsch auf dem NAS aktiv**.
Die Erkennung ist eine nachvollziehbare geometrische Vorauswahl mit getrennten
Volumenhinweisen. Sie bewertet weder künftige Rendite noch eine Erfolgswahrscheinlichkeit.

Die technische Prüfung und die Kalibrierung an Buchbeispielen reichen nicht für
eine Aussage über die Trefferquote im gesamten Aktienuniversum. Eine zusätzliche
visuelle Stichprobe mit 32 Treffern aus 13 weiteren Aktien deckte unzulässige
Double-Bottom-Geometrien und zu großzügige Cup-Zuordnungen auf. Diese führten zu
Korrekturen und zusätzlichen Regressionstests. Die Stichprobe wurde dadurch zur
Kalibrierung verwendet und ist kein unabhängiger Nachweis der Erkennungspräzision.
Bei unruhigen Cup-Verläufen bleiben fachlich mehrdeutige Grenzfälle. Grüne
Softwaretests belegen keine allgemeine Erkennungspräzision.

Version `chapter-4.2-v3` verbessert die Behandlung asymmetrischer Cups,
Handle-Ausbrüche und späterer Strukturverletzungen. Im ursprünglichen
[Internetvergleich mit v2](chart-analysis-internet-validation.md) wurde einer von
fünf Quellenfällen erkannt; v3 erkennt **zwei von fünf**. Bei vier weiteren
Quellenfällen bleibt es bei **einem von vier**. Die Auswertung und der erste,
schlechtere Entwicklungsstand sind im [v3-Prüfbericht](chart-analysis-robustness-v3.md)
offen dokumentiert. Die Erkennung ersetzt die visuelle Musterprüfung daher nicht.
Für belastbare Präzisions- und Abdeckungswerte ist ein größerer, fachlich beschrifteter
Prüfsatz mit positiven und negativen Fällen erforderlich.

Version `chapter-4.2-v4` ergänzt die Auswertung sicherer Kursabschnitte und
begrenztes Nachladen auffälliger Historien. Einzelne Kursfehler sperren damit
nicht mehr automatisch die gesamte Aktie. Muster können keine Unterbrechung
überspannen. Vorgehen und Grenzen stehen im
[v4-Bericht zur Datenqualität](chart-analysis-data-quality-v4.md).

## Bedienung

- Neuer privater Menüpunkt **Chartanalyse** (`/chart-analysis`), in beiden
  Dashboard-Ansichten und im mobilen Menü.
- **Universum nach Mustern scannen** startet einen Celery-Job. Die Trefferliste
  zeigt Aktie, Muster, Basisbeginn, Erkennungsdatum, Ausbruchsdatum, Tiefe und Pivot.
  Filter für Aktienname/Ticker, Musterart und Zustand, jeweils mit Seitennavigation.
- Ein Klick auf einen Treffer öffnet `/chart-analysis/{ticker}` mit der gewählten
  Formation, ihren Eckpunkten und dem Pivot im vorhandenen Kerzenchart.
- Ticker direkt eingeben, etwa `AAPL` oder `SAP.DE`. Bei fehlenden/veralteten
  Kursen stößt diese ausdrückliche Suche einmalig einen bestehenden Aktienrefresh
  im Hintergrund an. Direkte Seitenaufrufe erzeugen keine automatischen Refreshs.
  Ein Chart ohne passendes Muster bleibt benutzbar.
- Auswahl zwischen mehreren historischen Mustern, Zeichnung ein-/ausblenden,
  Zoom, Verschieben und Vollbild über die bestehenden Chartwerkzeuge.
- **Historischer Prüfzeitpunkt** schneidet alle späteren Kurse vor der Erkennung
  ab. Auch Intraday-Kerzen werden über den jeweiligen Börsenkalender ausgeschlossen.
- **Musterparameter anpassen** ist in Übersicht und Chart erreichbar. Speichern
  erfolgt zentral in Postgres. Nach Änderungen wird der Chart neu geprüft; der
  bisherige Universumscan bleibt sichtbar und wird als veraltet gekennzeichnet.

## Regeln und Operationalisierung

Grundlage: Groos, *Börse ohne Bauchgefühl*, Kapitel 4.2, Buchseiten 146–171.
Das PDF bleibt außerhalb des Repositorys. Regeln wurden in eigene Prüflogik
übersetzt; die Buchabbildungen werden nicht veröffentlicht.

| Muster | Kernregeln der Erkennung |
|---|---|
| Cup with Handle | Cup ab sechs Wochen, standardmäßig 12–50 % Tiefe; breite Bodenzone, fallende und steigende angepasste Kurve, Vergleich gegen zwei gerade V-Schenkel. Zusätzliche asymmetrische Formen benötigen einen deutlich besseren runden Fit. Einstellbares maximales Zeitverhältnis standardmäßig 3. Rechter Rand höchstens 15 % unter linkem Rand, marginale Intraday-Überschreitungen bis 1,5 % zulässig. Handle fünf bis 25 Handelstage, standardmäßig 5–15 % tief, vollständig in oberer Cup-Hälfte, Midpoint-Regel, Abwärtsdrift mit Erholung oder bestätigendem Ausbruch. |
| Cup without Handle | Gleicher Cup-Formfilter, Rückkehr bis nahe an den linken Rand; Pivot am linken Rand. Ein Setup ist von einem Schlusskursausbruch getrennt. |
| Double Bottom | Mindestens sieben Wochen; zweites Tief unter erstem, maximaler Unterschuss standardmäßig 10 %; Gesamttiefe höchstens 50 %. Mittelgipfel unter linkem Peak und über der Basismitte. Kein weiteres tieferes Tief zwischen zweitem Tief und Erkennung. Pivot am Mittelgipfel. |
| High Tight Flag | Mastanstieg mindestens 90 % in vier bis acht Wochen; Flagge drei bis fünf Wochen, 10–25 % tief. Pivot am Flaggenhoch. Anstiege über den typischen 120 % werden nicht pauschal ausgeschlossen; die einstellbare Obergrenze liegt standardmäßig bei 1.000 %. |
| Box | Mindestens vier Wochen, höchstens 15 % Tiefe; mindestens zwei zeitlich getrennte Tests beider Begrenzungen und geringer linearer Drift. Pivot am tatsächlichen Hoch der Basis. |

Der Basisbeginn ist die erste Sitzung einer negativen Kalenderwoche nach einem
lokalen Hoch, gemessen am Wochenschluss gegenüber der Vorwoche. Die Suche nach
dem linken Peak umfasst die zehn vorangehenden Sitzungen und diese negative
Woche selbst. So kann eine enge positive Woche zwischen Peak und Basisbeginn
liegen. Der linke Formationspunkt und der Beginn der Dauerzählung bleiben getrennt.
Maximale Basisdauer standardmäßig 65 Wochen; Analysefenster 850 Kalendertage.

Der Formfilter arbeitet mit drei Sitzungen geglätteten Schlusskursen. Quadratische
und kubische Anpassungsfehler werden durch die Basistiefe normiert. Zusätzliche
asymmetrische Kandidaten werden nur zugelassen, wenn der kubische Fehler höchstens
85 % des V-Fehlers beträgt. Andernfalls gelten weiter die konservativen symmetrischen
Quadratikregeln; der relative V-Vergleich kann zusätzliche Kandidaten verwerfen.
Die Zeitverteilung wird am Minimum der angepassten Kurve gemessen; eine einzelne
Tiefstkerze bestimmt sie nicht allein. Unruhige Verläufe erhalten einen Hinweis.
Diese Zahlen, die Zeitabstände
für lokale Wendepunkte und die Rückkehrschwellen sind technische Näherungen für
qualitative Buchmerkmale, keine wörtlichen Buchregeln. Der Formfilter ersetzt
deshalb die visuelle Prüfung nicht.

Volumen wird separat bewertet. Standardmäßig werden geometrische Muster auch
bei unbestätigtem oder fehlendem Volumen angezeigt, mit ausdrücklichem Hinweis.
Der zuschaltbare Pflichtfilter verlangt vollständige positive Volumendaten und
Rückgang gegenüber dem Vergleichsabschnitt (Standard 0,9; Flagge 0,75).
Die Bestätigung eines Ausbruchs verlangt unabhängig davon das 1,4-Fache des
vorangegangenen 50-Sitzungs-Mittelvolumens. Die Ausbruchssitzung ist nicht in
diesem Mittel enthalten. Dieser Faktor ist ein einstellbarer technischer Standard.

`ready` bezeichnet eine geometrisch erkennbare Basis; `breakout` einen späteren
Schlusskurs über Pivot mit Volumenbestätigung. Ohne diese Bestätigung wird
`unconfirmed_breakout` verwendet. Ein vor dem Ausbruch auch nur intraday
unterschrittener Boden ergibt `invalidated`. Bei Handles gelten zusätzlich
Maximaltiefe und obere Cup-Hälfte. Die erste Ausbruchssitzung darf den zuvor
fertigen Handle bestätigen; ihre Kurse fließen nicht in dessen Pivot ein.
Handles laufen nach ihrer eingestellten Höchstdauer ab (ein anschließender
Ausbruchstag ist zulässig); ansonsten gelten 35 Kalendertage ab Erkennung als Ablaufgrenze.
Diese Zustände beschreiben historische Ereignisse. Sie sind kein aktuelles
Kaufsignal und keine Bewertung, ob ein Ausbruch später erfolgreich blieb.

RS-Linie, Marktumfeld und Stellung zu gleitenden Durchschnitten werden in dieser
Version nicht vollständig automatisiert geprüft. Der fehlende Nachweis eines
vorausgehenden Anstiegs von etwa 30 % wird als Hinweis gezeigt. Optionale Handles
an Double Bottoms werden nicht gesondert modelliert; hier bleibt der Pivot am
Mittelgipfel. Das ist eine dokumentierte Grenze gegenüber dem gesamten Kapitel.

## Daten, Speicherung und Ausführung

- Tages-OHLC auf der bestehenden splitbereinigten Yahoo-Kursbasis. Der zusätzliche
  `split_adjustment_factor` aus der Transaktionsbewertung wird nicht erneut angewandt.
  Dividendenbereinigte Schlusskurse werden nicht mit OHLC vermischt.
- Fehlende oder ungültige OHLC-Werte erscheinen im Chart als leere Stellen.
  Widersprüchliche Tageskurse und doppelte Daten unterbrechen die Auswertung;
  Lücken über zehn Kalendertage und Tagessprünge über 60 % trennen Abschnitte.
  Jeder saubere Abschnitt mit mindestens 25 Handelstagen wird einzeln geprüft.
  Ein großer Sprung ist ein Verdachtsfall und kann eine echte Bewegung sein.
- Der Scan prüft alle gespeicherten Instrumente der Anlageklasse `stock`, jeweils
  in Batches von 25. Der Worker lädt zuvor auffällige Kursreihen begrenzt nach
  (standardmäßig 100 Ticker/300 Sekunden), mit Wartefristen und Rate-Limit-Stopp.
  Gemeinsame Preisbasen werden nur nach vollständiger Validierung ersetzt.
  Normale Lesezugriffe bleiben netzwerkfrei. Die Übersicht unterscheidet
  vollständig, teilweise und nicht auswertbare Aktien mit konkreten Gründen.
- Bestehende AppSetting-Tabelle: `chart_analysis_config_v1` und
  `chart_analysis_scan_v1`, zusätzlich `chart_analysis_price_repairs_v1` für
  Wiederholungsfristen. Keine neue Datenbankmigration.
- Erst nach erfolgreichem Scan wird der komplette neue Ergebnisstand publiziert.
  Abbruch oder Fehler erhalten den vorherigen Stand.
- Algorithmusversion plus kanonisch validierte Parameter bestimmen die Kennung.
  Die Muster-ID enthält zusätzlich die tatsächlichen Formationsdaten. Ein
  verschwundener Listentreffer wird nicht stillschweigend durch einen anderen ersetzt.
- Überlappende ähnliche Formationen werden reduziert; verschachtelte Muster
  unterschiedlicher Größen können nebeneinander bestehen. Die genauere spätere
  Klassifikation kann eine frühere Cup-ohne-Handle-Darstellung ersetzen.
- Kein automatischer Zeitplan und keine Änderung der öffentlichen Beta-Freigaben.

API unter `/api/v1/chart-analysis`: `GET /config`, `PUT /config`, `GET /results`,
`POST /scan`, `GET /{ticker}?as_of=YYYY-MM-DD`. Alternativ startet
`POST /api/v1/jobs` mit `type=scan_chart_patterns` den Scan. Der Worker ist über
die bestehende Standardqueue und Jobfortschrittsanzeige angebunden.

## Prüfbelege vom 26.10.2026

Letzter lokaler Gesamtstand mit v3: Backend **1.550 bestanden**, 55 ohne zusätzliche
Integrationsdienste übersprungen; die Postgres-Integration wurde separat in einer
frischen Docker-Datenbank ausgeführt. Frontend **53 Unit-Tests bestanden**, Lint,
Typprüfung und Produktionsbuild erfolgreich. **Neun Chartanalyse-Browserprüfungen bestanden**,
einschließlich mobiler Darstellung und zentralem Speichern des neuen Zeitverhältnisses.

Eingefrorene reale Kurse in `backend/tests/fixtures/chart_patterns/`, mit Herkunft
und Prüfzeiträumen im Manifest. Die Tests benötigen keine Live-Marktdaten.

| Aktie | Muster | Erkannt | Schlusskursausbruch |
|---|---|---|---|
| IBKR | Cup with Handle | 09.06.2025 | 27.06.2025 |
| RCL | Cup with Handle | 27.05.2025 | 30.05.2025 |
| TBBK | Cup without Handle | 15.07.2024 | 16.07.2024 |
| NFLX | Double Bottom | 15.04.2025 | 22.04.2025 |
| SNEX | Double Bottom | 22.04.2025 | 23.04.2025 |
| RKLB | High Tight Flag | 23.12.2024 | 26.12.2024 |
| SMCI | High Tight Flag | 03.07.2023 | 11.07.2023 |
| IBKR | Box | 16.06.2025 | 27.06.2025 |

Die ersten fünf Fälle stammen aus den annotierten Buchbeispielen. Die drei
weiteren wurden zusätzlich visuell im implementierten Chart geprüft. Die acht
Fälle sind eine Kalibrierungs- und Regressionssammlung. **8/8 ist keine Aussage
über Präzision oder Recall im Aktienuniversum.** Ausbruch bedeutet hier nicht
automatisch Volumenbestätigung; diese wird je Fall separat ausgewiesen.

Weitere Gegenbeispiele: saubere und verrauschte V-Erholungen, monotone Trends,
konstante Kurse, zu tiefer Handle, höheres zweites Tief, zu schwacher Flaggenmast,
fehlendes Volumen, Datenfehler und ein nachträglich unterschrittenes zweites Tief.
Reale AMD-/AMZN-Reihen sichern die in der Stichprobe gefundenen Tiefpunktfehler ab.
Für alle acht positiven Fälle wird die Erkennung nochmals mit einem exakt am
behaupteten Erkennungstag abgeschnittenen Kursverlauf geprüft.

Die HWM-Box im Buch erreicht nach der ersten negativen Woche nicht die
Mindestdauer von vier Wochen vor ihrem Ausbruch. Die gezeichnete CELH-Flagge
von 2020 dauert deutlich länger als die numerische Drei-bis-fünf-Wochen-Regel.
Die Implementierung folgt hier den numerischen Regeln und übernimmt diese
Ausnahmeabbildungen nicht unkritisch als automatische Positivfälle.

Ausführbare Prüfungen:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/pytest
# PostgreSQL-Tests nur mit einer separaten Datenbank namens audit_tests:
TEST_POSTGRES_URL=postgresql+psycopg://test:test@127.0.0.1:15483/audit_tests .venv/bin/pytest tests/integration
cd ../frontend
npm run lint
npm run typecheck
npm test
npm run build
npx playwright test tests/e2e/chart-analysis.spec.ts
```

Die neuen Browserfälle benutzen den echten Erkennungsalgorithmus mit den
eingefrorenen Kursen, einer eigenen Testkonfiguration und dem produktiven
Frontendbuild. Sie prüfen beide UI-Modi bei 1440 und 390 Pixeln, Trefferklick,
Musterzeichnung, Tickersuche, historische Grenze und Parameterspeicherung mit
Scanveraltung. Echte Postgres-Tests prüfen Persistenz, einen vollständigen Scan
und den Erhalt des vorherigen Ergebnisstands bei Abbruch.

Version `chapter-4.2-v2` korrigiert die Peak-Suche und verlangt beim Double Bottom
mindestens drei Sitzungen zwischen jedem Tief und dem Mittelgipfel. Eine Kerze
kann somit nicht zugleich Tief und Mittelgipfel sein. Die Algorithmusversion
geht in den Parameterhash ein; Ergebnisse der Vorgängerversion werden veraltet.
