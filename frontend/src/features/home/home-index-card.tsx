import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { StatusChip } from "@/components/ui/status-chip";
import type { HomeDashboard as HomeData } from "@/lib/types/api";
import { PowerTrendBadge, powerTrendDescription } from "../market/powertrend-card";
import { marketTone, number, shortDate, signedPercent } from "./home-ui";

export function IndexCard({ index }: { index: HomeData["market"]["indices"][number] }) {
  const current = index.phase_status === "available";
  const tone = current ? marketTone(index.phase) : "neutral";
  const border = tone === "good" ? "border-t-[#138a57]" : tone === "bad" ? "border-t-[#c2413b]" : tone === "warning" ? "border-t-[#b7791f]" : "border-t-[#94a3b8]";
  const returnTone = index.change_pct == null ? "text-[#687386]" : index.change_pct >= 0 ? "text-[#138a57]" : "text-[#c2413b]";
  return <Link href={`/market?ticker=${encodeURIComponent(index.ticker)}`} className={`group rounded-xl border border-[#e3e8ef] border-t-[3px] bg-[#fbfcfd] p-4 transition hover:bg-white hover:shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f766e] ${border}`}>
    <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold text-[#172033]">{index.label}</h3><ArrowUpRight size={15} className="shrink-0 text-[#94a3b8] group-hover:text-[#0f766e]" /></div>
    <div className="mt-3 flex flex-wrap gap-2"><StatusChip tone={tone}>{index.phase_label || "Phase fehlt"}</StatusChip>{current && index.powertrend?.enabled && <PowerTrendBadge powertrend={index.powertrend} />}</div>
    <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2"><span className="text-xl font-semibold tabular-nums text-[#172033]">{number(index.close, 2)}</span><span className={`text-sm font-semibold tabular-nums ${returnTone}`}>{signedPercent(index.change_pct)}</span></div>
    <p className="mt-2 text-[11px] leading-5 text-[#687386]">{index.as_of ? `Schlusskurs ${shortDate(index.as_of)}` : "Schlusskurs fehlt"} · zum Vortag</p>
    {!current && <p className="mt-1 text-xs text-[#b7791f]">{index.phase_status === "stale" ? `Ampelstand ${shortDate(index.phase_as_of)} · veraltet` : index.phase_status === "partial" ? "Ampel: unvollständige Kursdaten" : "Ampel noch nicht verfügbar"}</p>}
    {current && index.powertrend?.enabled && index.powertrend.state !== "off" && <p className="mt-2 text-[11px] leading-4 text-[#687386]">{powerTrendDescription(index.powertrend)}</p>}
    {index.status === "partial" && <p className="mt-1 text-xs text-[#b7791f]">Vorheriger Schlusskurs fehlt</p>}
    {index.status === "stale" && <p className="mt-1 text-xs text-[#b7791f]">Kursstand veraltet</p>}
  </Link>;
}

