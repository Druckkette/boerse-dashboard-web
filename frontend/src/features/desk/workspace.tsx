"use client";
import { AssessmentSnapshot } from "./assessment-snapshot";
import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { QueryState } from "@/components/ui/query-state";
import { useUiDraft } from "@/components/ui/ui-mode-provider";
import {
  deskApi,
  stageLabels,
  money,
  percent,
  type PlanInput,
  type Stage,
  type Watchlist,
  type WatchItem,
} from "@/lib/desk";
import {
  DeskLinks,
  Failure,
  Field,
  Metric,
  Panel,
  useDesk,
  useDeskChange,
} from "./shared";

export function Workspace() {
  const query = useDesk();
  return (
    <div className="space-y-5">
      <DeskLinks />
      <QueryState
        loading={query.isLoading}
        error={query.error}
        hasData={Boolean(query.data)}
        onRetry={() => query.refetch()}
      />
      {query.data && (
        <>
          <Watchlists />
          <PlanEditor />
          <Plans />
        </>
      )}
    </div>
  );
}

function Watchlists() {
  const query = useDesk(),
    data = query.data!;
  const [selected, setSelected] = useState("default"),
    [name, setName] = useState(""),
    [ticker, setTicker] = useState(""),
    [search, setSearch] = useState("");
  const [picked, setPicked] = useState<string[]>([]),
    [target, setTarget] = useState("");
  const [draft, setDraft] = useState<{
    list: Watchlist;
    revision: number;
    tagsText: Record<string, string>;
  } | null>(null);
  const list =
    data.watchlists.find((row) => row.id === selected) || data.watchlists[0];
  function editList() {
    setDraft({
      list: structuredClone(list),
      revision: data.revision,
      tagsText: Object.fromEntries(
        list.items.map((item) => [item.ticker, item.tags.join(", ")]),
      ),
    });
  }
  const transfer = useDeskChange((move: boolean) =>
    deskApi.transfer(list.id, target, picked, move, data.revision),
  );
  const change = useDeskChange(
    async ({
      body,
      id,
      revision,
    }: {
      body: Omit<Watchlist, "id">;
      id?: string;
      revision?: number;
    }) => deskApi.save("watchlists", body, revision ?? data.revision, id),
  );
  const remove = useDeskChange((id: string) =>
    deskApi.remove("watchlists", id, data.revision),
  );
  useUiDraft(Boolean(draft));
  const shown = list.items.filter((item) =>
    `${item.ticker} ${item.note} ${item.tags.join(" ")}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  function saveItems(items: WatchItem[]) {
    change.mutate({ id: list.id, body: { name: list.name, items } });
  }
  return (
    <Panel title="Meine Watchlists" id="watchlists">
      <div className="flex flex-wrap gap-2">
        {data.watchlists.map((row) => (
          <button
            key={row.id}
            type="button"
            className={`app-button ${row.id === list.id ? "app-button-primary" : ""}`}
            aria-pressed={row.id === list.id}
            onClick={() => {
              setSelected(row.id);
              setPicked([]);
            }}
          >
            {row.name} · {row.items.length}
          </button>
        ))}
      </div>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate(
            { body: { name, items: [] } },
            { onSuccess: () => setName("") },
          );
        }}
      >
        <Field label="Neue Liste">
          <input
            required
            maxLength={60}
            className="input-dark"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <button className="app-button self-end" disabled={change.isPending}>
          Liste anlegen
        </button>
      </form>
      <div className="grid gap-3 sm:grid-cols-2">
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const clean = ticker.trim().toUpperCase();
            if (!list.items.some((i) => i.ticker === clean))
              change.mutate(
                {
                  id: list.id,
                  body: {
                    name: list.name,
                    items: [
                      ...list.items,
                      {
                        ticker: clean,
                        note: "",
                        tags: [],
                        stage: "discovered",
                      },
                    ],
                  },
                },
                { onSuccess: () => setTicker("") },
              );
          }}
        >
          <Field label="Aktie hinzufügen">
            <input
              required
              pattern="[A-Za-z0-9.\^=\-]{1,32}"
              className="input-dark"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Ticker, z. B. NVDA"
            />
          </Field>
          <button
            className="app-button"
            disabled={change.isPending || list.items.length >= 100}
          >
            Hinzufügen
          </button>
        </form>
        <Field label="In Ticker, Notizen und Kennzeichnungen suchen">
          <input
            className="input-dark"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </Field>
      </div>
      <Failure error={change.error || remove.error || transfer.error} />
      <div className="grid gap-3 lg:grid-cols-2">
        {shown.map((item) => (
          <article
            key={item.ticker}
            className="rounded-xl border border-[#e3e8ef] p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`${item.ticker} auswählen`}
                  checked={picked.includes(item.ticker)}
                  onChange={(e) =>
                    setPicked(
                      e.target.checked
                        ? [...picked, item.ticker]
                        : picked.filter((t) => t !== item.ticker),
                    )
                  }
                />
                <Link
                  className="font-semibold text-teal-800"
                  href={`/stocks/${item.ticker}`}
                >
                  {item.ticker}
                </Link>
              </label>
              <span className="text-sm text-[#526174]">
                {stageLabels[item.stage]}
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm">
              {item.note || "Noch keine Notiz"}
            </p>
            <p className="mt-1 text-sm text-[#526174]">
              {item.tags.join(" · ")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link
                className="app-button"
                href={`/workspace?ticker=${item.ticker}#einstieg`}
              >
                Einstieg planen
              </Link>
              <button type="button" className="app-button" onClick={editList}>
                Notizen & Status bearbeiten
              </button>
              <button
                type="button"
                className="app-button"
                disabled={change.isPending}
                onClick={() =>
                  saveItems(list.items.filter((i) => i.ticker !== item.ticker))
                }
              >
                Entfernen
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <button
          type="button"
          className="app-button"
          onClick={() => setPicked(shown.map((i) => i.ticker))}
        >
          Sichtbare Aktien auswählen
        </button>
        <Field label="Zielliste">
          <select
            className="input-dark"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="">Liste wählen</option>
            {data.watchlists
              .filter((row) => row.id !== list.id)
              .map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
          </select>
        </Field>
        {[false, true].map((move) => (
          <button
            key={String(move)}
            type="button"
            className="app-button"
            disabled={!picked.length || !target || transfer.isPending}
            onClick={() =>
              transfer.mutate(move, { onSuccess: () => setPicked([]) })
            }
          >
            {picked.length} Aktien {move ? "verschieben" : "kopieren"}
          </button>
        ))}
      </div>
      {!shown.length && (
        <p className="text-sm text-[#526174]">
          Keine Aktien für diese Auswahl.
        </p>
      )}
      <button type="button" className="app-button" onClick={editList}>
        Liste umbenennen & gemeinsam bearbeiten
      </button>
      {list.id !== "default" && (
        <button
          type="button"
          className="app-button"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Liste „${list.name}“ samt Notizen entfernen?`))
              remove.mutate(list.id);
          }}
        >
          Liste entfernen
        </button>
      )}
      {draft && (
        <form
          className="space-y-3 rounded-xl border border-teal-300 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate(
              {
                id: draft.list.id,
                body: {
                  name: draft.list.name,
                  items: draft.list.items.map((item) => ({
                    ...item,
                    tags: (draft.tagsText[item.ticker] || "")
                      .split(",")
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  })),
                },
                revision: draft.revision,
              },
              { onSuccess: () => setDraft(null) },
            );
          }}
        >
          <h3 className="font-semibold">Liste bearbeiten</h3>
          <Field label="Listenname">
            <input
              required
              maxLength={60}
              className="input-dark"
              value={draft.list.name}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  list: { ...draft.list, name: e.target.value },
                })
              }
            />
          </Field>
          {draft.list.items.map((item, index) => (
            <div
              key={item.ticker}
              className="grid gap-2 border-t pt-3 sm:grid-cols-3"
            >
              <strong>{item.ticker}</strong>
              <Field label="Status">
                <select
                  className="input-dark"
                  value={item.stage}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      list: {
                        ...draft.list,
                        items: draft.list.items.map((r, i) =>
                          i === index
                            ? {
                                ...r,
                                stage: e.target.value as WatchItem["stage"],
                              }
                            : r,
                        ),
                      },
                    })
                  }
                >
                  {Object.entries(stageLabels)
                    .filter(([key]) => key !== "archived")
                    .map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Kennzeichnungen, mit Komma getrennt">
                <input
                  maxLength={450}
                  className="input-dark"
                  value={draft.tagsText[item.ticker] || ""}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      tagsText: {
                        ...draft.tagsText,
                        [item.ticker]: e.target.value,
                      },
                    })
                  }
                />
              </Field>
              <div className="sm:col-span-3">
                <Field label={`Notiz zu ${item.ticker}`}>
                  <textarea
                    maxLength={4000}
                    className="input-dark"
                    value={item.note}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        list: {
                          ...draft.list,
                          items: draft.list.items.map((r, i) =>
                            i === index ? { ...r, note: e.target.value } : r,
                          ),
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <button
              className="app-button app-button-primary"
              disabled={change.isPending}
            >
              Änderungen speichern
            </button>
            <button
              type="button"
              className="app-button"
              onClick={() => setDraft(null)}
            >
              Verwerfen
            </button>
          </div>
        </form>
      )}
    </Panel>
  );
}

function PlanEditor() {
  const params = useSearchParams(),
    query = useDesk(),
    data = query.data!;
  const key = [
    params.get("ticker"),
    params.get("entry"),
    params.get("currency"),
  ].join(":");
  return (
    <PlanForm
      key={key}
      initialTicker={params.get("ticker") || ""}
      initialEntry={Number(params.get("entry")) || 100}
      initialCurrency={params.get("currency") || "USD"}
      revision={data.revision}
    />
  );
}
function PlanForm({
  initialTicker,
  initialEntry,
  initialCurrency,
  revision,
}: {
  initialTicker: string;
  initialEntry: number;
  initialCurrency: string;
  revision: number;
}) {
  const data = useDesk().data!;
  const [input, setInput] = useState<PlanInput>({
    ticker: initialTicker,
    entry: initialEntry,
    stop: Math.round(initialEntry * 0.93 * 100) / 100,
    currency: /^[A-Z]{3}$/.test(initialCurrency) ? initialCurrency : "USD",
    account_id: "main",
    risk_pct: 1,
    fees: 0,
    target: null,
    thesis: "",
    invalidation: "",
  });
  const preview = useMutation({ mutationFn: deskApi.previewPlan });
  const save = useDeskChange(() =>
    deskApi.createPlan(input, revision, preview.data!.preview_hash),
  );
  const [dirty, setDirty] = useState(false);
  useUiDraft(dirty);
  function update(value: Partial<PlanInput>) {
    setInput((current) => ({ ...current, ...value }));
    preview.reset();
    setDirty(true);
  }
  const p = preview.data;
  return (
    <Panel title="Einstieg planen" id="einstieg">
      <p className="text-sm text-[#526174]">
        Kaufplan mit Risikobudget und verfügbarem Cash. Der Gebührenbetrag dient
        als gesamte Kostenreserve für Einstieg und Ausstieg. Das Speichern
        dokumentiert die Entscheidung und führt keine Order aus.
      </p>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          preview.mutate(input);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Aktie">
            <input
              required
              pattern="[A-Z0-9.\^=\-]{1,32}"
              className="input-dark"
              value={input.ticker}
              onChange={(e) => update({ ticker: e.target.value.toUpperCase() })}
            />
          </Field>
          <Field label="Depot">
            <select
              className="input-dark"
              value={input.account_id}
              onChange={(e) => update({ account_id: e.target.value })}
            >
              <option value="main">Bestehendes Depot</option>
              {data.accounts.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kurswährung">
            <input
              required
              pattern="[A-Z]{3}"
              maxLength={3}
              className="input-dark"
              value={input.currency}
              onChange={(e) =>
                update({ currency: e.target.value.toUpperCase() })
              }
            />
          </Field>
          {(
            [
              ["entry", "Einstieg"],
              ["stop", "Stopp"],
              ["risk_pct", "Maximales Depotrisiko (%)"],
              ["fees", "Gebühren in Kurswährung"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <input
                required
                type="number"
                min={key === "fees" ? 0 : 0.000001}
                max={key === "risk_pct" ? 5 : 1e9}
                step="any"
                className="input-dark"
                value={input[key]}
                onChange={(e) => update({ [key]: Number(e.target.value) })}
              />
            </Field>
          ))}
          <Field label="Kursziel (optional)">
            <input
              type="number"
              min="0.000001"
              step="any"
              className="input-dark"
              value={input.target ?? ""}
              onChange={(e) =>
                update({
                  target: e.target.value ? Number(e.target.value) : null,
                })
              }
            />
          </Field>
        </div>
        <Field label="Begründung des Einstiegs">
          <textarea
            required
            maxLength={8000}
            className="input-dark"
            value={input.thesis}
            onChange={(e) => update({ thesis: e.target.value })}
          />
        </Field>
        <Field label="Wann ist die Annahme widerlegt?">
          <textarea
            required
            maxLength={4000}
            className="input-dark"
            value={input.invalidation}
            onChange={(e) => update({ invalidation: e.target.value })}
          />
        </Field>
        <button
          className="app-button"
          disabled={preview.isPending || save.isPending}
        >
          {preview.isPending ? "Wird geprüft …" : "Plan berechnen"}
        </button>
        <Failure error={preview.error || save.error} />
        {p && (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Geplante Stückzahl" value={String(p.shares)} />
              <Metric
                label="Geplantes Verlustrisiko"
                value={`${money(p.planned_risk, p.account_currency)} · ${percent(p.planned_risk_pct)}`}
              />
              <Metric
                label="Benötigtes Cash"
                value={money(p.cash_required, p.account_currency)}
              />
              <Metric
                label="Depotrisiko nach Einstieg"
                value={percent(p.portfolio_risk_pct)}
              />
              <Metric
                label="Positionsgewicht"
                value={percent(p.position_weight_pct)}
              />
              <Metric
                label="Chance / Risiko"
                value={
                  p.reward_risk?.toLocaleString("de-DE") ?? "Kein Kursziel"
                }
              />
            </div>
            <p className="text-sm text-[#526174]">
              1 {p.quote_currency} ={" "}
              {p.fx_rate.toLocaleString("de-DE", { maximumFractionDigits: 6 })}{" "}
              {p.account_currency} · Wechselkursstand {p.fx_as_of} · Begrenzung:{" "}
              {p.limited_by === "cash" ? "verfügbares Cash" : "Risikobudget"}
            </p>
            <p className="text-sm">
              Stoppverluste sind modelliert; Kurslücken und Ausführungskosten
              können das Risiko erhöhen. Ein unbekanntes bestehendes Stopprisiko
              bleibt als solches sichtbar.
            </p>
            <button
              type="button"
              className="app-button app-button-primary"
              disabled={save.isPending || p.shares < 1}
              onClick={() =>
                save.mutate(undefined, {
                  onSuccess: () => {
                    setDirty(false);
                    preview.reset();
                  },
                })
              }
            >
              Plan mit damaliger Bewertung dokumentieren
            </button>
          </div>
        )}
        {save.isSuccess && (
          <p role="status" className="text-sm text-teal-800">
            Plan dokumentiert. Er ist unter „Meine Einstiegspläne“ verfügbar.
          </p>
        )}
      </form>
    </Panel>
  );
}
function Plans() {
  const data = useDesk().data!,
    [notes, setNotes] = useState<Record<string, string>>({});
  const change = useDeskChange(({ id, stage }: { id: string; stage: Stage }) =>
    deskApi.planStage(id, stage, notes[id] || "", data.revision),
  );
  return (
    <Panel title="Meine Einstiegspläne" id="plaene">
      <Failure error={change.error} />
      {!data.plans.length && (
        <p className="text-sm text-[#526174]">
          Noch keine dokumentierten Pläne.
        </p>
      )}
      {data.plans.map((plan) => (
        <article
          key={plan.id}
          className="space-y-3 rounded-xl border border-[#e3e8ef] p-4"
        >
          <div className="flex flex-wrap justify-between gap-2">
            <Link
              className="font-semibold text-teal-800"
              href={`/stocks/${plan.ticker}`}
            >
              {plan.ticker} · {plan.preview.shares} Stück
            </Link>
            <span className="text-sm">{stageLabels[plan.stage]}</span>
          </div>
          <p className="text-sm">
            Einstieg {money(plan.entry, plan.currency)} · Stopp{" "}
            {money(plan.stop, plan.currency)} · Risiko{" "}
            {money(plan.preview.planned_risk, plan.preview.account_currency)}
          </p>
          <p className="whitespace-pre-wrap break-words text-sm">
            {plan.thesis}
          </p>
          <p className="text-sm text-[#526174]">
            Annahme widerlegt: {plan.invalidation}
          </p>
          <details>
            <summary className="cursor-pointer text-sm font-semibold">
              Entscheidungsverlauf & damalige Bewertung
            </summary>
            <ol className="mt-3 space-y-3">
              {plan.history.map((item, index) => (
                <li key={index} className="text-sm">
                  <strong>{stageLabels[item.stage]}</strong> ·{" "}
                  {new Date(item.at).toLocaleString("de-DE")}
                  <p className="whitespace-pre-wrap break-words">{item.note}</p>
                </li>
              ))}
            </ol>
            {plan.preview.account_basis && (
              <p className="mt-3 text-sm text-[#526174]">
                Damals verwendeter Depotwert{" "}
                {money(
                  plan.preview.account_basis.total_value,
                  plan.preview.account_basis.currency,
                )}{" "}
                · Cash{" "}
                {money(
                  plan.preview.account_basis.cash,
                  plan.preview.account_basis.currency,
                )}{" "}
                · Wechselkursstand {plan.preview.fx_as_of}
              </p>
            )}
            <AssessmentSnapshot value={plan.preview.assessment} />
          </details>
          <Field label={`Prüfnotiz zu ${plan.ticker}`}>
            <textarea
              maxLength={4000}
              className="input-dark"
              value={notes[plan.id] || ""}
              onChange={(e) =>
                setNotes({ ...notes, [plan.id]: e.target.value })
              }
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            {(
              ["reviewed", "purchased", "reviewed_after", "archived"] as Stage[]
            ).map((stage) => (
              <button
                key={stage}
                type="button"
                className="app-button"
                disabled={!notes[plan.id]?.trim() || change.isPending}
                onClick={() =>
                  change.mutate(
                    { id: plan.id, stage },
                    { onSuccess: () => setNotes({ ...notes, [plan.id]: "" }) },
                  )
                }
              >
                {
                  (
                    {
                      reviewed: "Prüfung dokumentieren",
                      purchased: "Kauf dokumentieren",
                      reviewed_after: "Nachbetrachtung dokumentieren",
                      archived: "Archivieren",
                      planned: "Planung dokumentieren",
                      discovered: "Entdeckung dokumentieren",
                    } as Record<Stage, string>
                  )[stage]
                }
              </button>
            ))}
            <Link
              className="app-button"
              href={
                plan.account_id === "main"
                  ? `/trade-journal?search=${plan.ticker}`
                  : `/portfolio/accounts?account=${plan.account_id}#buchungen`
              }
            >
              Ausführungen im Journal ansehen
            </Link>
          </div>
          <p className="text-sm text-[#526174]">
            Statusänderungen sind persönliche Dokumentation. Ausführungen werden
            über das Depot oder einen Import erfasst.
          </p>
        </article>
      ))}
    </Panel>
  );
}
