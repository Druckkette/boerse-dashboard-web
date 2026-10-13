# Informationsscores unter der Trendampel

Umsetzung der Excel-Anweisungen vom13.10.2026 (`Kriterien`, Spalte F) und der bestätigten Entscheidung für fachliche Unterscores von0–100. Alle91 Anweisungen sind mit Zuordnung in [market-context-instructions.json](market-context-instructions.json) erfasst. Die Excel selbst wird nicht verändert.

Die Trendampel steht über den fünf Kennzahlen und bestimmt Phase, Farbe und Handlung. Es gibt keinen zusammengefassten Depot- oder Handelsscore aus diesen Kennzahlen. Insbesondere Schutz bei Equal Weight und Risk Off bei Volatilität haben keine Sperrwirkung auf die Ampel. Die vorhandenen Frühwarn-, Warn-, Breiten-, Sentiment- und Chartblöcke bleiben erhalten.

## Aufbau und Gewichtung

| Kennzahl | Unterscores und Anteil an der Kennzahl | Gewichtete Kriterien innerhalb der Unterscores |
|---|---|---|
| Index | Verkaufsdruck45%; Schlussqualität/Nachfrage35%; Trendbestätigung20% | W01:1, W03:0,5, W04:0,5; W02:1, W05:0,5, W11:0,5; A09:1, A11:1 |
| Marktbreite | Trendteilnahme30%; Breitenmomentum20%; A/D15%; neue Hochs/Tiefs20%; Volumenbreite5%; Breitenschub5%; Erholung5% | B01:1, B02:1, B11:0,5; D07:1; B04:0,5, D02:0,25; B05:1, B10:0,5; D03:0,25; D04:0,25; W14:0,5 |
| Powertrend | Bestätigter Status70%; Start/Erholung30% | P05:1, P06:2; P01 oder P03:1, abhängig vom formalen Zustand |
| Equal Weight | Bestätigter Breitenzustand80%; Bestätigung/Stabilität20% | E01:0,5, E03:1,5; E04:1. E02 ist neutral und ohne zusätzliches Gewicht. |
| Volatilität | VIX40%; VXX40%; gemeinsames Regime20% | V01/V02 je1; V04/V05 je1; V07:3, V06:1, V08:1, V09:0,5. V03 bleibt reine Anzeige. |

Unterscore = Summe(Gewicht×Kriteriumswert) / Summe(bewertbarer Gewichte). Kennzahl = Mittelwert mit effektivem Gruppengewicht = Gruppengewicht × bewertbarer Kriterienanteil. Fehlende Kriterien übertragen ihr Gewicht nicht auf vorhandene Gruppenmitglieder. Jeder angezeigte Kriterienbeitrag benennt ID, Messwert, Gewicht, Wert, Anteil am Unterscore und Regel. Der Anteil ist ein normalisierter Anteil an diesem Unterscore, keine Portfoliogewichtung. Regelversion der nachgeprüften Scores: `market_context_v2`. Powertrend ist erst mit54 vollständigen Kurssitzungen bewertbar. W01 und W03 benötigen elf Kurssitzungen für zehn Tagesvergleiche; W03 benötigt keine Volumen-SMA50.

Die Unterscore-Anteile sind explizite neue Designwerte. Sie wurden nicht als Renditeoptimum kalibriert. Frühere Excel-Achsen Kauf/Halten/Risiko wurden nicht ungekennzeichnet in einen einzigen Handelsscore umgerechnet. Die übernommenen relativen Einzelgewichte orientieren sich anV2; D02–D04 sind auf Nutzerwunsch klein. Diese neue Scorearchitektur ist nicht Gegenstand der bisherigen ETF-Backtests.

## Werte und Status

