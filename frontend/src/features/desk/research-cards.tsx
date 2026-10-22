"use client";
import Link from "next/link";
import type { StockScreeningItem, RsRatingItem } from "@/lib/types/api";
import { StatusChip } from "@/components/ui/status-chip";
export function ScreeningCards({ rows }: { rows: StockScreeningItem[] }) {
  return (
    <div className="stock-research-cards grid gap-3 p-3 lg:hidden">
      {rows.map((row) => (
        <article className="space-y-3 rounded-xl border p-4" key={row.ticker}>
          <div className="flex items-start justify-between gap-2">
            <div>
              <Link
                className="font-semibold text-teal-800"
                href={`/stocks/${row.ticker}`}
              >
                {row.ticker}
              </Link>
              <p className="mt-1 break-words text-sm text-[#526174]">
                {row.name}
              </p>
            </div>
            <StatusChip
              tone={
                row.overall_status === "limited" ? "warning" : row.verdict_tone
              }
            >
              {row.overall_score} · {row.verdict_label}
            </StatusChip>
          </div>
          <p className="text-sm">
            RS {row.rs_rating ?? "Fehlt"} · {row.warnings_count} Warnungen
          </p>
          {row.top_warning && (
            <p className="text-sm text-amber-800">{row.top_warning}</p>
          )}
          <p
            className={`text-sm ${row.prices_stale ? "text-amber-800" : "text-[#526174]"}`}
          >
            Kursstand {row.as_of}
            {row.prices_stale ? " · veraltet" : ""}
            {row.overall_status === "limited"
              ? ` · Abdeckung ${Math.round((row.available_weight ?? 0) * 100)} %`
              : ""}
          </p>
          <details>
            <summary className="cursor-pointer text-sm font-semibold">
              Alle Teilbewertungen & Daten
            </summary>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              {[
                ["Technisch", row.technical_score],
                [
                  "Fundamental",
                  row.fundamentals_available ? row.fundamental_score : "Fehlen",
                ],
                ["Gleitende Durchschnitte", row.moving_average_score],
                ["Chart", row.chart_behavior_score],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-[#526174]">{label}</dt>
                  <dd className="font-semibold">
                    {typeof value === "number"
                      ? value.toLocaleString("de-DE", {
                          maximumFractionDigits: 1,
                        })
                      : value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-sm text-amber-800">
              {[
                !row.fundamentals_available && "Fundamentaldaten fehlen",
                !row.rs_line_available && "RS-Linie fehlt",
                !row.institutional_available && "13F fehlen",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </details>
        </article>
      ))}
    </div>
  );
}
export function RsCards({ rows }: { rows: RsRatingItem[] }) {
  return (
    <div className="stock-research-cards grid gap-3 p-3 lg:hidden">
      {rows.map((row) => (
        <article key={row.ticker} className="space-y-2 rounded-xl border p-4">
          <div className="flex justify-between gap-2">
            <Link
              href={`/stocks/${row.ticker}`}
              className="font-semibold text-teal-800"
            >
              {row.ticker}
            </Link>
            <span className="font-semibold">RS {row.rating ?? "Fehlt"}</span>
          </div>
          <p className="break-words text-sm text-[#526174]">{row.name}</p>
          <p className="text-sm">Stand {row.date}</p>
          <details>
            <summary className="cursor-pointer text-sm font-semibold">
              Renditen & Einordnung
            </summary>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              {[
                ["3 Monate", row.ret_3m],
                ["6 Monate", row.ret_6m],
                ["Mehrertrag vs. SPY · 6 Monate", row.excess_return_6m],
                ["Perzentil", row.percentile],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <dt className="text-[#526174]">{label}</dt>
                  <dd>
                    {typeof value === "number"
                      ? `${value.toLocaleString("de-DE", { maximumFractionDigits: 2 })} %`
                      : "Nicht verfügbar"}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-sm">
              RS-Hoch:{" "}
              {row.new_high_52w
                ? "Neu erreicht"
                : row.near_high_52w
                  ? "In der Nähe"
                  : "Nicht in der Nähe"}
            </p>
          </details>
        </article>
      ))}
    </div>
  );
}
