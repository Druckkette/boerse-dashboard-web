# Verkaufsstrategien: Prüfung gegen Kapitel 6 und Buchprojekt

Stand: 5. Oktober 2026. Geprüfte Ausgangsversion: `fa04e0c` auf GitHub/main.

Die Settings-Überarbeitung hat keine zuvor global editierbaren Einstellungen entfernt: die bisherigen 13 Felder sind weiterhin vorhanden; vier Risikofelder kamen hinzu. Datenqualität, Systemstatus und 13F-Verwaltung stehen unter Jobs. Strategieauswahl, Grenzwerte und Baukasten waren zuvor ausschließlich pro Aktie im Verkaufsmonitor verfügbar. Diese Änderung ergänzt sie als globalen Standard und als Aktienanpassung in Settings → Überwachung & Alerts.

## Quellen und Prüfgrenze

- A. M. Groos, *Börse ohne Bauchgefühl*, Kapitel 6, Druckseiten 281–308 (PDF-Seiten 291–318).
- ChatGPT-Projekt **Buchprojekt**, Quellen `WRO 1-44.txt`, `WRO #49 Webby's 3-Day Rule to Identify Trend Changes.txt`, `WRO_56_bis_65_zusammengefuehrt.txt`, `WRO 66-78.txt` und `WRO_79-86_gesammelt.txt`. Durchgesehen wurden insbesondere die Passagen zu Verkauf, Halteregeln, Quick/QuickSand/Grateful Dead und Trendwechseln.
- `combined_alle_transcripts_unique.txt` ließ sich im Projekt weder in der Vorschau noch über den versuchten Download öffnen. Eine vollständige Prüfung jeder Datei des Projekts wird deshalb nicht behauptet.

Die Quellen beschreiben unterschiedliche Varianten. Die spätere WRO-Variante ersetzt nicht stillschweigend die Buchregeln. „Vorhanden“ bedeutet hier, dass die konkrete Logik implementiert ist; eine ähnliche Regel wird ausdrücklich als teilweise umgesetzt bezeichnet.

## Auswahl und Vererbung

Sieben Optionen sind verfügbar: RS-Linie täglich mit 21/50-SMA, Benutzerdefiniert, 21-EMA risikoavers, 21-EMA offensiv, Peak-Rückgang, Kauftag-Tief und MA-Brüche. Der Baukasten bietet alle **23 vom bestehenden Motor erkannten Kriterien**, einschließlich der zuvor nicht auswählbaren Häufung tiefer Schlusskurse, scharfem Einbruch ohne Rückeroberung, Verlusttagen und Rückfall auf den Kaufpreis. Das sind nicht sämtliche Regeln aus dem Buch.

Der globale Standard enthält Strategie, Grenzwerte und Baukasten. Aktien ohne eigene Konfiguration übernehmen ihn laufend. Bereits gespeicherte individuelle Konfigurationen bleiben eigene Regeln. Bei deaktivierter Option „Globale Verkaufsstrategie übernehmen“ wird das aktuell wirksame Setup zur anpassbaren Aktienkonfiguration. Beim erneuten Aktivieren und Speichern wird die eigene Konfiguration entfernt und wieder der globale Standard verwendet. Globale und Aktienregeln haben jeweils ausdrücklich beschriftete Speicheraktionen.

## Abgleich mit Kapitel 6