- 0–<40: schwach; 40–<65: gemischt; ≥65: konstruktiv. Es wird der mit zwei Nachkommastellen gespeicherte Wert bewertet und angezeigt.
- Negative Indexwarnung bestätigt:0, nicht bestätigt:100. Eintritt/Austritt je2 vollständige Sitzungen. A09 ist außerhalb des bestätigten Aufwärtstrends neutral50, im Aufwärtstrend100. A11 ist ohne Negation100, mit Negation0.
- B01/B02/B11: gemessener Anteil über dem jeweiligen Durchschnitt direkt als Wert0–100. Dadurch gibt es eine abgestufte Teilnahmebewertung statt einer neuen harten45%-Sperre. Die alten Farbstufen bleiben Anzeige.
- D07 McClellan: >125→100; >80→90; >50→80; >0→65; exakt0→50; >−50→35; >−80→20; >−125→5; sonst0. B03 erhält keinen zweiten Beitrag.
- A/D-, NH/NL- und Up/Down-Volumen-Verhältnisse: <0,8→0; 0,8–<1→40; 1–<1,5→60; 1,5–<2→75; ≥2→100. Positive Zählersumme bei Nenner0 ist konstruktiv (∞); beide Summen0 sind nicht bewertbar. Drei Sitzungen fürB04/B05/D03,20 fürB10. B10 glättet die vorhandenen NH/NL-Zählungen über20 Sitzungen. Dieses Summenfenster ist nicht die Hoch-/Tief-Referenz einzelner Aktien. Die bestehende Berechnung verwendet bis252 Vorwerte (mindestens20); die tatsächliche Referenz ist im Cache nicht gespeichert. Deshalb keine gesicherte52W-Aussage bei Altbeständen.
- D02: Indexschluss ≥99,8% des höchsten Hochs der vorherigen20 Sitzungen, A/D darunter ohne neuen A/D-Höchststand. Eintritt3, Austritt2 Sitzungen. Bei negativer A/D-Linie ist ein Prozentpuffer mathematisch ungeeignet; es wird das exakte vorherige Maximum verglichen.
- D04 Deemer: ≥1,97→100; ≥1,5→75; ≥1→50; darunter25. Zehn Sitzungssummen Advancer/Decliner; D05-Rückblick liefert keinen zusätzlichen Bonus.
- Powertrend: P05 beiON100, sonst neutral50; P06 beiDruck0, sonst50. Die Start-/Erholungsfortschritte sind der Anteil erfüllter vier Bedingungen. BeiON bleibt Vorbereitung100, selbst wenn einzelne Startbedingungen später verloren gehen. Alleiniger Scoreanstieg aktiviert keinen Powertrend.
- Equal Weight: E01 bei bestätigtem Rückenwind100, sonst50; E03 bei bestätigtem Schutz0, sonst50. Bestätigte Wachsamkeit bedeutet keine weitere Strafgewichtung. E04 verstärkt die bestätigte Richtung: Rückenwind100, Wachsam50, Schutz0; ein laufender Wechsel bei gültigem bisherigen Modus bleibt50. Die Gesamtwerte stabiler Zustände sind dadurch70/50/10 statt bisher70/60/30. Fehlende/unbestätigte Quellen sind unbekannt.
- Volatilität: aktiver VIX-/VXX-Stress0, Ruhe/Entspannung100, inaktive Beiträge neutral50. Im gemeinsamen Regime Risk Off0, Schock/fragile Rally25, Risk On100; inaktive Zustände50. Die gegensätzlichen Rohzustände erzeugen nicht mehrere aktive Stressereignisse. Das gemeinsame Regime hat nur20% Gewicht, da es von denselben Rohdaten abhängt. Es ist kein unabhängiger dritter Nachweis.

## Informationsmerkmale und Doppelzählung

W01–W14 erscheinen im Indexblock. W06/W08 (Überdehnung), W07/W09/W10 (MA-Brüche), W12/W13 (Intermarket/Sektoren) erhalten Gewicht0. Für W14 entscheidet die spezifische Excel-Anweisung: gewichtet bei Marktbreite, beim Index nur Verweis. MA-Brüche sind bereits Teil der maßgeblichen Ampel.

W12 bleibt eine Anzeige im bisherigen Block. Die sinnvolle Schwellenkorrektur ausV2 ist umgesetzt: mindestens ein Index nahe20T-Hoch, mindestens ein anderer mehr als2% darunter; eine marginale Abweichung von0,2% löst allein keine Divergenz mehr aus.

B06 Coverage ist Dateninformation; B07 wird nicht zusätzlich zum Volatilitätsscore gezählt. B08 Margin Debt bleibt im bisherigen Sentimentblock. D01 bleibt im bisherigen Russell/S&P-Vergleich. D05/D06/D08/D09 sowie B09 sind Anzeige oder abgeleitete Diagnose, keine zusätzliche Vollgewichtung. P02/P04 erklären die Powertrendmaschine, P06 bewertet deren Druck einmal. H01/H04/H06 verlieren ihre bisherigen Kontext-Overrides.

## Antworten auf offene Excel-Fragen

**A19/A22: Swing-Struktur.** Der Code berechnet Wendepunkte aus echten High-/Low-Kerzen und ATR21. Erst eine Gegenbewegung von1,5 ATR bestätigt einen Pivot. Je zwei bestätigte Hochs und Tiefs werden verglichen; ein Toleranzbereich von0,25 ATR trennt höher/tiefer von gleich. Aufwärtsstruktur verlangt höhere Hochs und höhere Tiefs; Abwärtsstruktur tiefere Hochs und tiefere Tiefs. A19 prüft den Bruch des zuvor im Aufwärtstrend gespeicherten höheren Tiefs. Das ist kausal reproduzierbar und bereits durch Präfix-/Strukturtests abgedeckt; Berechenbarkeit ist kein Beweis optimaler Rendite. Diese Preisregeln bleiben bestehen und werden im Indexdetail erklärt.

**W14: Erholungsquote.** Beispiel: Hoch100, Tief90, aktueller Schluss94:40% des Rückgangs sind aufgeholt, obwohl der Kurs seit Tief nur4,44% gewonnen hat. Berechnet aus dem kausalen60-Sitzungs-Fenster, bei>5% Rückgang und mindestens5 Sitzungen seit Hoch. Ohne relevante Korrektur entsteht kein Malus. Auf deinen Wunsch dient sie als kleiner Marktbreitenbeitrag; fachlich ist sie ein indexbasierter Erholungskontext.

