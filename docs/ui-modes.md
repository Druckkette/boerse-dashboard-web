# Neue und klassische Oberfläche

Die neue Oberfläche ist die Standardansicht. Oben steht jederzeit **Klassische Ansicht**. Damit wird die bisherige Navigation und Anordnung wieder angezeigt. **Neue Ansicht** schaltet zurück. Die Wahl gilt für den jeweiligen Browser, wird ein Jahr im Cookie `dashboard-ui` gespeichert und schon beim Serverrendern berücksichtigt. Bei offenen Stopp-, Einstellungs- oder Notizentwürfen ist der Wechsel gesperrt; zuerst speichern oder verwerfen.

Der Ansichtswechsel verwendet keine Finanz-API-Schreibzugriffe und ändert weder Depot, TR-Buchungen, Tageskurse, Berechnungsmodelle noch Notizen. Es gibt keine Datenmigration für das neue Design. Ein vorhandener Verlauf oder eine fehlende Bewertung wird in beiden Ansichten aus denselben Backenddaten angezeigt.

## Änderungen

- Mobile Navigation mit fünf Zielen und einem zugänglichen Menü für weitere Bereiche; private und Beta-Navigation bleiben getrennt. Kompakter Header, feste Navigation mit Abstand zum Seitenende und Berücksichtigung des sicheren Bildschirmbereichs.
- Startseite mit offenen Prüfpunkten, kompakten Indizes, Depot und Earnings. Indexdetails bleiben aufklappbar. Powertrend und Marktphase werden getrennt dargestellt; fehlende oder alte Ampeln erhalten keine aktuelle Statusbehauptung.
- Depot: Wert, Tagesergebnis und Stop-Abdeckung zuerst, danach Kurve und Positionen. Weitere Kennzahlen, Analyse und Verwaltung bleiben erreichbar. Mobile Positionskarten zeigen Kernwerte; zusätzliche Angaben sind aufklappbar. Mobile Sortierung und separate Desktop-Spaltenauswahl bleiben im Browser gespeichert.
- Stoppbearbeitung mit größerem Feld, Währungsangabe und ausdrücklichem Speichern. Ungültige oder leere Eingaben entfernen keinen Stopp. Die klassische Ansicht behält das bisherige Speichern beim Verlassen des Felds. Fehlgeschlagene Speicherungen behalten den Eingabewert. Eine neue Kurs-Snapshot-Antwort erhält einen offenen Stoppentwurf ebenfalls.
- Kurve mit aufklappbaren Darstellungsoptionen, Bewertungsabdeckung, tatsächlichen Lückenzeiträumen und den vom Backend gemeldeten betroffenen Instrumenten. Fehlende Werte bleiben fehlend. Keine Kursinterpolation und keine Änderung der automatischen Berliner Jahresumstellung.
- Charts erlauben normales vertikales Scrollen. Ablesen/Verschieben ist ausdrücklich aktivierbar; Zoom und Zurücksetzen bleiben verfügbar. Mausrad-Zoom in der neuen Ansicht benötigt den aktiven Interaktionsmodus oder Strg/Cmd.
- Aktienanalyse: Unternehmen, Kurs- und Quelldatum, Beurteilung und Gründe vor den ausführlichen Kriterien. Kennzahlen und Gewichte sind aufklappbar; der Chart steht in der Übersicht. PDF und Arbeitsbereich sind über weitere Aktionen erreichbar. Auf kleinen Bildschirmen ersetzt eine native Bereichsauswahl die breite Tab-Leiste. Die Bewertung selbst bleibt unverändert.
- Journal: kompakter Einstieg, Suche und Filteranzahl. Filter werden in einer eigenen Dialogansicht gesammelt angewendet. Ausführung, damalige Bewertung und Notizen bleiben getrennt. Die Notizbearbeitung ersetzt in der neuen Ansicht den Detailinhalt; es entsteht keine zweite modale Ebene. Speichern mit Fehler behält den Entwurf. Filter und Liste bleiben beim Schließen erhalten.
- Einstellungen: native mobile Bereichsauswahl und Speicherleiste nur bei Bedarf; Fehler lassen Entwürfe bestehen. Deutsche Darstellung der dokumentierten Backend-KPI-Zahlen. Verlustbeträge sind als Ergebnisrichtung gekennzeichnet, Positionszahlen neutral. Der Header benennt den Daten-/Systemstatus ausdrücklich.
- Einheitliche Mindestgröße für Schaltflächen, 16-px-Eingaben auf kleinen Bildschirmen, sichtbare Tastaturfokusse und reduzierte Animation bei entsprechender Systempräferenz. Ladezustände reservieren Fläche, vorhandene Daten bleiben bei einer fehlgeschlagenen Aktualisierung sichtbar.

