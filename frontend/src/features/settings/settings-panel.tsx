"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BellRing,
  DatabaseZap,
  Rocket,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/ui/status-chip";
import { api } from "@/lib/api/client";
import { normalizedWeights, settingsChanges } from "./settings-draft";
import { qualityLabel } from "@/lib/format";
import type { AppSettings, AssessmentScoreWeights } from "@/lib/types/api";

const defaultAssessmentScoreWeights: AssessmentScoreWeights = {
  overall: { technical: 30, fundamental: 30, chart: 30, moving_average: 10 },
  technical: {
    k4_rs_leadership: 30,
    k13_rs_dynamics: 23.3333,
    rs_rating: 20,
    high_position: 10,
    up_down_volume: 8.33335,
    cmf: 8.33335,
  },
  fundamental: { fundamental_core: 83.3333, k9_eps_sales_alignment: 16.6667 },
  chart: {
    price_action_core: 66.6666,
    k35_down_week_quality: 16.6667,
    k38_hh_hl_good_close: 16.6667,
  },
  moving_average: {
    price_above_200_sma: 20,
    price_above_50_sma: 15,
    price_above_21_ema: 10,
    price_above_10_sma: 5,
    ma_order: 15,
    persistence: 15,
    slope: 20,
  },
};

const fallbackSettings: AppSettings = {
  atr_threshold: 1.5,
  risk_per_position_pct: 1,
  target_risk_contribution: 0.2,
  max_depot_loss_lower_pct: 4,
  max_depot_loss_upper_pct: 8,
  position_monitor_enabled: false,
  position_monitor_interval_minutes: 1,
  position_monitor_threshold_atr: 1.5,
  position_monitor_atr_period: 14,
  position_monitor_lookback_days: 420,
  position_monitor_cooldown_hours: 18,
  position_monitor_reference: "previous_close",
  position_monitor_ma_alerts_enabled: true,
  position_monitor_assessment_alerts_enabled: true,
  position_monitor_assessment_interval_minutes: 15,
  pushover_enabled: false,
  pushover_configured: false,
  rs_rating_source: "computed",
  data_jobs_enabled: true,
  market_ampel_logic: "current",
  assessment_score_weights: defaultAssessmentScoreWeights,
};

const scoreWeightLabels: Record<
  keyof AssessmentScoreWeights,
  { title: string; fields: Record<string, string> }
> = {
  overall: {
    title: "Gewichtung im Gesamtscore",
    fields: {
      technical: "Technical",
      fundamental: "Fundamental",
      chart: "Chart",
      moving_average: "Moving Average",
    },
  },
  technical: {
    title: "Teil-Scores · Technical",
    fields: {
      k4_rs_leadership: "K4 RS Leadership",
      k13_rs_dynamics: "K13 RS Dynamics",
      rs_rating: "RS Rating",
      high_position: "Hoch-Position",
      up_down_volume: "Up/Down-Volumen",
      cmf: "CMF",
    },
  },
  fundamental: {
    title: "Teil-Scores · Fundamental",
    fields: {
      fundamental_core: "Fundamental Core",
      k9_eps_sales_alignment: "K9 EPS/Umsatz",
    },
  },
  chart: {
    title: "Teil-Scores · Chart",
    fields: {
      price_action_core: "Price Action Core",
      k35_down_week_quality: "K35 Down-Week-Qualität",
      k38_hh_hl_good_close: "K38 HH/HL Good Close",
    },
  },
  moving_average: {
    title: "Teil-Scores · Moving Average",
    fields: {
      price_above_200_sma: "Kurs > 200 SMA",
      price_above_50_sma: "Kurs > 50 SMA",
      price_above_21_ema: "Kurs > 21 EMA",
      price_above_10_sma: "Kurs > 10 SMA",
      ma_order: "MA-Reihenfolge",
      persistence: "Persistenz",
      slope: "Steigung",
    },
  },
};