**B09: interne Breitenphase.** Legacy-Diagnose aus Universe-MA-Anteilen und Warnzahl. Sie ist keine zweite maßgebliche Trendampel und wird nicht erneut gewichtet.

**E04: Bestätigung.** Für RSP und QQEW wird der Schluss relativ zum höchsten Hoch der letzten252 Sitzungen berechnet; der größere Abstand entscheidet. Bis4% Rückenwind, bis8% Wachsam, darüber Schutz. Der Kandidat muss drei gemeinsame abgeschlossene Sitzungen bestehen. Das dämpft einzelne Ausschläge. Die Bestätigung verstärkt die Richtung des Zustands und ist keine unabhängige Marktevidenz. Ein stabiler Schutzzustand verbessert den Score nicht.

**D12: Diagnose-Checkliste.** Die API berechnet vorhandene Prüfungen aus Trend, Breite, Intermarket, Volatilität und Sektoren. Eine separate Diagnose-Komponente kann die komplette Checkliste anzeigen; sie ist in der aktuellen Marktseite nicht eingebunden. Die Marktseite nutzt die Diagnose-API für ihre vorhandenen Intermarket- und Sektorblöcke. D12 ist kein unsichtbares Zusatzgewicht der fünf Kennzahlen.

**D13: Drawdown-Diagnose.** Die API prüft den Rückgang des ausgewählten Index gegenüber dem höchsten Schlusskurs in der geladenen420-Kalendertage-Historie. Der Wert gehört zur internen Diagnose-Checkliste; es gibt dafür keinen zusätzlichen sichtbaren Scorebeitrag. Er ist nicht identisch mit dem eigenen Trendhoch der harten Ampelregeln oder der Erholungsquote W14.

**Q02: gültiges Volumen.** Positive, zeitlich zugehörige Indexwerte und ausreichende Indexhistorie für die jeweilige Volumenberechnung. Es wird weder ETF-Volumen beigemischt noch ein fehlender Index durch ETF-Kurse ersetzt. W03/W04/W11 bleiben ohne passende Volumenhistorie unbewertet. Vorhandene Preis-/Strukturbeobachtungen bleiben separat verfügbar.

**Q03: Sektoren/FINRA.** Sektoren werden nur für den bisherigen Rotationsblock W13 benötigt, der nicht gewichtet wird. FINRA veröffentlicht die monatliche Margin-Debt-Reihe B08. Weder Sektoren noch Margin Debt sind Pflichtquellen der neuen Scores; fehlende Werte verursachen keinen Kauf- oder Risikomalus.

## Datenstand, Isolation und Grenzen

Die UI fordert Scores für dieselbe bestätigte Sitzung und denselben ausgewählten Index wie die Ampel an. Intraday-/spätere Zeilen werden vor Berechnung ausgefiltert. Jede Breitenzeile ist an den Indexkalender gebunden: keine stillschweigende Vorwärtsfüllung von A/D/Volumen-Verhältnissen. Equal Weight benötigt volle252 Sitzungen, zeitgleicheRSP/QQEW-Werte und tatsächliche Tagesbestätigung. Für die Kontextbewertung benötigt jeder der drei Equal-Weight-Bestätigungstage ein vollständiges252-Sitzungs-Fenster (früheste Erstbestätigung nach254 Sitzungen); Datenlücken zählen nicht mit. VIX benötigt21 aktuelle Sitzungen, VXX26 für den Vergleich EMA21 mit fünf Sitzungen zuvor und SPY sechs für die Fünf-Sitzungs-Rendite; das kombinierte Regime wird nicht mit fehlenden Rohquellen als Ruhe eingestuft.

Fehlend ist weder0 noch eine Markt-Warnung. Fehlende gewichtete Kriterien werden aus dem Mittelwert genommen; die reduzierte Bewertungsabdeckung und Einzelhinweise stehen daneben. Sind weniger als50% der konfigurierten Gewichtung bewertbar, bleibt der Gesamtwert offen. Ein allein bekannter W14 kann dadurch keine gesunde gesamte Marktbreite vortäuschen. Dieser Verfügbarkeitsstatus beeinflusst ausschließlich die Informationsanzeige.

Änderungen der Ampel: A20-Warnhäufung entfällt als Phasenwechsel; Version `trend_ampel_v5`. Originale harte Rot-Regeln A14/A15 sowie bestätigte MA-/Preis-/Strukturbrüche bleiben bestehen. Neue Informationsscores werden niemals in die Zustandsmaschine zurückgereicht. Historische archivierte Empfehlungen werden nicht überschrieben; Rekonstruktionen benennen ihre heutige Regelversion.

Die Gewichte und neuen Statusbänder sind transparente Designwerte. Technische Grenz-, Datenlücken-, Sitzungs- und Regressionstests belegen die Implementierung, keine zukünftige Anlageleistung. Ein neuer Backtest wäre ein gesonderter Test der neuen Architektur.
