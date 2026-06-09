"use client";

import clsx from "clsx";
import {
  Activity,
  BriefcaseBusiness,
  ChartCandlestick,
  Gauge,
  Home,
  LineChart,
  ListChecks,
  Search,
  Settings,
  Upload
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Dashboard", icon: Home },
  { href: "/market", label: "Market", icon: Gauge },
  { href: "/stocks", label: "Stocks", icon: Search },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness },
  { href: "/portfolio/imports", label: "Imports", icon: Upload },
  { href: "/sell-monitor", label: "Sell Monitor", icon: ChartCandlestick },
  { href: "/jobs", label: "Jobs", icon: ListChecks },
  { href: "/settings", label: "Settings", icon: Settings }
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="border-b border-[#2d333d] bg-[#111419]/95 lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center gap-3 px-5">
          <div className="flex size-9 items-center justify-center rounded bg-emerald-400 text-[#0f1115]">
            <LineChart size={20} strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wide">Boerse Web</div>
            <div className="text-xs text-[#a0a7b4]">API-first Dashboard</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-1 lg:overflow-visible lg:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
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
        <header className="sticky top-0 z-10 flex min-h-16 items-center justify-between border-b border-[#2d333d] bg-[#0f1115]/90 px-4 backdrop-blur md:px-7">
          <div>
            <div className="text-xs uppercase text-[#a0a7b4]">Migration Phase 4/5</div>
            <div className="text-base font-semibold">Trading Workspace</div>
          </div>
          <div className="flex items-center gap-2 rounded border border-[#2d333d] bg-[#171a20] px-3 py-2 text-xs text-[#a0a7b4]">
            <Activity size={15} className="text-emerald-300" />
            Worker-ready scaffold
          </div>
        </header>
        <div className="px-4 py-5 md:px-7">{children}</div>
      </main>
    </div>
  );
}