| Abschnitt | Buchregel | Umsetzung / Einschränkung |
| --- | --- | --- |
| 6.1 | Nothalt bei definierter Verlusthöhe | Prozent oder ATR auswählbar, universeller Komplettverkauf. Bewertet den aktuellen verfügbaren Kurs; keine vollständige Intraday-/Gap-Ausführungslogik. |
| 6.2.1 | Festgelegter Gewinn | Gewinnschwelle im Baukasten, Prozent/ATR. Bezug ist Einstand, nicht automatisch offizieller Pivot. Marktabhängige Gewinnbänder und automatische Einstandsstopps fehlen. |
| 6.2.2 | Deutlicher 21-EMA-Bruch | Zwei Strategievarianten und Custom-Kriterium. Nicht jede Volumen-/Kerzenbedingung des Buchs; risikoaverse Resttranche folgt 50-SMA/Nothalt statt vollständig der Buchfolge. |
| 6.2.3 | Starker Preisrückgang vom Hoch | Peak-Strategie mit zwei Schwellen und Trendbruch. 20-Tage-Hoch; differenzierte Rückeroberungs-/Retest-Folge nur teilweise. |
| 6.2.4 | Großer Abstand zu Durchschnitten | Vier Custom-Kriterien für 10-SMA/21-EMA/50-SMA/200-SMA. Prozent und ATR funktionieren. Rückfall unter den Schlusskurs der überdehnten Ankerkerze, nicht deren Tief; unmittelbarer Verkauf in Stärke fehlt als eigener Modus. |
| 6.2.5 | Viele tiefe Schlusskurse | Custom-Kriterium mit Anzahl/Fenster; unteres Kerzendrittel. Vollständiger Volumenkontext fehlt. |
| 6.2.6 | Schwache Industry Group | Fehlt als auswählbares Verkaufskriterium. Manuelle Branchenbewertung erzeugt keine eigene Verkaufstranche. |
| 6.2.7 | Scharfer Einbruch ohne Rückeroberung | Custom-Kriterium mit Prozent/ATR und Rückeroberungsfrist. |
| 6.2.8 | Häufung von Verlusttagen | Custom-Kriterium mit Zeitfenster; vereinfachte Zählregel. |
| 6.2.9 | Überschreiten oberer Trendkanallinie | Fehlt als Verkaufskriterium. |
| 6.2.10 | Größter Gewinn-/Volumentag | Custom-Kriterium mit Schwelle, Vergleichsfenster und Multiplikator. Earnings-Ausnahme und unabhängig größter Volumentag fehlen. |
| 6.2.11 | Split-Rallye | Fehlt. |
| 6.2.12 | Erschöpfungslücke | Kein eigenes Verkaufskriterium im Baukasten; Chartsignale sind kein Ersatz für die Tranche. |
| 6.2.13 | Abwärtsumkehr | Kein eigenes Verkaufskriterium im Baukasten. |
| 6.2.14 | Stau-Tage | Custom-Kriterium mit Anzahl, Fenster, Kursfortschritt und Volumenfaktor. |
| 6.3.1 | Rückkehr zum Pivot | Nur Annäherung über Kauftags-/Vortagstief. Pivot wird nicht als vollständige sequenzielle Verkaufsstrategie verwendet. |
| 6.3.2 | Bruch wichtiger Durchschnitte | Custom 10-SMA/21-EMA/50-SMA/200-SMA und Preset 50/200. Wochenvariante mit 10-Wochen-Linie und Haltefrist fehlt. |
| 6.3.3 | Untere Trendlinie gebrochen | Fehlt. |
| 6.3.4 | Verlustwochen | Custom-Anzahl, optional steigendes Volumen. Ausnahme für gesunde Drei-Wochen-Konsolidierung nicht vollständig umgesetzt. |
| 6.3.5 | Größter Tages-/Wochenverlust | Custom-Kriterien vorhanden; Bezug seit Kauf statt Beginn des gesamten Aufwärtstrends, mit Mindesthistorie. |
| 6.4.1 | RS-Linie | Nur Tagesbasis: 21/50 **SMA**; Erste zwei Anteile standardmäßig 25/25 %, editierbar; dritte Stufe verkauft den Rest (geplant 50 %). Zweite Tranche nach genau drei bestätigten Schlüssen in Folge unter 21-SMA; Bruchtag zählt mit. Dritte Stufe verkauft die gesamte Restposition, auch ohne vorherige Teilverkäufe. Buchbeispiel 20/30/50 einstellbar. Wochen-/Monatswechsel aus dem Buch nicht umgesetzt; auf ausdrücklichen Nutzerwunsch bleibt die Auswahl auf Tagesbasis. |
| 6.4.2 | Gewinnsicherungsfolge ab Pivot | Kein vollständiges Preset. Gewinnschwelle, Überdehnung, Linienbruch und Kaufpreis-Rückfall kombinierbar, aber ohne korrekte Pivot-/Zeitfolge und wiederholte Gewinnmitnahmen. |
| 6.4.3 | Gescheiterter Ausbruch | Preset Kauftag-Tief verkauft 50 % nach Rückeroberungsfrist, Vortagstief warnt. Die Buchfolge mit sofortigen Dritteln und die fünfstufige Intraday-/Schlusskursfolge samt Gap-Ausnahmen fehlen. |
| 6.4.4 | ATR-Regeln | Einheiten für Nothalt, Gewinn, EMA-Bruch, Peak, scharfen Einbruch, größten Anstieg und MA-Überdehnung vorhanden. Kein eigenständiges vollständiges ATR-Preset. |
| 6.5 | Wiederkauf / Aufstockung | Nur erläuternde Bedingungen, keine vollständige Regel für Wiederkauf und Aufstockung um 20 %. |

## Ergänzungen aus Buchprojekt

