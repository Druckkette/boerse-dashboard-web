"use client";

import { useEffect, useRef, useState } from "react";
import {
  BriefcaseBusiness,
  Gauge,
  Home,
  MoreHorizontal,
  Search,
  X,
  LineChart,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBetaMode } from "@/components/beta-mode-provider";

const analysis = [
  ["/market", "Marktübersicht"],
  ["/sectors", "Sektoren"],
  ["/industry-groups", "Branchen"],
  ["/stocks", "Aktien"],
];
const portfolio = [
  ["/portfolio", "Depot"],
  ["/workspace", "Watchlists & Pläne"],
  ["/alerts", "Alarmzentrale"],
  ["/calendar", "Kalender"],
  ["/portfolio/performance", "Performance"],
  ["/portfolio/accounts", "Weitere Depots"],
  ["/portfolio/buy-strength", "Stärke nach Kauf"],
  ["/sell-monitor", "Verkaufsmonitor"],
  ["/trade-journal", "Handelstagebuch"],
  ["/portfolio/imports", "TR-Import"],
];
const administration = [
  ["/research", "Forschung"],
  ["/settings", "Einstellungen"],
  ["/jobs", "Daten & System"],
];
const active = (path: string, href: string) =>
  path === href ||
  (href !== "/" && href !== "/portfolio" && path.startsWith(`${href}/`));
export function ProductSidebar() {
  const beta = useBetaMode();
  const path = usePathname();
  const groups = [
    ["Überblick", [["/", "Übersicht"]]],
    ["Markt & Analyse", analysis],
    ...(beta
      ? [["Prüfen", [["/sell-check", "Aktie frei prüfen"]]]]
      : [
          ["Mein Depot", portfolio],
          ["Verwaltung", administration],
        ]),
  ] as [string, string[][]][];
  return (
    <aside className="hidden h-dvh overflow-y-auto border-r border-[#e3e8ef] bg-white lg:sticky lg:top-0 lg:block">
      <Link
        href="/"
        className="flex min-h-20 items-center gap-3 px-5 font-semibold"
      >
        <LineChart className="size-9 rounded-xl bg-[#0f766e] p-2 text-white" />
        <span>
          Börse ohne
          <br />
          Bauchgefühl
        </span>
      </Link>
      <nav aria-label="Hauptnavigation" className="space-y-5 px-3 pb-6">
        {groups.map(([label, items]) => (
          <div key={label}>
            <p className="mb-2 px-3 text-xs font-semibold text-[#687386]">
              {label}
            </p>
            {items.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                aria-current={active(path, href) ? "page" : undefined}
                className={`flex min-h-11 items-center rounded-xl px-3 text-sm font-medium ${active(path, href) ? "bg-[#e8f4f2] text-[#0f766e]" : "text-[#526174] hover:bg-[#f5f7f9]"}`}
              >
                {label}
              </Link>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
export function ProductBottomNav() {
  const beta = useBetaMode();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!open) { element?.close(); return; }
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element?.showModal();
    return () => { element?.close(); document.body.style.overflow = overflow; };
  }, [open]);
  const items = beta
    ? ([
        ["/", "Übersicht", Home],
        ["/market", "Markt", Gauge],
        ["/stocks", "Aktien", Search],
        ["/sell-check", "Prüfen", BriefcaseBusiness],
      ] as const)
    : ([
        ["/", "Übersicht", Home],
        ["/market", "Markt", Gauge],
        ["/portfolio", "Depot", BriefcaseBusiness],
        ["/stocks", "Aktien", Search],
      ] as const);
  const more = beta
    ? analysis.filter(([href]) => href !== "/market" && href !== "/stocks")
    : [
        ...portfolio.filter(([href]) => href !== "/portfolio"),
        ...analysis.filter(
          ([href]) => href !== "/market" && href !== "/stocks",
        ),
        ...administration,
      ];
  const currentItem = items.find(([href]) => path === href || (href !== "/" && path.startsWith(`${href}/`)))?.[0];
  const moreIsCurrent = !currentItem && more.some(([href]) => active(path, href));
  return (
    <>
      <nav
        aria-label="Mobile Hauptnavigation"
        className="product-bottom-nav fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-[#d8e1ea] bg-white/95 px-1 backdrop-blur lg:hidden"
      >
        {items.map(([href, label, Icon]) => (
          <Link
            key={href}
            href={href}
            aria-current={currentItem === href ? "page" : undefined}
            className="product-bottom-nav-item"
          >
            <span className="product-bottom-nav-icon"><Icon size={20} aria-hidden="true" /></span>
            <span>{label}</span>
          </Link>
        ))}
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          data-current={moreIsCurrent || undefined}
          className="product-bottom-nav-item"
          onClick={() => setOpen(true)}
        >
          <span className="product-bottom-nav-icon"><MoreHorizontal size={20} aria-hidden="true" /></span>
          <span>Mehr</span>
        </button>
      </nav>
      <dialog
        ref={dialog}
        aria-label="Weitere Bereiche"
        onCancel={() => setOpen(false)}
        className="product-dialog m-auto max-h-[85dvh] w-[min(480px,100vw)] overflow-y-auto rounded-2xl border border-[#e3e8ef] bg-white p-4 shadow-2xl backdrop:bg-slate-900/50"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Weitere Bereiche</h2>
          <button
            type="button"
            aria-label="Menü schließen"
            className="p-3"
            onClick={() => setOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <nav aria-label="Weitere Navigation" className="grid gap-1">
          {more.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              aria-current={active(path, href) ? "page" : undefined}
              className="product-more-link rounded-lg px-3 py-3 text-sm hover:bg-[#e8f4f2]"
              onClick={() => setOpen(false)}
            >
              {label}
            </Link>
          ))}
        </nav>
      </dialog>
    </>
  );
}
