"use client";

import clsx from "clsx";
import {
  BriefcaseBusiness,
  ChartCandlestick,
  Gauge,
  LineChart,
  ListChecks,
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
  { href: "/market", label: "Market", icon: Gauge },
  { href: "/sectors", label: "Sectors", icon: Shield },
  { href: "/stocks", label: "Stocks", icon: Search },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness, exact: true },
  { href: "/portfolio/buy-strength", label: "Stärke nach Kauf", icon: TrendingUp },
  { href: "/trade-journal", label: "Handelstagebuch", icon: NotebookPen },
  { href: "/sell-monitor", label: "Sell Monitor", icon: ChartCandlestick },
  { href: "/workspace", label: "Workspace", icon: NotebookTabs },
  { href: "/jobs", label: "Jobs", icon: ListChecks },
  { href: "/settings", label: "Settings", icon: Settings }
];

const hiddenPageLabels = [
  { href: "/setup", label: "Setup" },
  { href: "/portfolio/imports", label: "Import" }
];

function isActive(pathname: string, href: string, exact = false) {
  if (href === "/") return pathname === "/";
  if (exact) return pathname === href;
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const currentPageLabel = pageLabel(pathname);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="border-b border-[#2d333d] bg-[#111419]/95 lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center gap-3 px-5">
          <div className="flex size-9 items-center justify-center rounded bg-emerald-400 text-[#0f1115]">
            <LineChart size={20} strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wide">Börse ohne Bauchgefühl</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href, item.exact);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex min-w-fit items-center gap-3 rounded px-3 py-2 text-sm transition",
                  active
                    ? "bg-[#26333a] text-emerald-200"
                    : "text-[#a0a7b4] hover:bg-[#1b2027] hover:text-white"
                )}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="min-w-0">
        <header className="sticky top-0 z-10 flex min-h-16 items-center border-b border-[#2d333d] bg-[#0f1115]/90 px-4 backdrop-blur md:px-7">
          <div>
            <div className="text-base font-semibold">{currentPageLabel}</div>
          </div>
        </header>
        <div className="px-4 py-5 md:px-7">{children}</div>
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
