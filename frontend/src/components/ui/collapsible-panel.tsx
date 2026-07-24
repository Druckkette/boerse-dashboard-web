"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

type CollapsiblePanelProps = {
  title: string;
  subtitle?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary?: ReactNode;
  children: ReactNode;
};

export function CollapsiblePanel({
  title,
  subtitle,
  open,
  onOpenChange,
  summary,
  children
}: CollapsiblePanelProps) {
  return (
    <section className="overflow-hidden rounded-[14px] border border-[#e3e8ef] bg-white shadow-[0_5px_18px_rgba(15,23,42,0.05)]">
      <button
        className={open
          ? "flex w-full flex-col gap-2.5 border-b border-[#e3e8ef] px-4 py-3 text-left transition hover:bg-[#f9fbfd] md:flex-row md:items-center md:justify-between"
          : "flex w-full flex-col gap-2.5 px-4 py-3 text-left transition hover:bg-[#f9fbfd] md:flex-row md:items-center md:justify-between"}
        type="button"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-7 shrink-0 place-items-center rounded-lg border border-[#e3e8ef] bg-[#f9fbfd] text-[#687386]">
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
          <span className="min-w-0">
            <span className="block text-base font-semibold text-[#172033]">{title}</span>
            {subtitle ? <span className="mt-0.5 block text-xs leading-5 text-[#687386]">{subtitle}</span> : null}
          </span>
        </span>
        {summary ? <span className="flex shrink-0 flex-wrap gap-1.5 md:justify-end">{summary}</span> : null}
      </button>
      {open ? children : null}
    </section>
  );
}
