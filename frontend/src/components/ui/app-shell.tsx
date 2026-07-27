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
import { HeaderTools } from "@/components/ui/header-tools";

const navItems = [
  { href: "/market", label: "Marktübersicht", icon: Gauge },
  { href: "/sectors", label: "Sektoren", icon: Shield },
  { href: "/stocks", label: "Aktien", icon: Search },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness, exact: true },
  { href: "/portfolio/buy-strength", label: "Stärke nach Kauf", icon: TrendingUp },
  { href: "/trade-journal", label: "Handelstagebuch", icon: NotebookPen },
  { href: "/sell-monitor", label: "Verkaufsmonitor", icon: ChartCandlestick },
  { href: "/workspace", label: "Heute", icon: NotebookTabs },
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
  "/workspace": "Markt, Datenqualität und Positionen mit Handlungsbedarf auf einen Blick.",
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
    <div className="min-h-screen lg:grid lg:grid-cols-[268px_1fr]">
      <aside className="border-b border-[#e3e8ef] bg-white lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
        <div className="flex min-h-16 items-center gap-2.5 px-4">
          <div className="flex size-9 items-center justify-center rounded-[10px] bg-[#0f766e] text-white shadow-[0_6px_16px_rgba(15,118,110,0.18)]">
            <LineChart size={18} strokeWidth={2.2} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-[#172033]">Börse ohne Bauchgefühl</div>
            <div className="mt-0.5 text-[11px] font-medium text-[#687386]">Regelbasiert. Ruhig. Verständlich.</div>
          </div>
        </div>
        <nav className="flex gap-1.5 overflow-x-auto px-3 pb-3 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href, item.exact);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "group flex min-w-fit items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-sm font-medium transition",
                  active
                    ? "bg-[#e8f4f2] text-[#0f766e]"
                    : "text-[#687386] hover:bg-[#f3f6f8] hover:text-[#172033]"
                )}
              >
                <span
                  className={clsx(
                    "grid size-7 shrink-0 place-items-center rounded-lg border transition",
                    active
                      ? "border-[#c8e2dd] bg-white text-[#0f766e]"
                      : "border-transparent bg-[#f5f7f9] text-[#687386] group-hover:text-[#172033]"
                  )}
                >
                  <Icon size={15} />
                </span>
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="min-w-0">
        <header className="sticky top-0 z-10 border-b border-[#e3e8ef] bg-white/92 px-4 py-3 backdrop-blur md:px-6">
          <div className="mx-auto flex max-w-[1680px] flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="min-w-0">
              <div className="text-xl font-semibold text-[#172033]">{currentPageLabel}</div>
              <p className="mt-0.5 max-w-3xl text-xs leading-5 text-[#687386] sm:text-sm">{currentPageDescription}</p>
            </div>
            <HeaderTools />
          </div>
        </header>
        <div className="mx-auto max-w-[1680px] px-4 py-4 md:px-6 md:py-5">{children}</div>
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