**WRO #73 – UPDATED Quick, QuickSand & Grateful Dead HOLDING Rules** beschreibt drei EMA-Linien auf der RS-Linie: täglich 21/34/50, wöchentlich 8/13/21 und experimentell monatlich 5/8/13. Diese neuere Variante ist **nicht umgesetzt oder auswählbar**. Das aktuelle RS-Preset mit zwei täglichen SMA-Linien darf nicht als WRO-73-Preset bezeichnet werden. Auch die Trennung zwischen einer zu haltenden Kernposition und einem flexiblen Positionsanteil ist nicht umgesetzt.

**WRO #49 – 3-Day Rule** verlangt in der Verkaufsrichtung nach dem ersten Schluss unter der 21-EMA weitere Kerzen vollständig unter der Linie, einschließlich ihrer Hochs und schwacher Schlusskurse. Das aktuelle EMA-Preset zählt Schlusskurse und einige Folgebedingungen; es ist keine vollständige Umsetzung dieser WRO-Regel.

Weitere WRO-Passagen zu Climax, Marktlage und diskretionärem Verkaufen liefern Kontext. Sie ergeben ohne präzise Regeldefinition keine zusätzlich implementierte Strategie. Eine echte Umsetzung der fehlenden Varianten benötigt eigene Presets, Zustandsfolgen und passende Tests. Wochen- und Monatsvarianten sind auf Nutzerwunsch nicht Teil der nächsten Erweiterung.

## Wirkung auf die Verkaufsempfehlung

1. Der Motor erkennt alle Kriterien und zeigt ihren Zustand an. **Aktiv allein bedeutet keine Verkaufstranche.** Nur Empfehlungen der gewählten Strategie tragen zum Verkaufsziel bei; andere aktive Kriterien bleiben Hinweise.
2. Im Baukasten werden die ausgewählten aktiven Tranchen addiert und bei 100 % begrenzt. Beispiel: Gewinnschwelle 20 % und Linienbruch 30 % aktiv ergeben ein Ziel von 50 % der ursprünglichen Position. Bei bereits protokollierten 20 % bleibt eine aktuelle Tranche von 30 %.
3. Der Nothalt gilt unabhängig von der Auswahl und erhöht das Verkaufsziel auf 100 %. Protokollierte Verkäufe werden auch hier abgezogen.
4. Vorschläge werden in ganzen Prozenten ausgegeben. Die bisherige Abrundung auf wenige feste Prozentstufen wurde entfernt: eine konfigurierte 20-%-Tranche wird nicht mehr zu 0 %.
5. Jedes Kriterium zeigt, ob es ausgewählt ist und wie seine Strategieempfehlung wirkt. Mehrere Kriterien können dieselbe Preset-Empfehlung erklären; die angezeigten Beiträge sind deshalb bei Presets nicht blind zu summieren. Maßgeblich ist die Liste der Strategie-Tranchen.
6. Der Zustands-/Gesundheitswert „Halten/Beobachten/Verkaufen“ ist eine separate Bewertung und setzt selbst keine Verkaufsprozente. Die Oberfläche bezeichnet ihn ausdrücklich als „Zustand“.
7. Die bestehende Bestätigung bleibt: Vorschläge von 33 % bis unter 75 % benötigen außerhalb der RS-Strategie in der Regel zwei aufeinanderfolgende Handelstage. Die RS-Stufen sind bereits durch Tagesschlüsse bestätigt und benötigen keine zusätzliche Bestätigung. Kleinere oder mindestens 75-%-Vorschläge sind sofort scharf. Nothalt umgeht Bestätigung und Snooze. Snooze unterdrückt die Freigabeanzeige, nicht die zugrunde liegende Prozentberechnung.
8. Es wird kein Brokerauftrag ausgelöst. Strategie-Tranchen sind kumulative Ziele; ein Custom-Baukasten ist keine frei programmierbare zeitliche Ereignisfolge.

## In dieser Änderung behoben

- Globaler Standard und eigene Aktienregeln mit gemeinsamer, vollständiger Auswahl.
- Alle 23 vorhandenen Kriterien im Baukasten zugänglich; doppelte Auswahl verhindert.
- Nicht ausgewählte aktive Kriterien erhöhten zuvor heimlich Custom-Verkaufsziele, teilweise bis 100 %. Diese Eskalation wurde entfernt.
- Konfigurierte kleine Tranchen wurden auf feste Stufen abgerundet, insbesondere 20 % auf 0 %. Jetzt bleiben die ganzen Prozentwerte erhalten.
- RS-Linien wurden als EMA beschriftet, obwohl SMA berechnet wurde. Beschriftung korrigiert.
- MA-Überdehnung ignorierte die gespeicherte ATR-Einheit. Jetzt verwendet sie ATR; fehlende ATR-Daten erzeugen keine Ersatzbewertung in Prozent.
- Die Worst-Loss-Regeln konnten auch bei ausschließlich positiven Kursänderungen aktiv werden. Jetzt erfordern sie einen tatsächlichen Verlust.
- Lange Durchschnitte verwendeten nur Kurse seit Kauf. Jetzt wird die vorhandene Vorgeschichte zum Aufwärmen genutzt, sodass z. B. 200-SMA nicht erst nach 200 gehaltenen Tagen verfügbar ist.

