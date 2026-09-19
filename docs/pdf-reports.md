# Investment- und Trade-PDFs

## Architektur und Auswahl

Next.js stellt den Download-Button auf `/stocks/[ticker]` und beim gespeicherten Eintrag im
Handelstagebuch bereit. Der bestehende authentifizierte API-Proxy reicht Binärantworten durch.
FastAPI erzeugt das PDF mit ReportLab 4.4.10. Gegenüber Browser-Print, Screenshots oder einem
zusätzlichen Chromium-Container ermöglicht das A4-Vektorgrafiken, eingebettete Schriftarten,
kontrollierte Seitenumbrüche und wiederholte Tabellenköpfe mit geringem NAS-Ressourcenbedarf.

`GET /api/v1/stocks/{ticker}/report.pdf` exportiert die Aktie. Mit `?trade_id=<id>` wird ein
historischer Trade samt explizit verknüpftem Einstieg, Verkauf und Nachbetrachtungen exportiert.
Der Ticker muss zum Trade passen. Reports werden nicht gespeichert oder gecacht.

## Datenvertrag

`InvestmentReport` trennt Erfassung (`reports/collect.py`) von Darstellung (`reports/pdf.py`).
Es enthält Identität, Währung, Exportzeit, Bewertung, Kursreihe, benannte Datenabschnitte,
Tagebucheinträge und Hinweise auf fehlende Quellen. Es findet kein Kursrefresh statt.

- Stammdaten: Instrument (Name, Ticker, ISIN, Währung). Das Projekt hat kein eigenes WKN-Feld.
- Bewertung: bestehende StockAssessment-Regeln; alle Checks in den vorhandenen Kategorien
  Fundamental, Technisch, Trend und Risiko, Scores, Messwerte, Erläuterungen, Warnungen,
  Chartsignale, Earnings und Datenqualität. Fehlende Bewertungen erhalten keinen Ersatzscore.
- Fundamentals, RS und institutionelle 13F-Daten inklusive vorhandener Detailfelder und Historien.
- Position: gespeicherter Kauf, Stückzahl, Stop und Notiz; Wert, P&L und Abstand zum Stop
  ausschließlich aus vorhandenen Kursen. Bei verschiedenen Währungen werden nur aktuelle
  gespeicherte FX-Kurse verwendet. Ohne belastbaren Kurs fehlen abgeleitete Werte ausdrücklich.
- Kaufstärke: bestehende Regeln im Standardfenster, mit Kaufpreis in der Währung der Kursreihe.
- Verkauf: volle SellEvaluation samt Kriterien, Signalen, Gewichtungs-/Beitragsfeldern,
  manuellen Eingaben und Tranchen. `preview_position_sell_decision` persistiert keinen Zustand.
- Markt: letzter gespeicherter MarketSnapshot. Kein Live-Marktdatenabruf.
- Journal: sämtliche Einträge der Aktie, bei Trade-Export nur die verknüpfte Trade-Gruppe.
  Notizen, Fragebogen, historische Aktien-, Markt- und Positions-Snapshots und lokale Chartbilder.
  Es gibt keine eigene lückenlose Änderungshistorie und kein dediziertes Kursziel-Feld;
  vorhandene Ziele in Notizen/Fragebögen werden unverändert übernommen.

Historische Reports verwenden niemals heutige Scores als damalige Bewertung. Nur die
Unternehmensstammdaten sind aktuell. Exportzeit und jeweiliger Datenstand sind getrennt.

## Layout, Sicherheit, Fehler

A4 mit festen Rändern, Dashboard-Farben, eingebetteter Vera-Schrift, Vektor-Kurschart und
Score-Balken. Tabellen wiederholen ihre Kopfzeile, lange Texte fließen über Seiten hinweg.
Header und Footer inklusive Seitenzahl erscheinen auf jeder Seite. Gleiche Reportdaten mit
gleicher Exportzeit erzeugen identische PDF-Bytes. Keine Browser-Navigation oder Zoom-Abhängigkeit.

Freitexte werden XML-escaped. Nur begrenzte eingebettete PNG/JPEG/WebP-Bilder werden gelesen;
externe URLs und Dateipfade werden nicht geladen. Fehlerhafte Bilder werden als Hinweis dargestellt.
Unbekannte Aktie/Trade: 404; ungültiger Ticker: 422; Datenbankausfall: 503; Renderfehler: 500.
Optionale Quellenfehler erscheinen im Report; interne Fehlerdetails bleiben in Serverlogs.
Der Button verhindert Mehrfachklicks, zeigt Lade-/Fehlerzustände und erlaubt einen erneuten Versuch.

## Prüfung und Deployment

`pytest tests/services/test_investment_report.py` prüft A4, lange Kriterien/Notizen, Seitenzahlen,
Determinismus, fehlende Scores, Literaltext, Währungen, historische Isolation, Download-Header
und Fehler. Zusätzlich vollständige Backend-Suite, Ruff, Frontend-Typecheck, ESLint und Build.
Visuelle QA: Test-PDFs mit Poppler rendern und sämtliche Seiten prüfen.

Die Backend-Abhängigkeit wird im vorhandenen Docker-Build installiert. Keine Migration nötig.
Nach Veröffentlichung beider Images das NAS über `infra/update-nas.sh` aktualisieren.
