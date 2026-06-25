"use client";

import clsx from "clsx";
import {
  BriefcaseBusiness,
  ChartCandlestick,
  Gauge,
  LineChart,
  NotebookPen,
  NotebookTabs,
  Search,
  Settings,
  Shield,
  TrendingUp
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const navItems = [
  { href: "/market", label: "Marktübersicht", icon: Gauge },
  { href: "/sectors", label: "Sektoren", icon: Shield },
  { href: "/stocks", label: "Aktien", icon: Search },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness, exact: true },
  { href: "/portfolio/buy-strength", label: "Stärke nach Kauf", icon: TrendingUp },
  { href: "/trade-journal", label: "Handelstagebuch", icon: NotebookPen },
  { href: "/sell-monitor", label: "Verkaufsmonitor", icon: ChartCandlestick },
  { href: "/workspace", label: "Workspace", icon: NotebookTabs },
  { href: "/settings", label: "Settings", icon: Settings }
];

const hiddenPageLabels = [
  { href: "/setup", label: "Setup" },
  { href: "/jobs", label: "Jobs" },
  { href: "/portfolio/imports", label: "Import" }
];

const pageDescriptions: Record<string, string> = {
  "/market": "Marktampel, Marktbreite und Frühwarnzeichen in einer ruhigen Übersicht.",
  "/sectors": "Sektorrotation und relative Stärke nach Tages- oder Wochenansicht.",
  "/stocks": "Aktien suchen, bewerten und technische sowie fundamentale Signale prüfen.",
  "/portfolio": "Depot, Risiko, Stopps und Positionsgrößen im Blick behalten.",
  "/portfolio/buy-strength": "Frische Käufe systematisch gegen die Stärke-nach-Kauf-Regeln prüfen.",
  "/trade-journal": "Kauf- und Verkaufsentscheidungen dokumentieren und später auswerten.",
  "/sell-monitor": "Verkaufsregeln, Tranchensignale und Positionszustand kontrollieren.",
  "/workspace": "Arbeitsbereich für Analysen, Notizen und vorbereitete Aktionen.",
  "/jobs": "Datenaktualisierung, Worker-Status und laufende Jobs überwachen.",
  "/settings": "Setup, Schlüssel, Datenquellen und Systemkonfiguration verwalten."
};

function isActive(pathname: string, href: string, exact = false) {
  if (href === "/") return pathname === "/";
  if (exact) return pathname === href;
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const currentPageLabel = pageLabel(pathname);
  const currentPageDescription = pageDescription(pathname);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[272px_1fr]">
      <aside className="border-b border-[#e3e8ef] bg-white/92 shadow-[8px_0_28px_rgba(15,23,42,0.03)] backdrop-blur lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex min-h-20 items-center gap-3 px-5">
          <div className="flex size-11 items-center justify-center rounded-2xl bg-[#0f766e] text-white shadow-[0_12px_24px_rgba(15,118,110,0.24)]">
            <LineChart size={20} strokeWidth={2.2} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold tracking-normal text-[#172033]">Börse ohne Bauchgefühl</div>
            <div className="mt-0.5 text-xs font-medium text-[#687386]">Regelbasiert. Ruhig. Verständlich.</div>
          </div>
        </div>
        <nav className="flex gap-2 overflow-x-auto px-3 pb-4 lg:block lg:space-y-1.5 lg:overflow-visible lg:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href, item.exact);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "group flex min-w-fit items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition",
                  active
                    ? "bg-[#e6f5f2] text-[#0f766e] shadow-[inset_0_0_0_1px_rgba(15,118,110,0.13)]"
                    : "text-[#687386] hover:bg-[#f2f7f8] hover:text-[#172033]"
                )}
              >
                <span
                  className={clsx(
                    "grid size-8 shrink-0 place-items-center rounded-xl border transition",
                    active
                      ? "border-[#b7ddd6] bg-white text-[#0f766e]"
                      : "border-[#e3e8ef] bg-[#f9fbfd] text-[#687386] group-hover:border-[#cbd5e1] group-hover:text-[#172033]"
                  )}
                >
                  <Icon size={16} />
                </span>
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="min-w-0">
        <header className="sticky top-0 z-10 border-b border-[#e3e8ef] bg-white/86 px-4 py-4 backdrop-blur md:px-7">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="min-w-0">
              <div className="text-2xl font-semibold tracking-normal text-[#172033]">{currentPageLabel}</div>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[#687386]">{currentPageDescription}</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Link
                href="/stocks"
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-[#d8e1ea] bg-white px-4 text-sm font-medium text-[#172033] shadow-sm transition hover:border-[#b8c4d2] hover:bg-[#f9fbfd]"
              >
                <Search size={16} className="text-[#687386]" />
                Ticker oder Firma suchen
              </Link>
              <Link
                href="/jobs"
                className="inline-flex min-h-11 items-center justify-center rounded-full bg-[#0f766e] px-5 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(15,118,110,0.18)] transition hover:bg-[#0b655f]"
              >
                Datenstatus prüfen
              </Link>
            </div>
          </div>
        </header>
        <div className="px-4 py-6 md:px-7">{children}</div>
      </main>
    </div>
  );
}

function pageLabel(pathname: string) {
  const hiddenMatch = [...hiddenPageLabels]
    .sort((left, right) => right.href.length - left.href.length)
    .find((item) => pathname.startsWith(item.href));
  if (hiddenMatch) return hiddenMatch.label;
  const match = [...navItems]
    .sort((left, right) => right.href.length - left.href.length)
    .find((item) => isActive(pathname, item.href, item.exact));
  if (match) return match.label;
  if (pathname === "/") return "Market";
  return "Workspace";
}

function pageDescription(pathname: string) {
  const match = Object.entries(pageDescriptions)
    .sort((left, right) => right[0].length - left[0].length)
    .find(([href]) => pathname.startsWith(href));
  return match?.[1] ?? "Regelbasierter Überblick über Markt, Portfolio und Entscheidungen.";
}