Die fehlenden Buch-/WRO-Strategien bleiben als konkrete Lücken dokumentiert. Diese Änderung behauptet keine vollständige Buchtreue und ersetzt bestehende individuelle Setups nicht durch neu interpretierte Regeln.


## Präzisierung der RS-Tagesstrategie

Die drei Stufen benötigen zwei Linien, nicht drei verschiedene Durchschnitte:

1. Bestätigter Tagesschluss der RS-Linie unter ihrem 21-Tage-SMA: erster eingestellter Anteil (aktuell 25 %).
2. Drei bestätigte Tagesschlüsse in Folge unter dem 21-Tage-SMA, einschließlich des ersten Bruchtags: zweiter eingestellter Anteil (aktuell 25 %). Das Ziel beträgt zusammen 50 %; protokollierte Verkäufe werden abgezogen.
3. Bestätigter Tagesschluss unter dem 50-Tage-SMA: gesamte Restposition. Geplant sind nach den ersten beiden Stufen aktuell 50 %. Bei einem direkten Bruch der langsamen Linie ohne vorherige Teilverkäufe sind es 100 %.

Die dritte geplante Tranche wird als `100 − erste − zweite` berechnet; die ersten beiden dürfen zusammen höchstens 100 % betragen. Intraday-Balken und vor Handelsschluss abgerufene Tagesbalken werden für die RS-Linie ausgeschlossen. Bewertet wird der letzte bestätigte gemeinsame Tagesschluss von Aktie und Benchmark. Eine explizite Stummschaltung bleibt wirksam; Nothalt ist davon weiterhin ausgenommen.

Der bisherige zusätzliche Auslöser „tiefer als am Bruchtag“ wurde entfernt: Er entsprach einer anderen WRO-Variante und konnte bereits am zweiten Tag auslösen. Ein langsamer Linienbruch führt jetzt unabhängig von den gerade aktiven frühen Stufen zum kumulativen Ziel von 100 %. Der Baukasten und die Strategie-Einstellungen stehen direkt bei der Auswahl und im Aktienmonitor vor den allgemeinen Regelübersichten.

## Aktuelle globale Grenzwerte und Zuständigkeit

Am 5. Oktober 2026 direkt am NAS geprüft. Diese Werte gelten für Aktien mit aktivierter globaler Übernahme. Sie stehen in Settings → Überwachung & Alerts → Globale Verkaufsstrategie → Grenzwerte. Bei eigenen Aktienregeln werden Änderungen im Aktieneditor nur für diese Aktie gespeichert. Beim Anlegen einer neuen Anpassung wird das aktuell wirksame komplette Setup kopiert. Ältere, nur teilweise gespeicherte Konfigurationen ergänzen nicht gespeicherte Werte aus dem globalen Standard; der erste neue Speichervorgang sichert das vollständig angezeigte Setup.

| Einstellung | Globaler Wert |
| --- | --- |
| Strategie / RS-Anteile | RS täglich, 25 % / 25 % / Rest (geplant 50 %) |
| Nothalt | 7 % Verlust vom Einstand |
| Gewinnschwelle | 20 % über Einstand |
| Deutlicher 21-EMA-Bruch | 2 % Abstand unter der Linie |
| Rückgang vom 20-Tage-Hoch | 8 % |
| Überdehnung 10-SMA / 21-EMA / 50-SMA / 200-SMA | 10 % / 15 % / 25 % / 70 % |
| Tiefe Schlusskurse | mindestens 4 im unteren Drittel in 10 Tagen |
| Scharfer Einbruch | 6 %; Rückeroberungsfrist 4 Tage |
| Verlusttage | Fenster 10 Tage; Verlusttage müssen Gewinntage überwiegen |
| Außergewöhnlicher Anstieg | 10 % oder 1,5-faches bisheriges Maximum im 20-Tage-Fenster, mit Volumenbedingung |
| Stau-Tage | mindestens 3 in 10 Tagen, maximal 1 % Kursfortschritt, Volumenfaktor 1,3 |
| Kauftags- und MA-Rückeroberung | jeweils 3 Tage; 200-SMA bleibt unmittelbar |
| Verlustwochen | 3; steigendes Volumen nicht verpflichtend |
| Größter Tages-/Wochenverlust | Vergleichshistorie 20 Tage / 4 Wochen |
| EMA risikoavers / offensiv | 25/25/25 % frühe Tranchen / offensiv erste 33 % |
| Peak-Preset | 8 % / 15 % Rückgang, jeweils 25-%-Tranche |
| Custom-Standard | Nothalt; weitere Regeln ausdrücklich auswählen |

