"use client";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";
import { deskApi, type DeskState } from "@/lib/desk";
import { useBetaMode } from "@/components/beta-mode-provider";

export function useDesk() {
  const beta = useBetaMode();
  return useQuery({
    queryKey: ["desk"],
    queryFn: deskApi.state,
    enabled: !beta,
    staleTime: 30_000,
  });
}
export function useDeskChange<T>(operation: (value: T) => Promise<DeskState>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: operation,
    onSuccess: async (value) => {
      client.setQueryData(["desk"], value);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["workspace"] }),
        client.invalidateQueries({ queryKey: ["home-dashboard"] }),
        client.invalidateQueries({ queryKey: ["desk-calendar"] }),
        client.invalidateQueries({ queryKey: ["desk-account"] }),
      ]);
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ["desk"] });
    },
  });
}
export function DeskLinks() {
  return (
    <nav aria-label="Arbeitsbereich" className="flex flex-wrap gap-2 text-sm">
      <Link className="app-button" href="/workspace">
        Watchlists & Pläne
      </Link>
      <Link className="app-button" href="/alerts">
        Alarmzentrale
      </Link>
      <Link className="app-button" href="/calendar">
        Kalender
      </Link>
      <Link className="app-button" href="/portfolio/performance">
        Performance
      </Link>
      <Link className="app-button" href="/portfolio/accounts">
        Weitere Depots
      </Link>
    </nav>
  );
}
export function Panel({
  title,
  children,
  id,
}: {
  title: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="dashboard-section space-y-4 scroll-mt-32">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}
export function Failure({ error }: { error: unknown }) {
  return error ? (
    <p
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      {error instanceof Error
        ? error.message
        : "Die Aktion konnte nicht abgeschlossen werden."}
    </p>
  ) : null;
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children)
        ? cloneElement(children as ReactElement<{ id: string }>, { id })
        : children}
    </div>
  );
}
export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#e3e8ef] bg-white p-4">
      <p className="text-sm text-[#526174]">{label}</p>
      <p className="mt-2 break-words text-xl font-semibold tabular-nums">
        {value}
      </p>
    </div>
  );
}
export function DateStatus({
  asOf,
  limited = false,
  children,
}: {
  asOf?: string;
  limited?: boolean;
  children?: ReactNode;
}) {
  return (
    <p className={`text-sm ${limited ? "text-amber-800" : "text-[#526174]"}`}>
      Daten bis {asOf || "unbekannt"} · Tagesdaten ·{" "}
      {limited ? "eingeschränkt" : "gespeicherter Stand"}
      {children && <> · {children}</>}
    </p>
  );
}