const monitorReferenceDescriptions: Record<
  AppSettings["position_monitor_reference"],
  string
> = {
  high_since_buy:
    "Misst den Rückgang vom höchsten Tageshoch seit dem Kaufdatum.",
  close_since_buy:
    "Misst den Rückgang vom höchsten Tagesschluss seit dem Kaufdatum.",
  entry_price:
    "Misst den Rückgang vom persönlichen Einstandskurs der Position.",
  previous_close:
    "Misst ausschließlich den Rückgang gegenüber dem vorherigen Handelstagesschluss.",
};

export function SettingsPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
  });
  const dataDiagnostics = useQuery({
    queryKey: ["settings-data-diagnostics"],
    queryFn: api.dataDiagnostics,
    staleTime: 60_000,
  });
  const readiness = useQuery({
    queryKey: ["system-readiness"],
    queryFn: api.readiness,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
  const [local, setLocal] = useState<AppSettings | null>(null);
  const [tab, setTab] = useState("investment");
  const changes = data && local ? settingsChanges(data, local) : {};
  const changeCount = Object.keys(changes).length;
  const dirty = changeCount > 0;
  const settings = local ?? data ?? fallbackSettings;

  const mutation = useMutation({
    mutationFn: api.patchSettings,
    onSuccess: (updated) => {
      queryClient.setQueryData(["settings"], updated);
      queryClient.invalidateQueries({ queryKey: ["market-ampel"] });
      queryClient.invalidateQueries({ queryKey: ["market-overview"] });
      queryClient.invalidateQueries({ queryKey: ["home-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-snapshot"] });
      setLocal(null);
    },
  });
  const pushoverMutation = useMutation({
    mutationFn: () =>
      api.startJob({
        type: "pushover_test",
        payload: { mode: "manual", source: "settings" },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function normalizeWeights() {
    update(
      "assessment_score_weights",
      normalizedWeights(settings.assessment_score_weights),
    );
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setLocal((current) => ({
      ...(current ?? data ?? fallbackSettings),
      [key]: value,
    }));
    mutation.reset();
  }

  function updateNumber(
    key: keyof AppSettings,
    value: number,
    min: number,
    max: number,
    step = 0.1,
  ) {
    if (!Number.isFinite(value)) return;
    const rounded = Math.round(value / step) * step;
    update(
      key,
      Math.max(min, Math.min(max, Number(rounded.toFixed(4)))) as never,
    );
  }

  function updateScoreWeight(
    group: keyof AssessmentScoreWeights,
    key: string,
    value: number,
  ) {
    if (!Number.isFinite(value)) return;
    const base = local ?? data ?? fallbackSettings;
    const currentGroup = base.assessment_score_weights[group] as Record<
      string,
      number
    >;
    const nextGroup = {
      ...currentGroup,
      [key]: Math.max(0, Math.min(100, Number(value.toFixed(4)))),
    };
    if (Object.values(nextGroup).reduce((sum, weight) => sum + weight, 0) <= 0)
      return;
    setLocal({
      ...base,
      assessment_score_weights: {
        ...base.assessment_score_weights,
        [group]: nextGroup,
      },
    });
    mutation.reset();
  }

  function resetScoreWeights() {
    update(
      "assessment_score_weights",
      structuredClone(defaultAssessmentScoreWeights),
    );
  }

  const invalidRisk =
    settings.max_depot_loss_lower_pct >= settings.max_depot_loss_upper_pct;
  if (isLoading) return <p role="status">Einstellungen werden geladen…</p>;
  if (error || !data)
    return (
      <p
        role="alert"
        className="rounded border border-rose-200 bg-rose-50 p-4 text-rose-700"
      >
        Einstellungen konnten nicht geladen werden. Bitte die Seite neu laden.
      </p>
    );

  return (
    <div className="space-y-4 text-[#172033]">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-[#687386]">
          Strategie, Risiko, Überwachung und Datenquellen konfigurieren.
        </p>
      </div>
      <nav
        aria-label="Einstellungsbereiche"
        className="flex gap-1 overflow-x-auto rounded-[12px] border border-[#e3e8ef] bg-white p-1"
      >
        {[
          ["investment", "Investmentmodell"],
          ["risk", "Portfolio & Risiko"],
          ["alerts", "Überwachung & Alerts"],
          ["system", "Daten & System"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={tab === id}
            onClick={() => setTab(id)}
            className={`shrink-0 rounded-[8px] px-4 py-2 text-sm font-medium ${tab === id ? "bg-[#e8f4f2] text-[#0f766e]" : "text-[#687386] hover:bg-[#f6f8fb]"}`}
          >
            {label}
          </button>
        ))}
      </nav>
      <fieldset
        disabled={mutation.isPending}
        className="min-w-0 space-y-4 disabled:opacity-70"
      >
        {tab === "investment" && (
          <section aria-label="Investmentmodell" className="space-y-4">
            {" "}
            <SettingCard
              description="Wähle zwischen der unveränderten bisherigen Marktampel und einer IBD-näheren Variante. Die Variante gilt für alle Indizes; jeder Index wird unabhängig berechnet."
              title="Marktampel-Logik"
              value={
                settings.market_ampel_logic === "ibd"
                  ? "IBD Logik"
                  : "Aktuelle Logik"
              }
            >
              <div className="space-y-3">
                <Field label="Variante">
                  <select
                    className="w-full rounded-[8px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e]"
                    value={settings.market_ampel_logic}
                    onChange={(event) =>
                      update(
                        "market_ampel_logic",
                        event.target.value as AppSettings["market_ampel_logic"],
                      )
                    }
                  >
                    <option value="current">Aktuelle Logik</option>
                    <option value="ibd">IBD Logik</option>
                  </select>
                </Field>
                <details>
                  <summary className="cursor-pointer text-sm text-[#0f766e]">
                    Details anzeigen
                  </summary>
                  <p className="mt-2 text-xs leading-5 text-[#687386]">
                    IBD Logik startet die Beobachtung eines Rallyversuchs
                    früher, erlaubt den Startschuss ab Rally Day 4 und trennt
                    ein negiertes Startschuss-/FTD-Tief vom tieferen
                    Rally-Day-1-Tief. Der Powertrend wird als zusätzlicher
                    Status berechnet und ersetzt die normale Aufwärtstrend-Phase
                    nicht. Die Korrekturschwellen (8% oder unter 50-SMA bei 3%
                    Rückgang bzw. drei Distributionstagen) sind eine eigene
                    Näherung. Die +1%-Startschuss-Schwelle und die weitere
                    Bestätigung bleiben deine Buchregeln; dies ist keine
                    vollständige Nachbildung des IBD Market Pulse.
                  </p>
                </details>
              </div>
            </SettingCard>{" "}
            <SettingCard
              description="Lege fest, wie stark die Hauptscores und ihre Teilkriterien in die Bewertung einfließen. Fehlende Daten werden weiterhin automatisch über die verfügbaren Gewichte renormalisiert."
              title="Gewichtung der Aktienbewertung"
              value="prozentual"
            >
              <div className="space-y-4">
                <p className="text-sm text-[#687386]">
                  {Object.entries(settings.assessment_score_weights.overall)
                    .map(
                      ([key, value]) =>
                        `${scoreWeightLabels.overall.fields[key]} ${Number(value.toFixed(2))} %`,
                    )
                    .join(" · ")}
                </p>
                <details>
                  <summary className="cursor-pointer text-sm font-semibold text-[#0f766e]">
                    Gewichtung bearbeiten
                  </summary>
                  <div className="mt-4 space-y-3">
                    {(
                      Object.keys(scoreWeightLabels) as Array<
                        keyof AssessmentScoreWeights
                      >
                    ).map((group) => (
                      <ScoreWeightGroup
                        group={group}
                        key={group}
                        values={
                          settings.assessment_score_weights[group] as Record<
                            string,
                            number
                          >
                        }
                        onChange={(key, value) =>
                          updateScoreWeight(group, key, value)
                        }
                      />
                    ))}
                    <div className="flex flex-col gap-2 border-t border-[#e3e8ef] pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-xs leading-5 text-[#687386]">
                        Gespeicherte Änderungen wirken auf Detailbewertungen.
                        Für Ranking und Screening anschließend den Job
                        „Aktienbewertungen aktualisieren“ starten.
                      </p>
                      <button
                        type="button"
                        className="rounded border border-[#d8e1ea] px-3 py-2 text-xs"
                        onClick={normalizeWeights}
                      >
                        Auf 100 % normieren
                      </button>
                      <button
                        className="shrink-0 rounded border border-[#d8e1ea] px-3 py-2 text-xs transition hover:border-emerald-300/60"
                        type="button"
                        onClick={resetScoreWeights}
                      >
                        Standard wiederherstellen
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            </SettingCard>
          </section>
        )}
        {tab === "risk" && (
          <section aria-label="Portfolio & Risiko">
            <SettingCard
              title="Risikomodell"
              description="Standardwerte für Positionsgröße und Depotrisiko. Der Positionsgrößenrechner übernimmt Risiko und Ziel-Risikobeitrag als Vorgaben."
              value="Globale Vorgaben"
            >
              <div className="grid gap-3 md:grid-cols-2">
                <NumberField
                  label="Risiko je Position (%)"
                  value={settings.risk_per_position_pct}
                  min={0.1}
                  max={5}
                  step={0.1}
                  onChange={(value) =>
                    updateNumber("risk_per_position_pct", value, 0.1, 5)
                  }
                />
                <NumberField
                  label="Ziel-Risikobeitrag"
                  value={settings.target_risk_contribution}
                  min={0.05}
                  max={0.5}
                  step={0.01}
                  onChange={(value) =>
                    updateNumber(
                      "target_risk_contribution",
                      value,
                      0.05,
                      0.5,
                      0.01,
                    )
                  }
                />
                <NumberField
                  label="Depotverlust Warnschwelle (%)"
                  value={settings.max_depot_loss_lower_pct}
                  min={0}
                  max={100}
                  step={0.1}
                  onChange={(value) =>
                    updateNumber("max_depot_loss_lower_pct", value, 0, 100)
                  }
                />
                <NumberField
                  label="Depotverlust kritische Schwelle (%)"
                  value={settings.max_depot_loss_upper_pct}
                  min={0}
                  max={100}
                  step={0.1}
                  onChange={(value) =>
                    updateNumber("max_depot_loss_upper_pct", value, 0, 100)
                  }
                />
              </div>
            </SettingCard>
          </section>
        )}
        {tab === "alerts" && (
          <section aria-label="Überwachung & Alerts" className="space-y-4">
            {" "}
            <SettingCard
              description="Überwacht offene Positionen auf Kurs-, MA- und Bewertungsänderungen."
              title="Positionsmonitor"
              value={settings.position_monitor_enabled ? "aktiv" : "aus"}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex items-center justify-between gap-3 rounded border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm">
                  <span>Monitor aktiv</span>
                  <input
                    checked={settings.position_monitor_enabled}
                    className="size-4 accent-[#0f766e]"
                    type="checkbox"
                    onChange={(event) =>
                      update("position_monitor_enabled", event.target.checked)
                    }
                  />
                </label>
                <Field label="Referenz">
                  <select
                    className="w-full rounded-[8px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e]"
                    value={settings.position_monitor_reference}
                    onChange={(event) =>
                      update(
                        "position_monitor_reference",
                        event.target
                          .value as AppSettings["position_monitor_reference"],
                      )
                    }
                  >
                    <option value="high_since_buy">Tageshoch seit Kauf</option>
                    <option value="close_since_buy">
                      Schlusskurs-Hoch seit Kauf
                    </option>
                    <option value="entry_price">Einstand</option>
                    <option value="previous_close">Vortagesschluss</option>
                  </select>
                </Field>
                <NumberField
                  label="ATR Schwelle"
                  max={10}
                  min={0.5}
                  step={0.1}
                  value={settings.position_monitor_threshold_atr}
                  onChange={(value) =>
                    updateNumber(
                      "position_monitor_threshold_atr",
                      value,
                      0.5,
                      10,
                    )
                  }
                />
                <label className="flex items-center justify-between gap-3 rounded-[9px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm text-[#172033]">
                  <span>MA-Brüche sofort melden</span>
                  <input
                    checked={settings.position_monitor_ma_alerts_enabled}
                    className="size-4 accent-[#0f766e]"
                    type="checkbox"
                    onChange={(event) =>
                      update(
                        "position_monitor_ma_alerts_enabled",
                        event.target.checked,
                      )
                    }
                  />
                </label>
                <label className="flex items-center justify-between gap-3 rounded-[9px] border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm text-[#172033]">
                  <span>Bewertungsänderungen melden</span>
                  <input
                    checked={
                      settings.position_monitor_assessment_alerts_enabled
                    }
                    className="size-4 accent-[#0f766e]"
                    type="checkbox"
                    onChange={(event) =>
                      update(
                        "position_monitor_assessment_alerts_enabled",
                        event.target.checked,
                      )
                    }
                  />
                </label>
                <details className="md:col-span-2">
                  <summary className="cursor-pointer text-sm font-semibold text-[#0f766e]">
                    Erweiterte Monitor-Einstellungen
                  </summary>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {" "}
                    <NumberField
                      label="ATR Periode"
                      max={63}
                      min={5}
                      step={1}
                      value={settings.position_monitor_atr_period}
                      onChange={(value) =>
                        updateNumber(
                          "position_monitor_atr_period",
                          value,
                          5,
                          63,
                          1,
                        )
                      }
                    />
                    <NumberField
                      label="Fallback-Lookback Tage"
                      max={740}
                      min={30}
                      step={5}
                      value={settings.position_monitor_lookback_days}
                      onChange={(value) =>
                        updateNumber(
                          "position_monitor_lookback_days",
                          value,
                          30,
                          740,
                          5,
                        )
                      }
                    />
                    <NumberField
                      label="Bewertung prüfen (Min.)"
                      max={120}
                      min={5}
                      step={5}
                      value={
                        settings.position_monitor_assessment_interval_minutes
                      }
                      onChange={(value) =>
                        updateNumber(
                          "position_monitor_assessment_interval_minutes",
                          value,
                          5,
                          120,
                          5,
                        )
                      }
                    />
                    <p className="rounded-[9px] border border-[#d8e1ea] bg-[#f6f8fb] px-3 py-2 text-xs leading-5 text-[#687386] md:col-span-2">
                      Brüche und Rückeroberungen von 10-SMA, 21-EMA, 50-SMA und
                      200-SMA werden mit dem Live-Kurs jede Minute geprüft. Die
                      vollständige Aktienbewertung wird ressourcenschonend alle{" "}
                      {settings.position_monitor_assessment_interval_minutes}{" "}
                      Minuten verglichen. Nur Zustandsänderungen lösen eine
                      Nachricht aus.
                    </p>
                    <p className="rounded border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-xs leading-5 text-[#687386] md:col-span-2">
                      {
                        monitorReferenceDescriptions[
                          settings.position_monitor_reference
                        ]
                      }{" "}
                      Alle Kurswerte und der ATR werden vor dem Vergleich auf
                      USD normalisiert. Für jede Referenz gilt derselbe
                      Pushover-Pfad: Prüfung jede Minute, erneuter Alarm nach
                      einer echten Erholung und erneutem Bruch sowie Eskalation
                      bei 2x ATR-Schwelle. Ein Alarm gilt erst nach bestätigter
                      Zustellung als versendet. Der Tages-Cooldown wechselt um
                      07:30 Uhr deutscher Zeit, ohne den unveränderten Verlust
                      des Vortags erneut zu melden.
                    </p>
                  </div>
                </details>
              </div>
            </SettingCard>{" "}
            <SettingCard
              description="Secrets bleiben in der Container-Umgebung. Die Oberfläche speichert nur, ob Alerts genutzt werden sollen."
              title="Pushover"
              value={
                settings.pushover_configured ? "konfiguriert" : "Secrets fehlen"
              }
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex items-center justify-between gap-3 rounded border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm">
                  <span>Pushover aktiv</span>
                  <input
                    checked={settings.pushover_enabled}
                    className="size-4 accent-[#0f766e]"
                    type="checkbox"
                    onChange={(event) =>
                      update("pushover_enabled", event.target.checked)
                    }
                  />
                </label>
                <button
                  className="inline-flex items-center justify-center gap-2 rounded border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm transition hover:border-emerald-300/60 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={
                    pushoverMutation.isPending ||
                    dirty ||
                    !data?.pushover_enabled ||
                    !data?.pushover_configured
                  }
                  type="button"
                  onClick={() => pushoverMutation.mutate()}
                >
                  <BellRing size={16} />
                  {pushoverMutation.isPending
                    ? "Startet"
                    : "Testnachricht senden"}
                </button>
              </div>
              <p className="mt-3 text-xs text-[#687386]">
                Zum Testen Pushover konfigurieren, aktivieren und Änderungen
                speichern.
              </p>
              {pushoverMutation.isSuccess && (
                <p role="status" className="mt-3 text-sm text-[#0f766e]">
                  Testjob gestartet. Den Versandstatus findest du unter Jobs.
                </p>
              )}
              {pushoverMutation.error && (
                <div className="mt-3 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                  {pushoverMutation.error instanceof Error
                    ? pushoverMutation.error.message
                    : "Pushover-Test konnte nicht gestartet werden."}
                </div>
              )}
            </SettingCard>
          </section>
        )}
        {tab === "system" && (
          <section aria-label="Daten & System" className="space-y-4">
            <SettingCard
              title="System"
              description="Aktueller Zustand der geprüften Systemdienste."
              value={
                readiness.data
                  ? {
                      ready: "Betriebsbereit",
                      degraded: "Eingeschränkt",
                      not_ready: "Nicht bereit",
                    }[readiness.data.status]
                  : readiness.isLoading
                    ? "Lädt…"
                    : "Nicht erreichbar"
              }
            >
              <div className="flex flex-wrap gap-2">
                {readiness.data?.checks.map((check) => (
                  <StatusChip
                    key={check.name}
                    tone={
                      check.status === "ok"
                        ? "good"
                        : check.status === "error"
                          ? "bad"
                          : check.status === "warning"
                            ? "warning"
                            : "neutral"
                    }
                  >
                    {check.name}:{" "}
                    {
                      {
                        ok: "OK",
                        error: "Fehler",
                        warning: "Prüfen",
                        unknown: "Unbekannt",
                      }[check.status]
                    }
                  </StatusChip>
                ))}
              </div>
              <Link
                href="/jobs#system-status"
                className="mt-3 inline-block text-sm font-semibold text-[#0f766e]"
              >
                Systemdetails öffnen →
              </Link>
            </SettingCard>
            <SettingCard
              description="Worker dürfen schwere Datenjobs starten; UI-Clicks bleiben davon getrennt."
              title="Datenjobs"
              value={settings.data_jobs_enabled ? "aktiv" : "aus"}
            >
              <div className="grid gap-3 md:grid-cols-2">
                <label className="flex items-center justify-between gap-3 rounded border border-[#e3e8ef] bg-[#f9fbfd] px-3 py-2 text-sm">
                  <span>Datenjobs aktiv</span>
                  <input
                    checked={settings.data_jobs_enabled}
                    className="size-4 accent-[#0f766e]"
                    type="checkbox"
                    onChange={(event) =>
                      update("data_jobs_enabled", event.target.checked)
                    }
                  />
                </label>
                <Field label="RS Quelle">
                  <select
                    className="w-full rounded-[8px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e]"
                    value={settings.rs_rating_source}
                    onChange={(event) =>
                      update(
                        "rs_rating_source",
                        event.target.value as AppSettings["rs_rating_source"],
                      )
                    }
                  >
                    <option value="computed">
                      Intern aus Price-Cache berechnen
                    </option>
                    <option value="csv_latest">
                      Externe RS-Daten verwenden
                    </option>
                  </select>
                </Field>
                <p className="text-xs leading-5 text-[#687386] md:col-span-2">
                  Externe RS-Daten stammen aus der Fred-GitHub-CSV. Die gewählte
                  Quelle gilt für Worker, Rankings und Aktienbewertung. Bei der
                  externen CSV wird deren eigenes Datenstand-Datum übernommen;
                  eine veraltete Datei wird nicht als aktuell markiert.
                </p>
              </div>
            </SettingCard>
            <SettingCard
              title="Datenqualität"
              description={
                dataDiagnostics.data?.summary ??
                (dataDiagnostics.isLoading
                  ? "Datenqualität wird geladen…"
                  : "Datenqualität ist aktuell nicht erreichbar.")
              }
              value={
                dataDiagnostics.data
                  ? qualityLabel(dataDiagnostics.data.decision_status)
                  : "Unbekannt"
              }
            >
              {dataDiagnostics.data && (
                <div className="flex flex-wrap gap-3 text-sm">
                  <span>
                    Kurse: {dataDiagnostics.data.missing_price_count} fehlend ·{" "}
                    {dataDiagnostics.data.stale_price_count} veraltet
                  </span>
                  <span>
                    Fundamentals:{" "}
                    {dataDiagnostics.data.missing_fundamentals_count} fehlend
                  </span>
                  <span>
                    Stop-Abdeckung:{" "}
                    {Math.round(dataDiagnostics.data.stop_coverage_pct)} %
                  </span>
                </div>
              )}
              <Link
                href="/jobs#data-quality"
                className="mt-3 inline-block text-sm font-semibold text-[#0f766e]"
              >
                Datenqualität öffnen →
              </Link>
            </SettingCard>
            <Link
              href="/jobs#data-management"
              className="inline-block text-sm font-semibold text-[#0f766e]"
            >
              Datenverwaltung und 13F-Mapping öffnen →
            </Link>
            <SettingsWorkflowLinks />
          </section>
        )}
      </fieldset>
      <div className="sticky bottom-4 z-20 rounded-[12px] border border-[#d8e1ea] bg-white p-4 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span role="status" className="text-sm">
            {mutation.isPending
              ? "Wird gespeichert…"
              : dirty
                ? `${changeCount} Änderungen`
                : mutation.isSuccess
                  ? "✓ Gespeichert"
                  : "Keine ungespeicherten Änderungen"}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-[#d8e1ea] px-3 py-2 text-sm disabled:opacity-50"
              disabled={!dirty || mutation.isPending}
              onClick={() => {
                setLocal(null);
                mutation.reset();
              }}
            >
              Verwerfen
            </button>
            <button
              type="button"
              className="rounded bg-[#0f766e] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              disabled={!dirty || mutation.isPending || invalidRisk}
              onClick={() => {
                mutation.mutate(changes);
              }}
            >
              Änderungen speichern
            </button>
          </div>
        </div>
        {invalidRisk && (
          <p role="alert" className="mt-2 text-sm text-rose-700">
            Die Depotwarnschwelle muss unter der kritischen Schwelle liegen
            (Portfolio & Risiko).
          </p>
        )}
        {mutation.error && (
          <p role="alert" className="mt-2 text-sm text-rose-700">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "Änderungen konnten nicht gespeichert werden."}
          </p>
        )}
      </div>
    </div>
  );
}

function ScoreWeightGroup({
  group,
  values,
  onChange,
}: {
  group: keyof AssessmentScoreWeights;
  values: Record<string, number>;
  onChange: (key: string, value: number) => void;
}) {
  const definition = scoreWeightLabels[group];
  const total = Object.values(values).reduce((sum, value) => sum + value, 0);
  const totalIsHundred = Math.abs(total - 100) < 0.01;
  return (
    <details
      open={group === "overall"}
      className="rounded border border-[#e3e8ef] bg-[#f9fbfd] p-4"
    >
      <summary className="mb-3 flex cursor-pointer items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">{definition.title}</h3>
        <span
          className={
            totalIsHundred ? "text-xs text-[#0f766e]" : "text-xs text-amber-700"
          }
        >
          Summe {total.toFixed(1)}%
        </span>
      </summary>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(definition.fields).map(([key, label]) => (
          <label className="block text-sm" key={key}>
            <span className="mb-1 block text-[#687386]">{label}</span>
            <div className="relative">
              <input
                className="w-full rounded-[8px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e] pr-8"
                max={100}
                min={0}
                step={0.1}
                type="number"
                value={Number(values[key].toFixed(4))}
                onChange={(event) => onChange(key, Number(event.target.value))}
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#687386]">
                %
              </span>
            </div>
          </label>
        ))}
      </div>
      {!totalIsHundred ? (
        <p className="mt-3 text-xs leading-5 text-amber-700">
          Die Berechnung normiert diese Werte auf 100%. Für eine leichter
          lesbare Konfiguration sollte die Summe 100% betragen.
        </p>
      ) : null}
    </details>
  );
}

function SettingsWorkflowLinks() {
  return (
    <section className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-4">
        <h2 className="text-base font-semibold">Verwaltung</h2>
        <p className="mt-1 text-sm text-[#687386]">
          Einmalige Einrichtung und Portfolio-Imports sind aus der
          Hauptnavigation hierher verschoben.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <SettingsWorkflowLink
          description="Erststart, Runtime-Secrets, Datenbank-Ziel, Datenjobs und Systemprüfung."
          href="/setup"
          icon={<Rocket size={18} />}
          title="Setup öffnen"
        />
        <SettingsWorkflowLink
          description="Positions-CSV und Trade-Republic-Import als vollständige Importseite."
          href="/portfolio/imports"
          icon={<Upload size={18} />}
          title="Import öffnen"
        />
        <SettingsWorkflowLink
          description="Marktdaten initialisieren, Smart Refresh starten und Worker-Status prüfen."
          href="/jobs"
          icon={<DatabaseZap size={18} />}
          title="Jobs öffnen"
        />
      </div>
    </section>
  );
}

function SettingsWorkflowLink({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      className="group flex items-center gap-2 rounded border border-[#d8e1ea] bg-white px-3 py-2 text-sm transition hover:border-[#0f766e]"
      href={href}
      title={description}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-[#0f766e]">{icon}</div>
        <ArrowRight
          className="text-[#687386] transition group-hover:translate-x-0.5 group-hover:text-[#0f766e]"
          size={16}
        />
      </div>
      <div className="font-semibold">{title}</div>
    </Link>
  );
}

function SettingCard({
  title,
  description,
  value,
  children,
}: {
  title: string;
  description: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[14px] border border-[#e3e8ef] bg-white p-5 shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[#687386]">{description}</p>
        </div>
        <StatusChip tone="neutral">{value}</StatusChip>
      </div>
      {children}
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        className="w-full rounded-[8px] border border-[#d8e1ea] bg-white px-3 py-2 text-sm text-[#172033] focus:outline-[#0f766e]"
        max={max}
        min={min}
        step={step}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[#687386]">{label}</span>
      {children}
    </label>
  );
}
