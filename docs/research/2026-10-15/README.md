# 13F-Daten und Aktien-Backtests · 15. Oktober 2026

**VEEV ist repariert. Die 13F-Abdeckung ist deutlich verbessert, aber weiterhin nicht vollständig. Die Backtests liefern einen Ausstiegsvergleich; sie belegen noch keine langfristige Überrendite der Top-3-Aktienauswahl.**

## 13F-Abdeckung des gesamten aktiven Universums

| Stand | Aktuelle Berichtsperiode | Veraltet | Fehlend |
|---|---:|---:|---:|
| Vor der Reparatur | 3.690 | 238 | 1.634 |
| Nach der Reparatur | 5.009 | 4 | 549 |

Damit haben **1319 zusätzliche Aktien** die erwartete Berichtsperiode. Geprüft wurden alle 5.562 aktiven Universumsmitglieder.

Bei VEEV scheiterte die Zuordnung von „VEEVA SYS INC CL A COM“ zu „VEEVA SYSTEMS INC“. Die SEC-Datei enthielt bereits 1.064 institutionelle Halter. Nach dem Import ist die 13F-Qualität auf dem NAS `fresh`, Berichtsperiode **30.06.2026**. Auch alle anderen Datenqualitätsbereiche von VEEV waren bei der abschließenden API-Prüfung aktuell.

Die Reparatur verwendet standardisierte vollständige und abgekürzte Namen, Rechtsformzusätze, die aktuellen Handelsnamen und bei eindeutigen Treffern dieselben Namen in anderer Wortreihenfolge. Lange, exakt übereinstimmende und im gesamten Namensbestand eindeutige Präfixe beheben abgeschnittene Firmennamen; kurze oder mehrdeutige Präfixe bleiben ausgeschlossen. Bereits gespeicherte, eindeutige CUSIP-Zuordnungen werden als Rückfall verwendet, wenn der aktuelle Name allein nicht zuordenbar ist. Mehrdeutige Zuordnungen bleiben offen. Fehlende Zahlen werden nicht geschätzt. Der regelmäßige 13F-Lauf umfasst künftig das ganze Universum; der globale Status zählt aktuelle, alte und fehlende Titel, statt nur den jüngsten Datensatz irgendeiner Aktie zu prüfen.

**Offen bleiben 553 Titel: 549 ohne gespeicherte 13F-Daten und 4 mit altem Stand.** Die vorhandene Quelle und die eindeutigen Zuordnungen reichen für sie noch nicht aus. Diese Lücken sind nicht als „keine institutionellen Halter“ oder als aktuell umgedeutet. Ob jeweils ein Name, eine Wertpapierklasse, eine Umfirmierung, ein erst späterer Börsengang oder fehlende öffentliche Holdings ursächlich ist, ist damit noch nicht für jeden Einzelfall geklärt.

