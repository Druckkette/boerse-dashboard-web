"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { MarketOverview, Opportunities, Groups } from "./home-dashboard";
import { Panel, shortDate } from "./home-ui";
import { TrendingUp, Layers3 } from "lucide-react";

export function BetaHomeDashboard() {
  const query = useQuery({ queryKey: ["beta-home"], queryFn: api.betaHome, staleTime: 60_000 });
  if (query.isLoading) return <p aria-busy="true">Marktdaten laden …</p>;
  if (!query.data) return <p role="alert">Marktdaten derzeit nicht verfügbar.</p>;
  const data = query.data;
  return <div className="space-y-5">
    <h1 className="sr-only">Beta-Startseite</h1>
    <p className="text-xs text-[#687386]">Gemeinsame Marktdaten · Stand {shortDate(data.market.session?.last_completed_as_of)} · Ansicht {new Date(data.generated_at).toLocaleString("de-DE")}</p>
    <MarketOverview data={data} />
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel icon={TrendingUp} title="Top-3-Aktien des Tages"><Opportunities data={data} /></Panel>
      <Panel icon={Layers3} title="Führende Industry Groups"><Groups data={data} /></Panel>
    </div>
    <nav aria-label="Analysefunktionen" className="flex flex-wrap gap-3 text-sm font-semibold text-[#0f766e]">
      {[["/market", "Marktübersicht"], ["/sectors", "Sektoren"], ["/industry-groups", "Industry Groups"], ["/stocks", "Aktien suchen und vergleichen"], ["/sell-check", "Aktie frei prüfen"]].map(([href, label]) => <Link key={href} href={href}>{label} →</Link>)}
    </nav>
  </div>;
}
