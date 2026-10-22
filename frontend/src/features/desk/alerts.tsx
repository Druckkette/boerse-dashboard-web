"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useUiDraft } from "@/components/ui/ui-mode-provider";
import { QueryState } from "@/components/ui/query-state";
import {
  deskApi,
  alertLabels,
  type AlertInput,
  type AlertKind,
} from "@/lib/desk";
import {
  DeskLinks,
  Failure,
  Field,
  Panel,
  useDesk,
  useDeskChange,
} from "./shared";

export function Alerts() {
  const query = useDesk(),
    data = query.data;
  const [input, setInput] = useState<AlertInput>({
    name: "",
    ticker: "",
    kind: "price_below",
    threshold: 0,
    repeat_minutes: 1440,
    quiet_start: "22:00",
    quiet_end: "07:00",
    enabled: true,
    push: false,
  });
  const [onlyOpen, setOnlyOpen] = useState(true),
    [editing, setEditing] = useState<string | null>(null);
  useUiDraft(Boolean(input.name.trim()));
  const save = useDeskChange((body: AlertInput) =>
    deskApi.save("alerts", body, data!.revision, editing || undefined),
  );
  const check = useDeskChange(() => deskApi.check());
  const toggle = useDeskChange((id: string) => {
    const row = data!.alerts.find((r) => r.id === id)!;
    const body: AlertInput = {
      name: row.name,
      ticker: row.ticker,
      kind: row.kind,
      threshold: row.threshold,
      repeat_minutes: row.repeat_minutes,
      quiet_start: row.quiet_start,
      quiet_end: row.quiet_end,
      enabled: !row.enabled,
      push: row.push,
    };
    return deskApi.save("alerts", body, data!.revision, id);
  });
  const ack = useDeskChange((id: string) =>
    deskApi.acknowledge(id, data!.revision),
  );
  const remove = useDeskChange((id: string) =>
    deskApi.remove("alerts", id, data!.revision),
  );
  const legacy = useQuery({
    queryKey: ["desk-legacy-alerts"],
    queryFn: deskApi.legacyAlerts,
  });
  const pending =
    save.isPending ||
    check.isPending ||
    toggle.isPending ||
    ack.isPending ||
    remove.isPending;
  return (
    <div className="space-y-5">
      <DeskLinks />
      <QueryState
        loading={query.isLoading}
        error={query.error}
        hasData={Boolean(data)}
        onRetry={() => query.refetch()}
      />
      {data && (
        <>
          <Panel title="Alarmzentrale">
            <p className="text-sm text-[#526174]">
              Regeln werden automatisch alle fünf Minuten anhand gespeicherter
              Daten geprüft. Kursalarme verwenden abgeschlossene Tageskurse. Die
              bestehenden ATR- und Intraday-Stoppmeldungen laufen unabhängig
              weiter.
            </p>
            <button
              type="button"
              className="app-button"
              disabled={pending}
              onClick={() => check.mutate(undefined)}
            >
              Jetzt prüfen
            </button>
            <Failure
              error={
                save.error ||
                check.error ||
                toggle.error ||
                ack.error ||
                remove.error
              }
            />
            <div className="grid gap-3 lg:grid-cols-2">
              {data.alerts.map((rule) => (
                <article
                  key={rule.id}
                  className="space-y-2 rounded-xl border p-4"
                >
                  <div className="flex flex-wrap justify-between gap-2">
                    <h3 className="font-semibold">{rule.name}</h3>
                    <span className="text-sm">
                      {rule.enabled ? "Aktiv" : "Pausiert"}
                    </span>
                  </div>
                  <p className="text-sm">
                    {rule.ticker && (
                      <Link
                        href={`/stocks/${rule.ticker}`}
                        className="font-semibold text-teal-800"
                      >
                        {rule.ticker} ·{" "}
                      </Link>
                    )}
                    {alertLabels[rule.kind]}
                    {[
                      "price_above",
                      "price_below",
                      "rs_below",
                      "earnings",
                    ].includes(rule.kind) &&
                      ` · ${rule.threshold.toLocaleString("de-DE")}${rule.kind === "earnings" ? " Kalendertage" : ""}`}
                  </p>
                  <p className="text-sm text-[#526174]">
                    Ruhezeit {rule.quiet_start}–{rule.quiet_end} Uhr Berlin ·
                    Wiederholung nach {rule.repeat_minutes} Minuten
                  </p>
                  <p className="text-sm">
                    {rule.check_status === "quiet"
                      ? "Auslösung während Ruhezeit zurückgestellt. "
                      : ""}
                    {rule.check_detail || "Noch nicht geprüft"}
                  </p>
                  {rule.checked_at && (
                    <p className="text-sm text-[#526174]">
                      Geprüft{" "}
                      {new Date(rule.checked_at).toLocaleString("de-DE")}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="app-button"
                      type="button"
                      disabled={pending}
                      onClick={() => {
                        setEditing(rule.id);
                        setInput({
                          name: rule.name,
                          ticker: rule.ticker,
                          kind: rule.kind,
                          threshold: rule.threshold,
                          repeat_minutes: rule.repeat_minutes,
                          quiet_start: rule.quiet_start,
                          quiet_end: rule.quiet_end,
                          enabled: rule.enabled,
                          push: rule.push,
                        });
                        document
                          .getElementById("alarmregel")
                          ?.scrollIntoView({
                            behavior: "smooth",
                            block: "start",
                          });
                      }}
                    >
                      Bearbeiten
                    </button>
                    <button
                      className="app-button"
                      type="button"
                      disabled={pending}
                      onClick={() => toggle.mutate(rule.id)}
                    >
                      {rule.enabled ? "Pausieren" : "Aktivieren"}
                    </button>
                    <button
                      className="app-button"
                      type="button"
                      disabled={pending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Alarm „${rule.name}“ entfernen? Der Verlauf bleibt erhalten.`,
                          )
                        )
                          remove.mutate(rule.id);
                      }}
                    >
                      Regel entfernen
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {!data.alerts.length && (
              <p className="text-sm text-[#526174]">
                Noch keine eigenen Alarmregeln.
              </p>
            )}
          </Panel>
          <Panel
            id="alarmregel"
            title={editing ? "Alarmregel bearbeiten" : "Alarmregel anlegen"}
          >
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                save.mutate(input, {
                  onSuccess: () => {
                    setInput({ ...input, name: "" });
                    setEditing(null);
                  },
                });
              }}
            >
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Name">
                  <input
                    required
                    maxLength={100}
                    className="input-dark"
                    value={input.name}
                    onChange={(e) =>
                      setInput({ ...input, name: e.target.value })
                    }
                  />
                </Field>
                <Field label="Alarmtyp">
                  <select
                    className="input-dark"
                    value={input.kind}
                    onChange={(e) =>
                      setInput({ ...input, kind: e.target.value as AlertKind })
                    }
                  >
                    {Object.entries(alertLabels).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Aktie (für Datenqualität optional)">
                  <input
                    required={input.kind !== "data"}
                    className="input-dark"
                    maxLength={32}
                    value={input.ticker}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        ticker: e.target.value.toUpperCase(),
                      })
                    }
                  />
                </Field>
                {!["stop", "data"].includes(input.kind) && (
                  <Field
                    label={
                      input.kind === "earnings"
                        ? "Vorlauf in Kalendertagen"
                        : input.kind === "rs_below"
                          ? "RS-Schwelle"
                          : "Schwelle in Kurswährung"
                    }
                  >
                    <input
                      type="number"
                      min={input.kind === "earnings" ? 0 : 0.000001}
                      step="any"
                      required
                      className="input-dark"
                      value={input.threshold}
                      onChange={(e) =>
                        setInput({
                          ...input,
                          threshold: Number(e.target.value),
                        })
                      }
                    />
                  </Field>
                )}
                <Field label="Erneut melden nach (Minuten)">
                  <input
                    required
                    type="number"
                    min={15}
                    max={43200}
                    className="input-dark"
                    value={input.repeat_minutes}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        repeat_minutes: Number(e.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="Ruhezeit ab (Berlin)">
                  <input
                    required
                    type="time"
                    className="input-dark"
                    value={input.quiet_start}
                    onChange={(e) =>
                      setInput({ ...input, quiet_start: e.target.value })
                    }
                  />
                </Field>
                <Field label="Ruhezeit bis (Berlin)">
                  <input
                    required
                    type="time"
                    className="input-dark"
                    value={input.quiet_end}
                    onChange={(e) =>
                      setInput({ ...input, quiet_end: e.target.value })
                    }
                  />
                </Field>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={input.push}
                  onChange={(e) =>
                    setInput({ ...input, push: e.target.checked })
                  }
                />
                Zusätzlich per Pushover senden, wenn in den Einstellungen
                aktiviert
              </label>
              <p className="text-sm text-[#526174]">
                Gleiche Anfangs- und Endzeit deaktiviert die Ruhezeit. Fehlende
                oder veraltete Daten lösen keinen Kurs- oder RS-Alarm aus; der
                Prüfstatus zeigt die Einschränkung.
              </p>
              <button
                className="app-button app-button-primary"
                disabled={pending}
              >
                {editing ? "Änderungen speichern" : "Regel speichern"}
              </button>
              {editing && (
                <button
                  type="button"
                  className="app-button ml-2"
                  onClick={() => {
                    setEditing(null);
                    setInput({ ...input, name: "" });
                  }}
                >
                  Bearbeitung verwerfen
                </button>
              )}
            </form>
          </Panel>
          <Panel title="Meldungsverlauf">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={onlyOpen}
                onChange={(e) => setOnlyOpen(e.target.checked)}
              />
              Nur unquittierte Meldungen
            </label>
            {data.history
              .filter((row) => !onlyOpen || !row.acknowledged_at)
              .map((row) => (
                <article
                  key={row.id}
                  className="space-y-2 border-t pt-3 text-sm"
                >
                  <h3 className="font-semibold">
                    {row.name} · {row.ticker}
                  </h3>
                  <p>{row.detail}</p>
                  <p className="text-[#526174]">
                    {new Date(row.at).toLocaleString("de-DE")} · Datenstand{" "}
                    {row.as_of} · Push:{" "}
                    {(
                      {
                        off: "aus",
                        pending: "vorgemerkt",
                        sending: "Versand begonnen",
                        sent: "zugestellt",
                        failed: "fehlgeschlagen",
                        skipped: "übersprungen",
                      } as Record<string, string>
                    )[row.push_status] || row.push_status}
                  </p>
                  {!row.acknowledged_at ? (
                    <button
                      type="button"
                      className="app-button"
                      disabled={pending}
                      onClick={() => ack.mutate(row.id)}
                    >
                      Quittieren
                    </button>
                  ) : (
                    <p>
                      Quittiert{" "}
                      {new Date(row.acknowledged_at).toLocaleString("de-DE")}
                    </p>
                  )}
                </article>
              ))}
            {!data.history.some((row) => !onlyOpen || !row.acknowledged_at) && (
              <p className="text-sm text-[#526174]">
                Keine Meldungen für diese Auswahl.
              </p>
            )}
          </Panel>
          <Panel title="Bestehende ATR- und Stoppzustellungen">
            <Failure error={legacy.error} />
            {legacy.isLoading ? (
              <p className="text-sm">Zustellverlauf wird geladen …</p>
            ) : !legacy.data?.entries.length ? (
              <p className="text-sm text-[#526174]">
                Noch keine Zustellungen protokolliert.
              </p>
            ) : (
              legacy.data.entries.slice(0, 30).map((row, index) => (
                <p key={index} className="border-t py-2 text-sm">
                  {row.ticker || "System"} ·{" "}
                  {row.timestamp
                    ? new Date(row.timestamp).toLocaleString("de-DE")
                    : "Zeitpunkt fehlt"}{" "}
                  · {row.status} · {row.detail}
                </p>
              ))
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