Zusätzlich wurden über die bereits konfigurierte FMP-Verbindung 248 Profile geprüft: 230 lieferten gültige, prüfsummengeprüfte CUSIP-Kennungen, vier hatten einen Zuordnungskonflikt und 14 keine gültige CUSIP. Weitere Abrufe wurden mit **HTTP 429** begrenzt; 514 Anfragen blieben zurückgestellt. Der Bulk-Zugang war mit HTTP 402 nicht verfügbar. Erfolgreiche Kennungen sind auf dem NAS gespeichert und werden bei einem erneuten Lauf aus dem Cache verwendet. 36 der geprüften Profile nennen einen Börsengang nach dem aktuellen 13F-Berichtsstichtag; dieses Merkmal ist in der CSV gesondert gekennzeichnet. Anbieterbeschreibung: [FMP Company Profile mit CUSIP, ISIN und IPO-Datum](https://site.financialmodelingprep.com/developer/docs/stable/profile-symbol).

[Vollständige Abdeckung je Aktie](13f-coverage.csv) · [Alle offenen Fälle](13f-unresolved.csv)

„Aktuell“ bezeichnet die fällige Berichtsperiode, keinen heutigen Besitzstand der Institutionen. Die SEC veröffentlicht ihre Sammeldaten quartalsweise. Für den 15.10.2026 ist der 30.06.2026 der erwartete vollständig meldepflichtige Zeitraum; die nächste Frist ist am 16.11.2026. Wochenenden und US-Bundesfeiertage werden in der Fristberechnung berücksichtigt. Quellen: [SEC-Datensätze](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets), [SEC FAQ 25 mit den Fristen 2026–2028](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f).

## Top-3-Auswahl: echte gespeicherte Empfehlungen

Die Datenbank enthält 54 Top-3-Empfehlungen aus 18 Bewertungsständen seit **22.09.2026**. Kaufannahme: frühestens der erste reguläre Börsenstart nach Bewertungsdatum und tatsächlichem Erstellungszeitpunkt. Bewertungsstichtag ist der letzte abgeschlossene US-Handelstag **14.10.2026**.

48 Empfehlungen hatten bis dahin einen ausführbaren Einstieg. Sechs Empfehlungen bleiben offen, da ihre nächste mögliche Sitzung außerhalb des Stichtags liegt. Die Haltedauer zählt Handelssitzungen einschließlich des Einstiegstags.

| Haltedauer | Empfehlungen / Bewertungstage | Aktien brutto | Aktien nach Kosten | SPY brutto | Mehrertrag brutto |
|---|---:|---:|---:|---:|---:|
| 1 Sitzung | 48 / 16 | +0,09 % | -0,11 % | -0,05 % | +0,14 Prozentpunkte |
| 5 Sitzungen | 36 / 12 | +0,99 % | +0,79 % | +0,32 % | +0,68 Prozentpunkte |
| 10 Sitzungen | 21 / 7 | +5,43 % | +5,22 % | +1,17 % | +4,26 Prozentpunkte |
| 20 Sitzungen | 0 | Noch offen | Noch offen | – | – |
| 63 Sitzungen | 0 | Noch offen | Noch offen | – | – |

Kosten: 10 Basispunkte je Kauf und Verkauf. SPY ist in dieser Tabelle als Bruttovergleich bezeichnet; der Mehrertrag vergleicht ebenfalls Bruttorenditen.

**Einordnung:** Nach einer Sitzung ist der durchschnittliche Gewinn kleiner als die modellierten Handelskosten. Nach fünf und zehn Sitzungen sind die verfügbaren Mittelwerte positiv. Für zehn Sitzungen stehen aber nur sieben Bewertungstage zur Verfügung; wiederkehrende Aktien und überlappende Zeiträume sind abhängig. Das reicht nicht für einen belastbaren Nachweis einer langfristig erfolgreichen Aktienauswahl. Für längere Haltedauern fehlen abgeschlossene Beobachtungen. Aktuelle Fundamentaldaten wurden nicht rückwirkend als damals bekannte Informationen verwendet.

[Einzelne Empfehlungen mit Erstellungs-, Einstiegs- und Messzeitpunkten](recommendation-events.csv)

## Alle acht Verkaufsstrategien: lange, identische Einstiege

40 Titel wurden vor der Ergebnisbetrachtung deterministisch aus dem heutigen Universum ausgewählt. 33 besitzen ausreichende Historie und abgeschlossene Vergleichsfenster. Es entstanden **472 Kohorten mit jeweils 126 Handelssitzungen**, erste Einstiege am **03.07.2017**, letztes abgeschlossenes Ende am **06.07.2026**. Einstiege liegen am ersten Handelstag im Januar und Juli, mit mindestens 200 vorherigen Kurskerzen. Neuere unvollständige 126-Sitzungs-Fenster werden nicht künstlich vervollständigt.

| Verkaufsstrategie | Mittlere Nettorendite | Median netto | Gewinnquote | Mittlerer maximaler Rückgang |
|---|---:|---:|---:|---:|
| Benutzerdefiniert: nur 7-%-Nothalt | +2,47 % | -7,45 % | 28,81 % | -17,75 % |
| Starker Rückgang vom 20-Tage-Hoch | +2,10 % | -3,41 % | 39,62 % | -11,59 % |
| 21-EMA-Bruch offensiv | +1,85 % | -3,41 % | 35,81 % | -11,91 % |
| Unterschreitung des Kauftags | +1,85 % | -6,28 % | 27,75 % | -16,54 % |
| Bruch gleitender Durchschnitte | +1,49 % | -0,71 % | 43,22 % | -6,95 % |
| 21-EMA-Bruch risikoavers | +1,10 % | -1,46 % | 38,35 % | -7,84 % |
| RS-Linie täglich mit 21/50-SMA | +0,91 % | -0,23 % | 45,55 % | -4,30 % |
| RS-Linie EMA | +0,64 % | -0,20 % | 47,03 % | -3,42 % |

Dieselben Aktien ohne vorzeitigen Ausstieg: im Mittel **+3,58 % netto** (+3,79 % brutto). SPY über dieselben Kohorten: **+7,28 % netto** (+7,49 % brutto). Alle Werte sind Ergebnisse pro 126-Sitzungs-Kohorte, keine Jahres- oder Gesamtdepotrenditen.

**Einordnung:** Keine der acht Verkaufsstrategien erhöht in dieser Stichprobe die mittlere Rendite gegenüber einfachem Halten derselben Aktien. Die RS-Varianten zeigen die geringsten durchschnittlichen Rückgänge der einzelnen Kohorten, geben dafür aber einen Teil der Rendite ab. Der benutzerdefinierte Baukasten entspricht im exportierten Setup ausschließlich dem universellen 7-%-Nothalt; er ist keine optimierte neue Strategie. Auf Basis dieser Untersuchung wurde keine produktive Strategie umgestellt.

## Verkaufsstrategien auf den echten Top-3-Einstiegen

Für **45 Einstiege in 21 Aktien** war mindestens eine Folgesitzung verfügbar. Drei weitere Einstiege vom 14.10.2026 besitzen noch keine Folgesitzung für einen Ausstiegsvergleich. Alle Kohorten enden am 14.10.2026; ihre Haltedauern unterscheiden sich. Deshalb dürfen diese Werte nicht mit den festen Haltedauern der Tabelle zur Aktienauswahl gleichgesetzt werden.

| Strategie | Mittlere Nettorendite bis Stichtag | Mittlerer maximaler Rückgang |
|---|---:|---:|
| RS-Linie EMA | -1,22 % | -6,80 % |
| 21-EMA-Bruch offensiv | -1,40 % | -7,17 % |
| RS-Linie täglich mit 21/50-SMA | -1,44 % | -7,09 % |
| Unterschreitung des Kauftags | -1,60 % | -7,39 % |
| Starker Rückgang vom 20-Tage-Hoch | -1,60 % | -7,30 % |
| Benutzerdefinierte Verkaufsstrategie | -1,65 % | -7,44 % |
| Bruch gleitender Durchschnitte | -1,65 % | -7,44 % |
| 21-EMA-Bruch risikoavers | -1,70 % | -7,37 % |

In diesem kurzen Ausschnitt begrenzen die Ausstiegsregeln die Verluste gegenüber Halten etwas. Die Stichprobe ist für einen allgemeinen Strategieentscheid zu kurz.

## Durchführung und Grenzen

- Insgesamt **517 Kohorten × 8 Strategien = 4.136 Strategieauswertungen**; keine wegen ungültiger Tagesmetriken verworfenen Signaltage.
- Produktionslogik einschließlich kumulativer Tranchen, Nothalt und Bestätigungsfolgen; Äquivalenz zur vollständigen Engine geprüft. Signale am Tagesschluss, Ausführung zum nächsten vorhandenen Börsenstart. Ein Kurssturz über Nacht kann den 7-%-Nothalt deutlich überschreiten.
- Verkaufserlöse bleiben als unverzinstes Cash liegen. Restbestände werden am gemeinsamen Ende bewertet und für den Kostenvergleich rechnerisch verkauft. Kostenvarianten: 0, 10 und 25 Basispunkte je Kauf/Verkauf; keine Mindestgebühren oder Marktbeeinflussung.
- Preisrenditen ohne Dividenden, Steuern oder Wechselkursänderungen. Die Kursdaten sind gespeicherte Vendor-Historien, keine unveränderlichen damaligen Tick-Daten.
- Die lange Zusatzstichprobe verwendet das **heutige Universum** und enthält Survivorship-Bias. Sie prüft Ausstiegsverhalten bei festen Einstiegen, nicht die historische Qualität der Aktienauswahl. Illiquide und stark schwankende Titel sind enthalten; 25 Basispunkte bilden nicht sämtliche realen Handelskosten ab.
- Zehn Tagesbewegungen von mehr als 75 % im Betrag wurden in der Stichprobenhistorie gesondert markiert. Sie wurden nicht nachträglich entfernt, um Ergebnisse zu verbessern. Ohne zusätzliche Einzelprüfung werden sie nicht pauschal als fehlerhafte Kurse oder als garantierte handelbare Gewinne behandelt.
- Mittelwerte, Mediane und Rückgänge beziehen sich auf einzelne Kohorten. Überlappende Kohorten ergeben kein umsetzbares Gesamtportfolio und sind keine unabhängigen Zufallsbeobachtungen. Es wurde nichts annualisiert oder auf die Ergebnisse hin optimiert.

[Methodik und Reproduktion](../../stock-backtests.md) · [Zusammenfassung aller Strategien](sell-summary.csv) · [Alle Kohorten](sell-cohorts.csv) · [Markierte extreme Kursbewegungen](extreme-price-moves.csv)

## Prüfbarkeit

Input-SHA-256: `6cd9c2d1a449414c72df0296b6e8af02b49d1f12ed5daf294adb6504dc2922c5`. Der unveränderte Input, alle simulierten Teilverkäufe und die vollständigen SEC-Aggregate werden zusätzlich auf dem NAS im geschützten Release-Verzeichnis aufbewahrt. Der Codeexport enthält keine Depotbestände oder Zugangsdaten.

Die vollständige GitHub-CI der ersten Implementierung war erfolgreich. Zusätzliche Prüfungen decken abgekürzte Haupt-CUSIPs und die SEC-Fristverschiebung an Wochenenden und US-Bundesfeiertagen ab. Ein eigener Test verändert zukünftige Kerzen stark und prüft, dass frühere Verkaufsergebnisse unverändert bleiben.
