/** Investor-facing names and notes, aligned with domain/stocks/assessment.py. */
export const assessmentCriteria: Record<
  string,
  { label: string; note?: string }
> = {
  k4_rs_leadership: {
    label: "Relative Stärke: Führungsqualität (K4)",
    note: "Teile: RS-Linie über 21-Tage-EMA (25 %), über 50-Tage-SMA (15 %), Beständigkeit über 63 Handelstage (20 %), Nähe zum 52-Wochen-Hoch der RS-Linie (30 %) und stabiler Abstand zu den Durchschnitten (10 %). Die Beständigkeit verbindet 21-EMA/50-SMA mit 60/40; der stabile Abstand verbindet aktuellen Abstand (35 %) und Stabilität über 20 Handelstage (65 %). Gemeint ist die RS-Linie gegenüber dem Vergleichsindex, nicht der Aktienkurs.",
  },
  k13_rs_dynamics: {
    label: "Relative Stärke: Verbesserung und Beschleunigung (K13)",
    note: "Teile: Unterschied der RS-Ratings über 3 und 6 Monate (35 %), über 6 und 12 Monate (25 %), Reihenfolge der 3-/6-/12-Monats-Ratings (25 %) und Beschleunigung (15 %). Die Beschleunigung verbindet die beiden Rating-Unterschiede mit 60/40.",
  },
  k9_eps_sales_alignment: {
    label: "Gewinn- und Umsatzwachstum im Einklang (K9)",
    note: "Vergleicht das Wachstum von Gewinn je Aktie (EPS) und Umsatz gegenüber dem Vorjahresquartal für dieselben Berichtsquartale. Die bis zu drei jüngsten passenden Quartale zählen mit 50/30/20; mindestens zwei sind erforderlich. Wiederholt steigender Gewinn bei sinkendem Umsatz begrenzt den Score und löst einen Recherchehinweis aus.",
  },
  k35_down_week_quality: {
    label: "Verkaufsdruck in Verlustwochen (K35)",
    note: "Teile: Schlusskursposition innerhalb der Wochenkursspanne und Wochenverlust. Bewertet die bis zu drei jüngsten Verlustwochen innerhalb von 13 abgeschlossenen Wochen mit 50/30/20. Ein Schluss nahe dem Wochenhoch ist positiv; mindestens 4 % Verlust bei Schluss im unteren Viertel ergibt 0 Punkte. Ohne Verlustwoche bleibt das Kriterium neutral.",
  },
  k38_hh_hl_good_close: {
    label: "Höhere Wochenhochs und -tiefs mit starkem Schluss (K38)",
    note: "Teile: Wochenhoch und -tief gegenüber der Vorwoche, Wochenrendite und Schlusskursposition in der Wochenkursspanne. Der Score bewertet die jüngste abgeschlossene Woche: höhere Hochs und Tiefs mit mindestens 2 % Plus und Schluss im oberen Viertel ergeben 90 Punkte; ab 4 % Plus und Schluss in den oberen 10 % sind es 100. Fehlen höhere Hochs oder Tiefs, bleibt der Score neutral. Die 8-Wochen-Zählung ist Kontext, kein zusätzlich gewichteter Teil.",
  },
  rs_rating: { label: "Relative Stärke im Aktienvergleich (RS-Rating)" },
  high_position: {
    label: "Nähe zu Allzeithoch und 52-Wochen-Hoch",
    note: "Teile: Entfernung zum Allzeithoch (zwei Drittel) und zum 52-Wochen-Hoch (ein Drittel); fehlt nur ein Hochwert, liefert dessen Anteil keine Punkte.",
  },
  up_down_volume: { label: "Volumen an Gewinn- und Verlusttagen" },
  cmf: { label: "Kauf- und Verkaufsdruck (Chaikin Money Flow)" },
  fundamental_core: {
    label: "Gewinn, Umsatz und Profitabilität",
    note: "Teile: EPS-Wachstum über drei Quartale und drei Jahre, EPS-Beschleunigung, positives EPS der letzten vier Quartale, Umsatzwachstum über drei Quartale und drei Jahre, Umsatz-Beschleunigung, Eigenkapitalrendite und Gewinnmarge. Bei ausländischen Emittenten mit Jahresberichten zählen Jahres-EPS, Jahresumsatz, Eigenkapitalrendite und Gewinnmarge jeweils zu 25 %.",
  },
  price_action_core: {
    label: "Kurs- und Volumenverhalten",
    note: "Verbindet die positiven und negativen, scorewirksamen Chartsignale: Volumenverteilung, Lage/Ordnung/Richtung der Durchschnitte, Kurslücken, Rückgänge und Anstiege, Stau-Tage, Umkehrtage, Outside Days, Engulfing-Kerzen, Unterstützungswochen, Schlusskursposition, Abstand zu Durchschnitten, fünf positive Wochen in Folge und RS-Linien-Signale. Die konkrete Signalliste steht im Chartverhalten; Kontextsignale ohne Score-Relevanz werden nicht mitgezählt.",
  },
  price_above_200_sma: { label: "Kurs über 200-Tage-Durchschnitt (SMA)" },
  price_above_50_sma: { label: "Kurs über 50-Tage-Durchschnitt (SMA)" },
  price_above_21_ema: { label: "Kurs über 21-Tage-Durchschnitt (EMA)" },
  price_above_10_sma: { label: "Kurs über 10-Tage-Durchschnitt (SMA)" },
  ma_order: {
    label: "Durchschnitte in Aufwärtstrend-Reihenfolge",
    note: "Prüft: 21-Tage-EMA über 50-Tage-SMA über 200-Tage-SMA.",
  },
  persistence: {
    label: "Beständigkeit über den Durchschnitten",
    note: "Teile: Dauer der aktuellen Kursserie über/unter 21-Tage-EMA (40 %) und 50-Tage-SMA (60 %).",
  },
  slope: {
    label: "Steigende oder fallende Durchschnitte",
    note: "Teile: Veränderungsrichtung von 21-Tage-EMA und 50-Tage-SMA über zehn Handelstage; die gemeinsame Richtung bestimmt den Score.",
  },
};

export function assessmentCriterionLabel(key: string): string {
  return assessmentCriteria[key]?.label ?? key;
}
