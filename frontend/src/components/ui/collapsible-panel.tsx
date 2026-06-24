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
    <section className="overflow-hidden rounded-[24px] border border-[#e3e8ef] bg-white shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
      <button
        className="flex w-full flex-col gap-3 border-b border-[#e3e8ef] p-5 text-left transition hover:bg-[#f9fbfd] md:flex-row md:items-start md:justify-between"
        type="button"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span className="flex min-w-0 items-start gap-3">
          <span className="mt-1 grid size-8 shrink-0 place-items-center rounded-full border border-[#e3e8ef] bg-[#f9fbfd] text-[#687386]">
            {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </span>
          <span className="min-w-0">
            <span className="block text-lg font-semibold text-[#172033]">{title}</span>
            {subtitle ? <span className="mt-1 block text-sm leading-6 text-[#687386]">{subtitle}</span> : null}
          </span>
        </span>
        {summary ? <span className="flex shrink-0 flex-wrap gap-2 md:justify-end">{summary}</span> : null}
      </button>
      {open ? children : null}
    </section>
  );
}
