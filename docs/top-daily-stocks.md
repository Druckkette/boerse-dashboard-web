# Top 3 Aktien des Tages

Research-Shortlist, keine automatische Kaufentscheidung. Die Seite `/stocks` liest
`GET /api/v1/stocks/top-daily`; dieser GET-Endpunkt startet weder Providerabrufe
noch Bewertungsjobs.

## Ranking und Filter

Die bestehende Aktienbewertung bleibt die Qualitätsbasis. Der Daily Opportunity
Score ist standardmäßig `0,65 × overall_score + 0,35 × daily_dynamics_score`.
Die Dynamik hat einen neutralen Mittelpunkt von 50 und sechs Komponenten:

| Komponente | Gewicht | Berechnung |
| --- | ---: | --- |
| Veränderung Gesamtscore | 25 % | `clamp(50 + 8 × Delta)` |
| Veränderung Technik | 15 % | `clamp(50 + 5 × Delta)` |
| Veränderung konfiguriertes RS-Rating | 20 % | `clamp(50 + 6 × Delta)` |
| Relative Performance gegen SPY | 15 % | `clamp(50 + 5 × 1T + 3 × 5T)` |
| Volumenbestätigung | 10 % | 50 plus/minus maximal 60, je nach Volumenratio und positivem/negativem Kurstag |
| Neue bzw. verlorene positive Signale | 15 % | `clamp(50 + 12 × neu − 12 × verloren)` |

`clamp` begrenzt auf 0–100. Fehlende Vergleichsdaten liefern **keine erfundene
Verbesserung**: die betreffende Komponente bleibt bei 50. Ein bestehendes Signal
gibt keinen erneuten Neu-Signal-Bonus. Negative Veränderungen senken die Dynamik.
Gleichstände werden nach Opportunity Score, Overall Score und Ticker aufgelöst;
es gibt keine Rotationsregel.

Der Kandidat muss zum erwarteten US-Handelstag einen frisch nach Marktbeginn
bzw. Marktschluss abgerufenen Schlusskurs besitzen. Standardfilter:
Overall Score ≥70, RS ≥80, Fundamental- und Trend-Score je ≥50, Kurs ≥$15,
20-Tage-Dollarvolumen ≥$30 Mio., Fundamentals und RS-Linie vorhanden.
Die Schwellen sowie die 65/35-Gewichtung sind zentral in `app.core_config.Settings`
als `DAILY_*`-Umgebungsvariablen konfigurierbar. Die sechs
Dynamik-Gewichte stehen zentral in `app.services.daily_opportunities`.

## Quellen, Historie und Aktualisierung

Die vorhandenen `stock_assessment_snapshots` liefern Scores, primäres konfiguriertes
RS-Rating (bei aktiver CSV/Fred-Quelle dieses Rating), Signal-Checks, Kurs,
Liquidität und Earnings. Nur für vorselektierte Kandidaten werden maximal 14
Kalendertage gespeicherter Kurszeilen sowie SPY aus `price_bars` gelesen.
Volumenratio und Chart-Signale werden vom normalen Assessment-Lauf übernommen.
Ein Providerabruf oder ein vollständiger Preis-Load findet nicht statt.

Migration `0019_daily_stock_opportunities` legt eine kompakte Tag/Ticker-Tabelle
an. Gespeichert werden Score-Kennzahlen, RS, aktive Signalnamen, Dynamik,
Opportunity Score, Rang und kurze Erläuterungen. Um Platz zu sparen, werden nur
Aktien ab 20 Punkten unter dem konfigurierten Qualitätsminimum historisiert.
Vortagsvergleich verwendet den letzten **gespeicherten** früheren Handelstag;
vor dem ersten Vergleich sind Deltas und Vortagsrang `null`.

Die Tabelle wird nach dem regulären vollständigen Aktienbewertungs-Lauf
aktualisiert. Eine erneute Berechnung am selben Tag ersetzt nur diesen Handelstag
transaktional; ältere Tage bleiben erhalten. Die Web-App liest ausschließlich
vorbereitete Zeilen. Wenn die Top-3-Nachbereitung scheitert, bleiben Markt- und
Assessment-Snapshots benutzbar; der Job meldet das Teilergebnis.

## NAS-Deployment und Smoke-Test

Der bestehende Pfad `infra/update-nas.sh` zieht versionierte GHCR-Images, führt
Alembic aus und aktualisiert Backend, Frontend, Worker und Scheduler. PostgreSQL-
und Redis-Volumes sowie `.env.nas` bleiben erhalten. Auf dem NAS ist die
Migration vor einem ersten API-Aufruf erforderlich. Für einen sofortigen Start
ohne vollen Marktdatenlauf kann einmalig im Backend-Container
`python -c 'from app.services.daily_opportunities import refresh_top_daily; print(refresh_top_daily())'`
ausgeführt werden. Ohne ältere Tageshistorie zeigt die UI den fehlenden
Vortagsvergleich ausdrücklich an.

Produktiver Smoke-Test und tatsächliche Aktivierung werden nach Deployment
bestätigt; bis dahin ist diese Dokumentation keine Freigabebestätigung.
