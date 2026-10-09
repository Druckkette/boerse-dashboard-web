# Private Dashboard-Startseite

Die Startseite trennt Marktlage, Depotentscheidungen, Earnings und Tagesveränderungen. Eine Aktie kann in mehreren passenden Bereichen erscheinen. Recherche und Watchlist bleiben erhalten; Daten und Meldungen sind standardmäßig eingeklappt. Die Beta-Startseite und ihre öffentliche Projektion enthalten keine persönlichen Daten.

## Depot

Das Backend ordnet gespeicherte Verkaufsbewertungen ein:

- **Handlungsbedarf:** `Verkaufen`, `pending_status=scharf`, positive Tranche, vertrauenswürdige Daten und aktuelle Bewertung. Nur hier wird eine Verkaufstranche angezeigt.
- **Beobachten:** offene Bestätigung oder zurückgestelltes Signal, sonstige Beobachtungsbewertung sowie fehlender Stop.
- **Daten prüfen:** eingeschränkte Datenqualität, fehlende Bewertung, fehlender/ungültiger Erzeugungszeitpunkt oder ein Bewertungsstand vor dem letzten abgeschlossenen US-Handelstag. Ein neuer Snapshot einer anderen Aktie macht eine alte Bewertung nicht aktuell.

Gespeichertes Signal, Bewertungsdatum und Erzeugungszeitpunkt bleiben sichtbar. Depotzugehörigkeit wird gegen aktuelle offene Positionen geprüft. Die eigentliche Verkaufsentscheidung und ihre Bestätigungsregeln werden nicht verändert. Tagesergebnis und Kennzahlen verwenden weiterhin den vorhandenen Portfolio-Snapshot. Ein Gewicht über 25 % wird als eigener Dashboard-Hinweis zum Positionsrisiko angezeigt, ohne daraus eine Verkaufsempfehlung abzuleiten. Die Stärke nach Kauf ist aufklappbar.

## Earnings

Ein gemeinsamer Datenbankabruf liefert die nächsten 30 Kalendertage einschließlich heute, bezogen auf Europe/Berlin. Die Anzeige startet mit 14 Tagen und Depotpositionen; Watchlist und 30 Tage lassen sich zuschalten. Datum, Wochentag, verbleibende Tage, Unternehmen, Quelle und Datenstand werden angezeigt. BMO/AMC beziehen sich auf den US-Handel. Fehlende Uhrzeiten und unbestätigte Zeitzonen werden ausdrücklich bezeichnet.

Bei widersprüchlichen Anbietern bleibt die vorhandene Quellenpriorität maßgeblich. Pro Aktie erscheint der nächstgelegene Termin des bevorzugten Anbieters innerhalb des Fensters; abweichende Daten werden markiert. Kalenderangaben werden nicht als vom Unternehmen bestätigte Veröffentlichung ausgegeben. Fehlende gespeicherte Termine bedeuten keine Entwarnung.

## Veränderungen und Historie

Die vorhandene Tabelle `daily_stock_opportunities` speichert zusätzlich sämtliche bewertbaren Depot- und Watchlist-Aktien, auch unterhalb der Qualitätsgrenze. Der reguläre vollständige Bewertungsprozess berücksichtigt diese Aktien auch außerhalb des Rechercheuniversums. Auswahlkriterien und Rangfolge der Tagesauswahl bleiben erhalten.

Verglichen werden tatsächliche, aufeinanderfolgende US-Börsentage. Relevante Änderungen sind:

- mindestens fünf Punkte beim Gesamtscore oder RS-Rating;
- Übergang über/unter Score 75 oder RS 80;
- neue oder entfallene technische/Trend- und positive Chartsignale;
- erstmaliges Erfüllen oder Verlust der bestehenden, konfigurierten Tagesauswahl-Kriterien.

Letzteres ist ein Recherchehinweis für beobachtete Aktien, keine zusätzliche Kaufempfehlung. Die Fünf-Punkte-Grenze ist zentral im Backend definiert (`HOME_CHANGE_THRESHOLD`). Neue historische Metadaten tragen `history_version=2`. Ältere Vergleichsstände werden anhand gespeicherter Werte gelesen; nicht verfügbare frühere Zustände schwacher Aktien werden nicht erfunden. Neue vollständige Vergleichspaare entstehen im täglichen Aktualisierungsprozess.

Fehlende Kurse, eingeschränkte Bewertungen, nicht abgeschlossene Tageskerzen und Lücken im vorangegangenen Handelstag erzeugen keine scheinbaren Verschlechterungen. Die Anzeige nutzt den letzten gespeicherten abgeschlossenen Tag, zeigt beide Vergleichsdaten und erlaubt Filter nach Depot, Watchlist und Marktchancen. Es gibt keine versteckte Begrenzung auf 8/20 Hinweise oder 400 Kandidaten; zunächst fünf Einträge sind aufklappbar.

## Datenzugriff und Kompatibilität

GET `/api/v1/home` arbeitet ausschließlich mit gespeicherten Daten und dem bestehenden 30-Sekunden-Cache. Watchlist-Bewertungen werden für alle gespeicherten Werte gesammelt geladen. Diagnose- und Meldungsabrufe beginnen erst beim Öffnen des entsprechenden Bereichs. Ampelveränderungen stammen aus denselben zentral berechneten, bestätigten Tagesphasen wie die Marktansicht.

Der private Antwortvertrag trägt `schema_version=2` und separate `portfolio_alerts`, `earnings` sowie `changes`. Die bisherigen Felder `priorities`/`priorities_total` bleiben als kompatible Aliasfelder für reine Depotwarnungen erhalten; sie mischen keine Earnings oder Veränderungen mehr. Eine Datenbankmigration ist nicht erforderlich. Bestehende Snapshots bleiben lesbar. Marktampelregeln und Powertrend werden nicht geändert.

Einzelne nicht verfügbare Quellen werden in `errors` zurückgegeben und lassen die übrigen Bereiche weiter rendern. Die operative Workspace-Seite bleibt unter `/workspace` erhalten.
