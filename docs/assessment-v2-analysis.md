# Assessment v2 – Bestandsaufnahme vor der Implementierung

## Wiederverwendete Berechnungen

- `evaluate_technicals()` liefert weiterhin Preis-/Liquiditäts-Eligibility, ATH-/52W-High,
  Up/Down-Volumen, CMF sowie die bestehenden verständlichen Checks.
- `_fundamental_checklist_score_100()` und die EPS-, Umsatz- und ROE-Teilfunktionen
  bleiben der unveränderte Fundamental Core. Die Foreign-Private-Issuer-Sonderlogik
  bleibt erhalten.
- Die Ereigniserkennung in `evaluate_chart_signs()` bleibt die Grundlage des Price
  Action Core. Das gilt insbesondere für Gaps, volumenbestätigte Tage, Reversals,
  Outside/Engulfing Days, Shakeouts, Closing Position und Unterstützungswochen.
- `_recent_reaction_signals()`, `_support_week_signal()`,
  `_moving_average_distance_warnings()` und `_moving_average_distance_details()`
  bleiben die Quellen für Kontext-/Setup-Texte.
- Die vorhandene RS-Line-Historie wird für K4-Persistenz und White Space verwendet;
  die Universe-RS-Berechnung wird um methodisch identische 3M-/6M-/12M-Ränge für K13
  erweitert.

## Bisher numerisch wirksame Signale

- Technical: Preis, Dollarvolumen, ATH, 52W-Hoch, Up/Down-Volumen, RS Rating,
  RS >21/50, RS-Trends 5W/13W, RS-Hoch und CMF.
- Fundamental: EPS/Umsatz (Quartal und Jahr), Beschleunigung, positives TTM-EPS,
  ROE und Marge. Institutionelle Unterstützung wird angezeigt, ist aber nicht Teil
  des bisherigen 9-Einheiten-Scores.
- Moving Average: aktuelle Position über 10/21/50/200 und MA-Ordnung.
- Chart: Anzahl aller positiven und negativen Chart-Signale. Dadurch wirken bisher
  auch MA-, RS- und Overextension-Signale indirekt numerisch.
- Overall: bislang ungewichteter Mittelwert der vier Hauptscores (25/25/25/25).

## Bisher nur als Text oder neutral

- Inside Day, enge Konsolidierung, Tests von 21 EMA/50 SMA, Natural Reaction und
  2,5-Tage-Korrektur sind neutrale Textsignale.
- Negative Signalzustände dienen zusätzlich der Alert-Auflösung.
- Earnings und MA-Abstände beeinflussen Verdict/Warnungen, aber keinen eigenen
  sauber abgegrenzten Hauptscore.

## Erkannte Doppelzählungen und neue Zuordnung

- MA-Persistenz, MA-Ordnung und MA-Richtung werden aus der Chart-Zählung entfernt
  und ausschließlich im Moving-Average-Score bewertet.
- RS-Position, RS-Trend, RS-Hoch und RS-Rating werden aus der Chart-Zählung entfernt
  und ausschließlich K4, K13 beziehungsweise dem RS-Rating-Block zugeordnet.
- Preis und Dollarvolumen werden aus Technical entfernt und bleiben ausschließlich
  Eligibility-Regeln.
- MA-Abstände werden ausschließlich Setup/Overextension; Natural Reaction und
  MA-Tests bleiben neutraler Kontext.
- Aggregiertes Up/Down-Volumen und CMF bleiben Technical. Einzelne konkrete
  Kurs-/Volumenereignisse bleiben Chart.

## Erhaltene Textinformationen

Alle bisherigen RS-, MA-, Chart-, Setup-, Eligibility-, Driver- und Warning-Texte
bleiben im Assessment erhalten. Signale tragen künftig getrennte Angaben für
`score_relevant` und `display_relevant`; eine numerische Verschiebung entfernt daher
keine Erklärung aus API, Stock Detail oder PDF.
