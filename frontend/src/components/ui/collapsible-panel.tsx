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
    <section className="rounded border border-[#2d333d] bg-[#171a20]">
      <button
        className="flex w-full flex-col gap-3 border-b border-[#2d333d] p-5 text-left transition hover:bg-[#1b2028] md:flex-row md:items-start md:justify-between"
        type="button"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <span className="flex min-w-0 items-start gap-3">
          <span className="mt-1 text-[#a0a7b4]">
            {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </span>
          <span className="min-w-0">
            <span className="block text-lg font-semibold">{title}</span>
            {subtitle ? <span className="mt-1 block text-sm leading-6 text-[#a0a7b4]">{subtitle}</span> : null}
          </span>
        </span>
        {summary ? <span className="flex shrink-0 flex-wrap gap-2 md:justify-end">{summary}</span> : null}
      </button>
      {open ? children : null}
    </section>
  );
}
