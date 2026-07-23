# Fachlicher Audit der Rechenlogiken

Stand: 2026-07-23

Dieses Dokument trennt feste Rechenregeln von heuristischen Bewertungen. Die
Anwendung unterstützt regelbasierte Entscheidungen, liefert aber keine
statistisch kalibrierte Rendite- oder Verlustprognose.

## Markt

- Marktbreiten-Coverage ist der Anteil der am jeweiligen Handelstag vorhandenen
  Titel am angeforderten Universum. Historisch geladene, am Stichtag aber
  fehlende Titel erhöhen die Coverage nicht.
- Fehlende 50-/200-SMA-Breitenwerte werden als nicht auswertbar behandelt. Sie
  erzeugen weder ein künstliches Warnsignal noch eine grüne Freigabe.
- Advance/Decline-Ratios und Up/Down-Volumen-Ratios sind ohne Decliner bzw.
  Down-Volumen nicht definiert und werden dann als nicht verfügbar ausgegeben.
- A/D-Divergenzen vergleichen Index und Breite nur auf gemeinsamen
  Handelstagen.
- VIX/VXX-Werte werden höchstens drei Indexzeilen vorgetragen. Ältere Werte
  gelten als nicht verfügbar.
- Die Trendwende-Ampel folgt einer Zustandsmaschine. Nach Grün wird Rot nur
  durch einen Schluss unter dem Startschuss-Tief oder unter der 200-SMA
  ausgelöst. Eine verlorene 21/50-Ordnung setzt Aufwärtstrend auf Grün zurück.

## Aktien und Fundamentals

- Das normale RS-Rating vergleicht 3-, 6-, 9- und 12-Monats-Zeitfenster. Titel
  ohne vollständige 12-Monats-Historie oder mit mehr als vier Kalendertagen
  Rückstand zum Benchmark-Stichtag werden nicht mit vollständigen Historien
  gerankt.
- EPS- und Umsatzbeschleunigung benötigen drei vollständige Quartalswerte. Zwei
  Werte oder Lücken reichen nicht für den Bonus.
- Die Drei-Quartals- und Drei-Jahres-Regeln bestehen nur, wenn jeder
  auswertbare Zeitraum die konfigurierte 20-Prozent-Schwelle erfüllt.
- ROE benötigt für die Kernregel drei Jahre mit jeweils mindestens 17 Prozent.
  Bis zu zwei weitere Jahre über 17 Prozent erhalten einen kleinen Bonus.
- Der Gesamtscore ist der gleichgewichtete Mittelwert aus Technik,
  Fundamentals, Chartverhalten und gleitenden Durchschnitten. Er ist eine
  Checklisten-Heuristik, keine probabilistische Prognose.

## Portfolio

- Positionsgewichte beziehen sich auf den gesamten Depotwert inklusive Cash.
- Portfolio-ATR und Beta-Balancer werden nur ausgegeben, wenn die benötigten
  ATR-/Beta-Werte für alle Positionen vorhanden sind. Fehlende Werte werden
  nicht als ATR 0 oder Beta 1 ersetzt.
- Trade-Republic-Einstandswerte werden von EUR in USD umgerechnet. Yahoo-Kurse
  aus ausländischen Listings werden anhand ihrer Quotierungswährung ebenfalls
  nach USD umgerechnet. Die benötigten FX-Paare liegen im Price Cache und
  können bei Bedarf gecacht nachgeladen werden.
- Ein manuell gepflegter Stoppkurs bleibt ein USD-Wert und wird nicht erneut
  mit EUR/USD multipliziert.

## Verkauf

- Aktive Teilverkaufsstufen einer Strategie werden kumuliert. Eine aktive
  100-Prozent-Stufe überschreibt die Summe als finalen Ausstieg.
- Die zweite RS-Tranche greift nach drei Tagen unter der RS-21-EMA oder bei
  einem tieferen RS-Schluss als am Bruchtag.
- Bei der risikoaversen 21-EMA-Strategie verlangt die zweite Tranche tatsächlich
  einen tieferen Folgetag.
- Der 200-SMA-Bruch ist in der MA-Strategie sofort aktiv; 10-, 21- und 50-Tage-
  Linien behalten die konfigurierbare Rückeroberungsfrist.
- Prozent- und ATR-Schwellen für Peak-Rückgänge werden numerisch geprüft und
  nicht aus Anzeigetexten zurückgelesen.

## Bewusst beibehaltene Konventionen

- ATR wird wie in der Referenz-App als einfacher Durchschnitt der True Range
  berechnet, nicht mit Wilders rekursiver Glättung.
- Distributionstage, Chartsignale und Health Scores bleiben regelbasierte
  Heuristiken der migrierten Anwendung. Ihre Schwellen sind fachliche
  Einstellungen und keine aus historischen Daten kalibrierten Wahrscheinlichkeiten.
