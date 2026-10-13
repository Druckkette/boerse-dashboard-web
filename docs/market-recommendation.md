# Marktphasen-Empfehlung

Seit 13.10.2026 bestimmt ausschließlich die bestätigte Trendampel des ausgewählten Index die Marktphase und ihre Handlung. Die fünf ergänzenden [Kontext-Kennzahlen](market-context-scores.md) sind informativ.

- Rot: defensiv, auch bei konstruktiven Kontext-Kennzahlen.
- Trend oder Rally unter Druck: keine aggressiven Neueinstiege; Powertrend überschreibt die Phase nicht.
- Startschuss: kleine Pilotpositionen; neutral: abwarten.
- Grün: frühe Bestätigung, vorsichtig aufbauen.
- Aufwärtstrend: vollständig bestätigter Trend, Qualitäts-Setups aufbauen und Gewinner mit individuellen Stops führen.

Warnzahl, Equal Weight, Powertrend und Volatilität dürfen keine dieser Haltungen überschreiben. Auch A20 (vier Indexwarnungen an zwei Tagen) schaltet die Ampel nicht mehr auf Trenddruck. Bestätigte Preis- und Strukturregeln sowie die ausdrücklich beibehaltenen harten Rot-Regeln bleiben bestehen. Die Regelversion ist `trend_ampel_v5`. Individuelle Verkaufssignale und Stops gelten weiterhin.

Die Hauptkarte verwendet Phase, Farbe und Handlung direkt aus `phase_info`; Detail und Übersicht verwenden denselben Phasenbezug. Alte gespeicherte Empfehlungstexte werden beim Lesen neu berechnet. Die bestehenden Detailblöcke bleiben erhalten. Die neuen Informationsscores werden über einen unabhängigen, lesenden Endpunkt geladen: `/market/context-scores?ticker=...&as_of=...`. Ausfall und Laden dieser Scores beeinträchtigen die Ampelanzeige nicht.
