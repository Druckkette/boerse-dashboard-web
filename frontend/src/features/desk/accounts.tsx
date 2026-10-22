"use client";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QueryState } from "@/components/ui/query-state";
import { deskApi, money } from "@/lib/desk";
import {
  DeskLinks,
  Failure,
  Field,
  Metric,
  Panel,
  useDesk,
  useDeskChange,
} from "./shared";

const template =
  "date,type,ticker,shares,price,currency,fees,tax,amount,external_id\n2026-01-02,deposit,,,,EUR,0,0,10000,deposit-1\n2026-01-05,buy,SAP.DE,5,200,EUR,1,0,,buy-1\n";
export function Accounts() {
  const params = useSearchParams();
  const desk = useDesk(),
    [selected, setSelected] = useState(params.get("account") || "main"),
    [input, setInput] = useState({ name: "", currency: "EUR", broker: "" });
  const create = useDeskChange(() =>
    deskApi.save("accounts", input, desk.data!.revision),
  );
  const query = useQuery({
    queryKey: ["desk-account", selected],
    queryFn: () => deskApi.account(selected),
    staleTime: 30_000,
  });
  const data = query.data;
  const overview = useQuery({
    queryKey: ["desk-account", "overview", desk.data?.revision],
    queryFn: deskApi.overview,
    staleTime: 60_000,
  });
  function downloadTemplate() {
    const url = URL.createObjectURL(
      new Blob([template], { type: "text/csv;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "depot-import-vorlage.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="space-y-5">
      <DeskLinks />
      <Panel title="Depots verwalten">
        <div className="grid gap-3 sm:grid-cols-2">
          <Metric
            label="Alle Depots zusammen (EUR)"
            value={money(overview.data?.total_value, "EUR")}
          />
          <Metric
            label="Erfasste Depots"
            value={String((desk.data?.accounts.length ?? 0) + 1)}
          />
        </div>
        <Failure error={overview.error} />
        {!!overview.data?.missing.length && (
          <p className="text-sm text-amber-800">
            Die konsolidierte Bewertung ist unvollständig. Mindestens ein Depot
            oder dessen Wechselkurs ist nicht bewertbar.
          </p>
        )}
        <Failure error={desk.error || create.error} />
        <div className="flex flex-wrap gap-2">
          <button
            className="app-button"
            type="button"
            aria-pressed={selected === "main"}
            onClick={() => setSelected("main")}
          >
            Bestehendes Depot
          </button>
          {desk.data?.accounts.map((row) => (
            <button
              key={row.id}
              type="button"
              className="app-button"
              aria-pressed={selected === row.id}
              onClick={() => setSelected(row.id)}
            >
              {row.name} · {row.currency}
            </button>
          ))}
        </div>
        <form
          className="grid items-end gap-3 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(undefined, {
              onSuccess: () => setInput({ ...input, name: "", broker: "" }),
            });
          }}
        >
          <Field label="Neues Depot">
            <input
              required
              maxLength={80}
              className="input-dark"
              value={input.name}
              onChange={(e) => setInput({ ...input, name: e.target.value })}
            />
          </Field>
          <Field label="Basiswährung">
            <input
              required
              pattern="[A-Z]{3}"
              maxLength={3}
              className="input-dark"
              value={input.currency}
              onChange={(e) =>
                setInput({ ...input, currency: e.target.value.toUpperCase() })
              }
            />
          </Field>
          <Field label="Broker / Strategie">
            <input
              maxLength={80}
              className="input-dark"
              value={input.broker}
              onChange={(e) => setInput({ ...input, broker: e.target.value })}
            />
          </Field>
          <button
            className="app-button"
            disabled={!desk.data || create.isPending}
          >
            Depot anlegen
          </button>
        </form>
      </Panel>
      <Panel title={data?.name || "Depotübersicht"}>
        <QueryState
          loading={query.isLoading}
          error={query.error}
          hasData={Boolean(data)}
          onRetry={() => query.refetch()}
        />
        {data && (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <Metric
                label="Depotwert"
                value={money(data.total_value, data.currency)}
              />
              <Metric label="Cash" value={money(data.cash, data.currency)} />
              <Metric
                label="Offene Positionen"
                value={String(data.positions.length)}
              />
            </div>
            {!!data.missing?.length && (
              <p role="status" className="text-sm text-amber-800">
                Bewertung eingeschränkt: {data.missing.join(", ")}. Fehlende
                Kurse und Wechselkurse werden nicht als Null bewertet.
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {data.positions.map((row) => (
                <article
                  key={row.ticker}
                  className="rounded-xl border p-4 text-sm"
                >
                  <Link
                    href={`/stocks/${row.ticker}`}
                    className="font-semibold text-teal-800"
                  >
                    {row.ticker}
                  </Link>
                  <p>
                    {row.shares.toLocaleString("de-DE")} Stück ·{" "}
                    {money(row.market_value, data.currency)}
                  </p>
                  <p className="text-[#526174]">
                    Kurs {money(row.current_price, row.currency)} · Stand{" "}
                    {row.price_as_of || "fehlt"}
                  </p>
                </article>
              ))}
            </div>
            {selected === "main" ? (
              <Link className="app-button" href="/portfolio">
                Bestehendes Depot öffnen
              </Link>
            ) : (
              <>
                <h3 id="buchungen" className="scroll-mt-32 font-semibold">
                  Letzte Buchungen
                </h3>
                {data.transactions.slice(0, 30).map((row) => (
                  <p key={row.id} className="border-t py-2 text-sm">
                    {row.date} ·{" "}
                    {(
                      {
                        buy: "Kauf",
                        sell: "Verkauf",
                        deposit: "Einzahlung",
                        withdrawal: "Auszahlung",
                        dividend: "Dividende",
                        fee: "Gebühr",
                        split: "Split",
                      } as Record<string, string>
                    )[row.type] || row.type}{" "}
                    · {row.ticker} ·{" "}
                    {row.shares
                      ? `${row.shares.toLocaleString("de-DE")} Stück · ${money(row.price, row.currency)}`
                      : money(row.amount, row.currency)}
                  </p>
                ))}
              </>
            )}
          </>
        )}
      </Panel>
      <Panel title="Brokerübergreifender CSV-Import">
        <p className="text-sm text-[#526174]">
          Zusätzliche Depots führen jeweils eigene Bestände und Cashbuchungen.
          Passe Exporte anderer Broker an die Vorlage an. Für Trade Republic im
          bestehenden Depot steht weiterhin der bisherige Import zur Verfügung.
        </p>
        <button className="app-button" type="button" onClick={downloadTemplate}>
          CSV-Vorlage herunterladen
        </button>
        <p className="text-sm">
          Unterstützt: buy, sell, deposit, withdrawal, dividend, fee, split. Bei
          split enthält shares den neuen Gesamtbestand. date im Format
          JJJJ-MM-TT, ISO-Währung, positive Beträge, Dezimalpunkt. Für
          identische Buchungen jeweils eine eindeutige external_id vergeben.
          Doppelte IDs werden erkannt.
        </p>
        {selected === "main" ? (
          <Link className="app-button" href="/portfolio/imports">
            Zum Trade-Republic-Import
          </Link>
        ) : (
          desk.data && (
            <AccountImport
              key={selected}
              accountId={selected}
              revision={desk.data.revision}
            />
          )
        )}
      </Panel>
    </div>
  );
}
function AccountImport({
  accountId,
  revision,
}: {
  accountId: string;
  revision: number;
}) {
  const client = useQueryClient();
  const [csv, setCsv] = useState(""),
    [fileError, setFileError] = useState(""),
    [checkedRevision, setCheckedRevision] = useState<number | null>(null);
  const query = useDesk();
  const preview = useMutation({
    mutationFn: () => deskApi.importAccount(accountId, csv, revision),
    onSuccess: () => setCheckedRevision(revision),
  });
  const save = useMutation({
    mutationFn: () =>
      deskApi.importAccount(
        accountId,
        csv,
        checkedRevision!,
        true,
        preview.data!.preview_hash,
      ),
    onSuccess: async () => {
      await query.refetch();
      await Promise.all([
        client.invalidateQueries({ queryKey: ["desk-account"] }),
        client.invalidateQueries({ queryKey: ["desk-performance"] }),
      ]);
      preview.reset();
      setCsv("");
    },
  });
  return (
    <div className="space-y-3">
      <Field label="CSV-Datei auswählen">
        <input
          type="file"
          accept=".csv,text/csv,text/plain"
          className="input-dark"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            if (file.size > 2_000_000) {
              setFileError("Die CSV-Datei darf höchstens 2 MB groß sein.");
              return;
            }
            setFileError("");
            setCsv(await file.text());
            preview.reset();
            save.reset();
          }}
        />
      </Field>
      <Field label="CSV-Inhalt">
        <textarea
          className="input-dark min-h-40 font-mono"
          maxLength={2_000_000}
          value={csv}
          onChange={(e) => {
            setCsv(e.target.value);
            preview.reset();
            save.reset();
          }}
        />
      </Field>
      <Failure
        error={fileError ? new Error(fileError) : preview.error || save.error}
      />
      <button
        className="app-button"
        disabled={!csv.trim() || preview.isPending || save.isPending}
        type="button"
        onClick={() => preview.mutate()}
      >
        Import prüfen
      </button>
      {preview.data && (
        <div className="space-y-3">
          <p className="text-sm">
            {preview.data.count} Zeilen · {preview.data.added} neue Buchungen ·{" "}
            {preview.data.duplicates} bereits vorhanden
          </p>
          <div className="max-h-64 overflow-auto">
            {preview.data.rows.map((row, index) => (
              <p key={index} className="border-t py-2 text-sm">
                {row.date} · {row.type} · {row.ticker} · {row.shares} ·{" "}
                {row.price} {row.currency} · Betrag {row.amount} · Gebühren{" "}
                {row.fees ?? 0} · Steuern {row.tax ?? 0} · ID {row.id}
              </p>
            ))}
          </div>
          <button
            type="button"
            className="app-button app-button-primary"
            disabled={save.isPending || preview.data.added === 0}
            onClick={() => save.mutate()}
          >
            Geprüfte Buchungen übernehmen
          </button>
        </div>
      )}
      {save.isSuccess && (
        <p role="status" className="text-sm text-teal-800">
          Buchungen übernommen. Die Depotbewertung wird mit gespeicherten Kursen
          aktualisiert.
        </p>
      )}
    </div>
  );
}
