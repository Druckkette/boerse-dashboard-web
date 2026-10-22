"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { QueryState } from "@/components/ui/query-state";
import { deskApi } from "@/lib/desk";
import { berlinDate } from "@/lib/date";
import {
  DeskLinks,
  Failure,
  Field,
  Panel,
  useDesk,
  useDeskChange,
} from "./shared";

export function Calendar() {
  const desk = useDesk(),
    [days, setDays] = useState(35),
    [scope, setScope] = useState("all");
  const [event, setEvent] = useState({
    title: "",
    date: berlinDate(),
    ticker: "",
    kind: "company",
    note: "",
  });
  const query = useQuery({
    queryKey: ["desk-calendar", days, scope],
    queryFn: () => deskApi.calendar(days, scope),
    staleTime: 60_000,
  });
  const save = useDeskChange(() =>
    deskApi.save("events", event, desk.data!.revision),
  );
  const remove = useDeskChange((id: string) =>
    deskApi.remove("events", id, desk.data!.revision),
  );
  const labels: Record<string, string> = {
    earnings: "Quartalszahlen",
    company: "Unternehmen",
    dividend: "Dividende",
    split: "Split",
    macro: "Makrotermin",
    review: "Eigene Prüfung",
  };
  return (
    <div className="space-y-5">
      <DeskLinks />
      <Panel title="Ereigniskalender">
        <div className="flex flex-wrap gap-3">
          <Field label="Zeitraum">
            <select
              className="input-dark"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              {[7, 14, 35, 90, 365].map((value) => (
                <option key={value} value={value}>
                  {value} Kalendertage
                </option>
              ))}
            </select>
          </Field>
          <Field label="Auswahl">
            <select
              className="input-dark"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            >
              <option value="all">Depot, Watchlists & eigene Termine</option>
              <option value="portfolio">Nur Depot</option>
              <option value="watchlist">Nur Watchlists</option>
            </select>
          </Field>
        </div>
        <QueryState
          loading={query.isLoading}
          error={query.error}
          hasData={Boolean(query.data)}
          onRetry={() => query.refetch()}
        />
        <Failure error={remove.error} />
        {query.data?.coverage_note && (
          <p role="status" className="text-sm text-amber-800">
            {query.data.coverage_note}
          </p>
        )}
        <p className="text-sm text-[#526174]">
          Gespeicherte Anbietertermine und selbst gepflegte Unternehmens- und
          Makroereignisse. Fehlende Termine bedeuten keine Entwarnung.
        </p>
        {query.data?.rows.map((row) => (
          <article key={row.id} className="space-y-2 rounded-xl border p-4">
            <div className="flex flex-wrap justify-between gap-2">
              <h3 className="font-semibold">{row.title}</h3>
              <time className="font-semibold" dateTime={row.date}>
                {new Date(`${row.date}T12:00:00`).toLocaleDateString("de-DE")}
              </time>
            </div>
            <p className="text-sm text-[#526174]">
              {labels[row.kind] || row.kind} · {row.source} ·{" "}
              {row.time === "bmo"
                ? "Vor US-Handelsbeginn"
                : row.time === "amc"
                  ? "Nach US-Handelsschluss"
                  : row.kind === "earnings"
                    ? "Veröffentlichungszeit unbekannt"
                    : "Eigener Termin"}
            </p>
            {row.note && (
              <p className="whitespace-pre-wrap break-words text-sm">
                {row.note}
              </p>
            )}
            {row.date_conflict && (
              <p className="text-sm text-amber-800">
                Anbietertermine widersprechen sich. Veröffentlichung beim
                Unternehmen prüfen.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {row.ticker && (
                <Link className="app-button" href={`/stocks/${row.ticker}`}>
                  Aktie öffnen
                </Link>
              )}
              {row.source === "Eigener Termin" && (
                <button
                  type="button"
                  className="app-button"
                  disabled={remove.isPending || !desk.data}
                  onClick={() => remove.mutate(row.id)}
                >
                  Eigenen Termin entfernen
                </button>
              )}
            </div>
          </article>
        ))}
        {query.data && !query.data.rows.length && (
          <p className="text-sm">
            Keine gespeicherten Ereignisse für diese Auswahl.
          </p>
        )}
      </Panel>
      <Panel title="Eigenes Ereignis eintragen">
        <Failure error={desk.error || save.error} />
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined, {
              onSuccess: () => setEvent({ ...event, title: "", note: "" }),
            });
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Titel">
              <input
                required
                className="input-dark"
                maxLength={160}
                value={event.title}
                onChange={(e) => setEvent({ ...event, title: e.target.value })}
              />
            </Field>
            <Field label="Datum">
              <input
                required
                type="date"
                className="input-dark"
                value={event.date}
                onChange={(e) => setEvent({ ...event, date: e.target.value })}
              />
            </Field>
            <Field label="Aktie (optional)">
              <input
                className="input-dark"
                maxLength={32}
                value={event.ticker}
                onChange={(e) =>
                  setEvent({ ...event, ticker: e.target.value.toUpperCase() })
                }
              />
            </Field>
            <Field label="Art">
              <select
                className="input-dark"
                value={event.kind}
                onChange={(e) => setEvent({ ...event, kind: e.target.value })}
              >
                {Object.entries(labels)
                  .filter(([key]) => key !== "earnings")
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
              </select>
            </Field>
          </div>
          <Field label="Notiz">
            <textarea
              maxLength={4000}
              className="input-dark"
              value={event.note}
              onChange={(e) => setEvent({ ...event, note: e.target.value })}
            />
          </Field>
          <button
            className="app-button app-button-primary"
            disabled={save.isPending || !desk.data}
          >
            Termin speichern
          </button>
        </form>
      </Panel>
    </div>
  );
}