## Vollständige Veröffentlichung zurücksetzen

Basis vor dieser Umstellung: `f3ce8f81d67eaa49cb2605039ed7ed5013c34653`.

Die zugehörigen unveränderlichen Backend- und Frontend-Images bleiben verfügbar. Auf dem NAS kann zusätzlich zur sofortigen Browser-Umschaltung die vollständige vorige Image-Version wieder gestartet werden:

```sh
cd /volume1/docker/boerse-dashboard-web
./infra/rollback-ui-release.sh --check
./infra/rollback-ui-release.sh
```

`--check` prüft Konfiguration, lokale Basisimages, unveränderte Backendkompatibilität und einen sauberen Checkout. Der eigentliche Rücksprung sichert die aktuelle Umgebungsdatei geschützt, ändert ausschließlich `IMAGE_TAG`, lädt die Basisimages und startet die acht Anwendungsdienste ohne ihre Abhängigkeiten neu. PostgreSQL, Redis, Volumes und aktuelle Finanzdaten werden nicht zurückgesetzt. Es werden keine Migrationen oder Journal-Neuberechnungen gestartet. Der Git-Checkout bleibt auf dem neuen Commit; ein späteres reguläres Deployment muss wieder den gewünschten Image-Tag setzen. Das Skript verweigert die Wiederverwendung nach Backendänderungen gegenüber der Basis.

Die NAS-Sicherung des Ausgangszustands und die Vorher-/Nachher-Fingerabdrücke liegen im geschützten Sicherungsverzeichnis `ui-redesign-20261018` unter der bestehenden Dashboard-Sicherung. Darin stehen keine öffentlichen Artefakte.

## Prüfumfang

Automatisierte Tests prüfen beide Ansichten, Speicherung der Browserwahl, das Ausbleiben finanzieller Schreibzugriffe beim Wechsel, private/Beta-Grenzen, Stoppvalidierung, Fehlerentwürfe, Journalfilter/-bearbeitung, Import, Kurvenlücken und Jahreswechsel. Mobile Prüfungen verwenden Chromium und WebKit. Browseremulation ersetzt keine Prüfung auf physischen iPhones/Androidgeräten oder einen Nutzertest; diese werden nicht als durchgeführt behauptet.

## Vereinfachte Analyseansicht (18. Oktober 2026)

Die zusätzliche Charttabelle und der allgemeine Block „Datenherkunft und Berechnungsgrundlage“ entfallen. Kursdatum, konkrete Datenlücken, Bewertungsabdeckung und veraltete Daten bleiben bei den betroffenen Kennzahlen sichtbar.

„Scoreverlauf und Ursachen“ wird nicht mehr angezeigt: Die zugrunde liegenden `daily_stock_opportunities` enthalten eine Auswahl von Kandidaten und verfolgten Aktien, kein verlässliches Archiv sämtlicher aufgerufener Aktien. Bei der Prüfung am 18. Oktober endete die TSLA-Historie am 15. Oktober; ältere Gesamtscores hatten keine Einzelkriterien. Der aktuelle Snapshot zum 16. Oktober lag mit Score 44 unter der Auswahlschwelle 50; TSLA gehörte weder zu den offenen Depotpositionen noch zur Watchlist. Einzelne spätere Detailaktualisierungen erzeugen ebenfalls keinen täglichen Archivstand. Aus heutigen Daten nachgerechnete frühere Scores wären kein Beleg für die damalige Bewertung. Die vorhandenen historischen Datensätze und Diagnose-Endpunkte bleiben erhalten; die Oberfläche ruft die beiden zusätzlichen Endpunkte nicht mehr ab. Der Vergleich der Chartsignale zum vorherigen Handelstag bleibt sichtbar.
