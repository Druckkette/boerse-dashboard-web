"use client";
import Link from "next/link";
import type { HomeDashboard } from "@/lib/types/api";
import { useDesk } from "./shared";

export function TodayTasks({ data }: { data: HomeDashboard }) {
  const desk = useDesk();
  const tasks: { key: string; label: string; href: string; urgent: boolean }[] =
    [];
  for (const row of data.portfolio_alerts || [])
    if (row.category === "action")
      tasks.push({
        key: row.id,
        label: `${row.ticker}: ${row.label} prüfen`,
        href: row.href,
        urgent: true,
      });
  const missing =
    (data.portfolio.stop_coverage_total || 0) -
    (data.portfolio.stop_coverage_count || 0);
  if (missing > 0)
    tasks.push({
      key: "stops",
      label: `${missing} ${missing === 1 ? "Position ohne Stopp" : "Positionen ohne Stopp"} prüfen`,
      href: "/portfolio#positionen",
      urgent: true,
    });
  const pending = desk.data?.history.filter(
    (row) => !row.acknowledged_at,
  ).length;
  if (pending)
    tasks.push({
      key: "alarms",
      label: `${pending} offene ${pending === 1 ? "Alarmmeldung" : "Alarmmeldungen"}`,
      href: "/alerts",
      urgent: true,
    });
  const earnings = (data.earnings?.rows || []).filter(
    (row) =>
      row.scopes.includes("portfolio") &&
      row.days_until >= 0 &&
      row.days_until <= 3,
  );
  if (earnings.length)
    tasks.push({
      key: "earnings",
      label: `${earnings.length} Depotwerte mit Quartalszahlen in den nächsten 3 Tagen`,
      href: "/calendar",
      urgent: false,
    });
  const plans = desk.data?.plans.filter(
    (row) => row.stage === "planned",
  ).length;
  if (plans)
    tasks.push({
      key: "plans",
      label: `${plans} dokumentierte Einstiegspläne prüfen`,
      href: "/workspace#plaene",
      urgent: false,
    });
  for (const row of data.portfolio_alerts || [])
    if (row.category === "data")
      tasks.push({
        key: row.id,
        label: `${row.ticker}: Datenstand prüfen`,
        href: row.href,
        urgent: false,
      });
  return (
    <section aria-label="Heute prüfen" className="dashboard-section space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Heute prüfen</h2>
        <Link href="/workspace" className="text-sm font-semibold text-teal-800">
          Watchlists & Pläne öffnen →
        </Link>
      </div>
      {tasks.length ? (
        <ol className="grid gap-2 lg:grid-cols-2">
          {tasks.slice(0, 5).map((task, index) => (
            <li key={task.key}>
              <Link
                className={`flex min-h-11 items-center gap-3 rounded-lg border p-3 text-sm ${task.urgent ? "border-amber-200 bg-amber-50" : "border-[#e3e8ef]"}`}
                href={task.href}
              >
                <span className="font-semibold">{index + 1}</span>
                {task.label}
                <span className="ml-auto">→</span>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-[#526174]">
          Aus den geladenen Daten ergeben sich keine priorisierten Aufgaben.{" "}
          <Link href="/portfolio" className="font-semibold text-teal-800">
            Depot ansehen
          </Link>
        </p>
      )}
      {desk.isError && (
        <p className="text-sm text-amber-800">
          Eigene Pläne und Alarmmeldungen konnten nicht einbezogen werden.
        </p>
      )}
    </section>
  );
}