Die Schwellen legen fest, wann ein Kriterium aktiv wird. Eine Verkaufstranche entsteht nur, wenn dieses Kriterium in der gewählten Strategie verwendet wird. Beim globalen RS-Standard erzeugt daher etwa das Erreichen von 20 % Gewinn allein keinen Verkauf.

## Technisch sinnvolle nächste Ergänzungen

Dies ist eine Machbarkeitsbewertung, keine Behauptung bereits integrierter Regeln. Trendkanal- und frei gezeichnete Trendlinien werden entsprechend der Nutzervorgabe ausgeschlossen. Eine automatische Regression wäre eine eigene Regel und kein gleichwertiger Ersatz für die im Buch eingezeichnete Linie.

| Ergänzung | Eindeutige technische Abbildung / benötigte Daten |
| --- | --- |
| WRO #49: vollständige 3-Tage-Verkaufsregel | Schlusskurs und anschließend gesamte Tageskerzen einschließlich Hoch unter der 21-EMA; Reihenfolge und Unterbrechungen aus OHLC bestimmen. Als eigenes Kriterium/Preset, nicht als heimliche Änderung der vorhandenen EMA-Regel. |
| WRO #73 auf Tagesbasis | Drei EMA der RS-Linie (21/34/50) mit getrennten Halte-/Verkaufsstufen. Berechenbar aus denselben bestätigten Kursreihen; eigenständige Alternative zur Buch-SMA-Strategie. |
| Buch: gescheiterter Ausbruch auf Schlusskursbasis | Datum des tatsächlichen Ausbruchs und Tief von Tag 1/Tag 0 festhalten; sequenziell Drittel und Nothalt. Ausbruchstag ausdrücklich wählen, nicht automatisch mit beliebigem Kaufdatum gleichsetzen. |
| Buch: Gewinnsicherungsfolge | Explizit gepflegter offizieller Pivot, Gewinnzone 20–25 %, Brüche 10-SMA/21-EMA/50-SMA; bereits ausgeführte Schritte pro Position speichern. Alternative: halber Verkauf am Gewinnziel, Rest beim Rückfall auf Einstand. |
| Größter Volumentag / Earnings-Ausnahme | Volumenmaximum in festgelegtem Fenster und bestätigte historische Earnings-Termine. Ohne Earnings-Daten die Ausnahme als nicht prüfbar kennzeichnen. |
| Rückfall nach Überdehnung unter das Ankertief | OHLC-Ankerdatum beim Überschreiten speichern; Rückfall unter das damalige Kerzentief statt Schlusskurs. Bestehende Regel als eigene Variante erhalten. |
| Downside Reversal und Erschöpfungslücke | Konkrete Kombination aus Hoch, Eröffnungs-Gap, Schlussposition in der Kerze, Volumen und vorausgehendem Anstieg. Ältere Entwürfe existieren in `strategies.py`, sind im aktuellen Motor aber nicht angeschlossen. Ein Erschöpfungs-Gap kann nur als regelbasierter Kandidat erkannt werden, nicht sicher als endgültiger Gipfel. |
| Schwache Industry Group | Numerische Branchen-RS, Rang oder definierter Rückgang über ein Fenster. Daten und Gruppenzuordnung müssen vorhanden sein; ein manuelles „Schwach“ oder bloß fehlende Daten dürfen nicht unbemerkt als berechnetes Signal gelten. |
| Verlustwochen mit Konsolidierungs-Ausnahme | Wochen-OHLC, Range, Rückgang und Volumen über drei abgeschlossene Wochen; Ausnahme mit expliziten einstellbaren Schwellen definieren. |

Eine Split-Rallye braucht verifizierte Split-Termine und konsistent bereinigte Kurse. Vorhandene Split-Kandidaten sind dafür nicht ausreichend. Die fünfstufige Intraday-Ausbruchsregel braucht echte Intraday-Daten: aus Tageshoch/-tief lässt sich die Reihenfolge der Verletzungen nicht zuverlässig rekonstruieren. Diese beiden Regeln sind deshalb mit dem aktuellen Datenbestand nicht sofort verlässlich integrierbar.
